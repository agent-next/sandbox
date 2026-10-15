#!/usr/bin/env python3
"""app-builder-preview demo: one command, one disposable sandbox, one verdict.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned judge toolchain (Node.js 22.23.3 + Playwright 1.63.0 with
Chromium), runs the judge self-test, then grades the known-good Vite + React
app — and always kills the sandbox afterwards, confirming it is gone.

python3 cookbook/app-builder-preview/run.py [--ref main] [--keep]

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
DEMO_DIR = "cookbook/app-builder-preview"
STEP_TIMEOUTS = {"clone": 300, "setup": 900, "selftest": 900, "grade": 900}
GATES = ("structure", "build", "serve", "flows", "hygiene")

# Everything cookbook/DEMO-STANDARD.md requires of this demo, checked in
# the clone before anything is installed: a file missing on the ref is a
# demo bug, and the run must fail loudly there, not pass quietly.
LAYOUT = [
    "README.md", "SPEC.md", "REPRODUCE.md", "RECEIPT.md", "run.py",
    "judge/setup.sh", "judge/grade.sh", "judge/selftest.sh",
    "judge/mutants.py", "judge/spec.json", "judge/VERSIONS.txt",
    "judge/ref_app/src/App.jsx", "judge/ref_app/package.json",
    "examples/good/app/package.json", "examples/good/app/package-lock.json",
    "examples/good/app/src/App.jsx",
    "media/result.png", "media/loop.png", "media/demo.mp4",
    "media/MANIFEST.json", "media/make_media.sh",
]


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
        proc, _ = run("layout", "sbx", "exec", sbx_id, "--timeout", "60",
                      "--", "python3", "-c",
                      "import os,sys\nbase=sys.argv[1]\nmissing=[p for p in "
                      "sys.argv[2:] if not os.path.isfile(os.path.join(base,p))]\n"
                      "print(' '.join(missing))\nsys.exit(1 if missing else 0)",
                      f"sandbox/{DEMO_DIR}", *LAYOUT, capture=True)
        if proc.returncode != 0:
            die(f"demo layout incomplete on ref {args.ref!r}, missing: "
                f"{proc.stdout.strip()}")
        exec_step("setup", ["bash", f"sandbox/{DEMO_DIR}/judge/setup.sh"])
        exec_step("selftest", ["bash", f"sandbox/{DEMO_DIR}/judge/selftest.sh"])
        exec_step("grade", ["bash", f"sandbox/{DEMO_DIR}/judge/grade.sh",
                            f"sandbox/{DEMO_DIR}/examples/good/app",
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
            # A list that failed is not a list that came back empty: the
            # sandbox is only gone if a successful list omits it.
            if proc.returncode != 0:
                die(f"cleanup not confirmed: sbx list exited "
                    f"{proc.returncode}; sandbox {sbx_id} may still be live; "
                    "check with: sbx list", 2)
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

    gates = verdict.get("gates", {})
    missing = [g for g in GATES if g not in gates]
    ok = (not missing
          and all(gates.get(g, {}).get("pass") for g in GATES)
          and verdict.get("judge_intact", False))
    print(f"\napp-builder-preview demo: {'PASS' if ok else 'FAIL'}")
    for name, g in sorted(verdict.get("gates", {}).items()):
        print(f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
