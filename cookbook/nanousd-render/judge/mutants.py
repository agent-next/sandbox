#!/usr/bin/env python3
"""Generate the known-bad mutants for the nanousd-render self-test.

Each mutant is a single, scriptable edit of the known-good example
(../examples/good/scene.usda) aimed at one gate, so the self-test proves the
judge can fail for the reason the SPEC says it should. No randomness: the
same edits are produced every run.

    python3 mutants.py --out <dir>            # write <dir>/<name>.usda
and prints one line per mutant: "<mutant> <gate it must fail> <path>".

Mutants and the gate each must trip:

  out_of_frame       translate one mesh far off-screen     -> G4 offscreen
  recolored          one mesh's displayColor -> near copy
                     of a neighbour's                        -> G1 colors_close
  camera_away        camera looks the wrong way             -> G4 (and G3)
  malformed          truncate the file mid-attribute        -> G1 nanousd.open
  skelroot_divergence one mesh typed SkelRoot (a schema
                     usd-core reads and nanousd drops)      -> G1/G2
  missing_light      the light prim is deleted              -> G1 no_light
  too_few_points     one mesh down to 4 points              -> G1 points
  aperture_broken    verticalAperture 20 (ratio 1.8)        -> G1 aperture_ratio
  composite_arc      a references = line                   -> G1 forbidden_arc
  smuggled_arc       an inherits=[</Nope>] arc formatted
                     without the spaces the old text scan
                     matched (the forge-a-pass cheat; now
                     the parser reports it)              -> G1 forbidden_arc
  rects_overlap      the Cube slid right until its projected
                     rectangle overlaps the Wedge's (every
                     structural rule still holds)          -> G4 rects_overlap
"""

from __future__ import annotations

import argparse
import os
import re
import sys

GOOD = None  # set in main() from --good


def read_good() -> str:
    with open(GOOD, "r", encoding="utf-8") as fh:
        return fh.read()


def sub_once(text: str, old: str, new: str, what: str) -> str:
    """Replace `old` exactly once; guard against silent drift in the good
    example making a mutant a no-op (which would fail the self-test)."""
    if text.count(old) != 1:
        raise SystemExit(
            f"mutants: {what}: pattern appears {text.count(old)} times, "
            f"expected exactly 1 -- update mutants.py against the example")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------- mutants

def m_out_of_frame(t: str) -> str:
    # Push the tetrahedron way past the right frustum edge.
    return sub_once(
        t, 'float3 xformOp:translate = (4.2, 0.55, 0)',
        'float3 xformOp:translate = (60.0, 0.55, 0)', "out_of_frame")


def m_recolored(t: str) -> str:
    # Cube becomes a near-duplicate of the cylinder's blue.
    return sub_once(
        t, 'color3f[] primvars:displayColor = [(0.85, 0.15, 0.15)]',
        'color3f[] primvars:displayColor = [(0.2, 0.35, 0.98)]',
        "recolored")


def m_camera_away(t: str) -> str:
    # Aim the camera at the ceiling instead of the mesh row.
    return sub_once(
        t, 'float3 xformOp:rotateXYZ = (-18, 0, 0)',
        'float3 xformOp:rotateXYZ = (85, 0, 0)', "camera_away")


def m_malformed(t: str) -> str:
    # Cut the file inside the camera's aperture attribute: unparseable value.
    return t[: t.index("float horizontalAperture")] + "float horizontalAperture = (\n"


def m_skelroot_divergence(t: str) -> str:
    # A plugin schema one reader knows and the other drops: usd-core sees the
    # prim under /World, nanousd does not, so the two readers diverge.
    return sub_once(
        t, 'def Mesh "Tetra"', 'def SkelRoot "Tetra"', "skelroot_divergence")


def m_missing_light(t: str) -> str:
    # Delete the whole DistantLight prim.
    i = t.index("    def DistantLight \"Sun\"")
    j = t.index("\n    }\n", i) + len("\n    }\n")
    return sub_once(t, t[i:j], "", "missing_light")


def m_too_few_points(t: str) -> str:
    # Tetrahedron down to 3 points (and the matching degenerate faces).
    old = t[t.index('def Mesh "Tetra"'):]
    start = old.index("point3f[] points =") + len("point3f[] points =")
    end = old.index("]", start) + 1
    pts = old[start:end]
    newpts = ("[(0.55, 0.55, 0.55), (-0.55, -0.55, 0.55), "
              "(-0.55, 0.55, -0.55)]")
    return sub_once(t, pts, newpts, "too_few_points")


def m_aperture_broken(t: str) -> str:
    # 16:9 ratio instead of 4:3.
    return sub_once(
        t, "float verticalAperture = 27", "float verticalAperture = 20.25",
        "aperture_broken")


def m_composite_arc(t: str) -> str:
    return sub_once(
        t, "defaultPrim = \"World\"",
        "defaultPrim = \"World\"\n    references = </World/Root>",
        "composite_arc")


def m_rects_overlap(t: str) -> str:
    # Slide the Cube right until its projected rectangle overlaps the
    # Wedge's by far more than 10% of the smaller area. Every structural
    # rule still holds (both readers agree, colors stay pairwise far
    # apart, the mesh is fully on screen), so only G4's screen-separation
    # layout rule -- re-measured by the judge's own projection -- catches
    # it (and the inner-rect color fit, whose samples now straddle two
    # meshes).
    return sub_once(
        t, 'float3 xformOp:translate = (-4.2, 0.6, 0)',
        'float3 xformOp:translate = (-2.3, 0.6, 0)', "rects_overlap")


def m_smuggled_arc(t: str) -> str:
    # The cheat attempt: a composition arc formatted WITHOUT the spaces the
    # old text scan matched ("inherits ="), so the scan saw nothing. If both
    # readers tolerate the arc, the scene would otherwise grade PASS -- a
    # forged verdict. The judge now takes arcs from the parser (and from a
    # whitespace-proof text net), so the smuggling is the thing that fails.
    return sub_once(
        t, 'uniform token[] xformOpOrder = ["xformOp:translate"]\n'
        '    }\n\n    def Mesh "Wedge"',
        'uniform token[] xformOpOrder = ["xformOp:translate"]\n'
        '        inherits=[</Nope>]\n'
        '    }\n\n    def Mesh "Wedge"',
        "smuggled_arc")


MUTANTS = [
    ("out_of_frame", "G4", m_out_of_frame),
    ("recolored", "G1", m_recolored),
    ("camera_away", "G3", m_camera_away),
    ("malformed", "G1", m_malformed),
    ("skelroot_divergence", "G2", m_skelroot_divergence),
    ("missing_light", "G1", m_missing_light),
    ("too_few_points", "G1", m_too_few_points),
    ("aperture_broken", "G1", m_aperture_broken),
    ("composite_arc", "G1", m_composite_arc),
    ("smuggled_arc", "G1", m_smuggled_arc),
    ("rects_overlap", "G4", m_rects_overlap),
]


def main() -> int:
    global GOOD
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--good", default=None)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    GOOD = os.path.abspath(args.good) if args.good else os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        os.pardir, "examples", "good", "scene.usda")

    for name, gate, fn in MUTANTS:
        before = read_good()
        after = fn(before)
        if after == before:
            print(f"mutants: {name}: edit was a no-op", file=sys.stderr)
            return 1
        path = os.path.join(args.out, f"{name}.usda")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(after)
        print(f"{name} {gate} {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
