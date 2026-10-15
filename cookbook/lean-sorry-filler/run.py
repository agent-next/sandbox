#!/usr/bin/env python3
"""lean-sorry-filler demo: one command, one disposable sandbox, one verdict.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned Lean toolchain (elan 4.2.4 / Lean 4.34.1), runs the judge
self-test (9 broken mutants must die), then grades the known-good
sorry-free artifact — and always kills the sandbox afterwards,
confirming it is gone.

    python3 cookbook/lean-sorry-filler/run.py [--ref main] [--keep]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

Standard library only. Wall time per step is printed.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/lean-sorry-filler"
STEP_TIMEOUTS = {"clone": 300, "setup": 1200, "selftest": 1800,
                 "grade": 900}


def die(msg, code=1):
    print(f"run.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def need_sbx():
    if not shutil.which("sbx"):
        die("sbx CLI not found: pip install "
            "'git+https://github.com/agent-next/sandbox#subdirectory=cli'")
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        die("no API key: export SBX_API_KEY (or E2B_API_KEY)")


def run(step, *args, timeout=None, capture=False):
    t0 = time.monotonic()
    proc = subprocess.run(args, capture_output=capture, text=True,
                          timeout=timeout and timeout + 30)
    dt = time.monotonic() - t0
    status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}"
    print(f"  [{step}] {' '.join(args[:3])} ... {status} ({dt:.0f} s)",
          flush=True)
    return proc, dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repository ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    args = ap.parse_args()

    total0 = time.monotonic()
    need_sbx()
    proc, _ = run("create", "sbx", "create", "--timeout-min", "30",
                  timeout=120, capture=True)
    if proc.returncode != 0:
        die(f"sbx create failed: {proc.stderr.strip()}")
    sbx_id = proc.stdout.strip().splitlines()[-1]
    print(f"sandbox: {sbx_id} (template default)")

    verdict = None
    try:
        def exec_step(name, cmd):
            proc, _ = run(name, "sbx", "exec", sbx_id, "--timeout",
                         str(STEP_TIMEOUTS[name]), "--", *cmd)
            if proc.returncode != 0:
                die(f"step {name} failed in sandbox {sbx_id} "
                    f"(exit {proc.returncode})")
            return proc

        exec_step("clone", ["git", "clone", "--depth", "1", "-b", args.ref,
                            REPO, "sandbox"])
        exec_step("setup", ["bash", f"sandbox/{DEMO_DIR}/judge/setup.sh"])
        exec_step("selftest", ["bash",
                               f"sandbox/{DEMO_DIR}/judge/selftest.sh",
                               "--json", "/tmp/selftest.json"])
        proc, _ = run("cat-selftest", "sbx", "exec", sbx_id, "--timeout",
                      "60", "--", "cat", "/tmp/selftest.json", capture=True)
        if proc.returncode != 0 or not proc.stdout.strip():
            die(f"selftest summary missing in sandbox {sbx_id} "
                f"(cat /tmp/selftest.json exited {proc.returncode})")
        print("selftest summary (JSON):")
        print(proc.stdout, end="")
        exec_step("grade", ["bash", f"sandbox/{DEMO_DIR}/judge/grade.sh",
                            f"sandbox/{DEMO_DIR}/examples/good/exercises",
                            "--json", "/tmp/verdict.json"])
        proc, _ = run("cat", "sbx", "exec", sbx_id, "--timeout", "60", "--",
                      "cat", "/tmp/verdict.json", capture=True)
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                verdict = json.loads(proc.stdout)
            except json.JSONDecodeError:
                pass
    finally:
        if args.keep:
            print(f"run.py: --keep: sandbox {sbx_id} left running; "
                  "kill it with: sbx kill " + sbx_id)
        else:
            # sbx kill returns 0 even when it killed nothing (e.g. a
            # gateway 503 or an already-gone id), so a 0 exit proves
            # nothing: both the kill and the confirming list must be
            # checked, and any failure here is fatal.
            proc, _ = run("kill", "sbx", "kill", sbx_id, timeout=120)
            if proc.returncode != 0:
                die(f"cleanup not confirmed: sbx kill {sbx_id} exited "
                    f"{proc.returncode}: {(proc.stderr or '').strip()} "
                    "(sandbox may still be running; kill it with: "
                    "sbx kill " + sbx_id + ")", 2)
            proc, _ = run("list", "sbx", "list", timeout=60, capture=True)
            if proc.returncode != 0:
                die(f"cleanup not confirmed: sbx list exited "
                    f"{proc.returncode}: {(proc.stderr or '').strip()} "
                    "— cannot verify sandbox " + sbx_id + " is gone", 2)
            if sbx_id in (proc.stdout or ""):
                die(f"cleanup not confirmed: sandbox {sbx_id} still live; "
                    "kill it with: sbx kill " + sbx_id, 2)
            print(f"cleanup: sandbox {sbx_id} killed and confirmed gone")

    print(f"total: {time.monotonic() - total0:.0f} s")
    if not verdict:
        die("no verdict JSON returned from the sandbox")
    ok = verdict.get("pass") is True and verdict.get("judge_intact", False)
    print(f"\nlean-sorry-filler demo: {'PASS' if ok else 'FAIL'}")
    for name in ("structure", "build", "axioms", "closure"):
        g = verdict.get(name, {})
        state = "pass" if g.get("pass") else "FAIL"
        detail = ""
        if name == "structure":
            detail = (f"statements {g.get('statements_matched')}/10, "
                      f"tokens {len(g.get('problems', []))} problems")
        elif name == "build":
            detail = (f"exit {g.get('build_exit')}, "
                      f"sorry warnings {g.get('sorry_warnings')}")
        elif name == "axioms":
            detail = f"{len(g.get('axioms', {}))}/10 audited"
        elif name == "closure":
            detail = (f"{g.get('closed')}/{g.get('planted')} closed "
                      f"({g.get('closed_rate') * 100:.0f}%)")
        print(f"  gate {name}: {state}  {detail}")
    print(f"  judge_intact: {verdict.get('judge_intact')}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
