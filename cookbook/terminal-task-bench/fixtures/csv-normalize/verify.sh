#!/usr/bin/env bash
# Verifier for task csv-normalize.
#
# Oracle: analytic expectation.  expected.json records the canonical output
# byte-for-byte (sha256) plus every kept row as a literal, computed by the
# generator from the rows it wrote -- not by running the repair.  The
# repaired file is compared against those literals; an "it ran" repair that
# drops a different row set fails on the row comparison.
set -euo pipefail

WORK="${1:?usage: verify.sh <work-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -I - "$WORK" "$HERE/expected.json" <<'PY'
import csv
import hashlib
import io
import json
import os
import sys

work, exp_path = sys.argv[1], sys.argv[2]
exp = json.load(open(exp_path))
out = os.path.join(work, exp["output"])
inp = os.path.join(work, exp["input"])
problems = []


def bad(msg):
    problems.append(msg)
    print("FAIL:", msg)


if not os.path.isfile(out):
    bad(f"{exp['output']} was not written")
    sys.exit(1)

raw = open(out, "rb").read()
text = raw.decode("utf-8")

# 1. shape: LF only, exactly one trailing newline, no blanks or comments
if b"\r" in raw:
    bad("output still contains CR bytes (CRLF not normalized)")
if not text.endswith("\n") or text.endswith("\n\n"):
    bad("output must end with exactly one newline")
lines = text.split("\n")
if lines and lines[-1] == "":
    lines = lines[:-1]
if any(ln.strip() == "" for ln in lines):
    bad("output contains a blank line")
if any(ln.startswith("#") for ln in lines):
    bad("output contains a comment line")
if any(ln != ln.strip() for ln in lines):
    bad("output has leading/trailing whitespace on a line")

# 2. parse it back and compare rows as literals
rows = list(csv.reader(io.StringIO(text)))
if not rows:
    bad("output is empty")
    sys.exit(1)
if rows[0] != exp["header"]:
    bad(f"header is {rows[0]!r}, expected {exp['header']!r}")

want = [[str(c) for c in r] for r in exp["rows"]]
got = rows[1:]
if got != want:
    bad(f"{len(got)} data rows, expected {len(want)}")
    for i, (g, w) in enumerate(zip(got, want)):
        if g != w:
            bad(f"  row {i}: {g!r} != {w!r}")
            break
    if len(got) != len(want):
        only_got = [r for r in got if r not in want]
        only_want = [r for r in want if r not in got]
        if only_got:
            bad(f"  unexpected: {only_got[:3]}")
        if only_want:
            bad(f"  missing:    {only_want[:3]}")

# 3. ordering: ids strictly ascending
ids = []
for row in got:
    if not row or not row[0].lstrip("-").isdigit():
        bad(f"row {row!r} does not start with an integer id")
        continue
    ids.append(int(row[0]))
if ids != sorted(ids):
    bad("rows are not ordered by id")
if len(ids) != len(set(ids)):
    bad("the output has duplicate ids")

# 4. byte-exact against the recorded canonical form
got_sha = hashlib.sha256(raw).hexdigest()
if got_sha != exp["sha256"]:
    bad(f"sha256 {got_sha[:16]}... != canonical {exp['sha256'][:16]}... "
        f"({len(raw)} bytes, canonical {exp['canonical_bytes']})")

# 5. the input must be untouched
if os.path.isfile(inp) and b"\r\n" not in open(inp, "rb").read():
    bad(f"{exp['input']} was modified; normalize, do not overwrite the input")

if problems:
    print(f"csv-normalize: {len(problems)} problem(s)")
    sys.exit(1)
print(f"csv-normalize: OK ({len(want)} rows kept, "
      f"{exp['dropped_ragged']} ragged rows dropped, byte-exact)")
PY
