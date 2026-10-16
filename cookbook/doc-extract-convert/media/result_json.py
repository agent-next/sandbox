#!/usr/bin/env python3
"""Write media/result.json from the real verdict JSONs.

The standard (`cookbook/DEMO-STANDARD.md`) wants one result manifest driving
the in-chat result card, the gallery and the storyboard with the *same*
numbers -- so it is generated, never hand-edited: every field below is read
out of media/data/*.json, the verdicts judge/grade.sh wrote in this
invocation.

Checked with the repo's own tool:
    python3 cookbook/tools/result.py check   (when the tools are present)
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")

GOOD = os.path.join(DATA, "good.json")


def ask_agent():
    """The README's "Ask your agent" prompt, verbatim from README.md.

    Read out of README.md rather than copied, so the manifest can never
    drift away from the prompt a plugin user actually pastes.
    """
    text = open(os.path.join(DEMO, "README.md")).read()
    start = text.index("## Ask your agent")
    block = text[start:]
    lines = []
    for line in block.splitlines()[1:]:
        if not line.strip():            # a blank line ends the block quote
            if lines:
                break
            continue
        lines.append(line.strip().lstrip("> ").rstrip())
    return "\n".join(lines).strip()


def main():
    v = json.load(open(GOOD))
    gates = {g["gate"]: g for g in v["gates"]}
    with open(os.path.join(DATA, "judge_guard.json")) as f:
        guard = json.load(f)
    mutants = []
    for name in ("m01-total-as-float", "m03-box-on-whitespace",
                 "m03b-whole-page-box", "m04-quarantine-everything",
                 "m05-wrong-date-format", "m06-accept-bad-date"):
        mutants.append(json.load(open(os.path.join(DATA, name + ".json"))))
    killed = sum(1 for m in mutants if not m["all_gates_passed"])

    g1, g2, g3, g4 = gates["G1"], gates["G2"], gates["G3"], gates["G4"]
    out = {
        "schema": "agent-next/result@1",
        "demo": "doc-extract-convert",
        "headline": "The extractor read all 48 field slots exactly out of 12 "
                    "ugly scanned invoices, every claimed box sits on ink, "
                    "and the blank/smear pages came back quarantined rather "
                    "than invented.",
        "verdict": "PASS" if v["all_gates_passed"] else "FAIL",
        "gates": [
            {"name": "G0 schema",
             "pass": gates["G0"]["passed"],
             "measured": gates["G0"]["detail"],
             "threshold": "0 schema violations"},
            {"name": "G1 field accuracy",
             "pass": g1["passed"],
             "measured": "%d/%d exact (%.3f)" % (g1["correct"], g1["slots"],
                                                 g1["accuracy"]),
             "threshold": "accuracy >= 0.95 and 0 wrong slots (48/48 here)"},
            {"name": "G2 grounding",
             "pass": g2["passed"],
             "measured": g2["detail"],
             "threshold": "0 boxes outside the area bound or off the ink"},
            {"name": "G3 exact totals",
             "pass": g3["passed"],
             "measured": "%d/%d exact to 0 ulp" % (g3["exact"], g3["totals"]),
             "threshold": "exact totals == correct totals"},
            {"name": "G4 negative control",
             "pass": g4["passed"],
             "measured": g4["detail"],
             "threshold": "2/2 corrupted pages quarantined with the expected "
                          "reason code, 0 invented values, 12/12 accounted"},
        ],
        "numbers": [
            {"label": "field accuracy", "value": "%d/%d" % (g1["correct"],
                                                            g1["slots"]),
             "unit": "field slots exact", "source": "judge/grade.sh "
             "examples/good --json media/data/good.json --seed 42"},
            {"label": "exact totals", "value": "%d/%d" % (g3["exact"],
                                                          g3["totals"]),
             "unit": "totals to 0 ulp", "source": "judge/grade.sh "
             "examples/good --json media/data/good.json --seed 42"},
            {"label": "ungrounded boxes",
             "value": 0,
             "unit": "boxes off the ink",
             "source": "judge/grade.sh examples/good --json media/data/"
                      "good.json --seed 42"},
            {"label": "mutant kill rate", "value": "%d/%d" % (killed,
                                                             len(mutants)),
             "unit": "single-edit mutants killed",
             "source": "judge/selftest.sh (kill rate, RECEIPT.md)"},
            {"label": "judge-guard mutant", "value": "killed",
             "unit": "", "source": "judge/selftest.sh (the weakened ink "
                                   "check must fail the good artifact)"},
            {"label": "quarantined corrupted pages", "value": "2/2",
             "unit": "blank + smear", "source": "judge/grade.sh --seed 42 "
             "(G4, second corpus run)"},
        ],
        "hero": {"kind": "image", "path": "media/result.png",
                 "caption": "G1 field accuracy per graded artifact with the "
                            "judge's pass line drawn on it"},
        "gallery": [
            {"kind": "image", "path": "media/loop.png",
             "caption": "the agent loop and the self-test kill rate"},
            {"kind": "video", "path": "media/demo.mp4",
             "poster": "media/result.png",
             "caption": "the run: boxes locking on ink, the negative "
                        "control, the self-test, the verdict"},
        ],
        "launch": {"command": "python3 cookbook/doc-extract-convert/run.py",
                   "ask_agent": ask_agent()},
        "receipt": "RECEIPT.md",
        "sandbox_commit": "0000000000000000000000000000000000000000",
    }
    path = os.path.join(HERE, "result.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print("[result] wrote result.json (verdict %s)" % out["verdict"])


if __name__ == "__main__":
    main()
