#!/usr/bin/env python3
"""people-counter-cv demo: one command, one disposable sandbox, one verdict.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned judge toolchain (opencv-python-headless 4.13.0.92), runs the
judge self-test, then grades the known-good classical-CV people counter
against the deterministic synthetic walkway clip — and always kills the
sandbox afterwards, confirming it is gone.

    python3 cookbook/people-counter-cv/run.py [--ref main] [--keep]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

Standard library only. Wall time per step is printed. Exits non-zero if
any step fails; never reports success without a confirmed verdict and a
confirmed kill.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/people-counter-cv"
STEP_TIMEOUTS = {"clone": 300, "setup": 900, "selftest": 1800, "grade": 900}


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
    ap.add_argument("--report-json", metavar="PATH",
                    help="write the verdict JSON here")
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
        exec_step("selftest", ["bash", f"sandbox/{DEMO_DIR}/judge/selftest.sh"])
        exec_step("grade", ["bash", f"sandbox/{DEMO_DIR}/judge/grade.sh",
                            f"sandbox/{DEMO_DIR}/examples/good/counter.py",
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
            run("kill", "sbx", "kill", sbx_id, timeout=120)
            proc, _ = run("list", "sbx", "list", timeout=60, capture=True)
            if sbx_id in (proc.stdout or ""):
                die(f"cleanup not confirmed: sandbox {sbx_id} still live; "
                    "kill it with: sbx kill " + sbx_id, 2)
            print(f"cleanup: sandbox {sbx_id} killed and confirmed gone")

    print(f"total: {time.monotonic() - total0:.0f} s")
    if not verdict:
        die("no verdict JSON returned from the sandbox")
    if args.report_json:
        with open(args.report_json, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
        print(f"wrote verdict JSON: {args.report_json}")

    ok = all(g.get("pass") for g in verdict.get("gates", {}).values()) \
        and verdict.get("judge_intact", False)
    print(f"\npeople-counter-cv demo: {'PASS' if ok else 'FAIL'}")
    for name, g in sorted(verdict.get("gates", {}).items()):
        print(f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}")
        for p in g.get("problems") or []:
            print(f"    - {p}")
    m = (verdict.get("gates", {}).get("oracle") or {}).get("metrics") or {}
    if m:
        print(f"  counts: truth {m.get('truth_counts')} vs artifact "
              f"{m.get('artifact_counts')} (error {m.get('count_err')})")
        print(f"  recall {m.get('recall')}, precision {m.get('precision')}, "
              f"time MAE {m.get('time_mae_s')} s, max dev "
              f"{m.get('time_max_dev_s')} s, direction accuracy "
              f"{m.get('direction_accuracy')}")
    a = (verdict.get("gates", {}).get("agreement") or {}).get("metrics") or {}
    if a:
        print(f"  vs judge reference: paired {a.get('paired')}, max time "
              f"dev {a.get('max_time_dev_s')} s, reference counts "
              f"{a.get('reference_counts')}")
    print(f"  judge intact: {verdict.get('judge_intact')}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
