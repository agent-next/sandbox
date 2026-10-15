#!/usr/bin/env python3
"""bake_physics.py — simulate Scene B with pinned headless PhysX (ovphysx)
and bake the time-sampled rigid-body xforms into scene.usda.

Reads the physics template (a rigid-body scene authored by build_scenes.py)
and replaces the static body xforms with `xformOp:translate.timeSamples` /
`xformOp:orient.timeSamples` recorded from the simulation at 30 fps (physics
substepped at 240 Hz, sampled every 8th step).  The committed scene.usda is
the baked output, so the renderer shows exactly the trajectory the judge
graded — and the checker in validate_scenes.py re-simulates to the same
trajectory.

Run with the pinned venv python (requires pxr):
  judge/bake_physics.py <template.usda> <out.usda> [--fps 30] [--duration-s 6]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import ovphysx
import ovstage
from ovphysx import PhysX, PhysXConfig
from ovphysx.types import SimObjectType


def find_newton_schema_dir():
    spec = __import__("importlib").util.find_spec("newton_usd_schemas")
    if spec is None or not spec.submodule_search_locations:
        return None
    d = Path(spec.submodule_search_locations[0])
    return str(d) if (d / "generatedSchema.usda").is_file() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("template", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--duration-s", type=float, default=6.0)
    args = ap.parse_args()

    from pxr import Sdf, Usd, UsdGeom, Gf

    dt = 1.0 / 240.0  # physics substep (s)
    subsample = 240 // args.fps
    steps = int(args.duration_s * 240)

    schema_dirs = [str(ovphysx.codeless_schema_root())]
    nd = find_newton_schema_dir()
    if nd:
        schema_dirs.append(nd)
    ovstage.population.register_usd_schemas(schema_dirs)

    stage = ovstage.Stage("bake-physics")
    physx = None
    traj = {}
    try:
        ovstage.population.open_usd(
            stage, str(args.template), ordinal=1,
            domains=ovstage.PopulationDomain.ALL)
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
                            t.numpy().copy() for t in g.tensors]
            return rows

        for k in range(steps):
            physx.step_sync(dt)
            if k % subsample == 0:
                r = read(["position", "orientation"])
                for pl, tens in r.get("position", {}).items():
                    arr = tens[0]
                    for i, p in enumerate(pl):
                        traj.setdefault(p, {"t": [], "pos": [], "quat": []})
                        traj[p]["t"].append(k)
                        traj[p]["pos"].append(list(arr[i]))
                for pl, tens in r.get("orientation", {}).items():
                    arr = tens[0]
                    for i, p in enumerate(pl):
                        if p in traj:
                            traj[p]["quat"].append(list(arr[i]))
    finally:
        if physx is not None:
            physx.detach_ovstage()
            physx.destroy()
        stage.destroy()

    # ---- write baked scene.usda from the template + recorded samples ----
    # Open template as usda text, then patch each body's xformOp.
    # Simplest robust route: open template layer, edit the 3 bodies directly
    # with Sdf so the output stays usda and small.
    from pxr import UsdUtils

    st = Usd.Stage.Open(str(args.template))
    layer = st.GetRootLayer()
    n_frames = args.duration_s * args.fps
    # adjust endTimeCode
    st.SetEndTimeCode(int(n_frames))

    for path, rec in traj.items():
        prim = st.GetPrimAtPath(path)
        if not prim:
            print(f"[bake] (missing) {path}", file=sys.stderr)
            continue
        xf = UsdGeom.Xformable(prim)
        # translate
        tattr = prim.GetAttribute("xformOp:translate")
        if not tattr:
            tattr = xf.AddTranslateOp()
            tattr.SetMetadata("apiPrecedence", 1)
        samples = {}
        for i, t in enumerate(rec["t"]):
            fr = t // subsample
            p = rec["pos"][i]
            samples[int(fr)] = (float(p[0]), float(p[1]), float(p[2]))
        tattr.Clear()
        tattr.Set(samples[0], 0)
        for fr, val in samples.items():
            tattr.Set(val, fr)

        # orientation (quatd)
        oattr = prim.GetAttribute("xformOp:orient")
        if not oattr:
            oattr = xf.AddOrientOp()
            oattr.SetMetadata("apiPrecedence", 1)
        oattr.Clear()
        for i, t in enumerate(rec["t"]):
            fr = t // subsample
            q = rec["quat"][i]
            oattr.Set(Gf.Quatd(float(q[0]),
                               float(q[1]), float(q[2]), float(q[3])),
                      int(fr))

    # prune velocity/angularVelocity so the baked scene is kinematic
    for prim in st.Traverse():
        if prim.HasAttribute("physics:velocity"):
            prim.GetAttribute("physics:velocity").Clear()
        if prim.HasAttribute("physics:angularVelocity"):
            prim.GetAttribute("physics:angularVelocity").Clear()

    st.GetRootLayer().Export(str(args.out))
    print(f"[bake] wrote {args.out} with {len(traj)} bodies, "
          f"{n_frames:.0f} frames")
    return 0


if __name__ == "__main__":
    # For the pinned venv (no pxr at import-time) this module uses pxr lazily.
    sys.exit(main())