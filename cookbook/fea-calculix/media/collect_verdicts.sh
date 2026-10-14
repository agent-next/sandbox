#!/bin/bash
# Collect the real judge outputs the media is built from.
#   - regenerates the 9 mutants into media/work/mutants/ (judge/mutants.py)
#   - grades known-good + every mutant with grade.sh --seed 42 --json
#     into media/data/verdicts/
#   - reruns judge/selftest.sh, saving output to media/data/selftest.txt
# Requires judge/setup.sh to have run (ccx + gmsh in ~/tools/bin).
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
export PATH="$HOME/tools/bin:$PATH"

command -v ccx  >/dev/null || { echo "ccx missing -- run judge/setup.sh" >&2; exit 1; }
command -v gmsh >/dev/null || { echo "gmsh missing -- run judge/setup.sh" >&2; exit 1; }

mkdir -p "$MEDIA/data/verdicts" "$MEDIA/work/mutants"
python3 "$DEMO/judge/mutants.py" "$MEDIA/work/mutants" >/dev/null

echo "== grade examples/good =="
"$DEMO/judge/grade.sh" "$DEMO/examples/good" --seed 42 \
    --json "$MEDIA/data/verdicts/good.json" >/dev/null \
    && echo "good: PASS" || { echo "good failed" >&2; exit 1; }

# replay order a fixing agent would plausibly hit them in
for m in no-stress-output coarse-mesh load-wrong-dof load-on-ntip \
         propped-tip units-in-metres overload-10x undersized unconverged; do
    echo "== grade mutant $m =="
    if "$DEMO/judge/grade.sh" "$MEDIA/work/mutants/$m" --seed 42 \
            --json "$MEDIA/data/verdicts/$m.json" >/dev/null 2>&1; then
        echo "$m: PASS (unexpected)" >&2; exit 1
    else
        echo "$m: FAIL (expected)"
    fi
done

echo "== selftest =="
bash "$DEMO/judge/selftest.sh" | tee "$MEDIA/data/selftest.txt"
echo "verdicts + selftest log collected in $MEDIA/data"
