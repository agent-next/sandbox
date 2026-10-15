#!/usr/bin/env python3
"""Write `judge/reference.json`: the judge's own reference answers per task.

G4 uses this to prove a task is *identifiable*: the reference answer must
pass the task's verifier, and every single-edit near-miss of it must fail.
The answers are computed by `judge/verify.py` -- the judge's independent
oracle -- and the near-misses by `judge/grade.py`'s deterministic single-edit
generator, so the file is a function of the corpus and nothing else.

    gen_reference.py            # writes judge/reference.json
    gen_reference.py --check    # exits non-zero if the file is stale

`setup.sh` runs `--check`, so a corpus edit that is not followed by a
regeneration is caught before a grade runs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

JDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(JDIR))

import grade    # noqa: E402
import verify   # noqa: E402

OUT = JDIR / "reference.json"
MIN_BAD = 3


def build() -> dict:
    with open(JDIR / "tasks.json", encoding="utf-8") as fh:
        tasks = json.load(fh)["tasks"]
    entries = {}
    for task in tasks:
        tid = task["task_id"]
        expected = verify.expected_answer(task)
        if not expected:
            raise SystemExit(f"gen_reference: {tid} has an empty reference "
                             f"answer; the task is not gradeable")
        bad = grade.single_edit_mutations(expected)
        if len(bad) < MIN_BAD:
            raise SystemExit(f"gen_reference: {tid} yields only {len(bad)} "
                             f"single-edit near-misses, want >= {MIN_BAD}")
        # The point of the file: the reference passes and the misses fail.
        if not verify.verify(task, expected):
            raise SystemExit(f"gen_reference: {tid}'s verifier rejects its "
                             f"own reference answer {expected!r}")
        accepted = [b for b in bad if verify.verify(task, b)]
        if accepted:
            raise SystemExit(f"gen_reference: {tid}'s verifier accepts the "
                             f"single-edit answer {accepted[0]!r}")
        entries[tid] = {"expected": expected, "bad": bad}
    return {"schema": "skill-ab-bench/reference/1", "tasks": entries}


def main() -> int:
    check = "--check" in sys.argv[1:]
    reference = build()
    text = json.dumps(reference, indent=2, sort_keys=True) + "\n"
    if check:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if current != text:
            print("gen_reference: judge/reference.json is stale; run "
                  "judge/gen_reference.py", file=sys.stderr)
            return 1
        print(f"gen_reference: judge/reference.json is up to date "
              f"({len(reference['tasks'])} tasks)")
        return 0
    OUT.write_text(text, encoding="utf-8")
    total_bad = sum(len(e["bad"]) for e in reference["tasks"].values())
    print(f"gen_reference: wrote {OUT} ({len(reference['tasks'])} tasks, "
          f"{total_bad} single-edit near-misses, "
          f"{min(len(e['bad']) for e in reference['tasks'].values())}.."
          f"{max(len(e['bad']) for e in reference['tasks'].values())} per task)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
