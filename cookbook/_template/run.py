#!/usr/bin/env python3
"""One-command run for the __NAME__ demo.

Creates a disposable agent-next sandbox, clones this repo at --ref
(default: main), runs judge/setup.sh, judge/selftest.sh and
judge/grade.sh on the known-good artifact, prints the verdict JSON, and
always kills the sandbox afterwards.

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
DEMO = "cookbook/__NAME__"


def sbx(*argv):
    """Run an sbx subcommand, return (output, exit_code)."""
    p = subprocess.run(["sbx", *argv], capture_output=True, text=True)
    return (p.stdout + p.stderr).strip(), p.returncode


def sbx_exec(sid, command, step_timeout=900):
    t0 = time.time()
    p = subprocess.run(["sbx", "exec", sid, "--timeout", str(step_timeout),
                        "--", "bash", "-lc", command],
                       capture_output=True, text=True)
    return p.stdout + p.stderr, p.returncode, time.time() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="main", help="git ref to clone (default: main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    ap.add_argument("--timeout-min", type=int, default=30,
                    help="sandbox lifetime in minutes (default: 30)")
    args = ap.parse_args()

    if not shutil.which("sbx"):
        sys.exit("sbx CLI not found; install with: pip install "
                 "\"git+https://github.com/agent-next/sandbox#subdirectory=cli\"")
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        sys.exit("set SBX_API_KEY (or E2B_API_KEY) in the environment")

    sid = None
    try:
        t0 = time.time()
        out, rc = sbx("create", "--timeout-min", str(args.timeout_min))
        if rc != 0:
            sys.exit(f"sbx create failed: {out}")
        sid = out.splitlines()[-1].strip()
        print(f"[{time.time()-t0:5.1f}s] sandbox {sid}")

        def step(name, command):
            t0 = time.time()
            out, rc, el = sbx_exec(sid, command)
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
            if line.startswith(("mutant ", "kill rate:", "determinism:")):
                print(f"    {line}")
        out = step("grade", f"cd {d} && bash judge/grade.sh examples/good")
        verdict = json.loads(out[out.index("{"):])
        print(json.dumps(verdict, indent=2))
        ok = verdict.get("verdict") == "PASS"
        print(f"verdict: {verdict.get('verdict')}")
        sys.exit(0 if ok else 1)
    finally:
        if sid:
            if args.keep:
                print(f"kept sandbox {sid} (kill with: sbx kill {sid})")
            else:
                _, kill_rc = sbx("kill", sid)
                out, list_rc = sbx("list")
                if list_rc != 0 or sid in out:
                    why = "sbx list failed" if list_rc != 0 else "still in sbx list"
                    print(f"WARNING: cleanup of sandbox {sid} not confirmed "
                          f"({why}, kill rc={kill_rc}); kill it with: sbx kill {sid}",
                          file=sys.stderr)
                    sys.exit(2)
                print(f"sandbox {sid} removed")


if __name__ == "__main__":
    main()
