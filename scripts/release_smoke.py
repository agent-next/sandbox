#!/usr/bin/env python3
"""Release smoke gate: install the sbx CLI from a git ref into a fresh venv
and exercise it the way an outsider with a key would.

    python scripts/release_smoke.py [--ref TAG_OR_SHA] [--gpu] [--json FILE]

Every run makes a temp venv, pip-installs the cli package from the ref and
checks `sbx --version` (against the tag name when --ref is a vX.Y.Z tag).
With SBX_API_KEY or E2B_API_KEY in the environment it also lists templates
and live sandboxes, creates a CPU sandbox, runs `echo ok`, copies a file up
and back and compares sha256, and kills it; --gpu adds a 1 GiB GPU lease that
runs a torch cuda check. Anything the run created is killed even when a step
fails, and any id alive at the end that was not in the before-list fails the
gate ("left N"). Without a key only the install and version steps run.

Prints a one-line verdict and a JSON receipt (steps, durations, rc, left
count); --json also writes the receipt to a file. Exit 0 on PASS, 1 on FAIL.
The API key is never printed or written.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_URL = "https://github.com/agent-next/sandbox"
KEY_VARS = ("SBX_API_KEY", "E2B_API_KEY")
_TAG_REF = re.compile(r"^v?\d+\.\d+\.\d+$")
GPU_CHECK = (
    "import torch;"
    "assert torch.cuda.is_available(), 'torch.cuda.is_available() is False';"
    "print('cuda ok')"
)


def scrub(text):
    """Remove any configured API key value from text bound for output."""
    for name in KEY_VARS:
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def latest_tag():
    proc = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True, text=True,
    )
    if proc.returncode or not proc.stdout.strip():
        raise SystemExit("no --ref given and `git describe --tags` found no tag")
    return proc.stdout.strip()


def venv_bin(venv):
    return Path(venv) / ("Scripts" if os.name == "nt" else "bin")


def cmd_venv(venv):
    return [sys.executable, "-m", "venv", str(venv)]


def cmd_install(venv, ref):
    return [
        str(venv_bin(venv) / "python"), "-m", "pip", "install", "--quiet",
        f"git+{REPO_URL}@{ref}#subdirectory=cli",
    ]


def run(receipt, name, argv, env=None):
    """Run one step, record rc and duration, and echo a progress line."""
    started = time.monotonic()
    proc = subprocess.run(argv, capture_output=True, text=True, env=env)
    entry = {
        "name": name,
        "rc": proc.returncode,
        "duration_s": round(time.monotonic() - started, 3),
    }
    if proc.returncode:
        detail = (proc.stderr or proc.stdout or "").strip()
        if detail:
            # scrub BEFORE truncating: the 300-char cut may land inside the
            # key, so any surviving fragment stays secret. Keep the last line
            # of the scrubbed text, then cut at 300 chars max.
            entry["error"] = scrub(detail.splitlines()[-1])[:300]
    receipt["steps"].append(entry)
    print(f"[{name}] rc={proc.returncode} {entry['duration_s']}s", file=sys.stderr)
    return proc


def check(receipt, name, passed, detail=None):
    """Record an assertion as a step with rc 0/1."""
    entry = {"name": name, "rc": 0 if passed else 1, "duration_s": 0.0}
    if detail:
        entry["detail" if passed else "error"] = scrub(detail)
    receipt["steps"].append(entry)
    print(f"[{name}] rc={entry['rc']}", file=sys.stderr)
    return passed


def _first_error(*procs):
    """First non-empty stderr/stdout line among failed steps, for the receipt."""
    for proc in procs:
        if proc.returncode:
            text = (proc.stderr or proc.stdout or "").strip()
            if text:
                return ": " + text.splitlines()[-1]
    return ""


def skip(receipt, name, reason):
    receipt["steps"].append({"name": name, "skipped": True, "reason": reason})
    print(f"[{name}] skipped: {reason}", file=sys.stderr)


def list_ids(proc):
    """Sandbox or lease ids in a `* list --json` reply, or None when unknown.

    None means "cannot confirm the inventory": a non-list payload, or any
    entry without a recognized id. Callers must treat None as a failure,
    never as an empty list — a malformed reply must not count as absence.
    """
    if proc.returncode:
        return None
    try:
        items = json.loads(proc.stdout)
    except ValueError:
        return None
    if isinstance(items, dict):
        items = items.get("sandboxes")
    if not isinstance(items, list):
        return None
    ids = set()
    for item in items:
        sid = None
        if isinstance(item, dict):
            sid = item.get("sandboxID") or item.get("sandbox_id")
        if isinstance(sid, str) and sid:
            ids.add(sid)
        else:
            # an entry we cannot identify makes the whole reply unknown
            return None
    return ids


def printed_id(proc):
    """The id a create printed (last stdout line), or ''."""
    lines = proc.stdout.strip().splitlines()
    return lines[-1].strip() if lines else ""


def smoke(ref, gpu, receipt):
    """Run every gate step against ref, filling receipt['steps']."""
    with tempfile.TemporaryDirectory(prefix="release-smoke-") as tmp:
        venv = Path(tmp) / "venv"
        if run(receipt, "venv", cmd_venv(venv)).returncode:
            return
        if run(receipt, "install", cmd_install(venv, ref)).returncode:
            return
        sbx = str(venv_bin(venv) / "sbx")
        proc = run(receipt, "version", [sbx, "--version"])
        if proc.returncode:
            return
        installed = printed_id(proc)
        if _TAG_REF.fullmatch(ref):
            expected = ref[1:] if ref.startswith("v") else ref
            check(
                receipt, "version-check", installed == expected,
                f"`sbx --version` printed {installed!r}, expected {expected!r} for ref {ref}",
            )
        else:
            skip(receipt, "version-check", "ref is not a vX.Y.Z tag")
        if receipt["keyless"]:
            return
        env = {
            **os.environ,
            "PATH": str(venv_bin(venv)) + os.pathsep + os.environ.get("PATH", ""),
        }
        alive = []  # (kind, id) we created and have not confirmed killed
        before_cpu = before_gpu = None
        try:
            run(receipt, "templates", [sbx, "templates"], env=env)
            before_cpu = list_ids(
                run(receipt, "list-before", [sbx, "list", "--json"], env=env)
            )
            sid = None
            proc = run(receipt, "create", [sbx, "create"], env=env)
            if proc.returncode == 0:
                sid = printed_id(proc)
                if sid:
                    alive.append(("cpu", sid))
                else:
                    check(receipt, "create-id", False,
                          "create exited 0 but printed no sandbox id")
                    sid = None
            if sid is None:
                for name in ("exec", "cp-up", "cp-down", "cp-verify", "kill"):
                    skip(receipt, name, "no sandbox id")
            else:
                run(receipt, "exec", [sbx, "exec", sid, "--", "echo ok"], env=env)
                probe = Path(tmp) / "probe.txt"
                probe.write_text(
                    f"release-smoke {ref} {datetime.now(timezone.utc).isoformat()}\n"
                )
                remote = f"{sid}:/tmp/release-smoke-probe.txt"
                up = run(receipt, "cp-up",
                         [sbx, "cp", str(probe), remote], env=env)
                back = Path(tmp) / "probe-back.txt"
                down = run(receipt, "cp-down",
                           [sbx, "cp", remote, str(back)], env=env)
                if up.returncode or down.returncode:
                    check(receipt, "cp-verify", False,
                          "a cp step failed" + _first_error(up, down))
                elif not back.exists():
                    # both copies reported success but produced nothing:
                    # that is a failed round trip, never a skipped check
                    check(receipt, "cp-verify", False,
                          "cp-down exited 0 but " + str(back) + " is missing")
                else:
                    a = hashlib.sha256(probe.read_bytes()).hexdigest()
                    b = hashlib.sha256(back.read_bytes()).hexdigest()
                    check(receipt, "cp-verify", a == b,
                          None if a == b else f"sha256 mismatch: {a} != {b}")
                proc = run(receipt, "kill", [sbx, "kill", sid], env=env)
                if proc.returncode == 0:
                    alive.remove(("cpu", sid))
            if gpu:
                before_gpu = list_ids(
                    run(receipt, "gpu-list-before",
                        [sbx, "gpu", "list", "--json"], env=env)
                )
                lid = None
                proc = run(receipt, "gpu-create",
                           [sbx, "gpu", "create", "--vram", "1"], env=env)
                if proc.returncode == 0:
                    lid = printed_id(proc)
                    if lid:
                        alive.append(("gpu", lid))
                    else:
                        check(receipt, "gpu-create-id", False,
                              "gpu create exited 0 but printed no lease id")
                        lid = None
                if lid is None:
                    for name in ("gpu-exec", "gpu-kill"):
                        skip(receipt, name, "no lease id")
                else:
                    run(receipt, "gpu-exec",
                        [sbx, "gpu", "exec", lid, "-c", GPU_CHECK,
                         "--timeout", "300"], env=env)
                    proc = run(receipt, "gpu-kill",
                               [sbx, "gpu", "kill", lid], env=env)
                    if proc.returncode == 0:
                        alive.remove(("gpu", lid))
        finally:
            for kind, rid in alive:
                verb = ["gpu", "kill"] if kind == "gpu" else ["kill"]
                run(receipt, "cleanup-kill", [sbx, *verb, rid], env=env)
        left = set()
        after_cpu = list_ids(
            run(receipt, "list-after", [sbx, "list", "--json"], env=env)
        )
        if before_cpu is not None and after_cpu is not None:
            left |= after_cpu - before_cpu
        else:
            left |= {rid for kind, rid in alive if kind == "cpu"}
            check(receipt, "leftover-check", False,
                  "could not diff `sbx list --json` before/after")
        if gpu:
            after_gpu = list_ids(
                run(receipt, "gpu-list-after",
                    [sbx, "gpu", "list", "--json"], env=env)
            )
            if before_gpu is not None and after_gpu is not None:
                left |= after_gpu - before_gpu
            else:
                left |= {rid for kind, rid in alive if kind == "gpu"}
                check(receipt, "leftover-check", False,
                      "could not diff `sbx gpu list --json` before/after")
        receipt["left"] = len(left)
        if left:
            receipt["left_ids"] = sorted(left)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Smoke-gate a release: install a ref into a fresh venv "
        "and exercise sbx against the live service."
    )
    parser.add_argument(
        "--ref", default=None,
        help="tag or sha to install (default: latest git tag)",
    )
    parser.add_argument(
        "--gpu", action="store_true",
        help="also create a 1 GiB GPU lease and run a torch cuda check",
    )
    parser.add_argument(
        "--json", dest="receipt_path", metavar="FILE",
        help="also write the JSON receipt to FILE",
    )
    args = parser.parse_args(argv)
    ref = args.ref or latest_tag()
    receipt = {
        "ref": ref,
        "gpu": bool(args.gpu),
        "keyless": not any(os.environ.get(name) for name in KEY_VARS),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps": [],
        "left": 0,
    }
    started = time.monotonic()
    smoke(ref, args.gpu, receipt)
    receipt["duration_s"] = round(time.monotonic() - started, 3)
    failed = [s for s in receipt["steps"] if s.get("rc")]
    passed = not failed and not receipt["left"]
    receipt["verdict"] = "pass" if passed else "fail"
    line = (
        f"{'PASS' if passed else 'FAIL'} ref={ref} "
        f"steps={len(receipt['steps'])} left={receipt['left']}"
    )
    if receipt["keyless"]:
        line += " (keyless: install and version only; set SBX_API_KEY or E2B_API_KEY for the full gate)"
    elif failed:
        line += f" first-failure={failed[0]['name']}"
    print(line)
    text = json.dumps(receipt, indent=2)
    if args.receipt_path:
        Path(args.receipt_path).write_text(text + "\n")
    print(text)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
