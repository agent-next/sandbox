#!/usr/bin/env python3
"""loop.png -- the self-test kill table plus the replayed agent loop.

Panel A: the agent-loop replay (a replay of the real grade JSONs, not a
         live agent trace): each column is one replayed iteration -- the
         seven mutants in the order a fixing agent would hit them
         (parameter-block/sanity mistakes first, then geometry, then the
         feed match), then the good artifact that passes everything.
Panel B: kill table -- every known-bad mutant with the gate that
         actually killed it and its measured value vs the gate limit,
         parsed out of that run's verdict JSON (never a metric where the
         mutant looks like the good one); plus the good row and the
         selftest kill rate from media/data/selftest.txt.

Every number is read from media/data/verdicts/*.json and
media/data/selftest.txt; the script exits non-zero if any source file
is missing, and if any placed text escapes its axes or overlaps.
"""
import json
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MEDIA = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(MEDIA, "data")
OUT = os.path.join(MEDIA, "loop.png")

C_BAD = "#D55E00"        # Okabe-Ito vermillion (failed iteration)
C_GOOD = "#0072B2"       # Okabe-Ito blue (pass)

# replay order = the order a fixing agent plausibly works through the
# design mistakes (make_data.sh grades in this order).
REPLAY = [
    ("bad_nan_er",          'er = float("nan")'),
    ("bad_substrate_er",    "er = 2.2 (out of range)"),
    ("bad_thick_substrate", "sub_h = 3.5 mm (out of range)"),
    ("bad_coarse_mesh",     "mesh_res = 2.4 mm (out of range)"),
    ("bad_patch_length",    "patch_L = 22 mm (resonance leaves band)"),
    ("bad_no_ground",       "ground plane deleted"),
    ("bad_feed_center",     "feed_inset = 12 mm (voltage node)"),
    ("good",                "all parameters fixed"),
]

GATE_LIMITS = {            # from judge/oracle.py ANTENNA_GATES
    "er": "[3.5, 5.0]",
    "sub_h": "[0.5, 2.5] mm",
    "mesh_res": "[0.4, 2.0] mm",
}


def need(p):
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run media/make_data.sh first")
    return p


def verdict(name):
    return json.load(open(need(os.path.join(DATA, "verdicts",
                                            name + ".json"))))


def first_failed(v):
    for g in v["gates"]:
        if not g["pass"]:
            return g
    return None


def g2_params(v):
    g = next(g for g in v["gates"] if g["gate"] == "G2_physical_sanity")
    return json.loads(g["detail"])


def num(pat, s):
    m = re.search(pat, s)
    if not m:
        raise SystemExit(f"could not parse {pat!r} from {s!r}")
    return m.group(1)


def kill_row(case):
    """(killer gate label, measured-vs-limit) from the verdict JSON."""
    v = verdict(case)
    g = first_failed(v)
    gate, d = g["gate"], g["detail"]
    if case == "bad_nan_er":
        miss = num(r"missing=\['(\w+)'\]", d)
        return ("G1 parameter block",
                f'er = float("nan") -- not a numeric literal '
                f'({miss} missing)')
    if gate == "G2_physical_sanity":
        p = g2_params(v)
        var = {"bad_substrate_er": "er", "bad_thick_substrate": "sub_h",
               "bad_coarse_mesh": "mesh_res"}[case]
        return (f"G2 {var} = {p[var]}",
                f"outside {GATE_LIMITS[var]}")
    if gate == "G5_resonance":
        f = num(r"f_res=([\d.]+) GHz", d)
        return (f"G5 f_res = {f} GHz",
                f"vs 2.45 GHz ±2 % (band 2.401–2.499 GHz)")
    if gate == "G4_S11_at_target":
        s = num(r"S11=([-\d.]+) dB", d)
        return (f"G4 S11 @ 2.45 GHz = {s} dB",
                "vs ≤ −10 dB (G6/G7 still pass: curve is real, the "
                "match is not)")
    raise SystemExit(f"unexpected killer gate for {case}: {gate}")


def check_layout(fig, items):
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    boxes = []
    for art, ax, tag in items:
        bb = art.get_window_extent(renderer=r)
        if ax is not None:
            ab = ax.get_window_extent(renderer=r)
            if bb.x0 < ab.x0 - 1 or bb.x1 > ab.x1 + 1 or \
                    bb.y0 < ab.y0 - 1 or bb.y1 > ab.y1 + 1:
                raise SystemExit(
                    f"text '{tag}' escapes its axes: "
                    f"text=({bb.x0:.0f},{bb.y0:.0f})-({bb.x1:.0f},{bb.y1:.0f}) "
                    f"axes=({ab.x0:.0f},{ab.y0:.0f})-({ab.x1:.0f},{ab.y1:.0f})")
        boxes.append((bb, tag))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i][0].overlaps(boxes[j][0]):
                raise SystemExit(
                    f"text overlap: {boxes[i][1]} vs {boxes[j][1]}")
    print(f"layout check: OK ({len(boxes)} texts, no overlaps)")


def main():
    st = open(need(os.path.join(DATA, "selftest.txt"))).read()
    m2 = re.search(r"selftest: good=(\d)/1, mutants_killed=(\d)/(\d)",
                   st)
    if not m2:
        raise SystemExit("selftest.txt has no summary line")
    good_n, killed_n, mutant_n = m2.groups()
    m = re.search(r"kill rate: (\d+)% \(required >= 90%\)", st)
    if not m:
        raise SystemExit("selftest.txt has no kill-rate line")
    kill_rate = m.group(1)

    vs = {c: verdict(c) for c, _ in REPLAY}

    fig = plt.figure(figsize=(15.5, 7.6), dpi=200)
    gs = fig.add_gridspec(
        2, 1, height_ratios=[0.75, 1.2], left=0.055, right=0.985,
        top=0.91, bottom=0.075, hspace=0.12)
    texts = []

    def reg(art, ax, tag):
        texts.append((art, ax, tag))
        return art

    # ---------------- panel A: replayed agent loop --------------------
    axA = fig.add_subplot(gs[0])
    axA.set_xlim(-0.6, len(REPLAY) - 0.4)
    axA.set_ylim(-1.15, 2.4)
    for i, (case, mutation) in enumerate(REPLAY):
        v = vs[case]
        ok = v["all_pass"]
        col = C_GOOD if ok else C_BAD
        axA.add_patch(plt.Rectangle((i - 0.42, 0.05), 0.84, 1.0,
                                    facecolor=col, alpha=0.16,
                                    edgecolor=col, lw=1.6))
        g = first_failed(v)
        label = "PASS" if ok else "FAIL"
        axA.text(i, 1.22, label, ha="center", fontsize=11,
                 fontweight="bold", color=col)
        axA.text(i, 0.55, f"iter {i+1}", ha="center", va="center",
                 fontsize=9, color="0.3")
        reg(axA.text(i, -0.02, case.replace("bad_", "").replace("_", " "),
                     ha="center", va="top", fontsize=8.4,
                     family="monospace"), axA, f"case-{case}")
        reg(axA.text(i, -0.52, mutation.replace(" (", "\n("),
                     ha="center", va="top", fontsize=7.6, color="0.35"),
            axA, f"mut-{case}")
    axA.annotate("", xy=(len(REPLAY) - 0.55, 1.88),
                 xytext=(-0.45, 1.88),
                 arrowprops=dict(arrowstyle="-|>", color="0.4", lw=1.6))
    reg(axA.text((len(REPLAY) - 1) / 2, 1.97,
                 "replay: one real grade.sh run per known-bad variant, then "
                 "the good design — recorded verdicts, not a live agent trace",
                 ha="center", va="bottom", fontsize=10.5), axA,
        "replay-title")
    axA.axis("off")

    # ---------------- panel B: kill table ------------------------------
    axB = fig.add_subplot(gs[1])
    rows = [c for c, _ in REPLAY if c != "good"]
    n = len(rows) + 1 + 1               # mutants + good + header
    axB.set_xlim(0, 1)
    axB.set_ylim(-0.9, n)
    axB.axis("off")

    x_name, x_gate, x_verdict = 0.015, 0.30, 0.845

    def cell(x, y, s, **kw):
        return axB.text(x, y, s, va="center", **kw)

    # header
    axB.add_patch(plt.Rectangle((0.005, n - 1), 0.99, 1,
                                facecolor="#e8ecef", edgecolor="none"))
    cell(x_name, n - 0.5, "mutant / artifact", fontsize=10.5,
         fontweight="bold")
    cell(x_gate, n - 0.5, "failing gate + measured value (from the "
         "verdict JSON)", fontsize=10.5, fontweight="bold")
    cell(x_verdict, n - 0.5, "verdict", fontsize=10.5,
         fontweight="bold")

    for r, case in enumerate(rows):
        y = n - 2 - r
        gate_label, meas = kill_row(case)
        axB.add_patch(plt.Rectangle((0.005, y), 0.99, 1,
                                    facecolor="#fdf3ee", edgecolor="none"))
        cell(x_name, y + 0.5, case.replace("bad_", "").replace("_", " "),
             fontsize=10, family="monospace")
        cell(x_gate, y + 0.5, f"{gate_label}   |   {meas}",
             fontsize=9.5, color="0.15")
        cell(x_verdict, y + 0.5, "killed", fontsize=10,
             fontweight="bold", color=C_BAD)

    # good row (measured values parsed from good.json)
    vg = vs["good"]
    g4 = next(g for g in vg["gates"] if g["gate"] == "G4_S11_at_target")
    g5 = next(g for g in vg["gates"] if g["gate"] == "G5_resonance")
    y_good = n - 2 - len(rows)
    axB.add_patch(plt.Rectangle((0.005, y_good), 0.99, 1,
                                facecolor="#eef5fa", edgecolor="none"))
    cell(x_name, y_good + 0.5, "good (final design)", fontsize=10,
         family="monospace")
    cell(x_gate, y_good + 0.5,
         f"G4 {g4['detail'].split(' (')[0]}  |  "
         f"G5 {g5['detail'].split(' (')[0]}  |  "
         f"G6 max|Δ| = {vg['raw_crosscheck_maxdiff_db']:.1f} dB  |  "
         f"G7 eeff Δ = {vg['oracle']['delta_pct']:.1f} %  |  "
         f"G8 shift = {vg['convergence']['f_res_shift_pct']:.1f} %",
         fontsize=9.5, color="0.15")
    cell(x_verdict, y_good + 0.5, "PASS", fontsize=10,
         fontweight="bold", color=C_GOOD)

    reg(axB.text(0.015, -0.55,
                 f"selftest (media/data/selftest.txt): good {good_n}/1, "
                 f"mutants killed {killed_n}/{mutant_n}, kill rate "
                 f"{kill_rate} % (required ≥ 90 %) — deterministic "
                 f"verdicts: yes", fontsize=10.5, fontweight="bold"),
        axB, "killrate")

    check_layout(fig, texts)
    fig.suptitle("rf-openems — the judge kills every bad design: "
                 "self-test kill table and loop replay",
                 fontsize=15, y=0.975)
    fig.savefig(OUT, dpi=200)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
