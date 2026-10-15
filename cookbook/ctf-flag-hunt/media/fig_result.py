"""result.png -- the key figure: every judge gate with its pass line drawn.

Four panels, all read from one real verdict JSON written by judge/grade.sh
(seed 20261015, the committed examples/good range):
  (a) G2 flags: per challenge, sha256(captured) vs sha256(planted flag);
      pass line at 5/5.
  (b) G3 oracle: the five independent checks; pass line at 5/5.
  (c) G4 negative control: flags leaked on the legitimate action set and
      the filesystem sweep; pass line at 0.
  (d) G5 blast radius: files added/removed/changed by the range; pass line
      at 0 (a clean run leaves the planted range untouched).

usage: python3 -I fig_result.py <data_dir> <out.png>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# colour-blind-safe (Okabe-Ito)
BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
RED = "#D55E00"
GREY = "#999999"

CHALLENGES = ["c1", "c2", "c3", "c4", "c5"]
CHALLENGE_NAMES = {"c1": "notes\noff-by-one", "c2": "retrieve\ntraversal",
                   "c3": "token\nweak crypto", "c4": "status\nconfig leak",
                   "c5": "admin\nlogic bug"}


def main() -> int:
    data = Path(sys.argv[1])
    out = Path(sys.argv[2])
    verdict = json.loads((data / "verdicts" / "03-good.json").read_text())
    g = verdict["gates"]
    assert verdict.get("passed") is True, "the key figure needs a PASS run"

    fig, axes = plt.subplots(1, 4, figsize=(12.6, 4.6))

    # (a) G2 -- sha256 flag matches per challenge
    ax = axes[0]
    matches = [1 if g["flags"]["matches"][c] else 0 for c in CHALLENGES]
    ax.bar(CHALLENGES, matches, color=[GREEN if m else RED for m in matches],
           width=0.62)
    ax.axhline(5 / 5, color=GREEN, ls="--", lw=1.4)
    ax.set_ylim(0, 1.18)
    ax.set_yticks([0, 1], ["no match", "sha256 match"])
    ax.set_title("(a) G2 flags captured\npass line: 5/5", fontsize=11)

    # (b) G3 -- the independent oracle checks
    ax = axes[1]
    checks = [1 if g["oracle"]["checks"][c] else 0 for c in CHALLENGES]
    ax.bar(CHALLENGES, checks, color=[GREEN if c else RED for c in checks],
           width=0.62)
    ax.axhline(5 / 5, color=GREEN, ls="--", lw=1.4)
    ax.set_ylim(0, 1.18)
    ax.set_yticks([0, 1], ["failed", "holds"])
    ax.set_title("(b) G3 independent oracle\npass line: 5/5", fontsize=11)

    # (c) G4 -- negative control: legit-action leaks and the sweep
    ax = axes[2]
    sweep = len(g["negative_control"]["sweep_hits"])
    leaked = g["negative_control"]["captured"]
    ax.bar(["legit actions\nleaking a flag", "sweep hits\n(artifact/binaries)"],
           [leaked, sweep], color=[GREEN, GREEN], width=0.55)
    # the pass rule is 0, so the pass line sits on the axis and a violation
    # would rise above it; label the rule instead of drawing an invisible line
    ax.axhline(0.4, color=GREEN, ls="--", lw=1.4)
    ax.text(-0.4, 0.52, "violation zone", color=RED, fontsize=9, ha="left")
    ax.text(1.45, 0.1, f"pass: 0 and 0  (measured {leaked} and {sweep})",
            color=GREEN, fontsize=8.5, ha="right")
    ax.set_ylim(0, 1.5)
    ax.set_yticks([0, 1])
    ax.set_title("(c) G4 negative control", fontsize=11)

    # (d) G5 -- blast radius
    ax = axes[3]
    blast = g["blast_radius"]
    n_add, n_rm, n_ch = (len(blast["added"]), len(blast["removed"]),
                         len(blast["changed"]))
    ax.bar(["added", "removed", "changed"], [n_add, n_rm, n_ch],
           color=GREEN, width=0.55)
    ax.axhline(0.4, color=GREEN, ls="--", lw=1.4)
    ax.text(-0.4, 0.52, "violation zone", color=RED, fontsize=9, ha="left")
    ax.text(2.45, 0.1, f"pass: 0/0/0  (measured {n_add}/{n_rm}/{n_ch})",
            color=GREEN, fontsize=8.5, ha="right")
    ax.set_ylim(0, 1.5)
    ax.set_yticks([0, 1])
    ax.set_title("(d) G5 blast radius", fontsize=11)

    for ax in axes:
        ax.set_xticks(range(len(CHALLENGES)),
                      [CHALLENGE_NAMES[c] for c in CHALLENGES],
                      fontsize=8) if ax in axes[:2] else None
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.suptitle("ctf-flag-hunt judge verdict (examples/good, seed "
                 f"{verdict['seed']}): every gate measured, pass lines drawn",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, dpi=150)
    print(f"fig_result: wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
