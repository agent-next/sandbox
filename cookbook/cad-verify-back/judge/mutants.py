#!/usr/bin/env python3
"""Generate the known-bad mutants of the good example for the self-test.

Each mutant is a single conceptual edit of the delivered artifact set
(part.step / part.stl / part.dxf), produced by re-running a mutated
part.py or by post-processing the good exports:

  wrong_bolt_count   - one bolt hole missing from the solid (and DXF kept
                       consistent, so only STEP/STL gates can catch it)
  wrong_pcd          - bolt holes on the wrong pitch-circle diameter
  bore_off           - central bore 0.5 mm oversize
  boss_missing       - no raised boss (flat plate); volume + bbox + dxf fail
  scale_inch_mm      - whole part scaled x25.4 (inch/mm confusion)
  stl_not_watertight - good solid, but one triangle dropped from the STL
  dxf_missing_hole   - good solid, one circle missing from the DXF
  edge_violation     - bolt circle moved so a hole violates min_edge

Usage:
    python3 mutants.py <good_dir> <out_dir>

Writes <out_dir>/<name>/{part.py,spec.json,part.step,part.stl,part.dxf}.
"""
import json
import math
import os
import shutil
import struct
import sys

MUTANTS = [
    "wrong_bolt_count", "wrong_pcd", "bore_off", "boss_missing",
    "scale_inch_mm", "stl_not_watertight", "dxf_missing_hole", "edge_violation",
]


def build_part(spec, out_dir):
    """Same geometry as examples/good/part.py (kept in sync deliberately:
    importing the example here would let a broken example break the
    self-test in confusing ways)."""
    import cadquery as cq
    import ezdxf
    L, W, T = spec["plate_l"], spec["plate_w"], spec["plate_t"]
    bore, boss_od, boss_h = spec["bore_d"], spec["boss_od"], spec["boss_h"]
    n, d, pcd = spec["bolt_n"], spec["bolt_d"], spec["pcd"]
    plate = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))
    if boss_h > 0:
        plate = plate.faces(">Z").workplane().circle(boss_od / 2).extrude(boss_h)
    plate = plate.faces(">Z").workplane().circle(bore / 2).cutThruAll()
    pts = [(pcd / 2 * math.cos(2 * math.pi * i / n),
            pcd / 2 * math.sin(2 * math.pi * i / n)) for i in range(n)]
    if pts:
        plate = (plate.faces(">Z").workplane()
                 .pushPoints(pts).circle(d / 2).cutThruAll())
    cq.exporters.export(plate, os.path.join(out_dir, "part.step"))
    cq.exporters.export(plate, os.path.join(out_dir, "part.stl"),
                        tolerance=0.01, angularTolerance=0.05,
                        exportType=cq.exporters.ExportTypes.STL)
    # DXF from the same spec
    doc = ezdxf.new("R2010", setup=False)
    msp = doc.modelspace()
    msp.add_lwpolyline([(L/2, W/2), (-L/2, W/2), (-L/2, -W/2), (L/2, -W/2)], close=True)
    msp.add_circle((0, 0), bore / 2)
    if boss_h > 0:
        msp.add_circle((0, 0), boss_od / 2)
    for i in range(n):
        a = 2 * math.pi * i / n
        msp.add_circle((pcd / 2 * math.cos(a), pcd / 2 * math.sin(a)), d / 2)
    doc.saveas(os.path.join(out_dir, "part.dxf"))


def drop_one_triangle(stl_in, stl_out):
    """Binary STL: rewrite with the first triangle removed (non-watertight)."""
    with open(stl_in, "rb") as f:
        data = f.read()
    n = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + 50 * n:
        raise SystemExit("mutants: expected a binary STL from the good build")
    with open(stl_out, "wb") as f:
        f.write(data[:80])
        f.write(struct.pack("<I", n - 1))
        f.write(data[84 + 50:])


def main():
    if "--list" in sys.argv:
        print("\n".join(MUTANTS))
        sys.exit(0)
    if len(sys.argv) != 3:
        print("usage: mutants.py <good_dir> <out_dir>", file=sys.stderr)
        sys.exit(2)
    good_dir, out_dir = sys.argv[1], sys.argv[2]
    spec0 = json.load(open(os.path.join(good_dir, "spec.json")))
    os.makedirs(out_dir, exist_ok=True)

    def sp(name, **over):
        s = dict(spec0)
        s.update(over)
        d = os.path.join(out_dir, name)
        os.makedirs(d, exist_ok=True)
        json.dump(s, open(os.path.join(d, "spec.json"), "w"), indent=2)
        return s, d

    # --- solid-level mutants: rebuild with a mutated spec ----------------
    s, d = sp("wrong_bolt_count", bolt_n=spec0["bolt_n"] - 1)
    build_part(s, d)
    s, d = sp("wrong_pcd", pcd=spec0["pcd"] + 10.0)
    build_part(s, d)
    s, d = sp("bore_off", bore_d=spec0["bore_d"] + 0.5)
    build_part(s, d)
    s, d = sp("boss_missing", boss_h=0.0)
    build_part(s, d)
    # edge_violation: shift the whole bolt pattern +Y until the worst hole
    # is closer than min_edge to the plate edge. Shifting the PCD centre
    # off the plate centre keeps holes round but breaks the rule.
    s, d = sp("edge_violation")
    s2 = dict(s)
    shift = (spec0["plate_w"] / 2 - spec0["pcd"] / 2 - spec0["bolt_d"] / 2) \
        - (spec0["min_edge"] - 2.0)
    # rebuild with pcd centre shifted: emulate by adding to y of each point
    import cadquery as cq
    import ezdxf
    L, W, T = s["plate_l"], s["plate_w"], s["plate_t"]
    bore, boss_od, boss_h = s["bore_d"], s["boss_od"], s["boss_h"]
    n, dd, pcd = s["bolt_n"], s["bolt_d"], s["pcd"]
    plate = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))
    plate = plate.faces(">Z").workplane().circle(boss_od / 2).extrude(boss_h)
    plate = plate.faces(">Z").workplane().circle(bore / 2).cutThruAll()
    pts = [(pcd / 2 * math.cos(2 * math.pi * i / n),
            pcd / 2 * math.sin(2 * math.pi * i / n) + shift) for i in range(n)]
    plate = (plate.faces(">Z").workplane()
             .pushPoints(pts).circle(dd / 2).cutThruAll())
    cq.exporters.export(plate, os.path.join(d, "part.step"))
    cq.exporters.export(plate, os.path.join(d, "part.stl"),
                        tolerance=0.01, angularTolerance=0.05,
                        exportType=cq.exporters.ExportTypes.STL)
    doc = ezdxf.new("R2010", setup=False)
    msp = doc.modelspace()
    msp.add_lwpolyline([(L/2, W/2), (-L/2, W/2), (-L/2, -W/2), (L/2, -W/2)], close=True)
    msp.add_circle((0, 0), bore / 2)
    msp.add_circle((0, 0), boss_od / 2)
    for i in range(n):
        a = 2 * math.pi * i / n
        msp.add_circle((pcd / 2 * math.cos(a), pcd / 2 * math.sin(a) + shift), dd / 2)
    doc.saveas(os.path.join(d, "part.dxf"))

    # --- scale error: inch/mm ------------------------------------------------
    s, d = sp("scale_inch_mm")
    sc = {k: (v * 25.4 if isinstance(v, float) else v) for k, v in s.items()}
    build_part(sc, d)

    # --- export-level mutants: good solid, broken mesh / drawing ------------
    s, d = sp("stl_not_watertight")
    build_part(s, d)
    drop_one_triangle(os.path.join(d, "part.stl"), os.path.join(d, "part.stl"))

    s, d = sp("dxf_missing_hole")
    build_part(s, d)
    doc = ezdxf.readfile(os.path.join(d, "part.dxf"))
    msp = doc.modelspace()
    circles = list(msp.query("CIRCLE"))
    # drop one bolt circle (last bolt-sized, off-origin)
    for c in reversed(circles):
        if abs(2 * c.dxf.radius - s["bolt_d"]) < 1e-6 and \
           (abs(c.dxf.center.x) > 1e-6 or abs(c.dxf.center.y) > 1e-6):
            msp.delete_entity(c)
            break
    doc.saveas(os.path.join(d, "part.dxf"))

    print("\n".join(MUTANTS))


if __name__ == "__main__":
    main()
