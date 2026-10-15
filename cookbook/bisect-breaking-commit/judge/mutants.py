#!/usr/bin/env python3
"""Generate the known-bad artifacts (single-edit mutants of examples/good).

Each mutant is ONE edit of the known-good report; the self-test requires
every one of them to fail at least one gate.  Neighbour SHAs are taken from a
fresh fixture build (deterministic by the pinned commit dates), so the
mutants are reproducible.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent
GOOD = DEMO_DIR / "examples" / "good" / "report.json"
BAD_DIR = DEMO_DIR / "examples" / "bad"
MAKE_FIXTURE = DEMO_DIR / "fixture" / "make_fixture.py"
NUM_COMMITS = 31
PLANTED_INDEX = 25


def sha_at(fixture: Path, index: int) -> str:
    depth = (NUM_COMMITS - 1) - index
    rev = f"HEAD~{depth}" if depth else "HEAD"
    out = subprocess.run(["git", "rev-parse", rev], cwd=fixture,
                         check=True, capture_output=True, text=True)
    return out.stdout.strip()


def main() -> int:
    good = json.loads(GOOD.read_text())

    with tempfile.TemporaryDirectory(prefix="mutants-") as td:
        fixture = Path(td) / "fixture"
        subprocess.run([sys.executable, "-I", str(MAKE_FIXTURE), str(fixture)],
                       check=True, capture_output=True, text=True)
        sha_prev = sha_at(fixture, PLANTED_INDEX - 1)
        sha_next = sha_at(fixture, PLANTED_INDEX + 1)

    # name -> single edit
    def edit_wrong_sha_prev(d): d["identified_commit"] = sha_prev
    def edit_wrong_sha_next(d): d["identified_commit"] = sha_next
    def edit_wrong_index(d): d["identified_index"] = PLANTED_INDEX - 1
    def edit_false_evidence(d): d["evidence"]["n_minus_1_passes"] = False
    def edit_true_evidence(d): d["evidence"]["n_fails"] = False
    def edit_trimmed_diff(d): d["diff"] = "\n".join(d["diff"].splitlines()[:-1])
    def edit_invented_speedup(d): d["speedup"] = 1.5
    def edit_one_sandbox(d): d["sandboxes_used"] = 1
    def edit_missing_field(d): del d["evidence"]

    mutants = {
        "wrong_sha_prev": edit_wrong_sha_prev,      # blames N-1
        "wrong_sha_next": edit_wrong_sha_next,      # blames N+1
        "wrong_index": edit_wrong_index,
        "false_evidence_prev": edit_false_evidence,
        "false_evidence_n": edit_true_evidence,
        "trimmed_diff": edit_trimmed_diff,
        "invented_speedup": edit_invented_speedup,  # breaks G2 arithmetic
        "one_sandbox": edit_one_sandbox,            # not one per commit
        "missing_field": edit_missing_field,
    }

    BAD_DIR.mkdir(parents=True, exist_ok=True)
    for name, edit in mutants.items():
        d = json.loads(json.dumps(good))  # deep copy
        edit(d)
        path = BAD_DIR / f"{name}.json"
        path.write_text(json.dumps(d, indent=2) + "\n")
        print(f"mutant {path.name} written")

    print(f"{len(mutants)} mutants in {BAD_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
