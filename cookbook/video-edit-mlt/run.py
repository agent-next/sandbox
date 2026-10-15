#!/usr/bin/env python3
"""Run the pinned demo in a fresh sandbox. Python 3.10+, stdlib only."""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/video-edit-mlt"


def sbx(*args, timeout=120):
    return subprocess.run(["sbx", *args], capture_output=True, text=True, timeout=timeout)


def detached(sid, name, command, timeout):
    """Persist the command and exit status across transient stream failures."""
    tag = "/tmp/video-edit-" + name
    script = f"{command} >{tag}.log 2>&1; echo $? >{tag}.rc"
    launch = f"nohup bash -c {shlex.quote(script)} >/dev/null 2>&1 </dev/null &"
    p = sbx("exec", "--timeout", "60", sid, "--", launch)
    if p.returncode:
        return p
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(3)
        try:
            p = sbx("exec", "--timeout", "30", sid, "--",
                    f"if [ -f {tag}.rc ]; then cat {tag}.rc; else echo PENDING; fi")
        except subprocess.TimeoutExpired:
            continue
        if p.returncode or p.stdout.strip() == "PENDING":
            continue
        status = p.stdout.strip()
        for _ in range(5):
            out = sbx("exec", "--timeout", "60", sid, "--", f"cat {tag}.log")
            if out.returncode == 0:
                return subprocess.CompletedProcess(name, int(status) if status.isdigit() else 1,
                                                   out.stdout, out.stderr)
            time.sleep(3)
        return subprocess.CompletedProcess(name, 1, "", "could not retrieve step output")
    return subprocess.CompletedProcess(name, 1, "", f"{name} timed out after {timeout}s")


def kill_confirmed(sid, attempts=5):
    for i in range(attempts):
        try:
            sbx("kill", sid, timeout=180)
            p = sbx("list")
            if p.returncode == 0 and sid not in p.stdout:
                return True
        except subprocess.TimeoutExpired:
            pass
        time.sleep(3*(i+1))
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="main")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    if not shutil.which("sbx") or not (os.getenv("SBX_API_KEY") or os.getenv("E2B_API_KEY")):
        print("Needs sbx CLI and SBX_API_KEY (or E2B_API_KEY).", file=sys.stderr)
        return 1
    sid, failed = None, False
    started = time.monotonic()

    def step(name, fn):
        start = time.monotonic()
        p = fn()
        print(f"run: [{time.monotonic()-start:.1f}s] {name} -> exit {p.returncode}", flush=True)
        if p.stdout:
            print(p.stdout.rstrip(), flush=True)
        if p.returncode:
            raise RuntimeError(f"{name}: {p.stderr[-2000:]}")
        return p

    try:
        p = step("sbx create --timeout-min 120",
                 lambda: sbx("create", "--timeout-min", "120"))
        sid = p.stdout.strip().splitlines()[-1]
        print(f"run: sandbox {sid}", flush=True)
        step("git clone", lambda: detached(
            sid, "clone", "git clone --depth 1 -b " + shlex.quote(args.ref) +
            f" {REPO} /tmp/repo && git -C /tmp/repo rev-parse HEAD", 600))
        for name, command, timeout in (
            ("setup", "bash judge/setup.sh", 1200),
            ("selftest", "bash judge/selftest.sh", 1800),
            ("grade", "bash judge/grade.sh examples/good/edit.mlt --seed 1", 300),
        ):
            p = step(name, lambda n=name, c=command, t=timeout: detached(
                sid, n, f"cd /tmp/repo/{DEMO} && {c}", t))
        verdict = json.loads(p.stdout)
        if not verdict["passed"]:
            raise RuntimeError("judge verdict failed")
        print("run: SUMMARY passed=True " +
              " ".join(f"{n}={g['measured']}" for n, g in verdict["gates"].items()
                       if n in {"edl", "dissolve", "ducking", "loudness"}), flush=True)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"run: FAILED: {exc}", file=sys.stderr)
        failed = True
    finally:
        if sid:
            if args.keep:
                print(f"run: --keep: sandbox {sid} left running")
            elif kill_confirmed(sid):
                print(f"run: killed and confirmed gone: {sid}", flush=True)
            else:
                print(f"run: FAILED cleanup: sandbox {sid} could not be confirmed gone",
                      file=sys.stderr)
                failed = True
        print(f"run: total wall {time.monotonic()-started:.1f}s", flush=True)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
