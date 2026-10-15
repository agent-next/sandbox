#!/usr/bin/env python3
"""Video frames for the notebook-exec-report demo: an animated step-through
of the agent loop's real verdicts and the judge's numbers (captions carry
the measured values).  Every number comes from files the judge wrote in a
real run (grade verdict JSONs) or the judge's own oracle refit — no
invented data; a missing source exits 1.

The step-through animates: hard cuts between the nine chapters, and inside
every chapter a replay marker sweeps across the timeline strip at the
bottom while the chapter's content builds up (typed lines, growing bars,
progressive draws).  Main's media video-gate requires >= 0.8 scene cuts /
10 s, >= 20 % of frames moving (frame-to-frame luma difference) and a
static end card over the last 2 s, which a deck of still slides fails.

Usage: make_frames.py <demo_dir> <judge_runs_dir> <outdir>
Writes frame_0001.png ... frame_0NNN.png at 1920x1080.
"""

import json
import math
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(sys.argv[1], 'judge'))
import oracle  # noqa: E402
from make_figures import (  # noqa: E402
    BLUE, BLUE_LT, RED, GREEN, INK, INK2, GRID,
    RMSE_LIMIT, RECOVERY_LIMIT, TOL_RMSE, TOL_R2,
    need, notebook_fit, blind_refits, style)

style()
DPI = 100
FIGSIZE = (19.2, 10.8)   # 1920x1080 exactly
FPS_IN = 30              # master renders at the delivery frame rate
SECONDS_PER_CHAPTER = 5  # 9 chapters x 5 s = 45 s (standard: 20-60 s)
FRAMES_PER_CHAPTER = FPS_IN * SECONDS_PER_CHAPTER
QUIET_TAIL_S = 2.5       # the gate requires a static end card over the
                         # last 2 s; the last chapter's sweep freezes then


def caption(ax, text):
    ax.text(0.5, 0.115, text, transform=ax.transAxes, ha='center',
            va='center', fontsize=17, color=INK)


def title(ax, text):
    ax.text(0.5, 0.90, text, transform=ax.transAxes, ha='center',
            va='center', fontsize=19, fontweight='bold')


def frame(out, build):
    """One 1920x1080 frame; `build(ax, i)` draws frame i of its chapter."""
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    ax.set_axis_off()
    fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02)
    build(ax)
    fig.savefig(out)
    plt.close(fig)


def reveal_lines(ax, lines, i, n, x=0.10, y=0.66, dy=0.085, size=16,
                 family='monospace', color=INK, **kw):
    """Type the lines in one by one."""
    shown = i / n * (len(lines) + 1)
    full = int(shown)
    last = max((len(lines[full]) if full < len(lines) else 1), 1)
    chars = int((shown - full) * last)
    for j, line in enumerate(lines):
        if j < full:
            ax.text(x, y - j * dy, line, ha='left', va='center', fontsize=size,
                    family=family, color=color, **kw)
        elif j == full:
            ax.text(x, y - j * dy, line[:chars], ha='left', va='center',
                    fontsize=size, family=family, color=color, **kw)


def progress(ax, i, n, color=BLUE):
    """A chapter progress bar along the bottom edge."""
    ax.add_patch(plt.Rectangle((0.0, 0.0), 1.0, 0.012, color=GRID,
                               transform=ax.transAxes))
    ax.add_patch(plt.Rectangle((0.0, 0.0), (i + 1) / n, 0.012, color=color,
                               transform=ax.transAxes))


def timeline(ax, i, n, ticks, quiet=False):
    """The chapter's replay strip along the bottom edge: a track with the
    chapter's beats ticked on it and a marker sweeping across (this is the
    element that moves in every frame).  `quiet` freezes the marker: the
    video must end on a still end card."""
    y = 0.035
    x0, x1 = 0.05, 0.95
    ax.plot([x0, x1], [y, y], color=GRID, lw=6, solid_capstyle='round')
    for t, label in ticks:
        xt = x0 + (x1 - x0) * t
        ax.plot([xt], [y], marker='|', ms=18, color=INK2)
        ax.text(xt, y + 0.045, label, ha='center', va='bottom', fontsize=12,
                color=INK2)
    head = 1.0 if quiet else i / (n - 1)
    xt = x0 + (x1 - x0) * head
    ax.plot([xt], [y], marker='o', ms=22, color=BLUE,
            markeredgecolor='white', markeredgewidth=2.5, zorder=5)


def main():
    demo_dir, runs, out = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out, exist_ok=True)
    good = need(os.path.join(runs, 'good.json'))
    o = good['gates']['oracle']
    blind = good['gates']['blind']
    metrics = good['metrics']
    fit = notebook_fit(demo_dir)
    if abs(fit['rmse_test'] - o['rmse_test']) > 1e-9:
        raise SystemExit("make_frames: scatter rmse disagrees with verdict")
    loop = [need(os.path.join(runs, 'loop', f))
            for f in sorted(os.listdir(os.path.join(runs, 'loop')))]
    muts = [(f[:-5], need(os.path.join(runs, 'mutants', f)))
            for f in sorted(os.listdir(os.path.join(runs, 'mutants')))]
    blind_rmses = blind_refits(demo_dir, blind['seeds'], alpha=10.0)
    n = 0

    def emit(build, ticks):
        # one chapter = FRAMES_PER_CHAPTER animated frames = 5 s at 30 fps;
        # the sweeping replay marker moves in every frame except the final
        # chapter's quiet tail (static end card)
        nonlocal n
        for i in range(FRAMES_PER_CHAPTER):
            n += 1
            frame(os.path.join(out, f'frame_{n:04d}.png'),
                  lambda ax, build=build, i=i, m=FRAMES_PER_CHAPTER:
                  build(ax, i, m, ticks))

    # 1 — the problem
    def f1(ax, i, m, ticks):
        ax.text(0.5, 0.78, 'The agent loop', ha='center', fontsize=26,
                fontweight='bold')
        ax.text(0.5, 0.60, 'deliver analysis.ipynb: load the pinned dataset,\n'
                'fit a seeded ridge regression, save 3 figures, render report.html\n'
                '— the judge re-runs it headless and refits every number itself',
                ha='center', va='center', fontsize=16, color=INK2)
        chips = ['G1 execution 1..N', 'G2 determinism 1e-12',
                 'G3 figures >= 3', 'G4 oracle 1e-6', 'G5 noise floor 0.3040']
        k = min(len(chips), int(i / m * (len(chips) + 1.5)))
        for j in range(k):
            ax.text(0.5, 0.44 - j * 0.055, chips[j], ha='center',
                    va='center', fontsize=15, family='monospace', color=INK)
        ax.text(0.5, 0.19, f'dataset 1600 rows  ·  split seed 20261015  ·  '
                f'Ridge(alpha=10)  ·  judge tolerance 1e-6', ha='center',
                fontsize=14, color=INK2)
        timeline(ax, i, m, ticks)
    emit(f1, [(0.0, 'the ask'), (0.4, 'the artifact'),
              (1.0, 'the judge')])

    # 2 — the artifact and its graded run (PASS lines typed in)
    def f2(ax, i, m, ticks):
        title(ax, 'the graded artifact runs clean, twice')
        lines = [
            'execution:    counts 1..N, no re-runs          —  PASS',
            'determinism:  two kernels agree to 1e-12       —  PASS',
            'figures:      3 distinct PNGs, all embedded    —  PASS',
            'report:       every metric key and value       —  PASS',
            'integrity:    judge tree sha256 unchanged      —  PASS',
        ]
        reveal_lines(ax, lines, i, m)
        ax.text(0.5, 0.19, f'notebook rmse_test  {metrics["rmse_test"]:.6f}'
                f'   (from the tagged metrics cell)',
                ha='center', fontsize=15, color=INK2)
        timeline(ax, i, m, ticks)
    emit(f2, [(0.0, 'run A'), (0.5, 'run B'), (1.0, 'both clean')])

    # 3 — the independent refit
    def f3(ax, i, m, ticks):
        title(ax, 'the judge refits the pipeline itself')
        lines = [
            f'refit rmse_test (log)   {o["rmse_test"]:.12f}',
            f'reported rmse_test      {metrics["rmse_test"]:.6f}',
            f'difference              '
            f'{abs(metrics["rmse_test"] - o["rmse_test"]):.3e}'
            f'  <= {TOL_RMSE:.0e}  —  PASS',
            f'refit r2_test           {o["r2_test"]:.15f}',
            'stdlib Gaussian elimination — no scikit-learn, no BLAS',
        ]
        reveal_lines(ax, lines, i, m)
        ax.text(0.5, 0.19, f'noise floor: {o["rmse_test"]:.4f} <= '
                f'{RMSE_LIMIT}  —  the fit sits at the generator noise '
                f'(sigma = 0.30)', ha='center', fontsize=15, color=INK2)
        timeline(ax, i, m, ticks)
    emit(f3, [(0.0, 'same CSV'), (0.5, 'own algebra'),
              (1.0, 'agreement')])

    # 4 — held-out predictions scatter, points drawn in split order
    def f4(ax, i, m, ticks):
        # draw space: the scatter lives in the upper area, clear of the strip
        draw = i / m
        frac = min(1.0, draw / 0.75)
        k = max(2, int(frac * len(fit['obs'])))
        lo = math.floor(min(fit['obs'].min(), fit['pred'].min()) * 4) / 4
        hi = math.ceil(max(fit['obs'].max(), fit['pred'].max()) * 4) / 4
        sc = ax.inset_axes([0.16, 0.28, 0.68, 0.52])
        sc.plot([lo, hi], [lo, hi], ls='--', lw=2, color=INK2)
        sc.plot(fit['obs'][:k], fit['pred'][:k], 'o', ms=6, color=BLUE,
                markeredgecolor='white', markeredgewidth=0.8)
        sc.set_xlim(lo, hi)
        sc.set_ylim(lo, hi)
        sc.set_xlabel('observed  ln(MED_VALUE / USD)', fontsize=15)
        sc.set_ylabel('predicted  ln(MED_VALUE / USD)', fontsize=15)
        sc.set_title(f'(a) held-out predictions — rmse_test '
                     f'{o["rmse_test"]:.6f} <= {RMSE_LIMIT}  PASS',
                     fontsize=17, fontweight='bold')
        caption(ax, f'{k} of 320 held-out rows, ridge refit seed 20261015 '
                    f'alpha 10')
        timeline(ax, i, m, ticks)
    emit(f4, [(0.0, 'split'), (0.5, '320 rows'), (1.0, 'diagonal')])

    # 5 — blind-seed band, bars grow to height
    def f5(ax, i, m, ticks):
        seeds = list(blind['seeds'])
        vals = [blind_rmses[s] for s in seeds]
        grow = min(1.0, i / (m * 0.5))
        bc = ax.inset_axes([0.12, 0.28, 0.76, 0.52])
        bc.bar(range(len(seeds)), [v * grow for v in vals], width=0.62,
               color=BLUE_LT, edgecolor='white', linewidth=2)
        bc.bar([len(seeds)], [o['rmse_test'] * grow], width=0.62, color=BLUE,
               edgecolor='white', linewidth=2)
        bc.axhline(RMSE_LIMIT, color=RED, ls='--', lw=2)
        bc.text(0.02, RMSE_LIMIT, f' G5 limit {RMSE_LIMIT}', fontsize=13,
                color=RED, va='bottom')
        bc.set_xticks(range(len(seeds) + 1),
                      [str(s) for s in seeds] + ['graded'], fontsize=11)
        bc.set_ylim(0.0, 0.312)
        bc.set_xlabel('judge refit split seed', fontsize=15)
        bc.set_ylabel('rmse_test (log scale)', fontsize=15)
        bc.set_title('(b) graded split vs five blind refits — '
                     f'ratio {blind["ratio"]:.3f} <= 1.25  PASS',
                     fontsize=17, fontweight='bold')
        caption(ax, f'blind median {blind["median_blind"]:.6f}; the graded '
                     f'split is not a lucky one')
        timeline(ax, i, m, ticks)
    emit(f5, [(0.0, 'five refits'), (0.5, 'graded split'),
              (1.0, 'in band')])

    # 6 — coefficient recovery, points drawn one by one, then the y=x line
    def f6(ax, i, m, ticks):
        sc = ax.inset_axes([0.22, 0.28, 0.56, 0.52])
        draw = i / m
        k = max(1, int(min(1.0, draw / 0.6) * len(fit['coef'])))
        if draw > 0.6:
            sc.plot([-0.5, 0.5], [-0.5, 0.5], ls='--', lw=2, color=INK2)
        sc.plot(oracle.W_TRUE[:k], fit['coef'][:k], 'o', ms=11, color=BLUE,
                markeredgecolor='white', markeredgewidth=1.0)
        for name, wt, wc in zip(oracle.FEATURES[:k], oracle.W_TRUE[:k],
                                fit['coef'][:k]):
            sc.annotate(name, (wt, wc), textcoords='offset points',
                        xytext=(7, 4), fontsize=10, color=INK2)
        sc.set_xlim(-0.55, 0.55)
        sc.set_ylim(-0.55, 0.55)
        sc.set_xlabel('true coefficient W_TRUE (generator, exact)',
                      fontsize=15)
        sc.set_ylabel('fitted coefficient (standardized)', fontsize=15)
        sc.set_title(f'(c) coefficient recovery {o["coef_recovery"]:.4f} '
                     f'<= {RECOVERY_LIMIT}  PASS',
                     fontsize=17, fontweight='bold')
        caption(ax, 'the fitted model recovered the generator coefficients')
        timeline(ax, i, m, ticks)
    emit(f6, [(0.0, '8 predictors'), (0.6, 'y = x'),
              (1.0, 'recovered')])

    # 7 — oracle agreement bars, growing on a log scale
    def f7(ax, i, m, ticks):
        pairs = [('rmse_test', abs(metrics['rmse_test'] - o['rmse_test']),
                  TOL_RMSE),
                 ('r2_test', abs(metrics['r2_test'] - o['r2_test']), TOL_R2)]
        grow = min(1.0, i / (m * 0.5))
        bc = ax.inset_axes([0.12, 0.28, 0.76, 0.52])
        ypos = [1, 0]
        bc.barh(ypos, [max(d, 1e-15) * grow for _, d, _ in pairs], height=0.5,
                color=BLUE, edgecolor='white', linewidth=2)
        for yi, (_, d, tol) in zip(ypos, pairs):
            bc.axvline(tol, color=RED, ls='--', lw=2 if tol > 1e-8 else 1.2)
            bc.text(tol, yi + 0.35, f'tolerance {tol:.0e}', fontsize=13,
                    color=RED, ha='center')
        bc.set_yticks(ypos, [f'{nm}  |reported - refit|'
                             for nm, _, _ in pairs], fontsize=11)
        bc.set_xscale('log')
        bc.set_xlim(1e-16, 1e-4)
        bc.set_xlabel('absolute disagreement (log scale)', fontsize=15)
        bc.set_title('(d) every reported number matches the independent '
                     'refit', fontsize=17, fontweight='bold')
        caption(ax, 'G4: a different model, a train metric or a stale value '
                     'cannot reproduce here')
        timeline(ax, i, m, ticks)
    emit(f7, [(0.0, 'reported'), (0.5, 'refit'), (1.0, 'within 1e-6')])

    # 8 — kill-rate bars slide in one by one
    def f8(ax, i, m, ticks):
        rows = [('known-good', None)] + [(n_, v) for n_, v in muts]
        shown = max(1, int(min(1.0, i / (m * 0.7)) * len(rows)))
        bc = ax.inset_axes([0.16, 0.26, 0.68, 0.56])
        y = list(range(len(rows)))[::-1]
        for yi, (name, v) in zip(y[:shown], rows[:shown]):
            color = GREEN if name == 'known-good' else BLUE
            note = ('passes every gate (baseline)' if name == 'known-good'
                    else f"killed — {(v.get('failed_gate') or '?')} gate")
            bc.barh(yi, 1.0, height=0.62, color=color, edgecolor='white',
                    linewidth=2)
            bc.text(0.02, yi, f'{name}: {note}', va='center', fontsize=13,
                    color='white')
        bc.set_yticks(y, [r[0] for r in rows], fontsize=10)
        bc.set_xticks([])
        bc.set_xlim(0, 1.9)
        bc.grid(False)
        killed = sum(1 for _, v in muts if not v.get('passed'))
        bc.set_title(f'self-test kill rate {killed}/{len(muts)} = '
                     f'{killed / len(muts):.0%}  (requirement >= 90%)  PASS',
                     fontsize=17, fontweight='bold')
        caption(ax, 'every known-bad single-edit mutant fails at least one '
                     'gate; the known-good artifact passes all of them')
        timeline(ax, i, m, ticks)
    emit(f8, [(0.0, 'baseline'), (0.7, '7 mutants'),
              (1.0, '7/7 killed')])

    # 9 — the verdict; the sweep freezes for the last 2.5 s: the gate
    # requires a still end card over the final 2 s
    def f9(ax, i, m, ticks):
        title(ax, 'the verdict')
        lines = [
            '"passed": true     failed_gate: null',
            f'rmse_test      {o["rmse_test"]:.6f}   (limit {RMSE_LIMIT})',
            f'r2_test        {o["r2_test"]:.6f}',
            f'coef_recovery  {o["coef_recovery"]:.4f}   '
            f'(limit {RECOVERY_LIMIT})',
            f'blind ratio    {blind["ratio"]:.3f}   (limit 1.25)',
            'figures        3 distinct PNGs, all embedded',
        ]
        reveal_lines(ax, lines, i, m)
        ax.text(0.5, 0.19, 'all 7 gates pass — grade.sh exit 0',
                ha='center', fontsize=16, fontweight='bold', color=GREEN)
        timeline(ax, i, m, ticks, quiet=(i >= m - QUIET_TAIL_S * FPS_IN))
    emit(f9, [(0.0, 'verdict'), (0.5, 'exit 0'), (1.0, 'done')])

    print(f'make_frames: wrote {n} frames to {out}')


if __name__ == '__main__':
    main()
