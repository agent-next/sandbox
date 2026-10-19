"""loop.png -- the agent loop and the self-test kill-rate bar.

Reads the verdict JSONs written by make_data.py (real judge output):
  - left: the loop stage (broken -> partial -> good) against the gate count
    the judge requires (5/5 flags, 5/5 oracle checks, 0/5 negative control,
    clean blast radius);
  - right: the self-test kill matrix, known-good vs each killed mutant.

usage: python3 -I fig_loop.py <data_dir> <out.png>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MUTANTS = ["admin-mode-fixed", "broken-compile", "flag-baked",
           "offbyone-fixed", "status-leak", "token-secret",
           "traversal-fixed", "writes-a-file"]

# colour-blind-safe (Okabe-Ito)
GREEN = "#009E73"
RED = "#D55E00"
BLUE = "#0072B2"
GREY = "#999999"


def load_verdict(p: Path) -> dict:
    return json.loads(p.read_text())


def loop_stage(verdict: dict) -> tuple[str, int, int, int]:
    """(stage, flags captured, oracle checks passed, negative-control hits).

    Counts the per-challenge checks, not the gate's own `passed` field:
    that field is a bool when the gate ran to the end and an int when it
    errored early, and both would print as True/False in an annotation.
    """
    g = verdict.get("gates", {})
    flags = g.get("flags", {}).get("captured", 0)
    oracle = sum(1 for c in g.get("oracle", {}).get("checks", {}).values()
                 if c is True)
    neg = g.get("negative_control", {}).get("captured", 0)
    return (verdict.get("seed", 0), flags, oracle, neg)


def main() -> int:
    data = Path(sys.argv[1])
    out = Path(sys.argv[2])
    verdicts = data / "verdicts"

    stages = []
    for name in ("01-broken", "02-partial", "03-good"):
        v = load_verdict(verdicts / f"{name}.json")
        stages.append((name, *loop_stage(v)[1:]))

    mutant_names, killed, survived = [], [], []
    for m in MUTANTS:
        p = verdicts / f"mutant-{m}.json"
        if not p.exists():
            continue
        v = load_verdict(p)
        mutant_names.append(m)
        if v.get("passed"):
            survived.append(m)
        else:
            killed.append(m)

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(12.4, 5.2), gridspec_kw={"width_ratios": [1, 1.35]})

    # --- left: the agent loop ---
    xs = [s[0] for s in stages]
    flags = [s[1] for s in stages]
    oracle = [s[2] for s in stages]
    neg = [s[3] for s in stages]
    ax1.plot(xs, flags, "o-", color=GREEN, lw=2.5, ms=9,
             label="flags captured (need 5)")
    ax1.plot(xs, oracle, "s-", color=BLUE, lw=2.5, ms=9,
             label="independent oracle checks (need 5)")
    ax1.plot(xs, neg, "^-", color=RED, lw=2.5, ms=9,
             label="negative-control flags (need 0)")
    ax1.axhline(5, color=GREEN, ls=":", lw=1)
    ax1.axhline(0, color=RED, ls=":", lw=1)
    for x, f, o, n in zip(xs, flags, oracle, neg):
        ax1.annotate(f"{f}/5", (x, f), textcoords="offset points",
                     xytext=(0, 9), ha="center", fontsize=10, color=GREEN)
        ax1.annotate(f"{o}/5", (x, o), textcoords="offset points",
                     xytext=(0, -18), ha="center", fontsize=10, color=BLUE)
        ax1.annotate(f"{n}", (x, n), textcoords="offset points",
                     xytext=(0, 9), ha="center", fontsize=10, color=RED)
    ax1.set_xticks(xs, [s[0].replace("-", "\n") for s in stages])
    ax1.set_ylim(-1.2, 6.2)
    ax1.set_xlabel("agent loop stage (real judge verdicts)")
    ax1.set_ylabel("count")
    ax1.set_title("The agent loop: gates cleared one at a time", fontsize=12)
    ax1.legend(fontsize=9, loc="center left")
    ax1.grid(alpha=0.25)

    # --- right: the self-test kill matrix ---
    ys = list(range(len(mutant_names)))[::-1]
    colours = [GREEN if m in killed else RED for m in mutant_names]
    ax2.barh(ys, [1 if m in killed else 0 for m in mutant_names],
             color=colours, height=0.62)
    for y, m in zip(ys, mutant_names):
        v = load_verdict(verdicts / f"mutant-{m}.json")
        gate = v.get("failed_gate", "?")
        ax2.text(0.05, y, f"killed ({gate})" if m in killed else "SURVIVED",
                 va="center", fontsize=10,
                 color="white" if m in killed else "black")
    ax2.set_yticks(ys, mutant_names, fontsize=9)
    ax2.set_xlim(0, 1)
    ax2.set_xticks([])
    ax2.set_title(f"Self-test kill rate: {len(killed)}/{len(mutant_names)}",
                  fontsize=12)
    for spine in ("top", "right", "bottom"):
        ax2.spines[spine].set_visible(False)

    fig.suptitle("ctf-flag-hunt: judge gates over the agent loop and the "
                 "mutant kill matrix", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out, dpi=150)
    print(f"fig_loop: wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
