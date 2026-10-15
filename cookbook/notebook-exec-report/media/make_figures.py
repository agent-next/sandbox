#!/usr/bin/env python3
"""Figures for the notebook-exec-report demo — every plotted number comes
from a file the judge wrote during a real run (grade verdict JSONs) or from
the judge's own oracle refit of the pinned dataset.  No invented data: if a
source file is missing or a plotted number disagrees with the verdict, this
exits 1.

Usage: make_figures.py <demo_dir> <judge_runs_dir> <outdir>
Writes result.png and loop.png (200 dpi, readable at 1200 px wide).
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.join(sys.argv[1], 'judge'))
import oracle  # noqa: E402  the judge's own refit, reused for the scatter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# dataviz reference palette (validated: CVD-safe on light surface;
# status green/red always carry a text label, never color alone)
BLUE = '#2a78d6'    # series 1 — graded split / measured entity
BLUE_LT = '#86b6ef'  # same hue, lighter step — the blind refits
ORANGE = '#eb6834'  # series 2 — true values / second series
RED = '#d03b3b'     # status: critical — failing data, gate limit
GREEN = '#0ca30c'   # status: good — PASS marker
INK = '#0b0b0b'
INK2 = '#52514e'
GRID = '#e5e4e0'

def style():
    plt.rcParams.update({
        'font.size': 11, 'axes.edgecolor': INK2, 'axes.labelcolor': INK,
        'xtick.color': INK2, 'ytick.color': INK2,
        'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.8,
        'axes.axisbelow': True, 'figure.facecolor': 'white',
        'axes.facecolor': 'white',
    })


style()

RMSE_LIMIT = 0.3040      # judge gate G5 (SPEC.md)
RECOVERY_LIMIT = 0.05    # acceptance oracle item 3
TOL_RMSE = 1e-6          # gate G4 tolerances
TOL_R2 = 1e-9


def need(path):
    if not os.path.isfile(path):
        raise SystemExit(f"make_figures: MISSING judge output {path}")
    with open(path) as f:
        return json.load(f)


# --- the notebook's own pipeline, recomputed only to plot the scatter -----
# (SPEC.md documents it; the verdict JSON below is what verifies the numbers)
def notebook_fit(demo_dir, seed=20261015, alpha=10.0):
    import pandas as pd
    from sklearn.linear_model import Ridge
    df = pd.read_csv(os.path.join(demo_dir, 'examples/good/dataset.csv'))
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(df))
    n_train = int(round(0.8 * len(df)))
    train_idx, test_idx = order[:n_train], order[n_train:]
    X = df[list(oracle.FEATURES)].to_numpy(dtype=float)
    log_y = np.log(df[oracle.TARGET].to_numpy(dtype=float))
    mu, sd = X[train_idx].mean(0), X[train_idx].std(0)
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd
    model = Ridge(alpha=alpha).fit(Xs[train_idx], log_y[train_idx])
    return {
        'test_idx': test_idx,
        'pred': model.predict(Xs[test_idx]),
        'obs': log_y[test_idx],
        'coef': model.coef_,
        'rmse_test': float(np.sqrt(np.mean(
            (log_y[test_idx] - model.predict(Xs[test_idx])) ** 2))),
    }


def blind_refits(demo_dir, seeds, alpha):
    with open(os.path.join(demo_dir, 'examples/good/dataset.csv'), 'rb') as f:
        csv_bytes = f.read()
    return {s: oracle.refit(csv_bytes, s, alpha)['rmse_test'] for s in seeds}


def tag_pass(ax, ok, label):
    if not label:
        raise SystemExit("make_figures: PASS/FAIL tag drawn without a "
                         "verdict check")
    ax.text(0.985, 0.03, ('PASS ' if ok else 'FAIL ') + label,
            transform=ax.transAxes, ha='right', va='bottom', fontsize=10,
            fontweight='bold',
            color=GREEN if ok else RED,
            bbox=dict(facecolor='white', edgecolor=GRID, pad=3))


def main():
    demo_dir, runs, out = sys.argv[1], sys.argv[2], sys.argv[3]
    good = need(os.path.join(runs, 'good.json'))
    if not good.get('passed'):
        raise SystemExit("make_figures: good.json is not a passing verdict")
    o = good['gates']['oracle']
    blind = good['gates']['blind']
    metrics = good['metrics']

    fit = notebook_fit(demo_dir)
    # every plotted number is tied back to the judge's verdict
    if abs(fit['rmse_test'] - o['rmse_test']) > 1e-9:
        raise SystemExit(
            f"make_figures: scatter rmse {fit['rmse_test']:.9f} disagrees "
            f"with the verdict refit {o['rmse_test']:.9f}")
    blind_rmses = blind_refits(demo_dir, blind['seeds'],
                               alpha=10.0)
    med = sorted(blind_rmses.values())[len(blind_rmses) // 2]
    if abs(med - blind['median_blind']) > 1e-12:
        raise SystemExit(
            f"make_figures: blind median {med:.12f} disagrees with the "
            f"verdict {blind['median_blind']:.12f}")

    # ================= result.png =========================================
    fig, axes = plt.subplots(2, 2, figsize=(12.4, 9.2))

    # (a) held-out predictions vs observations, log scale
    ax = axes[0][0]
    lo = math.floor(min(fit['obs'].min(), fit['pred'].min()) * 4) / 4
    hi = math.ceil(max(fit['obs'].max(), fit['pred'].max()) * 4) / 4
    ax.plot([lo, hi], [lo, hi], ls='--', lw=2, color=INK2,
            label='y = x (perfect prediction)', zorder=1)
    ax.plot(fit['obs'], fit['pred'], 'o', ms=7, color=BLUE,
            markeredgecolor='white', markeredgewidth=1.0,
            label='test split (320 rows)', zorder=2)
    ax.set_xlabel('observed  ln(MED_VALUE / USD)')
    ax.set_ylabel('predicted  ln(MED_VALUE / USD)')
    ax.set_title('(a) held-out predictions, ridge refit '
                 '(seed 20261015, alpha 10)')
    ax.legend(loc='upper left', frameon=True)
    tag_pass(ax, o['rmse_test'] <= RMSE_LIMIT,
             f"rmse_test {o['rmse_test']:.6f} <= {RMSE_LIMIT}")

    # (b) the graded split vs the five blind refits, with the G5 limit
    ax = axes[0][1]
    seeds = list(blind['seeds'])
    vals = [blind_rmses[s] for s in seeds]
    ax.bar(range(len(seeds)), vals, width=0.62, color=BLUE_LT,
           edgecolor='white', linewidth=2, label='blind refit seeds')
    ax.bar([len(seeds)], [o['rmse_test']], width=0.62, color=BLUE,
           edgecolor='white', linewidth=2, label='graded split (seed 20261015)')
    ax.axhline(RMSE_LIMIT, color=RED, ls='--', lw=2,
               label=f'G5 limit {RMSE_LIMIT}')
    ax.axhline(blind['median_blind'], color=INK2, ls=':', lw=2,
               label=f'blind median {blind["median_blind"]:.6f}')
    ax.set_xticks(range(len(seeds) + 1),
                  [str(s) for s in seeds] + ['graded'])
    ax.set_ylim(0.27, 0.312)
    ax.set_xlabel('judge refit split seed')
    ax.set_ylabel('rmse_test (log scale)')
    ax.set_title('(b) noise floor: graded split vs 5 blind refits')
    ax.legend(loc='lower left', fontsize=9, frameon=True)
    tag_pass(ax, blind['ratio'] <= 1.25,
             f"blind ratio {blind['ratio']:.3f} <= 1.25")

    # (c) coefficient recovery against the generator's exact W_TRUE
    ax = axes[1][0]
    ax.plot(oracle.W_TRUE, fit['coef'], 'o', ms=9, color=BLUE,
            markeredgecolor='white', markeredgewidth=1.0, zorder=2,
            label='fitted vs true coefficient')
    ax.plot([-0.5, 0.5], [-0.5, 0.5], ls='--', lw=2, color=INK2,
            label='y = x (exact recovery)', zorder=1)
    for name, wt, wc in zip(oracle.FEATURES, oracle.W_TRUE, fit['coef']):
        ax.annotate(name, (wt, wc), textcoords='offset points',
                    xytext=(7, 4), fontsize=8, color=INK2)
    ax.set_xlim(-0.55, 0.55)
    ax.set_ylim(-0.55, 0.55)
    ax.set_xlabel('true coefficient  W_TRUE (generator, exact)')
    ax.set_ylabel('fitted coefficient (standardized)')
    ax.set_title('(c) coefficient recovery, 8 predictors')
    ax.legend(loc='lower right', fontsize=9, frameon=True)
    tag_pass(ax, o['coef_recovery'] <= RECOVERY_LIMIT,
             f"recovery {o['coef_recovery']:.4f} <= {RECOVERY_LIMIT}")

    # (d) oracle agreement: reported metric vs independent refit
    ax = axes[1][1]
    yticks, labels, vals, tols = [], [], [], []
    pairs = [('rmse_test', abs(metrics['rmse_test'] - o['rmse_test']),
              TOL_RMSE),
             ('r2_test', abs(metrics['r2_test'] - o['r2_test']), TOL_R2)]
    for i, (name, d, tol) in enumerate(pairs):
        yticks.append(i)
        labels.append(f'{name}   |reported − refit|')
        vals.append(max(d, 1e-15))
        tols.append(tol)
        if d > tol:
            raise SystemExit(
                f"make_figures: {name} disagreement {d:.3e} exceeds the "
                f"gate tolerance {tol:.0e} — refusing to plot a pass")
    ax.barh(yticks, vals, height=0.5, color=BLUE, edgecolor='white',
            linewidth=2)
    for i, tol in enumerate(tols):
        ax.axvline(tol, color=RED, ls='--', lw=2 if i == 0 else 1.2)
        ax.text(tol, i + 0.33, f'tolerance {tol:.0e}', fontsize=8,
                color=RED, ha='center')
    ax.set_yticks(yticks, labels)
    ax.set_xscale('log')
    ax.set_xlim(1e-16, 1e-4)
    ax.set_xlabel('absolute disagreement (log scale)')
    ax.set_title('(d) notebook metric vs independent stdlib refit')
    tag_pass(ax, True, 'both metrics within tolerance (G4)')

    fig.suptitle('notebook-exec-report — judge verdict on '
                 'examples/good/analysis.ipynb (all 7 gates pass)',
                 fontsize=14, fontweight='bold', y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(os.path.join(out, 'result.png'), dpi=200)
    plt.close(fig)

    # ================= loop.png ===========================================
    loop = []
    for fname in sorted(os.listdir(os.path.join(runs, 'loop'))):
        loop.append(need(os.path.join(runs, 'loop', fname)))
    muts = []
    for fname in sorted(os.listdir(os.path.join(runs, 'mutants'))):
        muts.append((fname[:-5], need(os.path.join(runs, 'mutants',
                                                   fname))))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.8, 5.6),
                                   gridspec_kw={'width_ratios': [1, 1.25]})

    # left: the agent loop, replayed — which gate failed per iteration
    # (each iteration fixes the defect the previous verdict named), until
    # the artifact passes every gate.  A failing verdict carries no
    # metrics, so the plotted quantity is the gate outcome itself.
    gate_rows = ['execution', 'determinism', 'figures', 'oracle', 'report',
                 'ALL PASS']
    for v in loop:
        g = v.get('failed_gate')
        if g and g not in gate_rows:
            gate_rows.insert(-1, g)
    for i, v in enumerate(loop):
        gate = v.get('failed_gate')
        row = gate_rows.index('ALL PASS') if gate is None \
            else gate_rows.index(gate)
        if gate is None:
            ax1.plot(i, row, 'o', ms=13, color=GREEN, zorder=3)
            ax1.annotate('PASS', (i, row), textcoords='offset points',
                         xytext=(0, 14), ha='center', fontsize=10,
                         fontweight='bold', color=GREEN)
        else:
            ax1.plot(i, row, 'X', ms=13, color=RED, zorder=3)
    ax1.set_yticks(range(len(gate_rows)), gate_rows)
    ax1.set_xticks(range(len(loop)),
                   [f'iter {i + 1}\n{os.path.basename(v["artifact"])[:20]}'
                    for i, v in enumerate(loop)])
    ax1.set_ylim(-0.7, len(gate_rows) - 0.3)
    ax1.set_xlim(-0.6, len(loop) - 0.4)
    ax1.set_title('the agent loop, replayed: one defect fixed per iteration')

    # right: the self-test — the known-good passes, every known-bad is killed
    rows = [('known-good', None, True)] + [(n, v, not v.get('passed', False))
                                           for n, v in muts]
    rows.sort(key=lambda r: r[0] != 'known-good')
    y = list(range(len(rows)))[::-1]
    for yi, (name, v, ok) in zip(y, rows):
        color = GREEN if name == 'known-good' else BLUE
        if name == 'known-good':
            note = 'passes every gate (baseline)'
        else:
            gate = v.get('failed_gate') or '?'
            note = f"killed — {gate} gate"
            if v.get('reason'):
                note += f"  ({v['reason'][:60]})"
        ax2.barh(yi, 1.0, height=0.62, color=color, edgecolor='white',
                 linewidth=2)
        ax2.text(0.02, yi, f'{name}: {note}', va='center', fontsize=9.5,
                 color='white')
    ax2.set_yticks(y, [r[0] for r in rows])
    ax2.set_xticks([])
    ax2.set_xlim(0, 1.55)
    ax2.grid(False)
    killed = sum(1 for _, v, ok in rows[1:] if ok)
    ax2.set_title(f'self-test kill rate: {killed}/{len(rows) - 1} '
                  f'= {killed / (len(rows) - 1):.0%} (requirement >= 90%)')

    fig.tight_layout()
    fig.savefig(os.path.join(out, 'loop.png'), dpi=200)
    plt.close(fig)
    print('make_figures: wrote result.png and loop.png')


if __name__ == '__main__':
    main()
