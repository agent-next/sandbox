#!/usr/bin/env python3
"""check_gates.py — apply the SPEC.md gates to two judge-produced samples.

Usage:
    check_gates.py <scenario.py> --run1 a.npz --run2 b.npz [--json out.json]

Exit 0 iff every gate passes. Prints one JSON verdict (--json) and a short
human summary.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


def load_scenario(path: Path) -> dict:
    spec = importlib.util.spec_from_file_location("artifact_scenario", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(mod.SCENARIO)


def gate_record(idx, name, passed, details):
    return {"gate": idx, "name": name, "passed": bool(passed), **details}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", type=Path)
    ap.add_argument("--run1", type=Path, required=True)
    ap.add_argument("--run2", type=Path, required=True)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    s = load_scenario(args.scenario)
    r1 = np.load(args.run1, allow_pickle=False)
    r2 = np.load(args.run2, allow_pickle=False)

    dt = float(s["dt"]); steps = int(s["steps"])
    g = float(s["gravity"])
    ps = float(s["particle_size"])
    cs = np.array(s["column_size"], float)
    cpos = np.array(s["column_pos"], float)
    osz = np.array(s["obstacle_size"], float)
    opos = np.array(s["obstacle_pos"], float)
    dom_lo = np.array(s["domain_lower"], float)
    dom_up = np.array(s["domain_upper"], float)

    pos = r1["pos"]; vel = r1["vel"]
    fr = r1["sample_frames"].astype(int)
    meta = json.loads(str(r1["meta"]))

    gates = []

    # ---------------- Gate 1: completion, finiteness, bounded velocity ----
    finite = bool(np.isfinite(pos).all() and np.isfinite(vel).all())
    vmax = float(np.linalg.norm(vel[-1], axis=1).max())
    wall = float(meta["wall_run_s"])
    passed = finite and vmax <= 50.0 and wall <= 480.0
    gates.append(gate_record(1, "completes, no NaN, bounded speed",
                             passed,
                             {"finite": finite, "final_vmax_m_s": round(vmax, 4),
                              "wall_run_s": wall, "wall_limit_s": 480.0}))

    # ---------------- Gate 2: mass conservation ---------------------------
    n0 = int(r1["n_particles0"])
    n1 = int(pos[-1].shape[0])
    inside = bool(np.all(pos >= dom_lo) and np.all(pos <= dom_up))
    passed = (n0 == n1) and inside
    gates.append(gate_record(2, "mass conservation",
                             passed, {"n_particles_initial": n0,
                                      "n_particles_final": n1,
                                      "all_particles_in_domain": inside}))

    # ---------------- Gate 3: free-fall ballistics ------------------------
    obs_top = opos[2] + osz[2] / 2
    z_bottom0 = cpos[2]
    t_fall = float(np.sqrt(2 * (z_bottom0 - obs_top) / abs(g)))
    t1, t2 = 2 * dt, 0.5 * t_fall
    ts = fr * dt
    mask = (ts >= t1) & (ts <= t2)
    n_fit = int(mask.sum())
    if n_fit >= 20:
        zc = pos[mask].mean(axis=1)[:, 2]
        A = np.stack([np.ones_like(ts[mask]), ts[mask], 0.5 * ts[mask] ** 2], 1)
        coef, *_ = np.linalg.lstsq(A, zc, rcond=None)
        a_fit, v0_fit = float(coef[2]), float(coef[1])
        a_rel = abs((a_fit - g) / g)
        passed = a_rel <= 0.02 and abs(v0_fit) <= 0.05
    else:
        a_fit = v0_fit = float("nan"); a_rel = float("inf"); passed = False
    gates.append(gate_record(3, "free-fall matches ballistic g",
                             passed,
                             {"n_fit_samples": n_fit,
                              "a_fit_m_s2": round(a_fit, 5),
                              "a_rel_err_vs_spec_g": round(a_rel, 5),
                              "v0_fit_m_s": round(v0_fit, 5),
                              "t_fall_s": round(t_fall, 5)}))

    # ---------------- Gate 4: no penetration ------------------------------
    tol = 1.5 * ps
    floor_min = float(pos[..., 2].min())
    lo = opos - osz / 2; hi = opos + osz / 2
    q = pos - 0.5 * (lo + hi)          # centred coords
    dq = np.abs(q) - 0.5 * osz         # >0 outside per-axis (box SDF outer part)
    outside = np.linalg.norm(np.maximum(dq, 0.0), axis=-1)
    inside_pen = np.minimum(np.max(dq, axis=-1), 0.0)  # <0 when strictly inside
    signed = outside + inside_pen
    worst_pen = float(max(0.0, -signed.min()))
    passed = floor_min >= -tol and worst_pen <= tol
    gates.append(gate_record(4, "no interpenetration",
                             passed,
                             {"tol_m": round(tol, 6),
                              "floor_min_z_m": round(floor_min, 6),
                              "obstacle_worst_pen_m": round(worst_pen, 6)}))

    # ---------------- Gate 5: material behaviour --------------------------
    pf, vf = pos[-1], vel[-1]
    r = np.linalg.norm(pf[:, :2] - cpos[:2], axis=1)
    r95 = float(np.percentile(r, 95))
    s_half = float(max(cs[0], cs[1]) / 2)
    spread_ok = (1.4 * s_half) <= r95 <= (6.0 * s_half)
    mean_speed = float(np.linalg.norm(vf, axis=1).mean())
    settle_ok = mean_speed < 0.05
    com0_z = float(pos[0].mean(axis=0)[2])
    comF_z = float(pf.mean(axis=0)[2])
    collapse_ok = comF_z < 0.6 * com0_z
    passed = spread_ok and settle_ok and collapse_ok
    gates.append(gate_record(5, "granular heap spreads within band",
                             passed,
                             {"r95_m": round(r95, 5),
                              "r95_band_m": [round(1.4*s_half, 5),
                                             round(6.0*s_half, 5)],
                              "mean_final_speed_m_s": round(mean_speed, 6),
                              "com_z_initial_m": round(com0_z, 5),
                              "com_z_final_m": round(comF_z, 5),
                              "settle_ok": settle_ok, "collapse_ok": collapse_ok,
                              "spread_ok": spread_ok}))

    # ---------------- Gate 6: determinism ---------------------------------
    pos_b = r2["pos"]
    if pos_b.shape != pos.shape:
        passed, max_abs = False, float("inf")
    else:
        max_abs = float(np.abs(pos - pos_b).max())
        passed = max_abs == 0.0
    gates.append(gate_record(6, "bit-exact determinism at fixed seed",
                             passed,
                             {"max_abs_position_deviation_m": max_abs}))

    all_ok = all(g["passed"] for g in gates)
    verdict = {
        "scenario": str(args.scenario),
        "all_gates_passed": all_ok,
        "gates": gates,
        "spec": {k: s[k] for k in ("gravity", "dt", "substeps", "steps",
                                   "particle_size", "grid_density")},
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w") as f:
            json.dump(verdict, f, indent=2)
            f.write("\n")

    for grec in gates:
        print(f"[gates] gate {grec['gate']} {grec['name']}: "
              f"{'PASS' if grec['passed'] else 'FAIL'}")
    print(f"[gates] all gates passed: {all_ok}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
