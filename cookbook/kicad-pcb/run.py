#!/usr/bin/env python3
"""One-command run: kicad-pcb demo inside a disposable sbx sandbox.

    python3 run.py [--ref main] [--keep]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY or E2B_API_KEY in the environment.

Creates a sandbox, clones this repository at --ref, then inside it runs
judge/setup.sh, judge/selftest.sh and grades the known-good example.
Prints the verdict JSON plus per-step wall times. The sandbox is always
killed (and its absence verified with `sbx list`) unless --keep is given.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "repo/cookbook/kicad-pcb"


def sbx(*args, timeout=None, check=True):
    return subprocess.run(["sbx", *args], timeout=timeout, check=check)


def sbx_out(*args):
    return subprocess.run(["sbx", *args], check=True,
                          capture_output=True, text=True).stdout


def step(name, sid, cmd, timeout):
    print(f"--- {name}", flush=True)
    t0 = time.time()
    try:  # backstop in case the sbx client itself stalls
        rc = sbx("exec", sid, "--timeout", str(timeout), "--", cmd,
                 check=False, timeout=timeout + 120).returncode
    except subprocess.TimeoutExpired:
        rc = 124
    dt = time.time() - t0
    print(f"    {dt:.0f}s, exit {rc}", flush=True)
    return rc, dt


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="main",
                    help="git ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running, print its id")
    args = ap.parse_args()

    if not shutil.which("sbx"):
        sys.exit("sbx CLI not found; see README")
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        sys.exit("export SBX_API_KEY (or E2B_API_KEY)")

    sid = sbx_out("create", "--timeout-min", "30").strip().splitlines()[-1]
    print(f"sandbox: {sid}", flush=True)
    timing = {}
    rc = 1
    try:
        steps = [
            ("clone", f"git clone --depth 1 -b {shlex.quote(args.ref)} "
                      f"{REPO} repo", 600),
            ("setup", f"cd {DEMO} && bash judge/setup.sh", 1200),
            ("selftest", f"cd {DEMO} && bash judge/selftest.sh", 900),
            ("grade", f"cd {DEMO} && bash judge/grade.sh "
                      "examples/good/555-blinker --json /tmp/verdict.json"
                      " && cat /tmp/verdict.json", 600),
        ]
        for name, cmd, limit in steps:
            rc, timing[name] = step(name, sid, cmd, timeout=limit)
            if rc:
                print(f"{name} failed", file=sys.stderr)
                break
    finally:
        if args.keep:
            print(f"kept sandbox {sid} running (kill it with: "
                  f"sbx kill {sid})")
        else:
            try:
                sbx("kill", sid, check=False)
            except Exception:
                pass
            try:
                listed = sbx_out("list")
                if sid in listed:
                    print(f"WARNING: cleanup unconfirmed; {sid} still in "
                          f"`sbx list` output — run: sbx kill {sid}",
                          file=sys.stderr)
                    rc = 1
                else:
                    print(f"destroyed {sid}; verified absent", flush=True)
            except Exception:
                print(f"WARNING: cleanup unconfirmed for {sid}; "
                      f"run: sbx kill {sid}", file=sys.stderr)
                rc = 1

    print("--- summary")
    for k, v in timing.items():
        print(f"    {k:10s} {v:6.0f}s")
    sys.exit(rc)


if __name__ == "__main__":
    main()
