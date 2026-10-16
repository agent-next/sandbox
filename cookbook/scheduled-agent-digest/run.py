#!/usr/bin/env python3
"""One-command run for the cookbook/scheduled-agent-digest demo.

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
import shlex
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEFAULT_REF = "main"

# sbx create retry (transient platform errors): the window the account's
# concurrent-quota / host-capacity blips have been observed to clear within.
# Every attempt still fails loudly if the last one fails.
CREATE_RETRIES = 9
CREATE_BACKOFF_S = 20.0


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)


def sbx_create(env):
    """sbx create with bounded backoff; returns (sid, last_output).

    A 429 (concurrent quota) or 503 (host capacity) at create time is
    transient: the account's other sandboxes expire and the host recovers.
    Retrying with backoff rides those out; a create that still fails after
    the last attempt raises, keeping the failure identity.
    """
    last = ""
    for attempt in range(1, CREATE_RETRIES + 1):
        r = sh("sbx create --timeout-min 30", env=env)
        if r.returncode == 0:
            lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
            sid = lines[-1] if lines else ""
            if sid and all(c.isascii() and (c.isalnum() or c == "-") for c in sid):
                return sid, r.stdout
            raise RuntimeError(f"sbx create returned an unexpected id {sid!r} "
                               f"(check `sbx list` for a sandbox to kill):\n{r.stdout}")
        last = r.stdout
        transient = ("429" in r.stdout or "RateLimit" in r.stdout
                     or "503" in r.stdout)
        if transient and attempt < CREATE_RETRIES:
            wait = CREATE_BACKOFF_S * attempt
            print(f"scheduled-agent-digest: sbx create failed "
                  f"(attempt {attempt}/{CREATE_RETRIES}); retrying in {wait:.0f}s:\n{r.stdout}",
                  flush=True)
            time.sleep(wait)
    raise RuntimeError(f"sbx create failed after {CREATE_RETRIES} attempts:\n{last}")


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

    # in-sandbox script: clone this repo at ref, set up, self-test, grade.
    # Built *before* `sbx create`: an error while assembling it must never
    # leave a fresh sandbox orphaned.  All output is streamed by sbx exec,
    # which runs the argument through the sandbox shell.  The ref is quoted:
    # it arrives on the command line and must never be parsed as shell.
    script = f"""set -euo pipefail
cd /root 2>/dev/null || cd "$HOME"
git clone --depth 1 -b {shlex_quote(ref)} {REPO} sandbox 2>&1
cd sandbox/cookbook/scheduled-agent-digest
echo '=== judge/setup.sh ==='
bash judge/setup.sh
echo '=== judge/selftest.sh ==='
if bash judge/selftest.sh > /tmp/selftest.log 2>&1; then st=0; else st=$?; fi
cat /tmp/selftest.log
[ "$st" -eq 0 ] || {{ echo "selftest FAILED (exit $st)" >&2; exit 1; }}
echo '=== judge/grade.sh examples/good ==='
bash judge/grade.sh examples/good --json /tmp/digest-verdict.json
echo '=== verdict ==='
cat /tmp/digest-verdict.json || true
echo '=== selftest kill summary ==='
grep -E '^selftest: (mutant KILLED:|kill rate)' /tmp/selftest.log || true
"""

    t0 = time.monotonic()
    print(f"scheduled-agent-digest: creating sandbox (ref={ref})", flush=True)
    sid, create_out = sbx_create(env)
    print(f"scheduled-agent-digest: sandbox {sid}", flush=True)
    wall("create", t0)

    failed = False
    try:
        t1 = time.monotonic()
        print("scheduled-agent-digest: running in-sandbox pipeline (clone + setup + selftest + grade)",
              flush=True)
        r = sh(f"sbx exec {sid} --timeout 900 -- {shlex_quote(script)}", env=env)
        print(r.stdout, flush=True)
        wall("in-sandbox", t1)
        if r.returncode != 0:
            failed = True
            raise RuntimeError(f"in-sandbox run failed with exit {r.returncode}")
    finally:
        if keep:
            print(f"scheduled-agent-digest: --keep; sandbox left up: {sid}", flush=True)
        else:
            # always kill; a failure to confirm cleanup names the id
            rk = sh(f"sbx kill {sid}", env=env)
            rl = sh(f"sbx list", env=env)
            if rk.returncode != 0:
                raise RuntimeError(f"cleanup unconfirmed for {sid}: sbx kill exit {rk.returncode}\n{rk.stdout}")
            # a failed `sbx list` is not proof of absence: the CLI prints
            # its errors to stderr and exits non-zero, so an empty stdout
            # must never be read as "verified absent"
            if rl.returncode != 0:
                raise RuntimeError(f"cleanup unconfirmed for {sid}: sbx list exit {rl.returncode}\n{rl.stdout}")
            if sid not in rl.stdout:
                print(f"scheduled-agent-digest: destroyed {sid}; verified absent", flush=True)
            else:
                raise RuntimeError(f"cleanup unconfirmed for {sid}: still listed in sbx list\n{rl.stdout}")
            wall("total", t0)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        msg = str(exc)
        for name in ("SBX_API_KEY", "E2B_API_KEY"):
            if os.environ.get(name):
                msg = msg.replace(os.environ[name], "[redacted]")
        print(f"scheduled-agent-digest: {msg}", file=sys.stderr)
        sys.exit(1)
