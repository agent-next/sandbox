#!/usr/bin/env python3
"""One-command run for the backtest-equity demo (cookbook/DEMO-STANDARD.md).

Creates a disposable agent-next sandbox, clones this repo at --ref
(default main), runs the judge self-test, grades the known-good artifact,
prints the verdict JSON and a short human summary, and always kills the
sandbox afterwards, confirming with `sbx list` that the id is gone.
Exits non-zero on any failure, naming the sandbox id if cleanup could not
be confirmed.

Needs the `sbx` CLI and SBX_API_KEY (or E2B_API_KEY) in the environment:
  pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"

Usage: run.py [--ref GIT_REF] [--keep] [--timeout-min N]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/backtest-equity"
ARTIFACT = "examples/good"
DEFAULT_TIMEOUT_MIN = 45
STEP_TIMEOUT_S = 900


def sbx(*argv, timeout=STEP_TIMEOUT_S):
    """Run one sbx CLI command, return (output, exit code).  Never raises;
    the caller checks the exit code."""
    p = subprocess.run(["sbx", *argv], capture_output=True, text=True,
                       timeout=timeout)
    return (p.stdout + p.stderr).strip(), p.returncode


def in_sandbox(sid, command, timeout=STEP_TIMEOUT_S):
    """Run a shell command inside the sandbox, return (output, exit code)."""
    p = subprocess.run(
        ["sbx", "exec", sid, "--timeout", str(timeout), "--",
         "bash", "-lc", command],
        capture_output=True, text=True, timeout=timeout + 60)
    return (p.stdout or "") + (p.stderr or ""), p.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="main",
                    help="git ref to clone (default: main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    ap.add_argument("--timeout-min", type=int, default=DEFAULT_TIMEOUT_MIN,
                    help=f"sandbox lifetime in minutes (default: {DEFAULT_TIMEOUT_MIN})")
    args = ap.parse_args()

    if not shutil.which("sbx"):
        sys.exit("sbx CLI not found; install with: pip install "
                 '"git+https://github.com/agent-next/sandbox#subdirectory=cli"')
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        sys.exit("set SBX_API_KEY (or E2B_API_KEY) in the environment")

    sid = None
    clone = "backtest-demo-repo"
    try:
        t0 = time.monotonic()
        out, rc = sbx("create", "--timeout-min", str(args.timeout_min))
        if rc != 0:
            sys.exit(f"sbx create failed: {out}")
        sid = [line for line in out.splitlines() if line.strip()][-1].strip()
        print(f"[{time.monotonic()-t0:5.1f}s] sandbox {sid}")

        def step(name, command, timeout=STEP_TIMEOUT_S):
            t0 = time.monotonic()
            out, rc = in_sandbox(sid, command, timeout)
            status = "ok" if rc == 0 else f"FAILED rc={rc}"
            print(f"[{time.monotonic()-t0:6.1f}s] {name}: {status}", flush=True)
            if rc != 0:
                print(out[-4000:], file=sys.stderr)
                sys.exit(rc)
            return out

        step("clone", f"git clone --depth 1 -b {args.ref} {REPO} {clone}")
        d = f"{clone}/{DEMO}"
        step("setup", f"cd {d} && bash judge/setup.sh")
        selftest_out = step("selftest", f"cd {d} && bash judge/selftest.sh")
        for line in selftest_out.splitlines():
            if line.startswith(("mutant ", "kill rate:", "determinism:",
                                "judge integrity:", "selftest:")):
                print(f"    {line}")
        graded = step("grade", f"cd {d} && bash judge/grade.sh {ARTIFACT} "
                               f"--seed 42 --json /tmp/verdict.json")

        try:
            verdict = json.loads(graded[graded.index("{"):])
        except (ValueError, json.JSONDecodeError) as exc:
            sys.exit(f"could not parse the verdict JSON ({exc}): "
                     f"{graded[-1000:]}")
        print(json.dumps(verdict, indent=2))
        m = verdict.get("metrics", {})
        r = verdict.get("metrics", {}).get("reference", {})
        print("run: SUMMARY "
              f"verdict={verdict.get('verdict')} "
              f"final_equity={m.get('final_equity')} "
              f"(reference {r.get('final_equity')}) "
              f"sharpe={m.get('sharpe')} "
              f"max_drawdown={m.get('max_drawdown')} "
              f"n_trades={m.get('n_trades')} "
              f"n_days={m.get('n_days')} "
              f"failed_gates={verdict.get('failed_gates')}")
        sys.exit(0 if verdict.get("verdict") == "PASS" else 1)
    except subprocess.TimeoutExpired as exc:
        sys.exit(f"sbx command timed out: {exc}")
    finally:
        if sid:
            if args.keep:
                print(f"kept sandbox {sid} (kill with: sbx kill {sid})")
            else:
                # Kill, then CONFIRM with `sbx list` that the id is gone.
                # A listing that cannot be obtained (gateway 5xx, network)
                # proves nothing: a lost reply is not a confirmation
                # (DEMO-STANDARD.md; LESSONS.md), so it fails the run rather
                # than passing vacuously.  The id is searched for only in a
                # listing that exited 0 -- never inside error text, where an
                # id that happens to appear must not read as "still up".
                try:
                    killed_out, killed_rc = sbx("kill", sid, timeout=300)
                    if killed_rc != 0:
                        print(f"WARNING: sbx kill exit {killed_rc}: "
                              f"{killed_out}", file=sys.stderr)
                    listing_out, listing_rc = sbx("list", timeout=300)
                except subprocess.TimeoutExpired:
                    print(f"cleanup timed out: sandbox {sid} may still be "
                          f"running; confirm with: sbx list", file=sys.stderr)
                    sys.exit(2)
                if listing_rc != 0:
                    print(f"could not confirm sandbox {sid} is gone: "
                          f"sbx list exit {listing_rc}: {listing_out}",
                          file=sys.stderr)
                    sys.exit(2)
                if sid in listing_out:
                    print(f"sandbox {sid} is still in sbx list; kill it "
                          f"with: sbx kill {sid}", file=sys.stderr)
                    sys.exit(2)
                if killed_rc != 0:
                    # kill itself failed, but a listing that exited 0 and
                    # does not show the id proves the sandbox is gone from
                    # the account.  Report exactly that; do not claim a kill.
                    print(f"WARNING: sbx kill exit {killed_rc}, but sbx "
                          f"list no longer shows sandbox {sid} (gone)")
                else:
                    print(f"sandbox {sid} killed and confirmed gone")


if __name__ == "__main__":
    main()
