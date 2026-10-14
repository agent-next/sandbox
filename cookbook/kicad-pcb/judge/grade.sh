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
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json) JSON_OUT="$2"; shift 2 ;;
        --seed) shift 2 ;;        # accepted for compatibility; unused
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

SCH=$(find "$PROJ" -name '*.kicad_sch' | head -1)
PCB=$(find "$PROJ" -name '*.kicad_pcb' | head -1)
PRO=$(find "$PROJ" -name '*.kicad_pro' | head -1)
[[ -n "$SCH" && -n "$PCB" && -n "$PRO" ]] || {
    echo "Project needs .kicad_pro + .kicad_sch + .kicad_pcb" >&2; exit 2; }

mkdir -p "$WORK/gerbers" "$WORK/drill"

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
[[ -n "$JSON_OUT" ]] && ORA_ARGS+=(--json "$JSON_OUT")

python3 "$SCRIPT_DIR/oracle.py" "${ORA_ARGS[@]}"
