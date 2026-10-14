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

A directory containing a self-contained KiCad 9 project:

- `<name>.kicad_pro` — project file
- `<name>.kicad_sch` — single-sheet schematic, `lib_symbols` embedded
- `<name>.kicad_pcb` — 2-layer layout (F.Cu / B.Cu)

Reference constraints: board <= 50 x 50 mm, min track/space 0.20 mm,
min via drill 0.30 mm (checker: netclass values in the file, plus the
DRC gate below which fails on violations of the project's own rules).

The known-good example is `examples/good/555-blinker/`
(~80 KB total, no 3D models, no external libraries needed to grade).

## Gates (all must pass; each is a numeric rule)

| Gate | Command / artifact | Pass rule |
|------|--------------------|-----------|
| G1 ERC | `kicad-cli sch erc <sch> --format json -o erc.json --severity-all` | count of `severity=="error"` violations across all `sheets[]` == 0 **and** every reported non-error violation type is in the ERC warning allow-list below |
| G2 DRC | `kicad-cli pcb drc <pcb> --format json -o drc.json --severity-all` | `len(violations)==0` and `len(unconnected_items)==0` |
| G3 Netlist | `kicad-cli sch export netlist <sch> --format kicadxml`; `(net N "name")` decls parsed from the `.kicad_pcb` text | set of schematic net names (sheet prefix stripped) == set of PCB net names; zero `unconnected-*` synthetic nets; `unconnected_items == 0` |
| G4 Outline | `.kicad_pcb` parsed directly | every Edge.Cuts primitive endpoint is shared by >=2 primitives (closed loop), or a self-closing shape (rect/circle) is present |
| G5 Gerbers | `kicad-cli pcb export gerbers <pcb> -o dir --layers F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts` | all 7 layer files exist; each has >=1 `%ADD` aperture and >=1 draw/flash operation; **and** the bounding box of geometry drawn in the Edge.Cuts gerber matches the `.kicad_pcb` Edge.Cuts bounding box to <= 0.1 mm per side (gerber y-axis is inverted vs board coords) |
| G6 Drill | `kicad-cli pcb export drill <pcb> -o dir` | every `thru_hole`/`np_thru_hole` pad and every via in the `.kicad_pcb` has drill > 0; >=1 `.drl` file; >=1 `TnC<d>` tool with d>0; >=1 `X..Y..` hit; every required drill diameter has a matching tool; hits cover the holes the board needs |

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

Overall pass = all six gates pass. `grade.sh` exits 0 / non-zero and
writes a verdict JSON (`--json FILE`) containing per-gate booleans and
the raw numbers above.

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
- generates the mutants in `judge/mutants.py` (single-edit):
  `erc_unconnected_pin`, `erc_power_short`, `erc_off_grid`,
  `netlist_mismatch`, `drc_unconnected`, `drc_short`, `outline_open`,
  `drill_no_tools`,
- each mutant must fail >= 1 gate; kill rate must be >= 90 %,
- `judge/` checksum before and after must be identical.

## Reproduction tolerance

A different agent in a fresh sandbox following `README.md` should
observe, on the known-good example: `overall_pass: true`,
`erc_errors: 0`, `erc_warnings: 19` (all `lib_symbol_issues`),
`drc_violations: 0`, `drc_unconnected_items: 0`,
`unrouted_items: 0`, `open_endpoints: 0`, gerber-vs-board extents
`max_delta_mm: 0.0`, `drill_hits: 11`, `tools: 2`, and 8/8 mutants
killed. Aperture/op counts may differ (+-20 %) if the artifact was
regenerated, since they depend on layout.
