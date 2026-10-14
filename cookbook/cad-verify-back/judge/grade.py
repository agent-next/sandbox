#!/usr/bin/env python3
"""cad-verify-back judge: grade delivered STEP / STL / DXF against the spec.

Usage:
    python3 grade.py <artifact_dir> [--spec spec.json] [--seed N] [--json out.json]

<artifact_dir> must contain part.step, part.stl and part.dxf (the agent's
delivered files). The judge never runs the agent's Python: it re-imports the
STEP through OCCT, parses the STL with its own stdlib parser (judge/stl.py),
and reads the DXF with ezdxf. Every expected number comes from the closed-form
oracle in judge/oracle.py, derived only from the spec JSON.

Exit 0 iff every gate passes. The verdict JSON contains every measured and
expected number so a pass can be checked by hand.
"""
import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import oracle          # noqa: E402  (judge's own closed-form oracle)
import stl as stllib   # noqa: E402  (judge's own STL parser, stdlib only)

TOL_BBOX = 0.01        # mm, gate G2
TOL_VOL_STEP = 0.001   # relative, gate G3
TOL_DIAM = 0.01        # mm, gates G4 / G9
TOL_POS = 0.02         # mm, gates G4 / G5 / G9
TOL_ANG = 0.05         # deg, gate G5
TOL_VOL_STL = 0.01     # relative, gate G8
TOL_DR = 0.01          # mm, gate G11


class Gate:
    def __init__(self, gates, name, desc):
        self.name = name
        self.desc = desc
        self.gates = gates

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # a gate only ends here: _GateFail means it recorded its own failure
        return exc_type is _GateFail

    def fail(self, msg):
        self.gates[self.name] = {"pass": False, "desc": self.desc, "error": msg}
        raise _GateFail()

    def ok(self, **metrics):
        self.gates[self.name] = {"pass": True, "desc": self.desc, **metrics}


class _GateFail(Exception):
    pass


def load_step_solid(path):
    """Re-import the delivered STEP through OCCT; return the solid."""
    from cadquery import importers
    from OCP.TopAbs import TopAbs_ShapeEnum
    wp = importers.importStep(path)
    solids = wp.solids().vals()
    if len(solids) != 1:
        raise _GateFail()
    return solids[0]


def step_cylinders(solid):
    """Cylindrical faces of the solid: (dia, cx, cy, zmin, zmax) in mm."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType
    out = []
    for f in solid.Faces():
        ad = BRepAdaptor_Surface(f.wrapped)
        if ad.GetType() == GeomAbs_SurfaceType.GeomAbs_Cylinder:
            cyl = ad.Cylinder()
            loc = cyl.Axis().Location()
            bb = f.BoundingBox()
            out.append((2.0 * cyl.Radius(), loc.X(), loc.Y(), bb.zmin, bb.zmax))
    return out


def grade(art_dir, spec_path, seed, json_out):
    spec = json.load(open(spec_path))
    exp = oracle.expected(spec)

    gates = {}
    t_start = time.time()

    step_path = os.path.join(art_dir, "part.step")
    stl_path = os.path.join(art_dir, "part.stl")
    dxf_path = os.path.join(art_dir, "part.dxf")
    for p in (step_path, stl_path, dxf_path):
        if not os.path.isfile(p):
            print(f"grade: missing delivered file {p}", file=sys.stderr)
            return verdict_fail(gates, f"missing file {os.path.basename(p)}",
                               json_out, t_start)

    # ---- G1: STEP re-imports to exactly one solid --------------------
    try:
        with Gate(gates, "step_solid",
                  "STEP re-imports through OCCT as exactly 1 solid") as g:
            try:
                solid = load_step_solid(step_path)
            except _GateFail:
                g.fail("STEP does not contain exactly one solid")
            if solid is None:
                g.fail("STEP solid is null")
            g.ok(solids=1, volume_mm3=solid.Volume())
    except _GateFail:
        return verdict_fail(gates, "G1 step_solid failed", json_out, t_start)

    # ---- G2: bounding box ---------------------------------------------
    with Gate(gates, "step_bbox", "bbox within 0.01 mm of spec") as g:
        bb = solid.BoundingBox()
        errs = [abs(a - b) for a, b in zip((bb.xlen, bb.ylen, bb.zlen), exp["bbox"])]
        if max(errs) > TOL_BBOX:
            g.fail(f"bbox ({bb.xlen:.4f}, {bb.ylen:.4f}, {bb.zlen:.4f}) vs "
                   f"expected {exp['bbox']}, component errors {errs}")
        g.ok(measured=[bb.xlen, bb.ylen, bb.zlen], expected=exp["bbox"],
             max_err_mm=max(errs))

    # ---- G3: volume vs closed form ------------------------------------
    with Gate(gates, "step_volume",
              "OCCT volume within 0.1% of closed-form spec volume") as g:
        v = solid.Volume()
        ve = exp["volume_mm3"]
        rel = abs(v - ve) / ve
        if rel > TOL_VOL_STEP:
            g.fail(f"volume {v:.4f} vs closed-form {ve:.4f} "
                   f"(rel err {rel:.6%} > {TOL_VOL_STEP:.0%})")
        g.ok(volume_mm3=v, expected_mm3=ve, rel_err=rel,
             terms=exp["volume_terms"])

    # ---- G4: through-holes ---------------------------------------------
    with Gate(gates, "step_holes",
              "bore + bolt_n cylindrical through-holes at spec diameters") as g:
        cyls = step_cylinders(solid)
        plate_top = spec["plate_t"]
        # bore: dia ~= bore_d, centred, spans the full height
        bore_hits = [c for c in cyls
                     if abs(c[0] - spec["bore_d"]) <= TOL_DIAM
                     and abs(c[1]) <= TOL_POS and abs(c[2]) <= TOL_POS]
        if not bore_hits:
            g.fail(f"no cylinder of diameter {spec['bore_d']} at the origin "
                   f"(found: {[round(c[0], 2) for c in cyls]})")
        bore = min(bore_hits, key=lambda c: (c[3], c[4]))
        if abs(bore[3]) > TOL_POS or abs(bore[4] - (plate_top + spec["boss_h"])) > TOL_BBOX:
            g.fail(f"bore cylinder spans z {bore[3]:.3f}..{bore[4]:.3f}, "
                   f"expected 0..{plate_top + spec['boss_h']:.3f} (not through)")
        # bolt holes: dia ~= bolt_d, through the plate only (z 0..plate_t)
        bolt_hits = [c for c in cyls
                     if abs(c[0] - spec["bolt_d"]) <= TOL_DIAM
                     and abs(c[3]) <= TOL_BBOX and abs(c[4] - plate_top) <= TOL_BBOX]
        if len(bolt_hits) != spec["bolt_n"]:
            g.fail(f"{len(bolt_hits)} bolt-diameter through-holes found, "
                   f"expected {spec['bolt_n']}")
        centres = [(c[1], c[2]) for c in bolt_hits]
        g.ok(bore_d=round(bore[0], 4), bolt_d=round(bolt_hits[0][0], 4),
             bolt_centres=[(round(x, 4), round(y, 4)) for x, y in centres])

    # ---- G5: bolt centres on the PCD, evenly spaced --------------------
    with Gate(gates, "step_pcd",
              "bolt centres on PCD within 0.02 mm, spacing within 0.05 deg") as g:
        r = exp["pcd_radius"]
        r_errs = [abs(math.hypot(x, y) - r) for x, y in centres]
        if max(r_errs) > TOL_POS:
            g.fail(f"bolt centre radial error up to {max(r_errs):.4f} mm "
                   f"(> {TOL_POS}); radii="
                   f"{[round(math.hypot(x, y), 3) for x, y in centres]}")
        angs = sorted((math.degrees(math.atan2(y, x)) + 360.0) % 360.0
                      for x, y in centres)
        steps = [(angs[(i + 1) % len(angs)] - angs[i]) % 360.0
                 for i in range(len(angs))]
        if any(abs(s - exp["angular_step_deg"]) > TOL_ANG for s in steps):
            g.fail(f"angular steps {['%.4f' % s for s in steps]} vs expected "
                   f"{exp['angular_step_deg']} deg (tol {TOL_ANG})")
        # positions must also match the analytic centres
        pos_errs = []
        for (x, y) in centres:
            best = min(exp["bolt_centres"], key=lambda c: math.hypot(c[0] - x, c[1] - y))
            pos_errs.append(math.hypot(best[0] - x, best[1] - y))
        if max(pos_errs) > TOL_POS:
            g.fail(f"bolt centre positions off by up to {max(pos_errs):.4f} mm "
                   f"from analytic PCD positions")
        g.ok(max_radial_err_mm=round(max(r_errs), 5),
             max_pos_err_mm=round(max(pos_errs), 5),
             angular_steps_deg=[round(s, 4) for s in steps])

    # ---- G6/G7/G8: STL with the judge's own parser ----------------------
    with Gate(gates, "stl_watertight",
              "own parser: every edge shared by exactly 2 triangles") as g:
        try:
            tris = stllib.parse_stl(stl_path)
        except SystemExit:
            g.fail("STL could not be parsed by the judge's own parser")
        errs, m = stllib.check_mesh(tris)
        if errs:
            g.fail("; ".join(errs[:3]))
        g.ok(**m)

    with Gate(gates, "stl_orient",
              "consistent winding; divergence volume positive") as g:
        if m["signed_volume_mm3"] <= 0:
            g.fail(f"mesh has inverted orientation (signed volume "
                   f"{m['signed_volume_mm3']:.2f} <= 0)")
        g.ok(signed_volume_mm3=m["signed_volume_mm3"])

    with Gate(gates, "stl_volume",
              "divergence-theorem STL volume within 1% of STEP volume") as g:
        v_stl = m["volume_mm3"]
        v_step = solid.Volume()
        rel = abs(v_stl - v_step) / v_step
        if rel > TOL_VOL_STL:
            g.fail(f"STL volume {v_stl:.4f} vs STEP {v_step:.4f} "
                   f"(rel err {rel:.4%} > {TOL_VOL_STL:.0%})")
        g.ok(stl_volume_mm3=v_stl, step_volume_mm3=v_step, rel_err=rel)

    # ---- G9/G10: DXF ------------------------------------------------------
    with Gate(gates, "dxf_circles",
              "DXF circles: count, diameters, positions match spec") as g:
        import ezdxf
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        circles = list(msp.query("CIRCLE"))
        if len(circles) != exp["dxf_circle_count"]:
            g.fail(f"{len(circles)} CIRCLE entities, expected "
                   f"{exp['dxf_circle_count']} (bore + boss OD + "
                   f"{spec['bolt_n']} bolt holes)")
        # each circle: (dia, centre)
        got = [(2.0 * c.dxf.radius, c.dxf.center.x, c.dxf.center.y) for c in circles]
        # bore + boss OD at origin
        for dia in (spec["bore_d"], spec["boss_od"]):
            hits = [c for c in got if abs(c[0] - dia) <= TOL_DIAM
                    and abs(c[1]) <= TOL_POS and abs(c[2]) <= TOL_POS]
            if not hits:
                g.fail(f"no DXF circle of diameter {dia} mm at the origin")
        # bolt circles at analytic centres
        for (cx, cy) in exp["bolt_centres"]:
            hits = [c for c in got if abs(c[0] - spec["bolt_d"]) <= TOL_DIAM
                    and math.hypot(c[1] - cx, c[2] - cy) <= TOL_POS]
            if not hits:
                g.fail(f"no DXF circle of diameter {spec['bolt_d']} mm at "
                       f"({cx:.3f}, {cy:.3f})")
        g.ok(count=len(circles),
             diameters=sorted(set(round(c[0], 3) for c in got)))

    with Gate(gates, "dxf_outline",
              "DXF outline: closed rectangle plate_l x plate_w centred") as g:
        corners = set()
        closed = False
        for lwp in msp.query("LWPOLYLINE"):
            pts = [tuple(round(v, 3) for v in p[:2]) for p in lwp.get_points("xy")]
            if lwp.closed and len(pts) == 4:
                closed = True
                corners = set(pts)
        for pl in msp.query("POLYLINE"):
            pts = [tuple(round(v, 3) for v in (v_.dxf.location.x, v_.dxf.location.y))
                   for v_ in pl.vertices]
            if pl.is_closed and len(pts) == 4:
                closed = True
                corners = set(pts)
        if not closed and len(list(msp.query("LINE"))) == 4:
            # 4 LINEs: check they form a closed loop with the spec corners
            segs = [((round(l.dxf.start.x, 3), round(l.dxf.start.y, 3)),
                     (round(l.dxf.end.x, 3), round(l.dxf.end.y, 3)))
                    for l in msp.query("LINE")]
            pts_all = {p for s in segs for p in s}
            edges = {frozenset(s) for s in segs}
            loop_ok = len(segs) == 4 and len(edges) == 4 \
                and len(pts_all) == 4 and len(set(frozenset((p,))
                                                 for p in pts_all)) == 0
            # each point touched by exactly 2 lines
            deg = {p: sum(1 for s in segs if p in s) for p in pts_all}
            if loop_ok and all(v == 2 for v in deg.values()):
                closed = True
                corners = pts_all
        if not closed:
            g.fail("no closed 4-corner outline found in the DXF "
                   "(LWPOLYLINE, POLYLINE or 4 LINEs)")
        want = set((round(x, 3), round(y, 3)) for x, y in exp["outline_corners"])
        if corners != want:
            g.fail(f"outline corners {sorted(corners)} vs expected {sorted(want)}")
        g.ok(corners=sorted(corners))

    # ---- G11: design rules ------------------------------------------------
    with Gate(gates, "design_rules",
              "min edge distance and ligament meet the spec") as g:
        holes = [(spec["bore_d"], 0.0, 0.0)] + \
                [(spec["bolt_d"], x, y) for x, y in centres]
        L, W = spec["plate_l"], spec["plate_w"]
        edge = min(min(L / 2 - abs(x), W / 2 - abs(y)) - dia / 2
                   for dia, x, y in holes)
        lig = math.inf
        for i in range(len(holes)):
            for j in range(i + 1, len(holes)):
                a, b = holes[i], holes[j]
                d_ab = math.hypot(a[1] - b[1], a[2] - b[2])
                lig = min(lig, d_ab - (a[0] + b[0]) / 2)
        # ligament to the boss annulus counts too (bolt under boss rim)
        lig = min(lig, exp["ligament_boss_mm"])
        if edge + TOL_DR < spec["min_edge"]:
            g.fail(f"min edge distance {edge:.3f} mm < spec {spec['min_edge']} mm")
        if lig + TOL_DR < spec["min_lig"]:
            g.fail(f"min ligament {lig:.3f} mm < spec {spec['min_lig']} mm")
        g.ok(min_edge_mm=round(edge, 4),
             min_ligament_mm=round(lig, 4),
             spec_min_edge=spec["min_edge"], spec_min_lig=spec["min_lig"],
             expected_edge_mm=round(exp["min_edge_distance_mm"], 4),
             expected_ligament_mm=round(exp["min_ligament_mm"], 4))

    # -----------------------------------------------------------------------
    passed = all(g["pass"] for g in gates.values())
    v = {
        "verdict": "pass" if passed else "fail",
        "seed": seed,
        "artifact": os.path.abspath(art_dir),
        "gates": gates,
        "timing": {"wall_s": round(time.time() - t_start, 2)},
    }
    if json_out:
        with open(json_out, "w") as f:
            json.dump(v, f, indent=2)
    print(json.dumps(v, indent=2))
    return 0 if passed else 1


def verdict_fail(gates, why, json_out, t_start):
    v = {
        "verdict": "fail",
        "reason": why,
        "gates": gates,
        "timing": {"wall_s": round(time.time() - t_start, 2)},
    }
    if json_out:
        with open(json_out, "w") as f:
            json.dump(v, f, indent=2)
    print(json.dumps(v, indent=2))
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact_dir")
    ap.add_argument("--spec", default=os.path.join(HERE, "..", "examples", "good", "spec.json"))
    ap.add_argument("--seed", type=int, default=20261014)
    ap.add_argument("--json")
    args = ap.parse_args()
    sys.exit(grade(args.artifact_dir, args.spec, args.seed, args.json))


if __name__ == "__main__":
    main()
