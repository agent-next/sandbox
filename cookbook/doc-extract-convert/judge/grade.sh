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
judge_sum() { (cd "$here" && find . -type f ! -name VERSIONS.txt -print0 \
                    | sort -z | xargs -0 sha256sum | sha256sum); }
before="$(judge_sum)"

# -- run the artifact from a scratch copy -----------------------------------
cp -r "$artifact" "$work/artifact"
chmod -R u+w "$work/artifact"

rc=0
python3 "$here/check_gates.py" "$work/artifact" --work "$work/case" "$@" || rc=$?

after="$(judge_sum)"
if [ "$before" != "$after" ]; then
    echo "[grade] ERROR: judge/ changed during grading -- the artifact may have modified the judge" >&2
    exit 2
fi

exit $rc
