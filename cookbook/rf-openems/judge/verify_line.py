"""Judge-owned oracle simulation: effective permittivity of a ~50-ohm
microstrip line on FR-4, measured by openEMS and compared with the
Hammerstad-Jensen closed form.

The sim is a straight strip over a grounded FR-4 slab, excited by a pure
E-field sheet near one end, with PML-terminated ends. The guided
propagation constant beta is extracted from the phase slope of five
voltage probes under the strip (linear fit of unwrapped DFT phase vs
position) and compared with the analytic value:

    eeff = (beta * c0 / omega)^2   vs   microstrip_hammerstad_jensen(...)

This validates the whole toolchain (geometry, substrate, mesh, FDTD)
against a result the artifact cannot influence.
"""
import os, json, tempfile
import numpy as np

for _a, _v in (("float", float), ("int", int), ("bool", bool)):
    if not hasattr(np, _a):
        setattr(np, _a, _v)

from oracle import microstrip_hammerstad_jensen, fr4_kappa_s_per_m, \
    LINE_W_MM, LINE_H_MM, LINE_ER, LINE_TAND

XPS = np.array([30.0, 45.0, 60.0, 75.0, 90.0])   # probe positions, mm
XFE = 8.0                                         # feed position, mm
XMIN, XMAX = 0.0, 110.0
F0 = 2.45e9


def _dft(t, val, freq):
    """Single-sided DFT of a pulse — same math as openEMS.utilities but
    re-implemented here so the judge's number does not share a code path
    with the artifact."""
    t = np.asarray(t); val = np.asarray(val)
    dt = t[1] - t[0]
    out = np.zeros(len(freq), dtype=complex)
    for k, f in enumerate(freq):
        out[k] = np.sum(val * np.exp(-2j * np.pi * f * t))
    return 2.0 * out * dt


def run_verification(mesh_res=1.0, sim_path=None, numThreads=1):
    import CSXCAD
    from openEMS import openEMS
    from openEMS.physical_constants import C0

    W, h, er, tanD = LINE_W_MM, LINE_H_MM, LINE_ER, LINE_TAND
    sim_path = sim_path or tempfile.mkdtemp(prefix="rf-line-")

    CSX = CSXCAD.ContinuousStructure()
    FDTD = openEMS(NrTS=60000, EndCriteria=1e-4)
    FDTD.SetCSX(CSX)
    mesh = CSX.GetGrid(); mesh.SetDeltaUnit(1e-3)
    FDTD.SetGaussExcite(F0, F0 * 0.5)
    FDTD.SetBoundaryCond(['PML_8', 'PML_8', 'MUR', 'MUR', 'PEC', 'MUR'])

    y0, y1 = -W/2 - 15.0, W/2 + 15.0
    sub = CSX.AddMaterial('FR4')
    sub.SetMaterialProperty(epsilon=er, kappa=fr4_kappa_s_per_m(tanD, er, F0))
    sub.AddBox([XMIN, y0, 0], [XMAX, y1, h])
    pec = CSX.AddMetal('PEC')
    pec.AddBox([XMIN, -W/2, h - 0.05], [XMAX, W/2, h + 0.05], priority=10)

    def lines(a, b, r):
        n = max(2, int(np.ceil((b - a) / r)))
        return np.linspace(a, b, n + 1)

    third = mesh_res / 3.0
    mx = np.unique(np.concatenate([lines(XMIN, XMAX, mesh_res),
                                   [XFE - 0.4, XFE + 0.4], XPS]))
    my = np.unique(np.concatenate([
        lines(y0, -W/2 - third, 2.5)[:-1],
        lines(-W/2 - third, W/2 + third, 0.35),
        lines(W/2 + third, y1, 2.5)[1:]]))
    mz = np.unique(np.concatenate([[0.0], np.linspace(0, h, 7)[1:-1], [h],
                                   lines(h + 2.0, h + 15.0, 2.5)[1:]]))
    mesh.SetLines('x', mx); mesh.SetLines('y', my); mesh.SetLines('z', mz)

    exc = CSX.AddExcitation('e_feed', exc_type=0, exc_val=[0, 0, -1.0])
    exc.AddBox([XFE - 0.4, -W/2, 0], [XFE + 0.4, W/2, h], priority=20)
    for k, xp in enumerate(XPS):
        pr = CSX.AddProbe('u%d' % k, p_type=0, weight=1)
        pr.AddBox([xp, 0, 0], [xp, 0, h])

    FDTD.Run(sim_path, cleanup=True, verbose=0, numThreads=numThreads)

    freq = np.linspace(2.2e9, 2.7e9, 26)
    Us = []
    for k in range(len(XPS)):
        t, u = np.loadtxt(os.path.join(sim_path, 'u%d' % k),
                          comments='%', unpack=True)
        Us.append(_dft(t, u, freq))
    Us = np.array(Us)

    _, eeff_HJ = microstrip_hammerstad_jensen(W * 1e-3, h * 1e-3, er)
    i = int(np.argmin(np.abs(freq - F0)))
    ph = np.unwrap(np.angle(Us[:, i]))
    beta = -np.polyfit(XPS * 1e-3, ph, 1)[0]
    eeff = (beta * C0 / (2 * np.pi * freq[i])) ** 2
    return {
        "eeff_sim": float(eeff),
        "eeff_HJ": float(eeff_HJ),
        "delta_pct": float(abs(eeff - eeff_HJ) / eeff_HJ * 100.0),
        "freq_GHz": float(freq[i] / 1e9),
        "probes_mm": XPS.tolist(),
        "phases_deg": np.degrees(ph).tolist(),
        "mesh_res_mm": mesh_res,
    }


if __name__ == "__main__":
    print(json.dumps(run_verification(), indent=1))
