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
# every child process gets a deadline: a hung step must never block the
# verdict or the cleanup. install builds a wheel from git and may be slow;
# gpu-exec wraps a remote job bounded by its own --timeout 300.
STEP_TIMEOUT_S = 120
INSTALL_TIMEOUT_S = 600
GPU_EXEC_TIMEOUT_S = 360
# python import/pip settings inherited from a developer's checkout would
# defeat the fresh venv (an injected module can shadow the installed ref)
_DROP_ENV = ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONSTARTUP")


def strip_py_env(env):
    """env minus the python/pip overrides, with PATH/HOME/proxy kept."""
    return {
        k: v for k, v in env.items()
        if k not in _DROP_ENV and not k.startswith("PIP_")
    }


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
        capture_output=True, text=True, timeout=STEP_TIMEOUT_S,
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


def run(receipt, name, argv, env=None, timeout=None):
    """Run one step with a deadline, record rc and duration, echo progress."""
    timeout = STEP_TIMEOUT_S if timeout is None else timeout
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True,
            env=strip_py_env(env if env is not None else os.environ),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        proc = subprocess.CompletedProcess(argv, 124, stdout="", stderr="")
    entry = {
        "name": name,
        "rc": proc.returncode,
        "duration_s": round(time.monotonic() - started, 3),
    }
    if proc.returncode:
        detail = (proc.stderr or proc.stdout or "").strip()
        if not detail and timed_out:
            detail = f"timed out after {timeout}s"
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


def sweep_new_ids(receipt, name, before, argv, env, kind, created):
    """Record ids that appeared since `before` as unattributed leftovers.
    An id difference cannot prove the resource is ours (another client may
    have created it in the same window), so nothing is registered for a
    kill here; the run fails and the ids are reported for a human."""
    during = list_ids(run(receipt, name, argv, env=env))
    if before is None or during is None:
        return False
    found = False
    for rid in sorted(during - before):
        created.add(rid)
        found = True
    return found


def _clean_id(sid):
    """A usable resource id, or None: blank and non-printable strings carry
    no information and must not count as verified inventory."""
    if isinstance(sid, str) and sid.strip() and sid.isprintable():
        return sid
    return None


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
            sid = _clean_id(item.get("sandboxID") or item.get("sandbox_id"))
        if sid:
            ids.add(sid)
        else:
            # an entry we cannot identify makes the whole reply unknown
            return None
    return ids


def printed_id(proc):
    """The valid id a create printed (last stdout line), or None."""
    lines = proc.stdout.strip().splitlines()
    return _clean_id(lines[-1].strip()) if lines else None


def smoke(ref, gpu, receipt):
    """Run every gate step against ref, filling receipt['steps']."""
    with tempfile.TemporaryDirectory(prefix="release-smoke-") as tmp:
        venv = Path(tmp) / "venv"
        if run(receipt, "venv", cmd_venv(venv)).returncode:
            return
        if run(receipt, "install", cmd_install(venv, ref),
               timeout=INSTALL_TIMEOUT_S).returncode:
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
        created_cpu = set()  # cpu ids this run created, for unverifiable runs
        created_gpu = set()
        before_cpu = before_gpu = None
        cpu_visible = gpu_visible = None  # did the inventory see the create?
        try:
            run(receipt, "templates", [sbx, "templates"], env=env)
            before_cpu = list_ids(
                run(receipt, "list-before", [sbx, "list", "--json"], env=env)
            )
            sid = None
            proc = run(receipt, "create", [sbx, "create"], env=env)
            printed = printed_id(proc)
            if printed:
                sid = printed
                alive.append(("cpu", sid))
                created_cpu.add(sid)
                if proc.returncode:
                    # the request was served and the reply was lost: the
                    # sandbox is ours, so register it for cleanup first
                    check(receipt, "create-id", False,
                          f"create exited {proc.returncode} but allocated {sid}; "
                          "treating it as created by us and killing it")
            else:
                check(receipt, "create-id", False,
                      f"create exited {proc.returncode} but printed no "
                      "sandbox id; recording unattributed new ids as "
                      "leftovers for a human, killing nothing")
                if sweep_new_ids(receipt, "list-during", before_cpu,
                                 [sbx, "list", "--json"], env, "cpu",
                                 created_cpu):
                    # the inventory did show the new resource, so it can
                    # verify absence afterwards — but ownership stays
                    # unproven, so it is still only reported, never killed
                    cpu_visible = True
            if sid is None:
                for name in ("exec", "cp-up", "cp-down", "cp-verify", "kill"):
                    skip(receipt, name, "no sandbox id")
            else:
                # the gate can only trust list-after cleanup if the
                # inventory saw the sandbox while it was alive
                during = list_ids(
                    run(receipt, "list-during", [sbx, "list", "--json"], env=env)
                )
                cpu_visible = during is not None and sid in during
                check(receipt, "inventory-visibility", cpu_visible,
                      None if cpu_visible
                      else f"inventory does not show the created sandbox {sid}")
                proc = run(receipt, "exec", [sbx, "exec", sid, "--", "echo ok"],
                           env=env)
                check(receipt, "exec-check",
                      proc.returncode == 0 and proc.stdout.strip() == "ok",
                      None if proc.returncode == 0 and proc.stdout.strip() == "ok"
                      else f"exec printed {proc.stdout.strip()!r}, expected 'ok'")
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
                printed = printed_id(proc)
                if printed:
                    lid = printed
                    alive.append(("gpu", lid))
                    created_gpu.add(lid)
                    if proc.returncode:
                        check(receipt, "gpu-create-id", False,
                              f"gpu create exited {proc.returncode} but "
                              f"allocated {lid}; treating it as created by "
                              "us and killing it")
                else:
                    check(receipt, "gpu-create-id", False,
                          f"gpu create exited {proc.returncode} but printed "
                          "no lease id; recording unattributed new ids as "
                          "leftovers for a human, killing nothing")
                    if sweep_new_ids(receipt, "gpu-list-during", before_gpu,
                                     [sbx, "gpu", "list", "--json"], env,
                                     "gpu", created_gpu):
                        gpu_visible = True
                if lid is None:
                    for name in ("gpu-exec", "gpu-kill"):
                        skip(receipt, name, "no lease id")
                else:
                    during_gpu = list_ids(
                        run(receipt, "gpu-list-during",
                            [sbx, "gpu", "list", "--json"], env=env)
                    )
                    gpu_visible = during_gpu is not None and lid in during_gpu
                    check(receipt, "gpu-inventory-visibility", gpu_visible,
                          None if gpu_visible
                          else f"inventory does not show the created lease {lid}")
                    proc = run(receipt, "gpu-exec",
                               [sbx, "gpu", "exec", lid, "-c", GPU_CHECK,
                                "--timeout", "300"], env=env,
                               timeout=GPU_EXEC_TIMEOUT_S)
                    check(receipt, "gpu-exec-check",
                          proc.returncode == 0 and "cuda ok" in proc.stdout,
                          None if proc.returncode == 0 and "cuda ok" in proc.stdout
                          else "gpu exec did not confirm cuda: printed "
                               # scrub BEFORE truncating: the 80-char cut may
                               # land inside the key, so a fragment would
                               # survive any later scrubbing
                               f"{scrub(proc.stdout.strip())[:80]!r}")
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
        cpu_unverifiable = (
            before_cpu is None
            or after_cpu is None
            or (created_cpu and not cpu_visible)
        )
        if not cpu_unverifiable:
            left |= after_cpu - (before_cpu or set())
        else:
            # the baseline or the current inventory is unknown, or it could
            # not see the sandbox while it was alive: without a verified
            # baseline the leftover diff is meaningless
            left |= {rid for kind, rid in alive if kind == "cpu"}
            left |= created_cpu
            check(receipt, "leftover-check", False,
                  "could not verify the inventory baseline `sbx list --json`")
        if gpu:
            after_gpu = list_ids(
                run(receipt, "gpu-list-after",
                    [sbx, "gpu", "list", "--json"], env=env)
            )
            gpu_unverifiable = (
                before_gpu is None
                or after_gpu is None
                or (created_gpu and not gpu_visible)
            )
            if not gpu_unverifiable:
                left |= after_gpu - (before_gpu or set())
            else:
                left |= {rid for kind, rid in alive if kind == "gpu"}
                left |= created_gpu
                check(receipt, "leftover-check", False,
                      "could not verify the inventory baseline "
                      "`sbx gpu list --json`")
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
        "--require-live", action="store_true",
        help="fail if no API key is configured instead of checking install only",
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
    try:
        if args.require_live and receipt["keyless"]:
            check(receipt, "live-credentials", False,
                  "live smoke requires SBX_API_KEY or E2B_API_KEY")
        else:
            smoke(ref, args.gpu, receipt)
    except Exception as exc:  # any bug must still leave a verdict + receipt
        check(receipt, "run", False, f"unexpected {type(exc).__name__}: {exc}")
    receipt["duration_s"] = round(time.monotonic() - started, 3)
    failed = [s for s in receipt["steps"] if s.get("rc")]
    passed = not failed and not receipt["left"]
    receipt["verdict"] = "pass" if passed else "fail"
    line = (
        f"{'PASS' if passed else 'FAIL'} ref={ref} "
        f"steps={len(receipt['steps'])} left={receipt['left']}"
    )
    if receipt["keyless"] and not failed:
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
