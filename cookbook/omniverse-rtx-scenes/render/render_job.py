#!/usr/bin/env python3
"""render_job.py — runs INSIDE the GPU sandbox (omniverse template, ovrtx RTX).

Uploaded with the scene bundle and invoked by run.py through
POST /sandboxes/{id}/exec.  It renders all three scenes with the RTX
path tracer, writes PNG frames + an mp4 into the synced output dir, and
reports per-scene metrics in the exec `report` dict.

Contract with the product (verified live on template `omniverse`):
  * python = /opt/omniverse/bin/python (ovrtx, ovstage, pxr, PIL, numpy,
    av importable; no torch).
  * exec cwd is "/" — every path is absolute.
  * the GPU sandbox has NO network: the bundle carries the scenes.
  * `report` is a plain dict; the gateway returns it verbatim in the reply.

Usage (inside the sandbox):
  python render_job.py --workdir <untarred bundle root> --jobs all

Design notes (why the job looks like this):
  * Stage-1 scenes carry no UsdRender.Product, so the job authors one
    wrapper layer per scene that owns /Render/Camera + LdrColor and
    references scene.usda relatively (same folder, so the scene's own
    relative refs keep resolving).
  * `token omni:rtx:rendermode = "RealTimePathTracing"` on the product is
    what actually turns on the RTX path tracer.
  * RTX exposure lives ON THE CAMERA via OmniRtxCameraExposureAPI; without
    it a dome-lit frame maps to exactly 0 and the PNG is black.
  * Scene B (physics) ships no light at all, so the wrapper authors a
    dome + rect key exactly like scenes A and C carry.
  * Animated frames come from ovstage.population.update_from_usd_time
    (time in SECONDS = timecode/fps) with a FRESH renderer ordinal per
    frame (the ovrtx multi-rate-sensors example pattern).
  * Clean frames come from the offline PathTracing render mode: one
    renderer.step() per frame accumulates up to
    omni:rtx:pt:samplesPerPixel samples internally and the OptiX denoiser
    (omni:rtx:pt:denoising:enabled, on by default) runs on the result —
    both are RenderProduct attributes the wrapper authors, there is no
    separate Python denoiser API in ovrtx 0.5.1.  The default
    RealTimePathTracing mode takes 1 sample per step instead: measured
    live it converges 0% of pixels with luma_std ~16 (visibly noisy), so
    --render-mode rtpt + --steps-per-frame exists only for comparison
    sweeps.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

SCENES = {
    "warehouse": dict(label="Scene A warehouse robot dolly",
                      frames=8 * 30, end_time=8.0),
    "physics": dict(label="Scene B PhysX crate collapse",
                    frames=6 * 30, end_time=6.0),
    "arm": dict(label="Scene C robot arm hero turntable",
                frames=6 * 30, end_time=6.0),
}
W, H = 1920, 1080
FPS = 30
PRODUCT = "/Render/Camera"
LDR_VAR = "/Render/LdrColor"
# Stage-1 light intensities are authored for Kit auto-exposure; the manual
# RTX exposure needs ~1000x more radiance.
LIGHT_SCALE = 1000.0
# Scene B has no lights; the wrapper adds these (dome + key).
PHYSICS_DOME_INTENSITY = 800.0
PHYSICS_KEY_INTENSITY = 2500.0
# Offline path tracing: samples accumulated per pixel inside ONE
# renderer.step() (omni:rtx:pt:samplesPerPixel), OptiX denoised.
RENDER_MODE = "PathTracing"
SAMPLES_PER_PIXEL = 32
DENOISE = True
# Camera exposure in stops above the authored 0 (see author_wrapper).  The
# default frames measure mean luma 5.7 / 89 % of pixels below 8, which makes
# the underexposed/black-frame judge gates meaningless; +4 stops (16x) was
# measured to bring the same warehouse frame to a natural exposure.
EXPOSURE_STOPS = 4.0


def log(msg: str) -> None:
    print(f"[render] {msg}", flush=True)


def synced_outdir(workdir: Path, explicit: str | None = None) -> Path:
    """The directory the gateway syncs (GET /files lists it).

    PUT /files/out/<name> lands at <lease>/out/<name>, and that same
    <lease>/out IS the directory GET /files later serves (the exec global
    OUTPUT_DIR points at it).  Resolution order:
      1. --outdir (run.py always passes it: Path(OUTPUT_DIR)/"bundle")
      2. env OUTPUT_DIR
      3. walking up from the untarred workdir, the first dir whose
         children include the untar payload marker `bundle`
      4. workdir.parent of last resort.
    """
    if explicit:
        return Path(explicit).resolve()
    od = os.environ.get("OUTPUT_DIR")
    if od:
        return Path(od).resolve()
    cur = workdir
    for _ in range(6):
        try:
            names = {p.name for p in cur.iterdir()}
        except OSError:
            break
        if "bundle" in names:
            return cur.resolve()
        cur = cur.parent
    return workdir.parent.resolve()


def _attr(prim, name, vtype: str, value) -> None:
    """Create (or set) an attribute with an Sdf.ValueTypeNames type."""
    from pxr import Sdf
    attr = prim.GetAttribute(name) or prim.CreateAttribute(
        name, getattr(Sdf.ValueTypeNames, vtype))
    attr.Set(value)


def author_wrapper(scene_root: Path, render_mode: str = RENDER_MODE,
                   spp: int = SAMPLES_PER_PIXEL,
                   denoise: bool = DENOISE,
                   exposure_stops: float = EXPOSURE_STOPS) -> Path:
    """Overlay layer owning the RenderProduct/Var, referencing scene.usda."""
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdRender, UsdLux

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

    scope_path = "/Render/Scene"
    scope = UsdGeom.Xform.Define(stage, scope_path)
    scope.GetPrim().GetReferences().AddReference("./scene.usda")
    composed = f"{scope_path}{cam_path}"
    if not (stage.GetPrimAtPath(composed) or False):
        found = [p for p in stage.Traverse()
                 if p.GetName() == cam_path.rsplit("/", 1)[-1]
                 and p.IsA(UsdGeom.Camera)]
        if found:
            composed = found[0].GetPath().pathString
    cam_path = composed

    VAR_PATH = "/Render/LdrColor"
    var = UsdRender.Var.Define(stage, VAR_PATH)
    var.CreateSourceNameAttr().Set("LdrColor")
    var.CreateDataTypeAttr().Set("color3f")

    prod = UsdRender.Product.Define(stage, PRODUCT)
    prod.CreateCameraRel().SetTargets([cam_path])
    prod.CreateResolutionAttr().Set(Gf.Vec2i(W, H))
    prod.CreateOrderedVarsRel().SetTargets([Sdf.Path(VAR_PATH)])
    # The switch that makes the product an RTX path tracer.  PathTracing
    # (offline) accumulates --spp samples inside one renderer.step() and
    # denoises with OptiX before returning; RealTimePathTracing takes one
    # sample per step and needs a warm-up loop to converge.
    prod.GetPrim().CreateAttribute(
        "omni:rtx:rendermode", Sdf.ValueTypeNames.Token).Set(render_mode)
    if render_mode == "PathTracing":
        _attr(prod.GetPrim(), "omni:rtx:pt:samplesPerPixel", "UInt", int(spp))
        _attr(prod.GetPrim(), "omni:rtx:pt:denoising:enabled", "Bool", bool(denoise))
        # temporal accumulation would smear the fast crate motion in B
        _attr(prod.GetPrim(), "omni:rtx:pt:denoising:optix:temporal",
              "Bool", False)
    settings = UsdRender.Settings.Define(stage, "/Render/Settings")
    settings.GetPrim().CreateAttribute(
        "omni:rtx:scenePartitioning:showAllPartitionsByDefault",
        Sdf.ValueTypeNames.Bool).Set(True)

    cam_prim = stage.GetPrimAtPath(cam_path)
    if not cam_prim or not cam_prim.IsValid():
        raise RuntimeError(f"camera {cam_path} not composed into {wrapper_path}")
    cam_prim.SetMetadata("apiSchemas", Sdf.TokenListOp.CreateExplicit(
        ["OmniRtxCameraExposureAPI_1"]))
    _attr(cam_prim, "exposure", "Float", float(exposure_stops))
    _attr(cam_prim, "exposure:fStop", "Float", 5.0)
    _attr(cam_prim, "exposure:iso", "Float", 100.0)
    _attr(cam_prim, "exposure:responsivity", "Float", 1.1026709)
    _attr(cam_prim, "exposure:time", "Float", 0.02)
    _attr(cam_prim, "omni:rtx:autoExposure:enabled", "Bool", False)

    # Scale authored lights up from the wrapper `over` so the graded
    # scene.usda is never edited.
    domes = []
    for prim in stage.Traverse():
        if prim.IsA(UsdLux.DomeLight):
            domes.append(prim)
            a = prim.GetAttribute("inputs:intensity")
            _attr(prim, "inputs:intensity", "Float",
                  float(a.Get() or 1.0) * LIGHT_SCALE)
            tex = prim.GetAttribute("inputs:texture:file").Get()
            if tex:
                _attr(prim, "inputs:texture:format", "Token", "latlong")
                c = prim.GetAttribute("inputs:color")
                if not c or not c.Get():
                    _attr(prim, "inputs:color", "Color3f", (0.05, 0.07, 0.12))
        elif prim.IsA(UsdLux.DistantLight) or prim.IsA(UsdLux.RectLight):
            a = prim.GetAttribute("inputs:intensity")
            _attr(prim, "inputs:intensity", "Float",
                  float(a.Get() or 1.0) * LIGHT_SCALE)

    # Scene B authors no light: give it a dome + key so the boxes are
    # visible and the "dropped light" mutant has something to drop.
    if not domes:
        dome = UsdLux.DomeLight.Define(stage, "/Render/Environment")
        dome.CreateIntensityAttr(PHYSICS_DOME_INTENSITY)
        dome.CreateColorAttr(Gf.Vec3f(0.7, 0.72, 0.75))
        key = UsdLux.RectLight.Define(stage, "/Render/Key")
        key.CreateIntensityAttr(PHYSICS_KEY_INTENSITY)
        key.CreateWidthAttr(4.0)
        key.CreateHeightAttr(4.0)
        key.AddTranslateOp().Set(Gf.Vec3d(2.0, 4.0, 1.5))
        # AddRotateXOp takes (precision, opSuffix, isInverseOp) only, never
        # the angle: set the value on the returned op (verified live;
        # passing -60.0 here raises ArgumentError before any GPU time).
        key.AddRotateXOp().Set(-60.0)
        log("scene has no light: authored dome + rect key in the wrapper")

    stage.GetRootLayer().Save()
    return wrapper_path


def encode_mp4(frames_dir: Path, out_path: Path, fps: int = FPS) -> dict:
    """H.264 encode of a frame directory with PyAV (the omniverse image
    ships `av` 19.0.1 but NO ffmpeg binary — verified live, see
    PRODUCT-FRICTION.md).  libx264 is tried first; whatever encoder the
    image actually has is reported.  This mp4 is the review/screen copy;
    the shipped web encode is re-cut on the caller."""
    import av
    import numpy as np
    from PIL import Image
    files = sorted(frames_dir.glob("*.png"))
    if not files:
        return {"ok": False, "reason": f"no frames in {frames_dir}"}
    try:
        codec = av.codec.Codec("libx264", "w")
        name = "libx264"
    except av.error.FFmpegError:
        candidates = [c for c in ("mpeg4", "libopenh264")
                      if _codec_ok(av, c)]
        if not candidates:
            return {"ok": False, "reason": "no usable video encoder in PyAV"}
        name = candidates[0]
    options = {"crf": "16"} if name == "libx264" else {"q:v": "2"}
    container = av.open(str(out_path), mode="w")
    stream = container.add_stream(name, rate=fps)
    stream.width, stream.height = W, H
    stream.pix_fmt = "yuv420p"
    stream.options = options
    for fp in files:
        img = Image.open(fp).convert("RGB")
        frame = av.VideoFrame.from_ndarray(np.asarray(img), format="rgb24")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return {"ok": True, "codec": name, "bytes": out_path.stat().st_size,
            "frames": len(files)}


def _codec_ok(av, name: str) -> bool:
    try:
        av.codec.Codec(name, "w")
        return True
    except Exception:
        return False


def pick_hero(frames_dir: Path) -> dict:
    """The best finished hero frame: among the last quarter of the arm
    turntable (the most converged), the one with the most edge energy —
    a measured pick, not a hand choice.  Copies it to out/hero.png."""
    import numpy as np
    from PIL import Image
    files = sorted(frames_dir.glob("*.png"))
    if not files:
        return {"ok": False, "reason": "no frames"}
    tail = files[max(0, len(files) - max(1, len(files) // 4)):]
    best, best_energy = None, -1.0
    for fp in tail:
        img = np.asarray(Image.open(fp).convert("L"), dtype=np.float32)
        gx = np.abs(np.diff(img, axis=1)).mean()
        gy = np.abs(np.diff(img, axis=0)).mean()
        energy = float(gx + gy)
        if energy > best_energy:
            best, best_energy = fp, energy
    hero = frames_dir.parent.parent / "hero.png"
    hero.write_bytes(best.read_bytes())
    return {"ok": True, "frame": best.name, "edge_energy": round(best_energy, 4)}


def render_scene(scene: str, workdir: Path, outdir: Path,
                 steps_per_frame: int, frame_limit: int,
                 render_mode: str = RENDER_MODE, spp: int = SAMPLES_PER_PIXEL,
                 denoise: bool = DENOISE,
                 exposure_stops: float = EXPOSURE_STOPS) -> dict:
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

    wrapper = author_wrapper(scene_root, render_mode=render_mode, spp=spp,
                             denoise=denoise, exposure_stops=exposure_stops)
    renderer = ovrtx.Renderer()
    stage = ovstage.Stage(f"omniverse.{scene}")
    written, converged_flags, noise, progressions = [], [], [], []
    ordinal = 1
    try:
        renderer.attach_ovstage(stage)
        ovstage.population.open_usd(stage, str(wrapper), ordinal=ordinal)
        stage.advance_write_floor(ordinal, ovstage.Scope.ALL).wait()

        for i in range(n):
            # A FRESH ordinal per frame (the ovrtx multi-rate-sensors
            # example pattern): a fixed ordinal is rejected with OP_FAILED
            # because the write floor has already advanced past it.
            ordinal += 1
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
            rgb = np.clip(pixels[..., :3], 0.0, 255.0).astype(np.uint8)
            Image.fromarray(rgb).save(frames_dir / f"{i:04d}.png")
            written.append(f"{i:04d}.png")
            luma = pixels[..., :3].astype(float).mean(axis=2)
            noise.append(float(luma.std()))
            del pixels, frame_out, luma

        wall = time.monotonic() - t0
        row = {
            "frames": len(written),
            "render_mode": render_mode,
            "spp": spp if render_mode == "PathTracing" else None,
            "denoise": denoise if render_mode == "PathTracing" else None,
            "exposure_stops": exposure_stops,
            "steps_per_frame": steps_per_frame,
            "wall_s": round(wall, 3),
            "s_per_frame": round(wall / max(1, len(written)), 3),
            "converged_pct": round(100.0 * sum(1 for c in converged_flags if c)
                                   / max(1, len(converged_flags)), 1),
            "progression_last": progressions[-1] if progressions else None,
            "luma_std_p50": round(sorted(noise)[len(noise) // 2], 3)
            if noise else None,
        }
        if scene == "arm":
            row["hero"] = pick_hero(frames_dir)
        mp4 = encode_mp4(frames_dir, outdir / f"{scene}.mp4")
        row["mp4"] = mp4
        return row
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
                    help="untarred bundle root (contains <scene>/ folders)")
    ap.add_argument("--outdir", default=None,
                    help="synced output dir (default: OUTPUT_DIR / discovery)")
    ap.add_argument("--jobs", default="all",
                    help="comma list of scenes or 'all'")
    ap.add_argument("--render-mode", default=RENDER_MODE,
                    choices=["PathTracing", "RealTimePathTracing"],
                    help="PathTracing: spp samples inside ONE step, denoised")
    ap.add_argument("--spp", type=int, default=SAMPLES_PER_PIXEL,
                    help="PathTracing samples per pixel (accumulated "
                         "inside a single renderer.step())")
    ap.add_argument("--exposure-stops", type=float, default=EXPOSURE_STOPS,
                    help="camera exposure in stops (2 = 4x brighter); the "
                         "real run measures luma stats per scene and pins "
                         "the value that keeps frames clear of the "
                         "black-frame gate")
    ap.add_argument("--no-denoise", dest="denoise",
                    action="store_false", default=DENOISE,
                    help="disable the OptiX denoiser (noise measurement)")
    ap.add_argument("--steps-per-frame", type=int, default=1,
                    help="rtpt mode only: renderer steps accumulated per "
                         "frame (convergence warm-up)")
    ap.add_argument("--frame-limit", type=int, default=10 ** 9,
                    help="render only the first N frames (sweep/debug)")
    args = ap.parse_args()

    workdir = Path(args.workdir).resolve()
    outdir = synced_outdir(workdir, args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    jobs = list(SCENES) if args.jobs == "all" else args.jobs.split(",")
    report = {"render_mode": args.render_mode, "spp": args.spp,
              "denoise": args.denoise,
              "exposure_stops": args.exposure_stops,
              "steps_per_frame": args.steps_per_frame,
              "frame_limit": args.frame_limit, "jobs": {}}
    t_start = time.monotonic()
    for scene in jobs:
        if scene not in SCENES:
            raise SystemExit(f"unknown scene {scene!r}; known: {list(SCENES)}")
        spec = SCENES[scene]
        how = (f"{args.spp} spp{' denoised' if args.denoise else ' raw'}"
               if args.render_mode == "PathTracing"
               else f"{args.steps_per_frame} step(s)/frame")
        log(f"{spec['label']}: {spec['frames']} frames, "
            f"{args.render_mode} {how} @ {args.exposure_stops} stops")
        row = render_scene(scene, workdir, outdir, args.steps_per_frame,
                           args.frame_limit, render_mode=args.render_mode,
                           spp=args.spp, denoise=args.denoise,
                           exposure_stops=args.exposure_stops)
        report["jobs"][scene] = row
        log(f"{scene}: {row['frames']} frames in {row['wall_s']} s "
            f"({row['s_per_frame']} s/frame); "
            f"converged {row['converged_pct']}%")
    report["total_wall_s"] = round(time.monotonic() - t_start, 3)
    (outdir / "render_report.json").write_text(json.dumps(report, indent=2))
    log(f"done: {report['total_wall_s']} s total")
    print(json.dumps({"ok": True, "report": report}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
