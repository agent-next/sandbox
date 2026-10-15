#!/usr/bin/env python3
"""One-command run for the cookbook/cad-verify-back demo.

Creates a disposable agent-next sandbox, clones this repo at the chosen ref,
runs judge/setup.sh, judge/selftest.sh, judge/grade.sh on the good example,
prints the verdict, and always kills the sandbox.

Requires: the `sbx` CLI (pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli")
and SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage:
    python3 run.py [--ref main] [--keep]
"""
import json
import os
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEFAULT_REF = "main"


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)


def shlex_quote(s):
    return "'" + s.replace("'", "'\"'\"'") + "'"


def main():
    ref = DEFAULT_REF
    keep = False
    args = sys.argv[1:]
    while args:
        if args[0] == "--ref":
            ref = args[1]
            args = args[2:]
        elif args[0] == "--keep":
            keep = True
            args = args[1:]
        else:
            raise SystemExit(f"unknown arg {args[0]!r}\nusage: run.py [--ref R] [--keep]")

    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        raise RuntimeError("export SBX_API_KEY (or E2B_API_KEY) first; get one at https://sbx.agent-next.com/console")
    if sh("command -v sbx >/dev/null 2>&1").returncode != 0:
        raise RuntimeError("sbx CLI not found; pip install 'git+https://github.com/agent-next/sandbox#subdirectory=cli'")

    # ---- provide the key to sbx subprocesses ----
    env = dict(os.environ)
    env.setdefault("SBX_API_KEY", key)

    def wall(label, since):
        print(f"[{label}] {time.monotonic() - since:.1f}s wall", flush=True)

    t0 = time.monotonic()
    print(f"cad-verify-back: creating sandbox (ref={ref})", flush=True)
    r = sh("sbx create --timeout-min 30", env=env)
    if r.returncode != 0:
        raise RuntimeError(f"sbx create failed:\n{r.stdout}")
    lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    sid = lines[-1] if lines else ""
    if not sid or not all(c.isascii() and (c.isalnum() or c == "-") for c in sid):
        raise RuntimeError(f"sbx create returned an unexpected id {sid!r} "
                           f"(check `sbx list` for a sandbox to kill):\n{r.stdout}")
    print(f"cad-verify-back: sandbox {sid}", flush=True)
    wall("create", t0)

    # in-sandbox script: clone this repo at ref, set up, self-test, grade.
    # All output is streamed by sbx exec.
    qref = shlex_quote(ref)
    qrepo = shlex_quote(REPO)
    script = f"""set -euo pipefail
cd /root 2>/dev/null || cd "$HOME"
# -b accepts only branch/tag names; for a commit SHA, clone without a
# checkout, fetch that commit shallowly and check out FETCH_HEAD
if git clone --depth 1 -b {qref} {qrepo} sandbox 2>&1; then
    :
else
    rm -rf sandbox
    git clone --depth 1 --no-checkout {qrepo} sandbox 2>&1
    git -C sandbox fetch --depth 1 origin {qref} 2>&1
    git -C sandbox checkout -q FETCH_HEAD 2>&1
fi
cd sandbox/cookbook/cad-verify-back
echo '=== judge/setup.sh ==='
bash judge/setup.sh
echo '=== judge/selftest.sh ==='
bash judge/selftest.sh 2>&1 | tee /tmp/selftest.log
echo '=== judge/grade.sh examples/good ==='
python3 examples/good/part.py
bash judge/grade.sh examples/good --json /tmp/cvb-verdict.json
echo '=== verdict ==='
cat /tmp/cvb-verdict.json || true
echo '=== selftest kill summary ==='
grep -E '^selftest: (mutant KILLED:|kill rate|determinism)' /tmp/selftest.log || true
"""
    try:
        t1 = time.monotonic()
        print("cad-verify-back: running in-sandbox pipeline (clone + setup + selftest + grade)",
              flush=True)
        r = sh(f"sbx exec {sid} --timeout 900 -- {shlex_quote(script)}", env=env)
        print(r.stdout, flush=True)
        wall("in-sandbox", t1)
        if r.returncode != 0:
            raise RuntimeError(f"in-sandbox run failed with exit {r.returncode}")
    finally:
        if keep:
            print(f"cad-verify-back: --keep; sandbox left up: {sid}", flush=True)
            return
        # always kill; a failure to confirm cleanup names the id
        rk = sh(f"sbx kill {sid}", env=env)
        rl = sh("sbx list", env=env)
        if rk.returncode != 0:
            raise RuntimeError(f"cleanup unconfirmed for {sid}: sbx kill exit {rk.returncode}\n{rk.stdout}")
        if sid not in rl.stdout:
            print(f"cad-verify-back: destroyed {sid}; verified absent", flush=True)
        else:
            raise RuntimeError(f"cleanup unconfirmed for {sid}: still listed in sbx list\n{rl.stdout}")
        wall("total", t0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        msg = str(exc)
        for name in ("SBX_API_KEY", "E2B_API_KEY"):
            if os.environ.get(name):
                msg = msg.replace(os.environ[name], "[redacted]")
        print(f"cad-verify-back: {msg}", file=sys.stderr)
        sys.exit(1)
