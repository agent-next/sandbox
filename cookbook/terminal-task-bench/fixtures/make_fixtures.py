#!/usr/bin/env python3
"""Generate the ten terminal-task-bench fixtures from a seed.

For every task id this writes, into --out <DIR>:

    <DIR>/<task>/task.md        copied from the committed fixtures tree
    <DIR>/<task>/verify.sh      copied from the committed fixtures tree
    <DIR>/<task>/expected.json  the literal intent, written by this script
    <DIR>/<task>/work/          the pristine *broken* filesystem

`expected.json` is the oracle: the verifier compares the repaired tree
against these literals, never against "the repair command succeeded".

Deterministic: two runs with the same --seed produce byte-identical trees
and byte-identical expected.json (fixed git identity and dates, fixed file
mtimes, fixed tar metadata, no timestamps of the moment).

Standard library only, plus git / sqlite3 / tar on PATH. Run it with -I.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import random
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import tarfile
import tempfile

EPOCH = 1700000000  # fixed mtime for every generated file
GIT_ENV = {
    "GIT_AUTHOR_NAME": "bench",
    "GIT_AUTHOR_EMAIL": "bench@example.invalid",
    "GIT_COMMITTER_NAME": "bench",
    "GIT_COMMITTER_EMAIL": "bench@example.invalid",
    "GIT_AUTHOR_DATE": "@1700000000 +0000",
    "GIT_COMMITTER_DATE": "@1700000000 +0000",
    "GIT_CONFIG_NOSYSTEM": "1",
    "HOME": "/nonexistent-bench-home",
}

TASKS = [
    "wal-repair",
    "git-lost-branch",
    "systemd-unit",
    "perms-maze",
    "csv-normalize",
    "json-config",
    "symlink-maze",
    "tar-restore",
    "bugfix-python",
    "cron-repair",
]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write(path: str, data, mode: int = 0o644) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)
    os.chmod(path, mode)
    os.utime(path, (EPOCH, EPOCH))


def freeze_mtimes(root: str) -> None:
    for dirpath, dirnames, filenames in os.walk(root):
        for name in list(dirnames) + list(filenames):
            p = os.path.join(dirpath, name)
            try:
                os.utime(p, (EPOCH, EPOCH), follow_symlinks=False)
            except (NotImplementedError, OSError):
                pass


def git(cwd: str, *args: str) -> str:
    env = dict(os.environ)
    env.update(GIT_ENV)
    proc = subprocess.run(["git", *args], cwd=cwd, env=env,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


# --------------------------------------------------------------------------
# 1. wal-repair
# --------------------------------------------------------------------------
def gen_wal_repair(work: str, rng: random.Random) -> dict:
    """A WAL-mode SQLite database whose WAL header checksum was torn.

    Committed rows written after the last checkpoint live only in the WAL.
    With the WAL header checksum zeroed, SQLite ignores the whole WAL and
    the rows disappear; the database still opens, so the loss is silent.
    """
    dbfile = os.path.join(work, "app.db")
    os.makedirs(work, exist_ok=True)
    n_orders = 40 + rng.randrange(0, 10)
    n_audit = 5 + rng.randrange(0, 4)
    n_late_orders = 3 + rng.randrange(0, 2)
    n_late_audit = 2

    con = sqlite3.connect(dbfile)
    con.execute("pragma page_size=4096")
    con.execute("create table orders(id integer primary key, sku text, qty integer)")
    con.execute("create table audit(seq integer primary key, action text, who text)")
    con.executemany("insert into orders values(?,?,?)",
                    [(i, f"SKU-{i:04d}", (i * 7) % 19) for i in range(1, n_orders + 1)])
    con.executemany("insert into audit values(?,?,?)",
                    [(i, "seed", f"user{i % 4}") for i in range(1, n_audit + 1)])
    con.commit()
    con.execute("pragma journal_mode=wal")
    con.execute("pragma wal_checkpoint(TRUNCATE)")

    late_orders = [(n_orders + i, f"SKU-{n_orders + i:04d}", (i * 3) % 19)
                   for i in range(1, n_late_orders + 1)]
    late_audit = [(n_audit + i, "restock", f"user{i % 4}")
                  for i in range(1, n_late_audit + 1)]
    for row in late_orders:
        con.execute("insert into orders values(?,?,?)", row)
        con.commit()
    for row in late_audit:
        con.execute("insert into audit values(?,?,?)", row)
        con.commit()

    # the intent, read from the live database before it is damaged, and the
    # raw db+wal bytes, both snapshotted while the connection still holds
    # the WAL open (closing it checkpoints and removes the -wal file)
    orders = con.execute("select id, sku, qty from orders order by id").fetchall()
    audit = con.execute("select seq, action, who from audit order by seq").fetchall()
    db_bytes = open(dbfile, "rb").read()
    wal_bytes = open(dbfile + "-wal", "rb").read()
    con.close()

    if len(wal_bytes) <= 32:
        raise RuntimeError("fixture bug: nothing committed to the WAL")

    torn = bytearray(wal_bytes)
    torn[24:32] = b"\x00" * 8          # torn WAL header checksum
    write(dbfile, bytes(db_bytes))
    write(dbfile + "-wal", bytes(torn))
    shm = dbfile + "-shm"
    if os.path.exists(shm):
        os.remove(shm)

    # What an untouched tree shows, measured on a throwaway copy: opening
    # the fixture itself would checkpoint it and delete the torn WAL we just
    # wrote, destroying the task.
    probe_dir = tempfile.mkdtemp()
    visible = None
    try:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(dbfile + suffix):
                shutil.copyfile(dbfile + suffix,
                                os.path.join(probe_dir, "app.db" + suffix))
        probe = subprocess.run(
            ["sqlite3", os.path.join(probe_dir, "app.db"),
             "select count(*) from orders;"], capture_output=True, text=True)
        visible = probe.stdout.strip()
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)

    return {
        "orders": [list(r) for r in orders],
        "audit": [list(r) for r in audit],
        "orders_sha256": sha256_text(json.dumps([list(r) for r in orders])),
        "audit_sha256": sha256_text(json.dumps([list(r) for r in audit])),
        "orders_rows": len(orders),
        "audit_rows": len(audit),
        "untouched_orders_rows": int(visible) if visible.isdigit() else None,
        "db": "app.db",
    }


# --------------------------------------------------------------------------
# 2. git-lost-branch
# --------------------------------------------------------------------------
def gen_git_lost_branch(work: str, rng: random.Random) -> dict:
    """A detached HEAD with a branch tip that survives only in the reflog."""
    repo = os.path.join(work, "repo")
    os.makedirs(repo, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    write(os.path.join(repo, "README.md"), "# ingest service\n\nbuild: make\n")
    write(os.path.join(repo, "src", "main.py"), "def main():\n    return 'v1'\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base commit")

    git(repo, "checkout", "-q", "-b", "feature/ingest")
    token = f"{rng.randrange(10**6):06d}"
    write(os.path.join(repo, "src", "ingest.py"),
          "def ingest(batch):\n"
          f"    \"\"\"ingest token {token}\"\"\"\n"
          "    return [row for row in batch if row]\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "feat: ingest filter")
    write(os.path.join(repo, "src", "ingest.py"),
          "def ingest(batch):\n"
          f"    \"\"\"ingest token {token}\"\"\"\n"
          "    return [row for row in batch if row]\n\n\n"
          "def batches(rows, size):\n"
          "    return [rows[i:i + size] for i in range(0, len(rows), size)]\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "feat: batch helper")

    tip = git(repo, "rev-parse", "HEAD")
    main_sha = git(repo, "rev-parse", "main")
    ingest_sha = sha256_file(os.path.join(repo, "src", "ingest.py"))
    git(repo, "checkout", "-q", "--detach", tip)
    git(repo, "branch", "-q", "-D", "feature/ingest")
    return {
        "repo": "repo",
        "branch": "feature/ingest",
        "tip": tip,
        "main_sha": main_sha,
        "ingest_file": "src/ingest.py",
        "ingest_sha256": ingest_sha,
        "token": token,
    }


# --------------------------------------------------------------------------
# 3. systemd-unit
# --------------------------------------------------------------------------
def gen_systemd_unit(work: str, rng: random.Random) -> dict:
    """A unit file no parser accepts and whose ExecStart points nowhere."""
    token = f"ready-{rng.randrange(10**6):06d}"
    prog = os.path.join(work, "usr", "local", "bin", "ingestd")
    write(prog, "#!/bin/sh\n"
                "# ingest daemon (fixture stand-in)\n"
                "case \"$1\" in\n"
                f"  --self-test) echo \"{token}\" ; exit 0 ;;\n"
                "  *) echo \"usage: ingestd --self-test\" >&2 ; exit 2 ;;\n"
                "esac\n", mode=0o755)
    unit = os.path.join(work, "etc", "systemd", "system", "ingestd.service")
    write(unit,
          "# ingestd service\n"
          "[Unit]\n"
          "Description=ingest daemon\n"
          "After=network.target\n"
          "\n"
          "[Service]\n"
          "Type=simple\n"
          "ExecStart=/usr/bin/ingestd --self-test\n"
          "Restart=on-failure\n"
          "Restart=always\n"
          "User=ingest\n"
          "WorkingDirectory=/var/lib/ingestd\n"
          "\n"
          "[Install]\n"
          "WantedBy=multi-user.target\n")
    return {
        "unit": "etc/systemd/system/ingestd.service",
        "program": "usr/local/bin/ingestd",
        "token": token,
        "exec_start_argv": ["--self-test"],
        "required_sections": ["Unit", "Service", "Install"],
        "required_service_keys": ["Type", "ExecStart", "User", "WorkingDirectory",
                                  "WantedBy"],
        "expected_user": "root",
        "expected_working_directory": "/var/lib/ingestd",
        "allowed_type": ["simple", "exec"],
        "allowed_wanted_by": ["multi-user.target"],
        "allowed_restart": ["always", "on-failure"],
    }


# --------------------------------------------------------------------------
# 4. perms-maze
# --------------------------------------------------------------------------
def gen_perms_maze(work: str, rng: random.Random) -> dict:
    """A tool tree whose mode bits stop the tool from running.

    No root is needed anywhere: the grading user owns every path but the
    mode bits deny execution, so the symptom (Permission denied) is real
    and the repair is checkable by reading modes.  The mask deliberately
    punishes the two lazy repairs: `chmod -R 777` leaves a world-writable
    path, `chmod -R 755` leaves the secret file world-readable.
    """
    token = f"run-{rng.randrange(10**6):06d}"
    secret = f"cred-{rng.randrange(10**6):06d}"
    files = {
        "opt/bench/bin/run.sh":
            (f"#!/bin/sh\n# bench runner: prints a token when it can be "
             f"executed\necho \"{token}\"\n", 0o644),
        "opt/bench/bin/helper.sh": ("#!/bin/sh\necho helper\n", 0o644),
        "opt/bench/lib/common.sh": ("#!/bin/sh\nlog() { echo \"$*\"; }\n", 0o644),
        "opt/bench/data/input.txt": ("seed input\n" * 3, 0o644),
        "opt/bench/data/private.txt": (secret + "\n", 0o644),  # leaked
        "opt/bench/README": ("bench runner tree\n", 0o644),
    }
    for rel, (body, mode) in files.items():
        write(os.path.join(work, rel), body, mode=mode)
    dirs = ["opt", "opt/bench", "opt/bench/bin", "opt/bench/lib",
            "opt/bench/data", "opt/bench/var", "opt/bench/var/scratch"]
    for rel in dirs:
        p = os.path.join(work, rel)
        os.makedirs(p, exist_ok=True)
        os.chmod(p, 0o755)
    # the second symptom: a world-writable scratch dir
    os.chmod(os.path.join(work, "opt", "bench", "var", "scratch"), 0o777)
    return {
        "runner": "opt/bench/bin/run.sh",
        "token": token,
        "scripts": ["opt/bench/bin/run.sh", "opt/bench/bin/helper.sh",
                    "opt/bench/lib/common.sh"],
        "private_file": "opt/bench/data/private.txt",
        "secret": secret,
        "world_writable_now": "opt/bench/var/scratch",
        "contents_sha256": {
            rel: sha256_text(body) for rel, (body, _) in files.items()
        },
    }



# --------------------------------------------------------------------------
# 5. csv-normalize
# --------------------------------------------------------------------------
def gen_csv_normalize(work: str, rng: random.Random) -> dict:
    """A dirty CSV that must become one exact canonical file."""
    n = 25 + rng.randrange(0, 8)
    names = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
             "golf", "hotel", "india", "juliet", "kilo", "lima"]
    rows = []
    for i in range(1, n + 1):
        name = names[(i * 3 + rng.randrange(0, 3)) % len(names)]
        rows.append((i, name, (i * 5) % 40))

    dirty = io.StringIO()
    dirty.write("# export from the legacy till, do not edit by hand\r\n")
    dirty.write("\r\n")
    dirty.write("id, name ,qty\r\n")
    for i, (rid, name, qty) in enumerate(rows):
        if i == 3:
            dirty.write(f"{rid},{name},{qty},extra-field\r\n")   # ragged
        elif i == 5:
            dirty.write(f"{rid},{name}\r\n")                     # ragged
        elif i == 7:
            dirty.write(f'{rid},"{name}, ltd",{qty}\r\n')        # quoted comma
        elif i == 9:
            dirty.write(f"  {rid} ,{name}  ,{qty}  \r\n")       # padding
        else:
            dirty.write(f"{rid},{name},{qty}\r\n")
    dirty.write("\r\n")
    dirty.write("# end of export\r\n")
    # shuffled on purpose: the repaired file must be sorted by id
    lines = dirty.getvalue().split("\r\n")
    body = [ln for ln in lines if ln and not ln.startswith("#")
            and not ln.startswith("id,")]
    rng.shuffle(body)
    broken = ("# export from the legacy till, do not edit by hand\r\n\r\n"
              "id, name ,qty\r\n" + "\r\n".join(body) + "\r\n\r\n"
              "# end of export\r\n")

    write(os.path.join(work, "in", "export.csv"), broken)
    write(os.path.join(work, "README"), "legacy till export, one file\n")

    kept = []
    for i, (rid, name, qty) in enumerate(rows):
        if i in (3, 5):
            continue                       # ragged rows are dropped
        if i == 7:
            name = f"{name}, ltd"          # the quotes come off
        kept.append((rid, name, qty))
    kept.sort(key=lambda r: r[0])

    # canonical form: RFC 4180 minimal quoting, LF line endings
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["id", "name", "qty"])
    writer.writerows(kept)
    canonical = out.getvalue()

    return {
        "input": "in/export.csv",
        "output": "out/clean.csv",
        "header": ["id", "name", "qty"],
        "rows": [list(r) for r in kept],
        "rows_count": len(kept),
        "dropped_ragged": 2,
        "quoted_rows": [list(r) for r in kept if "," in r[1]],
        "sha256": sha256_text(canonical),
        "canonical_bytes": len(canonical.encode()),
    }


# --------------------------------------------------------------------------
# 6. json-config
# --------------------------------------------------------------------------
def gen_json_config(work: str, rng: random.Random) -> dict:
    """A config file that is not valid JSON and not the documented schema."""
    ids = ["ingest", "export", "compact", "verify"]
    rng.shuffle(ids)
    weights = {"ingest": 40, "export": 20, "compact": 30, "verify": 10}
    version = f"{1 + rng.randrange(0, 3)}.{rng.randrange(0, 10)}.0"
    name = "bench-pipeline"
    retries = 3 + rng.randrange(0, 3)

    broken = (
        "{\n"
        f'  "name": "{name}",\n'
        f'  "version": "{version}",\n'
        f'  "retries": {retries},\n'
        f'  "retries": {retries},\n'
        '  "enabled": "true",\n'
        '  "tags": ["bench", "pipeline", "bench"],\n'
        '  "weights": [\n'
        + ",\n".join(f'    {{"id": "{i}", "weight": '
                     + (f'"{weights[i]}"' if i == ids[-1] else str(weights[i]))
                     + "}" for i in ids)
        + ",\n"
        "  ],\n"
        "}\n"
    )
    write(os.path.join(work, "config.json"), broken)
    write(os.path.join(work, "README"), "pipeline config\n")
    return {
        "config": "config.json",
        "name": name,
        "version": version,
        "retries": retries,
        "enabled": True,
        "tags": sorted({"bench", "pipeline"}),
        "weights": {i: weights[i] for i in sorted(weights)},
        "weight_ids": sorted(weights),
        "weights_sum": 100,
        "version_regex": r"^\d+\.\d+\.\d+$",
    }


# --------------------------------------------------------------------------
# 7. symlink-maze
# --------------------------------------------------------------------------
def gen_symlink_maze(work: str, rng: random.Random) -> dict:
    """A dangling `current` link and a self-referential loop link."""
    versions = ["v1", "v2", "v3"]
    target = versions[1 + rng.randrange(0, len(versions) - 1)]
    for v in versions:
        write(os.path.join(work, "releases", v, "VERSION"), v + "\n")
        write(os.path.join(work, "releases", v, "payload", "data.txt"),
              f"payload for {v}\n" * 2)
    write(os.path.join(work, "RELEASE.txt"), f"release: {target}\n")
    os.makedirs(os.path.join(work, "links"), exist_ok=True)
    dangling = os.path.join(work, "links", "current")
    os.symlink("../releases/v4", dangling)          # v4 does not exist
    loop = os.path.join(work, "links", "loop")
    os.symlink("../links/loop", loop)               # cycle
    write(os.path.join(work, "README"), "release layout\n")
    return {
        "current_link": "links/current",
        "loop_link": "links/loop",
        "expected_version": target,
        # the link lives in links/, so a relative target that survives a
        # move of the whole tree is ../releases/<version>
        "expected_target": f"../releases/{target}",
        "payload": f"releases/{target}/payload/data.txt",
        "payload_sha256": sha256_text(f"payload for {target}\n" * 2),
        "release_file": "RELEASE.txt",
    }


# --------------------------------------------------------------------------
# 8. tar-restore
# --------------------------------------------------------------------------
def gen_tar_restore(work: str, rng: random.Random) -> dict:
    """An archive plus a manifest; the restore dir is partial and wrong."""
    entries = []
    payloads = {
        "etc/bench/bench.conf": ("# bench config\nworkers=4\n", 0o644),
        "etc/bench/secret.key": ("fixture-key-not-a-real-secret\n", 0o600),
        "usr/local/bin/bench-run": ("#!/bin/sh\necho bench-ok\n", 0o755),
        "var/lib/bench/state.txt": ("state=ready\n", 0o644),
        "var/lib/bench/nested/deep.txt": ("deep value\n" * 2, 0o640),
    }
    names = list(payloads)
    rng.shuffle(names)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name in names:
            body, mode = payloads[name]
            data = body.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = EPOCH
            info.mode = mode
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    raw = buf.getvalue()
    gz = io.BytesIO()
    with gzip.GzipFile(fileobj=gz, mode="wb", mtime=0) as g:
        g.write(raw)
    write(os.path.join(work, "archive.tar.gz"), gz.getvalue())

    manifest = {"entries": []}
    for name in sorted(names):
        body, mode = payloads[name]
        manifest["entries"].append({
            "path": name,
            "sha256": sha256_text(body),
            "mode": mode,
            "size": len(body.encode()),
        })
    write(os.path.join(work, "manifest.json"),
          json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    # a partial, partly wrong restore to be repaired
    write(os.path.join(work, "restore", "etc", "bench", "bench.conf"),
          "# bench config\nworkers=1\n")
    write(os.path.join(work, "restore", "etc", "bench", "leftover.tmp"),
          "stale\n")
    write(os.path.join(work, "restore", "usr", "local", "bin", "bench-run"),
          "#!/bin/sh\necho wrong\n")
    return {
        "archive": "archive.tar.gz",
        "manifest": "manifest.json",
        "restore_dir": "restore",
        "entries": manifest["entries"],
        "entry_count": len(manifest["entries"]),
        "archive_sha256": sha256_file(os.path.join(work, "archive.tar.gz")),
    }


# --------------------------------------------------------------------------
# 9. bugfix-python
# --------------------------------------------------------------------------
ROLLING_SRC = '''"""Rolling statistics used by the bench ingest pipeline.

Contract (see task.md):
    rolling_mean(values, window) -> list[float]
        len(result) == len(values) - window + 1
        result[i] == mean(values[i:i + window])
    ValueError when window < 1 or window > len(values).
"""


def rolling_mean(values, window):
    if window < 1:
        raise ValueError("window must be positive")
    if window > len(values):
        raise ValueError("window larger than the input")
    out = []
    for i in range(len(values) - window):     # BUG: off by one
        chunk = values[i:i + window]
        out.append(sum(chunk) / window)
    return out


def rolling_max(values, window):
    if window < 1 or window > len(values):
        raise ValueError("bad window")
    return [max(values[i:i + window])
            for i in range(len(values) - window + 1)]
'''

SHIPPED_TEST = '''"""Shipped test: passes on the buggy module, so it is not the oracle."""
import unittest

from pkg.rolling import rolling_mean, rolling_max


class TestRolling(unittest.TestCase):
    def test_first_window(self):
        self.assertEqual(rolling_mean([1, 2, 3, 4, 5, 6], 3)[0], 2.0)

    def test_max_first_window(self):
        self.assertEqual(rolling_max([1, 2, 3, 4, 5, 6], 3)[0], 3)


if __name__ == "__main__":
    unittest.main()
'''


def gen_bugfix_python(work: str, rng: random.Random) -> dict:
    """A module with a boundary bug; the shipped test does not catch it."""
    write(os.path.join(work, "pkg", "__init__.py"), "")
    write(os.path.join(work, "pkg", "rolling.py"), ROLLING_SRC)
    write(os.path.join(work, "tests", "test_rolling.py"), SHIPPED_TEST)
    write(os.path.join(work, "README"), "pkg: rolling statistics\n")

    values = [((i * 7 + 3) % 23) for i in range(9)]
    window = 4
    full = [sum(values[i:i + window]) / window
            for i in range(len(values) - window + 1)]
    return {
        "module": "pkg/rolling.py",
        "shipped_test": "tests/test_rolling.py",
        "values": values,
        "window": window,
        "full_mean": full,
        "len_values": len(values),
        "len_full": len(full),
        "len_values_plus_1": len(values) + 1,
        "single_value": [3.5],
    }


# --------------------------------------------------------------------------
# 10. cron-repair
# --------------------------------------------------------------------------
def expand_field(field: str, low: int, high: int, names=None):
    """Reference expander used by the fixture generator (see verify.sh for
    the verifier's own, independent implementation)."""
    if names:
        for k, v in names.items():
            field = re.sub(rf"\b{k}\b", str(v), field, flags=re.IGNORECASE)
    out = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
        if part == "*":
            start, end = low, high
        elif "-" in part.lstrip("-"):
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if step < 1:
            raise ValueError("step must be >= 1")
        out.update(range(start, end + 1, step))
    return out


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
DAYS = {d: i for i, d in enumerate(
    ["sun", "mon", "tue", "wed", "thu", "fri", "sat"], start=0)}


def gen_cron_repair(work: str, rng: random.Random) -> dict:
    """Crontab entries no scheduler would accept; the intent is a table."""
    minute_a = rng.choice([0, 5, 10, 15, 20, 30])
    intent = [
        {"schedule": f"{minute_a} * * * *", "command": "/opt/bench/bin/tick.sh"},
        {"schedule": "*/15 * * * *", "command": "/opt/bench/bin/poll.sh"},
        {"schedule": "0 2 * * *", "command": "/opt/bench/bin/backup.sh"},
        {"schedule": "30 4 * * 1-5", "command": "/opt/bench/bin/report.sh"},
        {"schedule": "0 0 1 * *", "command": "/opt/bench/bin/monthly.sh"},
        {"schedule": "0 6 * * 0", "command": "/opt/bench/bin/weekly.sh"},
    ]
    broken_lines = [
        f"{minute_a} * * * * /opt/bench/bin/tick.sh",
        "*/0 * * * * /opt/bench/bin/poll.sh",           # step zero
        "0 2 * * /opt/bench/bin/backup.sh",             # four fields
        "30 25 * * 1-5 /opt/bench/bin/report.sh",       # hour out of range
        "0 0 1 * * * /opt/bench/bin/monthly.sh",        # six fields
        "0 6 * * SUN /opt/bench/bin/weekly.sh",         # names not allowed
    ]
    header = ("# bench crontab\n"
              "# fields: minute hour day-of-month month day-of-week command\n"
              "# numeric fields only; day-of-week 0=Sunday\n")
    write(os.path.join(work, "crontab"), header + "\n".join(broken_lines) + "\n")
    write(os.path.join(work, "README"), "bench crontab\n")

    expected = []
    for row in intent:
        f = row["schedule"].split()
        expected.append({
            "schedule": row["schedule"],
            "command": row["command"],
            "minute": sorted(expand_field(f[0], 0, 59)),
            "hour": sorted(expand_field(f[1], 0, 23)),
            "dom": sorted(expand_field(f[2], 1, 31)),
            "month": sorted(expand_field(f[3], 1, 12)),
            "dow": sorted(expand_field(f[4], 0, 6)),
        })
    return {
        "crontab": "crontab",
        "lines": expected,
        "line_count": len(expected),
    }


GENERATORS = {
    "wal-repair": gen_wal_repair,
    "git-lost-branch": gen_git_lost_branch,
    "systemd-unit": gen_systemd_unit,
    "perms-maze": gen_perms_maze,
    "csv-normalize": gen_csv_normalize,
    "json-config": gen_json_config,
    "symlink-maze": gen_symlink_maze,
    "tar-restore": gen_tar_restore,
    "bugfix-python": gen_bugfix_python,
    "cron-repair": gen_cron_repair,
}


def build(src: str, out: str, seed: int) -> None:
    os.makedirs(out, exist_ok=True)
    for index, task in enumerate(TASKS):
        rng = random.Random(f"{seed}:{task}:{index}")
        taskdir = os.path.join(out, task)
        work = os.path.join(taskdir, "work")
        if os.path.exists(taskdir):
            subprocess.run(["sudo", "-n", "rm", "-rf", taskdir], check=False)
            shutil.rmtree(taskdir, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        for name in ("task.md", "verify.sh"):
            shutil.copyfile(os.path.join(src, task, name),
                            os.path.join(taskdir, name))
            os.chmod(os.path.join(taskdir, name),
                     0o755 if name.endswith(".sh") else 0o644)
        expected = GENERATORS[task](work, rng)
        expected["task"] = task
        expected["seed"] = seed
        with open(os.path.join(taskdir, "expected.json"), "w") as fh:
            json.dump(expected, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.chmod(os.path.join(taskdir, "expected.json"), 0o644)
        freeze_mtimes(taskdir)
        # perms-maze is root-owned by design; leave its modes alone
        print(f"fixtures: {task}: work/ + expected.json", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--out", required=True, help="output fixture tree")
    ap.add_argument("--src", default=os.path.dirname(os.path.abspath(__file__)),
                    help="committed fixtures tree with task.md and verify.sh")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        print("\n".join(TASKS))
        return 0
    build(args.src, args.out, args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
