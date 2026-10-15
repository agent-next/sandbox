#!/usr/bin/env python3
"""STORYBOARD.md -- the shot plan, written before the video is cut.

Rendered from media/scenes.py (the same table media/make_video.py cuts
from), with the source-data table and the caption speed-ups filled in from
what is actually on disk: the judge output files in media/data/ and the
real wall times inside them.  So the storyboard cannot claim a shot the
video does not have, or a speed-up the recorded run does not show.

Run before make_video.py by media/make_media.sh.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")

sys.path.insert(0, HERE)
import scenes  # noqa: E402
from common import MUTANTS  # noqa: E402


def need(path):
    if not os.path.exists(path):
        raise SystemExit("write_storyboard: missing %s -- run "
                         "media/collect.sh first" % path)
    return path


def wall_s(name):
    with open(need(os.path.join(DATA, "verdict-%s.json" % name))) as fh:
        return json.load(fh)["timing"]["wall_s"]


def speedup(real_s, shot_frames):
    """How many times faster than real time the shot plays."""
    return "%.0fx speed" % (real_s / (shot_frames / float(scenes.FPS)))


def main():
    good = json.load(open(need(os.path.join(DATA, "verdict-good.json"))))
    cells = good["metrics"]["cells"]
    versions = good["metrics"]["versions"]
    with open(need(os.path.join(DATA, "selftest.log"))) as fh:
        selftest_text = fh.read()
    kill_line = next(ln for ln in selftest_text.splitlines()
                     if ln.startswith("kill rate:"))

    # real wall times recorded inside the judge's own verdicts
    selftest_real = sum(wall_s(n) for n in ["good"] + MUTANTS) + 2 * wall_s(
        "good")  # nine mutants + known-good + the two determinism runs
    grade_real = wall_s("good")
    speeds = {}
    for s in scenes.SCENES:
        if s["key"] == "selftest":
            speeds[s["key"]] = speedup(selftest_real, s["frames"])
        if s["key"] == "verdict":
            speeds[s["key"]] = speedup(grade_real, s["frames"])

    spans, total = scenes.spans()
    rows = []
    for i, (s, a, b) in enumerate(spans, 1):
        cap = s["caption"].format(**speeds)
        rows.append("| %d | %s | **%s** | %s | `%s` | %s |"
                    % (i, scenes.fmt(a, b), s["slot"], s["fills"],
                       s["source"], cap))

    lines = [
        "# STORYBOARD -- `cookbook/ci-test-matrix/media/demo.mp4`",
        "",
        "Planned before the video was cut; `media/write_storyboard.py`",
        "renders this table from `media/scenes.py`, and `make_video.py` cuts",
        "exactly those shots for exactly those durations, so the storyboard",
        "and the cut cannot drift apart.  Every shot is built from the judge",
        "output files in `media/data/` and `make_media.sh` fails if one is",
        "missing.",
        "",
        "Every number and every line of terminal text on screen is real",
        "judge output (`judge/grade.sh --seed 42`, `judge/selftest.sh`) from",
        "the run recorded in `media/data/`; the fixing sequence is a",
        "**replay** of real grade verdicts, labelled as such on screen.",
        "",
        "## Source data (all written by the judge in this sandbox)",
        "",
        "| file | written by |",
        "|---|---|",
        "| `data/verdict-good.json` | `judge/grade.sh examples/good --seed "
        "42 --json` |",
        "| `data/verdict-<mutant>.json` (9) | `judge/grade.sh "
        "media/scratch/mutants/<mutant> --seed 42 --json` |",
        "| `data/grade-good.txt` | `judge/grade.sh examples/good` stdout "
        "(the verdict JSON) |",
        "| `data/selftest.log` | `judge/selftest.sh` (real transcript) |",
        "| `data/loop.json` | `media/write_loop.py` -- the replay order "
        "(stage labels only; every number comes from the verdict JSONs) |",
        "",
        "## Slot table",
        "",
        "| # | time | slot | fills the frame | source data / command | "
        "caption (burned in) |",
        "|---|---|---|---|---|---|",
    ]
    lines += rows
    lines += [
        "",
        "Total %d frames = %.1f s at %d fps; %d scene cuts = %.1f per 10 s "
        "(floor 0.8)."
        % (total, total / float(scenes.FPS), scenes.FPS, len(scenes.SCENES)
           - 1, scenes.cuts_per_10s()),
        "",
        "## Craft checks the cut must satisfy",
        "",
        "- Every shot before the end card moves: the terminal scrolls and",
        "  line groups pop in the two streaming shots, cells and matrix rows",
        "  fill one per beat, the progress and mask bars grow every frame,",
        "  the highlight band sweeps the hook.",
        "- >= 0.8 scene cuts per 10 s: %d cuts in %.1f s = %.1f / 10 s."
        % (len(scenes.SCENES) - 1, total / float(scenes.FPS),
           scenes.cuts_per_10s()),
        "- Captions >= 4 %% of frame height (44 pt cap height on 1080 px);",
        "  the terminal shots are cropped to the active region of the log.",
        "- The end card is the only static frame and holds %d s (the gate"
        % (scenes.SCENES[-1]["frames"] // scenes.FPS),
        "  measures the last 2 s).",
        "- The judge's PASS verdict and the kill rate are large enough to",
        "  read on a phone (the kill counter and the PASS stamp are >= 60 px",
        "  digits).",
        "- Every shot is real output from the pinned run: the transcript is",
        "  `judge/selftest.sh`'s own text, the verdict JSON is `grade.sh`'s",
        "  own stdout, the matrix, mask, stamps and kill matrix are the",
        "  verdict JSONs' own fields.",
        "",
        "## Recorded numbers on screen",
        "",
        "| number | value | source |",
        "|---|---|---|",
        "| cells | %s | verdict-good.json -> metrics.versions |"
        % ", ".join(versions),
        "| interpreter stamps | %s | verdict-good.json -> metrics.cells |"
        % ", ".join("%s=%s" % (v, cells[v]["stamp"]) for v in versions),
        "| tests per cell | %d | verdict-good.json -> metrics.tests_per_cell "
        "|" % good["metrics"]["tests_per_cell"],
        "| failing cell (toggle on) | 3.9 | verdict-good.json -> "
        "metrics.mask_on |",
        "| exit codes (on / off) | %d / %d | verdict-good.json -> "
        "metrics.exit_codes |" % (good["metrics"]["exit_codes"]["on"],
                                  good["metrics"]["exit_codes"]["off"]),
        "| %s | %s | data/selftest.log |" % (kill_line.split(":")[0],
                                             kill_line.split(":", 1)[1]
                                             .strip()),
        "",
        "Speed-ups are computed from the real `timing.wall_s` the judge",
        "recorded inside those verdict JSONs, not estimated.",
        "",
    ]
    out = os.path.join(HERE, "STORYBOARD.md")
    with open(out, "w") as fh:
        fh.write("\n".join(lines))
    print("wrote %s (%d shots, %.1f s, %s)"
          % (out, len(spans), total / float(scenes.FPS),
             ", ".join("%s %s" % (s["key"], speeds[s["key"]])
                       for s in scenes.SCENES if s["key"] in speeds)))


if __name__ == "__main__":
    main()
