#!/usr/bin/env python3
"""One-command run for the control-tuning demo.

Creates a disposable agent-next sandbox, clones this repo at --ref, runs
judge/setup.sh, judge/selftest.sh and judge/grade.sh on the good example
inside it, prints the verdict and kills the sandbox.

Python 3.10+, standard library only. Requires:
    pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
and SBX_API_KEY (or E2B_API_KEY) in the environment.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

REPO_URL = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/control-tuning"
GOOD = f"{DEMO}/examples/good/controller.json"
TIMEOUT_MIN = 30
SRC = "/home/user/sandbox-src"   # clone target inside the sandbox


def die(msg):
    print(f"run.py: {msg}", file=sys.stderr)
    sys.exit(1)


def sh(cmd):
    """Run cmd through the shell, stream nothing, return CompletedProcess."""
    print(f"+ {cmd}", flush=True)
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(
        description="design-and-judge run for the control-tuning demo")
    ap.add_argument("--ref", default="main", help="repo ref to clone")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    args = ap.parse_args()

    sbx = shutil.which("sbx")
    if not sbx:
        die("sbx CLI not found; install it with: "
            'pip install "git+https://github.com/agent-next/sandbox'
            '#subdirectory=cli"')
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        die("set SBX_API_KEY (or E2B_API_KEY) in the environment")

    sid = None
    t_start = time.monotonic()
    step = {"t": t_start}

    def clock(label):
        now = time.monotonic()
        print(f"[{label}: {now - step['t']:.1f}s]", flush=True)
        step["t"] = now

    def kill_and_confirm():
        print(f"run.py: killing sandbox {sid}", flush=True)
        subprocess.run([sbx, "kill", sid], capture_output=True)
        listing = sh(f"{sbx} list")
        ids = {line.split("\t")[0] for line in listing.stdout.splitlines()}
        if sid in ids:
            print(f"run.py: could not confirm sandbox {sid} was killed; "
                  f"check `sbx list` and remove it manually", file=sys.stderr)
            return False
        return True

    ok = False
    kept = False
    try:
        r = sh(f"{sbx} create --timeout-min {TIMEOUT_MIN}")
        if r.returncode != 0:
            die(f"sbx create failed:\n{r.stderr or r.stdout}")
        sid = r.stdout.strip().splitlines()[-1].strip()
        print(f"run.py: sandbox {sid}", flush=True)
        clock("create")

        steps = [
            (f"git clone --depth 1 -b {args.ref} {REPO_URL} {SRC}", "clone"),
            (f"bash {SRC}/{DEMO}/judge/setup.sh", "setup"),
            (f"bash {SRC}/{DEMO}/judge/selftest.sh", "selftest"),
            (f"bash {SRC}/{DEMO}/judge/grade.sh {SRC}/{GOOD} "
             f"--json /tmp/verdict.json", "grade"),
        ]
        for cmd, label in steps:
            r = sh(f"{sbx} exec --timeout 1200 {sid} -- {cmd}")
            sys.stdout.write(r.stdout or "")
            sys.stderr.write(r.stderr or "")
            if r.returncode != 0:
                die(f"step '{label}' failed with exit {r.returncode} in "
                    f"sandbox {sid}")
            clock(label)

        r = sh(f"{sbx} exec --timeout 60 {sid} -- cat /tmp/verdict.json")
        try:
            verdict = json.loads(r.stdout)
        except json.JSONDecodeError:
            die("could not read the verdict JSON from the sandbox")
        print(json.dumps(verdict, indent=2))
        print(f"\nverdict: {'PASS' if verdict.get('passed') else 'FAIL'} "
              f"({len(verdict.get('gates', {}))} gates, Monte-Carlo "
              f"{verdict.get('mc_pass')}/{verdict.get('mc_n')})", flush=True)
        ok = bool(verdict.get("passed"))
        clock("verdict")
    finally:
        if sid is not None:
            if args.keep:
                kept = True
                print(f"run.py: --keep set, leaving sandbox {sid} running "
                      f"(kill it with: sbx kill {sid})", flush=True)
            else:
                if not kill_and_confirm():
                    sys.exit(1)

    print(f"run.py: total {time.monotonic() - t_start:.1f}s", flush=True)
    if kept and not ok:
        print(f"run.py: run failed; sandbox {sid} left up by --keep")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
