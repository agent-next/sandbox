#!/usr/bin/env python3
"""Render media/result.png and media/loop.png from real verdict JSONs.

Every number drawn comes from a judge run produced by media/make_media.sh in
this same invocation (media/data/*.json); nothing is invented.  Each figure
names the seed it was graded at.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chartlib as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

MUTANT_ORDER = [          # the order selftest.sh grades them in
    "m01-total-as-float",
    "m03-box-on-whitespace",
    "m03b-whole-page-box",
    "m04-quarantine-everything",
    "m05-wrong-date-format",
    "m06-accept-bad-date",
]
SHORT = {
    "m01-total-as-float": "m01 total as float",
    "m03-box-on-whitespace": "m03 box on margin",
    "m03b-whole-page-box": "m03b whole-page box",
    "m04-quarantine-everything": "m04 quarantine all",
    "m05-wrong-date-format": "m05 date DD/MM/YYYY",
    "m06-accept-bad-date": "m06 accept any date",
    "good": "good extractor",
}


def load(name):
    with open(os.path.join(DATA, name + ".json")) as f:
        v = json.load(f)
    g1 = next(g for g in v["gates"] if g["gate"] == "G1")
    failed = [g["gate"] for g in v["gates"] if not g["passed"]]
    return {
        "name": name,
        "passed": v["all_gates_passed"],
        "accuracy": g1.get("accuracy", 0.0),
        "correct": g1.get("correct", 0),
        "slots": g1.get("slots", 0),
        "gates_passed": len(v["gates"]) - len(failed),
        "n_gates": len(v["gates"]),
        "failed": failed,
        "seed": v.get("seed"),
    }


def wrap(s, width):
    """Greedy wrap; returns a list of lines."""
    words, lines, cur = s.split(), [], ""
    for w in words:
        if cur and len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def new_figure(W, H, title, seed, caption_lines):
    im, d, _ = C.new_figure(W, H, title, None)
    for i, line in enumerate(wrap(caption_lines, 84)[:3]):
        d.text((70, 122 + i * 36), line, font=C.font(28), fill=C.INK_2)
    return im, d


# ---------------------------------------------------------------- result.png
def result_png(rows):
    """The key figure: G1 field accuracy per artifact + the >= 95 % pass line."""
    W, H = 2400, 1620
    seed = rows[-1]["seed"]
    im, d = new_figure(
        W, H, "Field accuracy per graded artifact — the judge's G1 gate",
        seed,
        "Exact field matches against the answer key the corpus generator "
        "wrote itself (48 slots over 12 pages).  One grade run per bar, "
        "every bar graded at seed %d." % seed)

    # Lay the right-hand columns out from measured text widths, so a long
    # verdict or artifact name can never be clipped or overlap a bar end.
    vfont, nfont, lfont = C.font(26, True), C.font(25), C.font(25)
    labels = ["%.3f  (%d/%d)" % (r["accuracy"], r["correct"], r["slots"])
              for r in rows]
    notes = [("all %d gates pass" % r["n_gates"]) if r["passed"]
             else ("fails " + ", ".join(r["failed"])) for r in rows]
    names = [SHORT[r["name"]] for r in rows]
    lw = int(max(vfont.getlength(t) for t in labels))
    nw = int(max(nfont.getlength(t) for t in notes))
    aw = int(max(lfont.getlength(t) for t in names))
    left = 560
    right = W - 70 - lw - 30 - nw - 30 - aw - 16
    nx, lx = right + 16 + lw + 30, right + 16 + lw + 30 + nw + 30

    top, bottom = 330, H - 140
    p = C.Panel(d, (left, top, right, bottom))
    ptop, axis_y = p.hscale(0.0, 1.0, [0.0, 0.25, 0.5, 0.75, 1.0])
    p.text((left, top - 46), "artifact graded", size=28, bold=True,
           anchor="lm")
    p.text(((left + right) // 2, H - 58),
           "field accuracy  (exact fields / 48 slots)", size=28,
           fill=C.INK_2, anchor="ma")
    d.text((nx, top - 46), "verdict", size=28, bold=True, anchor="lm")
    d.text((lx, top - 46), "artifact", size=28, bold=True, anchor="lm")

    step = (axis_y - ptop) / len(rows)
    for i, r in enumerate(rows):
        y = int(ptop + step * (i + 0.5))
        color = C.PASS_BLUE if r["passed"] else C.FAIL_RED
        p.hbar(y, 36, 0.0, 1.0, r["accuracy"], color, labels[i], note_x=nx,
               note=notes[i], note_fill=C.INK_2 if r["passed"] else C.FAIL_RED)
        p.text((lx, y), names[i], size=25, anchor="lm",
               fill=C.INK if r["passed"] else C.INK_2)
    p.passline_v(0.0, 1.0, 0.95, "G1 pass line  ≥ 95 %", ptop - 46, axis_y)

    # a legend (two series), so identity is never colour-alone
    d.rectangle([70, H - 112, 102, H - 80], fill=C.PASS_BLUE)
    d.text((116, H - 96), "meets every gate", font=C.font(26), fill=C.INK,
           anchor="lm")
    d.rectangle([470, H - 112, 502, H - 80], fill=C.FAIL_RED)
    d.text((516, H - 96), "misses at least one gate", font=C.font(26),
           fill=C.INK, anchor="lm")
    im.save(os.path.join(HERE, "result.png"), dpi=(200, 200))


# ----------------------------------------------------------------- loop.png
def loop_png(rows, guard):
    """The agent loop: gates passed per iteration, plus the self-test bars."""
    W, H = 2400, 1620
    good = rows[-1]
    seed, n = good["seed"], good["n_gates"]
    im, d = new_figure(
        W, H, "The agent loop and the self-test", seed,
        "Left: gates passed per graded iteration — six single-edit mutants, "
        "then the known-good extractor.  Right: the share of known-bad "
        "artifacts the judge rejects.")

    top, bottom = 470, H - 250
    # -- panel A: gates passed per iteration -------------------------------
    left, right = 190, 1200
    pa = C.Panel(d, (left, top, right, bottom))
    pa.text((left - 30, top - 130), "Gates passed per iteration (of %d)" % n,
            size=34, bold=True)
    ptop = pa.vscale(0, n, list(range(n + 1)))
    xs = [left + (i + 1) * (right - left) / (len(rows) + 1)
          for i in range(len(rows))]
    pts = [(x, bottom - r["gates_passed"] / float(n) * (bottom - ptop))
           for x, r in zip(xs, rows)]
    pa.passline_h(0, n, n, left, right, "all %d gates = pass" % n)
    pa.dotline(pts, ptop, bottom, 0, n, C.PASS_BLUE)
    for (x, y), r in zip(pts, rows):
        pa.text((x, y - 30), "%d/%d" % (r["gates_passed"], n), size=27,
                bold=True, anchor="ma",
                fill=C.INK if r["passed"] else C.FAIL_RED)
        pa.text((x, bottom + 40), "it-%d" % (rows.index(r) + 1), size=25,
                anchor="ma", fill=C.INK_2)
        # mutant ids only (a compact tier under the marker): full names are in
        # media/result.png and never fit in one screen-width column
        for j, line in enumerate([r["name"].split("-")[0]]):
            pa.text((x, bottom + 76 + j * 30), line, size=22, anchor="ma",
                    fill=C.INK_2)
    pa.text(((left + right) // 2, H - 58),
            "iteration  (known-bad mutants first, known-good last)",
            size=26, fill=C.INK_2, anchor="ma")

    # -- panel B: self-test kill rate ---------------------------------------
    left2, right2 = 1460, 2330
    pb = C.Panel(d, (left2, top, right2, bottom))
    pb.text((left2 - 30, top - 130), "Self-test kill rate", size=34,
            bold=True)
    ptop2 = pb.vscale(0.0, 1.0, [0, 0.5, 1.0])
    killed = sum(1 for r in rows[:-1] if not r["passed"])
    bars = [("known-bad\nmutants", killed / float(len(rows) - 1),
             "%d/%d killed" % (killed, len(rows) - 1)),
            ("judge-guard\nmutant", 1.0 if guard else 0.0,
             "killed" if guard else "survived")]
    for i, (name, val, lab) in enumerate(bars):
        x = int(left2 + (i + 1) * (right2 - left2) / 3)
        pb.vbar(x, 150, ptop2, bottom, 0.0, 1.0, val, C.FAIL_RED, lab,
                above=ptop2 + 20)
        for j, line in enumerate(name.split("\n")):
            pb.text((x, bottom + 40 + j * 38), line, size=25, anchor="ma",
                    fill=C.INK_2)
    pb.passline_h(0.0, 1.0, 0.90, left2, right2, "≥ 90 % required")
    pb.text(((left2 + right2) // 2, H - 58),
            "share of known-bad artifacts the judge rejects", size=26,
            fill=C.INK_2, anchor="ma")
    im.save(os.path.join(HERE, "loop.png"), dpi=(200, 200))


def main():
    rows = [load(m) for m in MUTANT_ORDER] + [load("good")]
    with open(os.path.join(DATA, "judge_guard.json")) as f:
        guard = json.load(f)["killed"]
    result_png(rows)
    loop_png(rows, guard)
    print("[media] wrote result.png, loop.png")


if __name__ == "__main__":
    main()