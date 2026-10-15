#!/usr/bin/env python3
"""The corpus and the arm policies must agree -- checked, not assumed.

`judge/gen_inputs.py` asserts facts about the arms (this task is hard, that
task is easy) while `judge/arms.py` is what actually answers.  Nothing in the
type system connects the two, and the draft corpus drifted from the policies
in exactly that gap: it pinned a naive answer for `re05` that the naive
pattern did not produce, and the generator could not run.

So this test closes the loop.  It runs all three policies over all 16 tasks
and requires:

  * the skill policy produces the oracle's answer for every task (the skill
    arm's 16/16 is a property of the corpus, not a hope);
  * the no-skill policy produces exactly the pinned `naive_answer` for every
    task (the pinned answers are what the policy does, not what it was
    supposed to do);
  * the `difficulty` flag agrees with whether the no-skill answer passes
    (4 easy, 12 hard -- the split SPEC.md documents);
  * the placebo policy is a real control: it differs from the no-skill policy
    on exactly one task, and passes it;
  * no two arms produce the same answer on a task where their verdicts
    differ -- the invariant G2 checks in the record, checked here in the
    policies that produce it.

Run by `judge/selftest.sh` before anything is graded.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

JDIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(JDIR))

import arms    # noqa: E402
import verify  # noqa: E402

EXPECTED_EASY = ("kv01", "kv06", "re01", "re08")
EXPECTED_HARD = 12
PLACEBO_DIFFERS_ON = ("kv05",)

FAILURES: list[str] = []


def fail(msg: str) -> None:
    print(f"  FAIL {msg}")
    FAILURES.append(msg)


def ok(msg: str) -> None:
    print(f"  ok   {msg}")


def main() -> int:
    with open(JDIR / "tasks.json", encoding="utf-8") as fh:
        tasks = json.load(fh)["tasks"]
    if len(tasks) != 16:
        fail(f"tasks.json has {len(tasks)} tasks, want 16")
        return 1
    techniques = arms.load_skill(JDIR.parent / "examples" / "good" / "skill")

    print("test_corpus: the skill policy reproduces the oracle")
    bad = [t["task_id"] for t in tasks
           if arms.skill_answer(t, techniques) != t["answer"]]
    if bad:
        fail(f"the skill policy misses the oracle on {bad}")
    else:
        ok(f"skill policy == oracle on all {len(tasks)} tasks")

    print("test_corpus: the no-skill policy reproduces the pinned answers")
    bad = [(t["task_id"], arms.noskill_answer(t), t["naive_answer"])
           for t in tasks if arms.noskill_answer(t) != t["naive_answer"]]
    if bad:
        for tid, got, want in bad:
            fail(f"{tid}: no-skill policy answers {got!r}, corpus pins {want!r}")
    else:
        ok("no-skill policy == pinned naive_answer on all 16 tasks")

    print("test_corpus: the difficulty flag matches the verdicts")
    easy, hard = [], []
    for t in tasks:
        passes = verify.verify(t, arms.noskill_answer(t))
        (easy if passes else hard).append(t["task_id"])
        want = (t["difficulty"] == 1)
        if passes != want:
            fail(f"{t['task_id']}: difficulty={t['difficulty']} but the "
                 f"no-skill answer {'passes' if passes else 'fails'}")
    if tuple(sorted(easy)) != tuple(sorted(EXPECTED_EASY)):
        fail(f"easy tasks are {sorted(easy)}, want {sorted(EXPECTED_EASY)}")
    else:
        ok(f"easy tasks are exactly {sorted(easy)}")
    if len(hard) != EXPECTED_HARD:
        fail(f"{len(hard)} hard tasks, want {EXPECTED_HARD}")
    else:
        ok(f"{len(hard)} hard tasks; the skill-no-skill delta is "
           f"{100.0 * len(hard) / len(tasks):.1f} pts")

    print("test_corpus: the placebo is a real control")
    differs = [t["task_id"] for t in tasks
               if arms.placebo_answer(t) != arms.noskill_answer(t)]
    if tuple(sorted(differs)) != tuple(sorted(PLACEBO_DIFFERS_ON)):
        fail(f"the placebo differs from no-skill on {sorted(differs)}, "
             f"want {sorted(PLACEBO_DIFFERS_ON)}")
    else:
        ok(f"placebo differs from no-skill on exactly {sorted(differs)}")
    # Its one rule is allowed to *fix* a task (that is what makes it a control
    # rather than a copy of the no-skill arm) -- but it must never do worse
    # than the no-skill arm, or the placebo would look harmful.
    worse = [t["task_id"] for t in tasks
             if verify.verify(t, arms.noskill_answer(t))
             and not verify.verify(t, arms.placebo_answer(t))]
    if worse:
        fail(f"the placebo loses tasks the no-skill arm passes: {worse}")
    else:
        ok("the placebo never does worse than the no-skill arm")

    print("test_corpus: no arm disagrees with itself across a shared answer")
    clashes = []
    for t in tasks:
        answers = {
            "skill": arms.skill_answer(t, techniques),
            "noskill": arms.noskill_answer(t),
            "placebo": arms.placebo_answer(t),
        }
        verdicts = {arm: verify.verify(t, a) for arm, a in answers.items()}
        for arm in answers:
            for other in answers:
                if arm >= other:
                    continue
                if answers[arm] == answers[other] and \
                        verdicts[arm] != verdicts[other]:
                    clashes.append(f"{t['task_id']}:{arm}/{other}")
    if clashes:
        fail(f"same answer, different verdict across arms: {clashes}")
    else:
        ok("every shared answer across arms has matching verdicts")

    if FAILURES:
        print(f"test_corpus: {len(FAILURES)} FAILURE(S)")
        return 1
    print("test_corpus: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
