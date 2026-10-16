#!/usr/bin/env python3
"""build_scenes.py — fetch, verify, localise and author the three flagship
omniverse-rtx-scenes demos (Stage 1).

Every asset is pulled from its official NVIDIA source, sha256-verified
against assets.lock.json, localised into each scene's own folder (absolute
and bare references rewritten to relative paths so the folder is
self-contained), and the final scene .usda files are authored.

Idempotent: fetches short-circuit on a matching sha256 and every scene
folder is rebuilt from its cached copy under <out>/assets/.

Scenes (see SPEC.md):
  A warehouse/   UR10 robot amid SimReady rack, pallet and boxes, HDRI dome +
                 rect lights, 8 s animated dolly camera @ 30 fps.
  C arm/         UR10 hero close-up on a SimReady table with props,
                 12 s turntable camera @ 30 fps.
  B physics/     SimReady boxes knocked over — the rigid-body scene is
                 simulated offline here with pinned ovphysx (when the pinned
                 venv is present) and the time-sampled xforms are baked into
                 scene.usda via judge/bake_physics.py.

Usage:
  python3 build_scenes.py [--out DIR] [--force] [--scene a|c|b]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import asset_types as at

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parent  # cookbook/omniverse-rtx-scenes
LOCKNAME = "assets.lock.json"
CACHE_DIR = "assets"  # raw downloads / cache, gitignored
MDL_FILES = ["OmniPBR.mdl", "OmniPBR_ClearCoat.mdl", "OmniPBRBase.mdl"]


# ---------------------------------------------------------------------------
# Lock + localisation
# ---------------------------------------------------------------------------
def load_lock(out: Path) -> dict:
    p = out / LOCKNAME
    if p.exists():
        return json.loads(p.read_text())
    raise SystemExit(f"[lock] {p} not found. Commit assets.lock.json (and the "
                     f"raw cache under {out / CACHE_DIR}) and re-run.")


def localise_into(scene_dir: Path, keys: list[str], cache: Path, lock: dict,
                  force: bool = False) -> list[Path]:
    """Copy each locked entry into scene_dir/assets/<key>, fetching first when
    missing.  A key is either:

      * a lock file key (copied singly), or
      * a lock directory prefix (every file listed under it in the lock is
        fetched then copied, preserving the prefix so relative ./materials/...,
        ./textures/... references keep resolving).

    Only files listed in the lock are copied.  Returns written paths."""
    written = []
    for key in keys:
        info = lock.get(key)
        if info is not None:
            src = cache / key
            dst = scene_dir / "assets" / key
            if not src.exists() or force:
                at.fetch(info["url"], src, info["sha256"])
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or at.sha256_file(dst) != info["sha256"]:
                shutil.copy2(src, dst)
            written.append(dst)
            continue

        # directory-prefix key: copy every locked file beneath it
        prefix = key.rstrip("/") + "/"
        sub = {k: v for k, v in lock.items() if k.startswith(prefix)}
        if not sub:
            raise SystemExit(f"[build] lock entry missing: {key}")
        for fkey in sorted(sub):
            fi = sub[fkey]
            src = cache / fkey
            if not src.exists() or force:
                at.fetch(fi["url"], src, fi["sha256"])
            dst = scene_dir / "assets" / fkey
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or at.sha256_file(dst) != fi["sha256"]:
                shutil.copy2(src, dst)
            written.append(dst)
    return written


def place_mdl_chain(scene_dir: Path, cache: Path, lock: dict,
                    force: bool = False) -> None:
    """Resolve bare @OmniPBR.mdl@ refs (and the M_*.mdl `using ::OmniPBR`
    imports) by dropping the 3-file MDL base chain wherever it is needed:
      * next to every layer that references OmniPBR.mdl by bare name
        (USD resolves a bare ref against the referencing layer's folder);
      * inside every materials/ dir (MDL search-path fallback);
      * at the scene root under mdl/ (safety net for rerendering tools).
    Run with the system python3 (pxr present)."""
    from pxr import Usd

    # ensure the base chain is in the cache (lock keys mdl/<m>)
    mdl_cache = cache / "mdl"
    mdl_cache.mkdir(parents=True, exist_ok=True)
    for m in MDL_FILES:
        info = lock.get(f"mdl/{m}")
        if info is None:
            raise SystemExit(f"[build] lock entry missing: mdl/{m}")
        src = mdl_cache / m
        if not src.exists() or force:
            at.fetch(info["url"], src, info["sha256"])

    layered_dirs = set()
    for usd_file in (scene_dir / "assets").rglob("*.usd*"):
        if usd_file.suffix not in (".usd", ".usda", ".usdc"):
            continue
        st = Usd.Stage.Open(str(usd_file))
        for prim in st.Traverse():
            bare = False
            for attr in prim.GetAttributes():
                an = attr.GetName()
                if an.endswith(":mdl:sourceAsset") or an == "info:mdl:sourceAsset":
                    v = attr.Get()
                    if v and str(v).strip("@") == "OmniPBR.mdl":
                        bare = True
                        break
            if bare:
                layered_dirs.add(usd_file.parent)
                break

    mdl_cache = cache / "mdl"
    for d in list(layered_dirs) + [
            c for c in (scene_dir / "assets").rglob("materials") if c.is_dir()]:
        d.mkdir(parents=True, exist_ok=True)
        for m in MDL_FILES:
            dst = d / m
            if not dst.exists():
                shutil.copy2(mdl_cache / m, dst)

    sroot = scene_dir / "mdl"
    sroot.mkdir(parents=True, exist_ok=True)
    for m in MDL_FILES:
        if not (sroot / m).exists():
            shutil.copy2(mdl_cache / m, sroot / m)


# ---------------------------------------------------------------------------
# Authoring helpers
# ---------------------------------------------------------------------------
def stage_header(usda: list, end_frame: int):
    usda.append("#usda 1.0")
    usda.append("(")
    usda.append('    defaultPrim = "World"')
    usda.append("    metersPerUnit = 1")
    usda.append('    upAxis = "Y"')
    usda.append("    framesPerSecond = 30")
    usda.append("    startTimeCode = 0")
    usda.append(f"    endTimeCode = {end_frame}")
    usda.append(")")
    usda.append("")


def look_at_yxz(eye, target):
    """Yaw/pitch (deg) that aims a camera's -Z view axis at target."""
    import math
    dx = target[0] - eye[0]
    dy = target[1] - eye[1]
    dz = target[2] - eye[2]
    yaw = math.degrees(math.atan2(-dx, -dz))
    horiz = math.hypot(dx, dz)
    pitch = math.degrees(math.atan2(dy, horiz))
    return (pitch, yaw, 0.0)


def write_translate_time_samples(usda: list, attr: str, samples: list,
                                 indent: str = "        "):
    """Writes `attr.timeSamples = { ... }` for a list of (frame, (x,y,z))."""
    usda.append(f"{indent}{attr}.timeSamples = {{")
    for f, p in samples:
        usda.append(
            f"{indent}    {f}: ({p[0]:.4f}, {p[1]:.4f}, {p[2]:.4f}),")
    usda.append(f"{indent}}}")


def write_rotate_time_samples(usda: list, attr: str, samples: list,
                              indent: str = "        "):
    usda.append(f"{indent}{attr}.timeSamples = {{")
    for f, r in samples:
        usda.append(f"{indent}    {f}: ({r[0]:.1f}, {r[1]:.1f}, {r[2]:.1f}),")
    usda.append(f"{indent}}}")


def anim_translate(usda: list, attr, start, end, n, indent="        ",
                   interp="linear"):
    """Animate an xformOp translate from start to end over n frames."""
    samples = []
    step = max(1, n // 30)
    for f in range(0, n + 1, step):
        t = f / n
        p = tuple(s + (e - s) * t for s, e in zip(start, end))
        samples.append((f, p))
    write_translate_time_samples(usda, attr, samples, indent)


# ---------------------------------------------------------------------------
# Scene A — warehouse
# ---------------------------------------------------------------------------
KEYS_A = [
    "Props/general/RackLongEmpty_A1",
    "Props/general/Pallet_A1",
    "Props/general/Cardbox_A2",
    "Props/general/Cardbox_A3",
    "Props/general/LongBox_A11_11x26x10xcm_PR_NVD_01",
    "Props/general/FlatBox_A12_56x56x20cm_PR_NVD_01",
    "Props/skies/Clear/evening_road_01_4k.hdr",
    "ur10",
]


def fix_rack_udim(scene_dir: Path) -> None:
    """Resolve the SimReady rack's <UDIM> placeholder texture refs to a concrete
    UDIM tile (1001) so every reference resolves offline.  The rack ships
    references to T_*_*.<UDIM>.png placeholders; we pin all of them to .1001
    (which exists in the lock) and keep only one tile per channel.

    The rack's .usd layer is binary USDC containing the <UDIM> placeholders,
    so we convert it to text usda (writing .usda over .usd) before patching,
    and rewrite the referencing scene.usda to point at the .usda layer.
    """
    import re
    from pxr import Usd

    # Rack layers reference T_*_*.<UDIM>.png placeholders as
    # `...Albedo.<UDIM>.png` (underscore before the channel name, for the rack
    # it is exactly `_Albedo.`/`_Normal.`/`_ORM.`), and a global pin to tile
    # `<UDIM>` -> 1001 is what makes every reference resolve offline.
    rack = scene_dir / "assets" / "Props" / "general" / "RackLongEmpty_A1"
    rack_usd = rack / "RackLongEmpty_A1.usd"
    rack_usda = rack / "RackLongEmpty_A1.usda"

    if rack_usd.exists() and b"<UDIM>" in rack_usd.read_bytes():
        st = Usd.Stage.Open(str(rack_usd))
        st.GetRootLayer().Export(str(rack_usda))
        rack_usd.unlink()

    for usd_file in sorted(rack.rglob("*.usd*")):
        if usd_file.suffix not in (".usd", ".usda", ".usdc"):
            continue
        data = usd_file.read_bytes()
        if b"<UDIM>" not in data:
            continue
        text = data.decode("utf-8", "ignore")
        text = text.replace("<UDIM>", "1001")
        usd_file.write_text(text)

    scene_usda = scene_dir / "scene.usda"
    if scene_usda.exists():
        text = scene_usda.read_text()
        text = text.replace("RackLongEmpty_A1.usd@", "RackLongEmpty_A1.usda@")
        scene_usda.write_text(text)


def build_a(out: Path, cache: Path, lock: dict, force: bool = False) -> dict:
    scene_dir = out / "scenes" / "warehouse"
    (scene_dir / "assets").mkdir(parents=True, exist_ok=True)
    localise_into(scene_dir, KEYS_A, cache, lock, force)
    fix_rack_udim(scene_dir)
    place_mdl_chain(scene_dir, cache, lock, force)

    N = 8 * 30  # 8 s dolly at 30 fps
    cam_eye0 = (-3.8, 2.2, 3.4)
    cam_eye1 = (0.6, 1.9, 3.0)
    cam_tgt = (-1.0, 1.0, 0.6)
    cam_pitch, cam_yaw, _ = look_at_yxz(cam_eye0, cam_tgt)

    usda = []
    stage_header(usda, N)
    usda += [
        'def Xform "World"',
        '{',
        '    def PhysicsScene "PhysicsScene"',
        '    {',
        '        uniform token physics:simulationOwner = ""',
        '    }',
        "",
        '    def DomeLight "SkyDome"',
        '    {',
        '        asset inputs:texture:file = @./assets/Props/skies/Clear/evening_road_01_4k.hdr@',
        '        float inputs:intensity = 0.8',
        '        float3 xformOp:rotateXYZ = (0, 0, 0)',
        '        uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
        '    }',
        "",
        '    def DistantLight "Sun"',
        '    {',
        '        float inputs:intensity = 1.2',
        '        float3 xformOp:rotateXYZ = (50, -30, 0)',
        '        uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
        '    }',
        "",
        '    def RectLight "Fill"',
        '    {',
        '        color3f inputs:color = (0.85, 0.9, 1.0)',
        '        float inputs:intensity = 2.5',
        '        float inputs:width = 4',
        '        float inputs:height = 2',
        '        float3 xformOp:translate = (-1.5, 3.0, 2.0)',
        '        quatf xformOp:orient = (0.94, -0.34, 0, 0)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient"]',
        '    }',
        "",
        '    def RectLight "Rim"',
        '    {',
        '        color3f inputs:color = (1.0, 0.96, 0.9)',
        '        float inputs:intensity = 1.5',
        '        float inputs:width = 3',
        '        float inputs:height = 3',
        '        float3 xformOp:translate = (0.5, 4.5, -3.5)',
        '        quatf xformOp:orient = (0.72, 0.69, 0, 0)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient"]',
        '    }',
        "",
        '    def Xform "Ground"',
        '    {',
        '        def Cube "GroundPlane"',
        '        {',
        '            float3[] extent = [(-40, -0.01, -40), (40, 0.01, 40)]',
        '            double size = 80',
        '            color3f[] primvars:displayColor = [(0.16, 0.17, 0.19)]',
        '        }',
        '    }',
        "",
        # UR10 (Z-up model -> Y-up world).  The model's arm lies along +X at height
        # ~0.15-0.21 m; after the Z->Y tilt (rotate -90 about X) it runs
        # horizontally.  We yaw about the WORLD-UP Y axis (not Z) so the arm
        # sweeps at a constant height instead of diving through the floor.
        # Base bottom is model z=-0.034 -> shift +0.034 to sit on the ground.
        '    def Xform "Robot"',
        '    {',
        '        double3 xformOp:translate = (0.9, 0.034, -0.4)',
        '        float3 xformOp:rotateXYZ = (0, -135, 0)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]',
        '        def Xform "UR10Tilt"',
        '        {',
        '            float3 xformOp:rotateXYZ = (-90, 0, 0)',
        '            uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
        '            def "UR10" (',
        '                prepend references = @./assets/ur10/ur10.usd@',
        '            )',
        '            {',
        '            }',
        '        }',
        '    }',
        "",
        # Rack (cm asset, Z-up -> rotate to Y-up)
        '    def Xform "Rack"',
        '    {',
        '        double3 xformOp:translate = (-2.6, 0, -1.0)',
        '        float3 xformOp:rotateXYZ = (0, 0, 90)',
        '        double3 xformOp:scale = (0.01, 0.01, 0.01)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]',
        '        def "RackAsset" (',
        '            prepend references = @./assets/Props/general/RackLongEmpty_A1/RackLongEmpty_A1.usda@',
        '        )',
        '        {',
        '            float3 xformOp:rotateXYZ = (-90, 0, 0)',
        '            uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
        '        }',
        '    }',
        "",
        '    def Xform "Pallet"',
        '    {',
        '        double3 xformOp:translate = (-2.2, 0, 1.3)',
        '        float3 xformOp:rotateXYZ = (0, 0, 0)',
        '        double3 xformOp:scale = (0.01, 0.01, 0.01)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]',
        '        def "PalletAsset" (',
        '            prepend references = @./assets/Props/general/Pallet_A1/Pallet_A1.usd@',
        '        )',
        '        {',
        '            float3 xformOp:rotateXYZ = (-90, 0, 0)',
        '            uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
        '        }',
        '    }',
        "",
        '    def Xform "Boxes"',
        '    {',
        '        double3 xformOp:translate = (0, 0, 0)',
        '        uniform token[] xformOpOrder = ["xformOp:translate"]',
    ]
    # boxes on/near the pallet (cm, Z-up -> Y-up).  Pallet top is at y=0.208 m
    # (0.01 * 20.87 cm); each centre sits half its own height above that.
    box_specs = [
        ("Cardbox_A3/Cardbox_A3.usd", (-2.6, 0.47, 1.55), 10),
        ("LongBox_A11_11x26x10xcm_PR_NVD_01/"
         "LongBox_A11_11x26x10xcm_PR_NVD_01.usd", (-1.9, 0.26, 1.75), -25),
        ("FlatBox_A12_56x56x20cm_PR_NVD_01/"
         "FlatBox_A12_56x56x20cm_PR_NVD_01.usd", (-1.85, 0.31, 1.25), 15),
    ]
    for i, (ref, (bx, by, bz), yaw) in enumerate(box_specs):
        usda += [
            f'        def Xform "Box{i}"',
            '        {',
            f'            double3 xformOp:translate = ({bx}, {by}, {bz})',
            f'            float3 xformOp:rotateXYZ = (0, {yaw}, 0)',
            '            double3 xformOp:scale = (0.01, 0.01, 0.01)',
            '            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]',
            f'            def "BoxAsset" (',
            f'                prepend references = @./assets/Props/general/{ref}@',
            '            )',
            '            {',
            '                float3 xformOp:rotateXYZ = (-90, 0, 0)',
            '                uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
            '            }',
            '        }',
        ]
    usda += [
        '    }',
        "",
        '    def Xform "CameraXform"',
        '    {',
    ]
    anim_translate(usda, "double3 xformOp:translate", cam_eye0, cam_eye1, N)
    usda += [
        f'        float3 xformOp:rotateXYZ = ({cam_pitch:.1f}, {cam_yaw:.1f}, 0)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]',
        '        def Camera "Camera"',
        '        {',
        '            float2 clippingRange = (0.05, 500)',
        '            float focalLength = 24',
        '            float horizontalAperture = 36',
        '            float verticalAperture = 20.25',
        '        }',
        '    }',
        '}',
    ]
    (scene_dir / "scene.usda").write_text("\n".join(usda) + "\n")
    return {"name": "warehouse", "dir": scene_dir, "usda": scene_dir / "scene.usda"}


# ---------------------------------------------------------------------------
# Scene C — arm hero close-up on a table, turntable camera
# ---------------------------------------------------------------------------
KEYS_C = [
    "Props/general/SM_MetalStainlessTable_A03_01",
    "Props/general/Cardbox_A2",
    "Props/general/FlatBox_A12_56x56x20cm_PR_NVD_01",
    "Props/general/LongBox_A11_11x26x10xcm_PR_NVD_01",
    "Props/skies/Clear/evening_road_01_4k.hdr",
    "ur10",
]


def build_c(out: Path, cache: Path, lock: dict, force: bool = False) -> dict:
    scene_dir = out / "scenes" / "arm"
    (scene_dir / "assets").mkdir(parents=True, exist_ok=True)
    localise_into(scene_dir, KEYS_C, cache, lock, force)
    place_mdl_chain(scene_dir, cache, lock, force)

    N = 12 * 30  # 12 s turntable at 30 fps
    eye = (0.0, 1.9, 3.6)
    tgt = (0.0, 1.0, 0.0)
    pitch, yaw0, _ = look_at_yxz(eye, tgt)

    usda = []
    stage_header(usda, N)
    usda += [
        'def Xform "World"',
        '{',
        '    def PhysicsScene "PhysicsScene"',
        '    {',
        '        uniform token physics:simulationOwner = ""',
        '    }',
        '    def DomeLight "SkyDome"',
        '    {',
        '        asset inputs:texture:file = @./assets/Props/skies/Clear/evening_road_01_4k.hdr@',
        '        float inputs:intensity = 0.9',
        '    }',
        '    def RectLight "Key"',
        '    {',
        '        color3f inputs:color = (1.0, 0.97, 0.92)',
        '        float inputs:intensity = 6.0',
        '        float inputs:width = 2.2',
        '        float inputs:height = 1.2',
        '        float3 xformOp:translate = (2.0, 3.0, 1.8)',
        '        uniform token[] xformOpOrder = ["xformOp:translate"]',
        '    }',
        '    def RectLight "Fill"',
        '    {',
        '        color3f inputs:color = (0.8, 0.88, 1.0)',
        '        float inputs:intensity = 1.2',
        '        float inputs:width = 2',
        '        float inputs:height = 1',
        '        float3 xformOp:translate = (-1.6, 2.2, -1.4)',
        '        uniform token[] xformOpOrder = ["xformOp:translate"]',
        '    }',
        '    def Xform "Ground"',
        '    {',
        '        def Cube "GroundPlane"',
        '        {',
        '            float3[] extent = [(-10, -0.02, -10), (10, 0.02, 10)]',
        '            double size = 20',
        '            color3f[] primvars:displayColor = [(0.1, 0.1, 0.12)]',
        '        }',
        '    }',
        '    def Xform "Table"',
        '    {',
        '        double3 xformOp:translate = (0, 0, 0.4)',
        '        double3 xformOp:scale = (0.01, 0.01, 0.01)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]',
        '        def "TableAsset" (',
        '            prepend references = @./assets/Props/general/SM_MetalStainlessTable_A03_01/SM_MetalStainlessTable_A03_01.usd@',
        '        )',
        '        {',
        '            float3 xformOp:rotateXYZ = (-90, 0, 0)',
        '            uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
        '        }',
        '    }',
        '    def Xform "Robot"',
        '    {',
        '        double3 xformOp:translate = (1.1, 0.034, 0.4)',
        '        float3 xformOp:rotateXYZ = (0, -120, 0)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]',
        '        def Xform "UR10Tilt"',
        '        {',
        '            float3 xformOp:rotateXYZ = (-90, 0, 0)',
        '            uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
        '            def "UR10" (',
        '                prepend references = @./assets/ur10/ur10.usd@',
        '            )',
        '            {',
        '            }',
        '        }',
        '    }',
        # props sit on the table top (y = 0.85): half their own height above
        '    def Xform "PropBox1"',
        '    {',
        '        double3 xformOp:translate = (-0.25, 0.95, 0.15)',
        '        float3 xformOp:rotateXYZ = (0, 15, 0)',
        '        double3 xformOp:scale = (0.01, 0.01, 0.01)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]',
        '        def "BoxAsset" (',
        '            prepend references = @./assets/Props/general/FlatBox_A12_56x56x20cm_PR_NVD_01/FlatBox_A12_56x56x20cm_PR_NVD_01.usd@',
        '        )',
        '        {',
        '            float3 xformOp:rotateXYZ = (-90, 0, 0)',
        '            uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
        '        }',
        '    }',
        '    def Xform "PropBox2"',
        '    {',
        '        double3 xformOp:translate = (0.32, 1.11, -0.12)',
        '        float3 xformOp:rotateXYZ = (0, -25, 0)',
        '        double3 xformOp:scale = (0.01, 0.01, 0.01)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]',
        '        def "BoxAsset" (',
        '            prepend references = @./assets/Props/general/Cardbox_A2/Cardbox_A2.usd@',
        '        )',
        '        {',
        '            float3 xformOp:rotateXYZ = (-90, 0, 0)',
        '            uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
        '        }',
        '    }',
        '    def Xform "PropBox3"',
        '    {',
        '        double3 xformOp:translate = (0.05, 0.90, -0.35)',
        '        float3 xformOp:rotateXYZ = (0, 60, 0)',
        '        double3 xformOp:scale = (0.01, 0.01, 0.01)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]',
        '        def "BoxAsset" (',
        '            prepend references = @./assets/Props/general/LongBox_A11_11x26x10xcm_PR_NVD_01/LongBox_A11_11x26x10xcm_PR_NVD_01.usd@',
        '        )',
        '        {',
        '            float3 xformOp:rotateXYZ = (-90, 0, 0)',
        '            uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
        '        }',
        '    }',
        '    def Xform "Turntable"',
        '    {',
    ]
    # orbit: rotate the whole (camera+light rig omitted; camera only) about Y
    write_rotate_time_samples(
        usda, "float3 xformOp:rotateXYZ",
        [(f, (0.0, f * 360.0 / N, 0.0)) for f in range(0, N + 1, 6)])
    usda += [
        '        uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
        '        def Camera "Camera"',
        '        {',
        '            double3 xformOp:translate = (0, 1.9, 3.6)',
        f'            float3 xformOp:rotateXYZ = ({pitch:.1f}, {yaw0:.1f}, 0)',
        '            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]',
        '            float2 clippingRange = (0.05, 500)',
        '            float focalLength = 35',
        '            float horizontalAperture = 36',
        '            float verticalAperture = 20.25',
        '        }',
        '    }',
        '}',
    ]
    (scene_dir / "scene.usda").write_text("\n".join(usda) + "\n")
    return {"name": "arm", "dir": scene_dir, "usda": scene_dir / "scene.usda"}


# ---------------------------------------------------------------------------
# Scene B — physics knock-over (template + offline bake)
# ---------------------------------------------------------------------------
KEYS_B = [
    "Props/general/Cardbox_A3",
    "Props/general/FlatBox_A12_56x56x20cm_PR_NVD_01",
    "Props/general/LongBox_A11_11x26x10xcm_PR_NVD_01",
]


def build_b_template(out: Path, cache: Path, lock: dict, force: bool = False) -> dict:
    """Author the rigid-body template for the knock-over sim.

    Colliders are Mesh prims with codeless physics schemas (as
    PhysxConvexHullCollisionAPI direct children of each rigid body) — the
    recipe proven to collide correctly in pinned ovphysx.  judge/bake_physics.py
    steps it and bakes time-sampled xforms into scene.usda."""
    scene_dir = out / "scenes" / "physics"
    (scene_dir / "assets").mkdir(parents=True, exist_ok=True)
    localise_into(scene_dir, KEYS_B, cache, lock, force)
    place_mdl_chain(scene_dir, cache, lock, force)

    # Read the cardbox collider geometry from the main SimReady mesh (the
    # *_physics.usd companion only adds the collision schema via sublayers).
    from pxr import Usd, UsdGeom

    st = Usd.Stage.Open(str(scene_dir / "assets" / KEYS_B[0] / "Cardbox_A3.usd"))
    mesh = next(pr for pr in st.Traverse() if pr.IsA(UsdGeom.Mesh))
    gm = UsdGeom.Mesh(mesh)
    pts = gm.GetPointsAttr().Get()
    fvc = gm.GetFaceVertexCountsAttr().Get()
    fvi = gm.GetFaceVertexIndicesAttr().Get()
    if None in (pts, fvc, fvi):
        raise RuntimeError(f"{KEYS_B[0]} has no mesh points")
    # SimReady Z-up cm -> world Y-up m: scale 0.01, then rotate -90 about X.
    # (x, y, z) cm  ->  (x*0.01, z*0.01, -y*0.01)
    pts_y = [(p[0] * 0.01, p[2] * 0.01, -p[1] * 0.01) for p in pts]
    ext = ([min(p[i] for p in pts_y) for i in range(3)],
           [max(p[i] for p in pts_y) for i in range(3)])
    fmt_p = lambda pp: ", ".join(
        f"({a:.6f}, {b:.6f}, {c:.6f})" for a, b, c in pp)
    fmt_i = lambda v: ", ".join(map(str, v))

    N = 6 * 30  # 6 s bake at 30 fps (physics stepped at 240 Hz)

    usda = []
    stage_header(usda, N)
    usda += [
        'def Xform "World"',
        '{',
        '    def PhysicsScene "PhysicsScene"',
        '    {',
        '        vector3f physics:gravityDirection = (0, -1, 0)',
        '        float physics:gravityMagnitude = 9.81',
        '    }',
        '    def Material "PropMaterial"',
        '    {',
        '        float physics:staticFriction = 0.52',
        '        float physics:dynamicFriction = 0.40',
        '        float physics:restitution = 0.08',
        '    }',
        '    def Cube "Ground" (',
        '        prepend apiSchemas = ["PhysicsCollisionAPI", "MaterialBindingAPI"]',
        '    )',
        '    {',
        '        rel material:binding:physics = </World/PropMaterial>',
        '        double size = 1',
        '        float3[] extent = [(-0.5, -0.5, -0.5), (0.5, 0.5, 0.5)]',
        '        double3 xformOp:scale = (100, 1, 100)',
        '        double3 xformOp:translate = (0, -0.5, 0)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]',
        '    }',
        '    def Xform "Boxes"',
        '    {',
    ]
    # Three cardboxes, slightly offset and tilted so the sim knocks them over.
    import math
    # Cardbox footprint: cm asset 69.9 x 50.9 x 52.1 cm.  To get a *visible
    # knock-over* (the point of Scene B) the hero box starts on its end and
    # topples onto its side; a second box tips into it.  Orientations are
    # about the world-up Y; each box also gets a small lateral/rotational
    # kick so it decisively tips rather than settling upright.
    #   Box1: standing tall on its short end, falls flat (hero shot).
    #   Box2: tipped onto an edge, angular velocity about Y to topple.
    #   Box3: a flat box knocked loose by Box2.
    # Convex-hull collider dims (meters) after Z->Y tilt:
    #   depth (x) 0.69, width (z) 0.51, height (y) 0.52
    body_specs = [
        # name, pos, quat(yaw about world Y), velocity, angular velocity
        ("Box1", (0.0, 0.42, 0.0), 90.0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ("Box2", (0.55, 0.26, 0.10), 12.0, (-0.25, 0.0, 0.0), (0.0, 0.8, 0.0)),
        ("Box3", (-0.45, 0.11, -0.18), -30.0, (0.18, 0.0, 0.0), (0.0, -0.6, 0.0)),
    ]
    for name, (bx, by, bz), ang, vel, angvel in body_specs:
        a = math.radians(ang)
        # rotate about Y (yaw) as a quat (w, x, y, z)
        quat = (math.cos(a / 2), 0.0, math.sin(a / 2), 0.0)
        usda += [
            f'        def Xform "{name}" (',
            '            prepend apiSchemas = ["PhysicsRigidBodyAPI", "PhysicsMassAPI"]',
            '        )',
            '        {',
            f'            double3 xformOp:translate = ({bx}, {by}, {bz})',
            f'            quatd xformOp:orient = ({quat[0]:.6f}, {quat[1]:.6f}, {quat[2]:.6f}, {quat[3]:.6f})',
            '            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient"]',
            '            float physics:mass = 2.0',
            f'            vector3f physics:velocity = ({vel[0]}, {vel[1]}, {vel[2]})',
            f'            vector3f physics:angularVelocity = ({angvel[0]}, {angvel[1]}, {angvel[2]})',
            '            def Mesh "Collider" (',
            '                prepend apiSchemas = ["PhysicsCollisionAPI", "PhysicsMeshCollisionAPI", "PhysxConvexHullCollisionAPI", "MaterialBindingAPI"]',
            '            )',
            '            {',
            '                rel material:binding:physics = </World/PropMaterial>',
            '                float3[] extent = ['
            f'({ext[0][0]:.4f}, {ext[0][1]:.4f}, {ext[0][2]:.4f}), '
            f'({ext[1][0]:.4f}, {ext[1][1]:.4f}, {ext[1][2]:.4f})]',
            '                token physics:approximation = "convexHull"',
            f'                int[] faceVertexCounts = [{fmt_i(fvc)}]',
            f'                point3f[] points = [{fmt_p(pts_y)}]',
            f'                int[] faceVertexIndices = [{fmt_i(fvi)}]',
            '            }',
            '            def Xform "Visual"',
            '            {',
            '                double3 xformOp:scale = (0.01, 0.01, 0.01)',
            '                uniform token[] xformOpOrder = ["xformOp:scale"]',
            '                def "Cardbox" (',
            '                    prepend references = @./assets/Props/general/Cardbox_A3/Cardbox_A3.usd@',
            '                )',
            '                {',
            '                    float3 xformOp:rotateXYZ = (-90, 0, 0)',
            '                    uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]',
            '                }',
            '            }',
            '        }',
        ]
    eye = (1.8, 1.6, 3.4)
    tgt = (0.05, 0.45, 0.0)
    cpitch, cyaw, _ = look_at_yxz(eye, tgt)
    usda += [
        '    }',
        '    def Xform "CameraXform"',
        '    {',
        f'        double3 xformOp:translate = ({eye[0]}, {eye[1]}, {eye[2]})',
        f'        float3 xformOp:rotateXYZ = ({cpitch:.1f}, {cyaw:.1f}, 0)',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]',
        '        def Camera "Camera"',
        '        {',
        '            float2 clippingRange = (0.05, 500)',
        '            float focalLength = 24',
        '            float horizontalAperture = 36',
        '            float verticalAperture = 20.25',
        '        }',
        '    }',
        '}',
    ]
    (scene_dir / "template.usda").write_text("\n".join(usda) + "\n")
    return {"name": "physics", "dir": scene_dir,
            "usda": scene_dir / "template.usda", "baked": scene_dir / "scene.usda"}


# ---------------------------------------------------------------------------
def _bake(builder_result: dict):
    """Run judge/bake_physics.py with the pinned venv if both exist."""
    venv = Path("/home/user/.venvs/omniverse-scenes/bin/python")
    bake = HERE.parent / "judge" / "bake_physics.py"
    if not venv.exists() or not bake.exists():
        print("[build]   (no pinned venv / bake_physics.py — template only)")
        return
    import subprocess
    print("[build]   baking Scene B …")
    subprocess.run([str(venv), str(bake),
                    str(builder_result["usda"]),
                    str(builder_result["baked"])], check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--scene", default=None, choices=["a", "b", "c"])
    ap.add_argument("--no-bake", action="store_true",
                    help="skip the Scene B physics bake (template only)")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    cache = out / CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    lock = load_lock(out)

    results = []
    for name, fn in (("a", build_a), ("c", build_c), ("b", build_b_template)):
        if args.scene and name != args.scene:
            continue
        print(f"[build] scene {name} …")
        r = fn(out, cache, lock, force=args.force)
        results.append(r)
        print(f"[build]   wrote {r['usda']}")

    if not args.scene or args.scene == "b":
        if args.no_bake or not results:
            pass
        elif any(r["name"] == "physics" for r in results):
            _bake(next(r for r in results if r["name"] == "physics"))

    print(f"[build] done ({len(results)} scenes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())