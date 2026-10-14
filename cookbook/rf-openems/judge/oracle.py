"""Independent analytic oracles for the rf-openems demo.

Hammerstad-Jensen closed-form microstrip Z0 / eeff, and the quasi-static
patch resonance estimate. Written from the published equations (Hammerstad &
Jensen, 1980; Balanis, *Antenna Theory* 4th ed.).

No MEEP import — pure Python so the judge can run it standalone.
"""
import math

C0 = 299792458.0   # m/s


def microstrip_hammerstad_jensen(w_m, h_m, er):
    """Characteristic impedance and effective permittivity of a microstrip
    line per Hammerstad-Jensen (1980). W in m, h in m, er dimensionless."""
    Wh = w_m / h_m
    # effective permittivity
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / Wh) ** -0.5
    if Wh >= 1:
        # add the dispersion correction for wide strips ~ negligible at 2.45 GHz
        ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / Wh) ** -0.5
    # Z0
    if Wh < 1:
        Z0 = 60 / math.sqrt(ee) * math.log(8 / Wh + 0.25 * Wh)
    else:
        Z0 = 120 * math.pi / (math.sqrt(ee) *
                              (Wh + 1.393 + 0.667 * math.log(Wh + 1.444)))
    return Z0, ee


def patch_resonance_ghz(L_m, h_m, er):
    """Quasi-static dominant-mode resonance of a rectangular patch: f = c /
    (2 (L + dL) sqrt(eeff)), with Hammerstad fringing correction."""
    W = L_m * 1.25  # width not needed for this order of estimate; set after
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 * h_m / W) ** -0.5
    dL = 0.412 * h_m * ((ee + 0.3) * (W / h_m + 0.264)) / \
         ((ee - 0.258) * (W / h_m + 0.8))
    return C0 / (2 * (L_m + dL) * math.sqrt(ee))


ANTENNA_GATES = dict(
    # physical sanity (gate G2)
    sub_h_min_mm=0.5, sub_h_max_mm=2.5,
    patch_L_min_mm=20.0, patch_L_max_mm=45.0,
    er_min=3.5, er_max=5.0,
    resolution_min=4, resolution_max=18,
    # RF performance
    s11_target_db=-10.0,
    f_target_ghz=2.45, f_res_tol=0.02,      # ±2 %
    s11_conv_delta_db=1.0,
    # oracle
    z0_tol=0.03,                            # 3 %
)

Z0_50_WIDTH_MM = 3.1     # what the verification case uses
Z0_50_ER = 4.4
Z0_50_H_MM = 1.6
