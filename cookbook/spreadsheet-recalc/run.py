#!/usr/bin/env python3
"""spreadsheet-recalc demo — one command, one disposable sandbox, one verdict.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned judge toolchain (openpyxl 3.1.5 + LibreOffice), runs the judge
self-test (known-good passes, known-bad workbooks all fail), then grades the
known-good DCF workbook — and always kills the sandbox afterwards,
confirming it is gone.

Every step is checked: a non-zero exit from any step names the step and the
sandbox id and exits non-zero. A lost reply is never treated as success.

python3 cookbook/spreadsheet-recalc/run.py [--ref main] [--keep]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment. Standard library only.
Wall time per step is printed.
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
    "setup": 900,
    "selftest": 900,
    "grade": 900,
}


def die(msg, code=1):
    print(f"run.py: FATAL: {msg}", file=sys.stderr)
    raise SystemExit(code)


def need_sbx():
    if not os.environ.get("SBX_API_KEY") and not os.environ.get("E2B_API_KEY"):
        die("SBX_API_KEY (or E2B_API_KEY) not in environment")
    try:
        subprocess.run(["sbx", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        die("sbx CLI not found or not working; install with: "
            'pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"')


def run(step, *args, timeout=300, capture=False):
    """Run a command; on failure name the step and exit non-zero (no 'ok' for
    a failed step). Returns (proc, dt)."""
    t0 = time.monotonic()
    shown = " ".join(str(a) for a in args[:4])
    print(f"  [{step}] {shown} ...", end="", flush=True)
    try:
        proc = subprocess.run(
            [str(a) for a in args],
            capture_output=capture,
            text=True,
            timeout=timeout + 30,
        )
    except subprocess.TimeoutExpired:
        dt = time.monotonic() - t0
        print(f" TIMEOUT ({dt:.0f} s)", flush=True)
        die(f"step {step} timed out after {timeout} s: {shown}")
    dt = time.monotonic() - t0
    if proc.returncode == 0:
        print(f" ok ({dt:.0f} s)", flush=True)
    else:
        out = (proc.stdout or "")[-300:]
        err = (proc.stderr or "")[-300:]
        print(f" exit {proc.returncode} ({dt:.0f} s)", flush=True)
        if out.strip():
            print(f"    stdout: {out.strip()}", file=sys.stderr)
        if err.strip():
            print(f"    stderr: {err.strip()}", file=sys.stderr)
    return proc, dt


def exec_step(name, sbx_id, cmd):
    proc, _ = run(
        name, "sbx", "exec", sbx_id, "--timeout",
        str(STEP_TIMEOUTS[name]), "--", *cmd,
        timeout=STEP_TIMEOUTS[name],
    )
    if proc.returncode != 0:
        die(f"step {name} failed in sandbox {sbx_id} "
            f"(exit {proc.returncode}); aborting before grade")
    return proc


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="main",
                    help="git ref to clone (default: main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    args = ap.parse_args()

    need_sbx()
    total0 = time.monotonic()

    print(f"spreadsheet-recalc demo: ref={args.ref}", flush=True)

    proc, _ = run("create", "sbx", "create", "--timeout-min", "30",
                  timeout=120, capture=True)
    if proc.returncode != 0:
        die(f"sbx create failed: {(proc.stderr or '').strip()}")
    sbx_id = proc.stdout.strip().splitlines()[-1]
    print(f"  sandbox: {sbx_id}", flush=True)

    verdict = None
    try:
        exec_step("clone", sbx_id, [
            "git", "clone", "--depth", "1", "-b", args.ref, REPO, "sandbox",
        ])
        exec_step("setup", sbx_id, [
            "bash", f"sandbox/{DEMO_DIR}/judge/setup.sh",
        ])
        exec_step("selftest", sbx_id, [
            "bash", f"sandbox/{DEMO_DIR}/judge/selftest.sh",
        ])
        exec_step("grade", sbx_id, [
            "bash", f"sandbox/{DEMO_DIR}/judge/grade.sh",
            f"sandbox/{DEMO_DIR}/examples/good/dcf_model.xlsx",
            "--json", "/tmp/verdict.json",
        ])

        proc, _ = run("cat", "sbx", "exec", sbx_id, "--timeout", "60", "--",
                      "cat", "/tmp/verdict.json", timeout=60, capture=True)
        if proc.returncode != 0 or not proc.stdout.strip():
            die(f"could not read verdict JSON from sandbox {sbx_id}")
        try:
            verdict = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            die(f"verdict JSON from sandbox {sbx_id} did not parse: {exc}; "
                f"raw: {proc.stdout[:200]}")
    finally:
        if args.keep:
            print(f"run.py: --keep: sandbox {sbx_id} left running; "
                  "kill it with: sbx kill " + sbx_id)
        else:
            run("kill", "sbx", "kill", sbx_id, timeout=120)
            proc, _ = run("list", "sbx", "list", timeout=60, capture=True)
            if sbx_id in (proc.stdout or ""):
                die(f"cleanup not confirmed: sandbox {sbx_id} still live; "
                    "kill it with: sbx kill " + sbx_id, 2)
            print(f"cleanup: sandbox {sbx_id} killed and confirmed gone")

    if not verdict:
        die("no verdict JSON returned from the sandbox")

    gates = verdict.get("gates", {})
    ok = bool(gates) and all(gates.values()) \
        and verdict.get("pass") is True

    print(f"\n{'=' * 60}")
    print(f"spreadsheet-recalc demo: {'PASS' if ok else 'FAIL'}")
    print(f"  artifact: {verdict.get('artifact', '?')}")
    print(f"  seed: {verdict.get('seed', '?')}")
    for gate in sorted(gates):
        val = gates[gate]
        # Gates are plain booleans in the verdict JSON.
        state = "pass" if val is True else "FAIL"
        print(f"  gate {gate}: {state}")
    metrics = verdict.get("metrics", {})
    for pct in (8, 10, 12):
        comp = metrics.get(f"npv_{pct}_computed")
        orac = metrics.get(f"npv_{pct}_oracle")
        err = metrics.get(f"npv_{pct}_err_pct")
        if comp is not None:
            print(f"  NPV @ {pct}%: computed={comp} oracle={orac} "
                  f"err={err}%")
    if "negative_control_move_pct" in metrics:
        print(f"  negative control: NPV moved {metrics['negative_control_move_pct']}%")
    if verdict.get("problems"):
        print("  problems:")
        for p in verdict["problems"]:
            print(f"    - {p}")
    print(f"{'=' * 60}")
    print(f"total: {time.monotonic() - total0:.0f} s")

    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
