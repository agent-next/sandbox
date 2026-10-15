# KiCad PCB design check — SPEC

## Goal

Give an agent a small, real PCB-design task inside a disposable sandbox:
design (or repair) a 2-layer KiCad project and prove correctness with an
independent judge. The reference artifact is a **555 astable LED
blinker** designed from scratch in KiCad s-expression format.

## Non-goals

- No simulation of the analog circuit (values, frequency correctness are
  out of scope; connectivity is what the judge checks).
- No 3D models, BOM, pick-and-place, or fabrication output review.
- No multi-sheet or multi-board designs.
- No third-party board content (footprints/symbols are embedded from the
  stock KiCad 9.0.9 libraries by the generators in `tools/`).

## Artifact under test

A directory containing a self-contained KiCad 9 project (exactly one of each
file below, at the top level of the directory):

- `<name>.kicad_pro` — project file
- `<name>.kicad_sch` — single-sheet schematic, `lib_symbols` embedded
- `<name>.kicad_pcb` — 2-layer layout (F.Cu / B.Cu)

Reference constraints: board <= 50 x 50 mm, min track/space 0.20 mm,
min via drill 0.30 mm. These are enforced rules, not advice — G7 below
measures the Edge.Cuts bounding box and reads the netclass values in
the project file, and grading always runs with the judge's pinned rule
severities (the artifact's own `rule_severities`, `drc_exclusions`,
`erc` section and any `.kicad_dru` are overridden in the graded copy).

The known-good example is `examples/good/555-blinker/`
(~80 KB total, no 3D models, no external libraries needed to grade).

## Gates (all must pass; each is a numeric rule)

| Gate | Command / artifact | Pass rule |
|------|--------------------|-----------|
| G1 ERC | `kicad-cli sch erc <sch> --format json -o erc.json --severity-all` | count of `severity=="error"` violations across all `sheets[]` == 0 **and** every reported non-error violation type is in the ERC warning allow-list below |
| G2 DRC | `kicad-cli pcb drc <pcb> --format json -o drc.json --severity-all` | `len(violations)==0` and `len(unconnected_items)==0` |
| G3 Netlist | `kicad-cli sch export netlist <sch> --format kicadxml`; `(net N "name")` decls + per-pad `(net N "name")` parsed from the `.kicad_pcb` text | for every net, the set of `(ref, pin)` in the schematic netlist == the set of `(ref, pad)` on that net in the PCB — comparing only net names would not see a part soldered backwards — with one documented name normalization applied identically to both sides (hierarchical sheet prefix `/.../` dropped); zero `unconnected-*` synthetic nets; `unconnected_items == 0`; the design is the assigned blinker: a 555 timer and an LED are among the schematic parts, and the schematic part references == the PCB footprint references |
| G4 Outline | `.kicad_pcb` parsed directly | no Edge.Cuts line/arc/curve endpoint is left open (each shared by >=2 primitives; `gr_rect`/`gr_circle`/`gr_poly` are inherently closed), and at least one closed loop or self-closing shape is present |
| G5 Gerbers | `kicad-cli pcb export gerbers <pcb> -o dir --layers F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts` | all 7 layer files exist; each has >=1 `%ADD` aperture and >=1 draw (`D01`) or flash (`D03`) operation — a `D02` pen-up move is not geometry; **and** the bounding box of geometry drawn in the Edge.Cuts gerber matches the `.kicad_pcb` Edge.Cuts bounding box to <= 0.1 mm per side (gerber y-axis is inverted vs board coords) |
| G6 Drill | `kicad-cli pcb export drill <pcb> -o dir` | every `thru_hole`/`np_thru_hole` pad and every via in the `.kicad_pcb` has drill > 0; >=1 `.drl` file; >=1 `TnC<d>` tool with d>0; >=1 `X..Y..` hit or `G85` slot cycle; every required drill diameter has a matching tool; hits cover the holes the board needs |
| G7 Limits | `.kicad_pcb` Edge.Cuts + `.kicad_pro` `net_settings` | Edge.Cuts bounding box fits within 50 x 50 mm; every netclass has clearance >= 0.20 mm, track width >= 0.20 mm, via drill >= 0.30 mm |

### ERC warning allow-list (G1)

ERC warnings are design smells; a clean artifact should produce none.
The judge therefore fails G1 on any warning `type` outside this list:

| type | why it is tolerated here |
|------|--------------------------|
| `lib_symbol_issues` | "library X not in the current configuration" — fires once per embedded symbol because the artifact is deliberately self-contained (`lib_symbols` embeds every used symbol; no sym-lib-table or system libraries are needed to grade it) and `kicad-cli` runs headless with no configured library table. Informational only: ERC still resolves connectivity from the embedded symbols, which G3 proves by matching the PCB net set. KiCad's own shipped demos produce the same warning under `kicad-cli`. |

Every other warning type (`endpoint_off_grid`, `pin_not_connected`
warnings, `unconnected_wire_endpoint`, ...) is a real design defect and
fails the gate. The known-good artifact produces exactly the
`lib_symbol_issues` warnings above.

Overall pass = all seven gates pass. `grade.sh` exits 0 / non-zero and
writes a verdict JSON (`--json FILE`) containing per-gate booleans and
the raw numbers above; a verdict that cannot be written is a judge
failure (non-zero exit), never a quiet pass.

## Acceptance oracle

`judge/oracle.py` (Python 3 stdlib only) is the independent checker.
It never re-runs KiCad: it parses the JSON reports, the netlist XML, the
`.kicad_pcb` s-expression, the exported Gerbers and the Excellon file.
"Tool exited 0" is never the acceptance criterion — the exported files
must contain real geometry (apertures, ops, drills, closed outline).

The artifact is graded in a copy, so it cannot modify itself or the
judge; `selftest.sh` checksums `judge/` before and after grading and
requires the sums to match.

## Tools (pinned)

- KiCad 9.0.9, official lite AppImage tarball from the KiCad GitHub
  release mirror, SHA256 `a54c3ff9072da707b360d698f070002dfcc8f557169d2f5993738be02a61e540`
  (release 2025-04-24; > 2 weeks old).
- Python 3 >= 3.10 (stdlib only) for the oracle and mutators.
- `judge/setup.sh` verifies the checksum, extracts the AppImage, and
  writes `judge/VERSIONS.txt` with the measured versions.

## Self-test

`judge/selftest.sh`:

- grades the known-good example twice with the same `--seed`; verdict
  JSONs must be identical except the `timing` key (determinism),
- runs the oracle unit tests (`judge/test_oracle.py`, stdlib unittest
  with in-memory fixtures — one regression per known gate weakness),
- generates the mutants in `judge/mutants.py` (single-edit):
  `erc_unconnected_pin`, `erc_power_short`, `erc_off_grid`,
  `netlist_mismatch`, `led_reversed`, `drc_unconnected`, `drc_short`,
  `drc_rules_off`, `outline_open`, `board_oversize`, `drill_no_tools`,
- each mutant must fail >= 1 gate with a valid failing verdict JSON —
  a grade crash or a missing/unreadable verdict is a selftest failure,
  not a kill; zero mutants generated is a selftest failure; kill rate
  must be >= 90 %,
- `judge/` checksum before and after must be identical.

## Reproduction tolerance

A different agent in a fresh sandbox following `README.md` should
observe, on the known-good example: `overall_pass: true`,
`erc_errors: 0`, `erc_warnings: 19` (all `lib_symbol_issues`),
`drc_violations: 0`, `drc_unconnected_items: 0`,
`unrouted_items: 0`, `open_endpoints: 0`, gerber-vs-board extents
`max_delta_mm: 0.0`, `drill_hits: 11`, `tools: 2`, board size
40 x 30 mm within the 50 mm limit, and 11/11 mutants killed.
Aperture/op counts may differ (+-20 %) if the artifact was
regenerated, since they depend on layout.
