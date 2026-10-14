# =============================================================================
# rf-openems demo artifact: 2.45 GHz probe-fed microstrip patch antenna on FR-4.
#
# Written from scratch for this demo. Geometry equations per Balanis,
# "Antenna Theory" 4th ed., and Pozar, "Microwave Engineering". The judge
# reads the parameter block below, runs this script, and re-derives the
# result from the raw openEMS port time series itself.
#
# Contract (see ../SPEC.md):
#   * parameter block: the 8 names below, literal constants, mm / GHz units
#   * def simulate(p, sim_path) -> {"freqs_GHz", "S11_dB"}; runs openEMS and
#     leaves the raw port files (port_ut_1, port_it_1) in sim_path
#   * __main__ writes antenna_results.json into the current directory and
#     prints one line: RESULT S11_dB_at_<f_target>=<x> f_res_GHz=<y>
# =============================================================================

f_target_ghz = 2.45     # GHz  -- target resonance
er           = 4.4      # FR-4 relative permittivity
tanD         = 0.02     # FR-4 loss tangent
sub_h        = 1.6      # mm   -- substrate thickness
patch_L      = 27.6     # mm   -- patch length along the resonant direction
patch_W      = 37.0     # mm   -- patch width
feed_inset   = 8.0     # mm   -- probe feed inset from the radiating edge
mesh_res     = 1.2      # mm   -- max mesh step inside the substrate footprint

import os
import numpy as np
# numpy>=1.24 removed the aliases this openEMS build still uses
for _a, _v in (("float", float), ("int", int), ("bool", bool)):
    if not hasattr(np, _a):
        setattr(np, _a, _v)

import CSXCAD
from openEMS import openEMS

EPS0 = 8.854187817e-12


def simulate(p, sim_path):
    """Run the FDTD sim. p: dict of the parameter block. sim_path receives the
    raw openEMS outputs (port_ut_1, port_it_1). Returns the S11 sweep dict."""
    f0 = p["f_target_ghz"] * 1e9
    h, L, W = p["sub_h"], p["patch_L"], p["patch_W"]
    res = p["mesh_res"]

    CSX = CSXCAD.ContinuousStructure()
    FDTD = openEMS(NrTS=60000, EndCriteria=1e-4)
    FDTD.SetCSX(CSX)
    mesh = CSX.GetGrid()
    mesh.SetDeltaUnit(1e-3)      # all coordinates in mm
    FDTD.SetGaussExcite(f0, f0 * 0.5)
    FDTD.SetBoundaryCond(['PML_8'] * 6)

    # substrate + margins
    sub_m = 9.0        # substrate extends this far beyond the patch
    air_l = 6.0        # lateral air beyond substrate edge
    air_up = 12.0      # air above the patch
    air_dn = 5.0       # air below the ground plane

    sub = CSX.AddMaterial('FR4')
    kappa = p["tanD"] * 2 * np.pi * f0 * EPS0 * p["er"]   # S/m
    sub.SetMaterialProperty(epsilon=p["er"], kappa=kappa)
    sub.AddBox([-sub_m, -W/2 - sub_m, 0], [L + sub_m, W/2 + sub_m, h])

    metal = CSX.AddMetal('PEC')
    metal.AddBox([-sub_m, -W/2 - sub_m, -0.05],
                 [L + sub_m, W/2 + sub_m, 0.05], priority=10)        # ground
    metal.AddBox([0, -W/2, h - 0.05],
                 [L, W/2, h + 0.05], priority=10)                    # patch

    # ---- mesh: fine inside the substrate footprint, coarse in air ----
    def lines(a, b, r):
        n = max(2, int(np.ceil((b - a) / r)))
        return np.linspace(a, b, n + 1)

    fx = p["feed_inset"]
    # mesh lines pin the metal edges so geometry does not snap differently
    # at different mesh_res (convergence gate G8 depends on this)
    mx = np.unique(np.concatenate([
        lines(-sub_m - air_l, -sub_m, 2.5),
        lines(-sub_m, L + sub_m, res)[1:-1],
        lines(L + sub_m, L + sub_m + air_l, 2.5),
        [0.0, L, fx - 0.4, fx, fx + 0.4]]))
    my = np.unique(np.concatenate([
        lines(-W/2 - sub_m - air_l, -W/2 - sub_m, 2.5),
        lines(-W/2 - sub_m, W/2 + sub_m, res)[1:-1],
        lines(W/2 + sub_m, W/2 + sub_m + air_l, 2.5),
        [-W/2, W/2, -0.4, 0.0, 0.4]]))
    mz = np.unique(np.concatenate([
        lines(-air_dn, 0, 1.0),
        np.linspace(0, h, 6)[1:-1],
        lines(h, h + air_up, 1.0)]))
    mesh.SetLines('x', mx); mesh.SetLines('y', my); mesh.SetLines('z', mz)

    # probe feed: 50 ohm lumped port between ground and patch at the inset
    port = FDTD.AddLumpedPort(1, 50.0,
                              [fx - 0.4, -0.4, 0], [fx + 0.4, 0.4, h],
                              'z', excite=1.0, priority=5,
                              edges2grid='xy')

    FDTD.Run(sim_path, cleanup=True, verbose=0, numThreads=1)

    freq = np.linspace(2.2e9, 2.7e9, 51)
    port.CalcPort(sim_path, freq)
    s11_db = 20 * np.log10(np.abs(port.uf_ref / port.uf_inc) + 1e-15)
    return {"freqs_GHz": (freq / 1e9).tolist(), "S11_dB": s11_db.tolist()}


def main():
    import json
    # openEMS chdir()s into the sim path — resolve all outputs absolutely
    results_path = os.path.abspath("antenna_results.json")
    p = dict(f_target_ghz=f_target_ghz, er=er, tanD=tanD, sub_h=sub_h,
             patch_L=patch_L, patch_W=patch_W, feed_inset=feed_inset,
             mesh_res=mesh_res)
    r = simulate(p, os.path.abspath("oems_sim"))
    s11, fr = np.asarray(r["S11_dB"]), np.asarray(r["freqs_GHz"])
    i_res = int(np.nanargmin(s11))
    i_tgt = int(np.argmin(np.abs(fr - f_target_ghz)))
    out = dict(params=p, S11_dB_at_target=float(s11[i_tgt]),
               f_res_GHz=float(fr[i_res]),
               freqs_GHz=r["freqs_GHz"], S11_dB=r["S11_dB"])
    with open(results_path, "w") as fh:
        json.dump(out, fh, indent=1)
    print("RESULT S11_dB_at_{:.2f}GHz={:.2f} f_res_GHz={:.3f}".format(
        f_target_ghz, out["S11_dB_at_target"], out["f_res_GHz"]))


if __name__ == "__main__":
    main()
