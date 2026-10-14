#!/usr/bin/env python3
"""One-command run for the control-tuning demo.

Creates a disposable agent-next sandbox, clones this repo at --ref, runs
judge/setup.sh, judge/selftest.sh and judge/grade.sh on the good example
inside it, prints the verdict and always kills the sandbox.

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


def die(msg):
    print(f"run.py: {msg}", file=sys.stderr)
    sys.exit(1)


def sh(cmd, **kw):
    """Run cmd, return CompletedProcess; stdout passes through by default."""
    print(f"+ {cmd}", flush=True)
    return subprocess.run(cmd, shell=True, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="main",
                    help=f"repo ref to clone (default: main)")
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
    killed = False
    t_start = time.monotonic()
    step = {"t": t_start}

    def clock(label):
        now = time.monotonic()
        print(f"[{label}: {now - step['t']:.1f}s]", flush=True)
        step["t"] = now

    def cleanup():
        nonlocal killed
        if sid is None or killed:
            return
        killed = True
        print(f"run.py: killing sandbox {sid}", flush=True)
        subprocess.run([sbx, "kill", sid], capture_output=True)
        listing = subprocess.run([sbx, "list"], capture_output=True,
                                 text=True)
        if sid in listing.stdout:
            print(f"run.py: could not confirm sandbox {sid} was killed; "
                  f"check `sbx list` and remove it manually", file=sys.stderr)
            sys.exit(1)

    try:
        r = sh(f"{sbx} create --timeout-min {TIMEOUT_MIN}", capture_output=True,
               text=True)
        if r.returncode != 0:
            die(f"sbx create failed:\n{r.stderr or r.stdout}")
        sid = r.stdout.strip().splitlines()[-1].strip()
        print(f"run.py: sandbox {sid}", flush=True)
        clock("create")

        steps = [
            (f"git clone --depth 1 -b {args.ref} {REPO_URL} /sandbox-src",
             "clone"),
            ("bash /sandbox-src/" + DEMO + "/judge/setup.sh", "setup"),
            ("bash /sandbox-src/" + DEMO + "/judge/selftest.sh", "selftest"),
            ("bash /sandbox-src/" + DEMO + "/judge/grade.sh /sandbox-src/"
             + GOOD + " --json /tmp/verdict.json", "grade"),
        ]
        for cmd, label in steps:
            r = sh(f"{sbx} exec --timeout 1200 {sid} -- {cmd!r}",
                   capture_output=True, text=True)
            sys.stdout.write(r.stdout or "")
            sys.stderr.write(r.stderr or "")
            if r.returncode != 0:
                die(f"step '{label}' failed with exit {r.returncode} in "
                    f"sandbox {sid}")
            clock(label)

        try:
            verdict = json.loads(
                sh(f"{sbx} exec {sid} 'cat /tmp/verdict.json'",
                   capture_output=True, text=True).stdout)
        except json.JSONDecodeError:
            die("could not read the verdict JSON from the sandbox")
        print(json.dumps(verdict, indent=2))
        print(f"\nverdict: {'PASS' if verdict.get('passed') else 'FAIL'} "
              f"({len(verdict.get('gates', {}))} gates, "
              f"Monte-Carlo {verdict.get('mc_pass')}/{verdict.get('mc_n')})",
              flush=True)
        clock("verdict")
        ok = bool(verdict.get("passed"))
    finally:
        cleanup()

    print(f"run.py: total {time.monotonic() - t_start:.1f}s", flush=True)
    if args.keep:
        print(f"run.py: --keep ignored after successful kill; sandbox {sid} "
              f"is already destroyed")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
