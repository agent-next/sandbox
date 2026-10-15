#!/usr/bin/env python3
"""loop.png: the agent loop and the self-test kill matrix.

Top  - the fixing-agent loop replayed through the judge: each iteration is a
       real 'judge/grade.sh <artifact> --json' run (media/data/replay/), from
       the grossly wrong first attempt (scale_inch_mm) through partly-fixed
       attempts to the known-good artifact, with the number of gates passing
       per iteration and the 14/14 pass line drawn.  This is a replay of
       graded verdicts, not a live agent trace.
Bottom - the mutant x gate matrix from the verdict JSONs (known-good + the 10
       scripted mutants x 14 gates): green = gate passed, red = gate failed on
       its own evidence with the measured value vs the limit parsed from the
       judge's own error string, gray = skipped because an earlier gate
       failed.  Plus the self-test kill rate from media/data/selftest.log.
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as rd  # noqa: E402

MUTANTS = [
    "wrong_bolt_count", "wrong_pcd", "bore_off", "boss_missing",
    "scale_inch_mm", "stl_flipped_facet", "stl_not_watertight",
    "dxf_missing_hole", "edge_violation", "tangential_hole_drift",
]
MUTANT_LABEL = {
    "wrong_bolt_count": "wrong_bolt_count (5 holes)",
    "wrong_pcd": "wrong_pcd (⌀66 vs ⌀56)",
    "bore_off": "bore_off (⌀24.5 vs ⌀24)",
    "boss_missing": "boss_missing",
    "scale_inch_mm": "scale_inch_mm (×25.4)",
    "stl_flipped_facet": "stl_flipped_facet",
    "stl_not_watertight": "stl_not_watertight",
    "dxf_missing_hole": "dxf_missing_hole",
    "edge_violation": "edge_violation",
    "tangential_hole_drift": "tangential_hole_drift (0.5 mm)",
}


def main():
    vdir = rd.verdicts_dir()
    needed = ["good.json"] + [f"{m}.json" for m in MUTANTS]
    for n in needed:
        p = os.path.join(vdir, n)
        if not os.path.isfile(p):
            raise SystemExit(f"loop: missing judge verdict {p} - run "
                             "'bash media/make_media.sh data' first")
    replay_files = sorted(glob.glob(os.path.join(rd.DATA, "replay", "iter*.json")))
    if len(replay_files) < 3:
        raise SystemExit("loop: missing replay verdicts in media/data/replay/")

    good = rd.load_verdict(os.path.join(vdir, "good.json"))
    verdicts = {"good": good}
    for m in MUTANTS:
        verdicts[m] = rd.load_verdict(os.path.join(vdir, f"{m}.json"))

    kill = "10/10"
    det = "PASS"
    with open(os.path.join(rd.DATA, "selftest.log")) as f:
        slog = f.read()
    mk = re.search(r"kill rate (\d+)/(\d+)", slog)
    if mk:
        kill = f"{mk.group(1)}/{mk.group(2)}"
    if "determinism PASS" not in slog:
        raise SystemExit("loop: selftest.log does not show determinism PASS")

    fig = rd.plt.figure(figsize=(12.4, 8.2), dpi=200, facecolor=rd.SURFACE)
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.55], left=0.185,
                          right=0.985, top=0.835, bottom=0.075, hspace=0.52)

    fig.text(0.015, 0.955, "cad-verify-back: the agent loop, judged from the delivered files",
             fontsize=17, fontweight="bold", color=rd.INK, va="center")
    fig.text(0.015, 0.890,
             f"grade.sh verdict per iteration (replay of a fixing agent: bad → partly "
             f"fixed → good; graded, not a live trace) · kill rate {kill} · "
             f"determinism PASS",
             fontsize=9.2, color=rd.INK2, va="center")

    # ---- top: replay of the fixing-agent loop -------------------------------
    ax = fig.add_subplot(gs[0])
    rd.style_axes(ax)
    labels, npass, notes = [], [], []
    for p in replay_files:
        v = rd.load_verdict(p)
        name = os.path.basename(p).split("_", 1)[1].rsplit(".", 1)[0]
        labels.append(name.replace("_", "\n"))
        npass.append(rd.n_pass(v))
        fails = rd.named_fails(v)
        notes.append(f"{rd.n_pass(v)}/14\n" + (", ".join(fails[:2]) +
                    ("…" if len(fails) > 2 else "") if fails else "PASS"))
    x = list(range(len(npass)))
    ax.plot(x, npass, color=rd.BLUE, linewidth=2.0, marker="o",
            markersize=7, markerfacecolor=rd.BLUE,
            markeredgecolor=rd.SURFACE, markeredgewidth=1.5, zorder=4)
    ax.axhline(14, color=rd.GOOD, linewidth=1.4, zorder=2)
    ax.text(len(x) - 0.42, 14.25, "all 14 gates pass (verdict PASS, exit 0)",
            fontsize=7.5, color=rd.GOOD, ha="right", va="bottom")
    for xi, yi, note in zip(x, npass, notes):
        ax.annotate(note, (xi, yi), textcoords="offset points",
                    xytext=(0, -30 if yi > 6 else 16), fontsize=6.6,
                    color=rd.INK2, ha="center",
                    arrowprops=dict(arrowstyle="-", color=rd.GRID, lw=0.7))
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.2, color=rd.INK2)
    ax.set_ylim(0, 15.6)
    ax.set_yticks([0, 4, 8, 12, 14])
    # explicit xlim with a right margin so the pass-line label (right-aligned
    # at len(x)-0.42) stays inside the axes and cannot run off the figure
    ax.set_xlim(-0.45, len(x) - 0.05)
    ax.set_ylabel("gates passing (of 14)", fontsize=8, color=rd.INK2)
    ax.set_title("judge feedback per iteration — gates passing out of 14, "
                 "with the gates that failed on their own evidence",
                 fontsize=9, color=rd.INK2, pad=6, loc="left")

    # ---- bottom: mutant x gate matrix ---------------------------------------
    axm = fig.add_subplot(gs[1])
    rows = ["good"] + MUTANTS
    rowlabels = ["good (examples/good)"] + [MUTANT_LABEL[m] for m in MUTANTS]
    n_r, n_c = len(rows), len(rd.GATE_ORDER)
    axm.set_xlim(0, n_c)
    axm.set_ylim(0, n_r)
    axm.invert_yaxis()
    for j, gate in enumerate(rd.GATE_ORDER):
        axm.text(j + 0.5, -0.62, rd.GATE_SHORT[gate], fontsize=6.6,
                 color=rd.INK2, ha="center", va="bottom")
    for i, row in enumerate(rows):
        axm.text(-0.15, i + 0.5, rowlabels[i], fontsize=7.2, color=rd.INK,
                 ha="right", va="center")
        v = verdicts[row]
        for j, gate in enumerate(rd.GATE_ORDER):
            gg = v["gates"][gate]
            err = str(gg.get("error", ""))
            if gg["pass"]:
                fc, txt, tc, fs = rd.GOOD_WASH, "PASS", rd.INK2, 5.6
            elif err.startswith("skipped"):
                fc, txt, tc, fs = rd.SKIP_WASH, "skip", rd.MUTED, 5.6
            else:
                fc, tc = rd.CRIT, "white"
                a, b = rd.fail_short(gate, err)
                txt = f"{a}\n{b}" if b else a
                fs = 5.6
            axm.add_patch(rd.matplotlib.patches.Rectangle(
                (j + 0.04, i + 0.10), 0.92, 0.80, facecolor=fc,
                edgecolor=rd.SURFACE, linewidth=1.0))
            axm.text(j + 0.5, i + 0.5, txt, fontsize=fs, color=tc,
                     ha="center", va="center", linespacing=1.25)
    axm.xaxis.set_ticks_position("top")
    axm.set_xticks([])
    axm.set_yticks([])
    for s in axm.spines.values():
        s.set_visible(False)
    axm.set_title(f"self-test matrix: every mutant fails ≥ 1 gate on its own "
                  f"evidence — kill rate {kill} (each red cell shows the judge's "
                  f"measured value vs that gate's limit)",
                  fontsize=9, color=rd.INK2, pad=34, loc="left")

    handles = [
        rd.matplotlib.patches.Patch(facecolor=rd.GOOD_WASH,
                                    edgecolor=rd.GOOD, label="gate PASS"),
        rd.matplotlib.patches.Patch(facecolor=rd.CRIT,
                                    label="gate FAIL: measured vs limit"),
        rd.matplotlib.patches.Patch(facecolor=rd.SKIP_WASH,
                                    label="skipped (earlier gate failed)"),
    ]
    axm.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.055),
               ncol=3, fontsize=7.2, frameon=False)

    rd.assert_no_overlaps(fig, "loop.png", ignore_xy=True)

    out = os.path.join(rd.HERE, "loop.png")
    fig.savefig(out, dpi=200, facecolor=rd.SURFACE)
    print(f"loop.png written ({os.path.getsize(out)} bytes)")


if __name__ == "__main__":
    main()
