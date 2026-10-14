#!/usr/bin/env python3
"""loop.png -- known-good + 14 mutants x the 8 judge gates.

Every cell is read from media/data/verdict-*.json (real grade.sh output,
seed 20260814).  Green = pass; red = a behavioural gate fired, with the
measured value in the cell; amber = the build-only kill (no ELF ever
existed, so the runtime gates report "no ELF" -- not behavioural
evidence).  Row order follows the SPEC.md mutant table.
"""

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, GATES, MUTANTS, C_PASS, C_FAIL, C_BUILD, C_BG,
                    C_DIM, load_verdict, cell_short, check_no_overlap)

MONO = "DejaVu Sans Mono"

# Row order: good first, then the SPEC.md mutant families.
ROWS = ["good",
        "ring-off-by-one", "ring-drop-newest", "ring-count-drift",
        "crc-poly", "crc-no-xorout", "crc-init", "crc-shift-dir",
        "shell-unknown-ok", "shell-bad-hex-accepted",
        "uart-no-init", "uart-rx-inverted",
        "startup-no-reset", "startup-bad-sp",
        "build-broken"]

# Gates that observe the firmware running (same set selftest.sh uses).
BEHAV = {"boot", "shell", "crc_oracle", "no_hardfault"}

GATE_SHORT = {"build_clean": "build\nclean", "elf_ok": "elf\nok",
              "maps_ok": "maps\nok", "boot": "boot",
              "shell": "shell", "crc_oracle": "crc\noracle",
              "no_hardfault": "no\nhardfault", "judge_intact": "judge\nintact"}


def kill_class(gates):
    bad = [k for k, v in gates.items() if v["verdict"] != "pass"]
    if not bad:
        return "good"
    if "build_clean" in bad:
        return "build-only"
    if any(k in BEHAV for k in bad):
        return "behavioural"
    return "static-only"


def main():
    verdicts = {name: load_verdict(name) for name in ROWS}
    for name in MUTANTS:
        assert name in verdicts, name

    fig = plt.figure(figsize=(16, 9.5), dpi=200, facecolor="#ffffff")
    fig.suptitle("firmware-qemu self-test: one judge, 14 known-bad mutants",
                 fontsize=16, fontweight="bold", x=0.5, y=0.978)

    ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    x0, x1 = 0.155, 0.865          # gate cell band
    ytop, dy = 0.868, 0.0495       # first row top / row height
    cw = (x1 - x0) / len(GATES)
    pad = 0.0035

    # column headers
    for j, gate in enumerate(GATES):
        ax.text(x0 + cw * (j + 0.5), ytop + 0.055, GATE_SHORT[gate],
                family=MONO, fontsize=9.5, fontweight="bold",
                color="#1a1a1a", ha="center", va="center")
    ax.text(x0 - 0.008, ytop + 0.055, "artifact", family=MONO, fontsize=9.5,
            fontweight="bold", color="#1a1a1a", ha="right", va="center")
    ax.text(0.935, ytop + 0.055, "kill class /\ngates passed", family=MONO,
            fontsize=9.5, fontweight="bold", color="#1a1a1a",
            ha="center", va="center")

    texts = []
    for i, name in enumerate(ROWS):
        y = ytop - i * dy
        v = verdicts[name]
        kclass = kill_class(v["gates"])
        label = "examples/good" if name == "good" else name
        ax.text(x0 - 0.008, y, label, family=MONO, fontsize=9.3,
                color="#1a1a1a" if name == "good" else "#30363d",
                fontweight="bold" if name == "good" else "normal",
                ha="right", va="center")
        for j, gate in enumerate(GATES):
            g = v["gates"][gate]
            ok = g["verdict"] == "pass"
            x = x0 + j * cw
            if ok:
                fc, tc = "#d7f0e5", C_PASS
                txt = "pass"
            elif kclass == "build-only":
                fc, tc = "#fde9c8", "#9a5b00"
                txt = cell_short(g["detail"])
            else:
                fc, tc = "#fbe0d4", "#a03d00"
                txt = cell_short(g["detail"])
            ax.add_patch(Rectangle((x + pad, y - dy * 0.36),
                                   cw - 2 * pad, dy * 0.72,
                                   fc=fc, ec="none"))
            texts.append(ax.text(x + cw / 2, y, txt, family=MONO,
                                 fontsize=7.4 if not ok else 8.2, color=tc,
                                 ha="center", va="center",
                                 fontweight="bold"))
        cls_col = {"good": C_PASS, "behavioural": C_FAIL,
                   "build-only": "#9a5b00", "static-only": "#6e7781"}[kclass]
        ax.text(0.935, y + 0.011, kclass, family=MONO, fontsize=8.6,
                color=cls_col, ha="center", va="center", fontweight="bold")
        ax.text(0.935, y - 0.014, "%d/%d" % (v["gates_passed"],
                                           v["gates_total"]),
                family=MONO, fontsize=8, color=C_DIM, ha="center",
                va="center")

    # footer: replayed agent loop + kill-rate summary from the same files
    loop_doc = None
    lp = os.path.join(DATA, "loop.json")
    with open(lp) as fh:
        import json
        loop_doc = json.load(fh)
    steps = []
    for s in loop_doc["steps"]:
        v = verdicts.get(s["artifact"].replace("examples/", "")) \
            or load_verdict(s["artifact"])
        steps.append("%s %d/8" % (s["artifact"], v["gates_passed"]))
    ax.text(0.02, 0.115,
            "replayed fix sequence (media/data/loop.json; real verdicts, "
            "not a live agent trace):  " + "  ->  ".join(steps),
            family=MONO, fontsize=8.4, color="#30363d", va="center")

    ax.text(0.02, 0.082,
            "kill rate 14/14 = 13 behavioural + 1 build-only "
            "(behavioural kill rate 100%; selftest floor 90%)  --  "
            "media/data/selftest.log",
            family=MONO, fontsize=8.6, color="#1a1a1a", va="center",
            fontweight="bold")

    # legend
    lx = 0.02
    for label, fc, tc in [("pass", "#d7f0e5", C_PASS),
                          ("behavioural gate failed "
                           "(value = judge's measurement)",
                           "#fbe0d4", "#a03d00"),
                          ("build-only kill (build failed; runtime gates "
                           "report no ELF)", "#fde9c8", "#9a5b00")]:
        ax.add_patch(Rectangle((lx, 0.028), 0.016, 0.024, fc=fc, ec=tc))
        ax.text(lx + 0.021, 0.04, label, family=MONO, fontsize=8,
                color="#30363d", va="center")
        lx += 0.021 + len(label) * 0.0062 + 0.02

    ax.text(0.02, 0.006,
            "Each cell comes from media/data/verdict-*.json written by "
            "judge/grade.sh --seed 20260814. Red-cell numbers are the "
            "gate's own measured detail, e.g. shell '5 of 46 responses "
            "wrong' -> '5/46 wrong'.",
            family=MONO, fontsize=7.6, color="#57606a", va="center")

    check_no_overlap(fig, texts, "loop.png cell labels")

    out = os.path.join(os.path.dirname(DATA), "loop.png")
    fig.savefig(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
