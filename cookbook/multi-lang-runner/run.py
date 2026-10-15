#!/usr/bin/env python3
"""One-command run for the multi-lang-runner demo.

Creates a disposable agent-next sandbox, clones this repo inside it, verifies
the pinned toolchain, proves the judge on the known-good and known-bad
artifacts, grades the reference solutions, prints the verdict JSON, then
kills the sandbox and confirms it is gone.

Needs: the `sbx` CLI
(`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage:
    python3 run.py [--ref BRANCH] [--keep] [--timeout-min N]
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "sandbox/cookbook/multi-lang-runner"   # inside the clone
GOOD = "examples/good"

# Per-step sbx exec timeouts (seconds).  Selftest grades the reference plus
# every mutant (18 x 3 compiles + 18 x 3 runs each).
T_CREATE = 120
T_CLONE = 300
T_SETUP = 600
T_SELFTEST = 2400
T_GRADE = 900


def say(msg):
    print(msg, flush=True)


def run(cmd, timeout, capture=False):
    """Run one local command; return (rc, stdout) or die on timeout."""
    try:
        out = subprocess.run(
            cmd, timeout=timeout, capture_output=capture, text=True,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("%s timed out after %ds" % (cmd[0], timeout))
    return out.returncode, (out.stdout or "")


def sbx_exec(sid, line, timeout):
    """Run a shell line inside the sandbox; returns the command's exit code."""
    rc, _ = run(["sbx", "exec", sid, "--timeout", str(timeout), "--", line],
                timeout + 60)
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="main",
                    help="git ref to clone inside the sandbox (default: main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    ap.add_argument("--timeout-min", type=float, default=30,
                    help="sandbox idle lifetime in minutes (default 30)")
    args = ap.parse_args()

    if shutil.which("sbx") is None:
        raise RuntimeError(
            "sbx CLI not found; install with\n"
            '  pip install "git+https://github.com/agent-next/sandbox'
            '#subdirectory=cli"')
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        raise RuntimeError("export SBX_API_KEY (or E2B_API_KEY) first")

    say("[run] create sandbox (timeout-min %g)" % args.timeout_min)
    t0 = time.time()
    rc, out = run(["sbx", "create", "--timeout-min", str(args.timeout_min)],
                  T_CREATE, capture=True)
    if rc != 0:
        raise RuntimeError("sbx create failed (exit %d)" % rc)
    sid = out.strip().splitlines()[-1].strip()
    if not sid:
        raise RuntimeError("sbx create printed no sandbox id")
    say("[run] sandbox id: %s  (%.0fs)" % (sid, time.time() - t0))

    killed = False
    try:
        steps = [
            ("clone", T_CLONE,
             "git clone --depth 1 -b %s %s %s"
             % (shlex.quote(args.ref), REPO, shlex.quote("sandbox"))),
            ("setup", T_SETUP,
             "cd %s && bash judge/setup.sh" % DEMO_DIR),
            ("selftest", T_SELFTEST,
             "cd %s && bash judge/selftest.sh" % DEMO_DIR),
            ("grade", T_GRADE,
             "cd %s && bash judge/grade.sh %s --json /tmp/verdict.json"
             % (DEMO_DIR, GOOD)),
        ]
        for name, timeout, line in steps:
            say("[run] %s ..." % name)
            t = time.time()
            rc = sbx_exec(sid, line, timeout)
            dt = time.time() - t
            say("[run] %s done  exit=%d  %.0fs" % (name, rc, dt))
            if rc != 0:
                raise RuntimeError(
                    "step %r failed with exit %d in sandbox %s"
                    % (name, rc, sid))
        rc, verdict_text = run(
            ["sbx", "exec", sid, "--timeout", "60", "--",
             "cat /tmp/verdict.json"], 120, capture=True)
        if rc != 0:
            raise RuntimeError("could not read verdict JSON in %s" % sid)
        # print the verdict JSON and a short human summary
        print(verdict_text.strip())
        try:
            v = json.loads(verdict_text)
            gates = v.get("gates", {})
            npass = sum(1 for ok in gates.values() if ok)
            say("[run] verdict: %s  %d/%d gates  seed=%s"
                % ("PASS" if v.get("pass") else "FAIL",
                   npass, len(gates), v.get("seed", -1)))
            ok = bool(v.get("pass"))
        except (ValueError, AttributeError):
            say("[run] could not parse verdict JSON")
            ok = False
        if not ok:
            raise RuntimeError("grade did not pass in sandbox %s" % sid)
    finally:
        if args.keep:
            say("[run] --keep: sandbox %s left running" % sid)
            killed = True  # caller owns it now; skip the confirmation below
        else:
            try:
                run(["sbx", "kill", sid], T_CREATE)
            except Exception:
                pass
            rc, out = run(["sbx", "list"], T_CREATE, capture=True)
            gone = rc == 0 and all(
                not row.split("\t", 1)[0].strip() == sid
                for row in out.splitlines() if row.strip())
            if not gone:
                raise RuntimeError(
                    "cleanup unconfirmed for sandbox %s; run `sbx kill %s`"
                    % (sid, sid))
            killed = True
            say("[run] killed %s; confirmed absent from sbx list" % sid)
    if not killed:
        raise RuntimeError("cleanup unconfirmed for sandbox %s" % sid)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = str(exc)
        for name in ("SBX_API_KEY", "E2B_API_KEY"):
            if os.environ.get(name):
                message = message.replace(os.environ[name], "[redacted]")
        print("run.py: %s" % message, file=sys.stderr)
        sys.exit(1)
