#!/usr/bin/env python3
"""One-command run for the notebook-exec-report cookbook demo
(DEMO-STANDARD.md).

Creates a disposable agent-next sandbox, clones this repo into it, installs
the pinned notebook toolchain, runs the judge self-test, grades the
known-good notebook artifact, prints the verdict, then always kills the
sandbox and confirms it is gone. Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage: python3 run.py [--ref main] [--keep]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/notebook-exec-report"
ARTIFACT = "examples/good/analysis.ipynb"
CLONE_DIR = "notebook-demo-repo"
# local wall-clock allowance per step; the in-sandbox --timeout is the
# command's own limit and this is the client-side backstop above it.
LOCAL_MARGIN_S = 120.0


class Failure(RuntimeError):
    pass


def scrub(text: str) -> str:
    """Never let a key from the environment reach the printed output."""
    for name in ("SBX_API_KEY", "E2B_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def sbx(*args: str, timeout: float = 180.0) -> subprocess.CompletedProcess:
    """Run one sbx CLI command; never raises, caller checks exit code."""
    try:
        proc = subprocess.run(["sbx", *args], capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        # the command's own limit already expired; the CLI did not reply
        return subprocess.CompletedProcess(
            ["sbx", *args], 124,
            f"sbx {' '.join(args)}: no reply within {timeout:.0f}s "
            f"(the sandbox command may still be running in the sandbox)\n")
    proc.stdout = scrub(proc.stdout or "")
    proc.stderr = scrub(proc.stderr or "")
    return proc


def step(name: str, fn) -> subprocess.CompletedProcess:
    start = time.monotonic()
    proc = fn()
    dt = time.monotonic() - start
    print(f"run: [{dt:6.1f}s] {name} -> exit {proc.returncode}", flush=True)
    if proc.returncode != 0:
        tail = (proc.stdout or "") + (proc.stderr or "")
        raise Failure(f"{name} failed (exit {proc.returncode}):\n"
                      f"{tail.strip()[-2000:]}")
    return proc


def show(proc: subprocess.CompletedProcess) -> None:
    """Echo a step's stdout so the user sees the judge's own lines
    (each 'killed <mutant> (gate: ...)', the kill rate, the verdict)."""
    if proc.stdout:
        print(proc.stdout.rstrip(), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repo ref to clone (default main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    args = ap.parse_args()

    if sbx("--version").returncode != 0:
        print("run: the sbx CLI is required: pip install "
              '"git+https://github.com/agent-next/sandbox#subdirectory=cli"',
              file=sys.stderr)
        return 1

    sid = None
    fail = False
    try:
        created = step("sbx create --timeout-min 30",
                       lambda: sbx("create", "--timeout-min", "30"))
        sid = created.stdout.strip().splitlines()[-1].strip()
        print(f"run: sandbox {sid}", flush=True)

        step("git clone",
             lambda: sbx("exec", sid, "--timeout", "300", "--",
                         "git", "clone", "--depth", "1", "-b", args.ref,
                         REPO, CLONE_DIR, timeout=300 + LOCAL_MARGIN_S))

        def in_sandbox(name: str, cmd: str, timeout: float,
                       echo: bool = False) -> subprocess.CompletedProcess:
            # the local subprocess timeout must cover the sandbox-side
            # --timeout, or a long step is killed while it still works
            proc = step(name, lambda: sbx(
                "exec", sid, "--timeout", str(timeout), "--",
                f"cd {CLONE_DIR}/{DEMO} && {cmd}",
                timeout=timeout + LOCAL_MARGIN_S))
            if echo:
                show(proc)
            return proc

        # fresh sandbox: the venv and the pinned wheels are not there yet
        in_sandbox("judge/setup.sh", "bash judge/setup.sh", 1200)
        in_sandbox("judge/selftest.sh", "bash judge/selftest.sh", 3600,
                   echo=True)
        graded = in_sandbox(
            f"judge/grade.sh {ARTIFACT}",
            f"bash judge/grade.sh {ARTIFACT} --json /tmp/verdict.json",
            900, echo=True)

        try:
            verdict = json.loads(graded.stdout[graded.stdout.index("{"):])
        except (ValueError, json.JSONDecodeError) as exc:
            raise Failure(f"could not parse the verdict JSON: {exc}\n"
                          f"{graded.stdout[-1000:]}") from exc
        gates = verdict.get("gates", {})
        oracle = gates.get("oracle", {})
        blind = gates.get("blind", {})
        print("run: SUMMARY "
              f"passed={verdict.get('passed')} "
              f"rmse_test={verdict.get('metrics', {}).get('rmse_test')} "
              f"(refit {oracle.get('rmse_test')}) "
              f"r2_test={verdict.get('metrics', {}).get('r2_test')} "
              f"coef_recovery={oracle.get('coef_recovery')} "
              f"blind_ratio={blind.get('ratio')} "
              f"figures={gates.get('figures', {}).get('count')}",
              flush=True)
        if not verdict.get("passed"):
            raise Failure(f"judge did not pass: {verdict.get('failed_gate')}"
                          f" -- {verdict.get('reason')}")
    except Failure as exc:
        print(f"run: FAILED: {exc}", file=sys.stderr)
        fail = True
    except subprocess.TimeoutExpired as exc:
        print(f"run: FAILED: sbx command timed out: {exc}", file=sys.stderr)
        fail = True
    finally:
        if sid is not None:
            if args.keep:
                print(f"run: --keep: sandbox {sid} left running "
                     "(remember: sbx kill when done)", flush=True)
            else:
                killed = sbx("kill", sid, timeout=240)
                listing = sbx("list", timeout=180)
                if killed.returncode != 0:
                    print(f"run: WARNING kill exit {killed.returncode}",
                          file=sys.stderr)
                if listing.returncode != 0:
                    print(f"run: FAILED cleanup: sbx list exit "
                          f"{listing.returncode}; cannot confirm sandbox {sid} "
                          f"is gone -- run sbx kill {sid}", file=sys.stderr)
                    sys.exit(1)
                if sid in (listing.stdout or ""):
                    print(f"run: FAILED cleanup: sandbox {sid} still live; "
                          f"run sbx kill {sid}", file=sys.stderr)
                    sys.exit(1)
                print(f"run: killed and confirmed gone: {sid}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
