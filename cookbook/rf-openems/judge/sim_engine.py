"""Shared FDTD helpers for the rf-openems demo (lumped-feed microstrip + patch).

Units: 1 meep-length = 1 mm.  f_meep = f[GHz] / 299.792458.
Every consumer imports from here so the judge, the examples, and the mutants
all exercise identical physics.
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")

import numpy as np
import meep as mp

GHZ_PER_MEEP = 299.792458


def meep_f(ghz):
    return ghz / GHZ_PER_MEEP


def fr4(er=4.4, tan_d=0.02):
    # loss tangent -> D-conductivity at ~2.45 GHz; sign convention per meep docs
    return mp.Medium(epsilon=er, D_conductivity=2 * np.pi * meep_f(2.45) * tan_d / er)


def simulate_antenna(p, resolution, verbose=False):
    """Run a patch-antenna S11 sweep.

    p: dict with keys
        f_target_ghz, er, tanD, patch_L, patch_W, sub_h,
        feed_inset (mm from the radiating edge), line_L (mm of feed line
        beyond the patch edge), grid clearance parameters.
    resolution: cells per mm.
    Returns dict(freqs_ghz, s11_db, s11_complex, wall_s, nsteps).
    """
    f_t = meep_f(p["f_target_ghz"])
    df = 1.1 * f_t                 # covers roughly DC..5 GHz
    fscan_lo, fscan_hi = 2.0, 3.0  # GHz band the S11 sweep reports
    nfreq = 41
    f_lo, f_hi = meep_f(fscan_lo), meep_f(fscan_hi)

    L, W = p["patch_L"], p["patch_W"]
    h = p["sub_h"]
    li = p["feed_inset"]
    line_L = p["line_L"]

    # cell: x along feed, y across patch, z vertical
    gnd_margin = 8.0
    sx = line_L + L + 14.0        # a bit of air behind patch + pml
    sy = W + 2 * gnd_margin
    air = 8.0                     # air above patch
    sz = h + air + 3.0            # 3 mm margin below ground for pml
    cell = mp.Vector3(sx, sy, sz)

    # z-stack: ground at z=0 (top of cell-offset stack); substrate z in [0,h]; air above
    sub = mp.Block(center=mp.Vector3(0, 0, h/2 - sz/2 + 3.0),
                   size=mp.Vector3(sx, sy, h), material=fr4(p["er"], p["tanD"]))
    # shift z so sub spans [h/2?]. easier: define z0 = -sz/2 + 3 (bottom of substrate)
    z0 = -sz/2 + 3.0
    sub = mp.Block(center=mp.Vector3(0, 0, z0 + h/2),
                   size=mp.Vector3(sx, sy, h), material=fr4(p["er"], p["tanD"]))
    gnd = mp.Block(center=mp.Vector3(0, 0, z0 - 0.05),
                   size=mp.Vector3(sx, sy, 0.1), material=mp.metal)

    # feed line + patch, at top of substrate z1 = z0 + h
    z1 = z0 + h
    # patch spans x = [x0, x0+L]; line runs from cell edge to patch edge
    x0 = -sx/2 + 3.0 + line_L
    line_y = p.get("line_w", 3.1)
    metal = [mp.Block(center=mp.Vector3(x0 + L/2, 0, z1 + 0.05),
                      size=mp.Vector3(L, W, 0.1), material=mp.metal),
             mp.Block(center=mp.Vector3(x0 - line_L/2, 0, z1 + 0.05),
                      size=mp.Vector3(line_L, line_y, 0.1), material=mp.metal)]
    geom = [sub, gnd] + metal

    # lumped feed: vertical Ez sheet in the feed port at the line/patch junction
    feed_x = x0 - li
    src = mp.Source(src=mp.GaussianSource(f_t, fwidth=df), component=mp.Ez,
                    center=mp.Vector3(feed_x, 0, z0 + h/2),
                    size=mp.Vector3(0.5, line_y*0.9, h*0.9))

    # reflection monitor: 2 mm before the strip end (air side), mid-y, mid-z of substrate
    mon_x = x0 - line_L + 2.0
    def build():
        s = mp.Simulation(cell_size=cell, resolution=resolution,
                          boundary_layers=[mp.PML(1.5)],
                          geometry=geom, sources=[src])
        mon = s.add_dft_fields([mp.Ez], (f_lo+f_hi)/2, f_hi-f_lo, nfreq,
                               center=mp.Vector3(mon_x, 0, z0 + h/2),
                               size=mp.Vector3(0, line_y*0.9, h*0.9))
        return s, mon

    # --- normalisation run (feed line only, no patch): incident wave ------ #
    geom_n = [sub, gnd, mp.Block(center=mp.Vector3((mon_x + -sx/2)/2 + 2, 0, z1 + 0.05),
                                 size=mp.Vector3(mon_x + sx/2 + 6, line_y, 0.1),
                                 material=mp.metal)]
    s_n = mp.Simulation(cell_size=cell, resolution=resolution,
                        boundary_layers=[mp.PML(1.5)],
                        geometry=geom_n, sources=[src])
    mon_n = s_n.add_dft_fields([mp.Ez], (f_lo+f_hi)/2, f_hi-f_lo, nfreq,
                               center=mp.Vector3(mon_x, 0, z0 + h/2),
                               size=mp.Vector3(0, line_y*0.9, h*0.9))
    s_n.run(until=100.0)
    inc = np.array([np.sum(s_n.get_dft_array(mon_n, mp.Ez, i)) for i in range(nfreq)])

    # --- device run -------------------------------------------------------- #
    s_d, mon_d = build()
    s_d.run(until=250.0)
    tot = np.array([np.sum(s_d.get_dft_array(mon_d, mp.Ez, i)) for i in range(nfreq)])

    gamma = (tot - inc) / inc
    freqs = np.linspace(f_lo, f_hi, nfreq) * GHZ_PER_MEEP
    s11_db = 20 * np.log10(np.abs(gamma) + 1e-12)
    return {"freqs_ghz": freqs.tolist(),
            "s11_db": s11_db.tolist(),
            "s11_complex_real": np.real(gamma).tolist(),
            "s11_complex_imag": np.imag(gamma).tolist()}
