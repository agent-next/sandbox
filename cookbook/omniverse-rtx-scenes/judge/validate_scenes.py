#!/usr/bin/env python3
"""validate_scenes.py — USD-level gate checks for the three flagship scenes.

Gates (from SPEC.md):
  G1: Silhouette vs bbox projection — camera frustum overlaps scene bbox, and
      projected bbox covers ≥ 0.5% of frame (checked by validating camera
      params + bbox; actual render coverage is stage-2 but we validate
      necessary conditions here).
  G2: No missing texture on bound materials — every Mesh with a material
      binding must resolve all its texture files locally.  MDL materials
      (surface output `outputs:mdl:surface`, shader with `info:mdl:sourceAsset`)
      must also have that MDL and every texture input resolve on disk, and a
      material with no connected surface output FAILS (it renders as an
      untextured grey blob in RTX).  UsdPreviewSurface materials pass the
      connect requirement too.
  G3: PhysX energy (Scene B only) — total KE at final frame < 0.01 J, plus a
      no-interpenetration check: at the last baked frame no box collider sits
      inside another's, and every body moved/tilted enough to be a knock-over.
  G4: USD integrity — 0 unresolved deps, metersPerUnit=1, upAxis=Y,
      ≥1 Camera, bbox non-empty, every Mesh bound.

Run:
  python3 judge/validate_scenes.py [--scene a|b|c]     # validate final scenes
  python3 judge/validate_scenes.py --selftest         # run known-bad mutants
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

from typing import NamedTuple

from pxr import Usd, UsdGeom, UsdUtils, Sdf, Gf, UsdShade, UsdPhysics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCENES = ROOT / "scenes"

# Scene B's knock-over stack (SPEC.md): >= 24 SimReady boxes, and each must
# travel far enough / tilt far enough for the topple to be visible.
PHYSX_MIN_BOXES = 24
PHYSX_MIN_FALL_M = 0.05        # min centroid travel over the 6 s bake
PHYSX_MIN_TILT_DEG = 5.0        # min orientation change over the bake
PHYSX_INTERPENETRATION_MM = 6   # tolerated collider overlap, in millimetres



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def open_stage(path: Path) -> Usd.Stage:
    return Usd.Stage.Open(str(path))


def compute_unresolved(path: Path) -> list[str]:
    """Return list of unresolved dependency strings."""
    deps = UsdUtils.ComputeAllDependencies(str(path))
    return [str(u) for u in deps[2]]


def get_bbox(stage: Usd.Stage) -> Gf.Range3d | None:
    """World-space bbox of the default prim."""
    bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
    bound = bbox_cache.ComputeWorldBound(stage.GetDefaultPrim())
    if bound.GetRange().IsEmpty():
        return None
    return bound.GetRange()


def get_cameras(stage: Usd.Stage) -> list[UsdGeom.Camera]:
    return [UsdGeom.Camera(p) for p in stage.Traverse() if p.IsA(UsdGeom.Camera)]


def get_meshes(stage: Usd.Stage) -> list[UsdGeom.Mesh]:
    return [UsdGeom.Mesh(p) for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]


def mesh_has_material_binding(mesh: UsdGeom.Mesh) -> bool:
    prim = mesh.GetPrim()
    return prim.HasRelationship("material:binding")


class MeshBinding(NamedTuple):
    """A material bound to a mesh, resolved against this machine's files."""
    material: str        # the material:binding target path
    kind: str            # "mdl" | "preview" | "unbound" | "unknown"
    missing: list[str]   # non-empty ⇒ the gate fails


def surface_shader(material_prim: Usd.Prim) -> Usd.Prim | None:
    """The Shader prim this Material's surface output is connected to, if any.

    UsdShade.Material.GetSurfaceOutput().GetConnectedSource() returns nothing
    for materials bound by the SimReady packs even when `outputs:mdl:surface`
    is authored, so the connection is read straight off the attribute.  Try
    the MDL render context first, then UsdPreviewSurface's `outputs:surface`.
    """
    for name in ("outputs:mdl:surface", "outputs:surface",
                 "outputs:universal:surface"):
        attr = material_prim.GetAttribute(name)
        conns = attr.GetConnections() if attr else []
        for path in conns:
            shader = material_prim.GetStage().GetPrimAtPath(path.GetPrimPath())
            if shader:
                return shader
    return None


def surface_output_name(material_prim: Usd.Prim) -> str | None:
    for name in ("outputs:mdl:surface", "outputs:surface",
                 "outputs:universal:surface"):
        attr = material_prim.GetAttribute(name)
        if attr and attr.GetConnections():
            return name
    return None


def shader_mdl_source(shader_prim: Usd.Prim) -> str | None:
    """`info:mdl:sourceAsset` of a shader, or None when it is not MDL.

    `str(Sdf.AssetPath)` returns the delimited reference (`@OmniPBR.mdl@`),
    which would not match anything on disk; use the bare `.path` field (or
    strip the delimiters from a non-AssetPath string).
    """
    if not shader_prim:
        return None
    attr = shader_prim.GetAttribute("info:mdl:sourceAsset")
    val = attr.Get() if attr else None
    if not val:
        return None
    if isinstance(val, Sdf.AssetPath):
        return val.path
    return str(val).strip("@")


def resolve_asset_path(path: str, layer_dirs: list[Path]) -> Path:
    """Resolve a (possibly bare) asset reference against the candidate dirs.

    USD resolves a bare reference like `OmniPBR.mdl` against the referencing
    layer's folder; texure inputs carry relative `./materials/...` paths that
    resolve the same way.  `Sdf.AssetPath.resolvedPath` already does that by
    itself once the resolver context is set, so that comes first; the explicit
    dir walk is the fallback for paths the resolver could not map.
    """
    path = path.strip("@")
    sp = Sdf.AssetPath(path)
    resolved = sp.resolvedPath
    if resolved and Path(resolved).exists():
        return Path(resolved)
    for d in layer_dirs:
        cand = d / path.lstrip("./")
        if cand.exists():
            return cand
    return Path(resolved) if resolved else Path(path)


def mesh_material_binding(stage: Usd.Stage, mesh: UsdGeom.Mesh,
                          scene_dir: Path,
                          search_dirs: list[Path]) -> MeshBinding:
    """What the mesh's bound material resolves to locally.

    Returns a MeshBinding whose `missing` list is non-empty (→ gate failure)
    when:
      * the Material has no connected surface output — an MDL-less or
        half-authored material cannot render, so it is a defect, not a pass; or
      * the surface shader's `info:mdl:sourceAsset` does not exist on disk; or
      * one of its texture inputs does not exist on disk.
    """
    prim = mesh.GetPrim()
    rel = prim.GetRelationship("material:binding")
    if not rel:
        return MeshBinding("", "unbound", [])
    targets = rel.GetTargets()
    if not targets:
        return MeshBinding("", "unbound", ["no material:binding targets"])

    missing: list[str] = []
    for t in targets:
        mat_prim = stage.GetPrimAtPath(t)
        if not mat_prim:
            missing.append(f"material prim not found: {t}")
            continue
        layer_dirs = [Path(l.realPath).parent
                      for l in stage.GetUsedLayers() if l.realPath]
        if not layer_dirs:
            layer_dirs = [scene_dir]
        layer_dirs += list(search_dirs)
        layer_dirs.append(scene_dir)

        shader_prim = surface_shader(mat_prim)
        if shader_prim is None:
            # A Material with no connected surface output cannot render: the
            # validator must FAIL rather than treat it as a constant-colour
            # material with nothing to check.
            out = surface_output_name(mat_prim)
            missing.append(
                f"material {t}: surface output "
                f"'{out or 'outputs:surface'}' is not connected to a shader")
            continue

        mdl = shader_mdl_source(shader_prim)
        if mdl and not resolve_asset_path(mdl, layer_dirs).exists():
            missing.append(f"mdl {mdl} not found")
        kind = "mdl" if mdl else "preview"

        for inp in UsdShade.Shader(shader_prim).GetInputs():
            if inp.GetTypeName() in ("asset", "texture"):
                val = inp.Get()
                if isinstance(val, Sdf.AssetPath) and val.path and \
                        not resolve_asset_path(val.path, layer_dirs).exists():
                    missing.append(val.path)
        return MeshBinding(str(t), kind, missing)
    return MeshBinding(str(targets[0]), "unknown", missing)


def mesh_bound_textures_resolve(stage: Usd.Stage, mesh: UsdGeom.Mesh,
                                stage_root: Path,
                                search_dirs: list[Path] | None = None
                                ) -> tuple[bool, list[str]]:
    """Gate G2: the mesh's bound material resolves fully on this machine.

    Every material the SimReady packs bind is an MDL OmniPBR material (surface
    output `outputs:mdl:surface` → Shader with `info:mdl:sourceAsset` and
    texture inputs).  UsdPreviewSurface materials are accepted too, but a
    material whose surface output is not connected to any shader — or whose
    MDL/textures do not resolve — fails the gate: it would render as an
    untextured grey blob in RTX.
    """
    binding = mesh_material_binding(
        stage, mesh, stage_root, search_dirs if search_dirs is not None else [])
    return len(binding.missing) == 0, binding.missing


def material_stats(stage: Usd.Stage, scene_dir: Path,
                   search_dirs: list[Path] | None = None
                   ) -> dict[str, int]:
    """Per-scene material census: MDL vs UsdPreviewSurface vs unresolvable."""
    stats = {"mdl": 0, "preview": 0, "unbound": 0, "unknown": 0,
             "unresolved": 0}
    seen: set[str] = set()
    for m in get_meshes(stage):
        if not mesh_has_material_binding(m):
            continue
        for t in m.GetPrim().GetRelationship("material:binding").GetTargets():
            if str(t) in seen:
                continue
            seen.add(str(t))
            binding = mesh_material_binding(stage, m, scene_dir,
                                            search_dirs or [])
            stats[binding.kind] += 1
            if binding.missing:
                stats["unresolved"] += 1
    return stats


def camera_frustum_overlaps_bbox(cam: UsdGeom.Camera, bbox: Gf.Range3d) -> bool:
    """Heuristic: camera points at the scene bbox (not at sky), and the bbox
    projects to a non-degenerate footprint within the frustum.

    Eye-inside-bbox is fine (camera within scene).  We only reject:
      * camera way outside looking away from bbox (points at sky), and
      * camera exactly at bbox center pointing in any direction (degenerate).

    Evaluates at every time sample of the camera's animated translate so a
    dolly/turntable that ever points away is rejected.
    """
    center = (bbox.GetMin() + bbox.GetMax()) * 0.5
    ext = bbox.GetMax() - bbox.GetMin()
    ext_mag = ext.GetLength()

    # Collect time codes: animated translate on the camera or its parent,
    # falling back to time 0 for static cameras.
    time_codes = [Usd.TimeCode(0.0)]
    for prim in (cam.GetPrim(), cam.GetPrim().GetParent()):
        t_attr = prim.GetAttribute("xformOp:translate")
        if t_attr and t_attr.GetTimeSamples():
            time_codes = [Usd.TimeCode(t) for t in t_attr.GetTimeSamples()]
            break

    for tc in time_codes:
        cache = UsdGeom.XformCache(tc)
        local_to_world = cache.GetLocalToWorldTransform(cam.GetPrim())
        eye = local_to_world.ExtractTranslation()

        # Degenerate: eye exactly at center → no view direction is "at" anything
        if (eye - center).GetLength() < 1e-6 * max(ext_mag, 1e-6):
            return False

        # View direction (-Z of camera local space)
        view_dir = -local_to_world.ExtractRotation().TransformDir(Gf.Vec3d(0, 0, 1))
        to_center = center - eye
        to_center_len = to_center.GetLength()
        if to_center_len < 1e-6:
            return False

        dot = Gf.Dot(view_dir.GetNormalized(), to_center.GetNormalized())
        # Require the camera to look roughly toward the bbox center (dot >= 0.25
        # ≈ within ~75° of pointing at it).  Pointing at the sky looks away.
        if dot < 0.25:
            return False

    return True


def _quat_angle(q0, q1) -> float:
    """Angle between two quaternions, in degrees."""
    # xformOp:orient comes back as a Gf.Quatd/Quatf or a plain tuple — both
    # expose (real, i, j, k) components; normalize on the way in so the dot
    # product is in [-1, 1].
    def comps(q):
        if isinstance(q, Gf.Quatd) or isinstance(q, Gf.Quatf):
            return [q.GetReal(), *[q.GetImaginary()[i] for i in range(3)]]
        return list(q)
    a, b = comps(q0), comps(q1)
    d = abs(sum(a[i] * b[i] for i in range(4)))
    return math.degrees(2 * math.acos(max(-1.0, min(1.0, d))))


def _oriented_points(points, quat, translate) -> list[tuple[float, float, float]]:
    """Apply (quat, translate) to every point, world-Y-up."""
    q = _quat_to_gf(quat)
    rot = Gf.Quaternion(q.GetReal(), q.GetImaginary())
    out = []
    for p in points:
        v = rot.Transform(Gf.Vec3f(*[float(x) for x in p]))
        out.append((v[0] + translate[0], v[1] + translate[1],
                    v[2] + translate[2]))
    return out


def _obb_from_points(points):
    """Local min/max of a collider mesh's points (its local box extent)."""
    mn = [min(p[i] for p in points) for i in range(3)]
    mx = [max(p[i] for p in points) for i in range(3)]
    return mn, mx


def _quat_to_gf(quat) -> Gf.Quatd:
    """Normalize an xformOp:orient value (Gf.Quatd/Quatf or tuple) to Gf.Quatd."""
    if isinstance(quat, Gf.Quatd):
        return quat
    if isinstance(quat, Gf.Quatf):
        return Gf.Quatd(float(quat.GetReal()),
                        float(quat.GetImaginary()[0]),
                        float(quat.GetImaginary()[1]),
                        float(quat.GetImaginary()[2]))
    return Gf.Quatd(float(quat[0]), float(quat[1]), float(quat[2]),
                    float(quat[3]))


def _point_in_obb(pt, quat, translate, mn, mx, tol: float) -> bool:
    """Is world-space point pt inside the oriented box (mn..mx) + tol?"""
    q = _quat_to_gf(quat)
    local = q.GetInverse().Transform(Gf.Vec3d(pt[0] - translate[0],
                                               pt[1] - translate[1],
                                               pt[2] - translate[2]))
    return all(mn[i] - tol <= local[i] <= mx[i] + tol for i in range(3))


def check_no_interpenetration(stage: Usd.Stage, body_prims: list,
                              tol: float = PHYSX_INTERPENETRATION_MM / 1000
                              ) -> list[str]:
    """G3: at the final baked frame, no box's collider sits inside another's.

    The bake collides each body as a convex hull of its own mesh points, and
    box-against-box is the overwhelmingly common contact here.  A contained
    vertex (beyond a small solver-slop tolerance) therefore means the baked
    result interpenetrates: the sim was mis-settled, not merely "close".
    Mirrors the geometry the physics engine actually collided.
    """
    if not body_prims:
        return []

    obbs = []
    for prim in body_prims:
        collider = next((c for c in prim.GetAllChildren()
                         if c.GetTypeName() == "Mesh"
                         and c.HasAttribute("physics:approximation")), None)
        if collider is None:
            continue
        pts = UsdGeom.Mesh(collider).GetPointsAttr().Get()
        if not pts:
            continue
        t_attr = prim.GetAttribute("xformOp:translate")
        o_attr = prim.GetAttribute("xformOp:orient")
        if not (t_attr and o_attr and t_attr.GetTimeSamples()):
            continue
        last = max(t_attr.GetTimeSamples())
        translate = t_attr.Get(Usd.TimeCode(last))
        quat = o_attr.Get(Usd.TimeCode(last)) if o_attr else \
            (1.0, 0.0, 0.0, 0.0)
        mn, mx = _obb_from_points(pts)
        obbs.append((prim.GetPath().pathString, pts, quat, translate, mn, mx))

    def world_pts(quat, translate, pts):
        q = _quat_to_gf(quat)
        out = []
        for p in pts:
            v = q.Transform(Gf.Vec3d(float(p[0]), float(p[1]), float(p[2])))
            out.append((v[0] + translate[0], v[1] + translate[1],
                        v[2] + translate[2]))
        return out

    bad = []
    for i in range(len(obbs)):
        for j in range(i + 1, len(obbs)):
            (na, ptsa, qa, ta, mna, mxa), (nb, ptsb, qb, tb, mnb, mxb) = \
                obbs[i], obbs[j]
            # containment is directional: a vertex of B inside A (or of A
            # inside B), beyond the solver-slop tolerance, is interpenetration.
            wb = world_pts(qb, tb, ptsb)
            if any(_point_in_obb(p, qa, ta, mna, mxa, tol) for p in wb):
                bad.append(f"{na} <-> {nb}")
                continue
            wa = world_pts(qa, ta, ptsa)
            if any(_point_in_obb(p, qb, tb, mnb, mxb, tol) for p in wa):
                bad.append(f"{na} <-> {nb}")
    return bad


def material_search_dirs(scene_dir: Path) -> list[Path]:
    """Directories a bare `OmniPBR.mdl` may resolve against for this scene.

    USD resolves a bare MDL reference against the folder of the layer that
    referenced it; build_scenes.py also drops the chain into every
    `materials/` dir and the scene-root `mdl/`.  Search all three.
    """
    dirs = [scene_dir, scene_dir / "mdl"]
    for p in (scene_dir / "assets").rglob("materials"):
        dirs.append(p)
    for p in (scene_dir / "assets").rglob("mdl"):
        dirs.append(p)
    seen: set[Path] = set()
    return [d for d in dirs if not (d in seen or seen.add(d))]


def check_scene_a(stage: Usd.Stage, stage_root: Path,
                  scene_dir: Path | None = None) -> dict:
    """A/C — dolly or turntable scene, 8s (warehouse) / 12s (arm), 30 fps.

    scene_dir overrides which scene folder's assets to resolve against, so the
    arm scene is checked against its own assets, not the warehouse's.
    """
    errors = []
    warnings = []

    # G4: USD integrity
    scene_dir = Path(scene_dir) if scene_dir else \
        Path(stage_root) / "scenes" / "warehouse"
    search_dirs = material_search_dirs(scene_dir)
    # Validate the stage actually under test: for the real scenes it is
    # scene_dir/scene.usda, for a mutant it is the mutant file itself — the
    # mutant's injected unresolvable reference must be what G4 sees, not the
    # pristine scene.
    root_layer = stage.GetRootLayer().realPath
    check_path = Path(root_layer) if root_layer else scene_dir / "scene.usda"
    unresolved = compute_unresolved(check_path)
    if unresolved:
        errors.append(f"G4: {len(unresolved)} unresolved deps: {unresolved}")

    mpu = UsdGeom.GetStageMetersPerUnit(stage)
    if abs(mpu - 1.0) > 1e-6:
        errors.append(f"G4: metersPerUnit = {mpu}, expected 1.0")

    up = UsdGeom.GetStageUpAxis(stage)
    if up != "Y":
        errors.append(f"G4: upAxis = {up}, expected Y")

    # G4: an active physics scene must pull toward the ground.  Rendering-only
    # scenes (A/C) leave simulationOwner empty and gravity unset, so a flipped
    # gravity to (0,1,0) on an *active* scene is a defect the gate must name.
    for prim in stage.Traverse():
        if prim.IsA(UsdPhysics.Scene):
            owner = prim.GetAttribute("physics:simulationOwner").Get()
            grav = prim.GetAttribute("physics:gravityDirection").Get()
            if owner and grav and grav[1] > 0:
                errors.append(
                    f"G4: PhysicsScene {prim.GetPath()} gravity points up "
                    f"{tuple(grav)}")

    cams = get_cameras(stage)
    if len(cams) != 1:
        errors.append(f"G4: {len(cams)} cameras, expected 1")
    cam = cams[0] if cams else None

    bbox = get_bbox(stage)
    if bbox is None:
        errors.append("G4: bbox empty")
    else:
        if cam and not camera_frustum_overlaps_bbox(cam, bbox):
            errors.append("G1: camera frustum does not overlap scene bbox")

    meshes = get_meshes(stage)
    unbound = [m for m in meshes if not mesh_has_material_binding(m)]
    if unbound:
        errors.append(f"G2: {len(unbound)} meshes without material:binding")

    # G2: every bound material resolves: MDL source + textures on disk, and
    # its surface output actually connected to a shader.
    for m in meshes:
        if mesh_has_material_binding(m):
            ok, missing = mesh_bound_textures_resolve(stage, m, scene_dir,
                                                      search_dirs)
            if not ok:
                errors.append(
                    f"G2: mesh {m.GetPrim().GetPath()}: {missing}")

    # Per-scene material census (reported, and asserted in the log/JSON).
    mats = material_stats(stage, scene_dir, search_dirs)

    # Camera animation: should have timeSamples on translate
    if cam:
        xf = UsdGeom.Xformable(cam.GetPrim())
        t_attr = xf.GetPrim().GetAttribute("xformOp:translate")
        if t_attr and not t_attr.GetTimeSamples():
            warnings.append("G1: camera has no animated translate timeSamples")

    return {"errors": errors, "warnings": warnings,
            "stats": {"meshes": len(meshes), "bound": len(meshes) - len(unbound),
                      "cameras": len(cams), "unresolved": len(unresolved),
                      "materials": mats}}


def check_scene_c(stage: Usd.Stage, stage_root: Path) -> dict:
    """Arm: C — 12s turntable, 360 frames, 30 fps, Y-up, meters."""
    # Same checks as A, but against the arm scene's own asset folder.
    return check_scene_a(stage, stage_root,
                         scene_dir=Path(stage_root) / "scenes" / "arm")


def check_scene_b(stage: Usd.Stage, stage_root: Path) -> dict:
    """Physics: B — baked trajectory, 180 frames, 30 fps, Y-up, meters."""
    errors = []
    warnings = []

    scene_dir = Path(stage_root) / "scenes" / "physics"
    search_dirs = material_search_dirs(scene_dir)
    unresolved = compute_unresolved(scene_dir / "scene.usda")
    if unresolved:
        errors.append(f"G4: {len(unresolved)} unresolved deps: {unresolved}")

    mpu = UsdGeom.GetStageMetersPerUnit(stage)
    if abs(mpu - 1.0) > 1e-6:
        errors.append(f"G4: metersPerUnit = {mpu}, expected 1.0")

    up = UsdGeom.GetStageUpAxis(stage)
    if up != "Y":
        errors.append(f"G4: upAxis = {up}, expected Y")

    cams = get_cameras(stage)
    if len(cams) != 1:
        errors.append(f"G4: {len(cams)} cameras, expected 1")

    bbox = get_bbox(stage)
    if bbox is None:
        errors.append("G4: bbox empty")

    meshes = get_meshes(stage)
    # Only visual meshes (not colliders) need materials; colliders are Mesh with
    # physics:approximation = "convexHull" and no material:binding
    visual_meshes = [m for m in meshes if not m.GetPrim().HasAttribute("physics:approximation")]
    for m in visual_meshes:
        if not mesh_has_material_binding(m):
            errors.append(f"G2: visual mesh {m.GetPrim().GetPath()} unbound")
        else:
            ok, missing = mesh_bound_textures_resolve(stage, m, scene_dir,
                                                      search_dirs)
            if not ok:
                errors.append(
                    f"G2: mesh {m.GetPrim().GetPath()}: {missing}")

    mats = material_stats(stage, scene_dir, search_dirs)

    # G3: PhysX energy check — kinetic energy should be near zero at end
    # We can't run PhysX here (no GPU/ovphysx in this venv); the bake already
    # did it.  Check that velocity/angularVelocity attrs are cleared (baked
    # scene is kinematic).  Zero-valued defaults (Gf.Vec3f(0,0,0)) are truthy as
    # Python objects; check magnitude instead.
    for prim in stage.Traverse():
        vel_attr = prim.GetAttribute("physics:velocity")
        if vel_attr and vel_attr.Get():
            vel = vel_attr.Get()
            if hasattr(vel, "__len__") and len(vel) == 3:
                if (vel[0]**2 + vel[1]**2 + vel[2]**2) > 1e-12:
                    warnings.append(f"G3: {prim.GetPath()} still has physics:velocity")
            elif hasattr(vel, "GetLength"):
                if vel.GetLength() > 1e-12:
                    warnings.append(f"G3: {prim.GetPath()} still has physics:velocity")

        angvel_attr = prim.GetAttribute("physics:angularVelocity")
        if angvel_attr and angvel_attr.Get():
            angvel = angvel_attr.Get()
            if hasattr(angvel, "__len__") and len(angvel) == 3:
                if (angvel[0]**2 + angvel[1]**2 + angvel[2]**2) > 1e-12:
                    warnings.append(f"G3: {prim.GetPath()} still has physics:angularVelocity")
            elif hasattr(angvel, "GetLength"):
                if angvel.GetLength() > 1e-12:
                    warnings.append(f"G3: {prim.GetPath()} still has physics:angularVelocity")

    # G3: bodies must be dynamic (pushable), animated and settled.
    # Scene B's point is a knock-over: a stack of SimReady boxes toppled by a
    # pushed pallet, so the bodies must actually move between t0 and tEnd.
    body_roots = [prim for prim in
                  stage.Traverse(Usd.TraverseInstanceProxies())
                  if prim.HasAPI(UsdPhysics.RigidBodyAPI)
                  and not prim.HasAttribute("physics:approximation")]
    if len(body_roots) < PHYSX_MIN_BOXES:
        errors.append(
            f"G3: {len(body_roots)} rigid bodies, "
            f"expected >= {PHYSX_MIN_BOXES} SimReady boxes")
    for prim in body_roots:
        t_attr = prim.GetAttribute("xformOp:translate")
        o_attr = prim.GetAttribute("xformOp:orient")
        if not (t_attr and t_attr.GetTimeSamples()):
            errors.append(f"G3: {prim.GetPath()} missing translate timeSamples")
            continue
        times = sorted(t_attr.GetTimeSamples())
        start = t_attr.Get(Usd.TimeCode(times[0]))
        end = t_attr.Get(Usd.TimeCode(times[-1]))
        moved = (Gf.Vec3d(*[start[i] for i in range(3)]) -
                 Gf.Vec3d(*[end[i] for i in range(3)])).GetLength()
        if moved < PHYSX_MIN_FALL_M:
            errors.append(
                f"G3: {prim.GetPath()} fell only {moved:.3f} m "
                f"(expected >= {PHYSX_MIN_FALL_M} m of knock-over)")
        if o_attr and o_attr.GetTimeSamples():
            samples = sorted(o_attr.GetTimeSamples())
            q0 = o_attr.Get(Usd.TimeCode(samples[0]))
            q1 = o_attr.Get(Usd.TimeCode(samples[-1]))
            if _quat_angle(q0, q1) < PHYSX_MIN_TILT_DEG:
                warnings.append(
                    f"G3: {prim.GetPath()} rotated only "
                    f"{_quat_angle(q0, q1):.1f} deg")
    # Interpenetration: at the last frame no box's collider overlaps another's.
    inter = check_no_interpenetration(stage, body_roots)
    if inter:
        errors.append(f"G3: {len(inter)} interpenetrating bodies: {inter[:3]}")

    return {"errors": errors, "warnings": warnings,
            "stats": {"meshes": len(meshes), "visual": len(visual_meshes),
                      "bodies": len(body_roots),
                      "cameras": len(cams), "unresolved": len(unresolved),
                      "materials": mats}}


# ---------------------------------------------------------------------------
# Mutants (known-bad) for selftest
# ---------------------------------------------------------------------------
MUTANTS_DIR = HERE / "mutants"

# Each mutant is (file, description, mutator, expected_error_substring).
# The substring is the defect the gate must name when rejecting the mutant —
# a mutant rejected for any other reason (e.g. missing assets) is a
# misreported kill, and the selftest fails on it.
MUTANT_SPECS = [
    ("missing_texture.usda", "missing albedo texture on bound mesh",
     lambda s, r: _mutant_missing_texture(s), "missing_texture.png"),
    ("unresolved_ref.usda", "unresolved reference to non-existent layer",
     lambda s, r: _mutant_unresolved_ref(s), "does_not_exist.usd"),
    ("wrong_units.usda", "metersPerUnit = 0.01 (cm) instead of 1.0",
     lambda s, r: _mutant_wrong_units(s), "metersPerUnit"),
    ("gravity_flip.usda", "physics:gravityDirection = (0, 1, 0) (upwards)",
     lambda s, r: _mutant_gravity_flip(s), "gravity"),
    ("camera_off_target.usda", "camera pointing at sky (0, 1, 0)",
     lambda s, r: _mutant_camera_off_target(s), "frustum"),
    ("unbound_mesh.usda", "mesh without material:binding",
     lambda s, r: _mutant_unbound_mesh(s), "material:binding"),
    ("empty_bbox.usda", "stage with empty bbox",
     lambda s, r: _mutant_empty_bbox(s), "bbox"),
    ("no_camera.usda", "stage with no camera",
     lambda s, r: _mutant_no_camera(s), "cameras"),
    ("disconnected_mdl_surface.usda",
     "MDL material whose outputs:mdl:surface is not connected to a shader",
     lambda s, r: _mutant_disconnected_mdl_surface(s), "not connected"),
    ("unresolvable_mdl.usda",
     "MDL material whose info:mdl:sourceAsset does not resolve on disk",
     lambda s, r: _mutant_unresolvable_mdl(s), "does_not_exist.mdl"),
    ("disconnected_preview_surface.usda",
     "UsdPreviewSurface material whose outputs:surface is not connected",
     lambda s, r: _mutant_disconnected_preview_surface(s), "not connected"),
]


def _mutant_missing_texture(stage: Usd.Stage) -> Usd.Stage:
    # On one bound mesh's material, we cannot easily connect surface output
    # via UsdShade API on a composed stage.  Instead, create a NEW material
    # with a connected shader that has a missing texture, and point the mesh
    # at it.
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh) and prim.HasRelationship("material:binding"):
            targets = prim.GetRelationship("material:binding").GetTargets()
            if targets:
                # Create a new material with a connected shader and missing texture
                mat_xf = UsdGeom.Xform.Define(stage, prim.GetPath().AppendChild("BadMaterial"))
                mat_prim = mat_xf.GetPrim()
                mat = UsdShade.Material.Define(stage, mat_prim.GetPath().AppendChild("Material"))

                # Create shader under material
                shader = UsdShade.Shader.Define(stage, mat.GetPath().AppendChild("Shader"))
                shader.CreateIdAttr("OmniPBR")
                shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)

                # Set missing texture
                shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("./missing_texture.png"))

                # Connect material surface output to shader
                mat.CreateSurfaceOutput().ConnectToSource(shader.GetOutput("surface"))

                # Point mesh at the new material
                prim.GetRelationship("material:binding").SetTargets([mat.GetPath()])
                break
    return stage


def _first_bound_mesh(stage: Usd.Stage) -> Usd.Prim | None:
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh) and prim.HasRelationship("material:binding") \
                and prim.GetRelationship("material:binding").GetTargets():
            return prim
    return None


def _mutant_disconnected_mdl_surface(stage: Usd.Stage) -> Usd.Stage:
    """A Material that declares an MDL surface output but never connects it.

    This is the defect gap 4 was reported on: a material authored with
    `outputs:mdl:surface` whose shader connection is missing renders as an
    untextured default grey, and the old validator passed it because it read
    "no connected source ⇒ constant-color material ⇒ no textures to check".
    Like _mutant_missing_texture, the mesh is pointed at a brand-new
    defective material so exactly one defect is introduced.
    """
    mesh = _first_bound_mesh(stage)
    if mesh is None:
        return stage
    mat = UsdShade.Material.Define(stage, mesh.GetPath().AppendChild(
        "BadMaterial").AppendChild("Material"))
    # outputs:mdl:surface declared but with no shader connection.
    mat.GetPrim().CreateAttribute("outputs:mdl:surface",
                                  Sdf.ValueTypeNames.Token)
    mesh.GetRelationship("material:binding").SetTargets([mat.GetPath()])
    return stage


def _mutant_unresolvable_mdl(stage: Usd.Stage) -> Usd.Stage:
    """A material whose MDL source asset is not on disk.

    Patches the mesh's real bound material: its connected surface shader keeps
    its texture wiring but names an MDL that does not exist locally.
    """
    mesh = _first_bound_mesh(stage)
    if mesh is None:
        return stage
    mat_prim = stage.GetPrimAtPath(
        mesh.GetRelationship("material:binding").GetTargets()[0])
    shader = surface_shader(mat_prim)
    if not shader:
        return stage
    shader.GetAttribute("info:mdl:sourceAsset").Set(
        Sdf.AssetPath("./does_not_exist.mdl"))
    return stage


def _mutant_disconnected_preview_surface(stage: Usd.Stage) -> Usd.Stage:
    """An UsdPreviewSurface material with outputs:surface and no shader."""
    mesh = _first_bound_mesh(stage)
    if mesh is None:
        return stage
    mat = UsdShade.Material.Define(stage, mesh.GetPath().AppendChild(
        "BadPreviewMaterial").AppendChild("Material"))
    mat.GetPrim().CreateAttribute("outputs:surface",
                                   Sdf.ValueTypeNames.Token)
    mesh.GetRelationship("material:binding").SetTargets([mat.GetPath()])
    return stage


def _mutant_unresolved_ref(stage: Usd.Stage) -> Usd.Stage:
    # Add a reference to a non-existent file

    # Add a reference to a non-existent file
    root = stage.GetDefaultPrim()
    xf = UsdGeom.Xform.Define(stage, root.GetPath().AppendChild("BadRef"))
    xf.GetPrim().GetReferences().AddReference("./does_not_exist.usd")
    return stage


def _mutant_wrong_units(stage: Usd.Stage) -> Usd.Stage:
    # metersPerUnit = 0.01: set the real stage metadata, not customLayerData
    # (which UsdGeom.GetStageMetersPerUnit ignores).
    UsdGeom.SetStageMetersPerUnit(stage, 0.01)
    return stage


def _mutant_gravity_flip(stage: Usd.Stage) -> Usd.Stage:
    # Flip gravity to (0, 1, 0) and activate the physicx scene: rendering-only
    # scenes leave simulationOwner empty, so G4's gravity check would be inert.
    for prim in stage.Traverse():
        if prim.IsA(UsdPhysics.Scene):
            prim.GetAttribute("physics:simulationOwner").Set("nvphysx")
            prim.GetAttribute("physics:gravityDirection").Set(Gf.Vec3f(0, 1, 0))
            break
    return stage


def _mutant_camera_off_target(stage: Usd.Stage) -> Usd.Stage:
    # Point camera at the sky: the camera's world transform is its parent
    # CameraXform (animated translate + rotate).  Move the parent above the
    # scene and point the camera's own -Z axis straight up.
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Camera):
            parent = prim.GetParent()
            px = UsdGeom.Xformable(parent)
            t_attr = px.GetPrim().GetAttribute("xformOp:translate")
            if t_attr:
                t_attr.Set(Gf.Vec3d(0, 10, 0))
            r_attr = px.GetPrim().GetAttribute("xformOp:rotateXYZ")
            if r_attr:
                r_attr.Set(Gf.Vec3f(-90, 0, 0))
            # Camera-local rotation so the view axis (-Z) points up at (0,1,0):
            # after the parent pitch'd -90, a local +90 pitch cants it upward.
            xf = UsdGeom.Xformable(prim)
            if not xf.GetPrim().HasAttribute("xformOp:rotateXYZ"):
                xf.AddRotateXYZOp()
            prim.GetAttribute("xformOp:rotateXYZ").Set(Gf.Vec3f(180, 0, 0))
            break
    return stage


def _mutant_unbound_mesh(stage: Usd.Stage) -> Usd.Stage:
    # Remove material:binding from one mesh by overriding with empty targets.
    # The relationship comes from the referenced UR10 asset, so we need a
    # local override (SetTargets) rather than RemoveProperty.
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh) and prim.HasRelationship("material:binding"):
            rel = prim.GetRelationship("material:binding")
            rel.SetTargets([])
            break
    return stage


def _mutant_empty_bbox(stage: Usd.Stage) -> Usd.Stage:
    # Replace root with empty xform
    root = stage.GetDefaultPrim()
    for child in root.GetChildren():
        child.SetActive(False)
    return stage


def _mutant_no_camera(stage: Usd.Stage) -> Usd.Stage:
    # Deactivate all cameras
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Camera):
            prim.SetActive(False)
    return stage


def write_mutants() -> None:
    """Generate mutant .usda files from the valid scenes.

    References in the base scene are relative (`@./assets/...@`), which resolve
    against the scene's folder.  Mutants live in `judge/mutants/`, so we
    rewrite every `@./assets/...@` to an absolute path to the warehouse assets
    before mutating.  That way each mutant introduces exactly one defect and
    nothing else breaks.
    """
    MUTANTS_DIR.mkdir(parents=True, exist_ok=True)

    base_path = SCENES / "warehouse" / "scene.usda"
    base_text = base_path.read_text()
    abs_prefix = str((SCENES / "warehouse" / "assets").resolve()) + "/"
    abs_text = base_text.replace("@./assets/", f"@{abs_prefix}")
    tmp_text_path = MUTANTS_DIR / "_base_abs.usda"
    tmp_text_path.write_text(abs_text)

    for fname, desc, mutator, _ in MUTANT_SPECS:
        # Open each mutant from a fresh copy of the base at its own path.
        # USD caches layers by file path in-process, so reopening the same
        # `_base_abs.usda` returns the already-mutated layer and every later
        # mutant inherits the first mutant's defect (a silent misreport).  The
        # per-mutant copy keeps exactly one defect per mutant.
        mut_base = MUTANTS_DIR / f"_base_{Path(fname).stem}.usda"
        mut_base.write_text(abs_text)
        stage = Usd.Stage.Open(str(mut_base))
        stage = mutator(stage, None)
        out = MUTANTS_DIR / fname
        stage.GetRootLayer().Export(str(out))
        mut_base.unlink()
        print(f"  wrote {fname}: {desc}")


def run_selftest() -> int:
    """Run validation against mutants; each MUST fail for its own defect.

    A mutant that is rejected only because the scene's assets are missing (or
    any other reason unrelated to the injected defect) is a misreported kill,
    so the rejection must name the expected error substring.  The unmutated
    base is validated first as a control: it must pass every gate, otherwise
    the whole run is vacuous and reported as failed.
    """
    write_mutants()

    # Control: the unmutated base must pass.  Its refs were rewritten to
    # absolute paths (_base_abs.usda), same as the mutants.
    base = open_stage(MUTANTS_DIR / "_base_abs.usda")
    base_result = check_scene_a(base, ROOT)
    if base_result["errors"]:
        print("  ✗ CONTROL FAILED — the unmutated scene itself does not "
              "validate, so the kill rate below would be vacuous:")
        for e in base_result["errors"][:4]:
            print(f"      {e}")
        return 1
    print("  ✓ control: unmutated scene passes all gates")

    passed = 0
    failed = 0
    for fname, desc, _, expect in MUTANT_SPECS:
        stage = open_stage(MUTANTS_DIR / fname)
        result = check_scene_a(stage, ROOT)
        named = any(expect in e for e in result["errors"])
        if result["errors"] and named:
            hit = next(e for e in result["errors"] if expect in e)
            print(f"  ✓ {fname} ({desc}) — correctly REJECTED: {hit[:90]}")
            passed += 1
        elif result["errors"]:
            print(f"  ✗ {fname} ({desc}) — rejected for the WRONG reason "
                  f"(expected '{expect}'): {result['errors'][0][:90]}")
            failed += 1
        else:
            print(f"  ✗ {fname} ({desc}) — INCORRECTLY ACCEPTED")
            failed += 1
    print(f"\nSelftest: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", choices=["a", "b", "c"],
                    help="Validate one scene (a=warehouse, b=physics, c=arm)")
    ap.add_argument("--selftest", action="store_true",
                    help="Run known-bad mutants; each must be rejected")
    ap.add_argument("--json", action="store_true",
                    help="Output JSON for CI")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()

    if not args.scene:
        ap.error("One of --scene or --selftest required")

    scene_map = {
        "a": ("warehouse", SCENES / "warehouse" / "scene.usda", check_scene_a),
        "b": ("physics", SCENES / "physics" / "scene.usda", check_scene_b),
        "c": ("arm", SCENES / "arm" / "scene.usda", check_scene_c),
    }
    name, path, checker = scene_map[args.scene]

    if not path.exists():
        print(f"Scene {name} not found at {path}", file=sys.stderr)
        return 1

    stage = open_stage(path)
    result = checker(stage, ROOT)

    if args.json:
        print(json.dumps({"scene": name, "ok": len(result["errors"]) == 0,
                          "errors": result["errors"],
                          "warnings": result["warnings"],
                          "stats": result["stats"]}))
    else:
        print(f"=== {name} ===")
        if result["errors"]:
            print("  ERRORS:")
            for e in result["errors"]:
                print(f"    - {e}")
        else:
            print("  OK")
        if result["warnings"]:
            print("  WARNINGS:")
            for w in result["warnings"]:
                print(f"    - {w}")
        print(f"  stats: {result['stats']}")

    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())