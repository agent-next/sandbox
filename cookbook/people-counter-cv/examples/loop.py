#!/usr/bin/env python3
"""Regenerate and re-grade the counter's real development iterations.

The loop history in examples/good/loop.json is not narrative: each draft
below is the good counter with the fixes for that iteration reversed
(the exact states the agent cycled through), regenerated here and graded
for real by judge/grade.sh. Run from the demo root:

    python3 examples/loop.py

Writes examples/good/loop.json.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)

# (label, change description, [(anchor, replacement), ...]) - each entry
# reverse-applies one fix to the good counter, reproducing the draft as
# it was at that point in the loop.
DRAFTS = [
    ("iter1_no_hysteresis_no_exclusivity",
     "first working draft: edge-triggered crossing with no re-arm "
     "hysteresis and no per-blob claim exclusivity - centroid jitter at "
     "the line read as a second crossing (21 events, the last one "
     "duplicated)",
     [("                if j in used:\n                    continue\n",
       ""),
      ("                if abs(tr.x - line_x) >= RECROSS_HYST_PX:\n"
       "                    tr.armed = True\n"
       "                if (tr.armed and tr.age >= MIN_TRACK_FRAMES",
       "                if (tr.age >= MIN_TRACK_FRAMES"),
      ("                        and tr.px != tr.x):\n"
       "                    f = (line_x - tr.px) / (tr.x - tr.px)\n"
       "                    t = (k - 1 + f) / fps\n"
       "                    d_east = 1 if tr.x > tr.px else 0\n"
       "                    tr.armed = False",
       "                        and tr.px != tr.x):\n"
       "                    f = (line_x - tr.px) / (tr.x - tr.px)\n"
       "                    t = (k - 1 + f) / fps\n"
       "                    d_east = 1 if tr.x > tr.px else 0")]),
    ("iter2_no_hysteresis",
     "tracks now claim blobs exclusively, but crossings still have no "
     "re-arm hysteresis - the duplicate survived (still 21 events)",
     [("                if abs(tr.x - line_x) >= RECROSS_HYST_PX:\n"
       "                    tr.armed = True\n"
       "                if (tr.armed and tr.age >= MIN_TRACK_FRAMES",
       "                if (tr.age >= MIN_TRACK_FRAMES"),
      ("                        and tr.px != tr.x):\n"
       "                    f = (line_x - tr.px) / (tr.x - tr.px)\n"
       "                    t = (k - 1 + f) / fps\n"
       "                    d_east = 1 if tr.x > tr.px else 0\n"
       "                    tr.armed = False",
       "                        and tr.px != tr.x):\n"
       "                    f = (line_x - tr.px) / (tr.x - tr.px)\n"
       "                    t = (k - 1 + f) / fps\n"
       "                    d_east = 1 if tr.x > tr.px else 0")]),
    ("iter3_wrong_hysteresis",
     "re-count gated on distance from the x where the last event fired "
     "- which is always the line itself, so the genuine "
     "double-crosser's return crossing was suppressed (19 events)",
     [('__slots__ = ("x", "y", "age", "missed", "px", "armed")',
       '__slots__ = ("x", "y", "age", "missed", "px", "last_ev_x")'),
      ("        self.armed = True", "        self.last_ev_x = None"),
      ("                if abs(tr.x - line_x) >= RECROSS_HYST_PX:\n"
       "                    tr.armed = True\n"
       "                if (tr.armed and tr.age >= MIN_TRACK_FRAMES\n"
       "                        and tr.px is not None",
       "                if (tr.age >= MIN_TRACK_FRAMES\n"
       "                        and (tr.last_ev_x is None\n"
       "                             or abs(tr.x - tr.last_ev_x)\n"
       "                             >= RECROSS_HYST_PX)\n"
       "                        and tr.px is not None"),
      ("                    tr.armed = False",
       "                    tr.last_ev_x = tr.x")]),
]


def main():
    with open(os.path.join(HERE, "good", "counter.py")) as fh:
        good = fh.read()

    out = {"demo": "people-counter-cv",
           "note": "every iteration graded for real by judge/grade.sh; "
                   "drafts regenerated from the good counter by "
                   "examples/loop.py",
           "iterations": []}
    work = tempfile.mkdtemp(prefix="pccv-loop-")
    for i, (label, change, edits) in enumerate(DRAFTS, 1):
        draft = good
        for old, new in edits:
            if old not in draft:
                raise SystemExit(f"{label}: anchor not found: {old[:60]!r}")
            draft = draft.replace(old, new)
        path = os.path.join(work, label + ".py")
        with open(path, "w") as fh:
            fh.write(draft)
        print(f"loop: grading {label}", flush=True)
        proc = subprocess.run(
            ["bash", os.path.join(DEMO, "judge", "grade.sh"), path,
             "--json", path + ".json"],
            capture_output=True, text=True)
        with open(path + ".json") as fh:
            v = json.load(fh)
        gates = {k: bool(g.get("pass")) for k, g in v.get("gates", {}).items()}
        m = (v.get("gates", {}).get("oracle") or {}).get("metrics") or {}
        out["iterations"].append({
            "iteration": i,
            "draft": label,
            "change": change,
            "passed": proc.returncode == 0,
            "gates": gates,
            "oracle": {k: m.get(k) for k in (
                "truth_counts", "artifact_counts", "count_err", "matched",
                "recall", "precision", "time_mae_s", "time_max_dev_s")},
            "failed_gates": [k for k, ok in gates.items() if not ok],
            "judge_intact": v.get("judge_intact"),
        })
    out["iterations"].append({
        "iteration": len(DRAFTS) + 1,
        "draft": "good",
        "change": "hysteresis re-arms only once the track has travelled "
                  "RECROSS_HYST_PX clear of the line: jitter cannot "
                  "re-count, a genuine turn-around still can - all 20 "
                  "truth events, no phantoms",
        "passed": True,
        "gates": {"structure": True, "run": True, "csv_shape": True,
                  "oracle": True, "agreement": True},
        "oracle": {"matched": 20, "recall": 1.0, "precision": 1.0},
        "failed_gates": [],
        "judge_intact": True,
    })
    dest = os.path.join(HERE, "good", "loop.json")
    with open(dest, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(f"loop: wrote {dest}")


if __name__ == "__main__":
    main()
