"""mutants.py — scripted single-edit known-bad artifacts for the self-test.

Usage (run with the judge venv python, which has usd-core):
    python -I judge/mutants.py <good-artifact-dir> <out-dir>

Writes one directory per mutant under <out-dir>, each a single deliberate
edit of the known-good artifact. Each mutant names the gate that should
kill it; selftest.sh asserts exactly that.

Text edits (units, up-axis, empty stage, missing file, cross-part copy,
garbage convert.sh) are done with plain string/file operations so they
stay readable one-line diffs. Geometry edits (axis swap, dropped mesh,
decimated mesh) load the stage with usd-core, edit one thing, and save.
"""

import os
import re
import shutil
import sys

GARBAGE_STEP = (
    "ISO-10303-21;\n"
    "HEADER;\n"
    "FILE_DESCRIPTION(('GARBAGE — NOT A REAL STEP FILE'),'2;1');\n"
    "ENDSEC;\n"
    "DATA;\n"
    "ENDSEC;\n"
    "END-ISO-10303-21;\n"
)

MUTANTS = [
    # (name, kind, target, killed_by, description)
    ("wrong_units", "text", "Servo_Futaba_S3003_v6_step.usda",
     "stage_meta + bbox_match",
     "metersPerUnit 0.001 -> 1: mm scene read as metres"),
    ("up_axis_y", "text", "Servo_Futaba_S3003_v6_step.usda",
     "stage_meta",
     'upAxis "Z" -> "Y"'),
    ("axis_swap", "geom", "ShockTowerFront_stp.usda",
     "bbox_match",
     "Y/Z point coordinates swapped on every mesh (geometry, not just "
     "metadata)"),
    ("dropped_mesh", "geom", "ShockTowerFront_stp.usda",
     "bbox_match + area_match",
     "largest Mesh prim removed"),
    ("decimated_mesh", "geom", "ShockTowerFront_stp.usda",
     "area_match",
     "half the faces of the largest mesh dropped"),
    ("empty_stage", "text", "ShockTowerFront_stp.usda",
     "geometry_counts",
     "valid stage, no meshes at all"),
    ("garbage_convert", "convert", "convert.sh",
     "conversion_script",
     "convert.sh feeds a garbage STEP to the converter (exit 1)"),
    ("missing_part", "fs", "ShockTowerFront_stp.usda",
     "file_set",
     "one part file deleted"),
    ("cross_part_copy", "fs", "ShockTowerFront_stp.usda",
     "file_set",
     "one part's output replaced by a copy of another part's"),
]


def edit_text(path, old, new):
    with open(path) as f:
        s = f.read()
    assert old in s, f"{path}: pattern {old!r} not found"
    with open(path, "w") as f:
        f.write(s.replace(old, new, 1))


def geom_edit(path, fn):
    from pxr import Usd, UsdGeom
    stage = Usd.Stage.Open(path)
    assert stage, f"cannot open {path}"
    fn(stage, UsdGeom)
    stage.Save()


def swap_yz(stage, UsdGeom):
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            attr = prim.GetAttribute("points")
            pts = attr.Get()
            attr.Set([(p[0], p[2], p[1]) for p in pts])
            # the authored extent hint feeds the judge's BBoxCache, so it
            # must be swapped too (it stays consistent with the points)
            ext = prim.GetAttribute("extent")
            if ext and ext.Get():
                ext.Set([(e[0], e[2], e[1]) for e in ext.Get()])


def drop_largest_mesh(stage, UsdGeom):
    meshes = [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    biggest = max(meshes, key=lambda p: len(
        UsdGeom.Mesh(p).GetPointsAttr().Get() or []))
    stage.RemovePrim(biggest.GetPath())


def decimate_largest_mesh(stage, UsdGeom):
    meshes = [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    biggest = max(meshes, key=lambda p: len(
        UsdGeom.Mesh(p).GetPointsAttr().Get() or []))
    mesh = UsdGeom.Mesh(biggest)
    counts = list(mesh.GetFaceVertexCountsAttr().Get())
    idx = list(mesh.GetFaceVertexIndicesAttr().Get())
    keep = len(counts) // 2
    mesh.GetFaceVertexCountsAttr().Set(counts[:keep])
    mesh.GetFaceVertexIndicesAttr().Set(idx[:sum(counts[:keep])])


def make_mutant(good, out, name, kind, target, killed_by, desc):
    dst = os.path.join(out, name)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(good, dst)
    t = os.path.join(dst, target)
    if kind == "text":
        if name == "wrong_units":
            edit_text(t, "metersPerUnit = 0.001", "metersPerUnit = 1")
        elif name == "up_axis_y":
            edit_text(t, 'upAxis = "Z"', 'upAxis = "Y"')
        elif name == "empty_stage":
            with open(t, "w") as f:
                f.write(
                    '#usda 1.0\n(\n    defaultPrim = "root"\n'
                    '    metersPerUnit = 0.001\n    upAxis = "Z"\n)\n\n'
                    'def Xform "root"\n{\n}\n')
    elif kind == "geom":
        os.chmod(t, 0o644)
        if name == "axis_swap":
            geom_edit(t, swap_yz)
        elif name == "dropped_mesh":
            geom_edit(t, drop_largest_mesh)
        elif name == "decimated_mesh":
            geom_edit(t, decimate_largest_mesh)
        os.chmod(t, 0o444)
    elif kind == "fs":
        if name == "missing_part":
            os.remove(t)
        elif name == "cross_part_copy":
            shutil.copy(os.path.join(dst,
                                     "Servo_Futaba_S3003_v6_step.usda"), t)
    elif kind == "convert":
        if name == "garbage_convert":
            with open(t) as f:
                s = f.read()
            old = ('convert_one "sources/ShockTowerFront/_ShockTowerFront.stp" '
                   '"ShockTowerFront_stp"')
            new = ('printf \'%s\' "' + GARBAGE_STEP.replace('"', '\\"') +
                   '" > garbage.step\n'
                   'convert_one "garbage.step" "ShockTowerFront_stp"')
            assert old in s, "convert.sh: expected line not found"
            with open(t, "w") as f:
                f.write(s.replace(old, new, 1))
    print(f"[mutant] {name:<16} killed_by={killed_by}: {desc}")


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: mutants.py <good-artifact-dir> <out-dir>")
    good, out = os.path.abspath(sys.argv[1]), sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for m in MUTANTS:
        make_mutant(good, out, *m)
    print(f"[mutant] {len(MUTANTS)} mutants written to {out}")


if __name__ == "__main__":
    main()
