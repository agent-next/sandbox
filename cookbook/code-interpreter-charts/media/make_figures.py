#!/usr/bin/env python3
"""Figures for the code-interpreter-charts demo — every plotted number comes
from a file the judge wrote during a real run (verdict JSONs, the good
artifact's own charts.json).  No invented data: if a source file is missing,
this exits 1.

Usage: make_figures.py <judge_runs_dir> <outdir>   (run via make_media.sh)

Reads   <runs>/good.json            verdict for the known-good artifact
        <runs>/good_out/charts.json the artifact's judged output
        <runs>/mutants/<name>.json  one verdict per known-bad mutant
Writes  result.png and loop.png (200 dpi).
"""

import json
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# dataviz reference palette (validated: CVD-safe on the light surface)
BLUE = '#2a78d6'    # series 1 — measured / good case
ORANGE = '#eb6834'  # series 2 — reference (OLS trend line)
GREEN = '#0ca30c'   # status: good — pass
RED = '#d03b3b'     # status: critical — failing data
INK = '#0b0b0b'
INK2 = '#52514e'
GRID = '#e1e0d9'

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
# with the judge's verdict numbers drawn on them.
# ---------------------------------------------------------------------------
def make_result(runs, outdir):
    good = load_json(need(os.path.join(runs, 'good.json')))
    charts = load_json(need(os.path.join(runs, 'good_out', 'charts.json')))

    fig = plt.figure(figsize=(12.8, 9.6))
    gs = fig.add_gridspec(2, 2, hspace=0.34, wspace=0.24,
                          left=0.07, right=0.97, top=0.90, bottom=0.08)

    # ---- (a) Mauna Loa monthly + OLS trend --------------------------------
    ax = fig.add_subplot(gs[0, 0])
    c1 = charts['C1']
    months = c1['months']
    xs = [m[0] for m in months]
    ys = [m[1] for m in months]
    ax.plot(xs, ys, color=BLUE, lw=1.0, label='Mauna Loa monthly mean')
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
    ax.bar(mlabels, mvals, color=BLUE, edgecolor='white', linewidth=0.5)
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
                 f"{c3['total_gt']:.2f} Gt, top share "
                 f"{c3['owid_top_emitter_2024_share']:.4f}", fontsize=12)

    fig.suptitle('code-interpreter-charts judge: known-good artifact '
                 'passes every gate', fontsize=14, y=0.965)
    out = os.path.join(outdir, 'result.png')
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# loop.png — the agent loop: verdict per draft iteration + self-test kills
# ---------------------------------------------------------------------------
# Draft iterations replayed as the agent loop: each is a real verdict the
# self-test produced (single-edit mutants of the good artifact model the
# plausible first drafts), ending at the known-good artifact.
LOOP_STEPS = [
    ('mutants/off-by-one-filter.json', 'draft 1:\nwindow 1991+'),
    ('mutants/mean-vs-median.json', 'draft 2:\nmedian for mean'),
    ('mutants/blank-chart.json', 'draft 3:\nC2 drawn blank'),
    ('good.json', 'final:\nexamples/good'),
]


def make_loop(runs, outdir):
    verdicts = []
    for fname, label in LOOP_STEPS:
        v = load_json(need(os.path.join(runs, fname)))
        # gates entries are assigned in order and stop at the first failure,
        # so the G-keys present are exactly the gates that passed.
        n_pass = len([g for g in v['gates'] if g.startswith('G')])
        verdicts.append((label, v['passed'], v.get('failed_gate'), n_pass))

    mutants = []
    mdir = os.path.join(runs, 'mutants')
    for f in sorted(os.listdir(mdir)):
        if not f.endswith('.json'):
            continue
        v = load_json(os.path.join(mdir, f))
        mutants.append((f[:-5], v['passed'], v.get('failed_gate')))

    fig = plt.figure(figsize=(12.8, 5.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.25], wspace=0.28,
                          left=0.065, right=0.98, top=0.86, bottom=0.16)

    # ---- (a) replay: gates passed per draft iteration ----------------------
    ax = fig.add_subplot(gs[0, 0])
    xs = range(len(verdicts))
    colors = [GREEN if p else RED for _, p, _, _ in verdicts]
    ax.bar(xs, [n * 20 for *_, n in verdicts], width=0.55,
           color=colors, edgecolor='white', linewidth=2)
    for i, (label, passed, gate, n) in enumerate(verdicts):
        ax.text(i, n * 20 + 3, f'{n}/5', ha='center', fontsize=9, color=INK)
        tag = 'PASS' if passed else f'FAIL gate {gate}'
        ax.text(i, 127, tag, ha='center', fontsize=10,
                color=GREEN if passed else RED,
                fontweight='bold' if passed else 'normal')
    ax.set_xticks(list(xs))
    ax.set_xticklabels([s[1] for s in verdicts], fontsize=9)
    ax.set_ylabel('gates passed (%)')
    ax.set_ylim(0, 135)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_title('(a) Agent loop: verdict per draft iteration\n'
                 'until every gate passes', fontsize=12)

    # ---- (b) self-test: known-good vs every known-bad ----------------------
    ax = fig.add_subplot(gs[0, 1])
    rows = [('known-good', True, None)] + mutants
    names = [m for m, _, _ in rows]
    y = range(len(rows))
    # killed = judge rejected it (a mutant); the known-good passes by design
    statuses = [('passes' if p else f'killed (G{g[-1]})', p)
                for _, p, g in rows]
    ax.barh(y, [100] * len(rows), height=0.55, color='#dcdcd8',
            edgecolor='white', linewidth=2)
    for i, (text, is_good) in enumerate(statuses):
        killed = not is_good
        ax.barh(i, 100, height=0.55,
                color=GREEN if is_good else BLUE,
                edgecolor='white', linewidth=2)
        ax.text(103, i, text, va='center', fontsize=9, color=INK)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 132)
    ax.set_xticks([0, 50, 100])
    ax.set_xlabel('judge verdict per self-test artifact (%)')
    killed_n = len(mutants) - sum(1 for _, p, _ in mutants if p)
    ax.set_title(f'(b) Self-test: {killed_n}/{len(mutants)} known-bad killed'
                 '\n(required >= 90 %)', fontsize=12)

    fig.suptitle('The judge the agent cannot fool — replayed loop and '
                 'self-test verdicts', fontsize=14, y=0.99)
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
