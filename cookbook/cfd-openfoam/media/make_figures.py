#!/usr/bin/env python3
"""Figures for the cfd-openfoam demo — every plotted number comes from a
file the judge or solver wrote during a real run (verdict JSONs, --trace
output).  No invented data: if a source file is missing, this exits 1.

Usage: make_figures.py <judge_runs_dir> <outdir>
Writes result.png and loop.png (200 dpi).
"""

import json
import math
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.tri as tri
import numpy as np
from scipy.interpolate import griddata

# dataviz reference palette (validated: CVD-safe on light surface)
BLUE = '#2a78d6'    # series 1 — measured / good case
ORANGE = '#eb6834'  # series 2 — analytic or second series
RED = '#d03b3b'     # status: critical — failing data
GREEN = '#0ca30c'   # status: good — pass line / PASS marker
INK = '#0b0b0b'
INK2 = '#52514e'
GRID = '#e5e4e0'

plt.rcParams.update({
    'font.size': 11, 'axes.edgecolor': INK2, 'axes.labelcolor': INK,
    'xtick.color': INK2, 'ytick.color': INK2,
    'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.8,
    'axes.axisbelow': True, 'figure.facecolor': 'white',
    'axes.facecolor': 'white',
})


def need(path):
    if not os.path.isfile(path):
        sys.exit('make_figures: missing source file %s — run the judge '
                 'first (see make_media.sh)' % path)
    return path


def load_json(path):
    with open(path) as f:
        return json.load(f)


def load_xy(path):
    xs, cols = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = [float(v) for v in line.split()]
                xs.append(parts[0])
                cols.append(parts[1:])
    return xs, [list(c) for c in zip(*cols)]


# ---------------------------------------------------------------------------
# result.png — the key figure: four panels
#   (a) Poiseuille u(y) vs analytic parabola with the 2 % band  (gate 3)
#   (b) Cavity centreline u, v vs Ghia 1982 points              (gate 5)
#   (c) Poiseuille L2 error vs mesh, log-log, fitted order      (gate 4)
#   (d) Cavity |U| field at the final traced time               (gate 5 context)
# ---------------------------------------------------------------------------
def make_result(runs, outdir):
    poi_v = load_json(need(os.path.join(
        runs, 'verdicts', '05_poiseuille_good.json')))
    cav_v = load_json(need(os.path.join(
        runs, 'verdicts', '04_cavity_good.json')))

    fig = plt.figure(figsize=(12.8, 9.6))
    gs = fig.add_gridspec(2, 2, hspace=0.34, wspace=0.24,
                          left=0.07, right=0.97, top=0.90, bottom=0.08)

    # ---- (a) poiseuille profile vs analytic, 2 % band ---------------------
    ax = fig.add_subplot(gs[0, 0])
    ys, ucols = load_xy(need(os.path.join(
        runs, 'poiseuille_traces', 'samples', 'centerline_U.xy')))
    u = ucols[0]
    g3 = {g['gate']: g for g in poi_v['gates']}[3]['details']
    l2 = g3['l2_error']
    # analytic parabola u(y) = 1 - ((y-h)/h)^2, h = 0.5  (SPEC gate 3)
    ana = [1.0 - ((y - 0.5) / 0.5) ** 2 for y in ys]
    band = [0.02 * 1.0] * len(ys)   # gate rule: normalised L2 err <= 0.02
    ax.fill_between(ys, [a - b for a, b in zip(ana, band)],
                    [a + b for a, b in zip(ana, band)],
                    color=BLUE, alpha=0.12, label='2 % L2 band (gate 3)',
                    linewidth=0)
    ax.plot(ys, ana, color=ORANGE, lw=2, label='analytic Poiseuille')
    ax.plot(ys, u, color=BLUE, lw=2, linestyle='--',
            label='icoFoam (measured)')
    ax.set_xlabel('y (m)')
    ax.set_ylabel('u (m/s)')
    ax.set_title('(a) Poiseuille profile vs analytic — gate 3', fontsize=12)
    ax.text(0.03, 0.06, 'L2 error = %.4f  <=  0.02  PASS' % l2,
            transform=ax.transAxes, fontsize=10, color=INK,
            bbox=dict(facecolor='white', edgecolor=GREEN, boxstyle='round',
                      pad=0.3))
    ax.legend(loc='upper left', fontsize=9, frameon=True, framealpha=0.95)

    # ---- (b) cavity centrelines vs Ghia ----------------------------------
    ax = fig.add_subplot(gs[0, 1])
    gx_u, gu_cols = load_xy(need(os.path.join(
        runs, 'cavity_traces', 'samples', 'centerline_u_U.xy')))
    gx_v, gv_cols = load_xy(need(os.path.join(
        runs, 'cavity_traces', 'samples', 'centerline_v_U.xy')))
    g5 = {g['gate']: g for g in cav_v['gates']}[5]['details']
    # same tabulated Ghia et al. (1982) Re=100 data the judge gates on —
    # imported from judge/check_gates.py so figure and gate cannot diverge
    sys.path.insert(0, os.path.join(os.path.dirname(
        os.path.abspath(__file__)), '..', 'judge'))
    try:
        import check_gates as cg
        ghia_u, ghia_v = cg.GHIA_U, cg.GHIA_V
    finally:
        sys.path.pop(0)
    ax.plot(gx_u, gu_cols[0], color=BLUE, lw=2,
            label='u at x=0.5 (measured)')
    ax.plot(gx_v, gv_cols[1],
            color=ORANGE, lw=2, label='v at y=0.5 (measured)')
    gu_sorted = sorted(ghia_u.items())
    gv_sorted = sorted(ghia_v.items())
    ax.plot([p[0] for p in gu_sorted], [p[1] for p in gu_sorted],
            'o', ms=5, color=INK, markerfacecolor='white',
            markeredgewidth=1.2, label='Ghia 1982 u', zorder=3)
    ax.plot([p[0] for p in gv_sorted], [p[1] for p in gv_sorted],
            's', ms=5, color=INK2, markerfacecolor='white',
            markeredgewidth=1.2, label='Ghia 1982 v', zorder=3)
    ax.set_xlabel('position along centreline (m)')
    ax.set_ylabel('velocity (m/s)')
    ax.set_title('(b) Cavity centreline vs Ghia et al. 1982 — gate 5',
                 fontsize=12)
    # PASS box in upper-left inside axes, avoiding data overlap
    # v-curve and Ghia squares are at x=0.6-0.85, y=-0.2; upper-left (0.03, 0.9) is clear
    ax.text(0.03, 0.90,
            'max |u| err = %.4f, |v| err = %.4f  <=  0.02  PASS'
            % (g5['max_u_error'], g5['max_v_error']),
            transform=ax.transAxes, fontsize=10, color=INK, va='top',
            bbox=dict(facecolor='white', edgecolor=GREEN, boxstyle='round',
                      pad=0.3))
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 0.82), fontsize=9,
              frameon=True, framealpha=0.95)

    # ---- (c) mesh convergence log-log ------------------------------------
    ax = fig.add_subplot(gs[1, 0])
    g4 = {g['gate']: g for g in poi_v['gates']}[4]['details']
    ns = sorted(int(k) for k in g4['l2_errors'])
    errs = [g4['l2_errors'][str(n)] for n in ns]
    ax.loglog(ns, errs, 'o-', color=BLUE, lw=2, ms=7, label='measured L2 err')
    # fitted order from the last two levels (the gate's own calculation)
    o2 = g4['orders'][1]
    fit = [errs[-1] * (ns[-1] / n) ** o2 for n in ns]
    ax.loglog(ns, fit, '-', color=ORANGE, lw=1.5,
              label='2nd-order slope (fit: %.2f)' % o2)
    ax.set_ylim(8e-4, 2.2e-1)
    ax.axhline(g3['l2_tol'], color=RED, lw=1.5, linestyle=':')
    ax.annotate('gate 3 pass line: L2 <= 0.02',
                xy=(10, g3['l2_tol']), xytext=(12.5, 0.06),
                fontsize=9, color=RED,
                arrowprops=dict(arrowstyle='-', color=RED, lw=0.8))
    ax.set_xlabel('mesh cells per side N')
    ax.set_ylabel('normalised L2 profile error')
    ax.set_xticks(ns)
    ax.set_xticklabels([str(n) for n in ns])
    ax.set_title('(c) Poiseuille mesh convergence — gate 4', fontsize=12)
    ax.text(0.03, 0.06,
            'observed orders %.2f, %.2f  >=  1.5  PASS'
            % tuple(g4['orders']),
            transform=ax.transAxes, fontsize=10, color=INK,
            bbox=dict(facecolor='white', edgecolor=GREEN, boxstyle='round',
                      pad=0.3))
    ax.legend(loc='upper right', fontsize=9, frameon=True, framealpha=0.95)

    # ---- (d) cavity |U| field at final traced time (continuous cell field + streamlines) -------
    ax = fig.add_subplot(gs[1, 1])
    cent = []
    cc_path = need(os.path.join(runs, 'cavity_traces', 'cellcentres.csv'))
    for line in open(cc_path):
        if line.startswith('x,y') or not line.strip():
            continue
        x, y = line.split(',')
        cent.append((float(x), float(y)))
    times = sorted((d for d in os.listdir(os.path.join(runs,
                   'cavity_traces'))
                   if d.replace('.', '', 1).isdigit()),
                   key=float)
    t_final = times[-1]
    ut_path = need(os.path.join(runs, 'cavity_traces', t_final, 'U'))
    ufield = []
    started = False
    for line in open(ut_path):
        s = line.strip()
        if s.startswith('internalField'):
            started = True
            continue
        if started and s.startswith('(') and s != '(':
            vals = s.strip('()').split()
            if len(vals) >= 2:
                ufield.append((float(vals[0]), float(vals[1])))
    # cell k in the field files corresponds to cell centre k as read from
    # cellcentres.csv (same solver, same mesh, same ordering) — do NOT sort.
    # (A scatter of (x_k, y_k) coloured by |U_k| must reproduce the cavity
    # vortex — fast band along the lid, eye near (0.5, 0.5) — otherwise the
    # pairing is wrong; assert the physical signature instead of trusting
    # the file order.)
    mag = [math.hypot(a, b) for a, b in ufield]
    assert len(mag) == len(cent), (len(mag), len(cent))
    top = max((m for m, c in zip(mag, cent) if c[1] > 0.75), default=0)
    assert top > 0.8, 'lid velocity band not found — field/centre pairing broken'

    X = np.array([c[0] for c in cent])
    Y = np.array([c[1] for c in cent])
    Ux = np.array([u[0] for u in ufield])
    Uy = np.array([u[1] for u in ufield])
    mag = np.array(mag)

    # Continuous cell field using tripcolor on cell centres (triangulation)
    triang = tri.Triangulation(X, Y)
    import matplotlib.colors as mcolors
    cmap = mcolors.LinearSegmentedColormap.from_list(
        'seq_blue', ['#f3f6fb', '#a8c8ec', '#5a9bd8', '#2a78d6', '#123c66'])
    tp = ax.tripcolor(triang, mag, cmap=cmap, vmin=0, vmax=1.0,
                      shading='gouraud', edgecolors='none')
    cb = fig.colorbar(tp, ax=ax, shrink=0.9, pad=0.02)
    cb.set_label('|U| (m/s)')

    # Streamlines: interpolate Ux, Uy onto a regular grid
    xi = np.linspace(0, 1, 61)
    yi = np.linspace(0, 1, 61)
    Xi, Yi = np.meshgrid(xi, yi)
    Ux_grid = griddata((X, Y), Ux, (Xi, Yi), method='linear')
    Uy_grid = griddata((X, Y), Uy, (Xi, Yi), method='linear')
    # Streamplot with density to show primary vortex clearly
    ax.streamplot(Xi, Yi, Ux_grid, Uy_grid, color=INK, linewidth=0.6,
                  density=1.2, arrowsize=0.5, minlength=0.1)

    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_aspect('equal')
    ax.grid(False)
    ax.set_xlabel('x (m)')
    ax.set_ylabel('y (m)')
    ax.set_title('(d) Cavity |U| at pseudo-time t = %s s — icoFoam, Re = 100'
                 % t_final, fontsize=12)

    fig.suptitle('cfd-openfoam judge: known-good cases pass every gate '
                 'against independent oracles', fontsize=14, y=0.965)
    out = os.path.join(outdir, 'result.png')
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# loop.png — the agent loop, replayed: verdict per replay step + kill rate
# ---------------------------------------------------------------------------
def make_loop(runs, outdir):
    steps = [
        ('01_cavity_wrong_lid.json', 'lid at 0.5 m/s\n(Re = 50)'),
        ('02_cavity_unconverged.json', 'endTime too early\n(unconverged)'),
        ('03_cavity_coarse_mesh.json', '10x10 mesh\n(too coarse)'),
        ('04_cavity_good.json', 'fixed:\n40x40, converged'),
    ]
    verdicts = []
    for fname, label in steps:
        v = load_json(need(os.path.join(runs, 'verdicts', fname)))
        failed = [g['gate'] for g in v['gates'] if not g['passed']]
        # metric of the gate that actually failed, per the hard rules
        vals = {}
        for g in v['gates']:
            d = g['details']
            if g['gate'] == 2 and not g['passed']:
                res = d.get('final_initial_residuals', {})
                vals['max residual'] = max(
                    res.values()) if res else None
            if g['gate'] == 5:
                vals['max Ghia err'] = max(d.get('max_u_error', 0),
                                           d.get('max_v_error', 0))
        verdicts.append((label, v['all_gates_passed'], failed, vals))

    mutants = []
    mdir = os.path.join(runs, 'mutants')
    for f in sorted(os.listdir(mdir)):
        v = load_json(os.path.join(mdir, f))
        mutants.append((f[:-5], v['all_gates_passed']))

    fig = plt.figure(figsize=(12.8, 5.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.25, 1], wspace=0.28,
                          left=0.065, right=0.98, top=0.86, bottom=0.16)

    # ---- (a) replay: error metric per iteration ---------------------------
    ax = fig.add_subplot(gs[0, 0])
    xs = range(len(steps))
    errs = [v['max Ghia err'] for _, _, _, v in verdicts]
    resid = [v.get('max residual') for *_, v in
             [(l, p, f, v) for l, p, f, v in verdicts]]
    colors = [GREEN if p else RED for _, p, _, _ in verdicts]
    bars = ax.bar(xs, [e * 100 for e in errs], width=0.55,
                  color=colors, edgecolor='white', linewidth=2)
    ax.axhline(2.0, color=INK, lw=1.5, linestyle='--')
    # Place pass-line annotation well above the PASS bar (index 3) so arrow
    # crosses nothing; target xy at the line near right edge, text further right/up
    ax.annotate('gate 5 pass line: max err <= 2 % of lid speed',
                xy=(3.7, 2.0), xytext=(2.8, 18),
                fontsize=9, color=INK, ha='left',
                arrowprops=dict(arrowstyle='-', color=INK, lw=0.8))
    for i, (label, passed, failed, _) in enumerate(verdicts):
        tag = 'PASS (%.2f %%)' % (errs[i] * 100) if passed else 'FAIL gates %s' % (
            ','.join(str(g) for g in failed))
        ax.text(i, max(errs[i] * 100 + 1.5, 4.0), tag, ha='center',
                fontsize=9, color=INK,
                fontweight='bold' if passed else 'normal')
    # PASS bar (last iteration) gets a visible green dot at its real value + printed value
    pass_idx = len(steps) - 1  # step 4 is PASS
    ax.plot(pass_idx, errs[pass_idx] * 100, 'o', ms=8, color=GREEN,
            markeredgecolor='white', markeredgewidth=1.5, zorder=5)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([s[1] for s in steps], fontsize=9)
    ax.set_ylabel('gate 5 metric: max centreline error vs Ghia (% lid speed)')
    ax.set_ylim(0, max(errs) * 100 * 1.22)
    ax.set_title('(a) Agent loop (replayed): each iteration graded by the '
                 'judge\niteration k+1 fixes the gate k failed', fontsize=12)

    # ---- (b) self-test kill rate -----------------------------------------
    ax = fig.add_subplot(gs[0, 1])
    names = [m for m, _ in mutants]
    killed = [0 if k else 1 for _, k in mutants]  # 1 = killed (failed)
    y = range(len(mutants))
    ax.barh(y, [100] * len(mutants), height=0.55, color='#dcdcd8',
            edgecolor='white', linewidth=2)
    ax.barh(y, [100 if k else 0 for k in killed], height=0.55,
            color=BLUE, edgecolor='white', linewidth=2)
    for i, k in enumerate(killed):
        ax.text(103, i, 'killed' if k else 'SURVIVED',
                va='center', fontsize=9,
                color=INK if k else RED,
                fontweight='bold' if not k else 'normal')
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 126)
    ax.set_xticks([0, 50, 100])
    ax.set_xlabel('mutants killed by selftest (%)')
    ax.set_title('(b) Self-test: %d/%d mutants killed\n(above: required '
                 '>= 90 %%)' % (sum(killed), len(mutants)),
                 fontsize=12)

    fig.suptitle('The judge the agent cannot fool — replayed loop and '
                 'self-test kill rate', fontsize=14, y=0.99)
    out = os.path.join(outdir, 'loop.png')
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def main():
    if len(sys.argv) != 3:
        sys.exit('usage: make_figures.py <judge_runs_dir> <outdir>')
    runs, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    r = make_result(runs, outdir)
    print('wrote', r)
    l = make_loop(runs, outdir)
    print('wrote', l)


if __name__ == '__main__':
    main()
