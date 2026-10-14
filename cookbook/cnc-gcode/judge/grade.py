#!/usr/bin/env python3
"""Run every cnc-gcode judge gate on an artifact and print one JSON verdict.

Invoked by judge/grade.sh with a scratch work directory that already holds
`cam.py` and the repo's `spec.json`.  This script runs the artifact itself
(with the venv interpreter, timeout 120 s), then parses and simulates the
`part.nc` it writes against the analytic oracle derived from the spec.

Exit 0 iff every gate passes.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import subprocess
import sys
import time
import traceback

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import gcode_sim as gs                                     # noqa: E402
import reference as ref                                    # noqa: E402

import numpy as np                                         # noqa: E402

# cam.py may import the standard library and numpy, nothing else: it is the
# agent's own CAM code, not a wrapper around somebody else's CAM kernel.
ALLOWED_IMPORTS = {
    "argparse", "ast", "cmath", "collections", "dataclasses", "itertools",
    "json", "math", "os", "pathlib", "re", "statistics", "sys", "typing",
    "numpy",
}

CAM_TIMEOUT_S = 120


class Gate:
    def __init__(self, name):
        self.name = name
        self.fields = {}
        self.ok = True

    def check(self, ok, **fields):
        self.ok = self.ok and bool(ok)
        self.fields.update(fields)
        return bool(ok)

    def dict(self):
        return {"pass": self.ok, **self.fields}


def check_imports(path):
    """Return (ok, imported module names) for the artifact's import list."""
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                mods.add(node.module.split(".")[0])
    bad = sorted(mods - ALLOWED_IMPORTS)
    return (not bad), sorted(mods), bad


# ---------------------------------------------------------------------------
# simulator self-check (gate 9): synthetic programs whose result is analytic
# ---------------------------------------------------------------------------

def measure_line_slot(spec):
    """Cut a 20 mm straight slot at Z=-2; measure its width at 5 stations."""
    nc = "\n".join([
        "G17 G21 G90",
        "S8000 M3",
        "G0 X20 Y10",
        "G1 Z-2 F400",
        "G1 X40 F1600",
        "G0 Z5",
        "M5",
    ])
    sim = gs.Simulator(spec, domain=((15.0, 45.0), (5.0, 15.0)))
    moves, _ = gs.parse_gcode(nc, (0.0, 0.0), spec["machine"]["safe_z_mm"])
    sim.run(moves)
    cut = sim.H < -1.0
    widths = []
    g = sim.g
    for station in (21.0, 25.0, 30.0, 35.0, 39.0):
        i = int(round((station - sim.x0) / g - 0.5))
        j_mid = int(np.argmin(np.abs(sim.ys - 10.0)))
        if not cut[j_mid, i]:
            widths.append(float("nan"))
            continue
        j0 = j_mid
        while j0 > 0 and cut[j0 - 1, i]:
            j0 -= 1
        j1 = j_mid
        while j1 + 1 < sim.ny and cut[j1 + 1, i]:
            j1 += 1
        widths.append((j1 - j0 + 1) * g)
    return widths


def measure_circle_slot(spec):
    """Cut a full circle of radius 10 mm at Z=-2; measure the annulus width."""
    nc = "\n".join([
        "G17 G21 G90",
        "S8000 M3",
        "G0 X30 Y10",
        "G1 Z-2 F400",
        "G3 X30 Y10 I10 J0 F1600",
        "G0 Z5",
        "M5",
    ])
    sim = gs.Simulator(spec, domain=((25.0, 55.0), (-5.0, 25.0)))
    moves, _ = gs.parse_gcode(nc, (0.0, 0.0), spec["machine"]["safe_z_mm"])
    sim.run(moves)
    cut = sim.H < -1.0
    ny, nx = cut.shape
    X, Y = np.meshgrid(sim.xs, sim.ys, indexing="ij")   # (nx, ny)
    r = np.hypot(X - 40.0, Y - 10.0)
    ang = np.arctan2(Y - 10.0, X - 40.0)
    widths = []
    for theta_deg in range(0, 360, 45):
        theta = math.radians(theta_deg)
        d = np.abs(np.mod(ang - theta + math.pi, 2 * math.pi) - math.pi)
        wedge = cut.T & (d <= math.radians(2.0))
        radii = r[wedge]
        widths.append(float(radii.max() - radii.min()) if radii.size else float("nan"))
    return widths


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--artifact-label", required=True,
                    help="original path of the artifact, for the report")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--seed", type=int, default=20261014)
    args = ap.parse_args()

    t0 = time.monotonic()
    gates = {}

    with open(args.spec, "r", encoding="utf-8") as fh:
        spec = json.load(fh)
    lim = spec["limits"]
    mach = spec["machine"]
    flutes = spec["tool"]["flutes"]
    grid = spec["grid_mm"]

    # ---- gate 0: artifact ------------------------------------------------
    g0 = Gate("artifact")
    cam_path = f"{args.work_dir}/cam.py"
    nc_path = f"{args.work_dir}/part.nc"
    try:
        ok_imports, mods, bad = check_imports(cam_path)
    except (OSError, SyntaxError) as exc:
        gates["artifact"] = {"pass": False, "error": f"cannot parse cam.py: {exc}"}
        return finish(args, {"gates": gates}, spec, t0, all_pass=False)
    g0.check(ok_imports, bad_imports=bad, imports=mods)
    t_cam = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "cam.py", "--spec", "spec.json", "--out", "part.nc"],
            cwd=args.work_dir, capture_output=True, text=True, timeout=CAM_TIMEOUT_S)
        cam_rc = proc.returncode
        cam_err = proc.stderr[-400:]
    except subprocess.TimeoutExpired:
        cam_rc, cam_err = -1, f"cam.py exceeded {CAM_TIMEOUT_S}s and was killed"
    t_cam = time.monotonic() - t_cam
    g0.check(cam_rc == 0, cam_exit=cam_rc, cam_stderr_tail=cam_err.strip())
    nc_text = None
    try:
        with open(nc_path, "r", encoding="utf-8") as fh:
            nc_text = fh.read(20 * 1024 * 1024)
    except OSError:
        pass
    g0.check(bool(nc_text), nc_bytes=(len(nc_text) if nc_text is not None else 0))
    gates["artifact"] = g0.dict()
    if not g0.ok:
        return finish(args, {"gates": gates}, spec, t0, all_pass=False)

    # ---- gate `units`: no inch-mode (G20) anywhere --------------------------
    # A mutant (or a bad artifact) that emits G20 is killed HERE by name, so
    # the self-test's kill attribution is never "no gate flagged".  This gate
    # runs on the raw text so it still fires when the full parse refuses first.
    gu = Gate("units")
    g20_lines, g21_line = gs.scan_unit_words(nc_text)
    gu.check(not g20_lines,
             g20_lines=g20_lines,
             first_g21_line=g21_line)
    if g20_lines:
        gu.check(False,
                 error=f"line {g20_lines[0]}: G20 inch mode -- the job is "
                       f"specified in millimetres (G21)")
        gates["units"] = gu.dict()
        # the units gate already names the kill; stop here
        return finish(args, {"gates": gates}, spec, t0, all_pass=False)
    gates["units"] = gu.dict()

    # ---- gate 1: program -------------------------------------------------
    g1 = Gate("program")
    try:
        moves, info = gs.parse_gcode(nc_text, mach["start_xy_mm"], mach["safe_z_mm"])
    except gs.GCodeError as exc:
        g1.check(False, error=str(exc), nc_lines=len(nc_text.splitlines()))
        gates["program"] = g1.dict()
        return finish(args, {"gates": gates}, spec, t0, all_pass=False)

    feed_moves = [m for m in moves if m["kind"] == "feed"]
    first_feed_line = min((m["line"] for m in feed_moves), default=None)
    last_feed_line = max((m["line"] for m in feed_moves), default=0)
    g1.check(info["has_g21"] and info["has_g90"] and info["has_g17"],
             has_g21=info["has_g21"], has_g90=info["has_g90"], has_g17=info["has_g17"])
    g1.check(info["m3_line"] is not None
             and first_feed_line is not None
             and info["m3_line"] < first_feed_line,
             m3_line=info["m3_line"], first_feed_line=first_feed_line)
    g1.check(info["m5_line"] is not None and info["m5_line"] >= last_feed_line,
             m5_line=info["m5_line"], last_feed_line=last_feed_line)
    g1.check(all(m["feed"] is not None and m["feed"] > 0 for m in feed_moves),
             feed_moves=len(feed_moves))
    gates["program"] = g1.dict()

    # ---- gate 2: envelope --------------------------------------------------
    g2 = Gate("envelope")
    ex0, ex1 = mach["envelope_x_mm"]
    ey0, ey1 = mach["envelope_y_mm"]
    ez0, ez1 = mach["envelope_z_mm"]
    worst = None
    for mv in moves:
        xmin, xmax, ymin, ymax = gs.path_bbox(mv, 0.0)
        zlo = min(mv["start"][2], mv["end"][2])
        zhi = max(mv["start"][2], mv["end"][2])
        cur = (xmin < ex0 or xmax > ex1 or ymin < ey0 or ymax > ey1
               or zlo < ez0 or zhi > ez1)
        if cur and worst is None:
            worst = (mv["line"], round(xmin, 3), round(xmax, 3),
                     round(ymin, 3), round(ymax, 3), round(zlo, 3), round(zhi, 3))
        if worst is not None:
            break
    g2.check(worst is None, first_violation=worst, moves=info["n_moves"])
    gates["envelope"] = g2.dict()

    # ---- simulate ----------------------------------------------------------
    t_sim = time.monotonic()
    sim = gs.Simulator(spec)
    recs = sim.run(moves)
    t_sim = time.monotonic() - t_sim

    cutting = [r for r in recs if r["kind"] == "feed" and r["cut_cells"] > 0]

    # ---- gate 3: stepdown --------------------------------------------------
    g3 = Gate("stepdown")
    max_axial = max((r["axial_mm"] for r in cutting), default=0.0)
    worst_line = max(cutting, key=lambda r: r["axial_mm"], default=None)
    g3.check(max_axial <= lim["max_stepdown_mm"] + 1e-6,
             max_axial_mm=round(max_axial, 4),
             limit_mm=lim["max_stepdown_mm"],
             worst_move_line=(worst_line["line"] if worst_line else None))
    gates["stepdown"] = g3.dict()

    # ---- gate 4: stepover --------------------------------------------------
    g4 = Gate("stepover")
    spaced = [r for r in cutting if r["spacing_mm"] is not None]
    max_sp = max((r["spacing_mm"] for r in spaced), default=0.0)
    worst_line = max(spaced, key=lambda r: r["spacing_mm"], default=None)
    g4.check(max_sp <= lim["max_stepover_mm"] + grid,
             max_spacing_mm=round(max_sp, 4),
             limit_mm=lim["max_stepover_mm"],
             tolerance_mm=grid,
             worst_move_line=(worst_line["line"] if worst_line else None),
             exempt_first_pass_moves=sum(1 for r in cutting if r["spacing_mm"] is None))
    gates["stepover"] = g4.dict()

    # ---- gate 5: process (chip load, feed, spindle) -------------------------
    g5 = Gate("process")
    cl_lo, cl_hi = lim["chip_load_mm_per_tooth"]
    f_lo, f_hi = lim["feed_mm_per_min"]
    rpm_tol = lim["spindle_rpm_tolerance"]
    chip = [r["feed"] / (r["spindle"] * flutes) for r in cutting
            if r["spindle"] and r["feed"]]
    bad_spindle = [r for r in cutting
                   if not r["spindle"]
                   or abs(r["spindle"] - lim["spindle_rpm"]) > rpm_tol * lim["spindle_rpm"]]
    bad_feed = [r for r in cutting if not (f_lo <= r["feed"] <= f_hi)]
    g5.check(chip and cl_lo <= min(chip) and max(chip) <= cl_hi,
             chip_load_mm_per_tooth=[round(min(chip), 5), round(max(chip), 5)]
             if chip else None,
             limits=[cl_lo, cl_hi])
    g5.check(not bad_spindle and not bad_feed,
             spindle_moves_out_of_band=len(bad_spindle),
             feed_moves_out_of_band=len(bad_feed),
             spindle_rpm=lim["spindle_rpm"])
    gates["process"] = g5.dict()

    # ---- gate 6: rapid safety ----------------------------------------------
    g6 = Gate("rapid_safety")
    rapids_low = [r for r in recs
                  if r["kind"] == "rapid" and r["z_end"] < mach["safe_z_mm"]]
    max_hit = max((r["rapid_hit_mm"] for r in rapids_low), default=0.0)
    worst_line = max(rapids_low, key=lambda r: r["rapid_hit_mm"], default=None)
    g6.check(all(r["rapid_hit_mm"] <= 0.01 for r in rapids_low),
             rapids_below_safe_z=len(rapids_low),
             max_rapid_hit_mm=round(max_hit, 4),
             tolerance_mm=0.01,
             worst_move_line=(worst_line["line"] if worst_line else None))
    gates["rapid_safety"] = g6.dict()

    # ---- oracle: residual + gouge -------------------------------------------
    orc = gs.oracle_heightmap(spec, sim.xs, sim.ys)
    H, target = sim.H, orc["target"]
    must = orc["must_clear"]
    res_cells = int((must & (H > target + 0.05)).sum())
    res_max = float((H - target)[must].max()) if must.any() else 0.0
    near_edge = ((orc["sdf_pocket"] < grid)
                 | (orc["in_island"] & (orc["d_island"] > spec["island"]["diameter_mm"] / 2 - grid)))
    quant_band = (target == 0.0) & near_edge
    gouge_mask = (H < target - 0.01) & ~quant_band
    gouge_cells = int(gouge_mask.sum())
    gouge_max = float((target - H)[gouge_mask].max()) if gouge_cells else 0.0

    g7 = Gate("residual")
    g7.check(res_cells == 0,
             residual_cells=res_cells,
             residual_area_mm2=round(res_cells * grid * grid, 4),
             worst_residual_mm=round(res_max, 4),
             tolerance_mm=0.05,
             unreachable_allowance_cells=orc["allowance_cells"])
    gates["residual"] = g7.dict()

    g8 = Gate("gouge")
    g8.check(gouge_cells == 0,
             gouge_cells=gouge_cells,
             gouged_area_mm2=round(gouge_cells * grid * grid, 4),
             worst_gouge_mm=round(gouge_max, 4),
             tolerance_mm=0.01)
    gates["gouge"] = g8.dict()

    # ---- gate 9: simulator self-check --------------------------------------
    g9 = Gate("simulator_selfcheck")
    t_sc = time.monotonic()
    lw = measure_line_slot(spec)
    cw = measure_circle_slot(spec)
    t_sc = time.monotonic() - t_sc
    d = spec["tool"]["diameter_mm"]
    ok = all(abs(w - d) <= grid for w in lw + cw)
    g9.check(ok, line_slot_widths_mm=[round(w, 4) for w in lw],
             circle_slot_widths_mm=[round(w, 4) for w in cw],
             expected_mm=d, tolerance_mm=grid)
    gates["simulator_selfcheck"] = g9.dict()

    # ---- gate 10: reference cross-check (LinuxCNC rs274) -------------------
    # Independent second opinion: the mature open-source RS274/NGC interpreter
    # (LinuxCNC's rs274).  The good program must be accepted (exit 0) by the
    # reference, must select mm units, and the reference's canonical move list
    # (feed/rapid/arc counts, min/max Z, XY bounding box) must agree with this
    # judge's own simulator within the stated tolerance.
    gr = Gate("reference")
    if ref.available():
        try:
            t_ref = time.monotonic()
            rr = ref.run(nc_text)
            t_ref = time.monotonic() - t_ref
        except Exception as exc:  # rs274 didn't run at all
            gr.check(False, error=f"reference run failed: {exc}")
            gates["reference"] = gr.dict()
        else:
            ss = ref.sim_stats(moves)
            agree = rr["ok"] and rr["units_mm"] is True
            diffs = {}
            if rr["ok"]:
                for k in ("feeds", "rapids", "arcs"):
                    diffs[f"{k}_diff"] = rr[k] - ss[k]
                agree = agree and all(v == 0 for v in diffs.values())
                for k in ("z_max", "z_min"):
                    if rr[k] is not None and ss[k] is not None:
                        diffs[f"{k}_diff_mm"] = round(rr[k] - ss[k], 6)
                        agree = agree and abs(rr[k] - ss[k]) <= ref.GEOM_TOL_MM
                if rr["bbox"] and ss["bbox"]:
                    bb = [round(rr["bbox"][i] - ss["bbox"][i], 6)
                          for i in range(4)]
                    diffs["bbox_diff_mm"] = bb
                    agree = agree and all(abs(v) <= ref.GEOM_TOL_MM for v in bb)
            gr.check(rr["ok"],
                     ref_exit=rr["exit"],
                     ref_units_mm=rr["units_mm"])
            if not rr["ok"]:
                gr.check(False,
                         ref_rejected=rr["stderr_tail"] or
                         "rs274 exited non-zero; program rejected by reference")
            gr.check(agree, ref_tool="LinuxCNC rs274 "
                     "2.9.0~pre1+git20230208.f1270d6ed7-1+deb12u2",
                     tolerance_mm=ref.GEOM_TOL_MM,
                     **diffs)
            gates["reference"] = gr.dict()
    else:
        gr.check(False, error="reference tool rs274 not installed "
                 "(run bash judge/setup.sh)")
        gates["reference"] = gr.dict()

    # ---- summary ------------------------------------------------------------
    cleared = int((H < -1e-9).sum())
    verdict = {
        "demo": "cnc-gcode",
        "artifact": args.artifact_label,
        "seed": args.seed,
        "randomness": "none (deterministic judge; seed recorded but unused)",
        "gates": gates,
        "summary": {
            "nc_lines": len(nc_text.splitlines()),
            "moves": info["n_moves"],
            "cutting_moves": len(cutting),
            "cells_cleared": cleared,
            "area_cleared_mm2": round(cleared * grid * grid, 2),
            "stock_removed_mm3": round(float((np.minimum(H, 0.0) * -1.0).sum()) * grid * grid, 1),
            "max_axial_engagement_mm": round(max_axial, 4),
            "max_pass_spacing_mm": round(max_sp, 4),
            "worst_residual_mm": round(res_max, 4),
            "worst_gouge_mm": round(gouge_max, 4),
        },
        "timing": {
            "cam_s": round(t_cam, 2),
            "simulate_s": round(t_sim, 2),
            "selfcheck_s": round(t_sc, 2),
            "reference_s": (round(t_ref, 2) if ref.available() else None),
            "total_s": None,                      # filled by finish()
        },
    }
    return finish(args, verdict, spec, t0, all_pass=all(g["pass"] for g in gates.values()))


def finish(args, verdict, spec, t0, all_pass):
    """Fill timing, emit JSON, print a short line, return the exit code."""
    if "timing" in verdict:
        verdict["timing"]["total_s"] = round(time.monotonic() - t0, 2)
    verdict["pass"] = bool(all_pass)
    text = json.dumps(verdict, indent=2, sort_keys=False)
    if getattr(args, "json_out", None):
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    failed = [n for n, g in verdict.get("gates", {}).items()
              if not g.get("pass")]
    if not all_pass:
        print(f"grade: FAIL (gates: {', '.join(failed) if failed else 'unknown'})",
              file=sys.stderr)
        return 1
    print("grade: PASS (all gates)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                     # noqa: BLE001
        traceback.print_exc()
        print("grade: internal judge error", file=sys.stderr)
        sys.exit(2)
