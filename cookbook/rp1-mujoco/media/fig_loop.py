#!/usr/bin/env python3
"""loop.png -- the agent-loop replay and the mutant x gate kill matrix.

Top strip: a REPLAY of the agent loop (bad -> partly fixed -> good; four
real graded artifacts in the order a fixing agent would submit them):

    zero_gains   (all gains zeroed)             0 of 4 gates   FAIL
    no_balance   (ankle balance law deleted)    0 of 4 gates   FAIL
    weak_balance (balance gains /1.5)           1 of 4 gates   FAIL
    good         (examples/good/controller.py)  4 of 4 gates   PASS

Every point counts the artifact-dependent gates (stand, push, limits,
integrity) that pass in that artifact's real verdict JSON in
media/data/verdicts/ (grade.sh --json); the four model gates and the
gravity-statics oracle do not depend on the artifact and pass for all.

Bottom: the self-test matrix -- known-good + the 8 mutants x all 10 of the
judge's gates (SPEC.md gate list order); each red cell shows the measured
value vs the limit from that mutant's real verdict JSON (its failed
gate's own metrics).  Data are a replay of real grade JSONs, not a live
agent trace.

The script raises if any source verdict is missing, a mutant is not
killed, or any text escapes its cell/axes or overlaps another.
"""
import json
import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

MEDIA = os.path.dirname(os.path.abspath(__file__))
VERDICTS = os.path.join(MEDIA, "data", "verdicts")
OUT = os.path.join(MEDIA, "loop.png")

GREEN = "#1a7a2f"
RED = "#b71c1c"
INK = "#0b0b0b"

# all 10 judge gates in SPEC.md gate-list order
GATES = ["model_loads", "mass_match", "joint_match", "effort_match",
         "gravity_statics", "stand", "push", "limits", "effort",
         "integrity"]
GATE_RULES = {
    "model_loads": "compiles, nq31 nv30 nu24",
    "mass_match": "MJCF vs URDF <= 1%",
    "joint_match": "ranges <= 1e-4 rad",
    "effort_match": "ctrlrange vs effort <= 1%",
    "gravity_statics": "fz = m*g within 2%",
    "stand": "z >= 0.9 z0, |tilt| <= 10 deg, feet only",
    "push": "stand ok & <= 5 deg by t = 7 s",
    "limits": "qpos / ctrl / force in range",
    "effort": "info only, never gated",
    "integrity": "checksums, audit, no tamper",
}
# artifact-dependent gates (the replay counts these)
PHYS_GATES = ("stand", "push", "limits", "integrity")

# row order: good first, then the replay's bad chain, then the rest of the
# kill set; (name, label, note)
ROWS = [
    ("good",             "good (final artifact)", "examples/good"),
    ("zero_gains",       "zero_gains",    "all KP/KD * 0"),
    ("no_balance",       "no_balance",    "balance law deleted"),
    ("weak_balance",     "weak_balance",  "balance gains /1.5"),
    ("sign_flip_knee",   "sign_flip_knee", "left knee KP negated"),
    ("wrong_joint_order", "wrong_joint_order", "actuator order reversed"),
    ("gains_100x",       "gains_100x",    "all gains * 100"),
    ("clamp_1pct",       "clamp_1pct",    "u clipped to 1% of limit"),
    ("cancels_push",     "cancels_push",  "zeroes the live push"),
    ("zero_torque",      "zero_torque",   "u = 0 (oracle must fall)"),
]
REPLAY = ["zero_gains", "no_balance", "weak_balance", "good"]


def load(name):
    p = os.path.join(VERDICTS, name + ".json")
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run media/collect_data.sh first")
    return json.load(open(p))


def cell(gate, d):
    """(kind, short measured-vs-limit text) for one gate cell;
    kind in {pass, fail, info}."""
    if d["verdict"] == "info":
        return "info", f"peak {d.get('peak_tau_nm', 0):.1f} N m"
    ok = d["pass"]
    if gate == "model_loads":
        return ok, f"nq {d['nq']} nv {d['nv']}\nnu {d['nu']}"
    if gate == "mass_match":
        return ok, f"dev {100 * d['worst_link_rel']:.2f}%\n<= 1%"
    if gate == "joint_match":
        return ok, (f"dev {d['worst_range_delta_rad']:.0f}\n<= 1e-4 rad"
                    if d["worst_range_delta_rad"] >= 1e-5 else
                    f"dev 0\n<= 1e-4 rad")
    if gate == "effort_match":
        return ok, f"dev {100 * d['worst_rel']:.2f}%\n<= 1%"
    if gate == "gravity_statics":
        return ok, f"fz/mg {d['ratio']:.3f}\ntol 2%"
    if gate == "stand":
        if "artifact_error" in d:
            return ok, "artifact\ntampered"
        return ok, (f"tilt {d['max_tilt_deg']:.1f}\nvs 10 deg\n"
                    f"z {d['zmin_m']:.3f} vs {d['z_floor_m']:.3f} m")
    if gate == "push":
        if "artifact_error" in d:
            return ok, "artifact\ntampered"
        return ok, (f"tilt >= t7\n{d['max_tilt_after_recovery_deg']:.1f} "
                    f"vs 5 deg")
    if gate == "limits":
        if "artifact_error" in d:
            return ok, "artifact\ntampered"
        q = d["worst_qpos_over_range_rad"]
        c = d["worst_ctrl_over_limit_nm"]
        f = d["worst_force_over_limit_nm"]
        if not ok:
            return ok, f"q over\n+{q * 1000:.1f} mrad\n(tol 1 mrad)"
        return ok, f"q/c/f\n{q:g}/{c:g}/{f:g}"
    if gate == "integrity":
        if not ok:
            viol = d.get("artifact_violations") or []
            why = "state tamper" if not viol else "audit violation"
            return ok, why.replace(" ", "\n")
        return ok, "clean"
    return ok, ""


def wrap(t, width):
    out = []
    for ln in t.split("\n"):
        out += textwrap.wrap(ln, width) or [""]
    return "\n".join(out)


def main():
    rows = [(n, lab, sub, load(n)) for n, lab, sub in ROWS]
    for n, _l, _s, v in rows[1:]:
        assert not v["all_pass"], f"mutant {n} unexpectedly passed"
    assert rows[0][3]["all_pass"]
    n_rows, n_cols = len(rows), len(GATES)

    fig = plt.figure(figsize=(14.4, 8.9), dpi=200, facecolor="#fcfcfb")
    axT = fig.add_axes([0.095, 0.885, 0.88, 0.075])
    axM = fig.add_axes([0.028, 0.035, 0.965, 0.70])
    axM.set_xlim(0, n_cols + 2.42)
    axM.set_ylim(0, n_rows + 1.3)
    axM.axis("off")

    texts, loose = [], []
    hdr_y = n_rows
    for j, gname in enumerate(GATES):
        x = 2.42 + j
        axM.add_patch(Rectangle((x, hdr_y), 1, 1.3, fc="#dce6f2",
                                ec="0.5", lw=0.6))
        loose.append((axM.text(x + 0.5, hdr_y + 1.00, gname, ha="center",
                               va="center", fontsize=7.6, fontweight="bold"),
                      f"header {gname}"))
        loose.append((axM.text(x + 0.5, hdr_y + 0.40,
                               wrap(GATE_RULES[gname], 20), ha="center",
                               va="center", fontsize=5.6, color="0.25"),
                      f"rule {gname}"))
    for i, (name, label, sub, v) in enumerate(rows):
        y = n_rows - 1 - i
        is_good = name == "good"
        loose.append((axM.text(2.36, y + 0.63, label, ha="right",
                               va="center", fontsize=7.6,
                               fontweight="bold" if is_good else "normal",
                               color=GREEN if is_good else INK),
                      f"row {name}"))
        loose.append((axM.text(2.36, y + 0.27, sub, ha="right", va="center",
                               fontsize=5.9, color="0.4"), f"row sub {name}"))
        for j, gname in enumerate(GATES):
            x = 2.42 + j
            kind, raw = cell(gname, v["gates"][gname])
            if kind == "info":
                fc, ec, status, col = "#e8edf4", "#4a4a48", "INFO", "#333"
            elif kind:
                fc, ec, status, col = "#d9f2dd", GREEN, "PASS", "#1c4d2a"
            else:
                fc, ec, status, col = "#f6d5d5", RED, "FAIL", "#8c1414"
            axM.add_patch(Rectangle((x, y), 1, 1, fc=fc, ec=ec, lw=0.7))
            t = axM.text(x + 0.5, y + 0.5,
                         status + "\n" + wrap(raw, 15), ha="center",
                         va="center", fontsize=5.6, color=col,
                         linespacing=1.1)
            texts.append((t, (x, y, 1, 1), f"{name}/{gname}"))

    axM.add_patch(Rectangle((0.02, n_rows - 1), n_cols + 2.40, 1, fc="none",
                            ec=GREEN, lw=1.4, linestyle=(0, (6, 3))))
    axM.set_xlim(0, n_cols + 2.42)
    axM.set_ylim(0, n_rows + 1.35)
    axM.set_title(
        "self-test kill matrix -- every cell is a gate result from a real "
        "grade.sh --seed 20261014 verdict JSON (media/data/verdicts/); "
        "known-good + 8 mutants x all 10 judge gates\n"
        "green pass / red fail / blue info (effort is reported, never "
        "gated); red cells carry the measured value vs the limit; "
        "self-test: 8/8 killed, physics kills 8/8 (media/data/selftest.txt)",
        fontsize=8.6, loc="left", pad=6, color=INK)

    # ---- replay timeline ---------------------------------------------------
    xs = list(range(len(REPLAY)))
    passed = []
    for n in REPLAY:
        v = load(n)
        passed.append(sum(1 for g in PHYS_GATES
                          if v["gates"][g]["pass"]))
    fails = []
    for n in REPLAY:
        v = load(n)
        failed = [g for g in PHYS_GATES if not v["gates"][g]["pass"]]
        fails.append(("all pass" if not failed else
                      "fails " + "+".join(g[:6] for g in failed)))
    axT.set_xlim(-0.4, len(REPLAY) - 0.6)
    axT.set_ylim(-0.6, 4.6)
    axT.axhline(len(PHYS_GATES), color=GREEN, lw=1.0, ls=":", alpha=0.8,
                zorder=1)
    axT.plot(xs, passed, "-", color="0.55", lw=1.2, zorder=2)
    for x, np_ in zip(xs, passed):
        col = GREEN if np_ == len(PHYS_GATES) else RED
        axT.plot([x], [np_], "o", ms=9, zorder=3, color=col)
    axT.set_xticks(xs)
    axT.set_xticklabels(
        [f"iter {i + 1}: {n}\n{fails[i]}" for i, n in enumerate(REPLAY)],
        fontsize=7.0)
    axT.set_yticks([0, 1, 2, 3, 4])
    axT.set_yticklabels(["0", "1", "2", "3", "4"], fontsize=7)
    axT.set_ylabel("gates passed\n(of 4)", fontsize=7, rotation=0,
                   labelpad=6, ha="right", va="center")
    axT.set_title(
        "agent-loop replay (real grade.sh verdicts, in the order a fixing "
        "agent would submit: bad -> partly fixed -> good)\n"
        "REPLAYED grades, not a live agent trace -- same seed, same judge; "
        "gates counted: stand, push, limits, integrity",
        fontsize=8.4, loc="left", pad=3, color=INK)
    for s in ("top", "right"):
        axT.spines[s].set_visible(False)

    # ---- no-overlap check --------------------------------------------------
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    inv = axM.transData.inverted()
    bboxes = []
    for t, (cx, cy, cw, ch), tag in texts:
        bb = t.get_window_extent(renderer=r)
        x0, y0 = inv.transform((bb.x0, bb.y0))
        x1, y1 = inv.transform((bb.x1, bb.y1))
        if (x0 < cx + 0.02 or x1 > cx + cw - 0.02 or
                y0 < cy + 0.03 or y1 > cy + ch - 0.03):
            raise SystemExit(f"cell text overflows in {tag}: "
                             f"({x0:.2f},{y0:.2f})-({x1:.2f},{y1:.2f}) "
                             f"vs cell ({cx},{cy})+{cw}x{ch}")
        bboxes.append((bb, tag))
    for t, tag in loose:
        bb = t.get_window_extent(renderer=r)
        ab = axM.get_window_extent(renderer=r)
        if bb.x0 < ab.x0 - 1 or bb.x1 > ab.x1 + 1 or \
                bb.y0 < ab.y0 - 1 or bb.y1 > ab.y1 + 1:
            raise SystemExit(f"text '{tag}' escapes its axes")
        bboxes.append((bb, tag))
    for i, tl in enumerate(axT.get_xticklabels()):
        bboxes.append((tl.get_window_extent(renderer=r), f"iter {i}"))
    bboxes.append((axT.title.get_window_extent(renderer=r), "replay title"))
    bboxes.append((axM.title.get_window_extent(renderer=r), "matrix title"))
    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            if bboxes[i][0].overlaps(bboxes[j][0]):
                raise SystemExit(
                    f"text overlap: {bboxes[i][1]} vs {bboxes[j][1]}")
    print(f"no-overlap check: OK ({len(bboxes)} texts inside cells/axes, "
          "no pairwise overlaps)")

    fig.savefig(OUT)
    print(f"wrote {OUT}  ({os.path.getsize(OUT)} bytes)")


if __name__ == "__main__":
    main()
