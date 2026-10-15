#!/usr/bin/env python3
"""Generate known-bad artifacts as single-edit mutants of the good ones.

Each mutant is ONE scripted edit of a good input (SPEC.md "Known-bad"):
 - a one-number edit in a .scad source (the STL/DXF is re-exported with
   the pinned OpenSCAD, exactly as the agent flow would),
 - a one-facet edit of the shipped STL (flipped winding / dropped facet),
 - a truncation of the shipped STEP.

Writes examples/bad/<mutant>/ (gitignored); selftest.sh grades them all.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parent.parent
GOOD = ROOT / "examples" / "good"
BAD = ROOT / "examples" / "bad"
OPENSCAD = "openscad"

MUTANTS = []


def mutant(name, case, files=()):
    def wrap(fn):
        MUTANTS.append((name, case, files, fn))
        return fn
    return wrap


def edit_text(path, old, new, count=1):
    text = path.read_text()
    assert old in text, f"{path}: pattern {old!r} not found"
    path.write_text(text.replace(old, new, count))


def reexport_stl(dir_):
    subprocess.run(
        [OPENSCAD, "-o", str(dir_ / "part.stl"), str(dir_ / "part.scad")],
        check=True, capture_output=True)


def reexport_dxf(dir_):
    subprocess.run(
        [OPENSCAD, "-o", str(dir_ / "drawing.dxf"),
         str(dir_ / "drawing.scad")],
        check=True, capture_output=True)


# ------------------------------------------------------------- scad edits
@mutant("bushing_bore_d12_to_15", "bushing", ["part.scad", "part.stl"])
def _(d):
    edit_text(d / "part.scad", "bore_d   = 12;", "bore_d   = 15;")
    reexport_stl(d)


@mutant("bushing_inch_scale", "bushing", ["part.scad", "part.stl"])
def _(d):
    edit_text(d / "part.scad", "$fn = 128;",
              "$fn = 128;\nscale([25.4, 25.4, 25.4]) {", 1)
    (d / "part.scad").write_text(
        (d / "part.scad").read_text() + "}\n")
    reexport_stl(d)


@mutant("bushing_missing_flange", "bushing", ["part.scad", "part.stl"])
def _(d):
    edit_text(d / "part.scad",
              "        translate([0, 0, body_h]) cylinder(h = flange_h, d = flange_d);\n",
              "")
    reexport_stl(d)


@mutant("plate_bolt_d6_to_7", "plate", ["part.scad", "part.stl"])
def _(d):
    edit_text(d / "part.scad", "bolt_d  = 6;", "bolt_d  = 7;")
    reexport_stl(d)


@mutant("plate_bolt_circle_r24_to_27", "plate", ["part.scad", "part.stl"])
def _(d):
    # tangential drift: holes move out until they break through the rim
    edit_text(d / "part.scad", "bc_r    = 24;", "bc_r    = 27;")
    reexport_stl(d)


@mutant("plate_hole_count_6_to_5", "plate",
        ["drawing.scad", "drawing.dxf"])
def _(d):
    edit_text(d / "drawing.scad", "n_bolts = 6;", "n_bolts = 5;")
    reexport_dxf(d)


@mutant("bracket_missing_fillet", "bracket", ["part.scad", "part.stl"])
def _(d):
    edit_text(d / "part.scad", "        concave_fillet();\n", "")
    reexport_stl(d)


@mutant("bracket_fillet_r6_to_3", "bracket", ["part.scad", "part.stl"])
def _(d):
    edit_text(d / "part.scad", "fillet_r  = 6;", "fillet_r  = 3;")
    reexport_stl(d)


# ------------------------------------------------------------- STL edits
@mutant("bushing_flipped_facet", "bushing", ["part.stl"])
def _(d):
    m = trimesh.load(str(d / "part.stl"))
    m.faces[7] = m.faces[7][::-1]  # one triangle wound backwards
    m.export(str(d / "part.stl"))


@mutant("bracket_nonwatertight", "bracket", ["part.stl"])
def _(d):
    m = trimesh.load(str(d / "part.stl"))
    keep = np.ones(len(m.faces), dtype=bool)
    keep[:1] = False  # drop one triangle -> hole in the mesh
    m.update_faces(keep)
    m.export(str(d / "part.stl"))


# ------------------------------------------------------------ STEP edit
@mutant("plate_corrupt_step", "plate", ["part.step"])
def _(d):
    data = (d / "part.step").read_text()
    (d / "part.step").write_text(data[: int(len(data) * 0.8)])


def main():
    if BAD.exists():
        shutil.rmtree(BAD)
    BAD.mkdir(parents=True)
    for name, case, files, fn in MUTANTS:
        target = BAD / name
        target.mkdir()
        for f in (GOOD / case).iterdir():
            if f.name in ("part.scad", "part.stl", "part.step",
                          "drawing.scad", "drawing.dxf", "case.json"):
                shutil.copy2(f, target / f.name)
        fn(target)
        print(f"[mutants] {name} <- {case} ({', '.join(files)})")
    print(f"[mutants] {len(MUTANTS)} mutants in {BAD}")


if __name__ == "__main__":
    main()
