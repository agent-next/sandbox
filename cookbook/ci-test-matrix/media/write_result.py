#!/usr/bin/env python3
"""result.json -- the demo result manifest, from the real grade JSON.

Builds media/result.json (schema agent-next/result@1) from
media/data/verdict-good.json (judge/grade.sh examples/good --seed 42) and
media/data/selftest.log (judge/selftest.sh).  Validates through
cookbook/tools/result.py's own writer, so a manifest the schema rejects
cannot be committed.
"""
import json
import os
import subprocess
import sys

MEDIA = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(MEDIA)
REPO = os.path.dirname(os.path.dirname(DEMO))
sys.path.insert(0, os.path.join(REPO, "cookbook", "tools"))

from common import GATES, GATE_RULES  # noqa: E402

import result  # cookbook/tools/result.py  # noqa: E402

ASK_AGENT = """Set up a sandbox and solve the demo in \
`cookbook/ci-test-matrix/` of https://github.com/agent-next/sandbox (clone \
it first). Run `bash cookbook/ci-test-matrix/judge/setup.sh`, read \
`cookbook/ci-test-matrix/SPEC.md`, then design the artifact yourself: a \
`matrix.yaml` naming the cells, the fixture, the toggle and the JUnit \
directory, plus a `run_matrix.py` that runs the fixture suite under each \
version in its own uv-managed interpreter, writes one JUnit XML file per \
cell, aggregates them into a matrix table, and exits non-zero when any \
cell fails. Iterate with `bash cookbook/ci-test-matrix/judge/grade.sh \
<your-dir> --json v.json` until it exits 0, then paste the final verdict \
JSON. Do not edit anything under `judge/`; if you believe the judge is \
wrong, say so instead of working around it. Kill the sandbox when you are \
done."""


def main():
    with open(os.path.join(MEDIA, "data", "verdict-good.json")) as fh:
        v = json.load(fh)
    if v["verdict"] != "PASS":
        raise SystemExit("write_result: verdict-good.json is not PASS")
    m = v["metrics"]
    cells = m["cells"]
    with open(os.path.join(MEDIA, "data", "selftest.log")) as fh:
        text = fh.read()
    import re
    km = re.search(r"kill rate: (\d+)/(\d+)", text)
    if not km:
        raise SystemExit("write_result: no kill rate in selftest.log")
    kill = "%s/%s (%d%%)" % (km.group(1), km.group(2),
                             100 * int(km.group(1)) // int(km.group(2)))
    stamps = ", ".join("%s=%s" % (k, cells[k]["stamp"]) for k in
                       m["versions"])
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                          capture_output=True, text=True,
                          check=True).stdout.strip()

    result.write_result(
        os.path.join(MEDIA, "result.json"),
        root=DEMO,
        demo="ci-test-matrix",
        headline=("The known-good matrix runner passes all %d judge "
                  "gates -- exactly the 3.9 cell fails (the fixture's "
                  "match-syntax SyntaxError below CPython 3.10), %d tests "
                  "per cell under five distinct interpreters, and the "
                  "self-test kills %s mutants."
                  % (len(v["gates"]), m["tests_per_cell"], kill)),
        verdict="PASS",
        gates=[{"name": g,
                "pass": v["gates"][g]["pass"],
                "measured": v["gates"][g]["detail"],
                "threshold": GATE_RULES[g]} for g in GATES],
        numbers=[
            {"label": "Failing cell (toggle on)",
             "value": "3.9 (match-syntax SyntaxError)",
             "unit": "",
             "source": "judge/grade.sh examples/good --seed 42 --json "
                       "media/data/verdict-good.json"},
            {"label": "Tests per cell", "value": m["tests_per_cell"],
             "unit": "tests",
             "source": "judge/grade.sh examples/good --seed 42 --json "
                       "media/data/verdict-good.json"},
            {"label": "Interpreter stamps", "value": stamps, "unit": "",
             "source": "judge/grade.sh examples/good --seed 42 --json "
                       "media/data/verdict-good.json"},
            {"label": "Exit codes (toggle on / off)",
             "value": "%d / %d" % (m["exit_codes"]["on"],
                                   m["exit_codes"]["off"]),
             "unit": "",
             "source": "judge/grade.sh examples/good --seed 42 --json "
                       "media/data/verdict-good.json"},
            {"label": "Self-test kill rate", "value": kill, "unit": "",
             "source": "judge/selftest.sh (media/data/selftest.log)"},
        ],
        hero={"kind": "image", "path": "media/result.png",
              "caption": "The five matrix cells with their measured "
                         "interpreter stamps and the judge's verdict; the "
                         "3.9 cell fails on the match-syntax SyntaxError, "
                         "the pass line is the CPython-3.10 oracle."},
        gallery=[
            {"kind": "image", "path": "media/loop.png",
             "caption": "The replayed fixing sequence (bad -> partly "
                        "fixed -> good, real grade verdicts) next to the "
                        "self-test kill matrix (9 mutants x 8 gates)."},
            {"kind": "video", "path": "media/demo.mp4",
             "poster": "media/result.png",
             "caption": "The matrix building from the real grade JSON, "
                        "the judge's output streaming, and the 9/9 kill "
                        "matrix."},
        ],
        launch={"command": "python3 cookbook/ci-test-matrix/run.py",
                "ask_agent": ASK_AGENT},
        receipt="RECEIPT.md",
        sandbox_commit=head,
    )
    print("wrote", os.path.join(MEDIA, "result.json"))


if __name__ == "__main__":
    main()
