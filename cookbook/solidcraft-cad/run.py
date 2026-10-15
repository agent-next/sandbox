#!/usr/bin/env python3
"""One-command run for the solidcraft-cad cookbook demo (DEMO-STANDARD.md).

Creates a disposable agent-next sandbox, clones this repo into it, installs
the pinned tools, runs the judge self-test, grades the known-good design
script, prints the verdict, then always kills the sandbox and confirms it
is gone. Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage: python3 run.py [--ref main] [--keep]
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/solidcraft-cad"
ARTIFACT = "examples/good/design.json"
CLONE_DIR = "solidcraft-demo-repo"


class Failure(RuntimeError):
    pass


def sbx(*args: str, timeout: float = 120.0) -> subprocess.CompletedProcess:
    """Run one sbx CLI command; never raises, caller checks exit code."""
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


def detached(sid: str, name: str, cmd: str, timeout: float) -> subprocess.CompletedProcess:
    """Run a long step in the background inside the sandbox and poll for its
    exit code with short sbx calls.  A dropped stream or a gateway restart
    during a 10-minute step is then retried instead of being mistaken for the
    step's exit (the step keeps running in the sandbox either way)."""
    tag = "/tmp/run-" + "".join(ch if ch.isalnum() else "-" for ch in name)
    launch = (f"rm -f {tag}.rc; (bash -c {shlex.quote(cmd)} > {tag}.out 2>&1 < /dev/null; "
              f"echo $? > {tag}.rc) > /dev/null 2>&1 < /dev/null &")
    poll = f"if [ -f {tag}.rc ]; then cat {tag}.rc; else echo PENDING; fi"
    if sbx("exec", sid, "--timeout", "60", "--", launch, timeout=120).returncode != 0:
        return subprocess.CompletedProcess(name, 1, "", f"could not start {name} in the sandbox")
    deadline, errors = time.monotonic() + timeout, 0
    while time.monotonic() < deadline:
        time.sleep(10)
        try:
            p = sbx("exec", sid, "--timeout", "30", "--", poll, timeout=90)
        except subprocess.TimeoutExpired:
            p = subprocess.CompletedProcess(name, 1, "", "poll timed out")
        if p.returncode != 0:  # transport error: the step itself is unaffected
            errors += 1
            if "not found" in (p.stderr or "") or errors > 30:
                return subprocess.CompletedProcess(name, 1, "", f"lost the sandbox while polling {name}: {p.stderr}")
            continue
        errors = 0
        status = p.stdout.strip()
        if status != "PENDING":
            for _ in range(5):
                out = sbx("exec", sid, "--timeout", "60", "--", f"cat {tag}.out", timeout=120)
                if out.returncode == 0:
                    break
                time.sleep(5)
            rc = int(status) if status.isdigit() else 1
            return subprocess.CompletedProcess(name, rc, out.stdout, out.stderr)
    return subprocess.CompletedProcess(name, 1, "", f"{name} did not finish within {timeout:.0f} s")


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
            proc = step(name, lambda: detached(sid, name, f"cd {CLONE_DIR}/{DEMO} && {cmd}", timeout))
            if echo:
                show(proc)
            return proc

        in_sandbox("judge/setup.sh", "bash judge/setup.sh", 1200)
        in_sandbox("judge/selftest.sh", "bash judge/selftest.sh", 1800,
                   echo=True)
        graded = in_sandbox(
            f"judge/grade.sh {ARTIFACT}",
            f"bash judge/grade.sh {ARTIFACT} --json /tmp/verdict.json", 600,
            echo=True)

        try:
            verdict = json.loads(graded.stdout[graded.stdout.index("{"):])
        except (ValueError, json.JSONDecodeError) as exc:
            raise Failure(f"could not parse the verdict JSON: {exc}\n"
                          f"{graded.stdout[-1000:]}") from exc
        g = verdict.get("gates", {})
        print("run: SUMMARY "
              f"passed={verdict.get('passed')} "
              f"volume={g.get('volume', {}).get('occt_mm3')} mm3 "
              f"(analytic {g.get('volume', {}).get('analytic_mm3')}) "
              f"mass={g.get('mass', {}).get('mass_g')} g "
              f"bolt_holes={g.get('features', {}).get('bolt_holes')} "
              f"kernels_agree={g.get('cross_check', {}).get('volume_rel_dev')} "
              f"param_dV={g.get('parametric', {}).get('volume_delta_mm3')} mm3",
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
