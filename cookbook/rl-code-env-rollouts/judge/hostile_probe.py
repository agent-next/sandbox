#!/usr/bin/env python3
"""Run one hostile action against an artifact's environment, in isolation.

The judge spawns this as a separate process with its own process group and a
hard wall-clock limit, so an artifact that hangs or fork-bombs cannot hang or
fork-bomb the judge.  The judge kills this whole process group when the limit
expires; this script's exit status and stdout are the only things that cross
back.

    hostile_probe.py <artifact_env.py> <tasks.json> <seed> <shape> <timeout_s>

`shape` is one of `infinite-loop`, `fork-bomb`, `file-deleter`.  Prints one
JSON object: {"reward": r, "timed_out": bool, "wall_s": float}.  Any failure
to produce that object is the judge's signal that the action was not handled.
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


def main(argv):
    artifact, tasks_path, seed, shape, timeout_s = argv[1:6]
    if shape not in SHAPES:
        raise SystemExit("unknown shape %r" % shape)

    spec = importlib.util.spec_from_file_location("hostile_env", artifact)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    bank = json.load(open(tasks_path))
    entry = {t["id"]: t["entry"] for t in bank["tasks"]}

    env = mod.CodeTaskEnv(tasks_path=tasks_path, seed=int(seed),
                          timeout_s=float(timeout_s))
    obs, _ = env.reset()
    tid = obs["task_id"]
    source = SHAPES[shape] % entry[tid]

    t0 = time.time()
    _o, reward, _term, _trunc, info = env.step(source)
    wall_s = time.time() - t0
    print(json.dumps({"reward": reward,
                      "timed_out": bool(info.get("timed_out")),
                      "wall_s": wall_s}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
