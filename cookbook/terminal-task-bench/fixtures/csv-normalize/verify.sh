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
import hashlib
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

# 1. shape: LF only, no CR, exactly one trailing newline, no blank lines
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
if any('"' in ln for ln in lines):
    bad("output still contains quote characters")

# 2. header and rows as literals
if not lines:
    bad("output is empty")
    sys.exit(1)
header = lines[0].split(",")
if header != exp["header"]:
    bad(f"header is {header!r}, expected {exp['header']!r}")

want_rows = [",".join(str(c) for c in r) for r in exp["rows"]]
got_rows = lines[1:]
if got_rows != want_rows:
    bad(f"{len(got_rows)} data rows, expected {len(want_rows)}")
    for i, (g, w) in enumerate(zip(got_rows, want_rows)):
        if g != w:
            bad(f"  row {i}: {g!r} != {w!r}")
            break
    if len(got_rows) != len(want_rows):
        only_got = [r for r in got_rows if r not in want_rows]
        only_want = [r for r in want_rows if r not in got_rows]
        if only_got:
            bad(f"  unexpected: {only_got[:3]}")
        if only_want:
            bad(f"  missing:    {only_want[:3]}")

# 3. ordering: ids strictly ascending
ids = []
for ln in got_rows:
    try:
        ids.append(int(ln.split(",")[0]))
    except ValueError:
        bad(f"row {ln!r} does not start with an integer id")
if ids != sorted(ids):
    bad("rows are not ordered by id")

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
print(f"csv-normalize: OK ({len(want_rows)} rows kept, "
      f"{exp['dropped_ragged']} ragged rows dropped, byte-exact)")
PY
