#!/usr/bin/env python3
"""spreadsheet-recalc demo — one-command run.

Creates a disposable sandbox, clones this repo, runs the judge toolchain
setup and self-test, grades the known-good DCF workbook, prints the
verdict, then always kills the sandbox and confirms it is gone.

Stdlib only. Needs the sbx CLI and SBX_API_KEY (or E2B_API_KEY).
"""

import argparse
import json
import os
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/spreadsheet-recalc"
STEP_TIMEOUTS = {
    "clone": 300,
    "setup": 600,
    "selftest": 600,
    "grade": 600,
}
API = "https://api.sbx.agent-next.com"


def die(msg, code=1):
    print(f"run.py: FATAL: {msg}", file=sys.stderr)
    sys.exit(code)


def need_sbx():
    if not os.environ.get("SBX_API_KEY") and not os.environ.get("E2B_API_KEY"):
        die("SBX_API_KEY (or E2B_API_KEY) not set")
    try:
        subprocess.run(["sbx", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        die("sbx CLI not found or not working; install with: "
            'pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"')


def run(step, *args, timeout=300, capture=False):
    t0 = time.monotonic()
    cmd = " ".join(str(a) for a in args[:4])
    print(f"  [{step}] {cmd} ...", end="", flush=True)
    try:
        proc = subprocess.run(
            [str(a) for a in args],
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        dt = time.monotonic() - t0
        print(f" ok ({dt:.0f} s)", flush=True)
        return proc
    except subprocess.TimeoutExpired:
        dt = time.monotonic() - t0
        print(f" TIMEOUT ({dt:.0f} s)", flush=True)
        raise


def exec_step(name, sbx_id, cmd, capture=False):
    return run(
        name, "sbx", "exec", sbx_id, "--timeout",
        str(STEP_TIMEOUTS[name]), "--", *cmd,
        timeout=STEP_TIMEOUTS[name], capture=capture,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="main", help=f"git ref to clone (default: main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    args = ap.parse_args()

    need_sbx()
    total0 = time.monotonic()

    print(f"spreadsheet-recalc demo: ref={args.ref}", flush=True)

    # Step 1: create sandbox
    proc = run("create", "sbx", "create", "--timeout-min", "30",
               timeout=120, capture=True)
    sbx_id = proc.stdout.strip().splitlines()[-1]
    print(f"  sandbox: {sbx_id}", flush=True)

    ok = False
    try:
        # Step 2: clone repo
        exec_step("clone", sbx_id, [
            "git", "clone", "--depth", "1", "-b", args.ref, REPO, "sandbox",
        ])

        # Step 3: setup toolchain
        exec_step("setup", sbx_id, [
            "bash", f"sandbox/{DEMO_DIR}/judge/setup.sh",
        ])

        # Step 4: selftest
        exec_step("selftest", sbx_id, [
            "bash", f"sandbox/{DEMO_DIR}/judge/selftest.sh",
        ])

        # Step 5: grade known-good
        exec_step("grade", sbx_id, [
            "bash", f"sandbox/{DEMO_DIR}/judge/grade.sh",
            f"sandbox/{DEMO_DIR}/examples/good/dcf_model.xlsx",
            "--json", "/tmp/verdict.json",
        ])

        # Fetch verdict
        proc = run("cat", "sbx", "exec", sbx_id, "--timeout", "60", "--",
                   "cat", "/tmp/verdict.json", timeout=60, capture=True)
        verdict = json.loads(proc.stdout)

        print(f"\n{'=' * 60}")
        print(f"spreadsheet-recalc demo: "
              f"{'PASS' if all(g.get('pass') for g in verdict.get('gates', {}).values()) else 'FAIL'}")
        print(f"  artifact: {verdict.get('artifact', '?')}")
        for gate, g in verdict.get("gates", {}).items():
            status = "pass" if g.get("pass") else "FAIL"
            print(f"  gate {gate}: {status}")
            for p in g.get("problems", []):
                print(f"    - {p}")
        for scenario, s in verdict.get("scenarios", {}).items():
            print(f"  {scenario}:")
            for k, v in s.items():
                if isinstance(v, dict) and "pass" in v:
                    print(f"    {k}: {'pass' if v['pass'] else 'FAIL'}")
                elif not isinstance(v, dict):
                    print(f"    {k}: {v}")
        print(f"{'=' * 60}")
        print(f"timing: {verdict.get('timing', {})}")

        ok = all(g.get("pass") for g in verdict.get("gates", {}).values())

    finally:
        if args.keep:
            print(f"run.py: --keep: sandbox {sbx_id} left running; "
                  "kill it with: sbx kill " + sbx_id)
        else:
            run("kill", "sbx", "kill", sbx_id, timeout=120)
            proc = run("list", "sbx", "list", timeout=60, capture=True)
            if sbx_id in (proc.stdout or ""):
                die(f"cleanup not confirmed: sandbox {sbx_id} still live; "
                    "kill it with: sbx kill " + sbx_id, 2)
            print(f"cleanup: sandbox {sbx_id} killed and confirmed gone")

    total = time.monotonic() - total0
    print(f"total: {total:.0f} s")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
