#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test by single edits of the good one.

Each mutant is the good artifact with exactly one scripted edit; the self-test
expects every mutant to fail at least one gate (SPEC.md). Mutants cover the
failure classes from the brief: default nconmax/njmax (the headline bug),
timestep x10 (blow-up), solver_iterations=1 (incomplete convergence),
gravity sign flipped (boxes fly), wrong nworld capacity (OOM), and NaN injection.
"""

import json
import os
import sys


def main():
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "examples", "good")
    with open(os.path.join(src_dir, "sweep.json")) as fh:
        good = json.load(fh)

    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutants")
    os.makedirs(out_dir, exist_ok=True)

    names = []

    # 1. default nconmax/njmax — the headline bug: contacts silently dropped
    m = json.loads(json.dumps(good))
    m["nconmax"] = 1
    m["njmax"] = 1
    for p in m["points"]:
        if p["nworld"] >= 2048:
            p["box_z_min"] = -0.5  # boxes tunnel through the table
    names.append(("default_capacity", m))

    # 2. timestep x10 — physics blow-up
    m = json.loads(json.dumps(good))
    m["timestep"] = m["timestep"] * 10
    for p in m["points"]:
        p["qpos_finite"] = False  # NaN from blow-up
        p["qvel_finite"] = False
    names.append(("timestep_x10", m))

    # 3. solver_iterations = 1 — incomplete convergence
    m = json.loads(json.dumps(good))
    m["solver_iterations"] = 1
    for p in m["points"]:
        p["arm_max_err"] = 0.5  # arm doesn't reach target
    names.append(("solver_iter_1", m))

    # 4. gravity sign flipped — boxes fly up
    m = json.loads(json.dumps(good))
    m["scene"] = m["scene"].replace('gravity="0 0 -9.81"', 'gravity="0 0 9.81"')
    for p in m["points"]:
        p["box_z_max"] = 5.0  # boxes fly off
    names.append(("gravity_flipped", m))

    # 5. wrong nworld capacity — OOM reported as clean fail
    m = json.loads(json.dumps(good))
    m["nworld_ladder"] = [1, 64, 512, 2048, 8192, 32768]
    m["points"] = m["points"] + [
        {"nworld": 32768, "steps_per_s": 0, "ok": False,
         "error": "OOM: put_data nworld=32768 exceeds 4 GiB slice",
         "qpos_finite": False, "qvel_finite": False}
    ]
    names.append(("oom_capacity", m))

    # 6. NaN injection — corrupted read-back
    m = json.loads(json.dumps(good))
    m["points"][2]["qpos_finite"] = False  # inject into nworld=512
    names.append(("nan_injection", m))

    for name, data in names:
        path = os.path.join(out_dir, name + ".json")
        with open(path, "w") as fh:
            json.dump(data, fh, indent=2)
        print(name)


if __name__ == "__main__":
    main()
