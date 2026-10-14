#!/usr/bin/env bash
# cookbook/cad-verify-back judge: grade delivered STEP/STL/DXF files.
#
# Usage:
#   bash judge/grade.sh <artifact_dir> [--spec spec.json] [--seed N] [--json out.json]
#
# <artifact_dir> must contain part.step, part.stl and part.dxf (only the
# delivered files; the agent's part.py is never executed).
#
# 1. copies the artifact into a scratch dir (the artifact cannot modify the judge)
# 2. hashes judge/ before and after; any change fails the run
# 3. runs every gate in grade.py
#
# Exit 0 iff every gate passes.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ARTIFACT="${1:-}"
shift || true
[ -n "$ARTIFACT" ] || { echo "usage: grade.sh <artifact_dir> [--spec s.json] [--seed N] [--json out.json]" >&2; exit 1; }
[ -d "$ARTIFACT" ] || { echo "grade: artifact dir not found: $ARTIFACT" >&2; exit 1; }
for f in part.step part.stl part.dxf; do
    [ -f "${ARTIFACT}/$f" ] || { echo "grade: ${ARTIFACT}/$f missing (need part.step, part.stl, part.dxf)" >&2; exit 1; }
done

python3 - <<'EOF' >/dev/null 2>&1 || { echo "grade: cadquery/ezdxf not importable -- run 'bash judge/setup.sh' first" >&2; exit 1; }
import cadquery, ezdxf
EOF

# hash the judge before any artifact content is read (python bytecode
# caches are excluded: they are created by running the judge itself)
JUDGE_HASH_BEFORE="$(find "$HERE" -type f ! -path '*/__pycache__/*' \
                     ! -name 'RECEIPT.md' ! -name 'VERSIONS.txt' \
                     -exec sha256sum {} + | sort | sha256sum)"

# scratch copy so the artifact cannot modify the judge's inputs
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
cp "${ARTIFACT}"/part.step "${ARTIFACT}"/part.stl "${ARTIFACT}"/part.dxf "$SCRATCH"/

# --artifact-name keeps the verdict deterministic: grade.py records this
# label instead of the random scratch directory it actually reads
python3 "${HERE}/grade.py" "$SCRATCH" --artifact-name "$(basename "${ARTIFACT%/}")" "$@"

# the artifact must not have touched the judge (bytecode caches excluded:
# they are created by running the judge itself, not by the artifact)
JUDGE_HASH_AFTER="$(find "$HERE" -type f ! -path '*/__pycache__/*' \
                     ! -name 'RECEIPT.md' ! -name 'VERSIONS.txt' \
                     -exec sha256sum {} + | sort | sha256sum)"
[ "$JUDGE_HASH_BEFORE" = "$JUDGE_HASH_AFTER" ] \
    || { echo "grade: judge sources changed during grading (checksum mismatch)" >&2; exit 1; }

echo "grade: PASS (all gates; judge integrity verified)"
