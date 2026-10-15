#!/usr/bin/env python3
"""Generate the bisect-breaking-commit fixture repo (deterministic, seeded).

The fixture is a tiny synthetic "casefile" project: a parser (caseparser.py),
a corpus (corpus.txt), a test suite (test_suite.py) and a version.txt.  The
history is NUM_COMMITS commits; the commit at index PLANTED_INDEX (counting
from the oldest, 0-based) is the planted regression: it changes the parser so
an indented '\\tENDCASE' terminator is silently accepted instead of rejected.

Before the planted commit the suite passes; from the planted commit on it
fails.  The corpus uses clean column-0 keys so the ONLY defect is the indented
terminator -- the planted commit is the sole cause of the failure.

Every commit carries pinned author/committer dates (BASE_DATE + i minutes),
a fixed author and fixed tree content, so any two builds at the same seed
produce byte-identical commit SHAs -- the judge, the sweep sandboxes and the
known-good example can therefore agree on a SHA without sharing state.

Usage: make_fixture.py <outdir> [--revert-planted]
       --revert-planted writes the repo with the planted commit reverted
       (the negative-control fixture: no regression in range).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SEED = 20261015
NUM_COMMITS = 31          # commits 0..30; version.txt holds the number
PLANTED_INDEX = 25        # commit "bump version to 25" is the planted regression
SWEEP_FIRST, SWEEP_LAST = 20, 30   # the suspect range (11 commits, 11 sandboxes)
NUM_CASES = 400
# The suite's settle delay, standing in for real-suite I/O: per-commit cost is
# latency-dominated, as it is for real test suites and sandbox lifecycles.
# This is the latency the parallel sweep overlaps (SPEC.md, "speedup"); 3.0 s
# keeps the G7 speedup gate's >= 2x margin on 2 vCPU when per-commit work also
# pays fixture build + local clone.
SOAK_S = 3.0
# Fixed history clock: base + i minutes, so SHAs are reproducible.
BASE_DATE = "2026-01-01T00:00:00+00:00"

# Good parser: ENDCASE must sit at column 0 (exact match, no strip).
PARSER = '''\
"""casefile parser (fixture).

Splits a file into CASE ... ENDCASE blocks and parses each record's key:value
lines.  An ENDCASE is only accepted when it sits at the start of a line with no
leading whitespace.
"""

BEGIN = "CASE"
END = "ENDCASE"


def parse(text):
    """Return a list of case dicts, one per CASE..ENDCASE block.

    Raises ValueError on a malformed record (bad line, or unterminated case).
    """
    cases = []
    cur = None
    for line in text.splitlines():
        if line == BEGIN:
            cur = {}
            continue
        if line == END:
            if cur is None:
                raise ValueError("ENDCASE without CASE")
            cases.append(cur)
            cur = None
            continue
        if cur is None:
            continue
        # key: value   -- the key must touch the colon, the value is trimmed.
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError("malformed record line: %r" % line)
        if key != key.strip():
            raise ValueError("key has surrounding whitespace: %r" % key)
        cur[key.strip()] = value.strip()
    if cur is not None:
        raise ValueError("unterminated CASE block")
    return cases
'''

# Planted regression: the terminator is compared after .strip(), so an
# indented "\tENDCASE" is silently accepted (the regression).
PARSER_BAD = PARSER.replace(
    "        if line == END:",
    "        if line.strip() == END:",
)

SUITE = '''\
"""Fixture test suite: parse the corpus, expect a clean rejection."""
import sys
import time
from caseparser import parse

SOAK_S = {soak}

# Settle delay standing in for real-suite I/O (fixture docstring): per-commit
# cost is latency-dominated, which is what a parallel sweep overlaps.
time.sleep(SOAK_S)

corpus = open("corpus.txt").read()
try:
    parse(corpus)
except ValueError:
    print("OK: corpus rejected as expected")
    sys.exit(0)
print("FAIL: parser accepted a corpus with indented ENDCASE")
sys.exit(1)
'''

README = """\
# casefile fixture

A tiny synthetic project for the bisect-breaking-commit demo.

- `caseparser.py` -- splits a file into CASE..ENDCASE blocks.
- `corpus.txt`   -- a corpus of CASE records; every 3rd record is terminated
  by an indented `\\tENDCASE` (which this dialect rejects).
- `test_suite.py` -- parses the corpus and expects a clean rejection.

Run the suite: `python3 test_suite.py` (exit 0 = pass, 1 = fail).
"""


def write_corpus(path: Path) -> None:
    """A corpus of CASE records; every 3rd record is terminated by an
    indented '\\tENDCASE' (rejected by this dialect).  Keys are at column 0
    so the indented terminator is the ONLY defect."""
    lines = []
    for i in range(NUM_CASES):
        lines.append("CASE")
        lines.append(f"name: case-{i}")
        lines.append(f"severity: {i % 5}")
        # every 3rd record uses an indented terminator
        lines.append("\tENDCASE" if i % 3 == 0 else "ENDCASE")
    path.write_text("\n".join(lines) + "\n")


def sh(repo: Path, *args: str, env: dict | None = None) -> None:
    run_env = None
    if env:
        run_env = dict(os.environ, **env)
    subprocess.run(["git", *args], cwd=repo, check=True, env=run_env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def commit_date(i: int) -> str:
    """Pinned clock: base + i minutes, so commit SHAs are reproducible."""
    import datetime
    base = datetime.datetime.fromisoformat(BASE_DATE)
    return (base + datetime.timedelta(minutes=i)).isoformat()


def build(outdir: Path, revert_planted: bool) -> str:
    outdir.mkdir(parents=True, exist_ok=True)
    repo = outdir
    sh(repo, "init", "-q")
    sh(repo, "config", "user.email", "fixture@example.com")
    sh(repo, "config", "user.name", "fixture")
    sh(repo, "config", "commit.gpgsign", "false")

    suite = SUITE.format(soak=SOAK_S)
    planted_sha = ""
    for i in range(NUM_COMMITS):
        # version.txt always holds the commit number
        (repo / "version.txt").write_text(f"{i}\n")
        # parser: good until the planted commit, bad from it on
        is_planted = (i == PLANTED_INDEX)
        if revert_planted:
            parser = PARSER
        elif is_planted or (planted_sha and i > PLANTED_INDEX):
            parser = PARSER_BAD
        else:
            parser = PARSER
        (repo / "caseparser.py").write_text(parser)
        (repo / "test_suite.py").write_text(suite)
        (repo / "README.md").write_text(README)
        if i == 0:
            write_corpus(repo / "corpus.txt")
        sh(repo, "add", "-A")
        sh(repo, "commit", "-q", "-m", f"chore: bump version to {i}",
           env={"GIT_AUTHOR_DATE": commit_date(i),
                "GIT_COMMITTER_DATE": commit_date(i)})
        if is_planted and not revert_planted:
            planted_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                capture_output=True, text=True).stdout.strip()

    return planted_sha


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--revert-planted", action="store_true",
                    help="revert the planted commit (negative-control fixture)")
    args = ap.parse_args()
    planted = build(args.outdir, args.revert_planted)
    mode = "reverted" if args.revert_planted else "planted"
    print(f"{mode} bad: {planted or '(none — regression reverted)'}")
    print(f"fixture written to {args.outdir} "
          f"(seed {SEED}, {NUM_COMMITS} commits, sweep range "
          f"{SWEEP_FIRST}..{SWEEP_LAST}, planted at {PLANTED_INDEX})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
