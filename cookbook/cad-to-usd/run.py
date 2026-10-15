#!/usr/bin/env python3
"""One-command run for the cad-to-usd demo.

Creates a disposable agent-next sandbox, clones this repo at --ref
(default: main), runs judge/setup.sh, judge/selftest.sh and
judge/grade.sh on the known-good artifact, prints the verdict JSON, and
always kills the sandbox afterwards (verified by `sbx list`).

Needs the sbx CLI and SBX_API_KEY (or E2B_API_KEY) in the environment:
  pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"

Usage: run.py [--ref GIT_REF] [--keep] [--timeout-min N]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/cad-to-usd"


def sbx(*argv):
    """Run an sbx subcommand, return (output, exit_code)."""
    p = subprocess.run(["sbx", *argv], capture_output=True, text=True)
    return (p.stdout + p.stderr).strip(), p.returncode


def sbx_exec(sid, command, step_timeout=1800):
    t0 = time.monotonic()
    p = subprocess.run(["sbx", "exec", sid, "--timeout", str(step_timeout),
                        "--", "bash", "-lc", command],
                       capture_output=True, text=True)
    return p.stdout + p.stderr, p.returncode, time.monotonic() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="main",
                    help="git ref to clone (default: main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    ap.add_argument("--timeout-min", type=int, default=60,
                    help="sandbox lifetime in minutes (default: 60 — "
                         "setup fetches a ~500 MB converter wheel)")
    args = ap.parse_args()

    if not shutil.which("sbx"):
        sys.exit("sbx CLI not found; install with: pip install "
                 "\"git+https://github.com/agent-next/sandbox#subdirectory=cli\"")
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        sys.exit("set SBX_API_KEY (or E2B_API_KEY) in the environment")

    sid = None
    try:
        t0 = time.monotonic()
        out, rc = sbx("create", "--timeout-min", str(args.timeout_min))
        if rc != 0:
            sys.exit(f"sbx create failed: {out}")
        sid = out.splitlines()[-1].strip()
        print(f"[{time.monotonic()-t0:5.1f}s] sandbox {sid}")

        def step(name, command, step_timeout=1800):
            out, rc, el = sbx_exec(sid, command, step_timeout)
            status = "ok" if rc == 0 else f"FAILED rc={rc}"
            print(f"[{el:6.1f}s] {name}: {status}")
            if rc != 0:
                print(out[-4000:])
                sys.exit(rc)
            return out

        step("clone", f"git clone --depth 1 -b {args.ref} {REPO} /tmp/repo")
        d = f"/tmp/repo/{DEMO}"
        step("setup", f"cd {d} && bash judge/setup.sh")
        selftest_out = step("selftest", f"cd {d} && bash judge/selftest.sh")
        for line in selftest_out.splitlines():
            if line.lstrip().startswith(("known-good:", "mutant ", "kill rate:",
                                         "determinism:", "selftest: ")):
                print(f"    {line.strip()}")
        out = step("grade", f"cd {d} && bash judge/grade.sh examples/good --seed 42")
        verdict = json.loads(out[out.index("{"):])
        print(json.dumps(verdict, indent=2))
        ok = verdict.get("all_gates_passed") is True
        gates = {k: v.get("passed") for k, v in verdict.get("gates", {}).items()
                 if isinstance(v, dict) and "passed" in v}
        print(f"verdict: {'PASS' if ok else 'FAIL'}  gates: {gates}")
        sys.exit(0 if ok else 1)
    finally:
        if sid:
            if args.keep:
                print(f"kept sandbox {sid} (kill with: sbx kill {sid})")
            else:
                sbx("kill", sid)
                out, _ = sbx("list")
                if sid in out:
                    print(f"ERROR: sandbox {sid} still in sbx list "
                          f"— could not confirm cleanup", file=sys.stderr)
                    sys.exit(2)
                print(f"sandbox {sid} removed")


if __name__ == "__main__":
    main()
