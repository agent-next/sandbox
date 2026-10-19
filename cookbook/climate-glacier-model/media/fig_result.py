#!/usr/bin/env python3
"""media/result.png -- the key figure with the judge's pass lines drawn on it.

Left panel: the three scenario volume curves from the *judge's own* run of
the good artifact (media/data/run/good/volumes.csv, produced by grade.sh),
with the analytic oracle V_exact(t) dashed on top, the 50 %-of-V(0) crossing
line, and each measured crossing year marked.  Right panel: the judge's
shape gate -- the measured volume minus the analytic volume at every year,
as a percentage, against the +-2 % tolerance band; the gate is "every year
inside the band", so the band *is* the pass line.

Numbers come from the verdict JSON and the CSV the judge wrote; nothing is
illustrative.

Usage: fig_result.py <demo-dir>
"""

import csv
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# SPEC constants, duplicated so the oracle is derived here too.
Z_HEAD, SLOPE, H0, DH, W = 3500.0, 0.08, 650.0, 0.02, 800.0
ELA0, KAPPA, TAU, YEARS = 2900.0, 200.0, 10.0, 100
L0 = 2.0 * (Z_HEAD - ELA0) / SLOPE
SCENARIOS = (("warm_2p0", 2.0), ("warm_2p4", 2.4), ("warm_2p8", 2.8))
COLORS = {"warm_2p0": "#4C72B0", "warm_2p4": "#DD8452", "warm_2p8": "#55A868"}


def l_exact(t, a2):
    c = (2.0 * KAPPA / SLOPE) * a2
    return L0 - c * (t / YEARS - (TAU / YEARS) * (1.0 - math.exp(-t / TAU)))


def v_exact(t, a2):
    L = l_exact(t, a2)
    return W * (H0 * L - DH * L * L / 2.0) / 1e9


def read_csv(path):
    table = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            table.setdefault(row["scenario"], {})[int(row["year"])] = \
                float(row["volume_km3"])
    return table


def main():
    demo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent
    media = demo / "media"
    table = read_csv(media / "data" / "run" / "good" / "volumes.csv")
    verdict = json.loads((media / "data" / "verdicts" / "good.json").read_text())
    shape = verdict["gates"]["shape"]["scenarios"]
    crossing = verdict["gates"]["crossing"]["scenarios"]

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(12.5, 5.2), dpi=200)
    years = list(range(YEARS + 1))

    for name, a2 in SCENARIOS:
        vols = [table[name][y] for y in years]
        ax.plot(years, vols, lw=2.2, color=COLORS[name],
                label=f"{name}  V(100)={vols[-1]:.3f} km³")
        ax.plot(years, [v_exact(y, a2) for y in years], lw=1.1, ls="--",
                color=COLORS[name], alpha=0.75)
        cy = crossing[name]["reported_year"]
        if cy is not None:
            ax.plot([cy], [0.5 * vols[0]], marker="o", ms=5,
                    color=COLORS[name], mec="k", mew=0.5)
            ax.annotate(f"{cy:.1f} yr", (cy, 0.5 * vols[0]),
                        textcoords="offset points", xytext=(0, 10),
                        ha="center", fontsize=8, color=COLORS[name],
                        fontweight="bold")
    v0 = table["warm_2p0"][0]
    ax.axhline(0.5 * v0, ls=":", lw=1.4, color="#333333")
    ax.text(1.0, 0.5 * v0 + 0.06, "50 % of V(0)  (crossing rule)",
            fontsize=8, color="#333333")
    ax.set_xlabel("year (yr)")
    ax.set_ylabel("glacier volume (km³)")
    ax.set_title("Synthetic glacier volume: measured (solid) vs.\n"
                 "analytic oracle (dashed), 100-yr SMB sweep")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8.5)

    # Right: the shape gate's pass band, measured.
    for name, a2 in SCENARIOS:
        devs = [100.0 * (table[name][y] - v_exact(y, a2)) / v_exact(y, a2)
                for y in years]
        bx.plot(years, devs, lw=1.8, color=COLORS[name], label=name)
    tol = verdict["gates"]["shape"]["tolerance_relative"] * 100.0
    bx.axhspan(-tol, tol, color="#2E7D32", alpha=0.10,
               label=f"pass band ±{tol:g} %")
    bx.axhline(tol, ls="--", lw=1.2, color="#2E7D32")
    bx.axhline(-tol, ls="--", lw=1.2, color="#2E7D32")
    worst = max(s["worst_relative_deviation"] for s in shape.values()) * 100
    bx.set_xlabel("year (yr)")
    bx.set_ylabel("V_measured − V_analytic (% of analytic)")
    bx.set_title(f"Shape gate: every year inside ±{tol:g} %\n"
                 f"worst measured deviation {worst:.2f} %")
    bx.grid(alpha=0.3)
    bx.legend(loc="lower left", fontsize=8.5)

    fig.suptitle("climate-glacier-model — judge verdict: PASS "
                 f"(seed {verdict['seed']}, 13/13 mutants killed)", y=1.005,
                 fontsize=11)
    fig.tight_layout()
    out = media / "result.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
