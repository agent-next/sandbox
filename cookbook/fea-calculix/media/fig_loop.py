#!/usr/bin/env python3
"""loop.png -- agent-loop replay + mutant x gate matrix.

Rows: the known-good artifact and the 9 scripted mutants, in the order a
fixing agent would plausibly meet them.  Columns: the three judge gates.
Every cell is drawn from that artifact's real verdict JSON in
media/data/verdicts/ (grade.sh --seed 42 --json): green cells carry the
measured margin, red cells the measured value vs the limit.

Top strip: a *replay* of the agent loop (bad -> partly fixed -> good),
each point the number of gates passed (0..3) in that grade's verdict
JSON -- replayed grades, not a live agent trace.

The script raises if any text escapes its axes/cell or overlaps another.
"""
import json
import os
import re
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

MEDIA = os.path.dirname(os.path.abspath(__file__))
VERDICTS = os.path.join(MEDIA, "data", "verdicts")
OUT = os.path.join(MEDIA, "loop.png")

GATES = ["verification", "convergence", "spec_limits"]
GATE_RULES = {
    "verification": "ref beam vs Euler-Bernoulli <= 3%",
    "convergence": "mesh s vs s/2 agree <= 2%",
    "spec_limits": "sigma <= 166.7 MPa, delta <= L/100, EB sanity band",
}

# row order = the replay sequence a fixing agent would plausibly hit
ROWS = [
    ("good",             "good -- final artifact", ""),
    ("no-stress-output", "no-stress-output", "deck drops *EL FILE S"),
    ("coarse-mesh",      "coarse-mesh", "mesh_size = min(b,h)"),
    ("load-wrong-dof",   "load-wrong-dof", "load in +Y, not -Z"),
    ("load-on-ntip",     "load-on-ntip", "-250 N on every tip node"),
    ("propped-tip",      "propped-tip", "tip clamped as well"),
    ("units-in-metres",  "units-in-metres", "dimensions in m, not mm"),
    ("overload-10x",     "overload-10x", "-2500 N per corner node"),
    ("undersized",       "undersized", "b=8, h=40 mm"),
    ("unconverged",      "unconverged", "mesh_size=15: s vs s/2 disagree"),
]

# replay storyline: same artifact list order the agent would submit
REPLAY = ["no-stress-output", "undersized", "unconverged", "good"]


def load(name):
    p = os.path.join(VERDICTS, name + ".json")
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run the judge collection first")
    return json.load(open(p))


def cell_text(gate, g):
    """Short measured-vs-limit text for one cell, parsed from the verdict
    detail string.  Returns (ok, text)."""
    ok = g["pass"]
    det = g["detail"]
    if "invalid design" in det:
        if "mesh_size too large" in det:
            return ok, "invalid design:\nmesh_size too\nlarge"
        return ok, "invalid\ndesign:\n" + re.sub(r"^invalid design: ",
                                                 "", det)
    if gate == "verification":
        m = re.search(r"deflection [\d.eE+-]+ vs [\d.eE+-]+ mm "
                      r"\(([+-][\d.]+)%\), stress [\d.eE+-]+ vs [\d.eE+-]+ "
                      r"MPa \(([+-][\d.]+)%\)", det)
        if m:
            return ok, f"d {m.group(1)}%\ns {m.group(2)}%\ntol 3%"
        if "reference run failed" in det:
            return ok, "ref beam run\nfailed; gates\ncannot run"
        m = re.search(r"run failed: (.*)", det)
        if m:
            return ok, "run failed:\n" + m.group(1)
        return ok, det
    if gate == "convergence":
        m = re.search(r"deflection change ([\d.eE+-]+)%, stress change "
                      r"([\d.eE+-]+)%", det)
        if m:
            return ok, f"dd {m.group(1)}%\nds {m.group(2)}%\ntol 2%"
        if "reference run failed" in det:
            return ok, "ref beam run\nfailed; gates\ncannot run"
        m = re.search(r"run failed: (.*)", det)
        if m:
            return ok, "run failed:\n" + m.group(1)
        return ok, det
    if "reference run failed" in det:
        return ok, "ref beam run\nfailed; gates\ncannot run"
    # spec_limits: failing clauses are those without "<="
    clauses = [c.strip() for c in det.split(";")]
    bad = [c for c in clauses
           if re.search(r"> (allowable|limit)|outside|invalid|failed", c)]
    show = bad if bad else clauses
    short = []
    for c in show:
        c = re.sub(r"deflection/EB ratio ([\d.eE+-]+) outside "
                   r"\[([\d., ]+)\].*", r"d/EB \1 out [\2]", c)
        c = re.sub(r"stress/EB ratio ([\d.eE+-]+) outside "
                   r"\[([\d., ]+)\].*", r"s/EB \1 out [\2]", c)
        c = re.sub(r"deflection (-?[\d.eE+]+) > limit ([\d.]+) mm",
                   r"d \1 > \2 mm", c)
        c = re.sub(r"deflection (-?[\d.eE+]+) <= limit ([\d.]+) mm",
                   r"d \1 <= \2 mm", c)
        c = re.sub(r"sigma ([\d.eE+]+) > allowable ([\d.]+) MPa",
                   r"s \1 > \2 MPa", c)
        c = re.sub(r"sigma ([\d.eE+]+) <= allowable ([\d.]+) MPa",
                   r"s \1 <= \2 MPa", c)
        short.append(c)
    return ok, "\n".join(short)


def wrap(t, width):
    out = []
    for ln in t.split("\n"):
        out += textwrap.wrap(ln, width) or [""]
    return "\n".join(out)


def main():
    rows = [(name, label, sub, load(name)) for name, label, sub in ROWS]
    n_rows, n_cols = len(rows), len(GATES)

    fig = plt.figure(figsize=(13.5, 8.4), dpi=200)
    axT = fig.add_axes([0.07, 0.875, 0.88, 0.085])   # replay timeline
    axM = fig.add_axes([0.05, 0.03, 0.90, 0.72])     # matrix
    axM.set_xlim(0, n_cols + 2.35)
    axM.set_ylim(0, n_rows + 1.15)
    axM.axis("off")

    # ---------------- matrix ----------------
    hdr_y = n_rows  # header row baseline
    texts = []   # (artist, cell rect in data coords, tag)
    loose = []   # (artist, ax|None, tag): inside-axes + pairwise checks
    for j, g in enumerate(GATES):
        x = 2.35 + j
        axM.add_patch(Rectangle((x, hdr_y), 1, 1.15, fc="#dce6f2",
                                ec="0.5", lw=0.6))
        loose.append((axM.text(x + 0.5, hdr_y + 0.86, g, ha="center",
                               va="center", fontsize=9,
                               fontweight="bold"),
                      axM, f"header {g}"))
        loose.append((axM.text(x + 0.5, hdr_y + 0.34,
                               wrap(GATE_RULES[g], 26), ha="center",
                               va="center", fontsize=6.3, color="0.25"),
                      axM, f"header rule {g}"))
    for i, (name, label, sub, v) in enumerate(rows):
        y = n_rows - 1 - i
        is_good = name == "good"
        loose.append((axM.text(2.28, y + 0.62, label, ha="right",
                             va="center", fontsize=8.2,
                             fontweight="bold" if is_good else "normal",
                             color="#1a7a2f" if is_good else "black"),
                      axM, f"row {name}"))
        loose.append((axM.text(2.28, y + 0.26, sub, ha="right",
                               va="center", fontsize=6.4, color="0.4"),
                      axM, f"row sub {name}"))
        for j, g in enumerate(GATES):
            x = 2.35 + j
            ok, raw = cell_text(g, v["gates"][g])
            fc = "#d9f2dd" if ok else "#f6d5d5"
            ec = "#1a7a2f" if ok else "#b71c1c"
            axM.add_patch(Rectangle((x, y), 1, 1, fc=fc, ec=ec, lw=0.7))
            status = "PASS" if ok else "FAIL"
            lines = wrap(raw, 30).split("\n")
            if len(lines) > 5:
                lines = lines[:4] + ["..."]
            n_tot = len(lines) + 1      # + status line
            fs = 6.0 if n_tot <= 4 else (5.4 if n_tot <= 5 else 4.8)
            t = axM.text(x + 0.5, y + 0.47,
                         status + "\n" + "\n".join(lines),
                         ha="center", va="center", fontsize=fs,
                         color="#14406b" if ok else "#8c1414",
                         linespacing=1.12)
            texts.append((t, (x, y, 1, 1), f"{name}/{g}"))

    # row highlight for the good artifact
    axM.add_patch(Rectangle((0, n_rows - 1), n_cols + 2.35, 1,
                            fc="none", ec="#1a7a2f", lw=1.4,
                            linestyle=(0, (6, 3))))
    axM.set_xlim(0, n_cols + 2.4)
    axM.set_ylim(0, n_rows + 1.2)

    axM.set_title(
        "self-test matrix: every cell is a gate result from a real "
        "grade.sh --seed 42 verdict JSON\n"
        "known-good passes; 9/9 mutants killed (kill rate 100%, "
        "selftest.sh exit 0)", fontsize=10, loc="left", pad=10)

    # ---------------- replay timeline ----------------
    xs = list(range(len(REPLAY)))
    passed = [sum(1 for g in GATES if load(n)["gates"][g]["pass"])
              for n in REPLAY]
    axT.set_xlim(-0.4, len(REPLAY) - 0.6)
    axT.set_ylim(-0.6, 3.6)
    axT.axhline(len(GATES), color="#1a7a2f", lw=0.9, ls=":", alpha=0.7,
                zorder=1)
    axT.plot(xs, passed, "-", color="0.6", lw=1.2, zorder=2)
    for x, np_ in zip(xs, passed):
        axT.plot([x], [np_], "o", ms=9, zorder=3,
                 color="#1a7a2f" if np_ == len(GATES) else "#b71c1c")
    axT.set_xticks(xs)
    axT.set_xticklabels(
        [f"iter {i + 1}\n{n}" for i, n in enumerate(REPLAY)],
        fontsize=7.5)
    axT.set_yticks([0, 1, 2, 3])
    axT.set_yticklabels(["0", "1", "2", "3"], fontsize=7)
    axT.set_ylabel("gates passed\n(of 3)", fontsize=7, rotation=0,
                   labelpad=6, ha="right", va="center")
    axT.set_title("agent-loop replay (graded in sequence, bad -> partly "
                  "fixed -> good; a replay of real grade JSONs, not a "
                  "live agent trace)", fontsize=9, loc="left", pad=2)
    axT.tick_params(axis="x", pad=2)
    for s in ("top", "right"):
        axT.spines[s].set_visible(False)

    # ---------------- enforced no-overlap check ----------------
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    inv = axM.transData.inverted()
    bboxes = []
    for t, (cx, cy, cw, ch), tag in texts:
        bb = t.get_window_extent(renderer=r)
        x0, y0 = inv.transform((bb.x0, bb.y0))
        x1, y1 = inv.transform((bb.x1, bb.y1))
        if x0 < cx + 0.02 or x1 > cx + cw - 0.02 or \
                y0 < cy + 0.03 or y1 > cy + ch - 0.03:
            raise SystemExit(
                f"cell text overflows in {tag}: "
                f"text=({x0:.2f},{y0:.2f})-({x1:.2f},{y1:.2f}) "
                f"cell=({cx:.2f},{cy:.2f})+{cw}x{ch}")
        bboxes.append((bb, tag))
    for t, ax, tag in loose:
        bb = t.get_window_extent(renderer=r)
        if ax is not None:
            ab = ax.get_window_extent(renderer=r)
            if bb.x0 < ab.x0 - 1 or bb.x1 > ab.x1 + 1 or \
                    bb.y0 < ab.y0 - 1 or bb.y1 > ab.y1 + 1:
                raise SystemExit(f"text '{tag}' escapes its axes")
        bboxes.append((bb, tag))
    # replay strip: iteration tick labels and the title are pairwise-only
    for i, tl in enumerate(axT.get_xticklabels()):
        bboxes.append((tl.get_window_extent(renderer=r), f"iter label {i}"))
    bboxes.append((axT.title.get_window_extent(renderer=r), "replay title"))
    bboxes.append((axM.title.get_window_extent(renderer=r), "matrix title"))
    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            if bboxes[i][0].overlaps(bboxes[j][0]):
                raise SystemExit(
                    f"text overlap: {bboxes[i][1]} vs {bboxes[j][1]}")
    print("no-overlap check: OK (%d texts inside their cells/axes, "
          "no pairwise overlaps)" % len(bboxes))

    fig.savefig(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
