#!/usr/bin/env python3
"""Drive one artifact's environment from *outside* the judge process.

The judge never imports the artifact into its own address space: an artifact is
untrusted code, and import-time code in it could patch the judge's own modules
(`runner`, `reference`, `gymnasium`) in memory, where the `judge_intact`
checksums -- taken on disk -- cannot see it.  This script is therefore the only
place the artifact's `CodeTaskEnv` is imported, and `drive.py` spawns it per
batch, so the artifact runs in a throwaway interpreter.

Two kinds of action:

* `probe <shape>` -- the *hostile* single action.  Its own process, its own
  process group, a hard wall-clock limit; the judge kills the whole group if
  the limit expires.  The shapes live here so the judge has one copy of them.
* `drive <ops.json>` -- a *batch* of non-hostile gates: one process, one import
  of the artifact, then a deterministic sequence of `reset` / `step` / `check`
  ops.  Each op prints one JSON line; `drive.py` reads them and reduces them.
  A batch stops at the first op that raises, so a broken artifact cannot take
  the judge down with it.

    env_probe.py <artifact_env.py> <tasks.json> <seed> <timeout_s> probe <shape>
    env_probe.py <artifact_env.py> <tasks.json> <seed> <timeout_s> drive <ops.json>
"""

import importlib.util
import json
import sys
import time

SHAPES = {
    "infinite-loop": "def %s(*a, **k):\n    while True:\n        pass\n",
    "fork-bomb": ("import os\n"
                  "def %s(*a, **k):\n"
                  "    while True:\n"
                  "        try:\n            os.fork()\n"
                  "        except OSError:\n            pass\n"),
    "file-deleter": ("import shutil, os\n"
                     "def %s(*a, **k):\n"
                     "    shutil.rmtree(os.getcwd(), ignore_errors=True)\n"
                     "    return None\n"),
}


class OutOfBand(Exception):
    """An op the worker cannot perform; reported as a failed batch."""


def _emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _fail(op, exc):
    _emit({"op": op, "ok": False,
           "error": "%s: %s" % (type(exc).__name__, exc)})


def load_env(artifact_env, tasks_path, seed, timeout_s):
    """Import the artifact's `code_task_env` and build one environment.

    Runs in this process only, which is a throwaway interpreter the judge
    spawned for the batch; nothing the artifact does at import time reaches the
    judge's own modules.
    """
    spec = importlib.util.spec_from_file_location("artifact_env", artifact_env)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "CodeTaskEnv"):
        raise OutOfBand("module defines no CodeTaskEnv")
    return mod.CodeTaskEnv(tasks_path=tasks_path, seed=seed, timeout_s=timeout_s)


def op_reset(env, op):
    obs, info = env.reset(seed=op.get("seed", None))
    _emit({"op": op["op"], "ok": True, "obs": obs, "info": info})


def op_step(env, op):
    obs, reward, term, trunc, info = env.step(op["source"])
    _emit({"op": op["op"], "ok": True, "obs": obs, "reward": reward,
           "terminated": term, "truncated": trunc, "info": info})


def op_check(env, op):
    """Answer a claim about the environment that is not an observation."""
    import gymnasium
    what = op["check"]
    if what == "instance":
        ok = isinstance(env, gymnasium.Env)
    elif what == "observation_space":
        ok = env.observation_space.contains(op["value"])
    elif what == "action_space_type":
        ok = isinstance(getattr(env, "action_space", None),
                        gymnasium.spaces.Text)
    elif what == "obs_keys":
        ok = set(op["value"]) == set(op["expect"])
    elif what == "metadata":
        ok = getattr(env, "metadata", None) == op["expect"]
    else:
        raise OutOfBand("unknown check %r" % what)
    _emit({"op": op["op"], "ok": True, "check": what, "result": bool(ok)})


OPS = {"reset": op_reset, "step": op_step, "check": op_check}


def run_drive(env, ops):
    for op in ops:
        handler = OPS.get(op["op"])
        if handler is None:
            _fail(op, OutOfBand("unknown op %r" % op["op"]))
            return False
        try:
            handler(env, op)
        except BaseException as exc:
            _fail(op, exc)
            return False
    return True


def main(argv):
    artifact, tasks_path, seed, timeout_s, mode = argv[1:6]
    if mode == "probe":
        shape = argv[6]
        if shape not in SHAPES:
            raise SystemExit("unknown shape %r" % shape)
        bank = json.load(open(tasks_path))
        entry = {t["id"]: t["entry"] for t in bank["tasks"]}
        env = load_env(artifact, tasks_path, int(seed), float(timeout_s))
        obs, _ = env.reset()
        tid = obs["task_id"]
        source = SHAPES[shape] % entry[tid]
        t0 = time.time()
        _o, reward, _term, _trunc, info = env.step(source)
        wall_s = time.time() - t0
        _emit({"reward": reward, "timed_out": bool(info.get("timed_out")),
               "wall_s": wall_s})
        return 0

    if mode == "drive":
        env = load_env(artifact, tasks_path, int(seed), float(timeout_s))
        run_drive(env, json.loads(argv[6]))
        return 0

    raise SystemExit("unknown mode %r" % mode)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
