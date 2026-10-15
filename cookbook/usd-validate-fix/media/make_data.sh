#!/usr/bin/env bash
# usd-validate-fix media: produce every judge output the figures and video
# consume, into media/data/ -- the media draws only from these files.
#
#   data/selftest_output.txt            judge/selftest.sh full output
#                                       (kill rate, determinism check)
#   data/grade_good.json                verdict for examples/good (seed below)
#   data/grade_good_replica.json        second run, same seed -- must match
#                                       grade_good.json byte-for-byte after
#                                       removing "timing" (checked here)
#   data/grade_broken.json              verdict for task/traffic_cone_broken
#                                       .usda (the repair's starting state)
#   data/grade_<mutant>.json            verdict for each of the 11 mutants
#   data/mesh_good.json                 the graded good asset's geometry,
#   data/mesh_broken.json               normals, extents, bindings, materials
#                                       (media/extract_mesh.py)
#
# Verdict JSON "artifact" fields are rewritten from the sandbox-absolute
# build path to the repo-relative path; everything else is the judge's
# verbatim output.  mktemp paths in selftest_output.txt become "<tmp>".
#
# Requirements: judge/setup.sh has been run once (pinned venv in $HOME).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
JUDGE="$DEMO/judge"
VENV="$HOME/.usd-validate-fix-venv"
GOOD="$DEMO/examples/good/traffic_cone_fixed.usda"
BROKEN="$DEMO/task/traffic_cone_broken.usda"
DATA="$HERE/data"
SEED="20261015"

[ -x "$VENV/bin/nvidia_usd_validate" ] \
    || { echo "make_data.sh: judge venv missing -- run 'bash judge/setup.sh' first" >&2; exit 1; }

rm -rf "$DATA"
mkdir -p "$DATA"

# 1. self-test: kill rate + determinism, full log
bash "$JUDGE/selftest.sh" > "$DATA/selftest_output.txt" 2>&1
sed -i "s|/tmp/tmp\.[A-Za-z0-9]*|<tmp>|g" "$DATA/selftest_output.txt"
grep -E "kill rate|determinism|selftest: OK" "$DATA/selftest_output.txt"

# 2. known-good graded twice with the same seed (determinism evidence)
bash "$JUDGE/grade.sh" "$GOOD" --seed "$SEED" \
    --json "$DATA/grade_good.json" > /dev/null
bash "$JUDGE/grade.sh" "$GOOD" --seed "$SEED" \
    --json "$DATA/grade_good_replica.json" > /dev/null
python3 -I - "$DATA/grade_good.json" "$DATA/grade_good_replica.json" <<'EOF' \
    || { echo "make_data.sh: determinism FAILED" >&2; exit 1; }
import json, sys
a = json.load(open(sys.argv[1])); a.pop("timing", None)
b = json.load(open(sys.argv[2])); b.pop("timing", None)
raise SystemExit(0 if a == b else 1)
EOF
echo "make_data.sh: determinism PASS (same seed -> identical verdict body)"

# 3. the broken task asset -- the state the agent starts from
if bash "$JUDGE/grade.sh" "$BROKEN" --json "$DATA/grade_broken.json" \
        > /dev/null 2>&1; then
    echo "make_data.sh: broken asset PASSED the judge?!" >&2
    exit 1
fi
echo "make_data.sh: broken asset fails the judge as expected"

# 4. every known-bad mutant, graded
MUTDIR="$(mktemp -d)"
trap 'rm -rf "$MUTDIR"' EXIT
"$VENV/bin/python" -I "$JUDGE/mutants.py" "$GOOD" "$MUTDIR" > /dev/null
for m in "$MUTDIR"/*.usda; do
    name="$(basename "$m" .usda)"
    if bash "$JUDGE/grade.sh" "$m" --json "$DATA/grade_${name}.json" \
            > /dev/null 2>&1; then
        echo "make_data.sh: mutant $name SURVIVED the judge" >&2
        exit 1
    fi
done
echo "make_data.sh: graded $(find "$DATA" -name 'grade_*.json' ! -name '*replica*' ! -name 'grade_good.json' ! -name 'grade_broken.json' | wc -l) mutants, all killed"

# 5. the graded assets' own geometry (what the figures render)
"$VENV/bin/python" -I "$HERE/extract_mesh.py" "$GOOD" "$DATA/mesh_good.json"
"$VENV/bin/python" -I "$HERE/extract_mesh.py" "$BROKEN" "$DATA/mesh_broken.json"

# 6. relativize sandbox-absolute artifact paths in the committed verdicts
python3 -I - "$DATA" "$DEMO" <<'EOF'
import json, os, sys
data, demo = sys.argv[1], sys.argv[2]
for name in os.listdir(data):
    if not (name.startswith("grade_") and name.endswith(".json")):
        continue
    path = os.path.join(data, name)
    with open(path, encoding="utf-8") as fh:
        verdict = json.load(fh)
    art = os.path.abspath(verdict["artifact"])
    if art == os.path.abspath(os.path.join(demo, "examples", "good",
                                           "traffic_cone_fixed.usda")):
        verdict["artifact"] = "examples/good/traffic_cone_fixed.usda"
    elif art == os.path.abspath(os.path.join(demo, "task",
                                             "traffic_cone_broken.usda")):
        verdict["artifact"] = "task/traffic_cone_broken.usda"
    else:
        verdict["artifact"] = "<mutant>/" + os.path.basename(art)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(verdict, fh, indent=1, sort_keys=True)
        fh.write("\n")
EOF

echo "make_data.sh: wrote $DATA:"
ls "$DATA"
