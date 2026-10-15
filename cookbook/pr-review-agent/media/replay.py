#!/usr/bin/env python3
"""Build the replayed agent-loop artifacts for media/make_media.sh.

    python3 replay.py <good-artifact-dir> <out-dir>

The loop a reviewer actually goes through, as four single-edit steps of the
known-good artifact (each step fixes the gate the previous one failed):

  iter1  only PR 1's defect reported          -> G2 fails (caught 1/4)
  iter2  PRs 1-2 reported                    -> G2 fails (caught 2/4)
  iter3  all 4 reported + a major on clean    -> G3 fails (false positive)
  iter4  the known-good artifact itself       -> PASS

Every iteration keeps the good tests, so only the review gates move.  The
artifacts are derived; the numbers plotted later come from grading them for
real in make_media.sh, never from this script.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

# The false positive iter3 adds to the clean PR 5 -- the same single finding
# judge/mutants.py plants for its false-positive-on-clean mutant, so it is
# known to be shape-valid and to fail exactly G3.
FALSE_POSITIVE = {"file": "orders/config.py", "line": 20,
                  "severity": "major", "kind": "off-by-one"}


def strip_findings(good: Path, out: Path, prs: list[int]) -> None:
    shutil.copytree(good, out)
    for pr in prs:
        review = out / f"pr{pr}" / "review.json"
        review.write_text(json.dumps({"pr": pr, "findings": []}, indent=2)
                          + "\n", encoding="utf-8")


def add_false_positive(good: Path, out: Path, pr: int) -> None:
    shutil.copytree(good, out)
    review = out / f"pr{pr}" / "review.json"
    doc = json.loads(review.read_text(encoding="utf-8"))
    doc["findings"].append(FALSE_POSITIVE)
    review.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: replay.py <good-artifact-dir> <out-dir>",
              file=sys.stderr)
        return 2
    good, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if not good.is_dir():
        print(f"replay: {good} is not a directory", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)

    strip_findings(good, out / "iter1", [2, 3, 4])
    strip_findings(good, out / "iter2", [3, 4])
    add_false_positive(good, out / "iter3", 5)
    shutil.copytree(good, out / "iter4", dirs_exist_ok=True)

    for name in ("iter1", "iter2", "iter3", "iter4"):
        print(f"replay: wrote {out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
