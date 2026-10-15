#!/usr/bin/env python3
"""loop.png -- the agent loop and the self-test, from real verdict JSONs.

Three panels, one file:

  * top: the fixing agent's loop REPLAYED on adapter_plate (labelled a
    replay, not a live trace): iteration = one graded artifact, bar =
    how many of the 10 gates failed, annotated with the failing gate's
    own measured value vs its rule (from that artifact's verdict JSON),
    until the 4th iteration passes everything.
  * middle: the mutant x gate matrix -- rows = the 3 known-good parts +
    the 8 single-edit mutants, columns = the judge's 10 gates.  Green =
    pass, vermillion = fail, and every failing cell prints the measured
    value against its limit, wrapped.  A bottom row states each gate's
    rule verbatim from the verdict JSONs.
  * bottom: the self-test kill-rate bar (known-good pass rate and
    known-bad kill rate) with the 90 % floor DEMO-STANDARD.md requires,
    plus the summary line selftest.sh actually printed.

Script-enforced layout check: every cell's text must stay inside its own
cell rectangle, and cadviz.check_no_overlap rejects any overlapping or
clipped text on the whole figure.
"""
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

import cadviz

MEDIA = cadviz.MEDIA
OUT = os.path.join(MEDIA, "loop.png")

# judge gate order = SPEC.md's table
GATES = ["tool_runs", "delivery_matches", "step_valid", "stl_valid", "bbox",
         "volume_analytic", "xor_volume", "features", "min_wall",
         "judge_intact"]
GATE_LAB = {g: f"{i + 1}\n{g}" for i, g in enumerate(GATES)}

# row order: the 3 good parts, then the 8 mutants grouped by part
MUTANT_ORDER = ["plate-hole-count", "plate-hole-diameter", "plate-hole-drift",
                "plate-flipped-facet", "bracket-missing-fillet",
                "bracket-fillet-radius", "bushing-scale-25_4",
                "bushing-non-watertight"]
ROWS = ["good_bushing", "good_adapter_plate", "good_bracket"] + MUTANT_ORDER

INK = "#0b0b0b"
MUTED = "#52514e"
PASS = cadviz.PASS
FAIL = cadviz.FAIL


# one short, faithful name per scripted edit; keys are verified against
# judge/mutants.py's MODEL_EDITS/STL_EDITS below, so a rename there fails
# this figure loudly rather than mislabelling a row.
EDIT_LABEL = {
    ("plate-hole-count", "N_BOLT_HOLES = 4"):
        "model.py: N_BOLT_HOLES = 4 -> 3",
    ("plate-hole-diameter", "BOLT_HOLE_D = 6.5"):
        "model.py: BOLT_HOLE_D = 6.5 -> 5.0",
    ("plate-hole-drift", "FIRST_ANGLE_DEG = 45.0"):
        "model.py: FIRST_ANGLE_45 -> 53 deg",
    ("bracket-missing-fillet",
     "bd.CenterArc((LEG_T + FILLET_R, LEG_T + FILLET_R), FILLET_R, -90, -90)"):
        "model.py: R5 fillet -> its chord",
    ("bracket-fillet-radius", "FILLET_R = 5.0"):
        "model.py: FILLET_R = 5.0 -> 2.0",
    ("bushing-scale-25_4", "SHAFT_D = 20.0"):
        "model.py: SHAFT_D = 20.0 -> 20.0 * 25.4",
    ("bushing-non-watertight", "drop_triangle"):
        "STL byte edit: drop one triangle",
    ("plate-flipped-facet", "flip_facet"):
        "STL byte edit: flip one facet",
}


def row_label(name):
    """Row label + the single scripted edit, keyed off judge/mutants.py
    itself (an edit renamed there fails here -- no stale labels)."""
    if name.startswith("good_"):
        return ("good / " + name[5:].replace("_", " "), None)
    sys.path.insert(0, cadviz.JUDGE)
    import mutants
    for m, part, old, _new in mutants.MODEL_EDITS:
        if m == name:
            key = (name, old)
            break
    else:
        for m, part, edit in mutants.STL_EDITS:
            if m == name:
                key = (name, edit)
                break
        else:
            raise SystemExit(f"unknown mutant row {name}")
    if key not in EDIT_LABEL:
        raise SystemExit(f"no EDIT_LABEL for {key} -- mutants.py changed")
    return (f"{name}  ({part.replace('_', ' ')})", EDIT_LABEL[key])


def _feature_cell(errs):
    """The features gate's errors, verbatim but with repeated centre-
    drift errors collapsed to a count (a mutant with 4 drifted holes
    otherwise overflows its matrix cell; the verdict JSON keeps every
    error verbatim)."""
    errs = list(errs or ["failed"])
    out, centres = [], {}
    for e in errs:
        if "centre (" in e and "not within" in e:
            key = e.split(":")[0]
            centres[key] = centres.get(key, 0) + 1
        else:
            out.append(e)
    for key in sorted(centres):
        out.append(f"{key}: {centres[key]} centres off-spec (>0.05 mm)")
    txt = "; ".join(out[:2])
    if len(out) > 2:
        txt += f"; +{len(out) - 2} more"
    return txt


def cell_text(gate, g):
    """Short text for one matrix cell: measured value vs limit when red."""
    m = g.get("measured") or {}
    if gate == "tool_runs":
        return "exit 0, wrote step+stl" if g["pass"] else \
            f"exit {m.get('exit')}, no files"
    if gate == "delivery_matches":
        if g["pass"]:
            return "sha256 delivered == fresh regen"
        bad = [k for k, d in m.items() if isinstance(d, dict)
               and not d.get("equal", True)]
        return "sha256 != regen: " + ", ".join(bad)
    if gate == "step_valid":
        return "BRepCheck valid, 1 solid" if g["pass"] else \
            f"valid={m.get('brepcheck_valid')} solids={m.get('solids')}"
    if gate == "stl_valid":
        if g["pass"]:
            return f"watertight, winding ok, {m.get('facets')} facets"
        why = []
        if not m.get("watertight", True):
            why.append("watertight: False")
        if not m.get("winding_consistent", True):
            why.append("winding: False")
        return ", ".join(why) + "  (rule: both True, 1 body)"
    if gate == "bbox":
        v = m["step_max_dev_mm"]
        return f"max dev {v:g} mm <= 0.05" if g["pass"] else \
            f"max dev {v:g} mm > 0.05 mm limit"
    if gate == "volume_analytic":
        v = m["rel_err"] * 100
        return f"rel err {v:.4g} % <= 0.5 %" if g["pass"] else \
            f"rel err {v:.3g} % > 0.5 % limit"
    if gate == "xor_volume":
        v = m["rel"] * 100
        return f"XOR {v:.4g} % of ref <= 1.0 %" if g["pass"] else \
            f"XOR {v:.3g} % of ref > 1.0 % limit"
    if gate == "features":
        if g["pass"]:
            return "counts, radii, centres, spacing all as spec"
        return _feature_cell(m.get("errors"))
    if gate == "min_wall":
        if m.get("applicable") is False:
            return "not graded (spec min_wall_mm = null)"
        v, want = m["min_wall_mm"], m["spec_min_wall_mm"]
        return f"{v:g} mm >= {want:g} - 0.1" if g["pass"] else \
            f"{v:g} mm < {want:g} - 0.1 floor"
    if gate == "judge_intact":
        return f"{m.get('files', '?')} files sha256 unchanged" if g["pass"] \
            else f"changed: {m.get('changed')}"
    raise KeyError(gate)


def replay_annotation(v):
    """The failing gate's own measured value + rule, for one iteration."""
    failed = [k for k in GATES if not v["gates"][k]["pass"]]
    if not failed:
        return "all 10 gates PASS -- grade.sh exit 0"
    g = v["gates"][failed[0]]
    m = g["measured"] or {}
    if failed[0] == "features":
        txt = f"{failed[0]}: {_feature_cell(m.get('errors'))}"
    elif failed[0] == "volume_analytic":
        txt = (f"{failed[0]}: rel err {m['rel_err'] * 100:.3g} % "
               f"> 0.5 % limit")
    elif failed[0] == "bbox":
        txt = f"{failed[0]}: max dev {m['step_max_dev_mm']:g} mm > 0.05 mm"
    else:
        txt = f"{failed[0]}: {cell_text(failed[0], g)}"
    return txt


def selftest_summary():
    """The summary line selftest.sh actually printed (provenance)."""
    path = os.path.join(cadviz.DATA, "selftest.txt")
    cadviz.need(path)
    for line in open(path):
        if "summary:" in line:
            return line.strip()
    raise SystemExit(f"no summary line in {path}")


def parse_selftest(summary):
    m = re.search(r"good (\d+)/(\d+) pass.*killed (\d+)/(\d+).*kill rate "
                  r"(\d+)%", summary)
    if not m:
        raise SystemExit(f"cannot parse selftest summary: {summary!r}")
    gp, gt, kp, kt, kr = map(int, m.groups())
    return gp / gt, kp / kt, kr


def main():
    verdicts = {name: cadviz.load_verdict(name + ".json") for name in ROWS}
    for name, v in verdicts.items():
        if name.startswith("good_") and not v["pass"]:
            raise SystemExit(f"{name} graded FAIL -- demo broken")
        if not name.startswith("good_") and v["pass"]:
            raise SystemExit(f"mutant {name} graded PASS -- judge fooled")

    fig = plt.figure(figsize=(16.0, 15.2), dpi=200)
    gs = fig.add_gridspec(
        3, 1, height_ratios=[2.5, 8.2, 1.9],
        left=0.055, right=0.988, top=0.946, bottom=0.022, hspace=0.30)

    # ---------------------------------------------------------------- top
    axR = fig.add_subplot(gs[0])
    replay = [l.strip() for l in open(
        cadviz.need(os.path.join(cadviz.DATA, "replay.txt")))]
    iter_lab = {"plate-hole-count": "1: 3 bolt holes\n(wrong count)",
                "plate-hole-diameter": "2: Ø5.0 holes\n(wrong diameter)",
                "plate-hole-drift": "3: first hole at 53°\n(drifted)",
                "good_adapter_plate": "4: good part"}
    nf = [sum(1 for g in verdicts[r]["gates"].values() if not g["pass"])
          for r in replay]
    x = np.arange(len(replay))
    cols = [FAIL if n else PASS for n in nf]
    axR.bar(x, nf, width=0.58, color=cols, alpha=0.92)
    for xi, n in zip(x, nf):
        axR.text(xi, n + 0.07, f"{n} gate{'s' if n != 1 else ''} failed"
                 if n else "0 failed = PASS", ha="center", va="bottom",
                 fontsize=8.5, color=INK)
    axR.set_xticks(x)
    axR.set_xticklabels([iter_lab[r] for r in replay], fontsize=8.5)
    axR.set_ylabel("gates failed (of 10)", fontsize=9)
    axR.set_ylim(0, max(nf) + 0.9)
    axR.set_yticks(range(0, max(nf) + 1))
    for s in ("top", "right"):
        axR.spines[s].set_visible(False)
    axR.tick_params(length=2)
    for xi, r in zip(x, replay):
        axR.annotate(replay_annotation(verdicts[r]), (xi, 0), xytext=(xi, -0.30),
                     textcoords=("data", "axes fraction"), ha="center",
                     va="top", fontsize=7.6, color=MUTED, linespacing=1.35,
                     annotation_clip=False,
                     bbox=dict(boxstyle="round,pad=0.32", fc="#f4f4f2",
                               ec="#d8d8d4", lw=0.6))
    axR.set_title("the fixing agent's loop, REPLAYED (each step graded for "
                  "real; not a live trace): judge error per iteration until "
                  "pass -- adapter_plate", fontsize=11.5, fontweight="bold",
                  color=INK, pad=8)

    # ------------------------------------------------------------- matrix
    axM = fig.add_subplot(gs[1])
    axM.set_xlim(0, 11)
    nr = len(ROWS)
    axM.set_ylim(-2.3, nr + 1.6)
    axM.set_xticks([])
    axM.set_yticks([])
    for s in axM.spines.values():
        s.set_visible(False)

    col_x0, col_w = 1.45, (11.0 - 1.45) / 10.0
    row_h = 1.0
    cell_texts = []          # (artist, rect in display coords)

    for j, gate in enumerate(GATES):
        x0 = col_x0 + j * col_w
        axM.text(x0 + col_w / 2, nr + 1.28, GATE_LAB[gate], ha="center",
                 va="center", fontsize=7.8, fontweight="bold", color=INK,
                 linespacing=1.25)
    for i, name in enumerate(ROWS):
        y0 = nr - 1 - i
        v = verdicts[name]
        main_lab, edit = row_label(name)
        axM.text(0.04, y0 + row_h * 0.80, main_lab, ha="left", va="center",
                 fontsize=8.2, fontweight="bold",
                 color=INK if name.startswith("good_") else FAIL)
        if edit:
            axM.text(0.04, y0 + row_h * 0.50,
                     cadviz.wrap(edit, 42), ha="left", va="center",
                     fontsize=6.8, color=MUTED, linespacing=1.3)
        verdict_all = v["pass"]
        axM.text(0.04, y0 + row_h * 0.20,
                 ("grade.sh exit 0" if verdict_all else "grade.sh exit 1"),
                 ha="left", va="center", fontsize=6.6,
                 color=PASS if verdict_all else FAIL)
        for j, gate in enumerate(GATES):
            g = v["gates"][gate]
            x0 = col_x0 + j * col_w
            ok = g["pass"] is True
            axM.add_patch(Rectangle(
                (x0 + 0.015, y0 + 0.02), col_w - 0.03, row_h - 0.04,
                facecolor=PASS if ok else FAIL,
                alpha=0.92 if ok else 0.30, lw=0))
            t = axM.text(x0 + col_w / 2, y0 + row_h / 2,
                         cadviz.wrap(cell_text(gate, g), 23), ha="center",
                         va="center", fontsize=6.4,
                         color=INK if not ok else "#ffffff", linespacing=1.3)
            cell_texts.append((t, (x0, y0, col_w, row_h)))
        if i < nr - 1:
            axM.axhline(y0, color="#ffffff", lw=1.2)

    # rules row: each gate's rule, verbatim from the verdict JSON
    rule_src = verdicts["good_bushing"]
    for j, gate in enumerate(GATES):
        x0 = col_x0 + j * col_w
        rule = rule_src["gates"][gate]["rule"]
        t = axM.text(x0 + col_w / 2, -1.15, cadviz.wrap("rule: " + rule, 24),
                     ha="center", va="center", fontsize=6.3, color=MUTED,
                     linespacing=1.3)
        cell_texts.append((t, (x0, -2.05, col_w, 1.7)))
    axM.text(0.04, -1.15, "gate rules\n(from the\nverdict JSON)", ha="left",
             va="center", fontsize=6.8, color=MUTED, linespacing=1.3)

    # legend, outside the data
    lx = col_x0 + 0.02
    axM.add_patch(Rectangle((lx, nr + 0.52), 0.26, 0.30, facecolor=PASS,
                            alpha=0.92, lw=0))
    axM.text(lx + 0.34, nr + 0.67, "gate PASS", fontsize=7.6, va="center",
             color=INK)
    axM.add_patch(Rectangle((lx + 1.75, nr + 0.52), 0.26, 0.30,
                            facecolor=FAIL, alpha=0.30, lw=0))
    axM.text(lx + 2.09, nr + 0.67,
             "gate FAIL -- cell text = measured value vs limit "
             "(from that artifact's verdict JSON)", fontsize=7.6,
             va="center", color=INK)
    axM.set_title("mutant x gate matrix: 3 good parts + 8 single-edit "
                  "mutants against the judge's 10 gates "
                  "(grade.sh --seed 42 --json each)", fontsize=11.5,
                  fontweight="bold", color=INK, pad=8)

    # ---------------------------------------------------------- kill rate
    summary = selftest_summary()
    gp, kp, kr = parse_selftest(summary)
    axK = fig.add_subplot(gs[2])
    vals = [gp * 100, kp * 100]
    y = [1, 0]
    axK.barh(y, vals, height=0.52, color=[PASS, FAIL], alpha=0.92)
    axK.axvline(90, color=FAIL, lw=1.6, ls=(0, (5, 3)))
    axK.text(90, 1.20, " 90% kill-rate floor (DEMO-STANDARD.md)", fontsize=8,
             color=FAIL, ha="left", va="center")
    axK.text(gp * 100 + 1.2, 1, f"{gp * 100:.0f}%  (3/3 parts)", va="center",
             fontsize=8.5, color=INK)
    axK.text(kp * 100 + 1.2, 0, f"{kp * 100:.0f}%  (8/8 mutants killed)",
             va="center", fontsize=8.5, color=INK)
    axK.set_yticks(y)
    axK.set_yticklabels(["good parts", "mutants"], fontsize=8.5)
    axK.set_xlim(0, 132)
    axK.set_xticks([])
    for s in ("top", "right"):
        axK.spines[s].set_visible(False)
    axK.tick_params(length=2, labelsize=8)
    axK.set_title("self-test kill rate -- " + summary, fontsize=10,
                  fontweight="bold", color=INK, pad=22)

    fig.suptitle("the judge an agent cannot fool: every single-edit mutant "
                 "dies on at least one gate, the good parts pass all ten",
                 fontsize=14, fontweight="bold", y=0.983)
    fig.text(0.012, 0.004,
             "source: media/data/verdicts/*.json (judge/grade.sh --seed 42 "
             "--json, run by media/collect_verdicts.sh) and "
             "media/data/selftest.txt (judge/selftest.sh).  Mutant edits are "
             "read from judge/mutants.py.  seed 42 everywhere.",
             fontsize=7.2, color=MUTED)

    # script-enforced layout checks
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    for t, (x0, y0, w, h) in cell_texts:
        bb = t.get_window_extent(renderer=r)
        (dx0, dy0) = axM.transData.transform((x0, y0))
        (dx1, dy1) = axM.transData.transform((x0 + w, y0 + h))
        if bb.x0 < dx0 - 0.5 or bb.x1 > dx1 + 0.5 or bb.y0 < dy0 - 0.5 \
                or bb.y1 > dy1 + 0.5:
            raise SystemExit(
                f"[layout] loop.png: cell text escapes its cell: "
                f"{t.get_text()[:40]!r} bbox={bb} cell=({dx0},{dy0})-"
                f"({dx1},{dy1})")
    print(f"[layout] loop.png: {len(cell_texts)} matrix cells checked -- "
          "every text inside its cell")
    cadviz.check_no_overlap(fig, "loop.png")
    fig.savefig(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
