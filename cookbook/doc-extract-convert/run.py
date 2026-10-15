#!/usr/bin/env python3
"""One-command run for the doc-extract-convert demo.

Creates a disposable agent-next sandbox, clones this repo inside it,
installs the pinned OCR toolchain, proves the judge can fail (self-test)
and grades the known-good artifact.  The sandbox is always killed
afterwards (unless --keep is given).

Requires the `sbx` CLI on PATH:
  pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
and SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage: python3 run.py [--ref REF] [--keep]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

REPO_URL = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/doc-extract-convert"
SID_RE = re.compile(r"^sbx_[A-Za-z0-9]+$")


def scrub(text):
    """Redact API-key-shaped text before anything is printed.

    The CLI scrubs its own output; this is a second, independent pass so a
    key can never reach the terminal even if that one drifts.
    """
    text = re.sub(r"(?:sbx|e2b)_[A-Za-z0-9_-]{16,}", "[redacted-key]", text)
    for name in ("SBX_API_KEY", "E2B_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def sbx(*args, timeout=120, capture=False):
    """Run one sbx command; return (exit_code, output)."""
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
    # The id is whatever line looks like one; do not assume it is the last
    # line, so extra CLI output cannot make us kill or list the wrong thing.
    ids = [ln.strip() for ln in out.splitlines() if SID_RE.match(ln.strip())]
    if len(ids) != 1:
        sys.exit(f"run.py: cannot tell the sandbox id from `sbx create` "
                 f"output ({len(ids)} candidate lines): {out.strip()}")
    sid = ids[0]
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
                sbx, "exec", sid, "--timeout", "2400", "--",
                "bash", "-c", f"cd repo/{DEMO_DIR} && bash judge/selftest.sh",
                timeout=2430, capture=True)
            tail = "\n".join(out.splitlines()[-10:])
            print(tail, flush=True)
            if rc != 0:
                failed = "selftest.sh"

        if not failed:
            rc, out, timings["grade good"] = step(
                "grade examples/good",
                sbx, "exec", sid, "--timeout", "900", "--",
                "bash", "-c",
                f"cd repo/{DEMO_DIR} && bash judge/grade.sh examples/good "
                f"--json /tmp/v.json >/tmp/grade.log 2>&1; "
                f"rc=$?; tail -5 /tmp/grade.log; cat /tmp/v.json; exit $rc",
                timeout=930, capture=True)
            # Decide on rc first, then parse: a crash before /tmp/v.json was
            # written leaves no verdict to look at, and that is still a
            # failure.  Only a clean rc and a verdict with
            # all_gates_passed=true is a pass.
            verdict = {"all_gates_passed": False,
                       "error": "grading failed and produced no verdict JSON"}
            try:
                verdict = json.loads(out[out.index("{"):out.rindex("}") + 1])
            except (ValueError, IndexError):
                if rc == 0:
                    failed = "grade examples/good"
                    verdict["error"] = "grade.sh exited 0 with no verdict JSON"
            if rc != 0 or not verdict.get("all_gates_passed"):
                failed = failed or "grade examples/good"

        print("\n[run] ======== verdict ========", flush=True)
        print(json.dumps(verdict, indent=2) if verdict else
              json.dumps({"failed_at": failed}, indent=2), flush=True)
        ok = bool(verdict) and verdict.get("all_gates_passed") is True
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
                print(f"[run] ERROR: could not confirm cleanup of {sid}; "
                      f"run `sbx kill {sid}`", file=sys.stderr, flush=True)
                failed = failed or "cleanup"

    if failed or not (verdict and verdict.get("all_gates_passed") is True):
        sys.exit(f"run.py: failed at step '{failed or 'grade examples/good'}' "
                 f"(sandbox {sid})")


if __name__ == "__main__":
    main()
