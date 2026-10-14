# KiCad PCB Design Check Demo — Specification

## Goal
Verify a small 2-layer KiCad project (schematic + PCB) passes all automated checks:
- ERC (Electrical Rules Check) on schematic: 0 errors
- DRC (Design Rules Check) on PCB: 0 errors
- Netlist from schematic matches PCB (no unrouted nets)
- Board outline is closed
- Gerber + drill export succeeds and parses (aperture/layer counts)
- Known-bad variants each fail at least one gate

## Non-goals
- Full signal-integrity analysis
- 3D model generation
- BOM generation
- Assembly drawings
- Multi-board or flex-rigid designs

## Artifact
A KiCad 9.x project directory containing:
- `<name>.kicad_pro` — project file
- `<name>.kicad_sch` — schematic (single sheet)
- `<name>.kicad_pcb` — PCB layout (2 layers: F.Cu, B.Cu)
- `footprints/` — local footprints if any (prefer built-in libs)
- `sym/` — local symbols if any (prefer built-in libs)

Reference design: **555 LED blinker** (astable multivibrator driving an LED).
- 555 timer (SOIC-8), LED (0805), resistors (0805 × 2), capacitors (0805 × 2), power connector (2-pin JST-PH or similar)
- Netlist: VCC, GND, OUT, THR, TRIG, CTRL, DIS, LED_A, LED_K
- Board size: ≤ 50 × 50 mm, 2-layer, 0.2 mm min track/space, 0.3 mm min via

## Gates (numeric pass rules)

| Gate | Check | Pass rule | Source |
|---|---|---|---|
| G1 | `kicad-cli sch erc --format json` | `summary.errors == 0` | JSON `summary` object |
| G2 | `kicad-cli pcb drc --format json` | `summary.errors == 0` | JSON `summary` object |
| G3 | Netlist match | Schematic netlist nets == PCB nets (set equality); `unrouted == 0` | `kicad-cli pcb export netlist --format json` |
| G4 | Board outline closed | `kicad-cli pcb check --format json` → `outline_closed == true` | JSON |
| G5 | Gerber export | `kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts --format json` succeeds; each layer file parses (aperture count > 0) | `gerbv` or `pygerber` parse |
| G6 | Drill export | `kicad-cli pcb export drill --format json` succeeds; drill file parses (hole count > 0) | `pygerber` parse |

## Acceptance oracle
An independent reference check:
- Parse ERC/DRC JSON directly (no re-run) and assert `errors == 0`
- Netlist equality: sort both net-name lists, compare strings
- Gerber parse: use `pygerber` (pip) to load each file, count apertures ≥ 1
- Drill parse: use `pygerber` to load drill file, count holes ≥ 1
- No KiCad CLI re-invocation in oracle; only file reads

## Known-bad mutants (single-edit, ≥ 5)
1. Deleted track (break a net on PCB)
2. Shorted nets (overlap two net copper pours)
3. Too-thin track (set track width < 0.2 mm DRC rule)
4. Missing footprint (delete a footprint from PCB, keep in schematic)
5. Unconnected pin (leave a pin with no wire in schematic)
6. Open board outline (delete one outline segment)
7. Via too small (via drill < 0.3 mm)

## Tool versions (pinned, ≥ 2 weeks old)
- KiCad 9.0.1 (released 2025-03-15) — official tarball SHA256
- Python 3.11+ (system)
- pygerber ≥ 1.0.0 (pip wheel, pinned version)
- gerbv (Debian package, version recorded)

## Self-test requirements
- Known-good (examples/good/555-blinker/) passes all gates → exit 0
- Each known-bad (examples/bad/* or judge/mutants.py) fails ≥ 1 gate
- Kill rate ≥ 90 % (bad_failing / bad_total × 100)
- Judge never modified by artifact (checksum judge/ before/after)