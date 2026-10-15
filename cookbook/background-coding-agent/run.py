#!/usr/bin/env python3
"""One-command run for the background-coding-agent cookbook demo
(DEMO-STANDARD.md).

Creates a disposable agent-next sandbox, clones this repo into it, installs
the pinned tools, runs the judge self-test, grades the known-good delivery,
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
DEMO = "cookbook/background-coding-agent"
ARTIFACT = "examples/good/delivery.patch"
ARTIFACT_PR = "examples/good/PR.md"
CLONE_DIR = "bca-demo-repo"


class Failure(RuntimeError):
    pass


def sbx(*args: str, timeout: float = 120.0) -> subprocess.CompletedProcess:
    """Run one sbx CLI command; never raises, caller checks exit code."""
    return subprocess.run(["sbx", *args], capture_output=True, text=True,
                          timeout=timeout)


def retry_sbx(name: str, args: tuple[str, ...], attempts: int,
              timeout: float = 120.0) -> subprocess.CompletedProcess:
    """Run an sbx command, retrying with backoff while the service answers
    429/quota (a capacity condition, not a verdict on the command: another
    tenant's sandbox can hold the last concurrent slot for a while).  Every
    attempt prints its outcome; a non-rate-limit failure returns at once."""
    delay = 10.0
    for attempt in range(1, attempts + 1):
        proc = sbx(*args, timeout=timeout)
        if proc.returncode == 0:
            return proc
        blob = (proc.stdout or "") + (proc.stderr or "")
        transient = proc.returncode != 0 and (
            "RateLimitException" in blob or "429" in blob
            or "quota exceeded" in blob or "try again later" in blob)
        if not transient or attempt == attempts:
            return proc
        print(f"run: {name} hit a rate limit (attempt {attempt}/{attempts}); "
              f"retrying in {delay:.0f} s", flush=True)
        time.sleep(delay)
        delay *= 2
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
    (each 'selftest: killed <mutant> (gate: ...)', the kill rate, the
    verdict)."""
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
        # 6 attempts with 10..320 s backoff: a concurrent-quota 429 can last
        # as long as another tenant's sandbox holds the slot (up to its
        # timeout-min lifetime), and giving up on the first one fails a demo
        # that would have run.
        created = step(
            "sbx create --timeout-min 30",
            lambda: retry_sbx("sbx create", ("create", "--timeout-min", "30"),
                              attempts=6, timeout=120))
        sid = created.stdout.strip().splitlines()[-1].strip()
        print(f"run: sandbox {sid}", flush=True)

        step("git clone",
             lambda: sbx("exec", sid, "--timeout", "300", "--",
                         "git", "clone", "--depth", "1", "-b", args.ref,
                         REPO, CLONE_DIR, timeout=420))

        def in_sandbox(name: str, cmd: str, timeout: float,
                       echo: bool = False) -> subprocess.CompletedProcess:
            # The local subprocess timer must exceed the CLI --timeout it
            # hands over, or Python kills a step the sandbox is still
            # running happily (selftest alone takes ~4 minutes).
            proc = step(name, lambda: sbx(
                "exec", sid, "--timeout", str(int(timeout)), "--",
                f"cd {CLONE_DIR}/{DEMO} && {cmd}",
                timeout=timeout + 120))
            if echo:
                show(proc)
            return proc

        in_sandbox("judge/setup.sh", "bash judge/setup.sh", 900)
        in_sandbox("judge/selftest.sh", "bash judge/selftest.sh", 900,
                   echo=True)
        graded = in_sandbox(
            f"judge/grade.sh {ARTIFACT}",
            f"bash judge/grade.sh {ARTIFACT} --pr {ARTIFACT_PR} "
            f"--json /tmp/verdict.json", 900, echo=True)

        try:
            verdict = json.loads(graded.stdout[graded.stdout.index("{"):])
        except (ValueError, json.JSONDecodeError) as exc:
            raise Failure(f"could not parse the verdict JSON: {exc}\n"
                          f"{graded.stdout[-1000:]}") from exc
        gates = verdict.get("gates", {})
        print("run: SUMMARY "
              f"passed={verdict.get('passed')} "
              f"files={gates.get('patch', {}).get('files')} "
              f"regression={gates.get('regression', {}).get('tests_collected')}"
              f" passed "
              f"acceptance="
              f"{gates.get('acceptance', {}).get('tests_collected')} passed "
              f"lint_findings={gates.get('lint', {}).get('findings')} "
              f"oracle_cases={len(gates.get('oracle', {}).get('cases', []))} "
              f"pr_chars={gates.get('pr', {}).get('chars')}",
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
                try:
                    killed = sbx("kill", sid, timeout=180)
                    if killed.returncode != 0:
                        print(f"run: WARNING kill exit {killed.returncode}",
                              file=sys.stderr)
                    listing = sbx("list", timeout=120)
                except subprocess.TimeoutExpired:
                    print(f"run: FAILED cleanup: sbx kill/list timed out; "
                          f"run sbx kill {sid}", file=sys.stderr)
                    sys.exit(1)
                if sid in (listing.stdout or ""):
                    print(f"run: FAILED cleanup: sandbox {sid} still live; "
                          "run sbx kill for this id", file=sys.stderr)
                    sys.exit(1)
                print(f"run: killed and confirmed gone: {sid}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
