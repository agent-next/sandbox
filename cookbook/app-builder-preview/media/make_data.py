#!/usr/bin/env python3
"""Media data for the app-builder-preview demo: judge outputs only.

Runs the real judge (judge/grade.sh) on the known-good artifact and on every
scripted mutant, and writes:

  media/data/grade_good.json   the good artifact's full verdict
  media/data/mutants/*.json    each mutant's verdict
  media/data/selftest.json     kill rate and the gate that killed each mutant
  media/data/replay.json       the scripted fixing replay (per iteration:
                               which gates still failed) - labelled as a
                               scripted replay, not a recorded live trace
  media/data/shots/*.png       one screenshot per flow, captured by the
                               judge's own flow gate (--shots)

Usage: make_data.py [replay-order...]
Nothing here is invented: every number is read back from a judge verdict.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent
JUDGE = DEMO / "judge"
GOOD = DEMO / "examples" / "good" / "app"
DATA = DEMO / "media" / "data"

# The fixing order a scripted replay follows: the wrong element id first
# (nothing works), then the stats, then delete, then the console error,
# then persistence, then the good artifact.
REPLAY = ["wrong_element_id", "stats_wrong_span", "broken_delete",
          "console_error", "no_persist", "good"]


def grade(app_dir, json_out, shots_dir=None):
    cmd = ["bash", str(JUDGE / "grade.sh"), str(app_dir),
           "--json", str(json_out)]
    if shots_dir:
        cmd += ["--shots", str(shots_dir)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=False)
    return json.loads(Path(json_out).read_text())


def failing_gates(verdict):
    return sorted(k for k, g in verdict.get("gates", {}).items()
                  if not g.get("pass"))


def main():
    order = sys.argv[1:] or REPLAY
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "mutants").mkdir(exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="appbuilder-media-"))
    try:
        mutants = work / "mutants"
        names = subprocess.run(["python3", "-I", str(JUDGE / "mutants.py"),
                                str(mutants)], capture_output=True, text=True,
                               check=True).stdout.split()

        verdicts = {}
        for name in names:
            out = DATA / "mutants" / f"{name}.json"
            verdicts[name] = grade(mutants / name, out)
            print(f"media: graded mutant {name}: "
                  f"killed by {failing_gates(verdicts[name]) or 'NOTHING'}")

        # the good artifact, with one screenshot per flow
        shots = DATA / "shots"
        shutil.rmtree(shots, ignore_errors=True)
        good = grade(GOOD, DATA / "grade_good.json", shots)
        verdicts["good"] = good
        print(f"media: graded known-good: gates "
              f"{'all pass' if not failing_gates(good) else failing_gates(good)}")

        killed = [n for n in names if failing_gates(verdicts[n])]
        selftest = {
            "source": "judge/grade.sh over judge/mutants.py",
            "known_good_passes": not failing_gates(good),
            "kill_rate": f"{len(killed)}/{len(names)}",
            "mutants": [{"name": n,
                         "killed": bool(failing_gates(verdicts[n])),
                         "failed_gates": failing_gates(verdicts[n])}
                        for n in names],
        }
        (DATA / "selftest.json").write_text(
            json.dumps(selftest, indent=2, sort_keys=True) + "\n")

        iterations = []
        for i, label in enumerate(order, start=1):
            v = good if label == "good" else verdicts[label]
            iterations.append({
                "iteration": i,
                "artifact": label,
                "failed_gates": failing_gates(v),
                "failing_flows": sorted(
                    k for k, f in v.get("flows", {}).items()
                    if not f.get("pass")),
                "console_errors": len(v.get("gates", {}).get("hygiene", {})
                                      .get("console_errors", [])),
                "passed": not failing_gates(v),
            })
        (DATA / "replay.json").write_text(json.dumps(
            {"note": "scripted fixing replay in the order a fixing agent "
                     "would meet the failures; not a recorded live trace",
             "iterations": iterations}, indent=2, sort_keys=True) + "\n")
        print(f"media: wrote {DATA}/selftest.json and replay.json")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
