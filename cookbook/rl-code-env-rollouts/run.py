#!/usr/bin/env python3
"""One-command run for the cookbook/rl-code-env-rollouts demo.

Creates a disposable agent-next sandbox, clones this repo at the chosen ref,
runs judge/setup.sh, judge/selftest.sh, judge/grade.sh on the known-good
artifact, prints the verdict JSON, then always kills the sandbox and
confirms it is gone.

Requires: the `sbx` CLI
(pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli")
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

# The in-sandbox pipeline is sequential (selftest alone is eleven grade runs,
# ~15 min on 2 vCPU; the judge's hostile gate must never run twice at once,
# or one grader's children look like another's leak), so the exec timeout and
# the sandbox lifetime both carry generous margins over the measured ~20 min.
EXEC_TIMEOUT_S = 1800


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)


def shlex_quote(s):
    return "'" + s.replace("'", "'\"'\"'") + "'"


def parse_args(argv):
    ref = DEFAULT_REF
    keep = False
    args = list(argv)
    while args:
        if args[0] == "--ref" and len(args) > 1:
            ref = args[1]
            args = args[2:]
        elif args[0] == "--keep":
            keep = True
            args = args[1:]
        else:
            raise SystemExit(
                "unknown argument %r (run.py takes --ref <git-ref> and --keep)"
                % args[0])
    return ref, keep


def require_tools():
    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        raise RuntimeError("SBX_API_KEY (or E2B_API_KEY) is not set; export "
                           "one first (get a key at "
                           "https://sbx.agent-next.com/console)")
    if sh("command -v sbx >/dev/null 2>&1").returncode != 0:
        raise RuntimeError("sbx CLI not found on PATH; pip install "
                           "'git+https://github.com/agent-next/sandbox"
                           "#subdirectory=cli'")
    return key


def create_sandbox(env):
    r = sh("sbx create --timeout-min 30", env=env)
    if r.returncode != 0:
        raise RuntimeError("sbx create failed (exit %d):\n%s"
                           % (r.returncode, r.stdout))
    lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    sid = lines[-1] if lines else ""
    if not sid or not all(c.isascii() and (c.isalnum() or c == "-") for c in sid):
        raise RuntimeError(
            "sbx create returned an unexpected id %r; check `sbx list` for a "
            "sandbox this run created and kill it:\n%s" % (sid, r.stdout))
    return sid


def run_pipeline(sid, ref, env):
    """Clone, set up, self-test and grade -- exactly the steps a user could
    run by hand, streamed by sbx exec.  Returns the exec result."""
    script = f"""set -euo pipefail
cd /root 2>/dev/null || cd "$HOME"
git clone --depth 1 -b {ref} {REPO} sandbox
cd sandbox/cookbook/rl-code-env-rollouts
echo '=== judge/setup.sh ==='
bash judge/setup.sh
echo '=== judge/selftest.sh ==='
bash judge/selftest.sh 2>&1 | tee /tmp/selftest.log
echo '=== judge/grade.sh examples/good ==='
bash judge/grade.sh examples/good --seed 20261015 --json /tmp/v.json
echo '=== verdict ==='
cat /tmp/v.json
echo '=== selftest kill summary ==='
grep -E '^(mutants killed|kill rate)' /tmp/selftest.log || true
"""
    return sh(f"sbx exec {sid} --timeout {EXEC_TIMEOUT_S} -- {shlex_quote(script)}",
              env=env)


def verdict_summary(stdout):
    """Pull the verdict JSON out of the streamed exec output, if it arrived.

    The verdict is the last complete JSON object in the stream that has the
    keys a verdict has -- the gate table and the sandbox's own chatter can
    carry braces, so shape is the test, not position.
    """
    decoder = json.JSONDecoder()
    best = None
    for i, ch in enumerate(stdout):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(stdout, i)
        except ValueError:
            continue
        if isinstance(obj, dict) and "gates" in obj and "pass" in obj:
            best = obj
    return best


def confirm_gone(sid, env):
    """A kill reply is not a confirmation: the sandbox must be absent from
    `sbx list` before the run reports success."""
    rk = sh(f"sbx kill {sid}", env=env)
    rl = sh("sbx list", env=env)
    if rk.returncode != 0:
        raise RuntimeError("could not kill sandbox %s (sbx kill exit %d); "
                           "kill it by id: sbx kill %s\n%s"
                           % (sid, rk.returncode, sid, rk.stdout))
    if sid in rl.stdout:
        raise RuntimeError("sandbox %s still listed after sbx kill; kill it "
                           "by id and check again: sbx kill %s && sbx list"
                           % (sid, sid))
    return True


def redact(text):
    """Never let a key that leaked into an error message reach the user."""
    for name in ("SBX_API_KEY", "E2B_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def main():
    ref, keep = parse_args(sys.argv[1:])
    require_tools()
    env = dict(os.environ)
    env.setdefault("SBX_API_KEY", os.environ["SBX_API_KEY"]
                   if os.environ.get("SBX_API_KEY")
                   else os.environ["E2B_API_KEY"])

    t0 = time.monotonic()
    print(f"rl-code-env-rollouts: creating sandbox (ref={ref})", flush=True)
    sid = create_sandbox(env)
    print(f"rl-code-env-rollouts: sandbox {sid}", flush=True)
    print(f"[create] {time.monotonic() - t0:.1f}s wall", flush=True)

    failure = None
    try:
        t1 = time.monotonic()
        print("rl-code-env-rollouts: clone + setup + selftest + grade", flush=True)
        r = run_pipeline(sid, ref, env)
        print(r.stdout, flush=True)
        print(f"[in-sandbox] {time.monotonic() - t1:.1f}s wall", flush=True)
        if r.returncode != 0:
            failure = RuntimeError(
                "in-sandbox pipeline failed with exit %d (sandbox %s); the "
                "sbx exec timeout is %d s -- a step killed mid-run may have "
                "left output above" % (r.returncode, sid, EXEC_TIMEOUT_S))
            # No `return` here: a return inside the try skips the `raise
            # failure` below the finally, so a failed pipeline would exit 0.
            # Fall through and let the finally kill the sandbox first.
        else:
            v = verdict_summary(r.stdout)
            if v is None:
                failure = RuntimeError("no verdict JSON found in the exec "
                                       "output (sandbox %s)" % sid)
            else:
                gates = "%d/%d" % (v.get("gates_passed", 0),
                                   v.get("gates_total", 0))
                ok = "PASS" if v.get("pass") else "FAIL"
                print(f"rl-code-env-rollouts: verdict {ok} ({gates} gates), "
                      f"seed {v.get('seed')}", flush=True)
                if not v.get("pass"):
                    failed = sorted(k for k, g in v.get("gates", {}).items()
                                    if g.get("verdict") != "pass")
                    failure = RuntimeError("judge verdict FAIL: %s"
                                           % ", ".join(failed))
    finally:
        if keep:
            print(f"rl-code-env-rollouts: --keep; sandbox left up: {sid}",
                  flush=True)
        else:
            try:
                confirm_gone(sid, env)
                print(f"rl-code-env-rollouts: destroyed {sid}; verified absent",
                      flush=True)
            except RuntimeError as exc:
                # The pipeline's own failure, if any, keeps its identity; the
                # cleanup failure is reported alongside it, not instead of it.
                if failure is not None:
                    raise RuntimeError("%s; additionally, cleanup failed: %s"
                                       % (failure, exc)) from exc
                raise
        print(f"[total] {time.monotonic() - t0:.1f}s wall", flush=True)

    if failure is not None:
        raise failure


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("rl-code-env-rollouts: %s" % redact(str(exc)), file=sys.stderr)
        sys.exit(1)
