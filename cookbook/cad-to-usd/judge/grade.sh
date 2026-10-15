#!/usr/bin/env bash
# judge/grade.sh <artifact-dir> [--seed N] [--json out.json]
#
# Grades a CAD->USD artifact against the independent OpenCASCADE +
# usd-core oracle. Gates (see SPEC.md):
#   file_set  all three <key>.usda present, distinct, parse as USD
#   stage_meta      metersPerUnit=0.001 (±1e-9), upAxis=Z, defaultPrim valid
#   geometry_counts prim count > 0 and mesh count > 0 per part
#   bbox_match      USD world bbox vs oracle, per-axis endpoint deltas
#                   <= 1% of oracle extent (0.1 mm floor)
#   area_match      total triangle area within 3% of oracle face area
#   conversion_script  convert.sh reproduces all three parts from fresh
#                   sources, each regenerated part passes gates 2-5,
#                   and the judge's converter log proves every pinned
#                   source was actually converted (not copied)
#
# The artifact runs out of process in a scratch copy, and never with the
# judge's python: judge/ and the two pinned venvs are checksummed
# before and after, and the fetched sources are digest-re-verified — a
# mismatch anywhere fails the grade. Exit 0 only if every gate passes.
# Verdict JSON on stdout (and at --json path). Wall times live under
# the "timing" key.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_BASE="${CAD2USD_VENV_BASE:-$HOME/.venvs}"
JUDGE_PY="$VENV_BASE/cad2usd-judge/bin/python"
CONV_BIN="$VENV_BASE/cad2usd-convert/bin/usd-convert-cad"

usage() { echo "usage: judge/grade.sh <artifact-dir> [--seed N] [--json out.json]" >&2; exit 64; }

artifact=""
seed="0"
json_out=""
reconvert="1"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --seed) seed="$2"; shift 2 ;;
        --json) json_out="$2"; shift 2 ;;
        --no-reconvert) reconvert="0"; shift ;; # self-test only: skip gate 6
        -h|--help) usage ;;
        -*) echo "grade.sh: unknown flag $1" >&2; usage ;;
        *)  if [[ -n "$artifact" ]]; then echo "grade.sh: one artifact only" >&2; usage; fi
            artifact="$1"; shift ;;
    esac
done
[[ -n "$artifact" ]] || usage
[[ -x "$JUDGE_PY" && -x "$CONV_BIN" ]] || {
    echo "grade.sh: pinned venvs missing — run judge/setup.sh first" >&2; exit 1; }

# judge integrity: record checksums, compare at the end
JUDGE_SUMS="$(mktemp)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/cad2usd-grade.XXXXXX")"
trap 'rm -rf "$WORK" "$JUDGE_SUMS"' EXIT
(cd "$SCRIPT_DIR" && find . -type f ! -path './.git/*' ! -path '*__pycache__*' -print0 | sort -z |
 xargs -0 sha256sum) > "$JUDGE_SUMS"
# copy artifact; run everything against the copy
cp -r "$artifact" "$WORK/artifact"

# fetch the pinned sources now (before the artifact runs) and digest-check
# them once up front; the same digests are re-verified after grading
bash "$SCRIPT_DIR/fetch_sources.sh" "$WORK" >/dev/null
verify_sources() {
    while IFS='|' read -r sha path key; do
        [[ -z "$sha" || "$sha" == \#* ]] && continue
        echo "$sha  $WORK/sources/$path" | sha256sum -c --quiet - || return 1
    done < "$SCRIPT_DIR/sources.txt"
}
verify_sources || { echo "[grade] ERROR: fetched sources fail their pinned sha256" >&2; exit 1; }

# venv integrity baseline: every file in the two pinned venvs. The
# artifact's convert.sh runs with these venvs reachable; if it changed
# anything in them (sitecustomize, a monkeypatched pxr/OCP, ...), the
# manifest below will differ and the grade fails.
VENV_MANIFEST_BASE="$WORK/venv_before.txt"
find "$VENV_BASE/cad2usd-convert" "$VENV_BASE/cad2usd-judge" \
     -type f -printf '%p %s\n' | sort > "$VENV_MANIFEST_BASE"

# converter shim: the judge hands the artifact $USD_CONVERT_CAD pointing
# at this wrapper, which logs each invocation's input sha256 + output
# path to a judge-owned log. Gate 6 requires one logged conversion per
# pinned source: an artifact that ships pre-made outputs and copies them
# in convert.sh never invokes the converter on the real sources and the
# gate fails. (The log is evidence of conversion, not a secret: what
# actually decides the grade is that every judged quantity is re-derived
# from the regenerated files against the independent oracle.)
CONVERT_LOG="$WORK/convert_invocations.log"
SHIM="$WORK/shim/usd-convert-cad"
mkdir -p "$(dirname "$SHIM")"
cat > "$SHIM" <<EOF
#!/usr/bin/env bash
# converter shim installed by judge/grade.sh; wraps the pinned converter:
#   usd-convert-cad -i <src> -o <out> [flags...]
orig=("\$@")
in=""; out=""
i=0
while [[ \$i -lt \${#orig[@]} ]]; do
    case "\${orig[\$i]}" in
        -i|--input)  in="\${orig[\$((i+1))]}"; i=\$((i+2)) ;;
        -o|--output) out="\${orig[\$((i+1))]}"; i=\$((i+2)) ;;
        *) i=\$((i+1)) ;;
    esac
done
in_sha="\$(sha256sum "\$in" | cut -d' ' -f1)"
printf 'call sha256=%s out=%s\n' "\$in_sha" "\$(basename "\$out")" >> "$CONVERT_LOG"
exec "$CONV_BIN" "\${orig[@]}"
EOF
chmod +x "$SHIM"
: > "$CONVERT_LOG"

echo "[grade] artifact: $artifact  seed: $seed"
set +e
"$JUDGE_PY" -I -B "$SCRIPT_DIR/grade_gates.py" \
    --work "$WORK" --demo "$DEMO_DIR" --seed "$seed" \
    --python "$JUDGE_PY" --converter "$SHIM" \
    --convert-log "$CONVERT_LOG" \
    --reconvert "$reconvert" 2>&1 | sed 's/^/  /'
rc=${PIPESTATUS[0]}
set -e

# judge integrity check (after the artifact ran out of process, in the copy)
(cd "$SCRIPT_DIR" && find . -type f ! -path './.git/*' ! -path '*__pycache__*' -print0 | sort -z |
 xargs -0 sha256sum) | diff -q "$JUDGE_SUMS" - >/dev/null || {
    echo "[grade] ERROR: judge/ changed during grading — failing" >&2
    exit 1
}
# venv integrity: unchanged by the artifact run
find "$VENV_BASE/cad2usd-convert" "$VENV_BASE/cad2usd-judge" \
     -type f -printf '%p %s\n' | sort | diff -q "$VENV_MANIFEST_BASE" - >/dev/null || {
    echo "[grade] ERROR: judge venvs changed during grading — failing" >&2
    exit 1
}
# the fetched sources must be byte-identical to their pinned sha256
verify_sources || {
    echo "[grade] ERROR: source digests changed during grading — failing" >&2
    exit 1
}

verdict="$WORK/verdict.json"
if [[ -f "$verdict" ]]; then
    cat "$verdict"
    [[ -n "$json_out" ]] && cp "$verdict" "$json_out"
else
    echo "[grade] ERROR: no verdict JSON produced" >&2
    exit 1
fi
exit "$rc"
