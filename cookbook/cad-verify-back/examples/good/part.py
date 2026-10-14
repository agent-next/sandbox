#!/usr/bin/env python3
"""Good example: industrial adapter plate built with CadQuery 2.7.0.

Reads the customer spec JSON and exports, next to itself:
  part.step  - STEP AP214 solid
  part.stl   - tessellated mesh (binary STL)
  part.dxf   - 2-D drawing of the top face: outline + every hole as a CIRCLE

Usage:
    python3 part.py [spec.json]

The spec defaults to the copy in this directory (the canonical customer
spec the judge grades against is judge/spec.json, same values). Only the
three exported files are graded; this script is never run by the judge.

Third-party sources:
  - CadQuery 2.7.0, Apache-2.0, https://github.com/CadQuery/cadquery
    (API used: Workplane.box/circle/pushPoints/cut/combinedVersion, exporters)
  - ezdxf 1.4.4, MIT, https://github.com/mozman/ezdxf
"""
import json
import math
import os
import sys

import cadquery as cq
import ezdxf


def load_spec(path):
    with open(path) as f:
        return json.load(f)


def build(spec):
    """Plate centred on origin, bottom face at Z=0, boss up (+Z)."""
    L = spec["plate_l"]
    W = spec["plate_w"]
    T = spec["plate_t"]
    bore = spec["bore_d"]
    boss_od = spec["boss_od"]
    boss_h = spec["boss_h"]
    n = spec["bolt_n"]
    d = spec["bolt_d"]
    pcd = spec["pcd"]

    # plate body: centred on origin in X/Y, from Z=0 up
    plate = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))

    # raised boss on the top face, concentric with the bore
    plate = plate.faces(">Z").workplane().circle(boss_od / 2.0).extrude(boss_h)

    # central through-bore
    plate = plate.faces(">Z").workplane().circle(bore / 2.0).cutThruAll()

    # bolt holes, evenly spaced on the PCD starting at 0 deg (+X)
    pts = [
        (pcd / 2.0 * math.cos(2.0 * math.pi * i / n),
         pcd / 2.0 * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    ]
    plate = (
        plate.faces(">Z").workplane()
        .pushPoints(pts)
        .circle(d / 2.0)
        .cutThruAll()
    )
    return plate


def export(part, out_dir):
    step = os.path.join(out_dir, "part.step")
    stl = os.path.join(out_dir, "part.stl")
    dxf = os.path.join(out_dir, "part.dxf")
    cq.exporters.export(part, step)
    cq.exporters.export(
        part, stl,
        tolerance=0.01, angularTolerance=0.05,
        exportType=cq.exporters.ExportTypes.STL,
    )
    return step, stl, dxf


def export_dxf(spec, dxf_path):
    """2-D top view: outline rectangle + CIRCLE per hole, on layer 0."""
    L = spec["plate_l"]
    W = spec["plate_w"]
    bore = spec["bore_d"]
    boss_od = spec["boss_od"]
    n = spec["bolt_n"]
    d = spec["bolt_d"]
    pcd = spec["pcd"]

    doc = ezdxf.new("R2010", setup=False)
    msp = doc.modelspace()
    # outline, corners (±L/2, ±W/2), as a closed LWPOLYLINE
    hL, hW = L / 2.0, W / 2.0
    msp.add_lwpolyline(
        [(hL, hW), (-hL, hW), (-hL, -hW), (hL, -hW)],
        close=True,
    )
    # every hole as a CIRCLE at its true position
    msp.add_circle((0.0, 0.0), bore / 2.0)
    msp.add_circle((0.0, 0.0), boss_od / 2.0)
    for i in range(n):
        a = 2.0 * math.pi * i / n
        msp.add_circle((pcd / 2.0 * math.cos(a), pcd / 2.0 * math.sin(a)), d / 2.0)
    doc.saveas(dxf_path)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    spec_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "spec.json")
    spec = load_spec(spec_path)
    part = build(spec)
    step, stl, dxf = export(part, here)
    export_dxf(spec, dxf)
    v = part.val().Volume()
    print(f"part.py: exported part.step, part.stl, part.dxf (volume {v:.2f} mm^3)")


if __name__ == "__main__":
    main()
