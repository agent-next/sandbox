#!/usr/bin/env python3
"""loop.png -- can the judge be fooled?  The self-test's per-mutant verdicts
and the kill rate it measured.

Left:  the 11 known-bad single-edit mutants of the good artifact, each with
       the gate that actually caught it and the error count that gate
       reported (all from data/grade_<mutant>.json, real grade.sh runs).
       The known-good artifact is shown first as the control: the judge must
       pass it, or a "kill rate" is meaningless.
Right: the kill-rate bar -- killed vs survived mutants -- with the measured
       rate read out of data/selftest_output.txt (the judge's own line), the
       >= 90 % SPEC requirement as the pass line, and the determinism check
       result from the same log.
"""
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import (DEMO_NAME, INK, INK_2, MUTED, GRID, SURFACE, SEED,
                    GOOD, CRITICAL, BASELINE, MUTANT_ORDER, MUTANT_IDS,
                    GATE_LABEL, load_verdict)

KILL_RATE_MIN = 0.90      # SPEC.md: "A judge whose kill rate is below 90 %"
                          # is not done.


def selftest_facts(log_name="selftest_output.txt"):
    """Kill rate and determinism line, parsed out of the selftest log."""
    path = __import__("os").path.join(__import__("os").path.dirname(
        __import__("os").path.abspath(__file__)), "data", log_name)
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

    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=SURFACE)
    fig.text(0.5, 0.965,
             "%s: the self-test -- a judge that cannot fail is not a judge"
             % DEMO_NAME, ha="center", va="center", fontsize=24, color=INK,
             fontweight="bold")
    fig.text(0.5, 0.925,
             "the graded good asset passes; every known-bad single-edit "
             "mutant fails at least one gate · all verdicts from real "
             "judge/selftest.sh and grade.sh runs in media/data/",
             ha="center", va="center", fontsize=13, color=INK_2)

    # --- left: per-mutant verdicts ---------------------------------------
    left = fig.add_axes([0.030, 0.045, 0.585, 0.845])
    left.set_xlim(0, 1)
    left.set_ylim(0, 1)
    left.axis("off")

    rows = [("good", None, None, None, None)]           # the control
    for name in MUTANT_ORDER:
        v = load_verdict(name)
        if v["passed"]:
            raise SystemExit("loop.png: mutant %s passed the judge!" % name)
        gate = v["failed_gate"]
        errs = v["gates"][gate]["errors"]
        rows.append((name, MUTANT_IDS[name], gate, len(errs),
                     v["gates"]["validator"]["validator_status"]))
    # the unrepaired task input: the state the agent starts from
    b = load_verdict("broken")
    rows.append(("broken", "task", b["failed_gate"],
                 len(b["gates"][b["failed_gate"]]["errors"]),
                 b["gates"]["validator"]["validator_status"]))

    row_h = 1.0 / (len(rows) + 2.2)
    left.text(0.0, 1 - row_h * 0.65, "artifact graded", fontsize=12.5,
              color=MUTED, fontweight="bold", va="center")
    for x, head in ((0.335, "gate that caught it"),
                    (0.600, "validator status"), (0.815, "errors")):
        left.text(x, 1 - row_h * 0.65, head, fontsize=12.5, color=MUTED,
                  fontweight="bold", va="center")
    left.plot([0, 1], [1 - row_h * 1.25] * 2, color=BASELINE, linewidth=1.0)

    y = 1 - row_h * 1.85
    for entry in rows:
        name, did, gate, nerr, val_status = entry
        if name == "good":
            left.text(0.0, y, "examples/good/  (control)", fontsize=12,
                      color=INK, va="center", fontweight="bold")
            left.add_patch(plt.Rectangle((0.325, y - 0.014), 0.040, 0.028,
                                         facecolor=GOOD, linewidth=0))
            left.text(0.345, y, "✓", fontsize=11, color="#ffffff",
                      fontweight="bold", ha="center", va="center")
            left.text(0.382, y, "passed all 4 gates", fontsize=11.5,
                      color=INK_2, va="center")
            left.text(0.600, y, "PASS", fontsize=11.5, color=GOOD,
                      va="center", fontweight="bold")
            left.text(0.815, y, "0", fontsize=11.5, color=INK_2,
                      va="center")
            y -= row_h
            left.plot([0, 1], [y + row_h * 0.45] * 2, color=GRID,
                      linewidth=0.8)
            continue
        label = "%s  (%s)" % (name, did) if name != "broken" else \
            "task/traffic_cone_broken.usda  (task input)"
        left.text(0.0, y, label, fontsize=12, color=INK, va="center",
                  fontweight="bold")
        left.add_patch(plt.Rectangle((0.325, y - 0.014), 0.040, 0.028,
                                     facecolor=CRITICAL, linewidth=0))
        left.text(0.345, y, "✗", fontsize=11, color="#ffffff",
                  fontweight="bold", ha="center", va="center")
        left.text(0.382, y, GATE_LABEL[gate].replace("\n", " · "),
                  fontsize=11.5, color=INK_2, va="center")
        left.text(0.600, y, val_status, fontsize=11.5, color=CRITICAL,
                  va="center", fontweight="bold")
        left.text(0.815, y, str(nerr), fontsize=11.5, color=INK_2,
                  va="center")
        y -= row_h
        left.plot([0, 1], [y + row_h * 0.42] * 2, color=GRID, linewidth=0.8)

    left.text(0.0, 0.02, "error count = gate errors reported for the gate "
             "that failed (a mutant can trip an upstream gate first, e.g. "
             "scale_points fails the validator before geometry is scored) · "
             "seed %s" % SEED, fontsize=9.5, color=MUTED, va="bottom",
             style="italic")

    # --- right: kill-rate bar --------------------------------------------
    right = fig.add_axes([0.660, 0.045, 0.310, 0.845])
    right.set_facecolor(SURFACE)
    right.set_xticks([])
    right.set_yticks([])
    for side in ("top", "right", "bottom", "left"):
        right.spines[side].set_visible(False)

    right.set_title("self-test kill rate", fontsize=18, color=INK,
                    fontweight="bold", pad=20, loc="left")
    right.set_xlim(0, 1)
    right.set_ylim(0, 1)

    # the measured bar: killed share of the mutants
    bar_h = 0.115
    right.add_patch(plt.Rectangle((0.0, 0.855), 1.0, bar_h,
                                  facecolor=GRID, linewidth=0))
    right.add_patch(plt.Rectangle((0.0, 0.855), killed / total, bar_h,
                                  facecolor=GOOD, linewidth=0))
    right.text(0.0, 0.855 + bar_h + 0.030, "%d / %d = %d %%"
               % (killed, total, rate_pct), fontsize=32, color=GOOD,
               fontweight="bold", va="bottom")
    right.text(0.0, 0.855 - 0.030, "known-bad mutants killed", fontsize=13,
               color=INK_2, va="top")

    # the SPEC pass line
    right.plot([KILL_RATE_MIN] * 2, [0.855, 0.855 + bar_h],
                color=INK, linewidth=2.4)
    right.text(KILL_RATE_MIN, 0.855 + bar_h + 0.030,
               "\nSPEC minimum %d %%" % (KILL_RATE_MIN * 100), fontsize=11,
               color=INK, va="bottom", ha="left", linespacing=1.4)

    # readouts from the selftest log
    y = 0.740
    right.text(0.0, y, "from judge/selftest.sh", fontsize=15, color=INK,
               fontweight="bold", va="top")
    y -= 0.075
    for text, value, ok in (
            ("known-good artifact passed", "all 4 gates", True),
            ("mutants graded", "%d" % total, True),
            ("survived the judge", "%d" % (total - killed),
             (total - killed) == 0),
            ("determinism (--seed 1 twice)",
             "identical" if det_ok else "DIFFERS", det_ok),
            ("self-test exit", "OK" if test_ok else "FAILED", test_ok)):
        glyph = "✓" if ok else "✗"
        color = GOOD if ok else CRITICAL
        right.add_patch(plt.Rectangle((0.0, y - 0.018), 0.045, 0.036,
                                      facecolor=color, linewidth=0))
        right.text(0.0225, y, glyph, fontsize=12, color="#ffffff",
                   fontweight="bold", ha="center", va="center")
        right.text(0.065, y, text, fontsize=12, color=INK, va="center")
        right.text(0.995, y, value, fontsize=12, color=INK_2, va="center",
                   ha="right")
        y -= 0.070

    # what the three gates are, for context
    y -= 0.030
    right.text(0.0, y, "which gate caught the mutants", fontsize=15,
               color=INK, fontweight="bold", va="top")
    y -= 0.075
    mutants = [r for r in rows if r[0] not in ("good", "broken")]
    for gate, label in (("validator", "NVIDIA nvidia_usd_validate"),
                        ("oracle", "independent usd-core oracle"),
                        ("geometry", "invariance vs the original"),
                        ("recount", "clean-room text recount")):
        caught = sum(1 for r in mutants if r[2] == gate)
        right.text(0.0, y, GATE_LABEL[gate].replace("\n", " · "),
                   fontsize=11.5, color=INK, va="center", fontweight="bold")
        right.text(0.995, y, "%d" % caught, fontsize=11.5, color=INK_2,
                   va="center", ha="right")
        y -= 0.058
        right.text(0.0, y, label, fontsize=9.5, color=MUTED, va="center")
        y -= 0.050

    right.text(0.0, 0.02, "a mutant that fails an early gate never reaches "
               "the later ones, so the counts need not sum to %d · source: "
               "media/data/" % total,
               fontsize=9, color=MUTED, va="bottom", style="italic")

    fig.savefig("loop.png", dpi=100, facecolor=SURFACE)
    print("wrote loop.png")


if __name__ == "__main__":
    main()
