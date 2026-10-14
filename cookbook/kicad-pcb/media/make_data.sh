#!/usr/bin/env bash
# media/make_data.sh — regenerate media/data/ from fresh judge runs.
#
# For the known-good example and every scripted mutant this writes:
#   data/<name>.json       verdict JSON from judge/grade.sh (the judge)
#   data/<name>.erc.json   raw `kicad-cli sch erc` report (marker coords)
#   data/<name>.drc.json   raw `kicad-cli pcb drc` report (marker coords)
# and keeps a copy of each mutant project in data/mutants/<name>/ so
# make_media.sh can render the mutated artifacts (gitignored).
#
# Mutants are expected to FAIL the judge; that is not an error here.

set -euo pipefail
cd "$(dirname "$0")/.."                    # cookbook/kicad-pcb/

GOOD=examples/good/555-blinker
DATA=media/data
SEED=42

# Resolve kicad-cli the same way judge/grade.sh does.
if [[ -n "${KICAD_CLI:-}" ]]; then
    CLI="$KICAD_CLI"
elif command -v kicad-cli >/dev/null 2>&1; then
    CLI="kicad-cli"
elif [[ -x "$HOME/.local/kicad-pcb-demo/bin/kicad-cli" ]]; then
    CLI="$HOME/.local/kicad-pcb-demo/bin/kicad-cli"
else
    echo "kicad-cli not found; run judge/setup.sh first" >&2
    exit 2
fi
echo "kicad-cli: $CLI ($("$CLI" --version))"

mkdir -p "$DATA"
rm -f "$DATA"/*.json "$DATA"/*.log
rm -rf "$DATA/mutants"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

python3 judge/mutants.py "$GOOD" "$WORK/mutants"

collect() {
    local name="$1" dir="$2" expect_fail="$3"
    local sch pcb
    sch=$(find "$dir" -name '*.kicad_sch' | head -1)
    pcb=$(find "$dir" -name '*.kicad_pcb' | head -1)
    [[ -n "$sch" && -n "$pcb" ]] || { echo "no project in $dir" >&2; exit 1; }

    echo "== $name: judge"
    local rc=0
    bash judge/grade.sh "$dir" --seed "$SEED" --json "$WORK/$name.json" \
        >"$DATA/$name.log" 2>&1 || rc=$?
    [[ -f "$WORK/$name.json" ]] || {
        echo "grade.sh produced no verdict for $name" >&2; exit 1; }
    if [[ "$expect_fail" == no && $rc -ne 0 ]]; then
        echo "ERROR: $name was expected to pass but failed" >&2; exit 1
    fi
    if [[ "$expect_fail" == yes && $rc -eq 0 ]]; then
        echo "ERROR: mutant $name passed the judge" >&2; exit 1
    fi
    mv "$WORK/$name.json" "$DATA/$name.json"

    echo "== $name: raw ERC/DRC reports (marker coordinates)"
    "$CLI" sch erc "$sch" --format json --severity-all \
        -o "$DATA/$name.erc.json" >/dev/null
    "$CLI" pcb drc "$pcb" --format json --severity-all \
        -o "$DATA/$name.drc.json" >/dev/null
}

collect good "$GOOD" no
mkdir -p "$DATA/mutants"
for mdir in "$WORK/mutants"/*/; do
    name=$(basename "$mdir")
    collect "$name" "$mdir" yes
    cp -a "$mdir" "$DATA/mutants/"
done

rm -f "$DATA"/*.log

python3 - "$DATA" <<'PY'
import json, os, sys
data = sys.argv[1]
names = sorted(f[:-5] for f in os.listdir(data)
               if f.endswith(".json") and not f.endswith((".erc.json", ".drc.json")))
print(f"{len(names)} verdicts:")
for n in names:
    v = json.load(open(os.path.join(data, n + ".json")))
    bad = [g for g, r in v["gates"].items() if not r["pass"]]
    print(f"  {n:<22} {'PASS' if v['overall_pass'] else 'FAIL: ' + ','.join(bad)}")
PY
echo "make_data: done"
