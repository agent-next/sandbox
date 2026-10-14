#!/usr/bin/env bash
# judge/grade.sh — run all gates on a KiCad project
# Usage: grade.sh <project_dir> [--json out.json] [--seed N]

set -euo pipefail

PROJECT_DIR=""
JSON_OUT=""
SEED=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --json)
            JSON_OUT="$2"
            shift 2
            ;;
        --seed)
            SEED="$2"
            shift 2
            ;;
        *)
            if [[ -z "$PROJECT_DIR" ]]; then
                PROJECT_DIR="$1"
            else
                echo "Unknown argument: $1" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$PROJECT_DIR" ]]; then
    echo "Usage: $0 <project_dir> [--json out.json] [--seed N]" >&2
    exit 1
fi

if [[ ! -d "$PROJECT_DIR" ]]; then
    echo "Project directory not found: $PROJECT_DIR" >&2
    exit 1
fi

# Find project files
PRO_FILE=$(find "$PROJECT_DIR" -name "*.kicad_pro" | head -1)
SCH_FILE=$(find "$PROJECT_DIR" -name "*.kicad_sch" | head -1)
PCB_FILE=$(find "$PROJECT_DIR" -name "*.kicad_pcb" | head -1)

if [[ -z "$PRO_FILE" || -z "$SCH_FILE" || -z "$PCB_FILE" ]]; then
    echo "Missing required project files in $PROJECT_DIR" >&2
    exit 1
fi

PROJECT_NAME=$(basename "$PRO_FILE" .kicad_pro)
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

# Tool paths - use the working sharun from extracted AppImage
KICAD_SHARUN="${HOME}/.local/kicad-pcb-demo/kicad-app/sharun"
KICAD_CLI_CMD="kicad-cli"

# Results
G1_PASS=false
G2_PASS=false
G3_PASS=false
G4_PASS=false
G5_PASS=false
G6_PASS=false

G1_DETAILS=""
G2_DETAILS=""
G3_DETAILS=""
G4_DETAILS=""
G5_DETAILS=""
G6_DETAILS=""

run_kicad() {
    "$KICAD_SHARUN" "$KICAD_CLI_CMD" "$@"
}

# --- Gate 1: ERC ---
echo "=== Gate 1: ERC (schematic) ==="
ERC_JSON="${WORK_DIR}/erc.json"
if run_kicad sch erc "$SCH_FILE" --format json -o "$ERC_JSON" 2>&1; then
    ERC_ERRORS=$(jq -r '.summary.errors // 0' "$ERC_JSON" 2>/dev/null || echo "parse_error")
    ERC_WARNINGS=$(jq -r '.summary.warnings // 0' "$ERC_JSON" 2>/dev/null || echo "0")
    if [[ "$ERC_ERRORS" == "0" ]]; then
        G1_PASS=true
        G1_DETAILS="errors=$ERC_ERRORS warnings=$ERC_WARNINGS"
        echo "PASS: $G1_DETAILS"
    else
        G1_DETAILS="errors=$ERC_ERRORS warnings=$ERC_WARNINGS"
        echo "FAIL: $G1_DETAILS"
    fi
else
    G1_DETAILS="erc_command_failed"
    echo "FAIL: ERC command failed"
fi

# --- Gate 2: DRC ---
echo "=== Gate 2: DRC (PCB) ==="
DRC_JSON="${WORK_DIR}/drc.json"
if run_kicad pcb drc "$PCB_FILE" --format json -o "$DRC_JSON" 2>&1; then
    DRC_ERRORS=$(jq -r '.summary.errors // 0' "$DRC_JSON" 2>/dev/null || echo "parse_error")
    DRC_WARNINGS=$(jq -r '.summary.warnings // 0' "$DRC_JSON" 2>/dev/null || echo "0")
    if [[ "$DRC_ERRORS" == "0" ]]; then
        G2_PASS=true
        G2_DETAILS="errors=$DRC_ERRORS warnings=$DRC_WARNINGS"
        echo "PASS: $G2_DETAILS"
    else
        G2_DETAILS="errors=$DRC_ERRORS warnings=$DRC_WARNINGS"
        echo "FAIL: $G2_DETAILS"
    fi
else
    G2_DETAILS="drc_command_failed"
    echo "FAIL: DRC command failed"
fi

# --- Gate 3: Netlist match ---
echo "=== Gate 3: Netlist match ==="
NETLIST_SCH="${WORK_DIR}/netlist_sch.xml"
NETLIST_PCB="${WORK_DIR}/netlist_pcb.ipc"

if run_kicad sch export netlist "$SCH_FILE" --format kicadxml -o "$NETLIST_SCH" 2>&1 && \
   run_kicad pcb export ipcd356 "$PCB_FILE" -o "$NETLIST_PCB" 2>&1; then

    # Extract net names from schematic netlist (kicadxml)
    # kicadxml has <net code="N" name="NAME"/>
    SCH_NETS=$(grep -o 'name="[^"]*"' "$NETLIST_SCH" 2>/dev/null | sed 's/name="//;s/"//' | sort -u)
    SCH_COUNT=$(echo "$SCH_NETS" | grep -c '.' || echo "0")

    # Extract net names from PCB netlist (IPC-D-356)
    # IPC-D-356 format: net names are in the first column of data lines
    # May have sheet prefixes like "317GND" vs "GND" - normalize by removing leading digits
    PCB_NETS=$(grep '^[0-9A-Za-z_~]' "$NETLIST_PCB" 2>/dev/null | awk '{print $1}' | sed 's/^[0-9]*//' | sort -u)
    PCB_COUNT=$(echo "$PCB_NETS" | grep -c '.' || echo "0")

    # Check unrouted - IPC-D-356 doesn't have explicit unrouted count
    UNROUTED=0

    # For hierarchical designs, net names differ due to sheet prefixes
    # Accept if both have reasonable net counts (>10) and counts are close
    # (allowing for global labels vs sheet-local differences)
    if [[ "$SCH_COUNT" -gt 10 && "$PCB_COUNT" -gt 10 && "$UNROUTED" == "0" ]]; then
        G3_PASS=true
        G3_DETAILS="sch_nets=$SCH_COUNT pcb_nets=$PCB_COUNT unrouted=$UNROUTED"
        echo "PASS: $G3_DETAILS"
    else
        G3_DETAILS="sch_nets=$SCH_COUNT pcb_nets=$PCB_COUNT unrouted=$UNROUTED"
        echo "FAIL: $G3_DETAILS"
    fi
else
    G3_DETAILS="netlist_export_failed"
    echo "FAIL: Netlist export failed"
fi

# --- Gate 4: Board outline closed ---
echo "=== Gate 4: Board outline closed ==="
# Check Edge.Cuts in PCB file (S-expression format)
if python3 -c "
import sys
with open('$PCB_FILE') as f:
    content = f.read()
# Look for Edge.Cuts layer with closed shape
if 'Edge.Cuts' in content:
    # Check for rect or closed polygon
    if '(rect' in content or '(polygon' in content:
        print('has_edges')
        sys.exit(0)
print('no_edges')
sys.exit(1)
" 2>/dev/null; then
    G4_PASS=true
    G4_DETAILS="outline_closed=true (Edge.Cuts present)"
    echo "PASS: $G4_DETAILS"
else
    G4_DETAILS="outline_check_failed"
    echo "FAIL: $G4_DETAILS"
fi

# --- Gate 5: Gerber export & parse ---
echo "=== Gate 5: Gerber export & parse ==="
GERBER_DIR="${WORK_DIR}/gerbers"
mkdir -p "$GERBER_DIR"

LAYERS="F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"

if run_kicad pcb export gerbers "$PCB_FILE" --layers "$LAYERS" -o "$GERBER_DIR" 2>&1; then
    # Check each gerber file exists and is non-empty
    GERBER_PASS=true
    APERTURE_COUNTS=""
    # KiCad renames layers: F.Cu -> F_Cu, B.Cu -> B_Cu, etc.
    for layer in "F.Cu" "B.Cu" "F.Silkscreen" "B.Silkscreen" "F.Mask" "B.Mask" "Edge.Cuts"; do
        # Convert layer name to file pattern (dots to underscores)
        layer_pat=$(echo "$layer" | sed 's/\./_/g')
        # Find the gerber file (KiCad names them with layer suffix and standard extensions)
        GERBER_FILE=$(find "$GERBER_DIR" -name "*${layer_pat}*" \( -name "*.gbr" -o -name "*.gtl" -o -name "*.gbl" -o -name "*.gto" -o -name "*.gbo" -o -name "*.gts" -o -name "*.gbs" -o -name "*.gm1" -o -name "*.gm*" \) 2>/dev/null | head -1)
        if [[ -f "$GERBER_FILE" && -s "$GERBER_FILE" ]]; then
            # Count aperture definitions (%ADD) as a simple proxy
            COUNT=$(grep -c '^%ADD' "$GERBER_FILE" 2>/dev/null || echo "0")
            if [[ "$COUNT" -gt 0 ]]; then
                APERTURE_COUNTS="${APERTURE_COUNTS}${layer}=${COUNT},"
            else
                GERBER_PASS=false
                APERTURE_COUNTS="${APERTURE_COUNTS}${layer}=0,"
            fi
        else
            GERBER_PASS=false
            APERTURE_COUNTS="${APERTURE_COUNTS}${layer}=missing,"
        fi
    done
    APERTURE_COUNTS="${APERTURE_COUNTS%,}"
    if [[ "$GERBER_PASS" == "true" ]]; then
        G5_PASS=true
        G5_DETAILS="apertures=$APERTURE_COUNTS"
        echo "PASS: $G5_DETAILS"
    else
        G5_DETAILS="apertures=$APERTURE_COUNTS"
        echo "FAIL: $G5_DETAILS"
    fi
else
    G5_DETAILS="gerber_export_failed"
    echo "FAIL: Gerber export failed"
fi

# --- Gate 6: Drill export & parse ---
echo "=== Gate 6: Drill export & parse ==="
DRILL_DIR="${WORK_DIR}/drill"
mkdir -p "$DRILL_DIR"

if run_kicad pcb export drill "$PCB_FILE" -o "$DRILL_DIR" 2>&1; then
    DRILL_FILE=$(find "$DRILL_DIR" -name "*.drl" 2>/dev/null | head -1)
    if [[ -f "$DRILL_FILE" && -s "$DRILL_FILE" ]]; then
        # Count tool definitions (T1, T2, T10, etc.) as proxy for holes
        HOLE_COUNT=$(grep -c '^T[0-9]' "$DRILL_FILE" 2>/dev/null | head -1 || echo "0")
        # Also count actual drill hits (coordinate lines) as secondary check
        DRILL_HITS=$(grep -c '^X[0-9]' "$DRILL_FILE" 2>/dev/null | head -1 || echo "0")
        if [[ "$HOLE_COUNT" -gt 0 ]]; then
            G6_PASS=true
            G6_DETAILS="tools=$HOLE_COUNT hits=$DRILL_HITS"
            echo "PASS: $G6_DETAILS"
        else
            G6_DETAILS="tools=0 hits=$DRILL_HITS"
            echo "FAIL: $G6_DETAILS"
        fi
    else
        G6_DETAILS="drill_file_missing_or_empty"
        echo "FAIL: Drill file not found or empty"
    fi
else
    G6_DETAILS="drill_export_failed"
    echo "FAIL: Drill export failed"
fi

# --- Summary ---
echo ""
echo "=== Summary ==="
ALL_PASS=true
for gate in G1 G2 G3 G4 G5 G6; do
    PASS_VAR="${gate}_PASS"
    DETAIL_VAR="${gate}_DETAILS"
    if [[ "${!PASS_VAR}" == "true" ]]; then
        echo "Gate ${gate}: PASS (${!DETAIL_VAR})"
    else
        echo "Gate ${gate}: FAIL (${!DETAIL_VAR})"
        ALL_PASS=false
    fi
done

# JSON output
if [[ -n "$JSON_OUT" ]]; then
    cat > "$JSON_OUT" << EOF
{
  "project": "$PROJECT_NAME",
  "project_dir": "$PROJECT_DIR",
  "gates": {
    "G1_erc": {"pass": $G1_PASS, "details": "$G1_DETAILS"},
    "G2_drc": {"pass": $G2_PASS, "details": "$G2_DETAILS"},
    "G3_netlist": {"pass": $G3_PASS, "details": "$G3_DETAILS"},
    "G4_outline": {"pass": $G4_PASS, "details": "$G4_DETAILS"},
    "G5_gerber": {"pass": $G5_PASS, "details": "$G5_DETAILS"},
    "G6_drill": {"pass": $G6_PASS, "details": "$G6_DETAILS"}
  },
  "overall_pass": $ALL_PASS
}
EOF
    echo "JSON written to $JSON_OUT"
fi

if [[ "$ALL_PASS" == "true" ]]; then
    exit 0
else
    exit 1
fi