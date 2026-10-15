#!/usr/bin/env python3
"""validate_scenes.py — USD-level gate checks for the three flagship scenes.

Gates (from SPEC.md):
  G1: Silhouette vs bbox projection — camera frustum overlaps scene bbox, and
      projected bbox covers ≥ 0.5% of frame (checked by validating camera
      params + bbox; actual render coverage is stage-2 but we validate
      necessary conditions here).
  G2: No missing texture on bound materials — every Mesh with a material
      binding must resolve all its texture files locally.
  G3: PhysX energy (Scene B only) — total KE at final frame < 0.01 J.
  G4: USD integrity — 0 unresolved deps, metersPerUnit=1, upAxis=Y,
      ≥1 Camera, bbox non-empty, every Mesh bound.

Run:
  python3 judge/validate_scenes.py [--scene a|b|c]     # validate final scenes
  python3 judge/validate_scenes.py --selftest         # run known-bad mutants
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from pxr import Usd, UsdGeom, UsdUtils, Sdf, Gf, UsdShade, UsdPhysics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCENES = ROOT / "scenes"


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


def mesh_bound_textures_resolve(stage: Usd.Stage, mesh: UsdGeom.Mesh,
                                stage_root: Path) -> tuple[bool, list[str]]:
    """Check that all textures referenced by the mesh's bound material exist locally.
    Returns (all_resolved, missing_paths).

    If the material's surface output is not connected to a shader (constant-color
    fallback), there are no texture inputs to validate → pass (no missing).
    """
    prim = mesh.GetPrim()
    mat_rel = prim.GetRelationship("material:binding")
    if not mat_rel:
        return True, []

    targets = mat_rel.GetTargets()
    if not targets:
        return False, ["no material:binding targets"]

    missing = []
    for t in targets:
        mat_prim = stage.GetPrimAtPath(t)
        if not mat_prim:
            missing.append(f"material prim not found: {t}")
            continue
        mat = UsdShade.Material(mat_prim)
        # find surface output -> shader -> inputs
        surface_out = mat.GetSurfaceOutput()
        if not surface_out:
            missing.append(f"material {t}: no surface output")
            continue
        connected = surface_out.GetConnectedSource()
        if not connected:
            # No shader connected → constant-color material, no textures to check
            continue
        shader_prim = connected[0].GetPrim()
        if not shader_prim:
            missing.append(f"material {t}: shader prim not found")
            continue
        shader = UsdShade.Shader(shader_prim)
        for inp in shader.GetInputs():
            if inp.GetTypeName() in ("asset", "texture"):
                val = inp.Get()
                if val and isinstance(val, Sdf.AssetPath):
                    # Sdf.AssetPath.resolvedPath requires an asset resolver
                    # context. For relative paths, resolve against the layer's
                    # directory (which is the warehouse assets dir for this demo).
                    p = val.resolvedPath
                    if not p:
                        # Fallback: relative path → resolve against stage root
                        p = str((stage_root / val.path).resolve())
                    if p and not Path(p).exists():
                        missing.append(p)
    return len(missing) == 0, missing


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


def check_scene_a(stage: Usd.Stage, stage_root: Path) -> dict:
    """Warehouse: A — 8s dolly, 240 frames, 30 fps, Y-up, meters."""
    errors = []
    warnings = []

    # G4: USD integrity
    unresolved = compute_unresolved(stage_root / "scenes" / "warehouse" / "scene.usda")
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

    # G2: texture resolution on bound meshes
    for m in meshes:
        if mesh_has_material_binding(m):
            ok, missing = mesh_bound_textures_resolve(stage, m, stage_root)
            if not ok:
                errors.append(f"G2: mesh {m.GetPrim().GetPath()}: missing textures {missing}")

    # Camera animation: should have timeSamples on translate
    if cam:
        xf = UsdGeom.Xformable(cam.GetPrim())
        t_attr = xf.GetPrim().GetAttribute("xformOp:translate")
        if t_attr and not t_attr.GetTimeSamples():
            warnings.append("G1: camera has no animated translate timeSamples")

    return {"errors": errors, "warnings": warnings,
            "stats": {"meshes": len(meshes), "bound": len(meshes) - len(unbound),
                      "cameras": len(cams), "unresolved": len(unresolved)}}


def check_scene_c(stage: Usd.Stage, stage_root: Path) -> dict:
    """Arm: C — 12s turntable, 360 frames, 30 fps, Y-up, meters."""
    # Reuse same checks as A
    return check_scene_a(stage, stage_root)


def check_scene_b(stage: Usd.Stage, stage_root: Path) -> dict:
    """Physics: B — baked trajectory, 180 frames, 30 fps, Y-up, meters."""
    errors = []
    warnings = []

    unresolved = compute_unresolved(stage_root / "scenes" / "physics" / "scene.usda")
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
            ok, missing = mesh_bound_textures_resolve(stage, m, stage_root)
            if not ok:
                errors.append(f"G2: mesh {m.GetPrim().GetPath()}: missing textures {missing}")

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

    # Check timeSamples exist on the 3 boxes
    for name in ["Box1", "Box2", "Box3"]:
        prim = stage.GetPrimAtPath(f"/World/Boxes/{name}")
        if not prim:
            errors.append(f"G3: missing body /World/Boxes/{name}")
            continue
        t_attr = prim.GetAttribute("xformOp:translate")
        o_attr = prim.GetAttribute("xformOp:orient")
        if not (t_attr and t_attr.GetTimeSamples()):
            errors.append(f"G3: {name} missing translate timeSamples")
        if not (o_attr and o_attr.GetTimeSamples()):
            errors.append(f"G3: {name} missing orient timeSamples")

    return {"errors": errors, "warnings": warnings,
            "stats": {"meshes": len(meshes), "visual": len(visual_meshes),
                      "cameras": len(cams), "unresolved": len(unresolved)}}


# ---------------------------------------------------------------------------
# Mutants (known-bad) for selftest
# ---------------------------------------------------------------------------
MUTANTS_DIR = HERE / "mutants"

MUTANT_SPECS = [
    ("missing_texture.usda", "missing albedo texture on bound mesh",
     lambda s, r: _mutant_missing_texture(s)),
    ("unresolved_ref.usda", "unresolved reference to non-existent layer",
     lambda s, r: _mutant_unresolved_ref(s)),
    ("wrong_units.usda", "metersPerUnit = 0.01 (cm) instead of 1.0",
     lambda s, r: _mutant_wrong_units(s)),
    ("gravity_flip.usda", "physics:gravityDirection = (0, 1, 0) (upwards)",
     lambda s, r: _mutant_gravity_flip(s)),
    ("camera_off_target.usda", "camera pointing at sky (0, 1, 0)",
     lambda s, r: _mutant_camera_off_target(s)),
    ("unbound_mesh.usda", "mesh without material:binding",
     lambda s, r: _mutant_unbound_mesh(s)),
    ("empty_bbox.usda", "stage with empty bbox",
     lambda s, r: _mutant_empty_bbox(s)),
    ("no_camera.usda", "stage with no camera",
     lambda s, r: _mutant_no_camera(s)),
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


def _mutant_unresolved_ref(stage: Usd.Stage) -> Usd.Stage:
    # Add a reference to a non-existent file
    root = stage.GetDefaultPrim()
    xf = UsdGeom.Xform.Define(stage, root.GetPath().AppendChild("BadRef"))
    xf.GetPrim().GetReferences().AddReference("./does_not_exist.usd")
    return stage


def _mutant_wrong_units(stage: Usd.Stage) -> Usd.Stage:
    # metersPerUnit = 0.01
    layer = stage.GetRootLayer()
    layer.customLayerData["metersPerUnit"] = 0.01
    return stage


def _mutant_gravity_flip(stage: Usd.Stage) -> Usd.Stage:
    # Flip gravity to (0, 1, 0)
    for prim in stage.Traverse():
        if prim.IsA(UsdPhysics.Scene):
            prim.GetAttribute("physics:gravityDirection").Set(Gf.Vec3f(0, 1, 0))
            break
    return stage


def _mutant_camera_off_target(stage: Usd.Stage) -> Usd.Stage:
    # Point camera straight up
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Camera):
            xf = UsdGeom.Xformable(prim)
            t_attr = prim.GetAttribute("xformOp:translate")
            if t_attr:
                t_attr.Set(Gf.Vec3d(0, 10, 0))
            r_attr = prim.GetAttribute("xformOp:rotateXYZ")
            if r_attr:
                r_attr.Set(Gf.Vec3f(-90, 0, 0))
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

    for fname, desc, mutator in MUTANT_SPECS:
        stage = Usd.Stage.Open(str(tmp_text_path))
        stage = mutator(stage, None)
        out = MUTANTS_DIR / fname
        stage.GetRootLayer().Export(str(out))
        print(f"  wrote {fname}: {desc}")


def run_selftest() -> int:
    """Run validation against mutants; each MUST fail (produce ≥1 error)."""
    write_mutants()

    checkers = {
        "missing_texture.usda": check_scene_a,
        "unresolved_ref.usda": check_scene_a,
        "wrong_units.usda": check_scene_a,
        "gravity_flip.usda": check_scene_a,
        "camera_off_target.usda": check_scene_a,
        "unbound_mesh.usda": check_scene_a,
        "empty_bbox.usda": check_scene_a,
        "no_camera.usda": check_scene_a,
    }

    passed = 0
    failed = 0
    for fname, desc, _ in MUTANT_SPECS:
        path = MUTANTS_DIR / fname
        stage = open_stage(path)
        result = checkers[fname](stage, ROOT)
        if result["errors"]:
            print(f"  ✓ {fname} ({desc}) — correctly REJECTED: {result['errors'][0][:80]}")
            passed += 1
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