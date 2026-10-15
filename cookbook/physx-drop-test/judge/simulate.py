#!/usr/bin/env python3
"""simulate.py — run one USD scene through pinned headless PhysX (ovphysx).

Called by grade.sh with the venv python.  Steps the scene on CPU with one
thread (deterministic), records per-step world positions and velocities of
the rigid bodies, and reads back the authored mass and material properties
before the first step.  Writes everything to <out_dir>/traj.npz plus
<out_dir>/meta.json; exits non-zero with a clear message if the scene
cannot be populated or stepped (that is a graded failure, not a crash).

The recorded numbers are the raw material the independent analytic oracle
in check_gates.py works on; nothing here compares against the oracle.
"""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import ovphysx
import ovstage
from ovphysx import PhysX, PhysXConfig
from ovphysx.types import SimObjectType

DT = 1.0 / 240.0          # physics step (s) — 1 frame = 1/240 s
STEPS = 2400              # 10 s simulated time
BODY_PATHS = ("/World/Box", "/World/Ball")


def find_newton_schema_dir():
    """Directory of the installed newton-usd-schemas wheel, without
    importing it (the package import needs pxr, which we do not install)."""
    spec = importlib.util.find_spec("newton_usd_schemas")
    if spec is None or not spec.submodule_search_locations:
        return None
    d = Path(spec.submodule_search_locations[0])
    return str(d) if (d / "generatedSchema.usda").is_file() else None


def main():
    if len(sys.argv) != 3:
        print("usage: simulate.py <scene.usda> <out_dir>", file=sys.stderr)
        return 2
    usd_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    schema_dirs = [str(ovphysx.codeless_schema_root())]
    newton_dir = find_newton_schema_dir()
    if newton_dir:
        schema_dirs.append(newton_dir)
    ovstage.population.register_usd_schemas(schema_dirs)

    stage = ovstage.Stage("physx-drop-test")
    physx = None
    try:
        ovstage.population.open_usd(
            stage, str(usd_path), ordinal=1,
            domains=ovstage.PopulationDomain.ALL,
        )
        stage.advance_write_floor(ordinal=1).wait()
        physx = PhysX(config=PhysXConfig(num_threads=1))
        physx.attach_ovstage(stage, read_ordinal=1)

        def read(names):
            rows = {}
            with physx.read(SimObjectType.RIGID_BODY, names) as result:
                with ovstage.PathDictionary(stage) as paths:
                    for g in result.groups:
                        if not g.tensors:
                            continue
                        pl = paths.get_path_strings(g.prim_list)
                        attr = paths.token_to_string(g.attribute)
                        rows.setdefault(attr, {})[tuple(pl)] = [
                            t.numpy().copy() for t in g.tensors
                        ]
            return rows

        props = None
        series = {p: {"y": [], "vy": []} for p in BODY_PATHS}
        for k in range(STEPS):
            physx.step_sync(DT)
            if k == 0:
                # Body/shape properties are readable once a step has
                # completed (a read observes the last completed step).
                props = read(["mass", "staticFriction", "dynamicFriction",
                              "restitution", "shapeCount"])
            r = read(["position", "linearVelocity"])
            for pl, tens in r.get("position", {}).items():
                arr = tens[0]
                for i, p in enumerate(pl):
                    if p in series:
                        series[p]["y"].append(float(arr[i][1]))
            for pl, tens in r.get("linearVelocity", {}).items():
                arr = tens[0]
                for i, p in enumerate(pl):
                    if p in series:
                        series[p]["vy"].append(float(arr[i][1]))
    finally:
        if physx is not None:
            physx.detach_ovstage()
            physx.destroy()
        stage.destroy()

    traj = {}
    for p in BODY_PATHS:
        ys = series[p]["y"]
        vs = series[p]["vy"]
        if not ys or len(ys) != STEPS or len(vs) != STEPS:
            traj[p] = None
        else:
            traj[p] = {"y": np.asarray(ys), "vy": np.asarray(vs)}

    # Flatten props into per-body dicts (row i of a group belongs to prim i)
    bodies_meta = {}
    for attr, groups in props.items():
        for pl, tens in groups.items():
            arr = np.atleast_1d(tens[0]).ravel()
            for i, p in enumerate(pl):
                if p in BODY_PATHS and i < len(arr):
                    bodies_meta.setdefault(p, {})[attr] = float(arr[i])

    missing = [p for p in BODY_PATHS if traj.get(p) is None]
    np.savez(out_dir / "traj.npz",
             **{f"{p.split('/')[-1].lower()}_y": traj[p]["y"]
                for p in BODY_PATHS if traj.get(p) is not None},
             **{f"{p.split('/')[-1].lower()}_vy": traj[p]["vy"]
                for p in BODY_PATHS if traj.get(p) is not None})
    (out_dir / "meta.json").write_text(json.dumps({
        "dt": DT, "steps": STEPS,
        "bodies": {p: bodies_meta.get(p) for p in BODY_PATHS},
        "sampled": {p: traj.get(p) is not None for p in BODY_PATHS},
        "missing": missing,
    }, indent=2) + "\n")
    print(f"[simulate] stepped {STEPS} frames dt={DT:.6f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
