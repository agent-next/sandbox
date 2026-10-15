#!/usr/bin/env bash
# sweep/one_commit.sh <index> — what ONE sandbox runs: reposes the fixture at
# the pinned seed (byte-identical SHAs everywhere), checks out commit <index>,
# runs the suite, and prints exactly one JSON line with the receipt:
#   {"index": N, "sha": "...", "passed": true/false, "diff": "<git show>"}
# Run from the demo directory of a clone of this repo (run.py does that).
set -euo pipefail

IDX="${1:?usage: one_commit.sh <commit index>}"
FIXTURE_DIR="${FIXTURE_DIR:-/tmp/fixture}"
HERE="$(cd "$(dirname "$BASH_SOURCE[0]")" && pwd)"

# Repose the fixture at the pinned seed — deterministic SHAs by construction.
python3 -I "$HERE/../fixture/make_fixture.py" "$FIXTURE_DIR" >&2

LAST=$(( $(git -C "$FIXTURE_DIR" rev-list --count HEAD) - 1 ))
W="$(mktemp -d /tmp/one-commit.XXXXXX)"
trap 'rm -rf "$W"' EXIT
git clone -q "$FIXTURE_DIR" "$W/repo"
SHA="$(git -C "$W/repo" rev-parse "HEAD~$((LAST - IDX))")"
git -C "$W/repo" checkout -q "$SHA"

set +e
(cd "$W/repo" && python3 test_suite.py) >&2
RC=$?
set -e

python3 - "$IDX" "$SHA" "$RC" "$FIXTURE_DIR" <<'PY'
import base64, json, subprocess, sys
idx, sha, rc, fixture = (int(sys.argv[1]), sys.argv[2], int(sys.argv[3]),
                         sys.argv[4])
diff = subprocess.run(["git", "-C", fixture, "show", "--format=", sha],
                      check=True, capture_output=True, text=True).stdout
print(json.dumps({"index": idx, "sha": sha, "passed": rc == 0, "diff": diff}))
PY
