"""Independent analytic oracles for the rf-openems demo (pure Python, no
openEMS import — the judge can run it standalone).

- microstrip_hammerstad_jensen: closed-form quasi-static Z0 / effective
  permittivity of a microstrip line (Hammerstad & Jensen 1980).
- patch_resonance_ghz: quasi-static dominant-mode resonance of a rectangular
  patch incl. Hammerstad fringing correction (Balanis, Antenna Theory).

These are the acceptance references the measured openEMS numbers are checked
against. They never touch the artifact.
"""
import math

C0 = 299792458.0   # m/s
EPS0 = 8.854187817e-12


def microstrip_hammerstad_jensen(w_m, h_m, er):
    """(Z0, eeff) of a microstrip line, Hammerstad-Jensen 1980 closed form."""
    Wh = w_m / h_m
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / Wh) ** -0.5
    if Wh < 1:
        Z0 = 60 / math.sqrt(ee) * math.log(8 / Wh + 0.25 * Wh)
    else:
        Z0 = 120 * math.pi / (math.sqrt(ee) *
                              (Wh + 1.393 + 0.667 * math.log(Wh + 1.444)))
    return Z0, ee


def patch_resonance_ghz(L_m, h_m, W_m, er):
    """Quasi-static dominant-mode (TM010) resonance of a rectangular patch
    with Hammerstad fringing extension. Returns GHz."""
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 * h_m / W_m) ** -0.5
    dL = 0.412 * h_m * ((ee + 0.3) * (W_m / h_m + 0.264)) / \
         ((ee - 0.258) * (W_m / h_m + 0.8))
    return C0 / (2 * (L_m + dL) * math.sqrt(ee)) / 1e9


def fr4_kappa_s_per_m(tanD, er, f_hz):
    """Substrate conductivity corresponding to a loss tangent."""
    return tanD * 2 * math.pi * f_hz * EPS0 * er


# ---------------------------------------------------------------- gates ---
ANTENNA_GATES = dict(
    # G2 physical sanity
    er_min=3.5, er_max=5.0,
    sub_h_min_mm=0.5, sub_h_max_mm=2.5,
    patch_L_min_mm=20.0, patch_L_max_mm=45.0,
    patch_W_min_mm=20.0, patch_W_max_mm=55.0,
    mesh_res_min_mm=0.4, mesh_res_max_mm=2.0,
    # G4/G5 RF spec
    s11_target_db=-10.0,
    f_target_ghz=2.45, f_res_tol=0.02,       # resonance within +/-2 %
    # G6 raw-data cross-check (judge re-derives S11 from openEMS port files)
    crosscheck_tol_db=1.5,
    # G7 oracle: simulated microstrip eeff vs Hammerstad-Jensen
    eeff_tol=0.04,                            # <= 4 %
    # G8 convergence: spec must still hold at mesh_res*0.75
    conv_mesh_factor=0.75,
    conv_fres_tol=0.015,                      # fine-mesh f_res within 1.5 %
)

# Verification line (oracle): ~50 ohm microstrip on 1.6 mm FR-4.
LINE_W_MM = 3.08
LINE_H_MM = 1.6
LINE_ER = 4.4
LINE_TAND = 0.02
