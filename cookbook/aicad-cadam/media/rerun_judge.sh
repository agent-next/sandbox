#!/usr/bin/env bash
# media/rerun_judge.sh — (re)generate every judge verdict JSON in
# media/data/ with the real pinned judge, and print the summary numbers
# the figures read.
#
# What it runs (all real judge runs, nothing synthesised):
#   judge/setup.sh                    — installs the pinned toolchain
#   judge/selftest.sh                 — good 3/3, kill rate, determinism
#   grade.sh on examples/good/*       — good_{case}.{json,log}
#   grade.sh on each examples/bad/*/  — mutant_{name}.{json,log}
#     (examples/bad is regenerated from judge/mutants.py by selftest.sh)
#   replay_bushing_{1_bad,2_partial,3_good} — a fixing agent's loop on the
#     bushing spec, graded from real artifacts in media/replay_src:
#       1_bad     bore_d 12 -> 15   (fails volume_stl/xor_reference/volume_step)
#       2_partial bore_d 12 -> 13   (fails the same gates, 2x closer)
#       3_good    the shipped good source re-exported by OpenSCAD
#     These are a REPLAY of the loop the README "Ask your agent" prompt
#     describes, not a live agent trace; make_figures.py labels them as such.
#
# Usage: bash media/rerun_judge.sh            (takes ~5 min)

set -euo pipefail
DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="$DEMO/media/data"
OUT=/tmp/aicad-media-replay
rm -rf "$OUT"; mkdir -p "$OUT"

echo "=== judge/setup.sh ==="
bash "$DEMO/judge/setup.sh"

echo ""
echo "=== judge/selftest.sh ==="
bash "$DEMO/judge/selftest.sh" | tee "$DATA/selftest.log"

echo ""
echo "=== grade.sh on the three good cases ==="
for case in bushing plate bracket; do
    bash "$DEMO/judge/grade.sh" "$DEMO/examples/good/$case" \
        --json "$DATA/good_$case.json" >"$DATA/good_$case.log" 2>&1
    echo "  good/$case exit $?"
done

echo ""
echo "=== grade.sh on each mutant (from examples/bad, regenerated above) ==="
for dir_ in "$DEMO/examples/bad"/*/; do
    m="$(basename "$dir_")"
    bash "$DEMO/judge/grade.sh" "$dir_" \
        --json "$DATA/mutant_$m.json" >"$DATA/mutant_$m.log" 2>&1
    echo "  $m exit $?"
done

echo ""
echo "=== replay: fixing-agent loop on the bushing spec ==="
mkdir -p "$DEMO/media/replay_src"
# 1_bad: one-number edit of the good source (the classic first attempt)
cp "$DEMO/examples/good/bushing/part.scad" "$DEMO/media/replay_src/1_bad.scad"
sed -i 's/^bore_d   = 12;/bore_d   = 15;/' "$DEMO/media/replay_src/1_bad.scad"
# 2_partial: a partial fix (bore 13 — still wrong, half the error)
cp "$DEMO/examples/good/bushing/part.scad" "$DEMO/media/replay_src/2_partial.scad"
sed -i 's/^bore_d   = 12;/bore_d   = 13;/' "$DEMO/media/replay_src/2_partial.scad"
# 3_good: the shipped good source, re-exported by the pinned OpenSCAD
cp "$DEMO/examples/good/bushing/part.scad" "$DEMO/media/replay_src/3_good.scad"
mkdir -p "$OUT/replay"
for step in 1_bad 2_partial 3_good; do
    d="$OUT/replay/$step"
    mkdir -p "$d"
    cp "$DEMO/media/replay_src/$step.scad" "$d/part.scad"
    echo '{"case": "bushing"}' > "$d/case.json"
    cp "$DEMO/examples/good/bushing/part.step" "$d/part.step"
    openscad -o "$d/part.stl" "$d/part.scad" 2>/dev/null
    bash "$DEMO/judge/grade.sh" "$d" \
        --json "$DATA/replay_bushing_$step.json" \
        >"$DATA/replay_bushing_$step.log" 2>&1
    echo "  replay_bushing_$step exit $?"
done

echo ""
echo "=== summary (numbers the figures read) ==="
~/.venvs/aicad/bin/python - "$DATA" <<'PY'
import json, os, sys
d = sys.argv[1]
for f in sorted(os.listdir(d)):
    if not f.endswith(".json"):
        continue
    v = json.load(open(os.path.join(d, f)))
    gates = {g["gate"]: g for g in v["gates"]}
    vol = gates.get("volume_stl", {})
    xor_ = gates.get("xor_reference", {})
    failed = [g["gate"] for g in v["gates"] if not g["passed"]]
    print(f"{f:38s} passed={v['passed']!s:5s} "
          f"vol={vol.get('measured_mm3', float('nan')):>10} "
          f"xor={xor_.get('measured_mm3', float('nan')):>8} "
          f"failed={','.join(failed) or '-'}")
PY
echo "done — verdict JSONs in $DATA"
