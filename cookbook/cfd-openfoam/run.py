#!/usr/bin/env python3
"""One-command run for the cfd-openfoam demo.

Creates a disposable agent-next sandbox, clones this repo inside it,
installs the pinned OpenFOAM toolchain, proves the judge can fail
(self-test) and grades the known-good cases. The sandbox is always
killed afterwards (unless --keep is given).

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
DEMO_DIR = "cookbook/cfd-openfoam"


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
    print(f"[run] {name:<28} {dt:6.1f}s  exit={rc}", flush=True)
    return rc, out, dt


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
    verdict = None
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
                sbx, "exec", sid, "--timeout", "1800", "--",
                "bash", "-c", f"cd repo/{DEMO_DIR} && bash judge/selftest.sh",
                timeout=1830, capture=True)
            tail = "\n".join(out.splitlines()[-8:])
            print(tail, flush=True)
            if rc != 0:
                failed = "selftest.sh"

        if not failed:
            verdict = {}
            for case in ("poiseuille", "cavity"):
                name = f"grade {case}"
                rc, out, timings[name] = step(
                    name,
                    sbx, "exec", sid, "--timeout", "900", "--",
                    "bash", "-c",
                    f"cd repo/{DEMO_DIR} && bash judge/grade.sh "
                    f"examples/good/{case} --json /tmp/verdict_{case}.json "
                    f">/tmp/grade_{case}.log 2>&1; "
                    f"cat /tmp/verdict_{case}.json",
                    timeout=930, capture=True)
                # stdout = grade log tail? we redirected it; parse the JSON
                try:
                    verdict[case] = json.loads(out[out.index("{"):])
                except (ValueError, json.JSONDecodeError):
                    verdict[case] = {"all_gates_passed": False,
                                     "error": "no verdict JSON produced"}
                if rc != 0 or not verdict[case].get("all_gates_passed"):
                    failed = f"grade {case}"

        print("\n[run] ======== verdict ========", flush=True)
        print(json.dumps(verdict, indent=2) if verdict else
              json.dumps({"failed_at": failed}, indent=2), flush=True)
        ok = verdict and all(
            v.get("all_gates_passed") for v in verdict.values())
        print(f"[run] {'PASS' if ok else 'FAIL'}", flush=True)
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
                print(f"[run] WARNING: could not confirm cleanup of {sid}; "
                      f"run `sbx kill {sid}`", file=sys.stderr, flush=True)

    if failed:
        sys.exit(f"run.py: failed at step '{failed}' (sandbox {sid})")


if __name__ == "__main__":
    main()
