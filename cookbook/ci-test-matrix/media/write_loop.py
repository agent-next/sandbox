#!/usr/bin/env python3
"""loop.json -- the replayed agent fixing loop, from real grade verdicts.

Orders three *existing* media/data/verdict-*.json files (all written by
judge/grade.sh --seed 42 in this sandbox) into the sequence an agent's
iterations would have hit: a bad first attempt, a partly-fixed middle
attempt, then the known-good artifact.  Nothing is synthesised -- each
step only references a verdict file the judge wrote, and the figures and
video label the sequence a **replay** of real grade output, not a live
agent trace.

The stage labels describe the *edit* each mutant is (judge/mutants.py),
so the arrow from one step to the next reads as what the agent changed.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, gates_passed, load_verdict  # noqa: E402

# iteration, verdict file (data/verdict-<name>.json), the real edit the
# artifact is away from examples/good, the replay stage label
STEPS = [
    (1, "no-versions-key", "matrix.yaml: python_versions key deleted",
     "bad -- judge cannot even parse the matrix"),
    (2, "junit-missing", "runner writes the 3.12 cell XML next to the cell",
     "partly fixed -- 4/5 cells covered, gate coverage fails"),
    (3, "good", "the known-good artifact (examples/good)",
     "good -- all gates pass"),
]


def main():
    out = []
    for it, name, edit, stage in STEPS:
        v = load_verdict(name)
        out.append(dict(iteration=it, name=name,
                        artifact=("examples/good" if name == "good"
                                  else "mutant: " + name),
                        edit=edit, stage=stage,
                        verdict=v["verdict"],
                        gates_passed=gates_passed(v),
                        gates_failed=[k for k, g in v["gates"].items()
                                      if not g["pass"]],
                        replay=True))
    path = os.path.join(DATA, "loop.json")
    with open(path, "w") as fh:
        json.dump(dict(note=("replay of real judge/grade.sh verdicts "
                             "(media/data/verdict-*.json), reordered bad -> "
                             "partly fixed -> good; not a live agent trace"),
                       steps=out), fh, indent=2)
        fh.write("\n")
    print("wrote", path)
    for s in out:
        print("  it %d %-16s %d/8 gates  %s" % (s["iteration"], s["name"],
                                                s["gates_passed"], s["stage"]))


if __name__ == "__main__":
    main()
