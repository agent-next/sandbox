#!/usr/bin/env python3
"""One-command run for the mcp-tools-host demo.

Creates a disposable agent-next sandbox, clones this repo inside it,
installs the pinned MCP toolchain, proves the judge can fail
(self-test), then grades the known-good stdio MCP server against the
oracle judge. The sandbox is always killed afterwards (unless --keep).

Requires the `sbx` CLI on PATH:
  pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
and SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage: python3 run.py [--ref REF] [--seed N] [--keep]
"""

import argparse
import json
import os
import subprocess
import sys
import time

REPO_URL = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/mcp-tools-host"
GRADE_TARGET = "examples/good/server.py"
DEFAULT_SEED = 20261015


def scrub(text):
    for name in ("SBX_API_KEY", "E2B_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def sbx(*args, timeout=120, capture=False):
    """Run one sbx command; return (exit_code, combined output)."""
    cmd = ["sbx", *[str(a) for a in args]]
    p = subprocess.run(cmd, capture_output=capture, text=True,
                       timeout=timeout + 30)
    out = scrub((p.stdout or "") + (p.stderr or "")) if capture else ""
    return p.returncode, out


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
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help="seed the judge's fixtures with it (default: "
                         f"{DEFAULT_SEED})")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    args = ap.parse_args()

    if not (os.environ.get("SBX_API_KEY")
            or os.environ.get("E2B_API_KEY")):
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
                "bash", "-c",
                f"cd repo/{DEMO_DIR} && bash judge/setup.sh",
                timeout=930)
            if rc != 0:
                failed = "setup.sh"

        if not failed:
            rc, out, timings["selftest"] = step(
                "judge/selftest.sh",
                sbx, "exec", sid, "--timeout", "1800", "--",
                "bash", "-c",
                f"cd repo/{DEMO_DIR} && bash judge/selftest.sh",
                timeout=1830, capture=True)
            tail = [line for line in out.splitlines()
                    if "Processing request" not in line][-15:]
            print("\n".join(tail), flush=True)
            if rc != 0:
                failed = "selftest.sh"

        if not failed:
            name = "grade good example"
            rc, out, timings[name] = step(
                name,
                sbx, "exec", sid, "--timeout", "900", "--",
                "bash", "-c",
                f"cd repo/{DEMO_DIR} && bash judge/grade.sh "
                f"{GRADE_TARGET} --seed {args.seed} "
                f"--json /tmp/verdict.json >/tmp/grade.log 2>&1; "
                f"rc=$?; grep -v 'Processing request' /tmp/grade.log; "
                f"exit $rc",
                timeout=930, capture=True)
            try:
                decoder = json.JSONDecoder()
                verdict, _ = decoder.raw_decode(out[out.index("{"):])
            except (ValueError, json.JSONDecodeError):
                verdict = None
            if rc != 0 or not verdict or \
                    not verdict.get("all_gates_passed"):
                failed = name

        print("\n[run] ======== verdict ========", flush=True)
        if verdict:
            gates = verdict.get("gates", {})
            for gname in sorted(gates):
                mark = "PASS" if gates[gname].get("passed") else "FAIL"
                print(f"[run]   {mark}  {gname}", flush=True)
            print(f"[run] seed {verdict.get('seed')}  "
                  f"total {verdict.get('timing', {}).get('total_seconds')}s",
                  flush=True)
        else:
            print(json.dumps({"failed_at": failed}, indent=2), flush=True)
        print(f"[run] {'PASS' if not failed else 'FAIL'}", flush=True)
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
