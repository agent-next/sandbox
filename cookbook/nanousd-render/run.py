#!/usr/bin/env python3
"""One-command run for cookbook/nanousd-render.

Creates a disposable agent-next sandbox, clones this repo into it at
`--ref` (default `main`), and runs the whole demo:

    judge/setup.sh     install the pinned toolchain (nanousd + renderer)
    judge/selftest.sh  prove the judge can fail (kill rate)
    judge/grade.sh     grade the known-good example, print the verdict

It then always kills the sandbox and confirms with `sbx list` that the id
is gone. Python 3.10+, standard library only.

    SBX_API_KEY=... python3 run.py [--ref REF] [--keep] [--timeout-min 30]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

REPO_URL = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/nanousd-render"


def log(msg: str) -> None:
    print(f"[run] {msg}", flush=True)


def die(msg: str) -> int:
    print(f"[run] ERROR: {msg}", file=sys.stderr, flush=True)
    return 1


def require_sbx() -> str:
    exe = shutil.which("sbx")
    if not exe:
        raise RuntimeError(
            "the `sbx` CLI is not on PATH; install it with "
            "pip install \"git+https://github.com/agent-next/sandbox#subdirectory=cli\"")
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        raise RuntimeError("SBX_API_KEY (or E2B_API_KEY) is not set in the environment")
    return exe


class Step:
    """One timed step: prints its wall time on exit."""

    def __init__(self, name: str):
        self.name = name
        self.t0 = time.time()

    def __enter__(self):
        log(f"--- {self.name} ...")
        return self

    def __exit__(self, *exc):
        dt = time.time() - self.t0
        log(f"--- {self.name}: {dt:.1f}s")
        return False


def sh(argv: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, **kw)


def sandbox_id(out: str) -> str | None:
    """Pull the sandbox id out of `sbx create` output. The CLI prints the
    id on its own (a single bare line); take the first one-token line."""
    for line in out.splitlines():
        line = line.strip()
        if line and " " not in line:
            return line
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="main",
                    help="git ref to clone (default: main)")
    ap.add_argument("--timeout-min", type=int, default=30)
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    args = ap.parse_args()

    timings: dict[str, float] = {}
    try:
        sbx = require_sbx()
    except RuntimeError as e:
        return die(str(e))

    # ---------------------------------------------------- create sandbox
    with Step("sbx create") as s:
        p = sh([sbx, "create", "--timeout-min", str(args.timeout_min)])
        if p.returncode != 0:
            return die(f"sbx create failed: {p.stderr.strip()[:300]}")
        sb_id = sandbox_id(p.stdout)
        if not sb_id:
            return die(f"could not read a sandbox id from: {p.stdout.strip()[:200]}")
    timings["create_s"] = round(time.time() - s.t0, 1)
    log(f"sandbox id: {sb_id}")

    def exec_in(cmd: str, step: str) -> tuple[bool, str]:
        """Run one shell command inside the sandbox; return (ok, output)."""
        p = sh([sbx, "exec", sb_id, "bash", "-lc", cmd])
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")

    ok_all = True
    verdict_text = ""
    try:
        # ------------------------------------------------ clone the repo
        with Step(f"clone --depth 1 --branch {args.ref}") as s:
            ok, out = exec_in(
                f"set -eo pipefail; rm -rf sandbox && "
                f"git clone --depth 1 -b {args.ref} {REPO_URL} sandbox "
                f"2>&1 | tail -2", "clone")
            if not ok:
                return die(f"clone failed:\n{out[-800:]}")
            log(f"cloned {args.ref} into ~/sandbox")
        timings["clone_s"] = round(time.time() - s.t0, 1)

        # ------------------------------------------------------- setup
        with Step("judge/setup.sh (pinned toolchain build)") as s:
            ok, out = exec_in(
                f"set -o pipefail; cd ~/sandbox/{DEMO} && "
                f"bash judge/setup.sh 2>&1 | tail -25",
                "setup")
            log(out.strip()[-1500:])
            if not ok:
                return die("judge/setup.sh failed inside the sandbox (output above)")
        timings["setup_s"] = round(time.time() - s.t0, 1)

        # ----------------------------------------------------- selftest
        with Step("judge/selftest.sh") as s:
            ok, out = exec_in(
                f"set -o pipefail; cd ~/sandbox/{DEMO} && "
                f"bash judge/selftest.sh --json /tmp/selftest.json "
                f"2>&1 | tail -25", "selftest")
            log(out.strip()[-2500:])
            if not ok:
                ok_all = False
                log("selftest FAILED (kill rate or determinism)")
        timings["selftest_s"] = round(time.time() - s.t0, 1)

        # -------------------------------------------------------- grade
        with Step("judge/grade.sh examples/good/scene.usda") as s:
            ok, out = exec_in(
                f"set -o pipefail; cd ~/sandbox/{DEMO} && "
                f"bash judge/grade.sh examples/good/scene.usda "
                f"--seed 0 --json /tmp/verdict.json 2>&1 | tail -40", "grade")
            verdict_text = out
            log(out.strip()[-3000:])
            if not ok:
                ok_all = False
                log("grade FAILED on the known-good example")
        timings["grade_s"] = round(time.time() - s.t0, 1)

        # -------------------------------------------------- JSON summary
        ok, out = exec_in(
            "cat /tmp/verdict.json 2>/dev/null | head -60; "
            "echo '--- selftest.json'; cat /tmp/selftest.json 2>/dev/null | head -40",
            "summary")
        if out.strip():
            log("--- verdict / selftest JSON as written in the sandbox:")
            log(out.strip()[-3000:])

        print()
        print("=" * 68)
        print("SUMMARY")
        print("=" * 68)
        print(f"sandbox      : {sb_id}")
        print(f"ref          : {args.ref}")
        print(f"result       : {'PASS' if ok_all else 'FAIL'}")
        for k, v in timings.items():
            print(f"  {k:<11}: {v}s")
        if ok_all:
            print("\nAll gates passed: see the verdict JSON above.")
        else:
            print("\nSomething failed; the outputs above name the gate.")
        return 0 if ok_all else 1

    finally:
        if args.keep:
            log(f"--keep given: sandbox {sb_id} left running")
            print(f"[run] kept sandbox id: {sb_id}")
            sys.exit(0 if ok_all else 1)
        # ------------------------------------------------ always kill
        with Step("sbx kill"):
            p = sh([sbx, "kill", sb_id])
            if p.returncode != 0:
                log(f"sbx kill reported a failure for {sb_id}: "
                    f"{p.stderr.strip()[:200]}")
        # and confirm it is really gone (a lost kill reply is not a kill)
        p = sh([sbx, "list"])
        if re.search(rf"\b{re.escape(sb_id)}\b", p.stdout or ""):
            print(f"[run] ERROR: cleanup of sandbox {sb_id} could not be "
                  f"confirmed: it still appears in `sbx list`", file=sys.stderr)
            sys.exit(1)
        log(f"confirmed {sb_id} is gone")


if __name__ == "__main__":
    sys.exit(main())
