#!/usr/bin/env python3
"""One-command run for the pr-review-agent cookbook demo (DEMO-STANDARD.md).

Creates a disposable agent-next sandbox, clones this repo into it, installs
the pinned tools, runs the judge self-test, grades the known-good artifact,
prints the verdict, then always kills the sandbox and confirms it is gone.
Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage: python3 run.py [--ref main] [--keep]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/pr-review-agent"
ARTIFACT = "examples/good/review"
CLONE_DIR = "pr-review-demo-repo"


class Failure(RuntimeError):
    pass


def sbx(*args: str, timeout: float = 120.0) -> subprocess.CompletedProcess:
    """Run one sbx CLI command; never raises, the caller checks the exit code."""
    return subprocess.run(["sbx", *args], capture_output=True, text=True,
                          timeout=timeout)


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


def confirm_killed(sid: str) -> bool:
    """`sbx kill`, then PROVE the sandbox is gone; never assume it.

    Fails closed (returns False) whenever the outcome cannot be confirmed:
    a kill or list command that errors or times out, or a listing whose
    output is missing. A failed kill is not retried here — a blip may hide
    a kill that already landed (LESSONS.md 616b07c / d877345 / e08022b) —
    instead the follow-up `sbx list` decides: only a list that exited 0 and
    no longer names the id (whole first column, not a substring) counts as
    confirmed, and an exit-0 list that proves the sandbox dead makes even a
    503'd kill a success.
    """
    try:
        killed = sbx("kill", sid, timeout=180)
        if killed.returncode != 0:
            print(f"run: WARNING kill exit {killed.returncode}",
                  file=sys.stderr)
        listing = sbx("list", timeout=120)
    except subprocess.TimeoutExpired:
        print(f"run: FAILED cleanup: sbx kill/list timed out; "
              f"run sbx kill {sid}", file=sys.stderr)
        return False
    if listing.returncode != 0 or listing.stdout is None:
        print(f"run: FAILED cleanup: cannot confirm kill of {sid} "
              f"(sbx list exit {listing.returncode}) — the sandbox may still "
              "be running and billable; run sbx kill for this id",
              file=sys.stderr)
        return False
    ids = [line.split()[0] for line in listing.stdout.splitlines()
           if line.strip()]
    if sid in ids:
        print(f"run: FAILED cleanup: sandbox {sid} still live; "
              "run sbx kill for this id", file=sys.stderr)
        return False
    if killed.returncode != 0:
        print(f"run: WARNING: kill exited {killed.returncode} but the "
              "sandbox is confirmed gone", file=sys.stderr)
    print(f"run: killed and confirmed gone: {sid}", flush=True)
    return True


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
                         REPO, CLONE_DIR, timeout=360))

        def in_sandbox(name: str, cmd: str, timeout: float,
                       echo: bool = False) -> subprocess.CompletedProcess:
            proc = step(name, lambda: sbx(
                "exec", sid, "--timeout", str(timeout), "--",
                f"cd {CLONE_DIR}/{DEMO} && {cmd}",
                timeout=timeout + 60))
            if echo:
                show(proc)
            return proc

        in_sandbox("judge/setup.sh", "bash judge/setup.sh", 900)
        in_sandbox("judge/selftest.sh", "bash judge/selftest.sh", 1800,
                   echo=True)
        graded = in_sandbox(
            f"judge/grade.sh {ARTIFACT}",
            f"bash judge/grade.sh {ARTIFACT} --json /tmp/verdict.json", 900,
            echo=True)

        try:
            verdict = json.loads(graded.stdout[graded.stdout.index("{"):])
        except (ValueError, json.JSONDecodeError) as exc:
            raise Failure(f"could not parse the verdict JSON: {exc}\n"
                          f"{graded.stdout[-1000:]}") from exc
        gates = verdict.get("gates", {})
        coverage = gates.get("g2_coverage", {})
        print("run: SUMMARY "
              f"passed={verdict.get('passed')} "
              f"defects_caught={coverage.get('caught')}/"
              f"{coverage.get('planted')} "
              f"clean_pr_majors="
              f"{gates.get('g3_clean_prs', {}).get('major_findings_on_clean_prs')} "
              f"buggy_tests_failing={gates.get('g4_failing_test', {}).get('passed')} "
              f"fixed_tests_passing={gates.get('g5_passing_test', {}).get('passed')}",
              flush=True)
        if not verdict.get("passed"):
            raise Failure(f"judge did not pass: {verdict.get('failed_gate')}")
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
            elif not confirm_killed(sid):
                sys.exit(1)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
