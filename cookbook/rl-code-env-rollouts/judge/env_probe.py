#!/usr/bin/env python3
"""Drive one artifact's environment from *outside* the judge process.

The judge never imports the artifact into its own address space: the artifact
is untrusted code -- the README's "Ask your agent" prompt asks an agent to
write it from scratch -- and import-time code in it could rebind the judge's
own modules in memory (`runner.score`, `gymnasium.Env`, the verdict object),
where the `judge_intact` checksums, taken on disk, cannot see it.  This script
is therefore the only place the artifact's `CodeTaskEnv` is imported, and the
judge spawns a fresh copy of it per batch, so the artifact always runs in a
throwaway interpreter.

    env_probe.py <artifact_env.py> <tasks.json> <seed> <timeout_s> <ops.json> <out.jsonl>

The ops are the judge's script for the batch; each op runs to completion and
appends one JSON document to `out.jsonl` (a file the judge made, not stdout,
so nothing the artifact prints can forge or garble a document).  The judge
reads the documents afterwards and validates every field against the bank and
its own runner before recording anything -- nothing the artifact says about
itself is trusted, and nothing it prints is read at all.

One batch op (`isolation`) and the standalone `probe` mode run *hostile*
actions -- source the judge composes to hang, fork-bomb or delete files -- so
the judge can ask whether the environment contains them without ever running
them itself:

    env_probe.py <artifact_env.py> <tasks.json> <seed> <timeout_s> probe <shape> <out.json>

Ops (see `drive.py` for which gate uses which):

* `episode {policy, seed?}` -- one full episode; each step's observation,
  reward, flags and info, with the wall clock the judge checks `info.wall_s`
  against.
* `first_steps {policy, seed, repeats}` -- the same first step, fresh episode
  each time; the reward-determinism probe.
* `reset_orders {seeds[]}` -- the task-id order each seed produces.
* `isolation {policy}` -- a warm episode, one hostile action *on that same
  instance*, then `reset` and another episode; if the artifact cannot contain
  its own hostile action, this op dies with it, which is the failure the gate
  reports.
* `throughput {policy, episodes}` -- timed full episodes.

A step that raises is recorded as that step's `error` and ends its episode;
the batch continues with the next op, so the judge sees every defect rather
than only the first.
"""

import importlib.util
import json
import sys
import time

# Longer than any episode has steps; a loop that never terminates is recorded,
# not hung on.
MAX_STEPS = 1000


class OutOfBand(Exception):
    """Something the worker cannot do; recorded as a failed op."""


class Sink:
    """Appends one JSON document per line to the judge's file."""

    def __init__(self, path):
        self._fh = open(path, "w")

    def emit(self, obj):
        self._fh.write(json.dumps(obj) + "\n")
        self._fh.flush()

    def close(self):
        self._fh.close()


def load_module(artifact_env):
    spec = importlib.util.spec_from_file_location("artifact_env", artifact_env)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)   # import-time code runs here, in this
    if not hasattr(mod, "CodeTaskEnv"):  # throwaway interpreter only
        raise OutOfBand("module defines no CodeTaskEnv")
    return mod


def task_of(bank, obs):
    """The bank task the observation claims to describe, or None."""
    if not isinstance(obs, dict):
        return None
    return next((t for t in bank["tasks"] if t["id"] == obs.get("task_id")),
                None)


def policy_source(policy, obs, bank):
    """The action for the task in `obs`.

    `policy` is a `{task_id: source}` map the judge composed.  The
    environment's own observation picks the entry, so an environment that
    asks about a task the judge did not script is a visible failure, not a
    silent skip.
    """
    task = task_of(bank, obs)
    if task is None:
        raise OutOfBand("observation names no task in the bank: %r"
                        % (obs.get("task_id") if isinstance(obs, dict)
                           else obs,))
    src = policy.get(task["id"])
    if src is None:
        raise OutOfBand("the judge scripted no action for task %r"
                        % task["id"])
    return src


def episode(env, bank, policy, sink, name):
    """Drive one full episode, recording every step's raw result."""
    obs, info = env.reset()
    sink.emit({"op": name, "phase": "reset", "obs": obs, "info": info})
    for _ in range(MAX_STEPS):
        src = policy_source(policy, obs, bank)
        t0 = time.time()
        try:
            o, r, term, trunc, i = env.step(src)
        except BaseException as exc:
            sink.emit({"op": name, "phase": "step", "task_id":
                       obs.get("task_id") if isinstance(obs, dict) else None,
                       "error": "%s: %s" % (type(exc).__name__, exc)})
            return False
        sink.emit({"op": name, "phase": "step",
                   "task_id": obs.get("task_id") if isinstance(obs, dict)
                   else None,
                   "obs": o, "reward": r, "terminated": term,
                   "truncated": trunc, "info": i,
                   "outer_wall_s": time.time() - t0})
        if term:
            return True
        obs = o
    sink.emit({"op": name, "error": "episode did not terminate after %d steps"
               % MAX_STEPS})
    return False


def op_episode(mod, tasks_path, seed, timeout_s, op, sink, bank):
    env = mod.CodeTaskEnv(tasks_path=tasks_path, seed=op.get("seed", seed),
                          timeout_s=timeout_s)
    episode(env, bank, op["policy"], sink, "episode")


def op_first_steps(mod, tasks_path, seed, timeout_s, op, sink, bank):
    """`repeats` fresh episodes, recording only each first step.

    All use the same seed, so the same task is asked each time; the reward
    must come out bit-identical every time.
    """
    for n in range(int(op.get("repeats", 3))):
        env = mod.CodeTaskEnv(tasks_path=tasks_path, seed=op.get("seed", seed),
                              timeout_s=timeout_s)
        obs, info = env.reset()
        src = policy_source(op["policy"], obs, bank)
        t0 = time.time()
        try:
            o, r, term, trunc, i = env.step(src)
            sink.emit({"op": "first_steps", "run": n, "ok": True,
                       "obs": obs, "reward": r, "info": i,
                       "outer_wall_s": time.time() - t0})
        except BaseException as exc:
            sink.emit({"op": "first_steps", "run": n, "ok": False,
                       "error": "%s: %s" % (type(exc).__name__, exc)})


def op_reset_orders(mod, tasks_path, seed, timeout_s, op, sink, bank):
    """The task-id order each seed produces, one episode per seed."""
    generic = "def _(*a, **k):\n    return None\n"
    policy = {t["id"]: generic for t in bank["tasks"]}
    for s in op["seeds"]:
        env = mod.CodeTaskEnv(tasks_path=tasks_path, seed=s,
                              timeout_s=timeout_s)
        obs, _ = env.reset()
        order = []
        try:
            for _ in range(MAX_STEPS):
                order.append(obs.get("task_id") if isinstance(obs, dict)
                             else None)
                o, _r, term, _tr, _i = env.step(policy[obs["task_id"]]
                                                if isinstance(obs, dict)
                                                and obs.get("task_id") in policy
                                                else generic)
                if term:
                    break
                obs = o
            sink.emit({"op": "reset_orders", "seed": s, "ok": True,
                       "order": order})
        except BaseException as exc:
            sink.emit({"op": "reset_orders", "seed": s, "ok": False,
                       "error": "%s: %s" % (type(exc).__name__, exc)})


def op_isolation(mod, tasks_path, seed, timeout_s, op, sink, bank):
    """The reset-isolation sequence on one instance: warm episode, hostile
    action on that same instance, reset, episode again.

    The hostile action is built here from the bank and the shape the judge
    named, and runs through the instance's ordinary `step` -- so an
    environment whose state is corrupted by hostile source, or that cannot
    contain its own hostile action, fails this op rather than the gate's
    comparison quietly passing.
    """
    entry = {t["id"]: t["entry"] for t in bank["tasks"]}
    shape = op.get("shape", "infinite-loop")
    env = mod.CodeTaskEnv(tasks_path=tasks_path, seed=seed,
                          timeout_s=timeout_s)
    episode(env, bank, op["policy"], sink, "isolation_warm")

    obs, _ = env.reset()
    tid = obs.get("task_id") if isinstance(obs, dict) else None
    if tid not in entry:
        sink.emit({"op": "isolation", "phase": "hostile", "ok": False,
                   "error": "reset reported task %r, not in the bank"
                   % (tid,)})
        return
    src = HOSTILE[shape] % entry[tid]
    t0 = time.time()
    try:
        _o, r, _term, _trunc, i = env.step(src)
        sink.emit({"op": "isolation", "phase": "hostile", "ok": True,
                   "task_id": tid, "reward": r, "info": i,
                   "outer_wall_s": time.time() - t0})
    except BaseException as exc:
        sink.emit({"op": "isolation", "phase": "hostile", "ok": False,
                   "error": "%s: %s" % (type(exc).__name__, exc)})
        return
    episode(env, bank, op["policy"], sink, "isolation_after")


def op_throughput(mod, tasks_path, seed, timeout_s, op, sink, bank):
    """Timed full episodes; the judge records the rate under `timing`."""
    env = mod.CodeTaskEnv(tasks_path=tasks_path, seed=seed,
                          timeout_s=timeout_s)
    policy = op["policy"]
    steps = 0
    t0 = time.time()
    for _ in range(int(op.get("episodes", 1))):
        obs, _ = env.reset()
        for _ in range(MAX_STEPS):
            o, _r, term, _tr, _i = env.step(policy_source(policy, obs, bank))
            steps += 1
            if term:
                break
            obs = o
        else:
            sink.emit({"op": "throughput", "ok": False,
                       "error": "episode did not terminate after %d steps"
                       % MAX_STEPS})
            return
    sink.emit({"op": "throughput", "ok": True, "steps": steps,
               "wall_s": time.time() - t0})


# The one copy of the hostile action shapes the judge owns.  (`hostile_probe.py`
# imports this dict, so the judge's two probe scripts cannot drift apart.)
HOSTILE = {
    "infinite-loop": "def %s(*a, **k):\n    while True:\n        pass\n",
    "fork-bomb": ("import os\n"
                  "def %s(*a, **k):\n"
                  "    while True:\n"
                  "        try:\n            os.fork()\n"
                  "        except OSError:\n"
                  "            pass\n"),
    "file-deleter": ("import shutil, os\n"
                     "def %s(*a, **k):\n"
                     "    shutil.rmtree(os.getcwd(), ignore_errors=True)\n"
                     "    return None\n"),
}

OPS = {"episode": op_episode, "first_steps": op_first_steps,
       "reset_orders": op_reset_orders, "isolation": op_isolation,
       "throughput": op_throughput}


def main(argv):
    artifact, tasks_path, seed, timeout_s = argv[1:5]
    if argv[5] == "probe":
        # One hostile action in a fresh environment.  The judge runs this in
        # its own process group with a hard limit and sweeps the group
        # afterwards, so a hang or a fork bomb here costs the judge nothing.
        shape, out_path = argv[6:8]
        if shape not in HOSTILE:
            raise SystemExit("unknown shape %r" % shape)
        sink = Sink(out_path)
        try:
            with open(tasks_path) as fh:
                bank = json.load(fh)
            t0 = time.time()
            try:
                mod = load_module(artifact)
                env = mod.CodeTaskEnv(tasks_path=tasks_path, seed=int(seed),
                                      timeout_s=float(timeout_s))
                obs, _ = env.reset()
                task = task_of(bank, obs)
                if task is None:
                    raise OutOfBand("reset reported task %r, not in the bank"
                                    % (obs.get("task_id")
                                       if isinstance(obs, dict) else obs,))
                _o, reward, _t, _tr, info = env.step(
                    HOSTILE[shape] % task["entry"])
                sink.emit({"op": "probe", "shape": shape, "ok": True,
                           "reward": reward, "timed_out":
                           bool(info.get("timed_out")) if isinstance(info,
                                                                    dict)
                           else None,
                           "wall_s": time.time() - t0})
            except BaseException as exc:
                sink.emit({"op": "probe", "shape": shape, "ok": False,
                           "error": "%s: %s" % (type(exc).__name__, exc)})
            return 0
        finally:
            sink.close()

    ops_path, out_path = argv[6:8]
    sink = Sink(out_path)
    try:
        with open(tasks_path) as fh:
            bank = json.load(fh)
        ops = json.loads(open(ops_path).read())
        try:
            mod = load_module(artifact)
        except OutOfBand as exc:
            sink.emit({"op": "load", "ok": False, "error": str(exc)})
            return 0
        except BaseException as exc:
            sink.emit({"op": "load", "ok": False,
                       "error": "import failed: %s: %s"
                       % (type(exc).__name__, exc)})
            return 0
        sink.emit({"op": "load", "ok": True})
        for op in ops:
            handler = OPS.get(op.get("op"))
            if handler is None:
                sink.emit({"op": op.get("op", "?"), "ok": False,
                           "error": "unknown op %r" % op.get("op")})
                continue
            try:
                handler(mod, tasks_path, seed, float(timeout_s), op, sink,
                        bank)
            except BaseException as exc:
                sink.emit({"op": op.get("op"), "ok": False,
                           "error": "%s: %s" % (type(exc).__name__, exc)})
        return 0
    finally:
        sink.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
