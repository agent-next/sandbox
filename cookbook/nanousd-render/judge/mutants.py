#!/usr/bin/env python3
"""Generate the known-bad mutants for the nanousd-render self-test.

Each mutant is a single, scriptable edit of the known-good example
(../examples/good/scene.usda) aimed at one gate, so the self-test proves the
judge can fail for the reason the SPEC says it should. No randomness: the
same edits are produced every run.

    python3 mutants.py --out <dir>            # write <dir>/<name>.usda
and prints one line per mutant: "<mutant> <gate it must fail> <path>".

Mutants and the gate each must trip:

  out_of_frame       one mesh translated far off-screen    -> G4
  half_offscreen     one mesh translated so only ~36% of its
                     projected rectangle is inside the frame
                     (area and every structural rule still pass)
                                                             -> G4 offscreen
  recolored          one mesh's displayColor -> near copy
                     of a neighbour's                        -> G1 colors_close
  camera_away        camera looks the wrong way             -> G3
  malformed          truncate the file mid-attribute        -> G1 nanousd.open
  skelroot_schema    one mesh typed SkelRoot (a forbidden schema
                     prefix; both readers keep the prim, so it
                     is the schema rule that fires, not G2)  -> G1
  missing_light      the light prim is deleted              -> G1 no_light
  too_few_points     one mesh down to 3 points              -> G1 points
  aperture_broken    verticalAperture 20.25 (ratio 1.78)    -> G1 aperture_ratio
  composite_arc      a references = line                   -> G1 forbidden_arc
  smuggled_arc       an inherits=[</Nope>] arc formatted
                     without the spaces the old text scan
                     matched (the forge-a-pass cheat; now
                     the parser reports it)              -> G1 forbidden_arc
  rects_overlap      the Cube slid right until its projected
                     rectangle overlaps the Cylinder's (every
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
    # Push the tetrahedron way past the right frustum edge (0% of its
    # projected rectangle is on screen).
    return sub_once(
        t, 'float3 xformOp:translate = (4.2, 0.55, 0)',
        'float3 xformOp:translate = (60.0, 0.55, 0)', "out_of_frame")


def m_half_offscreen(t: str) -> str:
    # Slide the tetrahedron right so only ~36% of its projected rectangle
    # is inside the frame: the area rule and every structural rule still
    # pass, and what fails is G4's on-screen rule specifically.
    return sub_once(
        t, 'float3 xformOp:translate = (4.2, 0.55, 0)',
        'float3 xformOp:translate = (5.7, 0.55, 0)', "half_offscreen")


def m_recolored(t: str) -> str:
    # Cube becomes a near-duplicate of the cylinder's blue.
    return sub_once(
        t, 'color3f[] primvars:displayColor = [(0.85, 0.15, 0.15)]',
        'color3f[] primvars:displayColor = [(0.2, 0.35, 0.98)]',
        "recolored")


def m_camera_away(t: str) -> str:
    # Aim the camera at the ceiling instead of the mesh row.
    return sub_once(
        t, 'float3 xformOp:rotateXYZ = (-14, 0, 0)',
        'float3 xformOp:rotateXYZ = (85, 0, 0)', "camera_away")


def m_malformed(t: str) -> str:
    # Cut the file inside the camera's aperture attribute: unparseable value.
    return t[: t.index("float horizontalAperture")] + "float horizontalAperture = (\n"


def m_skelroot_schema(t: str) -> str:
    # A plugin schema type (SkelRoot) that is on G1's forbidden-prefix list:
    # both readers keep the prim and agree, so G2 still passes; the parsed
    # type name is reported as a forbidden schema and fails G1.
    return sub_once(
        t, 'def Mesh "Tetra"', 'def SkelRoot "Tetra"', "skelroot_schema")


def m_missing_light(t: str) -> str:
    # Delete the whole DistantLight prim.
    i = t.index("    def DistantLight \"Sun\"")
    j = t.index("\n    }\n", i) + len("\n    }\n")
    return sub_once(t, t[i:j], "", "missing_light")


def m_too_few_points(t: str) -> str:
    # Tetrahedron down to 3 points (the faces keep indexing the old
    # vertices; G1's point-count rule fires before anything renders).
    old = t[t.index('def Mesh "Tetra"'):]
    start = old.index("point3f[] points =") + len("point3f[] points =")
    end = old.index("]", start) + 1
    pts = old[start:end]
    newpts = ("[(0.55, 0.55, 0.55), (-0.55, -0.55, 0.55), "
              "(-0.55, 0.55, -0.55)]")
    return sub_once(t, pts, newpts, "too_few_points")


def m_aperture_broken(t: str) -> str:
    # 16:9 ratio (20.25) instead of 4:3 (27): the judge renders 640x480.
    return sub_once(
        t, "float verticalAperture = 27", "float verticalAperture = 20.25",
        "aperture_broken")


def m_composite_arc(t: str) -> str:
    # A references arc, spaced the way the text scan catches. Placed in
    # the prim header (prim metadata must precede properties in USDA) so
    # the file still parses and the kill comes from the arc gates, not
    # from a reader error.
    return sub_once(
        t, 'def Mesh "Wedge"\n    {',
        'def Mesh "Wedge" (\n        references = </World/Cube>\n    )\n    {',
        "composite_arc")


def m_rects_overlap(t: str) -> str:
    # Slide the Cube right until its projected rectangle overlaps the
    # Cylinder's by ~31% of the smaller area (cube -> x [248,309] vs
    # cylinder x [291,349] at the 640x480 grade frame). Every structural
    # rule still holds (both readers agree, colors stay pairwise far
    # apart, the mesh is fully on screen), so only G4's screen-separation
    # layout rule -- re-measured by the judge's own projection -- catches
    # it (and the inner-rect color fit, whose samples now straddle two
    # meshes).
    return sub_once(
        t, 'float3 xformOp:translate = (-4.2, 0.6, 0)',
        'float3 xformOp:translate = (-0.7, 0.6, 0)', "rects_overlap")


def m_smuggled_arc(t: str) -> str:
    # The cheat attempt: a composition arc formatted WITHOUT the spaces the
    # old text scan matched ("inherits ="), so the scan saw nothing while
    # the file still parsed and both readers composed it quietly -- the
    # scene would have graded PASS: a forged verdict. The judge now takes
    # arcs from the parser (HasAuthoredInherits & co., which formatting
    # cannot hide from) plus a whitespace-proof text net, so the smuggling
    # itself is what fails.
    return sub_once(
        t, 'def Mesh "Cube"\n    {',
        'def Mesh "Cube" (\n        inherits=[</Nope>]\n    )\n    {',
        "smuggled_arc")


MUTANTS = [
    ("out_of_frame", "G4", m_out_of_frame),
    ("half_offscreen", "G4", m_half_offscreen),
    ("recolored", "G1", m_recolored),
    ("camera_away", "G3", m_camera_away),
    ("malformed", "G1", m_malformed),
    ("skelroot_schema", "G1", m_skelroot_schema),
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
