#!/usr/bin/env python3
"""render_job.py — runs INSIDE the GPU sandbox (omniverse template, ovrtx RTX).

Uploaded as part of bundle.tar.zst and invoked by run.py through
POST /sandboxes/{id}/exec.  It renders all three scenes with the RTX
path tracer, writes PNG frames + an mp4 into OUTPUT_DIR, and reports
per-scene metrics in the exec `report` dict.

Contract with the product (verified live on template `omniverse`):
  * python = /opt/omniverse/bin/python (ovrtx, ovstage, pxr, PIL, numpy,
    av importable; no torch).
  * exec cwd is "/" — every path is absolute (OUTPUT_DIR or under it).
  * the GPU sandbox has NO network: the bundle carries the scenes.
  * `report` is a plain dict; the gateway returns it verbatim in the reply.

Usage (inside the sandbox):
  python render_job.py --workdir <untarred bundle root> --jobs all

Design notes (why the job looks like this):
  * Stage-1 scenes carry no UsdRender.Product, so the job authors one
    wrapper layer per scene that owns /Render/Camera + LdrColor and
    references scene.usda relatively (same folder, so the scene's own
    relative refs keep resolving).  The reference template
    (agent-infra examples/gpu/omniverse_smoke.py) proved those exact
    paths are what ovrtx steps for.
  * Animated frames come from ovstage.population.update_from_usd_time
    (time in SECONDS = timecode/fps) followed by one renderer.step()
    per frame; the physics bake (time-sampled xformOp) therefore
    renders exactly the trajectory the judge graded.
  * Path-tracer convergence: this image has no working denoiser (the
    NGX context fails at boot — logged, not fatal), so clean frames are
    bought with renderer time: --steps-per-frame accumulates renderer
    steps per frame (FrameOutput.converged/progression are recorded in
    the report so the sweep can pick the rung that clears the noise
    target without overspending).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

SCENES = {
    "warehouse": dict(label="Scene A warehouse robot dolly", frames=8 * 30),
    "physics": dict(label="Scene B PhysX crate collapse", frames=6 * 30),
    "arm": dict(label="Scene C robot arm hero turntable", frames=6 * 30),
}
W, H = 1920, 1080
FPS = 30
PRODUCT = "/Render/Camera"
LDR_VAR = "/Render/LdrColor"
# Stage-1 light intensities are authored for Kit auto-exposure; the manual
# RTX exposure needs ~1000x more radiance (see author_wrapper).
LIGHT_SCALE = 1000.0
# The bundled sky is a Radiance .hdr; a colour fallback keeps the background
# visible if ovrtx cannot decode that format (see author_wrapper).
USE_COLOR_SKY = True
SKY_COLOR = (0.05, 0.07, 0.12)


def log(msg: str) -> None:
    print(f"[render] {msg}", flush=True)


def synced_outdir(workdir: Path) -> Path:
    """The directory the gateway syncs (GET /files lists it).

    PUT /files/out/<name> lands at <lease>/out/<name>, and that same
    <lease>/out IS the directory GET /files later serves.  The exec
    global OUTPUT_DIR is *not* guaranteed: this run writes frames where
    it knows the gateway will expose them.

    Resolution order:
      1. --outdir if ever passed (unused today)
      2. env OUTPUT_DIR (set by some exec variants; the reference lands
         frames there and they ARE synced)
      3. the discovered lease root: walking up from the untarred bundle
         workdir, the dir containing `bundle/` and sibling to a
         `toplevel.txt`-style marker is the synced `out`.
      4. workdir.parent of last resort.
    """
    od = os.environ.get("OUTPUT_DIR")
    if od:
        return Path(od).resolve()
    LOOK = ("bundle",)
    cur = workdir
    for _ in range(6):
        parts = [p.name for p in cur.iterdir()] if cur.is_dir() else []
        if all(l in parts for l in LOOK):
            return cur.resolve()
        cur = cur.parent
    return workdir.parent.resolve()


def author_wrapper(scene_root: Path) -> Path:
    """Overlay layer owning the RenderProduct/Var, referencing scene.usda.

    Written with pxr (present in the image) rather than string surgery so
    the layer is guaranteed-valid USD.  Follows the canonical ovrtx
    scene_partitions.usda authoring exactly:
      * the RenderVar is a SIBLING of the product at /Render/LdrColor,
        not nested under the product path;
      * orderedVars points at that sibling;
      * `token omni:rtx:rendermode = "RealTimePathTracing"` on the product
        is what actually turns on the RTX path tracer — without it the
        product renders env-light only and comes out black;
      * resolution is Gf.Vec2i (a tuple raises a type mismatch).
    The scene is referenced from a sibling prim so the scene's own
    relative refs keep resolving (same folder)."""
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdRender

    scene_file = scene_root / "scene.usda"
    scene = Usd.Stage.Open(str(scene_file))
    cams = [p for p in scene.Traverse() if p.IsA(UsdGeom.Camera)]
    if not cams:
        raise RuntimeError(f"{scene_file}: no camera prim")
    cam_path = cams[0].GetPath().pathString

    wrapper_path = scene_root / "_render_wrapper.usda"
    stage = Usd.Stage.CreateNew(str(wrapper_path))
    root = UsdGeom.Xform.Define(stage, "/Render")
    stage.SetDefaultPrim(root.GetPrim())

    # the scene comes in under its own scope via a relative reference
    scope_path = "/Render/Scene"
    scope = UsdGeom.Xform.Define(stage, scope_path)
    scope.GetPrim().GetReferences().AddReference("./scene.usda")
    # The camera prim composes under the reference scope, so the composed
    # path is <scope>/<scene-relative path>.  Re-resolve it from the
    # composed stage: the scene's own path (/World/CameraXform/Camera)
    # does NOT exist at the wrapper's root.
    composed = f"{scope_path}{cam_path}"
    if not (stage.GetPrimAtPath(composed) or False):
        found = [p for p in stage.Traverse()
                 if p.GetName() == cam_path.rsplit("/", 1)[-1]
                 and p.IsA(UsdGeom.Camera)]
        if found:
            composed = found[0].GetPath().pathString
    cam_path = composed

    # RenderVar sibling at /Render/LdrColor (canonical path, matches the
    # product's orderedVars target and render_job's step() var lookup).
    VAR_PATH = "/Render/LdrColor"
    var = UsdRender.Var.Define(stage, VAR_PATH)
    var.CreateSourceNameAttr().Set("LdrColor")
    var.CreateDataTypeAttr().Set("color3f")

    prod = UsdRender.Product.Define(stage, PRODUCT)
    prod.CreateCameraRel().SetTargets([cam_path])
    prod.CreateResolutionAttr().Set(Gf.Vec2i(W, H))
    prod.CreateOrderedVarsRel().SetTargets([Sdf.Path(VAR_PATH)])
    # The switch that makes the product an RTX path tracer.  CreateAttribute
    # needs an Sdf.ValueTypeName (a bare "token" string picks the vector
    # overload and raises).
    prod.GetPrim().CreateAttribute(
        "omni:rtx:rendermode", Sdf.ValueTypeNames.Token).Set("RealTimePathTracing")
    # Global render settings: show every partition (no partitions authored,
    # but the canonical example sets it and it is harmless).
    settings = UsdRender.Settings.Define(stage, "/Render/Settings")
    settings.GetPrim().CreateAttribute(
        "omni:rtx:scenePartitioning:showAllPartitionsByDefault",
        Sdf.ValueTypeNames.Bool).Set(True)

    # RTX exposure lives ON THE CAMERA (canonical torus-plane.usda): the
    # dome-lit frame maps to exactly 0 without OmniRtxCameraExposureAPI,
    # which is why a bare product renders a black PNG.  `over` the camera
    # from the wrapper so the graded scene.usda is never edited.
    cam_prim = stage.GetPrimAtPath(cam_path)
    if not cam_prim or not cam_prim.IsValid():
        raise RuntimeError(f"camera {cam_path} not composed into {wrapper_path}")
    cam_prim.SetMetadata("apiSchemas", Sdf.TokenListOp.CreateExplicit(
        ["OmniRtxCameraExposureAPI_1"]))
    _attr(cam_prim, "exposure", "Float", 0.0)
    _attr(cam_prim, "exposure:fStop", "Float", 5.0)
    _attr(cam_prim, "exposure:iso", "Float", 100.0)
    _attr(cam_prim, "exposure:responsivity", "Float", 1.1026709)
    _attr(cam_prim, "exposure:time", "Float", 0.02)
    _attr(cam_prim, "omni:rtx:autoExposure:enabled", "Bool", False)

    # Stage-1 lights are authored for Kit's AUTO-exposure (a dome at
    # intensity 0.8 is a normal Kit value).  Under the manual exposure
    # above that radiance maps below 1/255 and the frame is black, so each
    # authored light is scaled up from the wrapper `over` — the graded
    # scene.usda is never edited.  1000x matches the canonical
    # scene_partitions.usda dome intensity.
    from pxr import UsdLux
    for prim in stage.Traverse():
        if prim.IsA(UsdLux.DomeLight):
            a = prim.GetAttribute("inputs:intensity")
            _attr(prim, "inputs:intensity", "Float",
                  float(a.Get() or 1.0) * LIGHT_SCALE)
            tex = prim.GetAttribute("inputs:texture:file").Get()
            if tex:
                # Without texture:format="latlong" ovrtx treats the HDR as a
                # flat projection onto a small dome, so almost no ray samples
                # it and the background renders black.  The canonical
                # scene_partitions.usda always sets it.
                _attr(prim, "inputs:texture:format", "Token", "latlong")
                if USE_COLOR_SKY:
                    # The bundled sky is a Radiance .hdr; if the ovrtx asset
                    # pipeline cannot decode it the background stays black, so
                    # the graded dome texture is kept AND a colour is added as
                    # a guaranteed-visible fallback.
                    c = prim.GetAttribute("inputs:color")
                    if not c or not c.Get():
                        _attr(prim, "inputs:color", "Color3f", SKY_COLOR)
        elif prim.IsA(UsdLux.DistantLight) or prim.IsA(UsdLux.RectLight):
            a = prim.GetAttribute("inputs:intensity")
            _attr(prim, "inputs:intensity", "Float",
                  float(a.Get() or 1.0) * LIGHT_SCALE)

    stage.GetRootLayer().Save()
    return wrapper_path


def _attr(prim, name, vtype: str, value) -> None:
    """Create (or set) an attribute with an Sdf.ValueTypeNames type."""
    from pxr import Sdf
    attr = prim.GetAttribute(name) or prim.CreateAttribute(
        name, getattr(Sdf.ValueTypeNames, vtype))
    attr.Set(value)


def render_scene(scene: str, workdir: Path, outdir: Path,
                 steps_per_frame: int, frame_limit: int) -> dict:
    """Render one scene; write <scene>/<frame>.png frames into outdir."""
    import numpy as np
    import ovrtx
    import ovstage

    scene_root = workdir / scene
    frames_dir = outdir / "frames" / scene
    frames_dir.mkdir(parents=True, exist_ok=True)
    total = SCENES[scene]["frames"]
    n = min(total, frame_limit)
    t0 = time.monotonic()

    wrapper = author_wrapper(scene_root)
    renderer = ovrtx.Renderer()
    stage = ovstage.Stage(f"omniverse.{scene}")
    written, converged_flags, noise, progressions = [], [], [], []
    ordinal = 1
    try:
        renderer.attach_ovstage(stage)
        ovstage.population.open_usd(stage, str(wrapper), ordinal=ordinal)
        stage.advance_write_floor(ordinal, ovstage.Scope.ALL).wait()

        for i in range(n):
            # Time advances one step per frame with a FRESH ordinal each
            # step, exactly like the ovrtx multi-rate-sensors example:
            #   ordinal += 1
            #   update_from_usd_time(stage, ordinal, sim_time)
            #   advance_write_floor(ordinal, ...)
            #   renderer.step(..., ordinal=ordinal)
            # The offending pattern was a fixed ordinal=1 on every frame,
            # which the population manager rejects (OP_FAILED) because the
            # write floor had already advanced past it.
            ordinal += 1
            # time in seconds (update_from_usd_time converts via fps)
            ovstage.population.update_from_usd_time(stage, ordinal=ordinal,
                                                    time_code=i / FPS)
            stage.advance_write_floor(ordinal, ovstage.Scope.ALL).wait()
            products = None
            frame_out = None
            for _ in range(steps_per_frame):
                products = renderer.step(render_products={PRODUCT},
                                         delta_time=1 / FPS, ordinal=ordinal)
            if not products:
                raise RuntimeError(f"{scene}: renderer produced nothing")
            pixels = None
            for product in products.values():
                for frame in product.frames:
                    frame_out = frame
                    rv = frame.render_vars[LDR_VAR]
                    mapping = rv.map(device=ovrtx.Device.CPU)
                    try:
                        pixels = np.from_dlpack(mapping).copy()
                    finally:
                        mapping.unmap()
                    # The renderer force-unmaps any mapping still alive at
                    # destroy and the VRAM cap then kills the lease
                    # ("VRAM cap exceeded ... graphics"), so drop every
                    # reference exactly as the canonical examples do.
                    del mapping, rv, frame
            del products
            if pixels is None:
                raise RuntimeError(f"{scene}: no {LDR_VAR} at frame {i}")
            converged_flags.append(bool(frame_out.converged)
                                   if frame_out else None)
            progressions.append(int(frame_out.progression)
                                if frame_out else None)
            from PIL import Image
            # map() already returns bytes in the same layout PIL saves;
            # clip to [0,255] uint8 so the PNG is valid RGB.
            rgb = np.clip(pixels[..., :3], 0.0, 255.0).astype(np.uint8)
            img = Image.fromarray(rgb)
            name = f"{i:04d}.png"
            img.save(frames_dir / name)
            written.append(name)
            luma = pixels[..., :3].astype(float).mean(axis=2)
            noise.append(float(luma.std()))
            del pixels, frame_out, luma

        wall = time.monotonic() - t0
        return {
            "frames": len(written),
            "steps_per_frame": steps_per_frame,
            "wall_s": round(wall, 3),
            "s_per_frame": round(wall / max(1, len(written)), 3),
            "converged_pct": round(100.0 * sum(1 for c in converged_flags if c)
                                   / max(1, len(converged_flags)), 1),
            "progression_last": progressions[-1] if progressions else None,
            "luma_std_p50": round(sorted(noise)[len(noise) // 2], 3)
            if noise else None,
        }
    finally:
        for closer in (lambda: renderer.detach_ovstage(),
                       lambda: stage.destroy(),
                       lambda: renderer.destroy()):
            try:
                closer()
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True,
                    help="untarred bundle root (contains <scene>/ scene folders)")
    ap.add_argument("--jobs", default="all",
                    help="comma list of scenes or 'all'")
    ap.add_argument("--steps-per-frame", type=int, default=1,
                    help="renderer steps accumulated per frame (convergence)")
    ap.add_argument("--frame-limit", type=int, default=10 ** 9,
                    help="render only the first N frames (sweep/debug)")
    args = ap.parse_args()

    workdir = Path(args.workdir).resolve()
    outdir = synced_outdir(workdir)
    outdir.mkdir(parents=True, exist_ok=True)

    jobs = list(SCENES) if args.jobs == "all" else args.jobs.split(",")
    report = {"steps_per_frame": args.steps_per_frame, "jobs": {}}
    t_start = time.monotonic()
    for scene in jobs:
        if scene not in SCENES:
            raise SystemExit(f"unknown scene {scene!r}; known: {list(SCENES)}")
        spec = SCENES[scene]
        log(f"{spec['label']}: {spec['frames']} frames, "
            f"{args.steps_per_frame} step(s)/frame")
        row = render_scene(scene, workdir, outdir, args.steps_per_frame,
                           args.frame_limit)
        report["jobs"][scene] = row
        log(f"{scene}: {row['frames']} frames in {row['wall_s']} s "
            f"({row['s_per_frame']} s/frame)")
    report["total_wall_s"] = round(time.monotonic() - t_start, 3)
    (outdir / "render_report.json").write_text(json.dumps(report, indent=2))
    log(f"done: {report['total_wall_s']} s total")
    print(json.dumps({"ok": True, "report": report}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
