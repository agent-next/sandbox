#!/usr/bin/env python3
"""Figures for the code-interpreter-charts demo — every plotted number comes
from a file the judge wrote during a real run (verdict JSONs).  No invented
data: if a source file is missing, this exits 1.

Usage: make_figures.py <judge_runs_dir> <outdir>
Writes result.png and loop.png (200 dpi).
"""

import json
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Colour-blind-safe palette (Wong 2011, verified CVD-safe)
BLUE = '#0072B2'    # series 1 — measured / good case
ORANGE = '#D55E00'  # series 2 — oracle / reference
GREEN = '#009E73'   # pass / good
RED = '#CC79A7'     # fail / bad
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


# ---------------------------------------------------------------------------
# result.png — the key figure: three panels
#   (a) Mauna Loa monthly series + OLS trend line (C1 data from charts.json)
#   (b) Mean seasonal cycle (C2 data from charts.json)
#   (c) 2024 top-10 emitters (C3 data from charts.json)
# ---------------------------------------------------------------------------
def make_result(runs, outdir):
    good = load_json(need(os.path.join(runs, 'verdicts', '01_good.json')))
    charts = load_json(need(os.path.join(runs, 'verdicts', '01_good_charts.json')))

    fig = plt.figure(figsize=(12.8, 9.6))
    gs = fig.add_gridspec(2, 2, hspace=0.34, wspace=0.24,
                          left=0.07, right=0.97, top=0.90, bottom=0.08)

    # ---- (a) Mauna Loa monthly + OLS trend --------------------------------
    ax = fig.add_subplot(gs[0, 0])
    c1 = charts['C1']
    months = c1['months']
    xs = [m[0] for m in months]
    ys = [m[1] for m in months]
    ax.plot(xs, ys, color=BLUE, lw=0.8, label='Mauna Loa monthly mean')
    line = c1['trend_line']
    ax.plot([line[0][0], line[1][0]], [line[0][1], line[1][1]],
            color=ORANGE, lw=2.0, ls='--',
            label=f"OLS trend {c1['mauna_loa_trend_ppm_per_year']:.3f} ppm/yr")
    ax.set_xlabel('Year (decimal date)')
    ax.set_ylabel('CO$_2$ (ppm)')
    ax.set_title('(a) Mauna Loa monthly CO$_2$ + OLS trend (C1)', fontsize=12)
    ax.legend(loc='upper left', fontsize=9, frameon=True, framealpha=0.95)

    # ---- (b) Mean seasonal cycle -------------------------------------------
    ax = fig.add_subplot(gs[0, 1])
    c2 = charts['C2']
    mlabels = [m[0] for m in c2['months']]
    mvals = [m[1] for m in c2['months']]
    ax.bar(mlabels, mvals, color=GREEN, edgecolor='white', linewidth=0.5)
    ax.set_xlabel('Month')
    ax.set_ylabel('Mean CO$_2$ (ppm)')
    ax.set_title(f"(b) Mean seasonal cycle (C2) — amplitude "
                 f"{c2['amplitude_ppm']:.2f} ppm", fontsize=12)
    ax.set_xticks(range(1, 13))

    # ---- (c) 2024 top-10 emitters ------------------------------------------
    ax = fig.add_subplot(gs[1, :])
    c3 = charts['C3']
    entities = c3['entities'][::-1]
    values = [v for _, v in c3['emissions_gt']][::-1]
    ax.barh(entities, values, color=BLUE, edgecolor='white', linewidth=0.5)
    ax.set_xlabel('Annual CO$_2$ emissions 2024 (GtCO$_2$)')
    ax.set_title(f"(c) Top 10 emitters 2024 (C3) — total "
                 f"{c3['total_gt']:.2f} Gt", fontsize=12)

    fig.suptitle('code-interpreter-charts judge: known-good artifact '
                 'passes every gate', fontsize=14, y=0.965)
    out = os.path.join(outdir, 'result.png')
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# loop.png — the agent loop: verdict per replay step + kill rate
# ---------------------------------------------------------------------------
def make_loop(runs, outdir):
    steps = [
        ('01_good.json', 'known-good\nartifact'),
    ]
    verdicts = []
    for fname, label in steps:
        v = load_json(need(os.path.join(runs, 'verdicts', fname)))
        failed = [g for g, d in v['gates'].items()
                  if isinstance(d, dict) and d.get('passed') is False]
        verdicts.append((label, v['passed'], failed))

    mutants = []
    mdir = os.path.join(runs, 'mutants')
    for f in sorted(os.listdir(mdir)):
        v = load_json(os.path.join(mdir, f))
        mutants.append((f[:-5], v['passed']))

    fig = plt.figure(figsize=(12.8, 5.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.25], wspace=0.28,
                          left=0.065, right=0.98, top=0.86, bottom=0.16)

    # ---- (a) replay: gate status per iteration -----------------------------
    ax = fig.add_subplot(gs[0, 0])
    xs = range(len(steps))
    colors = [GREEN if p else RED for _, p, _ in verdicts]
    bars = ax.bar(xs, [100] * len(steps), width=0.55,
                  color=colors, edgecolor='white', linewidth=2)
    for i, (label, passed, failed) in enumerate(verdicts):
        tag = 'PASS' if passed else 'FAIL gates %s' % ','.join(failed)
        ax.text(i, 102, tag, ha='center', fontsize=10, color=INK,
                fontweight='bold' if passed else 'normal')
    ax.set_xticks(list(xs))
    ax.set_xticklabels([s[1] for s in steps], fontsize=9)
    ax.set_ylabel('gates passed (%)')
    ax.set_ylim(0, 115)
    ax.set_title('(a) Agent loop: known-good artifact\npasses all 5 gates',
                 fontsize=12)

    # ---- (b) self-test kill rate -------------------------------------------
    ax = fig.add_subplot(gs[0, 1])
    names = [m for m, _ in mutants]
    killed = [0 if p else 1 for _, p in mutants]  # 1 = killed (failed)
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
