#!/usr/bin/env python3
"""loop.png -- can the judge be fooled?  The self-test's per-mutant verdicts
and the kill rate it measured.

Left:  the known-bad single-edit mutants of the good artifact, each with the
       gate that actually caught it and the error count that gate reported
       (all from data/grade_<mutant>.json, real grade.sh runs).  The
       known-good artifact is shown first as the control: the judge must pass
       it, or a "kill rate" is meaningless.  The unrepaired task input is the
       last row.
Right: the kill-rate bar -- killed vs survived mutants -- with the measured
       rate read out of data/selftest_output.txt (the judge's own line), the
       >= 90 % SPEC requirement as the pass line, and the determinism check
       result from the same log.
"""
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DEMO_NAME, INK, INK_2, MUTED, GRID, SURFACE, SEED,
                    GOOD, CRITICAL, BASELINE, MUTANT_ORDER, MUTANT_IDS,
                    GATE_LABEL, GATE_ORDER, load_verdict, load_row)

KILL_RATE_MIN = 0.90      # SPEC.md: a judge whose kill rate is below 90 %
                          # is not done.

GATE_CAUGHT_REASON = {
    "validator": "NVIDIA nvidia_usd_validate",
    "oracle": "independent usd-core oracle",
    "geometry": "invariance vs the original",
    "up_axis": "up axis vs the measured height axis",
    "recount": "clean-room text recount",
}


def selftest_facts(log_name="selftest_output.txt"):
    """Kill rate and determinism line, parsed out of the selftest log."""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                        log_name)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"kill rate (\d+)/(\d+) = (\d+)%", text)
    if not m:
        raise SystemExit("loop.png: no 'kill rate' line in %s" % log_name)
    killed, total = int(m.group(1)), int(m.group(2))
    det = "determinism OK" in text and "DETERMINISM FAILED" not in text
    ok = re.search(r"^selftest: OK$", text, re.M) is not None
    return killed, total, int(m.group(3)), det, ok


def main():
    killed, total, rate_pct, det_ok, test_ok = selftest_facts()
    good = load_verdict("good")
    n_gates = len(GATE_ORDER)

    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=SURFACE)
    fig.text(0.5, 0.975,
             "%s: the self-test -- a judge that cannot fail is not a judge"
             % DEMO_NAME, ha="center", va="center", fontsize=24, color=INK,
             fontweight="bold")
    fig.text(0.5, 0.940,
             "the graded good asset passes; every known-bad single-edit "
             "mutant fails at least one gate · all verdicts from real "
             "judge/selftest.sh and grade.sh runs in media/data/",
             ha="center", va="center", fontsize=13, color=INK_2)

    # --- left: per-mutant verdicts ---------------------------------------
    left = fig.add_axes([0.030, 0.040, 0.565, 0.860])
    left.set_xlim(0, 1)
    left.set_ylim(0, 1)
    left.axis("off")

    rows = [("good", None, None, None, None)]           # the control
    for name in MUTANT_ORDER:
        v = load_row(name)
        if v["passed"]:
            raise SystemExit("loop.png: mutant %s passed the judge!" % name)
        gate = v["failed_gate"]
        errs = v["gates"][gate]["errors"]
        rows.append((name, MUTANT_IDS[name], gate, len(errs),
                     v["gates"]["validator"]["validator_status"]))
    # the unrepaired task input: the state the agent starts from
    b = load_row("broken")
    rows.append(("broken", "task", b["failed_gate"],
                 len(b["gates"][b["failed_gate"]]["errors"]),
                 b["gates"]["validator"]["validator_status"]))

    # Row layout: header + N rows + footnote, all inside [0, 1] with room.
    row_h = 1.0 / (len(rows) + 1.6)
    hy = 1.0 - row_h * 0.60
    left.text(0.0, hy, "artifact graded", fontsize=12.5,
              color=MUTED, fontweight="bold", va="center")
    for x, head in ((0.360, "gate that caught it"),
                    (0.615, "validator status"), (0.845, "errors")):
        left.text(x, hy, head, fontsize=12.5, color=MUTED,
                  fontweight="bold", va="center")
    left.plot([0, 1], [1 - row_h * 1.10] * 2, color=BASELINE, linewidth=1.0)

    y = 1 - row_h * 1.60
    for entry in rows:
        name, did, gate, nerr, val_status = entry
        if name == "good":
            left.text(0.0, y, "examples/good/  (control)", fontsize=12,
                      color=INK, va="center", fontweight="bold")
            left.add_patch(plt.Rectangle((0.345, y - 0.014), 0.038, 0.028,
                                         facecolor=GOOD, linewidth=0))
            left.text(0.364, y, "✓", fontsize=11, color="#ffffff",
                      fontweight="bold", ha="center", va="center")
            left.text(0.396, y, "passed all %d gates" % n_gates, fontsize=11.5,
                      color=INK_2, va="center")
            left.text(0.615, y, "PASS", fontsize=11.5, color=GOOD,
                      va="center", fontweight="bold")
            left.text(0.845, y, "0", fontsize=11.5, color=INK_2,
                      va="center")
            y -= row_h
            left.plot([0, 1], [y + row_h * 0.45] * 2, color=GRID,
                      linewidth=0.8)
            continue
        label = "%s  (%s)" % (name, did) if name != "broken" else \
            "task/traffic_cone_broken.usda  (task input)"
        left.text(0.0, y, label, fontsize=12, color=INK, va="center",
                  fontweight="bold")
        left.add_patch(plt.Rectangle((0.345, y - 0.014), 0.038, 0.028,
                                     facecolor=CRITICAL, linewidth=0))
        left.text(0.364, y, "✗", fontsize=11, color="#ffffff",
                  fontweight="bold", ha="center", va="center")
        left.text(0.396, y, GATE_LABEL[gate].replace("\n", " · "),
                  fontsize=11.5, color=INK_2, va="center")
        left.text(0.615, y, val_status, fontsize=11.5, color=CRITICAL,
                  va="center", fontweight="bold")
        left.text(0.845, y, str(nerr), fontsize=11.5, color=INK_2,
                  va="center")
        y -= row_h
        left.plot([0, 1], [y + row_h * 0.42] * 2, color=GRID, linewidth=0.8)

    left.text(0.0, 0.015, "error count = the errors reported by the gate that "
             "failed (a mutant can trip an upstream gate first, e.g. "
             "scale_points fails the validator before geometry is scored) · "
             "seed %s" % SEED, fontsize=9.5, color=MUTED, va="bottom",
             style="italic")

    # --- right: kill-rate bar --------------------------------------------
    right = fig.add_axes([0.660, 0.055, 0.310, 0.845])
    right.set_facecolor(SURFACE)
    right.set_xticks([])
    right.set_yticks([])
    for side in ("top", "right", "bottom", "left"):
        right.spines[side].set_visible(False)

    right.set_title("self-test kill rate", fontsize=18, color=INK,
                    fontweight="bold", pad=14, loc="left")
    right.set_xlim(0, 1)
    right.set_ylim(0, 1)

    # the measured bar: killed share of the mutants.  Everything that labels
    # the bar sits ABOVE it, inside the axes, so nothing runs off the top or
    # into the figure subtitle.
    bar_h = 0.115
    bar_y = 0.800
    right.add_patch(plt.Rectangle((0.0, bar_y), 1.0, bar_h,
                                  facecolor=GRID, linewidth=0))
    right.add_patch(plt.Rectangle((0.0, bar_y), killed / total, bar_h,
                                  facecolor=GOOD, linewidth=0))
    right.text(0.0, bar_y + bar_h + 0.035, "%d / %d = %d %%"
               % (killed, total, rate_pct), fontsize=34, color=GOOD,
               fontweight="bold", va="bottom")
    right.text(0.0, bar_y - 0.030, "known-bad mutants killed", fontsize=13,
               color=INK_2, va="top")

    # the SPEC pass line, labelled INSIDE the axes below the line
    right.plot([KILL_RATE_MIN] * 2, [bar_y, bar_y + bar_h],
               color=INK, linewidth=2.4)
    right.text(KILL_RATE_MIN - 0.015, bar_y + bar_h + 0.010,
               "SPEC min %d %%" % (KILL_RATE_MIN * 100), fontsize=11,
               color=INK, va="bottom", ha="right", linespacing=1.4)

    # readouts from the selftest log
    y = 0.660
    right.text(0.0, y, "from judge/selftest.sh", fontsize=15, color=INK,
               fontweight="bold", va="top")
    y -= 0.072
    for text, value, ok in (
            ("known-good artifact passed", "all %d gates" % n_gates, True),
            ("mutants graded", "%d" % total, True),
            ("survived the judge", "%d" % (total - killed),
             (total - killed) == 0),
            ("determinism (--seed 1 twice)",
             "identical" if det_ok else "DIFFERS", det_ok),
            ("self-test exit", "OK" if test_ok else "FAILED", test_ok)):
        glyph = "✓" if ok else "✗"
        color = GOOD if ok else CRITICAL
        right.add_patch(plt.Rectangle((0.0, y - 0.016), 0.042, 0.032,
                                      facecolor=color, linewidth=0))
        right.text(0.021, y, glyph, fontsize=12, color="#ffffff",
                   fontweight="bold", ha="center", va="center")
        right.text(0.060, y, text, fontsize=12, color=INK, va="center")
        right.text(0.995, y, value, fontsize=12, color=INK_2, va="center",
                    ha="right")
        y -= 0.066

    # what the gates are, for context
    y -= 0.022
    right.text(0.0, y, "which gate caught the mutants", fontsize=15,
               color=INK, fontweight="bold", va="top")
    y -= 0.072
    mutants = [r for r in rows if r[0] not in ("good", "broken")]
    for gate in GATE_ORDER:
        caught = sum(1 for r in mutants if r[2] == gate)
        right.text(0.0, y, GATE_LABEL[gate].replace("\n", " · "),
                   fontsize=11.5, color=INK, va="center", fontweight="bold")
        right.text(0.995, y, "%d" % caught, fontsize=11.5, color=INK_2,
                   va="center", ha="right")
        y -= 0.046
        right.text(0.0, y, GATE_CAUGHT_REASON[gate], fontsize=9.5, color=MUTED,
                   va="center")
        y -= 0.044

    right.text(0.0, 0.020, "a mutant that fails an early gate never reaches "
               "the later ones, so the counts need not sum to %d · source: "
               "media/data/" % total,
               fontsize=9, color=MUTED, va="bottom", style="italic")

    fig.savefig("loop.png", dpi=100, facecolor=SURFACE)
    print("wrote loop.png")


if __name__ == "__main__":
    main()
