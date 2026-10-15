#!/usr/bin/env python3
"""The judge's own action runner.

This is the judge's independent way to score a piece of candidate source: it
does not import, call or look at the artifact under test.  `grade.sh` uses it
to compute, for each scripted partial solution, the reward that solution
*should* get, and then requires the artifact's environment to report exactly
that number (gate `partial_exact`).

It is deliberately a separate implementation from the environment in
`examples/good/`: it shells out once per test rather than once per action, and
it writes its own limits.  Agreement between the two is evidence about the
reward, not an echo.

    python3 runner.py --tasks tasks/tasks.json --entry add --source-file f.py

prints one JSON object: {"passed": n, "total": 5, "reward": r}
"""

import argparse
import json
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile

RLIMIT_AS_MB = 256
RLIMIT_CPU_S = 2
RLIMIT_NPROC = 64
RLIMIT_FSIZE_MB = 8
RLIMIT_NOFILE = 256
DEFAULT_TIMEOUT_S = 3.0

# One test per child process: no candidate code is loaded twice, and a test
# that hangs cannot poison the ones after it.
CHILD = r'''
import importlib.util, json, sys

job = json.load(sys.stdin)
spec = importlib.util.spec_from_file_location("cand", job["module"])
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except BaseException:
    print(json.dumps({"ok": False}))
    sys.exit(0)
fn = getattr(mod, job["entry"], None)
if not callable(fn):
    print(json.dumps({"ok": False}))
    sys.exit(0)
try:
    got = fn(*job["args"])
except BaseException:
    print(json.dumps({"ok": False}))
    sys.exit(0)
print(json.dumps({"ok": got == job["expect"] and type(got) is type(job["expect"])}))
'''


def _limits():
    mb = 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (RLIMIT_AS_MB * mb, RLIMIT_AS_MB * mb))
    resource.setrlimit(resource.RLIMIT_CPU, (RLIMIT_CPU_S, RLIMIT_CPU_S))
    resource.setrlimit(resource.RLIMIT_FSIZE, (RLIMIT_FSIZE_MB * mb, RLIMIT_FSIZE_MB * mb))
    resource.setrlimit(resource.RLIMIT_NOFILE, (RLIMIT_NOFILE, RLIMIT_NOFILE))
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (RLIMIT_NPROC, RLIMIT_NPROC))
    except (ValueError, OSError):
        pass
    os.setsid()


def score_one(module, entry, args, expect, timeout_s):
    """Return True iff the candidate passes this single test."""
    job = json.dumps({"module": module, "entry": entry, "args": args,
                      "expect": expect})
    try:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-c", CHILD],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True,
            cwd=os.path.dirname(module), preexec_fn=_limits)
    except OSError:
        return False
    try:
        out, _ = proc.communicate(job, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill(proc)
        return False
    try:
        return bool(json.loads(out.strip().splitlines()[-1])["ok"])
    except (ValueError, IndexError, KeyError):
        return False


def _kill(proc):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def score(task, source, timeout_s=DEFAULT_TIMEOUT_S):
    """Return (passed, total, reward) for `source` against `task`."""
    workdir = tempfile.mkdtemp(prefix="judge-run-")
    try:
        module = os.path.join(workdir, "cand.py")
        with open(module, "w") as fh:
            fh.write(source)
        total = len(task["tests"])
        passed = 0
        for test in task["tests"]:
            if score_one(module, task["entry"], test["args"], test["expect"],
                         timeout_s):
                passed += 1
        return passed, total, passed / total
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--entry", required=True)
    ap.add_argument("--source-file", required=True)
    ap.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    args = ap.parse_args(argv[1:])

    bank = json.load(open(args.tasks))
    task = next((t for t in bank["tasks"] if t["entry"] == args.entry), None)
    if task is None:
        raise SystemExit("no task with entry %r" % args.entry)
    source = open(args.source_file).read()
    passed, total, reward = score(task, source, args.timeout_s)
    print(json.dumps({"passed": passed, "total": total, "reward": reward}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
