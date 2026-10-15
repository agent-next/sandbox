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

# One child per action, scoring every test in that action.  The candidate
# module is loaded once; a test that raises simply does not count, and the
# child is killed as a group if the whole action overruns.
CHILD = r'''
import importlib.util, json, sys

job = json.load(sys.stdin)
spec = importlib.util.spec_from_file_location("cand", job["module"])
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except BaseException as exc:
    print(json.dumps({"load_error": "%s: %s" % (type(exc).__name__, exc)}))
    sys.exit(0)
fn = getattr(mod, job["entry"], None)
if not callable(fn):
    print(json.dumps({"load_error": "no callable %r" % job["entry"]}))
    sys.exit(0)

passed = 0
for test in job["tests"]:
    try:
        got = fn(*test["args"])
    except BaseException:
        continue
    if got == test["expect"] and type(got) is type(test["expect"]):
        passed += 1
print(json.dumps({"passed": passed}))
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


def score_tests(module, entry, tests, timeout_s):
    """Return how many of `tests` the candidate at `module` passes.

    One child process for the whole action; it is killed as a group if it
    overruns `timeout_s`, in which case nothing is credited.
    """
    job = json.dumps({"module": module, "entry": entry, "tests": tests})
    try:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-c", CHILD],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True,
            cwd=os.path.dirname(module), preexec_fn=_limits)
    except OSError:
        return 0
    try:
        out, _ = proc.communicate(job, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill(proc)
        return 0
    try:
        return int(json.loads(out.strip().splitlines()[-1]).get("passed", 0))
    except (ValueError, IndexError, KeyError):
        return 0


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
        passed = score_tests(module, task["entry"], task["tests"], timeout_s)
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
