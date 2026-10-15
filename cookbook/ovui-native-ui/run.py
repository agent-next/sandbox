#!/usr/bin/env python3
"""One-command run for the ovui-native-ui demo.

Creates a disposable agent-next sandbox, clones this repo at --ref
(default: main), installs the pinned tools (judge/setup.sh), runs the
judge self-test (judge/selftest.sh) and grades the known-good panel
(judge/grade.sh examples/good/panel.py), prints the verdict JSON and a
short human summary, and always kills the sandbox afterwards.

Needs the sbx CLI and SBX_API_KEY (or E2B_API_KEY) in the environment:
  pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"

Usage: run.py [--ref GIT_REF] [--keep] [--timeout-min N]

The panel is rendered headless on Mesa lavapipe (CPU Vulkan); no GPU, no
display and no NVIDIA account are required.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/ovui-native-ui"
ARTIFACT = "examples/good/panel.py"


def sbx(*argv):
    """Run an sbx subcommand, return (output, exit_code)."""
    p = subprocess.run(["sbx", *argv], capture_output=True, text=True)
    return (p.stdout + p.stderr).strip(), p.returncode


def sbx_exec(sid, command, step_timeout=1800):
    t0 = time.time()
    p = subprocess.run(["sbx", "exec", sid, "--timeout", str(step_timeout),
                        "--", "bash", "-lc", command],
                       capture_output=True, text=True)
    return p.stdout + p.stderr, p.returncode, time.time() - t0


def confirm_gone(sid):
    """Return True only if sid is provably absent from sbx list."""
    out, rc = sbx("list")
    if rc != 0:
        return False
    return sid not in out


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
    exit_code = 1
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
            if line.startswith(("mutant ", "kill rate:", "good:")):
                print(f"    {line}")

        out = step("grade", f"cd {d} && bash judge/grade.sh {ARTIFACT}")
        verdict = json.loads(out[out.index("{"):out.rindex("}") + 1])
        print(json.dumps(verdict, indent=2))

        gates = verdict.get("gates", [])
        passed = verdict.get("pass") and all(g.get("ok") for g in gates)
        swatch = next((g.get("detail", {}).get("swatch_median")
                       for g in gates if g.get("gate") == "pixels"), None)
        print(f"verdict: {'PASS' if passed else 'FAIL'}"
              f"  gates: {sum(1 for g in gates if g.get('ok'))}/{len(gates)}"
              f"  swatch median RGB: {swatch}")
        exit_code = 0 if passed else 1
    finally:
        if sid:
            if args.keep:
                print(f"kept sandbox {sid} (kill with: sbx kill {sid})")
            else:
                sbx("kill", sid)
                if not confirm_gone(sid):
                    print(f"ERROR: could not confirm sandbox {sid} is gone; "
                          f"kill it by hand with: sbx kill {sid}",
                          file=sys.stderr)
                    sys.exit(2)
                print(f"sandbox {sid} removed")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
