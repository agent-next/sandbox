#!/usr/bin/env python3
"""Run the web-scrape-dataset demo end to end in a disposable sandbox.

    SBX_API_KEY=<your key> python3 run.py [--ref REF] [--seed N] [--keep]

Needs the `sbx` CLI (pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli")
and an API key in SBX_API_KEY or E2B_API_KEY.

Steps, each timed:
    1. sbx create --timeout-min 30
    2. in the sandbox: git clone --depth 1 -b <ref> the repo
    3. judge/setup.sh          install the pinned Playwright + Chromium
    4. judge/selftest.sh       good example passes, every mutant is killed
    5. judge/grade.sh examples/good/scrape.py --json /tmp/verdict.json
    6. print the verdict JSON and a short human summary

The sandbox is always killed in a `finally`, and `sbx list` is polled until the
id is gone. A kill reply is not proof of deletion: if the id is still listed the
run exits non-zero and names it, rather than reporting a success it cannot
confirm. --keep leaves the sandbox up and prints its id instead.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO_URL = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/web-scrape-dataset"
DEFAULT_REF = "main"

# generous per-step exec budgets: a cold setup.sh downloads ~115 MB of browser
# and the self-test runs the judge eight times (good + 7 mutants)
STEP_TIMEOUTS = {"clone": 600, "setup": 1200, "selftest": 1800, "grade": 900}


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%SZ}] {msg}", flush=True)


def run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run a local command, capturing output. Never raises on a non-zero exit."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def timed(label: str, fn):
    """Run fn(), print its wall time, and hand back its result."""
    start = time.monotonic()
    result = fn()
    log(f"{label}: {time.monotonic() - start:.1f}s")
    return result


def sbx_exec(sid: str, line: str, timeout: int) -> int:
    """Run a shell line in the sandbox, streaming its output. Returns its exit code."""
    proc = subprocess.run(
        ["sbx", "exec", sid, "--timeout", str(timeout), "--", line],
        text=True)
    return proc.returncode


def listed_ids() -> set[str]:
    """The sandbox ids `sbx list` reports for this key.

    Raises if the inventory cannot be read: an unreadable list must never be
    mistaken for "the sandbox is gone".
    """
    proc = run(["sbx", "list"], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(
            "sbx list failed (exit %d): %s"
            % (proc.returncode, (proc.stderr or proc.stdout).strip()[:300]))
    ids = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        ids.add(line.split()[0])
    return ids


def confirm_gone(sid: str) -> None:
    """Poll `sbx list` until the id is gone. Raise (naming the id) if it stays."""
    for delay in (0, 2, 5, 10, 20):
        if delay:
            time.sleep(delay)
        if sid not in listed_ids():
            return
    raise RuntimeError(
        f"could not confirm sandbox {sid} is gone after `sbx kill`; "
        f"it is still listed. Kill it by hand: sbx kill {sid}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=DEFAULT_REF,
                    help="git ref of the repo to clone in the sandbox (default: main)")
    ap.add_argument("--seed", type=int, default=None,
                    help="seed for the fixture; the demo default is used if omitted")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    args = ap.parse_args()

    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        print("run.py: no API key: export SBX_API_KEY (or E2B_API_KEY)", file=sys.stderr)
        return 2

    seed_flag = "" if args.seed is None else f"--seed {args.seed}"
    total_start = time.monotonic()
    sid = None
    failure = None
    verdict = None

    try:
        # ---- 1. create -----------------------------------------------------
        def create():
            nonlocal sid
            proc = run(["sbx", "create", "--timeout-min", "30"], timeout=180)
            if proc.returncode != 0:
                raise RuntimeError("sbx create failed (exit %d): %s"
                                   % (proc.returncode,
                                      (proc.stderr or proc.stdout).strip()[:300]))
            sid = proc.stdout.strip().splitlines()[-1].strip()
            if not sid:
                raise RuntimeError("sbx create printed no sandbox id")
            log(f"sandbox {sid}")
            return sid

        timed("create", create)

        # ---- 2. clone ------------------------------------------------------
        clone = (
            f"git clone --depth 1 -b {shlex.quote(args.ref)} {REPO_URL} /tmp/repo")
        rc = timed("clone", lambda: sbx_exec(sid, clone, STEP_TIMEOUTS["clone"]))
        if rc != 0:
            raise RuntimeError(f"git clone failed (exit {rc})")

        demo = f"/w/repo/{DEMO_DIR}"

        # ---- 3. setup ------------------------------------------------------
        rc = timed("setup.sh", lambda: sbx_exec(
            sid, f"cd {demo} && bash judge/setup.sh", STEP_TIMEOUTS["setup"]))
        if rc != 0:
            raise RuntimeError(f"judge/setup.sh failed (exit {rc})")

        # ---- 4. selftest ---------------------------------------------------
        rc = timed("selftest.sh", lambda: sbx_exec(
            sid, f"cd {demo} && bash judge/selftest.sh --json /tmp/selftest.json",
            STEP_TIMEOUTS["selftest"]))
        if rc != 0:
            raise RuntimeError(f"judge/selftest.sh failed (exit {rc})")

        # ---- 5. grade the good example ------------------------------------
        grade = (f"cd {demo} && bash judge/grade.sh examples/good/scrape.py "
                 f"{seed_flag} --json /tmp/verdict.json")
        rc = timed("grade.sh", lambda: sbx_exec(sid, grade, STEP_TIMEOUTS["grade"]))
        if rc != 0:
            raise RuntimeError(f"judge/grade.sh failed on the good example (exit {rc})")

        # ---- 6. verdict ----------------------------------------------------
        read = run(["sbx", "exec", sid, "--timeout", "60", "--",
                    "cat /tmp/verdict.json"], timeout=120)
        if read.returncode != 0:
            raise RuntimeError("could not read /tmp/verdict.json from the sandbox")
        try:
            verdict = json.loads(read.stdout)
        except ValueError as exc:
            raise RuntimeError(f"verdict JSON is unreadable: {exc}")

        print(read.stdout.strip())
        gates = verdict.get("gates", [])
        n_pass = sum(1 for g in gates if g.get("pass"))
        print("\n=== summary ===")
        print(f"verdict:        {'PASS' if verdict.get('pass') else 'FAIL'}")
        print(f"gates:          {n_pass}/{len(gates)} passed")
        print(f"products:       {verdict.get('truth', {}).get('ok')} ok, "
              f"{verdict.get('truth', {}).get('malformed')} malformed")
        print(f"requests seen:  {verdict.get('requests_seen', {}).get('total')}, "
              f"to the disallowed path: "
              f"{verdict.get('requests_seen', {}).get('to_disallowed')}")
        if not verdict.get("pass"):
            failure = "the judge verdict was FAIL"

    except Exception as exc:  # noqa: BLE001 -- report, then clean up
        failure = str(exc)
        print(f"run.py: ERROR: {exc}", file=sys.stderr)

    finally:
        if sid is None:
            log("no sandbox was created; nothing to clean up")
        elif args.keep:
            log(f"--keep: leaving sandbox {sid} running; explore it with: sbx exec {sid} -- bash")
        else:
            kill = timed("kill", lambda: run(["sbx", "kill", sid], timeout=120))
            if kill.returncode != 0:
                note = (kill.stderr or kill.stdout).strip()[:200]
                print(f"run.py: sbx kill {sid} exited {kill.returncode}: {note}",
                      file=sys.stderr)
            try:
                confirm_gone(sid)
                log(f"sandbox {sid} confirmed gone")
            except Exception as exc:  # noqa: BLE001
                # an unconfirmed cleanup is a failed run, never a silent success
                print(f"run.py: ERROR: {exc}", file=sys.stderr)
                failure = failure or str(exc)

    log(f"total: {time.monotonic() - total_start:.1f}s")
    if failure:
        print(f"run.py: FAILED: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
