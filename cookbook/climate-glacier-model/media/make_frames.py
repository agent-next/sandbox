#!/usr/bin/env python3
"""Render the demo video frames: the glacier retreating, year by year.

The physics here *is* time-dependent (the length relaxes toward L_eq every
year), so the video animates the real sweep rather than stepping through
static figures: the three volume curves draw themselves in over the 100
years, the 50 %-crossing line is fixed, and each scenario's crossing year is
marked as its curve reaches it.  Frames come from the same volumes.csv the
judge read (media/data/run/good/volumes.csv) -- no invented data.

Usage: make_frames.py <demo-dir> <framedir>
Writes 1920x1080 PNG frames named f0000.png .. to <framedir>.
"""

import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SCENARIOS = ("warm_2p0", "warm_2p4", "warm_2p8")
COLORS = {"warm_2p0": "#4C72B0", "warm_2p4": "#DD8452", "warm_2p8": "#55A868"}
YEARS = 100
FPS = 30
HOLD = 90          # frames held on the final state (3 s)
STEPS = 100        # animation steps (one per year)
REPEAT = 6         # frames each step is held -> 100*6/30 = 20 s of motion


def read_csv(path):
    table = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            table.setdefault(row["scenario"], {})[int(row["year"])] = \
                float(row["volume_km3"])
    return table


def draw(ax, table, crossings, upto):
    ax.clear()
    years = list(range(upto + 1))
    for name in SCENARIOS:
        vols = [table[name][y] for y in years]
        ax.plot(years, vols, lw=2.6, color=COLORS[name], label=name)
        cy = crossings[name]
        if cy is not None and cy <= upto:
            v = table[name][int(cy)]
            ax.plot([cy], [v], marker="o", ms=9, color=COLORS[name],
                    mec="k", mew=1.0)
    v0 = table["warm_2p0"][0]
    ax.axhline(0.5 * v0, ls=":", lw=1.8, color="#333333")
    ax.text(1.0, 0.5 * v0 + 0.05, "50 % of V(0)  (crossing rule)",
            fontsize=13, color="#333333")
    ax.set_xlim(0, YEARS)
    ax.set_ylim(0.8, 6.3)
    ax.set_xlabel("year (yr)", fontsize=15)
    ax.set_ylabel("glacier volume (km³)", fontsize=15)
    ax.set_title(f"Synthetic glacier retreat — 100-yr SMB sweep, "
                 f"year {upto}", fontsize=19)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=14)
    ax.tick_params(labelsize=12)
    # live readout of each scenario's current volume
    lines = [f"{n}: {table[n][upto]:.3f} km³" for n in SCENARIOS]
    ax.text(0.02, 0.03, "   ".join(lines), transform=ax.transAxes,
            fontsize=12, color="#222222", family="monospace")


def main():
    demo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent
    framedir = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        Path(__file__).parent / "frames"
    media = demo / "media"
    framedir.mkdir(parents=True, exist_ok=True)
    table = read_csv(media / "data" / "run" / "good" / "volumes.csv")
    verdict = json.loads((media / "data" / "verdicts" / "good.json").read_text())
    crossings = {n: verdict["gates"]["crossing"]["scenarios"][n]["reported_year"]
                 for n in SCENARIOS}

    fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
    n = 0
    for upto in range(0, YEARS + 1, YEARS // STEPS):
        draw(ax, table, crossings, upto)
        fig.tight_layout()
        for _ in range(REPEAT):
            fig.savefig(framedir / f"f{n:04d}.png")
            n += 1
    draw(ax, table, crossings, YEARS)
    for _ in range(HOLD):
        fig.tight_layout()
        fig.savefig(framedir / f"f{n:04d}.png")
        n += 1
    plt.close(fig)
    print(f"wrote {n} frames to {framedir} ({FPS} fps, {n / FPS:.1f}s)")


if __name__ == "__main__":
    main()
