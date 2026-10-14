#!/usr/bin/env python3
"""One-command run for the aicad-text-to-cad demo.

Creates a disposable agent-next sandbox, clones this repo inside it,
installs the pinned cadgen/text-to-cad toolchain plus the judge oracle
libraries, proves the judge can fail (self-test, 8 single-edit mutants),
then grades one delivered part. The sandbox is always killed afterwards
(unless --keep is given) and its removal confirmed via `sbx list`.

Requires the `sbx` CLI on PATH:
  pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
and SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage: python3 run.py [--ref REF] [--keep] [--part PART]
"""

import argparse
import json
import os
import subprocess
import sys
import time

REPO_URL = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/aicad-text-to-cad"

# The exact in-sandbox command sequence (also run verbatim by hand in a
# local verification: bash -c each entry with repo/<demo>/ as cwd).
def sandbox_steps(ref, part):
    return [
        ("clone",
         f"git clone --depth 1 -b {ref} {REPO_URL} repo"),
        ("setup",
         f"cd repo/{DEMO_DIR} && bash judge/setup.sh"),
        ("selftest",
         f"cd repo/{DEMO_DIR} && bash judge/selftest.sh"),
        ("grade",
         f"cd repo/{DEMO_DIR} && bash judge/grade.sh examples/good/{part} "
         f"--json /tmp/v.json >/tmp/grade.log 2>&1; rc=$?; "
         f"cat /tmp/v.json; exit $rc"),
    ]


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
    print(f"[run] {name:<34} {dt:6.1f}s  exit={rc}", flush=True)
    return rc, out, dt


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="main",
                    help="git ref of this repo to clone in the sandbox "
                         "(default: main)")
    ap.add_argument("--part", default="bushing",
                    choices=["bushing", "adapter_plate", "bracket"],
                    help="which delivered part to grade (default: bushing)")
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

    # the clone step runs without a cwd prefix; later steps cd into the demo
    step_timeouts = {"clone": 330, "setup": 960, "selftest": 1500, "grade": 600}
    timings, verdict, failed = {}, None, None
    try:
        for name, command in sandbox_steps(args.ref, args.part):
            rc, out, timings[name] = step(
                name, sbx, "exec", sid, "--timeout", str(step_timeouts[name]),
                "--", "bash", "-c", command,
                timeout=step_timeouts[name] + 30,
                capture=(name in ("selftest", "grade")))
            if name in ("selftest", "grade"):
                tail = "\n".join(out.splitlines()[-10:])
                print(tail, flush=True)
            if name == "grade":
                try:
                    verdict = json.loads(out[out.index("{"):out.rindex("}") + 1])
                except (ValueError, json.JSONDecodeError):
                    verdict = {"pass": False, "error": "no verdict JSON produced"}
            if rc != 0:
                failed = name
                break

        print("\n[run] ======== verdict ========", flush=True)
        if verdict is not None:
            gates = verdict.get("gates", {})
            print(f"[run] part {verdict.get('part')}: "
                  f"{'PASS' if verdict.get('pass') else 'FAIL'} "
                  f"({sum(1 for g in gates.values() if g.get('pass'))}/"
                  f"{len(gates)} gates)", flush=True)
            print(json.dumps(verdict, indent=2), flush=True)
        else:
            print(json.dumps({"failed_at": failed}, indent=2), flush=True)
    finally:
        if args.keep:
            print(f"[run] --keep: sandbox {sid} left running", flush=True)
        else:
            rc, out, _ = step("sbx kill", sbx, "kill", sid, capture=True)
            if rc != 0:
                # a lost reply is not a confirmed kill (LESSONS.md): re-check
                print(f"[run] kill replied exit={rc}: {out.strip()}", flush=True)
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
    if verdict is not None and not verdict.get("pass"):
        sys.exit(f"run.py: judge did not pass {args.part} (sandbox {sid})")


if __name__ == "__main__":
    main()
