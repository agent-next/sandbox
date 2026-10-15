#!/usr/bin/env bash
# Prove the judge can fail:
#   1. every known-good artifact passes,
#   2. every known-bad mutant fails at least one gate (kill rate printed),
#   3. two grades with the same seed differ only in the timing key,
#   4. grading leaves judge/ unchanged.
# Exits non-zero if the good artifact fails, the kill rate is below 90 %,
# the verdicts are not deterministic, or the judge tree changed.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
GRADE="$HERE/grade.sh"
VENV_PY="${AICAD_JUDGE_PY:-$HOME/.venvs/aicad-judge/bin/python}"
[ -x "$VENV_PY" ] || { echo "FATAL: run judge/setup.sh first" >&2; exit 2; }

JUDGE_SUM_BEFORE="$(find "$HERE" -type f ! -name VERSIONS.txt -print0 | sort -z | xargs -0 sha256sum | sha256sum)"

echo "== selftest: known-good artifacts =="
GOOD_FAIL=0
for part in bushing plate bracket; do
    if bash "$GRADE" "$ROOT/examples/good/$part" --json "/tmp/aicad-good-$part.json" > /tmp/aicad-good-$part.log 2>&1; then
        vol=$("$VENV_PY" -c "import json;d=json.load(open('/tmp/aicad-good-$part.json'));print('%.2f' % d['gates']['brep']['volume_mm3'])")
        echo "  good/$part PASS (volume ${vol} mm^3)"
    else
        echo "  good/$part FAIL (see /tmp/aicad-good-$part.log)" >&2
        GOOD_FAIL=1
    fi
done
[ "$GOOD_FAIL" -eq 0 ] || exit 1

echo "== selftest: known-bad mutants =="
"$VENV_PY" "$HERE/mutants.py" > /tmp/aicad-mutants.log 2>&1 || { cat /tmp/aicad-mutants.log >&2; exit 1; }
TOTAL=0
KILLED=0
for bad in "$ROOT"/examples/bad/*/; do
    name="$(basename "$bad")"
    ls "$bad"/*.step >/dev/null 2>&1 || continue
    TOTAL=$((TOTAL + 1))
    if bash "$GRADE" "$bad" --json "/tmp/aicad-bad-$name.json" > "/tmp/aicad-bad-$name.log" 2>&1; then
        echo "  MUTANT SURVIVED: $name" >&2
    else
        KILLED=$((KILLED + 1))
        gates=$("$VENV_PY" -c "
import json
d = json.load(open('/tmp/aicad-bad-$name.json'))
print(','.join(sorted(k for k, v in d['gates'].items() if not v['pass'])))")
        echo "  $name killed by: $gates"
    fi
done
if [ "$TOTAL" -lt 5 ]; then
    echo "FATAL: fewer than 5 known-bad mutants were built" >&2
    exit 1
fi
RATE=$(awk "BEGIN{printf \"%.0f\", 100 * $KILLED / $TOTAL}")
echo "kill rate: $KILLED/$TOTAL = ${RATE}%"
[ "$RATE" -ge 90 ] || { echo "FATAL: kill rate below 90 %" >&2; exit 1; }

echo "== selftest: determinism =="
bash "$GRADE" "$ROOT/examples/good/bushing" --json /tmp/aicad-det1.json > /dev/null
bash "$GRADE" "$ROOT/examples/good/bushing" --json /tmp/aicad-det2.json > /dev/null
if ! "$VENV_PY" - <<'PY'
import json, sys
a = json.load(open("/tmp/aicad-det1.json"))
b = json.load(open("/tmp/aicad-det2.json"))
for d in (a, b):
    d.pop("timing", None)
    for g in d["gates"].values():
        g.pop("_s", None)
sys.exit(0 if a == b else 1)
PY
then
    echo "FATAL: two grades with the same seed are not identical" >&2
    exit 1
fi
echo "  two grades identical (excluding timing)"

JUDGE_SUM_AFTER="$(find "$HERE" -type f ! -name VERSIONS.txt -print0 | sort -z | xargs -0 sha256sum | sha256sum)"
if [ "$JUDGE_SUM_BEFORE" != "$JUDGE_SUM_AFTER" ]; then
    echo "FATAL: judge/ changed during selftest" >&2
    exit 1
fi
echo "  judge/ unchanged"
echo "selftest OK"
