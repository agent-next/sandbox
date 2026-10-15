#!/usr/bin/env python3
"""cad-verify-back judge: grade delivered STEP / STL / DXF against the spec.

Usage:
    python3 grade.py <artifact_dir> [--spec spec.json] [--seed N] [--json out.json]

<artifact_dir> must contain part.step, part.stl and part.dxf (the agent's
delivered files). The judge never runs the agent's Python: it re-imports the
STEP through OCCT, checks that solid for validity with BRepCheck_Analyzer,
parses the STL with trimesh, reads the DXF with ezdxf, and compares the
re-imported STEP geometry against a reference solid built from the spec alone
via a boolean XOR (trimesh/manifold3d). Every expected number comes from the
closed-form oracle in judge/oracle.py, derived only from the spec JSON.

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

TOL_BBOX = 0.01        # mm, gate G2
TOL_VOL_STEP = 0.001   # relative, gate G3
TOL_DIAM = 0.01        # mm, gates G4 / G9
TOL_POS = 0.02         # mm, gates G4 / G5 / G6 / G9
TOL_ANG = 0.05         # deg, gates G5 / G6
TOL_VOL_STL = 0.01     # relative, gate G10
TOL_XOR = 0.01         # relative, gate G7 (symmetric difference vs reference)
TOL_DR = 0.01          # mm, gate G13
TESSELLATE_TOL = 0.01  # mm, chord tolerance for the XOR reference meshes


GATE_ORDER = [
    "step_solid", "step_valid", "step_bbox", "step_volume", "step_holes",
    "step_pcd", "angular_spacing", "step_xor",
    "stl_watertight", "stl_orient", "stl_volume", "dxf_circles",
    "dxf_outline", "design_rules",
]


class Gate:
    def __init__(self, gates, name, desc):
        self.name = name
        self.desc = desc
        self.gates = gates

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # _GateFail means the gate recorded its own failure; anything else
        # (a crash inside OCCT etc.) is recorded as a gate failure too
        if exc_type is None:
            return False
        if self.name not in self.gates:
            self.gates[self.name] = {"pass": False, "desc": self.desc,
                                    "error": f"{type(exc).__name__}: {exc}"}
        return True

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


def _tessellate_solid(solid_or_wp):
    """Tessellate a cadquery solid/workplane to a trimesh.Trimesh."""
    import numpy as np
    import trimesh
    val = solid_or_wp.val() if hasattr(solid_or_wp, "val") else solid_or_wp
    verts, faces = val.tessellate(TESSELLATE_TOL)
    return trimesh.Trimesh(
        vertices=np.array([[v.x, v.y, v.z] for v in verts]),
        faces=np.array(faces))


def build_reference(spec):
    """Reference solid built from the spec JSON alone (cadquery/OCCT).

    This is the only place geometry is reconstructed; every gate compares
    the delivered artifact against the spec-derived numbers in oracle.py
    or against this reference solid.
    """
    import math as _math
    import cadquery as cq
    L, W, T = spec["plate_l"], spec["plate_w"], spec["plate_t"]
    bore, boss_od, boss_h = spec["bore_d"], spec["boss_od"], spec["boss_h"]
    n, d, pcd = spec["bolt_n"], spec["bolt_d"], spec["pcd"]
    wp = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))
    if boss_h > 0:
        wp = wp.faces(">Z").workplane().circle(boss_od / 2).extrude(boss_h)
    wp = wp.faces(">Z").workplane().circle(bore / 2).cutThruAll()
    r = pcd / 2.0
    for i in range(n):
        a = 2.0 * _math.pi * i / n
        # cut each hole as an explicit cylinder through the plate: robust
        # where a single pushPoints cut can trip OCCT's shape upgrade
        cyl = (cq.Workplane("XY").workplane(offset=-1.0)
               .center(r * _math.cos(a), r * _math.sin(a))
               .circle(d / 2).extrude(T + 2.0))
        wp = wp.cut(cyl)
    return wp


def xor_volume_mm3(mesh_a, mesh_b):
    """Volume of the symmetric difference (A xor B) of two meshes, mm^3.

    Uses trimesh's boolean engine backed by manifold3d: XOR = union of
    (A - B) and (B - A). check_volume is off because both halves are empty
    when the shapes coincide.
    """
    from trimesh.boolean import boolean_manifold
    ab = boolean_manifold([mesh_a, mesh_b], "difference", check_volume=False)
    ba = boolean_manifold([mesh_b, mesh_a], "difference", check_volume=False)
    xor = boolean_manifold([ab, ba], "union", check_volume=False)
    return xor.volume


def angular_steps_deg(centres, n_expected):
    """Sorted angular positions and pairwise steps between consecutive holes."""
    angs = sorted((math.degrees(math.atan2(y, x)) + 360.0) % 360.0
                  for x, y in centres)
    steps = [(angs[(i + 1) % len(angs)] - angs[i]) % 360.0
             for i in range(len(angs))]
    return angs, steps


def grade(art_dir, spec_path, seed, json_out, artifact_name=None):
    spec = json.load(open(spec_path))
    exp = oracle.expected(spec)

    gates = {}
    t_start = time.time()
    # note: the verdict must stay byte-identical across runs with the same
    # seed, so it records only the artifact's basename, never its (random
    # scratch) absolute path

    step_path = os.path.join(art_dir, "part.step")
    stl_path = os.path.join(art_dir, "part.stl")
    dxf_path = os.path.join(art_dir, "part.dxf")
    for p in (step_path, stl_path, dxf_path):
        if not os.path.isfile(p):
            print(f"grade: missing delivered file {p}", file=sys.stderr)
            return verdict_fail(gates, f"missing file {os.path.basename(p)}",
                               json_out, t_start, art_dir, artifact_name)

    # ---- G1: STEP re-imports to exactly one solid --------------------
    solid = None
    centres = None
    with Gate(gates, "step_solid",
              "STEP re-imports through OCCT as exactly 1 solid") as g:
        try:
            solid = load_step_solid(step_path)
        except _GateFail:
            g.fail("STEP does not contain exactly one solid")
        except Exception as e:
            g.fail(f"STEP could not be re-imported through OCCT: "
                   f"{type(e).__name__}: {e}")
        if solid is not None and solid.Volume() <= 0:
            g.fail(f"STEP solid has non-positive volume {solid.Volume()}")
        g.ok(solids=1, volume_mm3=solid.Volume())

    # ---- G1b: STEP solid is a valid B-rep (OCCT BRepCheck_Analyzer) ------
    with Gate(gates, "step_valid",
              "re-imported STEP passes OCCT BRepCheck_Analyzer") as g:
        if solid is None:
            g.fail("skipped: no re-imported solid (G1)")
        from OCP.BRepCheck import BRepCheck_Analyzer
        if not BRepCheck_Analyzer(solid.wrapped).IsValid():
            g.fail("STEP solid is not a valid B-rep "
                   "(OCCT BRepCheck_Analyzer reports errors)")
        g.ok(valid=True)

    # ---- G2: bounding box ---------------------------------------------
    with Gate(gates, "step_bbox", "bbox within 0.01 mm of spec") as g:
        if solid is None:
            g.fail("skipped: no re-imported solid (G1)")
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
        if solid is None:
            g.fail("skipped: no re-imported solid (G1)")
        v = solid.Volume()
        ve = exp["volume_mm3"]
        rel = abs(v - ve) / ve
        if rel > TOL_VOL_STEP:
            g.fail(f"volume {v:.4f} vs closed-form {ve:.4f} "
                   f"(rel err {rel:.6%} > {TOL_VOL_STEP:.4%})")
        g.ok(volume_mm3=v, expected_mm3=ve, rel_err=rel,
             terms=exp["volume_terms"])

    # ---- G4: through-holes ---------------------------------------------
    with Gate(gates, "step_holes",
              "bore + bolt_n cylindrical through-holes at spec diameters") as g:
        if solid is None:
            g.fail("skipped: no re-imported solid (G1)")
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

    # ---- G5: bolt centres on the PCD ------------------------------------
    with Gate(gates, "step_pcd",
              "bolt centres on the spec PCD within 0.02 mm") as g:
        if centres is None:
            g.fail("skipped: no bolt centres from G4")
        r = exp["pcd_radius"]
        r_errs = [abs(math.hypot(x, y) - r) for x, y in centres]
        if max(r_errs) > TOL_POS:
            g.fail(f"bolt centre radial error up to {max(r_errs):.4f} mm "
                   f"(> {TOL_POS}); radii="
                   f"{[round(math.hypot(x, y), 3) for x, y in centres]}")
        # positions must also match the analytic centres
        pos_errs = []
        for (x, y) in centres:
            best = min(exp["bolt_centres"], key=lambda c: math.hypot(c[0] - x, c[1] - y))
            pos_errs.append(math.hypot(best[0] - x, best[1] - y))
        if max(pos_errs) > TOL_POS:
            g.fail(f"bolt centre positions off by up to {max(pos_errs):.4f} mm "
                   f"from analytic PCD positions")
        g.ok(max_radial_err_mm=round(max(r_errs), 5),
             max_pos_err_mm=round(max(pos_errs), 5))

    # ---- G6: angular spacing between consecutive holes --------------------
    with Gate(gates, "angular_spacing",
              "bolt holes evenly spaced: every step within 0.05 deg "
              "of 360/bolt_n") as g:
        if centres is None:
            g.fail("skipped: no bolt centres from G4")
        angs, steps = angular_steps_deg(centres, spec["bolt_n"])
        want = exp["angular_step_deg"]
        dev = max(abs(s - want) for s in steps)
        if dev > TOL_ANG:
            g.fail(f"angular steps {['%.4f' % s for s in steps]} deg vs "
                   f"expected {want} deg; max deviation {dev:.4f} > "
                   f"{TOL_ANG} deg")
        g.ok(angular_steps_deg=[round(s, 4) for s in steps],
             expected_step_deg=want,
             max_deviation_deg=round(dev, 5))

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
        if solid is None:
            g.fail("skipped: no re-imported solid (G1)")
        v_stl = m["volume_mm3"]
        v_step = solid.Volume()
        rel = abs(v_stl - v_step) / v_step
        if rel > TOL_VOL_STL:
            g.fail(f"STL volume {v_stl:.4f} vs STEP {v_step:.4f} "
                   f"(rel err {rel:.4%} > {TOL_VOL_STL:.2%})")
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
        if centres is None:
            g.fail("skipped: no bolt centres from G4")
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
    # a hard gate failure (G1) or a guard makes downstream gates
    # unreachable; record them explicitly so the verdict is always complete
    for name in GATE_ORDER:
        if name not in gates:
            gates[name] = {"pass": False, "desc": f"gate {name}",
                           "error": "skipped: an earlier gate failed"}
    passed = all(g["pass"] for g in gates.values())
    v = {
        "verdict": "pass" if passed else "fail",
        "seed": seed,
        "artifact": artifact_name or os.path.basename(os.path.normpath(art_dir)),
        "gates": gates,
        "timing": {"wall_s": round(time.time() - t_start, 2)},
    }
    if json_out:
        with open(json_out, "w") as f:
            json.dump(v, f, indent=2)
    print(json.dumps(v, indent=2))
    return 0 if passed else 1


def verdict_fail(gates, why, json_out, t_start, artifact=None, artifact_name=None):
    v = {
        "verdict": "fail",
        "reason": why,
        "gates": gates,
        "timing": {"wall_s": round(time.time() - t_start, 2)},
    }
    if artifact_name is not None:
        v["artifact"] = artifact_name
    elif artifact is not None:
        v["artifact"] = os.path.basename(os.path.normpath(artifact))
    if json_out:
        with open(json_out, "w") as f:
            json.dump(v, f, indent=2)
    print(json.dumps(v, indent=2))
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact_dir")
    ap.add_argument("--spec", default=os.path.join(HERE, "spec.json"),
                    help="customer spec JSON the artifact is graded against")
    ap.add_argument("--seed", type=int, default=20261014)
    ap.add_argument("--json")
    ap.add_argument("--artifact-name", default=None,
                    help="label recorded in the verdict instead of the "
                         "scratch dir path (keeps verdicts deterministic)")
    args = ap.parse_args()
    sys.exit(grade(args.artifact_dir, args.spec, args.seed, args.json,
                    artifact_name=args.artifact_name))


if __name__ == "__main__":
    main()
