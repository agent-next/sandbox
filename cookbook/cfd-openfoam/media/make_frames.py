#!/usr/bin/env python3
"""Video frames for the cfd-openfoam demo — cavity flow developing over
pseudo-time, from the --trace time directories the judge saved during a
real icoFoam run.  Every frame is rendered from solver output; if the
trace directory or the residuals.csv is missing, this exits 1.

Usage: make_frames.py <cavity_trace_dir> <frames_dir> [seconds_per_time]
"""

import math
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.tri as tri
import numpy as np
from scipy.interpolate import griddata

INK = '#0b0b0b'
INK2 = '#52514e'
SEQ_CMAP = mcolors.LinearSegmentedColormap.from_list(
    'seq_blue', ['#f3f6fb', '#a8c8ec', '#5a9bd8', '#2a78d6', '#123c66'])


def read_cellcentres(path):
    cent = []
    with open(path) as f:
        for line in f:
            if line.startswith('x,y') or not line.strip():
                continue
            x, y = line.split(',')
            cent.append((float(x), float(y)))
    return cent


def read_U(path):
    ufield = []
    started = False
    for line in open(path):
        s = line.strip()
        if s.startswith('internalField'):
            started = True
            continue
        if started and s.startswith('(') and s != '(':
            vals = s.strip('()').split()
            if len(vals) >= 2:
                ufield.append((float(vals[0]), float(vals[1])))
    return ufield


def read_residuals(path):
    ts, res = [], []
    with open(path) as f:
        header = f.readline()
        for line in f:
            parts = line.strip().split(',')
            if len(parts) != 4 or not parts[0]:
                continue
            t = float(parts[0])
            r = max(float(p) for p in parts[1:4] if p)
            ts.append(t)
            res.append(r)
    return ts, res


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: make_frames.py <cavity_trace_dir> <frames_dir>')
    trace, frames = sys.argv[1], sys.argv[2]
    cent = read_cellcentres(os.path.join(trace, 'cellcentres.csv'))
    ts, res = read_residuals(os.path.join(trace, 'residuals.csv'))
    if not ts or not cent:
        sys.exit('make_frames: empty residuals.csv or cellcentres.csv')

    times = sorted((d for d in os.listdir(trace)
                    if d.replace('.', '', 1).isdigit()
                    and os.path.isdir(os.path.join(trace, d))),
                   key=float)
    if not times:
        sys.exit('make_frames: no time directories under %s' % trace)
    os.makedirs(frames, exist_ok=True)

    # Prepare arrays for tripcolor and streamlines
    X = np.array([c[0] for c in cent])
    Y = np.array([c[1] for c in cent])

    # one figure, one colorbar, figure-level title — updated in place
    fig = plt.figure(figsize=(19.20, 10.80), facecolor='white')
    # |U| field takes left ~55%, residual panel takes right ~45% with full height
    ax = fig.add_axes([0.04, 0.06, 0.52, 0.88])
    ax_res = fig.add_axes([0.60, 0.06, 0.38, 0.88])

    # Initial tripcolor with triangulation
    triang = tri.Triangulation(X, Y)
    sc = ax.tripcolor(triang, [0.0] * len(X), cmap=SEQ_CMAP,
                      vmin=0, vmax=1.0, shading='gouraud', edgecolors='none')
    cb = fig.colorbar(sc, ax=ax, shrink=0.9, pad=0.015)
    cb.set_label('|U| (m/s)', fontsize=16)
    cb.ax.tick_params(labelsize=14)

    # Figure-level title (left-aligned): case + time
    fig_title = fig.text(0.04, 0.96, '', fontsize=22, color=INK,
                         ha='left', va='top', fontweight='bold')

    # Pre-create regular grid for streamlines
    xi = np.linspace(0, 1, 61)
    yi = np.linspace(0, 1, 61)
    Xi, Yi = np.meshgrid(xi, yi)

    stream_art = []

    def render(t_str, frame_no):
        u = read_U(os.path.join(trace, t_str, 'U'))
        if len(u) != len(cent):
            sys.exit('make_frames: U field %d vs centres %d — pairing broken'
                     % (len(u), len(cent)))
        Ux = np.array([u[0] for u in u])
        Uy = np.array([u[1] for u in u])
        mag = np.array([math.hypot(a, b) for a, b in u])

        # Update tripcolor field
        sc.set_array(mag)

        # Streamlines: interpolate Ux, Uy onto regular grid
        Ux_grid = griddata((X, Y), Ux, (Xi, Yi), method='linear')
        Uy_grid = griddata((X, Y), Uy, (Xi, Yi), method='linear')
        # Clear and redraw streamlines each frame
        for art in stream_art:
            art.remove()
        before = set(ax.patches)
        sp = ax.streamplot(Xi, Yi, Ux_grid, Uy_grid, color=INK, linewidth=0.6,
                           density=1.2, arrowsize=0.5, minlength=0.1)
        # arrows are added as individual patches; sp.arrows is not in the axes
        stream_art[:] = [sp.lines] + [a for a in ax.patches if a not in before]

        ax.set_xlim(-0.03, 1.03)
        ax.set_ylim(-0.03, 1.03)
        ax.set_aspect('equal')
        ax.grid(False)
        ax.set_xlabel('x (m)', fontsize=16, color=INK)
        ax.set_ylabel('y (m)', fontsize=16, color=INK)
        ax.tick_params(labelsize=14, colors=INK2)

        # Figure-level title with case + time (left-aligned)
        fig_title.set_text('Lid-driven cavity, Re = 100  |  t = %s s' % t_str)

        # Residual history panel
        ax_res.cla()
        ax_res.semilogy(ts, res, color='#2a78d6', lw=1.5, alpha=0.5,
                        label='all steps')
        shown_t = [t for t in ts if t <= float(t_str) + 1e-9]
        shown_r = res[:len(shown_t)]
        ax_res.semilogy(shown_t, shown_r, color='#eb6834', lw=2.5,
                        label='up to current t')
        ax_res.axhline(1e-5, color='#0ca30c', lw=1.5, linestyle='--')
        ax_res.text(0.02, 0.92, 'gate 2 pass line: all residuals < 1e-5',
                    fontsize=12, color='#0ca30c', transform=ax_res.transAxes,
                    va='top')
        ax_res.set_xlabel('pseudo-time t (s)', fontsize=14, color=INK)
        ax_res.set_ylabel('max initial residual (Ux, Uy, p)', fontsize=14,
                          color=INK)
        ax_res.tick_params(labelsize=12, colors=INK2)
        ax_res.set_title('Solver convergence — gate 2', fontsize=16,
                         color=INK)
        ax_res.set_xlim(0, ts[-1])
        ax_res.legend(loc='lower left', fontsize=11, frameon=True, framealpha=0.9)

        out = os.path.join(frames, 'frame_%04d.png' % frame_no)
        fig.savefig(out, dpi=100)
        return out

    n = 0
    for t_str in times:
        render(t_str, n)
        n += 1
    plt.close(fig)
    print('wrote %d frames to %s' % (n, frames))


if __name__ == '__main__':
    main()
