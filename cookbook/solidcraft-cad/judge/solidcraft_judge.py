#!/usr/bin/env python3
"""solidcraft-cad judge: grade one SolidCraft command script (design.json).

Usage: solidcraft_judge.py <design.json> [--spec spec.json] [--seed N]
                           [--json out.json]

SolidCraft builds the part; everything it delivers (STEP, STL) is then
measured again with OpenCascade (OCP) and checked against numbers the judge
derives from spec.json by hand-written formulas.  SolidCraft's own `eval`
numbers are used only in a cross-check gate, never as the answer.

Prints one JSON verdict; exits 0 only if every gate passes.  See SPEC.md.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent
SOLIDCRAFT_VERSION = "0.10.1"
CLI = Path(os.environ.get("HOME", "~")) / f".local/solidcraft-{SOLIDCRAFT_VERSION}-linux-x86_64/bin/solidcraft-cli"

# Commands a design script may use.  Anything that reads or writes files,
# opens other documents or touches diagnostics is refused before SolidCraft
# runs, so the artifact cannot reach outside its temp copy.
ALLOWED_PREFIXES = ("sketch.", "solid.", "construct.", "parameters.change", "parameters.add",
                    "timeline.", "material.assign", "appearance.assign", "body.rename",
                    "edit.undo", "edit.redo", "document.units", "select.")
DENIED = {"sketch.insert_dxf", "sketch.insert_svg", "sketch.export_dxf"}

GATES = ["build", "occt_shape", "volume", "features", "mass", "cross_check", "parametric", "stl"]

TOL = {
    "bbox_mm": 0.01,
    "volume_rel": 0.002,
    "diameter_mm": 0.02,
    "pcd_mm": 0.05,
    "angle_deg": 0.1,
    "cross_rel": 0.001,
    "com_mm": 0.01,
    "param_rel": 0.002,
    "stl_rel": 0.005,
}


def r6(x: float) -> float:
    """Round for the verdict so repeated runs are byte-identical."""
    return float(f"{x:.6g}")


# ---------------------------------------------------------------- analytic --

def analytic(spec: dict, thickness: float | None = None) -> dict:
    p = spec["plate"]
    L, W, r = p["length"], p["width"], p["corner_radius"]
    T = p["thickness"] if thickness is None else thickness
    bore_r = spec["bore"]["diameter"] / 2
    hole_r = spec["bolt_holes"]["diameter"] / 2
    n = spec["bolt_holes"]["count"]
    boss_R, H = spec["boss"]["outer_diameter"] / 2, spec["boss"]["height"]
    net_area = L * W - (4 - math.pi) * r * r - math.pi * bore_r ** 2 - n * math.pi * hole_r ** 2
    boss = math.pi * (boss_R ** 2 - bore_r ** 2) * H
    return {"net_plate_area": net_area, "volume": net_area * T + boss,
            "bbox_min": [-L / 2, -W / 2, 0.0], "bbox_max": [L / 2, W / 2, T + H]}


def hole_centres(spec: dict) -> list[tuple[float, float]]:
    b = spec["bolt_holes"]
    R = b["pitch_circle_diameter"] / 2
    a0 = math.radians(b.get("first_angle_deg", 0.0))
    return [(R * math.cos(a0 + 2 * math.pi * k / b["count"]),
             R * math.sin(a0 + 2 * math.pi * k / b["count"])) for k in range(b["count"])]


def edge_distance(spec: dict, x: float, y: float, rad: float) -> float:
    """Distance from a hole's edge to the rounded-rectangle outline."""
    p = spec["plate"]
    hx, hy, r = p["length"] / 2, p["width"] / 2, p["corner_radius"]
    ax, ay = abs(x), abs(y)
    if ax > hx - r and ay > hy - r:  # corner zone: distance to the fillet arc
        d = r - math.hypot(ax - (hx - r), ay - (hy - r))
    else:
        d = min(hx - ax, hy - ay)
    return d - rad


# ------------------------------------------------------------- SolidCraft --

def check_commands(design: dict) -> str | None:
    cmds = design.get("commands") if isinstance(design, dict) else None
    if not isinstance(cmds, list) or not cmds:
        return "design.json must be {\"commands\": [...]} with at least one command"
    for i, c in enumerate(cmds):
        name = c.get("command") if isinstance(c, dict) else None
        if not isinstance(name, str):
            return f"command {i} has no 'command' string"
        if name in DENIED or not name.startswith(ALLOWED_PREFIXES):
            return f"command {i} '{name}' is not allowed in a graded design (see SPEC.md)"
    return None


def solidcraft(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(CLI), *args], cwd=cwd, capture_output=True, text=True, timeout=300)


def build(design: Path, work: Path, tag: str) -> tuple[Path, Path, str | None]:
    step, stl = work / f"{tag}.step", work / f"{tag}.stl"
    proc = solidcraft(["run", design.name, "--out", step.name, "--out", stl.name, "--quiet"], work)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        return step, stl, f"solidcraft-cli run exit {proc.returncode}: {' | '.join(tail)}"
    for f in (step, stl):
        if not f.is_file() or f.stat().st_size == 0:
            return step, stl, f"{f.name} was not written"
    return step, stl, None


# -------------------------------------------------------------------- OCCT --

def occt_measure(step: Path) -> dict:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp, BRepGProp_Face
    from OCP.BRepTools import BRepTools
    from OCP.Bnd import Bnd_Box
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt, gp_Vec

    reader = STEPControl_Reader()
    if reader.ReadFile(str(step)) != IFSelect_RetDone:
        raise ValueError("OCCT could not read the STEP file")
    reader.TransferRoots()
    shape = reader.OneShape()

    solids = 0
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        solids += 1
        ex.Next()

    vp, sp = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vp)
    BRepGProp.SurfaceProperties_s(shape, sp)
    com = vp.CentreOfMass()
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    lo, hi = box.CornerMin(), box.CornerMax()

    # Cylindrical faces with a Z axis, merged by (centre, radius): a hole or
    # bore can be split into several faces by seams and boolean steps.
    cyl: dict[tuple, dict] = {}
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face(ex.Current())
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() == GeomAbs_Cylinder:
            c = surf.Cylinder()
            d, loc = c.Axis().Direction(), c.Location()
            if abs(abs(d.Z()) - 1) < 1e-9:
                umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
                p, n = gp_Pnt(), gp_Vec()
                BRepGProp_Face(face).Normal((umin + umax) / 2, (vmin + vmax) / 2, p, n)
                # concave (a hole) when the outward normal points at the axis
                concave = n.X() * (loc.X() - p.X()) + n.Y() * (loc.Y() - p.Y()) > 0
                fb = Bnd_Box()
                BRepBndLib.Add_s(face, fb)
                z0, z1 = fb.CornerMin().Z(), fb.CornerMax().Z()
                key = (round(loc.X(), 3), round(loc.Y(), 3), round(c.Radius(), 3), concave)
                e = cyl.setdefault(key, {"x": loc.X(), "y": loc.Y(), "r": c.Radius(),
                                         "concave": concave, "z0": z0, "z1": z1})
                e["z0"], e["z1"] = min(e["z0"], z0), max(e["z1"], z1)
        ex.Next()

    return {"solids": solids, "valid": bool(BRepCheck_Analyzer(shape).IsValid()),
            "volume": vp.Mass(), "area": sp.Mass(), "com": [com.X(), com.Y(), com.Z()],
            "bbox_min": [lo.X(), lo.Y(), lo.Z()], "bbox_max": [hi.X(), hi.Y(), hi.Z()],
            "cylinders": sorted(cyl.values(), key=lambda e: (e["r"], e["x"], e["y"]))}


# --------------------------------------------------------------------- STL --

def stl_check(path: Path) -> dict:
    """Binary or ASCII STL: closed 2-manifold with consistent orientation, and
    its divergence-theorem volume."""
    data = path.read_bytes()
    tris = []
    n = struct.unpack_from("<I", data, 80)[0] if len(data) >= 84 else -1
    if n >= 0 and 84 + 50 * n == len(data):
        for i in range(n):
            v = struct.unpack_from("<9f", data, 84 + 50 * i + 12)
            tris.append((v[0:3], v[3:6], v[6:9]))
    else:
        pts = [tuple(float(t) for t in ln.split()[1:4])
               for ln in data.decode("ascii", "replace").splitlines() if ln.strip().startswith("vertex")]
        tris = [tuple(pts[i:i + 3]) for i in range(0, len(pts) - 2, 3)]
    directed: dict[tuple, int] = {}
    vol = 0.0
    for a, b, c in tris:
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
        for e in ((a, b), (b, c), (c, a)):
            directed[e] = directed.get(e, 0) + 1
    bad = sum(1 for e, k in directed.items() if k != 1 or directed.get((e[1], e[0])) != 1)
    return {"triangles": len(tris), "bad_edges": bad, "volume": abs(vol)}


# ------------------------------------------------------------------- gates --

def grade(design_path: Path, spec: dict, seed: int) -> dict:
    gates: dict[str, dict] = {}
    timing: dict[str, float] = {}
    t0 = time.monotonic()

    def done(name: str, ok: bool, **kw) -> bool:
        gates[name] = {"pass": bool(ok), **kw}
        timing[name] = round(time.monotonic() - t0, 2)
        return ok

    ref = analytic(spec)
    with tempfile.TemporaryDirectory(prefix="solidcraft-judge-") as tmp:
        work = Path(tmp)
        try:
            design = json.loads(design_path.read_text())
        except (OSError, ValueError) as exc:
            done("build", False, reason=f"design is not valid JSON: {exc}")
            return finish(gates, timing, seed)
        err = check_commands(design)
        if err:
            done("build", False, reason=err)
            return finish(gates, timing, seed)
        (work / "design.json").write_text(json.dumps(design))
        step, stl, err = build(work / "design.json", work, "part")
        if not done("build", err is None, reason=err or "STEP and STL written"):
            return finish(gates, timing, seed)

        try:
            m = occt_measure(step)
        except Exception as exc:  # noqa: BLE001 - any OCCT failure fails the gate
            done("occt_shape", False, reason=f"OCCT re-import failed: {exc}")
            return finish(gates, timing, seed)
        bdev = max(max(abs(a - b) for a, b in zip(m["bbox_min"], ref["bbox_min"])),
                   max(abs(a - b) for a, b in zip(m["bbox_max"], ref["bbox_max"])))
        # OCCT's optimal box carries ~1e-7 mm of tolerance padding
        done("occt_shape", m["solids"] == 1 and m["valid"] and bdev <= TOL["bbox_mm"],
             solids=m["solids"], valid=m["valid"],
             bbox_min=[r6(v) for v in m["bbox_min"]], bbox_max=[r6(v) for v in m["bbox_max"]],
             bbox_max_dev_mm=r6(bdev), limit_mm=TOL["bbox_mm"])

        vrel = abs(m["volume"] - ref["volume"]) / ref["volume"]
        done("volume", vrel <= TOL["volume_rel"], occt_mm3=r6(m["volume"]),
             analytic_mm3=r6(ref["volume"]), rel_dev=r6(vrel), limit_rel=TOL["volume_rel"])

        ok, info = features(m, spec)
        done("features", ok, **info)

        mass = m["volume"] * spec["material"]["density_g_cm3"] / 1000.0
        done("mass", mass <= spec["mass_limit_g"], mass_g=r6(mass), limit_g=spec["mass_limit_g"],
             density_g_cm3=spec["material"]["density_g_cm3"])

        ok, info = cross_check(work, m)
        done("cross_check", ok, **info)
        ok, info = parametric(design, work, spec, m["volume"])
        done("parametric", ok, **info)

        s = stl_check(stl)
        srel = abs(s["volume"] - m["volume"]) / m["volume"]
        done("stl", s["bad_edges"] == 0 and s["triangles"] > 0 and srel <= TOL["stl_rel"],
             triangles=s["triangles"], non_manifold_edges=s["bad_edges"],
             stl_volume_mm3=r6(s["volume"]), rel_dev_vs_step=r6(srel), limit_rel=TOL["stl_rel"])
    return finish(gates, timing, seed)


def features(m: dict, spec: dict) -> tuple[bool, dict]:
    holes = [c for c in m["cylinders"] if c["concave"]]
    bosses = [c for c in m["cylinders"] if not c["concave"]]
    want_bore = spec["bore"]["diameter"] / 2
    T, H = spec["plate"]["thickness"], spec["boss"]["height"]
    problems = []

    bore = [c for c in holes if math.hypot(c["x"], c["y"]) < TOL["pcd_mm"]]
    bolts = [c for c in holes if c not in bore]
    bore_d = 2 * bore[0]["r"] if len(bore) == 1 else None
    if len(bore) != 1:
        problems.append(f"expected 1 centre bore, found {len(bore)}")
    elif abs(bore_d - 2 * want_bore) > TOL["diameter_mm"]:
        problems.append(f"bore diameter {bore_d:.4f} != {2 * want_bore}")
    elif bore[0]["z0"] > TOL["bbox_mm"] or bore[0]["z1"] < T + H - TOL["bbox_mm"]:
        problems.append("bore does not run through plate and boss")

    b = spec["bolt_holes"]
    if len(bolts) != b["count"]:
        problems.append(f"expected {b['count']} bolt holes, found {len(bolts)}")
    d_dev = max((abs(2 * c["r"] - b["diameter"]) for c in bolts), default=0.0)
    pcd_dev = max((abs(math.hypot(c["x"], c["y"]) - b["pitch_circle_diameter"] / 2) for c in bolts), default=0.0)
    angles = sorted(math.degrees(math.atan2(c["y"], c["x"])) % 360 for c in bolts)
    gaps = [(angles[(i + 1) % len(angles)] - angles[i]) % 360 for i in range(len(angles))] if len(angles) > 1 else []
    ang_dev = max((abs(g - 360 / len(angles)) for g in gaps), default=0.0)
    edge = min((edge_distance(spec, c["x"], c["y"], c["r"]) for c in bolts), default=float("nan"))
    if d_dev > TOL["diameter_mm"]:
        problems.append(f"bolt hole diameter off by {d_dev:.4f} mm")
    if pcd_dev > TOL["pcd_mm"]:
        problems.append(f"bolt hole off the pitch circle by {pcd_dev:.4f} mm")
    if ang_dev > TOL["angle_deg"]:
        problems.append(f"bolt hole spacing off by {ang_dev:.3f} deg")
    if bolts and edge < spec["min_edge_distance"]:
        problems.append(f"edge distance {edge:.3f} < {spec['min_edge_distance']}")
    for c in bolts:
        if c["z0"] > TOL["bbox_mm"] or c["z1"] < T - TOL["bbox_mm"]:
            problems.append("a bolt hole does not go through the plate")
            break

    boss = [c for c in bosses if math.hypot(c["x"], c["y"]) < TOL["pcd_mm"]]
    boss_h = (boss[0]["z1"] - boss[0]["z0"]) if len(boss) == 1 else None
    if len(boss) != 1 or abs(2 * boss[0]["r"] - spec["boss"]["outer_diameter"]) > TOL["diameter_mm"]:
        problems.append("boss outer cylinder missing or wrong diameter")
    elif abs(boss_h - H) > TOL["bbox_mm"] or abs(boss[0]["z0"] - T) > TOL["bbox_mm"]:
        problems.append(f"boss spans z {boss[0]['z0']:.3f}..{boss[0]['z1']:.3f}, expected {T}..{T + H}")

    r = spec["plate"]["corner_radius"]
    corners = [c for c in bosses if c not in boss and abs(c["r"] - r) <= TOL["diameter_mm"]]
    if len(corners) != 4:
        problems.append(f"expected 4 corner fillets of R{r}, found {len(corners)}")

    return not problems, {
        "bolt_holes": len(bolts), "bolt_diameter_max_dev_mm": r6(d_dev),
        "pcd_max_dev_mm": r6(pcd_dev), "spacing_max_dev_deg": r6(ang_dev),
        "min_edge_distance_mm": r6(edge) if bolts else None,
        "bore_diameter_mm": r6(bore_d) if bore_d else None,
        "boss_height_mm": r6(boss_h) if boss_h is not None else None,
        "corner_fillets": len(corners), "problems": problems}


def cross_check(work: Path, m: dict) -> tuple[bool, dict]:
    proc = solidcraft(["eval", "design.json"], work)
    try:
        ev = json.loads(proc.stdout)
        body = ev["bodies"][0]
        n = ev["body_count"] if "body_count" in ev else len(ev["bodies"])
    except (ValueError, KeyError, IndexError, TypeError):
        return False, {"reason": f"solidcraft-cli eval gave no body (exit {proc.returncode})"}
    vrel = abs(body["volume_mm3"] - m["volume"]) / m["volume"]
    arel = abs(body["area_mm2"] - m["area"]) / m["area"]
    cdev = max(abs(a - b) for a, b in zip(body["center_of_mass"], m["com"]))
    ok = n == 1 and vrel <= TOL["cross_rel"] and arel <= TOL["cross_rel"] and cdev <= TOL["com_mm"]
    return ok, {"solidcraft_volume_mm3": r6(body["volume_mm3"]), "volume_rel_dev": r6(vrel),
                "solidcraft_area_mm2": r6(body["area_mm2"]), "occt_area_mm2": r6(m["area"]),
                "area_rel_dev": r6(arel), "com_max_dev_mm": r6(cdev), "bodies": n,
                "limit_rel": TOL["cross_rel"], "limit_com_mm": TOL["com_mm"]}


def parametric(design: dict, work: Path, spec: dict, base_volume: float) -> tuple[bool, dict]:
    name, delta = spec["parametric"]["parameter"], spec["parametric"]["delta"]
    T = spec["plate"]["thickness"]
    edits = 0
    for c in design["commands"]:
        p = c.get("params") or {}
        if c["command"] in ("parameters.change", "parameters.add") and p.get("name") == name:
            p["expression"] = f"{T + delta} mm"
            edits += 1
    if edits == 0:
        return False, {"reason": f"no parameters.change/add for '{name}' in the design"}
    (work / "edited.json").write_text(json.dumps(design))
    step, _, err = build(work / "edited.json", work, "edited")
    if err:
        return False, {"reason": f"rebuild with {name}={T + delta} failed: {err}"}
    try:
        e = occt_measure(step)
    except Exception as exc:  # noqa: BLE001
        return False, {"reason": f"OCCT re-import of the rebuilt part failed: {exc}"}
    want = analytic(spec, T + delta)
    got_d, want_d = e["volume"] - base_volume, want["volume"] - analytic(spec)["volume"]
    rel = abs(got_d - want_d) / abs(want_d)
    zdev = abs(e["bbox_max"][2] - want["bbox_max"][2])
    ok = e["solids"] == 1 and rel <= TOL["param_rel"] and zdev <= TOL["bbox_mm"]
    return ok, {"parameter": name, "new_value_mm": T + delta, "solids": e["solids"],
                "volume_delta_mm3": r6(got_d), "analytic_delta_mm3": r6(want_d), "rel_dev": r6(rel),
                "top_z_mm": r6(e["bbox_max"][2]), "expected_top_z_mm": r6(want["bbox_max"][2]),
                "limit_rel": TOL["param_rel"]}


def finish(gates: dict, timing: dict, seed: int) -> dict:
    failed = next((g for g in GATES if g in gates and not gates[g]["pass"]), None)
    if failed is None and len(gates) < len(GATES):
        failed = next(g for g in GATES if g not in gates)
    reason = None
    if failed:
        g = gates.get(failed, {})
        reason = g.get("reason") or "; ".join(g.get("problems") or []) or json.dumps(
            {k: v for k, v in g.items() if k != "pass"})
    return {"demo": "solidcraft-cad", "passed": failed is None, "failed_gate": failed, "reason": reason,
            "seed": seed, "gates": gates,
            "versions": {"solidcraft": SOLIDCRAFT_VERSION, "python": sys.version.split()[0]},
            "timing": timing}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("design")
    ap.add_argument("--spec", default=str(DEMO / "spec.json"))
    ap.add_argument("--seed", type=int, default=20261014,
                    help="recorded in the verdict; the judge makes no random choices")
    ap.add_argument("--json", dest="json_out")
    a = ap.parse_args()
    if not CLI.is_file():
        print(f"judge: {CLI} not found; run judge/setup.sh first", file=sys.stderr)
        return 2
    spec = json.loads(Path(a.spec).read_text())
    verdict = grade(Path(a.design), spec, a.seed)
    text = json.dumps(verdict, indent=2, sort_keys=True)
    print(text)
    if a.json_out:
        Path(a.json_out).write_text(text + "\n")
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
