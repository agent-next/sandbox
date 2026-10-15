#!/usr/bin/env python3
"""Generate known-bad single-edit mutants of the known-good artifact.

    python3 mutants.py <good-artifact-dir> <out-dir>

Each mutant is a byte-for-byte copy of the good artifact with exactly one
edit, chosen so that a different gate must catch it.  The self-test grades
every mutant and requires each to fail at least one gate; a mutant that
survives means the corresponding gate is not doing its job.

The set covers every gate: G1 (malformed input), G2 (missed defect, wrong
kind, wrong line), G3 (false-positive major on a clean PR), G4 (a test that
passes on the buggy code) and G5 (a test that also fails on the fixed tree).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

# name -> (pr, edit)
#   edit is either a finding edit -- (file, line, severity, kind) of the
#   single finding to replace on that PR -- or ("test", <source>) to replace
#   that PR's test module, or ("test-append", <source>) to append to it.
MUTANTS: dict[str, tuple[int, tuple]] = {
    # G2: the review misses one planted defect entirely.
    "missed-off-by-one": (1, []),
    # G2: right place, wrong defect class.
    "wrong-kind-none-deref": (3, ("orders/store.py", 57, "major", "other")),
    # G2: right defect, reported far from the planted line (> +/- 2).
    "wrong-line-race": (4, ("orders/metrics.py", 40, "major", "race")),
    # G2: the defect is reported but played down below the major threshold.
    "downgraded-sql-injection": (2, ("orders/store.py", 37, "minor",
                                     "sql-injection")),
    # G1: a field the SPEC does not define.
    "invalid-severity": (1, ("orders/pagination.py", 7, "blocker",
                             "off-by-one")),
    # G3: a confident major finding on a clean PR.
    "false-positive-on-clean": (5, ("orders/config.py", 20, "major",
                                    "off-by-one")),
    # G4: the test passes on the buggy code too, so it proves nothing.
    "test-passes-on-buggy": (3, ("test",
                                 '"""A test that never exercises the bug."""\n\n'
                                 "\n"
                                 "def test_nothing():\n"
                                 "    assert True\n")),
    # G5: the test fails on the fixed tree as well.
    "test-fails-on-fixed": (1, ("test",
                                '"""The right check, but always wrong."""\n\n'
                                "\n"
                                "def test_always_fails():\n"
                                "    assert 1 == 2\n")),
    # G5: a collection error is not a failing test (SPEC G4/G5 rules).
    "test-collection-error": (2, ("test",
                                  '"""Imports something that does not exist."""\n'
                                  "\n"
                                  "from orders.not_a_module import nope\n"
                                  "\n"
                                  "\n"
                                  "def test_never_runs():\n"
                                  "    assert nope\n")),
    # G4: a skip is not a failing test either.
    "test-skipped": (4, ("test",
                         '"""Skipped, so it proves nothing."""\n\n'
                         "import pytest\n"
                         "\n"
                         "\n"
                         "@pytest.mark.skip(reason='never runs')\n"
                         "def test_skipped():\n"
                         "    assert False\n")),
}


def build(good: Path, out: Path) -> list[str]:
    names = []
    for name, (pr, edit) in MUTANTS.items():
        dest = out / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(good, dest)
        pr_dir = dest / f"pr{pr}"
        if isinstance(edit, list):
            review = {"pr": pr, "findings": []}
            (pr_dir / "review.json").write_text(
                json.dumps(review, indent=2) + "\n", encoding="utf-8")
        elif edit[0] == "test":
            (pr_dir / "tests" / f"test_pr{pr}.py").write_text(
                edit[1], encoding="utf-8")
        elif edit[0] == "test-append":
            test = pr_dir / "tests" / f"test_pr{pr}.py"
            test.write_text(test.read_text(encoding="utf-8") + edit[1],
                            encoding="utf-8")
        else:
            rel, line, severity, kind = edit
            review = {"pr": pr, "findings": [{
                "file": rel, "line": line, "severity": severity, "kind": kind,
            }]}
            (pr_dir / "review.json").write_text(
                json.dumps(review, indent=2) + "\n", encoding="utf-8")
        names.append(name)
    return names


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mutants.py <good-artifact-dir> <out-dir>", file=sys.stderr)
        return 2
    good, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if not good.is_dir():
        print(f"mutants: {good} is not a directory", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    names = build(good, out)
    print(f"mutants: wrote {len(names)} mutants to {out}")
    for name in names:
        print(f"mutants:   {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
