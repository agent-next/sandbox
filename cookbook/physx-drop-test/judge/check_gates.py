#!/usr/bin/env python3
"""check_gates.py — independent analytic oracle for the drop test.

Reads the raw trajectory sampled by simulate.py and compares it against
closed-form Newtonian mechanics computed here, from first principles:

    free fall:   y(t)  = y0 - g t^2 / 2          (before first contact)
    contact:     t_c   = sqrt(2 (y0 - y_rest) / g)
    bounce:      apex  = y_rest + e^2 (y0 - y_rest)
    energy:      E(t)  = m g y(t) + 1/2 m v(t)^2  (non-increasing, e <= 1)

Nothing in this file consults PhysX; the simulator only supplies samples.
Gates (SPEC.md):

  G1 loads         — both bodies sampled for every step, mass read back
                     within 0.1% of the authored value
  G2 freefall      — pre-contact samples match a free-fall parabola with
                     |g_fit - 9.81| <= 1% and residuals <= 1% + 0.5 mm
  G3 contact time  — first contact within 1 frame (1/240 s) of t_c
  G4 resting       — |y_final - y_rest| <= 1 mm
  G5 bounce apex   — ball's first rebound apex within 10% of the analytic
  G6 energy        — no sample-to-sample E increase > 0.5% of E0; E_final
                     <= E0 (+0.5% of E0)
  G7 contract      — the artifact itself obeys the SPEC's dynamics contract:
                     both bodies dynamic (no kinematic flags), no joints
                     or other constraint prims, stage self-contained (no
                     references/payload/sublayers), no velocity/drive
                     authoring.  Re-derived by the judge from the artifact
                     text; catches scenes that animate or scaffold their
                     way to a passing trajectory.

check_gates.py is handed the same scratch copy the simulator stepped, so
the judged scene and the judged numbers cannot differ.

Prints one JSON verdict and exits 0 only if every gate passes.
Wall-time fields live only under 'timing' (added by grade.sh).
"""

import json
import math
import re
import sys
from pathlib import Path

import numpy as np

G = 9.81                  # m/s^2 (the authored gravity magnitude)
DT = 1.0 / 240.0
STEPS = 2400
FRAME = 1.0 / 240.0       # 1-frame tolerance for G3

Y_REST = 0.10             # geometric resting height for BOTH bodies
                             # (box half-extent 0.10 m, ball radius 0.10 m)
H_BOX = 0.80              # authored drop heights (center, m)
H_BALL = 1.20
E_REST = 0.50             # authored restitution
M_BOX = 4.0               # authored masses (kg)
M_BALL = 1.0

MASS_TOL = 1e-3          # G1: body mass must be within 0.1% of the spec
FF_REL_TOL = 0.01        # G2: 1% relative (+0.5 mm absolute floor)
FF_G_TOL = 0.01          # G2: fitted gravity within 1% of 9.81
REST_ABS_TOL = 0.001     # G4: 1 mm
APEX_REL_TOL = 0.10      # G5: 10%
ENERGY_TOL = 0.005       # G6: 0.5% of initial potential energy
CONTACT_SPEED_EPS = 0.05  # m/s: pre-contact if still falling freely


def gate_freefall(y, vy, y0):
    """G2: every sample up to first contact lies on y0 - g t^2/2.

    PhysX integrates velocity semi-implicitly, so the sampled parabola can
    carry a small phase offset; the oracle is invariant to it: least-squares
    fit y(t) = a t^2 + b t + c over the pre-contact window and require
    a = -g/2 within 1% plus residuals within 1% + 0.5 mm.  Returns
    (ok, detail, contact_index).
    """
    n = len(y)
    falling = np.where(vy < -CONTACT_SPEED_EPS)[0]
    # first contact: first sample that is no longer in free fall by a
    # clear velocity break (vy departs upward after being negative)
    contact_idx = None
    for i in range(1, n):
        if vy[i - 1] < 0.0 and vy[i] > 0.0:
            contact_idx = i
            break
    if contact_idx is None:
        # never bounced: fall through or never moved — fail G2 if it also
        # never tracked the parabola; caller treats contact_idx=None in G3.
        if falling.size < 8:
            return False, {"reason": "no free-fall segment sampled",
                           "samples_falling": int(falling.size)}, None
        window = falling
    else:
        window = np.arange(0, max(contact_idx, 8))

    t = np.arange(len(y)) * DT
    tw = t[window]
    yw = y[window]
    # need a real parabola sample: at least 8 points spanning > 40 ms
    if len(yw) < 8 or tw[-1] - tw[0] < 0.04:
        return False, {"reason": "free-fall window too short",
                       "n": int(len(yw))}, contact_idx
    coeffs, res, *_ = np.polyfit(tw, yw, 2, full=True)
    a, b, c = coeffs
    g_fit = -2.0 * a
    y_fit = np.polyval(coeffs, tw)
    resid = np.abs(y_fit - yw)
    scale = np.maximum(np.abs(y_fit), 1e-9)
    rel = float((resid / scale).max())
    max_resid = float(resid.max())
    ok = (abs(g_fit - G) <= FF_G_TOL * G
          and rel <= FF_REL_TOL
          and max_resid <= FF_REL_TOL * np.abs(y0) + 5e-4)
    return ok, {
        "g_fit": round(float(g_fit), 4),
        "max_rel_residual": round(rel, 5),
        "max_abs_residual_m": round(max_resid, 6),
        "fit_start_s": round(float(tw[0]), 4),
        "fit_end_s": round(float(tw[-1]), 4),
    }, contact_idx


def gate_contact_time(contact_idx, y0):
    """G3: first contact within 1 frame of sqrt(2 (y0-y_rest)/g)."""
    if y0 <= Y_REST:
        return False, {"t_contact_analytic_s": None,
                       "t_contact_sim_s": None,
                       "reason": f"spawn height {y0:.3f} m is at/below the "
                                 f"resting height {Y_REST} m"}
    t_c = math.sqrt(2.0 * (y0 - Y_REST) / G)
    if contact_idx is None:
        return False, {"t_contact_analytic_s": round(t_c, 5),
                       "t_contact_sim_s": None,
                       "reason": "no velocity reversal — no contact detected"}
    t_sim = contact_idx * DT
    ok = abs(t_sim - t_c) <= FRAME
    return ok, {
        "t_contact_analytic_s": round(t_c, 5),
        "t_contact_sim_s": round(t_sim, 5),
        "delta_frames": round(abs(t_sim - t_c) / FRAME, 2),
    }


def gate_resting(y):
    """G4: final height within 1 mm of the geometric resting height."""
    y_final = float(y[-1])
    err = abs(y_final - Y_REST)
    return err <= REST_ABS_TOL, {
        "y_final_m": round(y_final, 6),
        "y_rest_m": Y_REST,
        "error_mm": round(err * 1000, 3),
    }


def gate_bounce_apex(y, contact_idx, y0):
    """G5: first rebound apex within 10% of y_rest + e^2 (y0 - y_rest)."""
    if contact_idx is None or contact_idx >= len(y) - 2:
        return False, {"reason": "no rebound sampled", "apex_analytic_m":
                       round(Y_REST + E_REST ** 2 * (y0 - Y_REST), 4)}
    apex_analytic = Y_REST + E_REST ** 2 * (y0 - Y_REST)
    # first local maximum after first contact
    seg = y[contact_idx + 1:]
    rises = np.where((seg[1:] - seg[:-1]) < 0)[0]
    if rises.size == 0:
        apex_sim = float(seg.max())
    else:
        apex_sim = float(seg[:rises[0] + 1].max())
    rel = abs(apex_sim - apex_analytic) / apex_analytic
    return rel <= APEX_REL_TOL, {
        "apex_analytic_m": round(float(apex_analytic), 4),
        "apex_sim_m": round(apex_sim, 4),
        "rel_error": round(float(rel), 4),
    }


def gate_contract(usd_text):
    """G7: the artifact obeys the SPEC's dynamics contract.

    The analytic gates above judge the trajectory; this gate judges the
    artifact itself, re-derived here straight from its text (the scene the
    simulator stepped — grade.sh passes the same scratch copy).  A scene
    that animates or scaffolds its way to a passing trajectory cannot pass:
    """
    problems = []

    # 1. no kinematic anything: dynamics must produce the motion
    for m in re.finditer(r"^\s*bool physics:(\w*[Kk]inematic\w*)\s*=\s*(\S+?);?\s*$",
                         usd_text, re.MULTILINE):
        if m.group(2) in ("1", "true", "True"):
            problems.append(
                f"physics:{m.group(1)} is set — bodies must be dynamic, "
                "not kinematically animated")

    # 2. no joints or other constraint prims
    joint = re.findall(r'^\s*def (Physics\w*Joint\w*|"Physics\w*Joint\w*")',
                       usd_text, re.MULTILINE)
    if joint:
        problems.append(f"{len(joint)} constraint prim(s) present "
                         f"(e.g. {joint[0].strip('\"')}) — the SPEC allows "
                         "no joints")

    # 3. the stage must be self-contained: no composition arcs to files
    for arc in ("references", "payload", "subLayers", "inherits", "variants"):
        hits = re.findall(rf"^\s*(prepend |append |add )?{arc}\s*=\s*[@<\[]",
                          usd_text, re.MULTILINE)
        if hits:
            problems.append(f"composition arc '{arc}' present ({len(hits)}) — "
                            "the artifact must be a single self-contained "
                            "file")

    # 4. no authored motion: the SPEC drops both bodies at rest
    if re.search(r"^\s*(vector3f|vector3d|float3)\s+physics:velocity\s*=\s*"
                 r"\((?!\s*0(\.0*)?\s*,\s*0(\.0*)?\s*,\s*0(\.0*)?\s*\)\s*;?\s*$)",
                 usd_text, re.MULTILINE):
        problems.append("non-zero physics:velocity authored — bodies must be "
                        "spawned at rest")
    if re.search(r"^\s*physics:drive\w*\s*=", usd_text, re.MULTILINE):
        problems.append("physics:drive* authored — motion must come from "
                        "gravity alone")

    return (not problems), {"violations": problems}


def gate_energy(y, vy, mass):
    """G6: mechanical energy never increases (tolerance 0.5% of E0)."""
    n = len(y)
    e0 = mass * G * float(y[0])
    if e0 <= 0:
        return False, {"reason": "initial potential energy not positive",
                       "E0_J": round(e0, 4)}
    E = mass * G * y + 0.5 * mass * vy ** 2
    dE = np.diff(E)
    worst = float(dE.max()) if dE.size else 0.0
    ok_gain = worst <= ENERGY_TOL * e0
    ok_total = float(E[-1]) <= e0 + ENERGY_TOL * e0
    return (ok_gain and ok_total), {
        "E0_J": round(e0, 4),
        "E_final_J": round(float(E[-1]), 4),
        "max_step_gain_J": round(worst, 5),
        "max_step_gain_allowed_J": round(ENERGY_TOL * e0, 5),
    }


def check_body(name, y, vy, mass_expected, meta, apply_bounce):
    gates = {}
    y0 = float(y[0])
    # G1: body sampled at every step, and the mass PhysX actually
    # constructed matches the spec's authored mass (catches "mass = 0"
    # falling back to a default-density mass, and a wrong-mass scene).
    m_read = meta.get("mass")
    mass_ok = (m_read is not None
               and abs(m_read - mass_expected) <= MASS_TOL * mass_expected)
    g1 = len(y) == STEPS and mass_ok
    gates["G1_loads"] = {
        "passed": bool(g1),
        "detail": {"steps_sampled": int(len(y)),
                   "mass_kg": m_read,
                   "mass_expected_kg": mass_expected},
    }
    if not g1:
        return gates, False

    ok2, d2, contact_idx = gate_freefall(y, vy, y0)
    gates["G2_freefall"] = {"passed": bool(ok2), "detail": d2}
    ok3, d3 = gate_contact_time(contact_idx, y0)
    gates["G3_contact_time"] = {"passed": bool(ok3), "detail": d3}
    ok4, d4 = gate_resting(y)
    gates["G4_resting"] = {"passed": bool(ok4), "detail": d4}
    if apply_bounce:
        ok5, d5 = gate_bounce_apex(y, contact_idx, y0)
        gates["G5_bounce_apex"] = {"passed": bool(ok5), "detail": d5}
    else:
        ok5 = True
    ok6, d6 = gate_energy(y, vy, meta["mass"])
    gates["G6_energy"] = {"passed": bool(ok6), "detail": d6}

    # The drop height is part of the spec: the first sampled height must
    # sit near the authored one (within 1% + 5 mm), so a mutant that moves
    # the spawn height fails G2 even if its fall is well integrated.
    expected_h = expected_height(name)
    height_err = abs(y0 - expected_h)
    height_ok = height_err <= 0.01 * expected_h + 0.005
    gates["G2_freefall"]["detail"]["y0_m"] = round(y0, 4)
    gates["G2_freefall"]["detail"]["y0_expected_m"] = expected_h
    if not height_ok:
        gates["G2_freefall"]["passed"] = False
        gates["G2_freefall"]["detail"]["reason"] = \
            f"spawn height {y0:.3f} m does not match authored {expected_h} m"
    return gates, all(g["passed"] for g in gates.values())


def expected_height(name):
    return H_BALL if name == "Ball" else H_BOX


def main():
    if len(sys.argv) < 3:
        print("usage: check_gates.py <sim_out_dir> <scene.usda> "
              "[--json out.json]", file=sys.stderr)
        return 2
    out_dir = Path(sys.argv[1])
    scene_path = Path(sys.argv[2])
    json_out = None
    if "--json" in sys.argv:
        json_out = Path(sys.argv[sys.argv.index("--json") + 1])

    meta = json.loads((out_dir / "meta.json").read_text())
    traj = np.load(out_dir / "traj.npz")

    verdict = {"gates": {}, "all_gates_passed": False, "bodies": {}}
    all_ok = True

    # G7 first: if the artifact violates the dynamics contract there is no
    # point grading its trajectory, and the verdict must say why.
    try:
        usd_text = scene_path.read_text()
    except (OSError, UnicodeDecodeError) as e:
        ok7, d7 = False, {"violations": [
            f"artifact is not a readable ASCII stage: {e}"]}
    else:
        ok7, d7 = gate_contract(usd_text)
    verdict["gates"]["G7_contract"] = {"passed": bool(ok7), "detail": d7}
    all_ok = all_ok and ok7

    for body, mass_exp, bounce in (("Box", M_BOX, False),
                                   ("Ball", M_BALL, True)):
        key = body.lower()
        if not meta["sampled"].get(f"/World/{body}", False):
            verdict["bodies"][body] = {"G1_loads": {
                "passed": False,
                "detail": {"reason": "body not sampled by simulator"}}}
            all_ok = False
            continue
        y = traj[f"{key}_y"]
        vy = traj[f"{key}_vy"]
        bmeta = meta["bodies"].get(f"/World/{body}") or {}
        gates, ok = check_body(body, y, vy, mass_exp, bmeta, bounce)
        # Both bodies must obey the same physics; G5 applies to the ball
        # only.  Report per body under bodies[body].
        verdict["bodies"][body] = gates
        all_ok = all_ok and ok

    # Top-level gate list: a gate passes only if it passes for every body
    # it applies to.
    gate_names = ["G1_loads", "G2_freefall", "G3_contact_time",
                  "G4_resting", "G6_energy"]
    ball_gates = verdict["bodies"].get("Ball", {})
    box_gates = verdict["bodies"].get("Box", {})
    for g in gate_names:
        parts = []
        for bg in (box_gates, ball_gates):
            if g in bg:
                parts.append(bg[g]["passed"])
        verdict["gates"][g] = {"passed": bool(parts and all(parts))}
    if "G5_bounce_apex" in ball_gates:
        verdict["gates"]["G5_bounce_apex"] = {
            "passed": bool(ball_gates["G5_bounce_apex"]["passed"]),
            "detail": ball_gates["G5_bounce_apex"]["detail"],
        }

    verdict["all_gates_passed"] = bool(all_ok)
    text = json.dumps(verdict, indent=2) + "\n"
    print(text)
    if json_out:
        json_out.write_text(text)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
