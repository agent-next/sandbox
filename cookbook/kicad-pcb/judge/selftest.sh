#!/usr/bin/env bash
# judge/selftest.sh — self-test with known-bad mutants
# Creates single-edit mutants of the good project, runs grade.sh on each,
# and verifies ≥90% kill rate (i.e., at least 5 of 6 mutants fail).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOOD_DIR="${SCRIPT_DIR}/../examples/good/555-blinker"
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

cd "$SCRIPT_DIR"

echo "=== KiCad PCB Demo Self-Test ==="
echo "Good project: $GOOD_DIR"
echo "Work dir: $WORK_DIR"
echo ""

# First, verify good project passes
echo "--- Testing good project (should PASS) ---"
if ./grade.sh "$GOOD_DIR" --json "$WORK_DIR/good.json"; then
    echo "✓ Good project passes all gates"
else
    echo "✗ Good project FAILED - cannot run selftest"
    exit 1
fi

MUTANTS_DIR="${WORK_DIR}/mutants"
mkdir -p "$MUTANTS_DIR"

KILL_COUNT=0
TOTAL_MUTANTS=0

create_mutant() {
    local name="$1"
    local desc="$2"
    local mutant_dir="${MUTANTS_DIR}/${name}"

    cp -r "$GOOD_DIR" "$mutant_dir"
    TOTAL_MUTANTS=$((TOTAL_MUTANTS + 1))

    echo ""
    echo "=== Mutant $TOTAL_MUTANTS: $name ==="
    echo "Description: $desc"

    case "$name" in
        "erc_short_circuit")
            # Create a direct short between VCC and GND in schematic
            # Add a wire connecting VCC net to GND net
            sed -i '/^    )/i\
        (net\n            (code "99")\n            (name "VCC")\n            (node\n                (ref "U1")\n                (pin "8")\n            )\n            (node\n                (ref "U1")\n                (pin "1")\n            )\n        )' "$mutant_dir/555-blinker.kicad_sch"
            ;;

        "drc_overlap")
            # Add a copper zone on F.Cu that overlaps with a pad
            sed -i '/(general/a\
    (zone\n        (net "VCC")\n        (layer "F.Cu")\n        (tstamp "zone_mutant")\n        (hatch edge 0.5)\n        (priority 0)\n        (polygon\n            (pts\n                (xy 45 48)\n                (xy 55 48)\n                (xy 55 50)\n                (xy 45 50)\n            )\n        )\n    )' "$mutant_dir/555-blinker.kicad_pcb"
            ;;

        "netlist_mismatch")
            # Add a net to schematic that doesn't exist in PCB
            # Add a completely new net with a unique name
            sed -i '/^    )/i\
        (net\n            (code "99")\n            (name "MUTANT_NET_ONLY_IN_SCH")\n            (node\n                (ref "U1")\n                (pin "8")\n            )\n        )' "$mutant_dir/555-blinker.kicad_sch"
            ;;

        "outline_missing")
            # Remove ALL Edge.Cuts graphics - no board outline at all
            sed -i '/(gr_draw/,/^    )/d' "$mutant_dir/555-blinker.kicad_pcb"
            ;;

        "gerber_empty_layer")
            # Remove all F.Cu content - move everything to B.Cu
            sed -i 's/(layer "F.Cu")/(layer "B.Cu")/g' "$mutant_dir/555-blinker.kicad_pcb"
            ;;

        "drill_zero_size")
            # Set all drill sizes to 0 - makes drill file have no tools
            sed -i 's/(drill [0-9.]\+)/(drill 0)/g' "$mutant_dir/555-blinker.kicad_pcb"
            ;;
    esac

    # Run grade on mutant
    if ./grade.sh "$mutant_dir" --json "$WORK_DIR/${name}.json" 2>&1 | tail -10; then
        echo "✗ MUTANT SURVIVED (should have failed): $name"
    else
        echo "✓ MUTANT KILLED: $name"
        KILL_COUNT=$((KILL_COUNT + 1))
    fi
}

# Run all mutants
for name in "erc_short_circuit" "drc_overlap" "netlist_mismatch" "outline_missing" "gerber_empty_layer" "drill_zero_size"; do
    case "$name" in
        "erc_short_circuit")
            desc="ERC: direct short between VCC and GND"
            ;;
        "drc_overlap")
            desc="DRC: copper zone overlapping pad"
            ;;
        "netlist_mismatch")
            desc="Netlist: net only in schematic, not in PCB"
            ;;
        "outline_missing")
            desc="Outline: completely remove Edge.Cuts"
            ;;
        "gerber_empty_layer")
            desc="Gerber: move all F.Cu to B.Cu (empty F.Cu)"
            ;;
        "drill_zero_size")
            desc="Drill: set all drill sizes to 0"
            ;;
    esac
    create_mutant "$name" "$desc"
done

# Summary
echo ""
echo "=== Self-Test Summary ==="
echo "Total mutants: $TOTAL_MUTANTS"
echo "Killed: $KILL_COUNT"
KILL_RATE=$((KILL_COUNT * 100 / TOTAL_MUTANTS))
echo "Kill rate: ${KILL_RATE}%"

if [[ $KILL_RATE -ge 90 ]]; then
    echo "✓ SELF-TEST PASSED (kill rate >= 90%)"
    exit 0
else
    echo "✗ SELF-TEST FAILED (kill rate < 90%)"
    exit 1
fi