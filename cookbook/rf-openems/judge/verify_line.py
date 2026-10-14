"""Analytic-oracle verification: 50-ohm microstrip line.

Runs a short MEEP sim of a straight 50 Ω microstrip on FR-4, extracts the
effective permittivity from phase delay, and checks it against the
Hammerstad-Jensen closed-form. Gate G6 compares |eeff_meep - eeff_HJ| / eeff_HJ
<= 3 %.
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")

import numpy as np
import meep as mp

from .oracle import microstrip_hammerstad_jensen, Z0_50_WIDTH_MM, Z0_50_ER, Z0_50_H_MM
from .sim_engine import meep_f, fr4, GHZ_PER_MEEP


def run_verification(resolution=10, quiet=True):
    """Straight through-line, lumped feed, two Ez monitors 10 mm apart.
    Returns dict: eeff_meep, eeff_HJ, delta_pct, s11_db."""
    ghz = 2.45
    f_t = meep_f(ghz)
    df = f_t
    sx, sy, sz = 50.0, 30.0, 12.0
    h, W, er = Z0_50_H_MM, Z0_50_WIDTH_MM, Z0_50_ER

    cell = mp.Vector3(sx, sy, sz)
    z0 = -sz/2 + 3.0
    sub = mp.Block(center=mp.Vector3(0, 0, z0 + h/2), size=mp.Vector3(sx, sy, h),
                   material=fr4(er, 0.02))
    gnd = mp.Block(center=mp.Vector3(0, 0, z0 - 0.05), size=mp.Vector3(sx, sy, 0.1),
                   material=mp.metal)
    line = mp.Block(center=mp.Vector3(0, 0, z0 + h + 0.05),
                    size=mp.Vector3(sx, W, 0.1), material=mp.metal)
    feed = mp.Source(src=mp.GaussianSource(f_t, fwidth=df), component=mp.Ez,
                     center=mp.Vector3(-sx/2 + 6, 0, z0 + h/2),
                     size=mp.Vector3(0.5, W*0.9, h*0.9))

    def build(with_line):
        geo = [sub, gnd] + ([line] if with_line else [])
        s = mp.Simulation(cell_size=cell, resolution=resolution,
                          boundary_layers=[mp.PML(1.5)],
                          geometry=geo, sources=[feed])
        mr = s.add_dft_fields([mp.Ez], f_t, f_t*0.25, 11,
                              center=mp.Vector3(-sx/2 + 10, 0, z0 + h/2),
                              size=mp.Vector3(0, W*0.9, h*0.9))
        mt = s.add_dft_fields([mp.Ez], f_t, f_t*0.25, 11,
                              center=mp.Vector3(sx/2 - 10, 0, z0 + h/2),
                              size=mp.Vector3(0, W*0.9, h*0.9))
        return s, mr, mt

    # incident
    s_n, mr_n, mt_n = build(False)
    s_n.run(until=80.0)
    inc_r = np.array([np.sum(s_n.get_dft_array(mr_n, mp.Ez, i)) for i in range(11)])
    inc_t = np.array([np.sum(s_n.get_dft_array(mt_n, mp.Ez, i)) for i in range(11)])

    s_d, mr_d, mt_d = build(True)
    s_d.run(until=200.0)
    tot_r = np.array([np.sum(s_d.get_dft_array(mr_d, mp.Ez, i)) for i in range(11)])
    tot_t = np.array([np.sum(s_d.get_dft_array(mt_d, mp.Ez, i)) for i in range(11)])

    gamma = (tot_r - inc_r) / inc_r
    trans = tot_t / inc_t
    freqs = np.linspace(f_t - f_t*0.125, f_t + f_t*0.125, 11) * GHZ_PER_MEEP
    i = int(np.argmin(np.abs(freqs - ghz)))
    beta = -np.unwrap(np.angle(trans)) / (sx - 20.0)
    eeff = (beta * GHZ_PER_MEEP / (2 * np.pi * freqs)) ** 2

    Z0_HJ, eeff_HJ = microstrip_hammerstad_jensen(Z0_50_WIDTH_MM*1e-3,
                                                  Z0_50_H_MM*1e-3, Z0_50_ER)
    return {
        "eeff_meep": float(np.real(eeff[i])),
        "eeff_HJ": float(eeff_HJ),
        "delta_pct": float(abs(np.real(eeff[i]) - eeff_HJ) / eeff_HJ * 100.0),
        "s11_db": float(20 * np.log10(np.abs(gamma[i]) + 1e-12)),
        "freq_GHz": float(freqs[i]),
    }


if __name__ == "__main__":
    import json, sys
    res = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    r = run_verification(resolution=res)
    print(json.dumps(r, indent=1))
