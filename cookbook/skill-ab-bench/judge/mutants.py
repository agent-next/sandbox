#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test by single edits of the good one.

    mutants.py <gooddir> <outdir>

Writes two families under `<outdir>`:

  `records/<name>/results.json`
      Single-edit mutants of `examples/good/results.json`.  Each is a bench
      that got one thing wrong, and each names the gate that must kill it.
      These are graded by the real judge.

  `judge/<name>/`
      A full copy of `judge/` with exactly one edit, used to prove the
      *judge* fails closed: G4 must reject a reference answer that has drifted
      from the oracle, a task with no known-bad reference answers, and a task
      whose oracle cannot be computed at all.  These grade the good artifact
      with a mutated judge.

Every mutant is scripted from the good artifact, so a mutant that stops being
a mutant (an edit that no longer changes anything) is a hard error here rather
than a silent survivor in the self-test.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# record mutants: (name, gate that must kill it, one-line description)
# ---------------------------------------------------------------------------

# The four tasks the no-skill arm answers correctly, and the twelve it does
# not (see judge/gen_inputs.py); the marginal-win mutant needs the split.
EASY = ("kv01", "kv06", "re01", "re08")


def _mut_fabricated_verdict(record: dict) -> str:
    """Flip one hard task's no-skill verdict to passed, answer untouched.

    The classic cheat: report a win the answer does not support.  G3 replays
    the task's verifier on the recorded answer and catches it.
    """
    task = _task(record, "kv02")
    task["noskill"]["passed"] = True
    return "kv02.noskill.passed False -> True (answer left wrong)"


def _mut_shared_answer(record: dict) -> str:
    """Give the no-skill arm the skill arm's answer, keep its wrong verdict.

    The same answer string with two different verdicts means at least one
    verdict was invented.  G2 catches the pair.
    """
    task = _task(record, "kv03")
    task["noskill"]["answer"] = task["skill"]["answer"]
    return "kv03.noskill.answer <- kv03.skill.answer (verdict left False)"


def _mut_dropped_task(record: dict) -> str:
    """Drop one task record: a bench that quietly forgets its failures."""
    before = len(record["tasks"])
    record["tasks"] = [t for t in record["tasks"] if t.get("task_id") != "kv04"]
    return f"tasks: {before} -> {len(record['tasks'])} (kv04 dropped)"


def _mut_arms_swapped(record: dict) -> str:
    """Report the two arms the wrong way round, every task.

    Every answer and every verdict is genuine, so G3 replay is satisfied --
    the record is a faithful experiment read backwards.  Only the effect-size
    gate sees it: the delta becomes -75 pts.
    """
    for task in record["tasks"]:
        for key in ("passed", "answer", "ms"):
            task["skill"][key], task["noskill"][key] = \
                task["noskill"][key], task["skill"][key]
        # The policy labels stay with their arm: the record is a faithful
        # experiment read backwards, not a mislabelled one.
    return "skill <-> noskill answers/verdicts (delta becomes -75 pts)"


def _mut_marginal_win(record: dict) -> str:
    """Let the no-skill arm share 8 hard answers, leaving a 25 pt delta.

    16/16 vs 12/16 is a real 25 pt gap that is *not* significant (Fisher
    p = 0.101), and 8 of the 12 no-skill answers are the skill arm's own, so
    G2 and G3 are both satisfied.  G5 is the gate that refuses to crown it.
    """
    moved = 0
    for task in record["tasks"]:
        if task["task_id"] in EASY:
            continue
        if moved >= 8:
            break
        task["noskill"]["answer"] = task["skill"]["answer"]
        task["noskill"]["passed"] = True
        moved += 1
    return f"noskill adopts {moved} skill answers (16/16 vs 12/16, p=0.101)"


def _mut_significant_placebo(record: dict) -> str:
    """Let the placebo arm inherit 4 skill answers: a placebo that 'works'.

    The placebo moves the pass rate by -31.25 pts against the no-skill arm
    with a CI that excludes 0.  G7 is the gate that refuses to crown a
    placebo.
    """
    moved = 0
    for task in record["tasks"]:
        if task["task_id"] in EASY or moved >= 4:
            continue
        block = dict(task["skill"])
        block["policy"] = task["placebo"]["policy"]   # label stays its own
        task["placebo"] = block
        moved += 1
    return f"placebo adopts {moved} skill answers (noskill-placebo = -31.25 pts)"


def _mut_fabricated_arm(record: dict) -> str:
    """Manufacture the no-skill arm out of answers the real policy never gives.

    The cheat G2 and G3 cannot see: the answers differ from the skill arm's
    (so G2's shared-answer check does not fire) and every verdict is honest
    (so G3 replay agrees), yet the record is evidence about a no-skill arm
    that never existed -- and it manufactures the 75 pt delta the gates then
    reward.  G9 requires the arm's answers to be the ones the corpus defines.
    """
    n = 0
    for i, task in enumerate(record["tasks"]):
        if task["task_id"] in EASY:
            continue
        task["noskill"]["answer"] = f"WRONG-{i}"
        task["noskill"]["passed"] = False
        n += 1
    return (f"noskill answers replaced with {n} fabricated strings "
            f"(verdicts honest, G2/G3 blind)")


def _mut_policy_relabelled(record: dict) -> str:
    """Relabel the placebo arm with the skill arm's policy name.

    A record whose arms are not the arms it claims to have run is not
    evidence about the skill; G1 checks every policy string against its arm.
    """
    task = _task(record, "kv05")
    task["placebo"]["policy"] = record["arms"]["skill"]
    return "kv05.placebo.policy <- arms.skill (label mismatch)"


RECORD_MUTANTS = [
    ("fabricated-verdict", "G3_verifier_replay", _mut_fabricated_verdict),
    ("shared-answer-arms", "G2_arm_isolation", _mut_shared_answer),
    ("dropped-task", "G1_record_shape", _mut_dropped_task),
    ("arms-swapped", "G6_effect_size", _mut_arms_swapped),
    ("marginal-win", "G5_power", _mut_marginal_win),
    ("significant-placebo", "G7_placebo_control", _mut_significant_placebo),
    ("policy-relabelled", "G1_record_shape", _mut_policy_relabelled),
    ("fabricated-arm-answers", "G9_arm_fidelity", _mut_fabricated_arm),
]


# ---------------------------------------------------------------------------
# judge mutants: one edit inside a copy of judge/, graded against the good
# artifact.  All three must be killed by G4 -- a judge that cannot tell a
# task's right answer from a wrong one is not a judge.
# ---------------------------------------------------------------------------

def _judge_reference_drift(judge_dir: Path) -> str:
    path = judge_dir / "reference.json"
    doc = json.loads(path.read_text())
    doc["tasks"]["re04"]["expected"] = "::1"
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return "reference.json: re04.expected -> '::1' (oracle drift)"


def _judge_no_bad_answers(judge_dir: Path) -> str:
    path = judge_dir / "reference.json"
    doc = json.loads(path.read_text())
    doc["tasks"]["kv07"]["bad"] = []
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return "reference.json: kv07.bad -> [] (no known-bad answers)"


def _judge_unverifiable_task(judge_dir: Path) -> str:
    path = judge_dir / "tasks.json"
    doc = json.loads(path.read_text())
    for task in doc["tasks"]:
        if task["task_id"] == "re05":
            task["params"] = {"how": "no_such_technique"}
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return "tasks.json: re05.params.how -> 'no_such_technique' (oracle raises)"


JUDGE_MUTANTS = [
    ("reference-drift", "G4_task_identifiability", _judge_reference_drift),
    ("no-bad-answers", "G4_task_identifiability", _judge_no_bad_answers),
    ("unverifiable-task", "G3_verifier_replay", _judge_unverifiable_task),
]


# ---------------------------------------------------------------------------

def _task(record: dict, task_id: str) -> dict:
    for task in record["tasks"]:
        if task.get("task_id") == task_id:
            return task
    raise SystemExit(f"mutants: no task {task_id!r} in the good record")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mutants.py <gooddir> <outdir>", file=sys.stderr)
        return 2
    good_dir = Path(sys.argv[1])
    outdir = Path(sys.argv[2])
    good_path = good_dir / "results.json"
    if not good_path.is_file():
        print(f"mutants: no results.json in {good_dir}", file=sys.stderr)
        return 2
    good_text = good_path.read_text(encoding="utf-8")
    judge_src = Path(__file__).resolve().parent

    if outdir.exists():
        shutil.rmtree(outdir)
    (outdir / "records").mkdir(parents=True)
    (outdir / "judge").mkdir(parents=True)

    names = []
    for name, gate, fn in RECORD_MUTANTS:
        record = json.loads(good_text)
        note = fn(record)
        text = json.dumps(record, indent=2, sort_keys=True) + "\n"
        if text == good_text:
            print(f"mutants: {name} made no change; the mutant is not a mutant",
                  file=sys.stderr)
            return 1
        dest = outdir / "records" / name
        dest.mkdir()
        (dest / "results.json").write_text(text, encoding="utf-8")
        print(f"mutants: records/{name}/results.json  [{gate}]  {note}")
        names.append(name)

    for name, gate, fn in JUDGE_MUTANTS:
        dest = outdir / "judge" / name
        shutil.copytree(judge_src, dest,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        note = fn(dest)
        print(f"mutants: judge/{name}/  [{gate}]  {note}")
        names.append(f"judge/{name}")

    print(f"mutants: wrote {len(RECORD_MUTANTS)} record mutants and "
          f"{len(JUDGE_MUTANTS)} judge mutants to {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
