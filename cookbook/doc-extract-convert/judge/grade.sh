#!/bin/bash
# doc-extract-convert — grade an artifact against every gate.
#
#   judge/grade.sh <artifact_dir> [--seed N] [--json out.json]
#
# Exits 0 only if all gates pass.  One JSON verdict on stdout.
#
# Judge integrity (SPEC "Judge integrity"):
#   * the artifact is copied to a scratch dir and run from there, so it can
#     never execute from a path it can write to inside the judge;
#   * judge/ itself is sha256-summed before and after grading; a difference
#     fails the run (the artifact cannot modify the judge);
#   * the corpus (with its truth) is generated into a fresh scratch dir,
#     and the truth lives outside the pages/ directory the artifact sees.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
artifact="${1:?usage: judge/grade.sh <artifact_dir> [--seed N] [--json out.json]}"
shift || true

artifact="$(cd "$artifact" && pwd)"
if [ ! -f "$artifact/extract.py" ]; then
    echo "[grade] ERROR: $artifact has no extract.py" >&2
    exit 2
fi

work="$(mktemp -d /tmp/docgrade.XXXXXX)"
trap 'rm -rf "$work"' EXIT

# -- judge integrity: checksum judge/ before and after ---------------------
# Byte-code caches and the versions file are written by the interpreter and
# by setup.sh, not by the artifact, so they are excluded: including them made
# the *first* grade.sh call in a fresh clone fail (check_gates.py imports
# fixtures/corrupt, which materialises judge/__pycache__ between the two sums).
# Everything that could be tampered with is still hashed.
judge_sum() { (cd "$here" && find . -type f ! -name '*.pyc' \
                    ! -path '*/__pycache__/*' ! -name VERSIONS.txt \
                    -print0 | sort -z | xargs -0 sha256sum | sha256sum); }
before="$(judge_sum)"

# -- run the artifact from a scratch copy -----------------------------------
cp -r "$artifact" "$work/artifact"
chmod -R u+w "$work/artifact"

# Don't let the judge write .pyc into judge/ either.
export PYTHONDONTWRITEBYTECODE=1

rc=0
python3 "$here/check_gates.py" "$work/artifact" --work "$work/case" "$@" || rc=$?

after="$(judge_sum)"
if [ "$before" != "$after" ]; then
    echo "[grade] ERROR: judge/ changed during grading -- the artifact may have modified the judge" >&2
    exit 2
fi

exit $rc
