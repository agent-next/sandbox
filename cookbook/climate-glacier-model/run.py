#!/usr/bin/env python3
"""One-command run for the climate-glacier-model cookbook demo.

Creates a disposable agent-next sandbox, clones this repo into it, installs
the pinned tools, runs the judge self-test, grades the known-good glacier
sweep, prints the verdict, then always kills the sandbox and confirms it is
gone. Needs the `sbx` CLI (pip install
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
DEMO = "cookbook/climate-glacier-model"
ARTIFACT = "examples/good"
CLONE_DIR = "glacier-demo-repo"


class Failure(RuntimeError):
    pass


def sbx(*args: str, timeout: float = 120.0) -> subprocess.CompletedProcess:
    """Run one sbx CLI command; never raises, caller checks exit code."""
    return subprocess.run(["sbx", *args], capture_output=True, text=True,
                          timeout=timeout)


def step(name: str, fn, echo: bool = False) -> subprocess.CompletedProcess:
    start = time.monotonic()
    proc = fn()
    dt = time.monotonic() - start
    print(f"run: [{dt:6.1f}s] {name} -> exit {proc.returncode}", flush=True)
    # Echo before raising: on a failed grade the judge's verdict JSON is the
    # most useful thing to show, and a bare "exit 1" would hide it.
    if echo and proc.stdout:
        print(proc.stdout.rstrip(), flush=True)
    if proc.returncode != 0:
        tail = (proc.stdout or "") + (proc.stderr or "")
        raise Failure(f"{name} failed (exit {proc.returncode}):\n"
                      f"{tail.strip()[-2000:]}")
    return proc


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
            # `timeout` is the sandbox-side limit; the local subprocess gets
            # a buffer on top so a slow-but-working step is not killed here.
            return step(name, lambda: sbx(
                "exec", sid, "--timeout", str(timeout), "--",
                f"cd {CLONE_DIR}/{DEMO} && {cmd}", timeout=timeout + 60),
                echo=echo)

        in_sandbox("judge/setup.sh", "bash judge/setup.sh", 900)
        in_sandbox("judge/selftest.sh", "bash judge/selftest.sh", 900,
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
        final = gates.get("final_volume", {}).get("scenarios", {})
        crossing = gates.get("crossing", {}).get("scenarios", {})
        summary = " ".join(
            f"{name}:V100={final.get(name, {}).get('measured_km3')}"
            f"/t50={crossing.get(name, {}).get('reported_year')}"
            for name in sorted(final))
        print("run: SUMMARY "
              f"passed={verdict.get('passed')} "
              f"zero_melt_worst="
              f"{gates.get('zero_melt', {}).get('worst_relative_deviation')} "
              f"rows={gates.get('artifact', {}).get('rows')} {summary}",
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
