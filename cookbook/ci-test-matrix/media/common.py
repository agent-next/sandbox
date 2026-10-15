#!/usr/bin/env python3
"""Shared helpers for the ci-test-matrix media figures and video.

Every number drawn by the figures is loaded here from a file the judge
wrote (media/data/verdict-*.json from judge/grade.sh, media/data/loop.json
for the replayed fixing sequence) -- nothing is invented.  The overlap and
bounds checks are the automated guard required by the standard: any text
that leaves the figure, or any two texts that intersect, raises
RuntimeError and fails make_media.sh.
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DEMO = os.path.dirname(HERE)

# The judge's gate order (judge/judge.py GATE_ORDER).
GATES = ["parse", "coverage", "identity", "detection", "counts",
         "table", "mask", "exit_code"]

GATE_SHORT = {
    "parse": "parse\n(G1)", "coverage": "coverage\n(G2)",
    "identity": "identity\n(G3)", "detection": "detection\n(G4)",
    "counts": "counts\n(G5)", "table": "table\n(G6)",
    "mask": "mask\n(G7)", "exit_code": "exit_code\n(G8)",
}

GATE_RULES = {
    "parse":      "4 required keys; versions == [3.9..3.13]",
    "coverage":   "one non-empty JUnit XML per cell (5)",
    "identity":   "5 distinct interpreters, each matching its cell",
    "detection":  "on: exactly 3.9 fails; off: none fails",
    "counts":     "every cell reports the same test count",
    "table":      "table agrees with the collected JUnit XML",
    "mask":       "pattern == [pass,pass,pass,pass,fail] on",
    "exit_code":  "0 when all pass, non-zero when one fails",
}

# The nine single-edit mutants judge/mutants.py generates, in its order.
MUTANTS = ["cell-skipped", "same-interpreter", "failure-masked",
           "junit-missing", "wrong-count", "no-versions-key",
           "toggle-swapped", "shared-mask", "no-runner"]

# loop.png row order: the replayed fix sequence first, then the rest.
ROWS = ["good", "cell-skipped", "same-interpreter", "failure-masked",
        "junit-missing", "wrong-count", "no-versions-key", "toggle-swapped",
        "shared-mask", "no-runner"]

VERSIONS = ["3.9", "3.10", "3.11", "3.12", "3.13"]

# Colour-blind-safe (Okabe-Ito).
C_PASS = "#009E73"
C_FAIL = "#D55E00"
C_ORACLE = "#E69F00"    # the judge's pass line / oracle boundary
C_BG = "#ffffff"
C_FG = "#1a1a1a"
C_DIM = "#57606a"
MONO = "DejaVu Sans Mono"


def load_verdict(name):
    """Load media/data/verdict-<name>.json (real grade.sh output)."""
    with open(os.path.join(DATA, "verdict-%s.json" % name)) as fh:
        return json.load(fh)


def load_loop():
    """The replayed fix sequence (bad -> partly fixed -> good).

    It only orders verdict files that already exist; the figures and the
    video label it as a replay of real judge output, not a live agent
    trace.
    """
    with open(os.path.join(DATA, "loop.json")) as fh:
        return json.load(fh)


def selftest_kill():
    """(killed, total) parsed from the real selftest.log."""
    with open(os.path.join(DATA, "selftest.log")) as fh:
        text = fh.read()
    m = re.search(r"kill rate: (\d+)/(\d+)", text)
    if not m:
        raise RuntimeError("selftest.log has no kill-rate line")
    return int(m.group(1)), int(m.group(2))


def gates_passed(verdict):
    return sum(1 for g in verdict["gates"].values() if g["pass"])


def cell_short(gate, detail):
    """Compress one gate's measured detail to fit a matrix cell."""
    # gates that never ran because an earlier gate closed them
    if detail in ("no valid matrix.yaml; no gate can run",
                  "run_matrix.py not found", "no runner",
                  "matrix.yaml failed the parse gate"):
        return "not run"
    short = {
        "matrix.yaml unreadable or invalid: matrix.yaml is missing: "
        "python_versions": "no versions",
        "parse gate ok, but run_matrix.py is missing": "no runner",
        "toggle on: the table says 3.9=pass but cell-3.9.xml says fail":
            "hides fail",
        "toggle on (the 3.9 cell fails): run_matrix.py exited 0 -- a "
        "runner that always exits 0 is masking the failure":
            "masks fail",
        "toggle off (all cells pass): run_matrix.py exited 1, expected 0":
            "exit 1",
        "toggle on: exactly the 3.9 cell must fail; failing cells were "
        "none; toggle off: all five cells pass": "none failed",
    }
    if detail in short:
        return short[detail]
    m = re.match(r"python_versions must be exactly \[.*\], got \[(.*)\]",
                 detail)
    if m:
        got = [x.strip().strip("'\"") for x in m.group(1).split(",")]
        if not any(got):
            return "no versions"
        if len(got) > 2:
            return "%s..%s only" % (got[0], got[-1])
        return "got " + ", ".join(got)
    if "no JUnit XML for python" in detail or "no JUnit XML for" in detail:
        return "no JUnit XML"
    if "cells have no interpreter stamp" in detail:
        return "no stamp"
    m = re.search(r"ran under (\d+\.\d+\.\d+), not", detail)
    if m:
        return "all ran " + m.group(1)
    if "share interpreter" in detail:
        return "shared"
    m = re.search(r"the table says (\S+) ran (\d+) tests but cell-\S+ "
                  r"records (\d+)", detail)
    if m:
        return "%s != %s tests" % (m.group(2), m.group(3))
    m = re.search(r"cell (\S+) = (\w+), expected", detail)
    if m:
        return "%s %s" % (m.group(1), m.group(2))
    if gate == "coverage" and detail.startswith("one non-empty JUnit XML"):
        return "5 files"
    if gate == "identity" and detail.startswith("each cell ran under"):
        return "distinct"
    if gate == "counts" and detail.startswith("all 5 cells"):
        return "7 each"
    if gate == "detection" and detail.startswith("toggle on: exactly"):
        return "3.9 only"
    if gate == "detection" and "failing cells were ['3.9']" in detail:
        return "3.9 failed"
    if gate == "detection" and "failing cells were none" in detail:
        return "none failed"
    if gate == "table" and detail.startswith("the aggregated table matches"):
        return "agrees"
    if gate == "mask" and detail.startswith("the pass/fail pattern"):
        return "mask ok"
    return detail[:14]


# ---------------------------------------------------------------- checks
def check_no_overlap(fig, items, what):
    """Assert no two drawn elements' window-extent bboxes intersect and
    none leaves the figure.  Raises RuntimeError -- make_media.sh treats
    any failure as fatal, so an overlapping figure can never be committed
    silently.
    """
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    boxes = [art.get_window_extent(renderer=rend) for art in items]
    fb = fig.bbox
    for i, bb in enumerate(boxes):
        if bb.x0 < fb.x0 - 1 or bb.x1 > fb.x1 + 1 or \
           bb.y0 < fb.y0 - 1 or bb.y1 > fb.y1 + 1:
            raise RuntimeError("%s: element %d escapes the figure" % (what, i))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i].overlaps(boxes[j]):
                raise RuntimeError(
                    "%s: elements %d and %d overlap" % (what, i, j))


def check_inside_axes(fig, axes, items, what):
    """Assert every artist's window extent lies within its axes panel."""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    ax_bb = axes.get_window_extent(renderer=rend)
    for i, art in enumerate(items):
        bb = art.get_window_extent(renderer=rend)
        if bb.x0 < ax_bb.x0 - 1 or bb.x1 > ax_bb.x1 + 1 or \
           bb.y0 < ax_bb.y0 - 1 or bb.y1 > ax_bb.y1 + 1:
            raise RuntimeError(
                "%s: element %d (%s) escapes its panel "
                "(bb: x0=%.1f x1=%.1f y0=%.1f y1=%.1f vs ax: "
                "x0=%.1f x1=%.1f y0=%.1f y1=%.1f)"
                % (what, i, type(art).__name__, bb.x0, bb.x1, bb.y0, bb.y1,
                   ax_bb.x0, ax_bb.x1, ax_bb.y0, ax_bb.y1))
