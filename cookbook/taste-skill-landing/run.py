#!/usr/bin/env python3
"""One-command run for the taste-skill-landing demo.

Creates a disposable agent-next sandbox, clones this repo inside it,
installs the pinned judge toolchain (Playwright 1.63.0 + Chromium +
axe-core), proves the judge can fail (self-test), then grades the
known-good site and the no-skill baseline with the same judge so the two
verdicts can be compared. The sandbox is always killed afterwards (unless
--keep is given), and cleanup is confirmed with `sbx list`.

Requires the `sbx` CLI on PATH:
  pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
and SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage: python3 run.py [--ref REF] [--keep]
"""

import argparse
import json
import os
import subprocess
import sys
import time

REPO_URL = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/taste-skill-landing"


def scrub(text):
    for name in ("SBX_API_KEY", "E2B_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def sbx(*args, timeout=120, capture=False):
    """Run one sbx command; return (exit_code, stdout)."""
    cmd = ["sbx", *[str(a) for a in args]]
    if capture:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout + 30)
        return p.returncode, scrub(p.stdout + p.stderr)
    p = subprocess.run(cmd, timeout=timeout)
    return p.returncode, ""


def step(name, fn, *args, timeout=120, capture=False):
    t0 = time.monotonic()
    rc, out = fn(*args, timeout=timeout, capture=capture)
    dt = time.monotonic() - t0
    print(f"[run] {name:<32} {dt:6.1f}s  exit={rc}", flush=True)
    return rc, out, dt


def grade_in_sandbox(sid, name, artifact, ref, timings):
    """Grade one artifact inside the sandbox; return its verdict dict."""
    rc, out, timings[name] = step(
        name,
        sbx, "exec", sid, "--timeout", "600", "--",
        "bash", "-c",
        f"cd repo/{DEMO_DIR} && bash judge/grade.sh {artifact} "
        f"--seed 42 --json /tmp/verdict.json >/tmp/grade.log 2>&1; "
        f"cat /tmp/verdict.json",
        timeout=630, capture=True)
    try:
        verdict = json.loads(out[out.index("{"):])
    except (ValueError, json.JSONDecodeError):
        verdict = {"all_gates_passed": False,
                   "error": "no verdict JSON produced"}
    return rc, verdict


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="main",
                    help="git ref of this repo to clone in the sandbox "
                         "(default: main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    args = ap.parse_args()

    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        sys.exit("run.py: export SBX_API_KEY (or E2B_API_KEY) first")

    rc, out, _ = step("sbx create --timeout-min 30",
                      sbx, "create", "--timeout-min", "30", capture=True)
    if rc != 0 or not out.strip():
        sys.exit(f"run.py: sandbox create failed: {out.strip()}")
    sid = out.strip().splitlines()[-1].strip()
    print(f"[run] sandbox id: {sid}", flush=True)

    timings = {}
    verdicts = {}
    failed = None
    try:
        rc, _, timings["clone"] = step(
            f"git clone --depth 1 -b {args.ref}",
            sbx, "exec", sid, "--timeout", "300", "--",
            "git", "clone", "--depth", "1", "-b", args.ref,
            REPO_URL, "repo", timeout=330)
        if rc != 0:
            failed = "git clone"
        else:
            rc, _, timings["setup"] = step(
                "judge/setup.sh",
                sbx, "exec", sid, "--timeout", "900", "--",
                "bash", "-c", f"cd repo/{DEMO_DIR} && bash judge/setup.sh",
                timeout=930)
            if rc != 0:
                failed = "setup.sh"

        if not failed:
            rc, out, timings["selftest"] = step(
                "judge/selftest.sh",
                sbx, "exec", sid, "--timeout", "1200", "--",
                "bash", "-c", f"cd repo/{DEMO_DIR} && bash judge/selftest.sh",
                timeout=1230, capture=True)
            tail = "\n".join(out.splitlines()[-8:])
            print(tail, flush=True)
            if rc != 0:
                failed = "selftest.sh"

        if not failed:
            rc, verdicts["good"] = grade_in_sandbox(
                sid, "grade good/site", "examples/good/site",
                args.ref, timings)
            if rc != 0 or not verdicts["good"].get("all_gates_passed"):
                failed = "grade good/site"

        if not failed:
            # The baseline is the same brief built WITHOUT the skill rules;
            # it must FAIL at least one gate — that contrast is the demo.
            rc, verdicts["baseline"] = grade_in_sandbox(
                sid, "grade baseline/site", "examples/baseline/site",
                args.ref, timings)
            if rc == 0 or verdicts["baseline"].get("all_gates_passed"):
                failed = "grade baseline/site (expected to fail some gates)"

        print("\n[run] ======== verdicts ========", flush=True)
        if verdicts:
            for name, v in verdicts.items():
                gates = {g["gate"]: g["passed"] for g in v.get("gates", [])}
                print(f"[run] {name}: "
                      f"{'ALL GATES PASS' if v.get('all_gates_passed') else 'FAILS'}")
                for g, ok in gates.items():
                    print(f"[run]   {'pass' if ok else 'FAIL'}  {g}")
        else:
            print(json.dumps({"failed_at": failed}, indent=2), flush=True)
    finally:
        if args.keep:
            print(f"[run] --keep: sandbox {sid} left running", flush=True)
        else:
            rc, out, _ = step("sbx kill", sbx, "kill", sid, capture=True)
            print(out.strip(), flush=True)
            # confirm the id is gone from the inventory
            rc2, listing, _ = step("sbx list", sbx, "list", capture=True)
            gone = rc2 == 0 and sid not in listing
            if gone:
                print(f"[run] confirmed: {sid} is gone", flush=True)
            else:
                print(f"[run] ERROR: could not confirm cleanup of {sid}; "
                      f"run `sbx kill {sid}`", file=sys.stderr, flush=True)
                failed = failed or "cleanup"

    if failed:
        sys.exit(f"run.py: failed at step '{failed}' (sandbox {sid})")


if __name__ == "__main__":
    main()
