#!/usr/bin/env bash
# judge/grade.sh — grade a KiCad project against all gates.
#
# Usage: grade.sh <project_dir> [--json out.json]
#
# Runs kicad-cli to produce ERC/DRC JSON, schematic netlist, Gerbers and
# Excellon drill into a private work dir, then calls judge/oracle.py,
# which parses those artifacts independently and emits the verdict.
# Exit 0 iff every gate passes.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_DIR=""
JSON_OUT=""
SEED=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json) JSON_OUT="$2"; shift 2 ;;
        --seed) SEED="$2"; shift 2 ;;
        -*) echo "Unknown flag: $1" >&2; exit 2 ;;
        *)
            if [[ -z "$PROJECT_DIR" ]]; then PROJECT_DIR="$1"
            else echo "Unexpected arg: $1" >&2; exit 2; fi
            shift ;;
    esac
done
[[ -n "$PROJECT_DIR" ]] || { echo "Usage: $0 <project_dir> [--json out.json]" >&2; exit 2; }
[[ -d "$PROJECT_DIR" ]] || { echo "Not a directory: $PROJECT_DIR" >&2; exit 2; }

# Resolve kicad-cli: $KICAD_CLI, PATH, or the setup.sh install
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

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# Grade a copy so the artifact under test is never modified.
cp -a "$PROJECT_DIR" "$WORK/proj"
PROJ="$WORK/proj"

# exactly one of each, at the top level: a copy of another project in a
# subdirectory must not be what gets graded
one() { local f; f=$(find "$PROJ" -maxdepth 1 -name "*.$1")
        [[ $(printf '%s' "$f" | grep -c .) -eq 1 ]] && echo "$f"; }
SCH=$(one kicad_sch); PCB=$(one kicad_pcb); PRO=$(one kicad_pro)
[[ -n "$SCH" && -n "$PCB" && -n "$PRO" ]] || {
    echo "Project needs exactly one .kicad_pro + .kicad_sch + .kicad_pcb at its top level" >&2; exit 2; }

mkdir -p "$WORK/gerbers" "$WORK/drill"
T_START=$(date +%s.%N)

t() { local s=$SECONDS; "$@"; local rc=$?
      echo "    ($((SECONDS - s))s) rc=$rc" >&2; return $rc; }

echo "== kicad-cli: ERC"
t "$CLI" sch erc "$SCH" --format json -o "$WORK/erc.json" --severity-all
echo "== kicad-cli: DRC"
t "$CLI" pcb drc "$PCB" --format json -o "$WORK/drc.json" --severity-all
echo "== kicad-cli: schematic netlist"
t "$CLI" sch export netlist "$SCH" --format kicadxml -o "$WORK/sch.netlist.xml"
echo "== kicad-cli: gerbers"
t "$CLI" pcb export gerbers "$PCB" -o "$WORK/gerbers" \
    --layers F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts
echo "== kicad-cli: drill"
t "$CLI" pcb export drill "$PCB" -o "$WORK/drill"
echo "== oracle"

# Missing artifacts must fail the gate, so pass the paths as-is; oracle.py
# reports oracle_error on any unreadable/missing file.
ORA_ARGS=(--pcb "$PCB" --erc "$WORK/erc.json" --drc "$WORK/drc.json"
          --sch-netlist "$WORK/sch.netlist.xml"
          --gerber-dir "$WORK/gerbers" --drill-dir "$WORK/drill")
[[ -n "$JSON_OUT" ]] && ORA_ARGS+=(--json "$WORK/verdict.json")

python3 "$SCRIPT_DIR/oracle.py" "${ORA_ARGS[@]}"
RC=$?

# Stamp seed + wall time under 'timing'. Per DEMO-STANDARD.md two runs with
# the same seed must give identical verdict JSON except the timing key, so
# nothing else here may vary between runs.
if [[ -n "$JSON_OUT" && -f "$WORK/verdict.json" ]]; then
    ELAPSED=$(python3 -c 'import sys; print(float(sys.argv[1]) - float(sys.argv[2]))' \
              "$(date +%s.%N)" "$T_START")
    python3 - "$WORK/verdict.json" "$JSON_OUT" "$SEED" "$ELAPSED" <<'PY'
import json, sys
src, dst, seed, secs = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
v = json.load(open(src))
v["seed"] = seed
v["timing"] = {"wall_seconds": round(secs, 3)}
with open(dst, "w") as f:
    json.dump(v, f, indent=2, sort_keys=True)
    f.write("\n")
PY
fi
exit $RC
