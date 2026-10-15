# media/ review record

Manual pixel-level review of the generated artifacts, done after
`bash media/make_data.sh && bash media/make_media.sh` on the hardened
judge output (kicad-cli 9.0.9, seed 42). Every figure was opened at
full size; video frames were extracted with
`ffmpeg -i demo.mp4 -vf "select='eq(n,N)'" -vsync vfr` and opened at
1920x1080.

Automated gates: `render.py:check_layout()` rasterises each figure and
fails the build if any text is clipped by the canvas or overlaps
another text — passed on all 2 figures + 11 frames. Additionally
`render.py:sch_text_overlap()` measures the true glyph boxes of every
`stroked-text` group KiCad emits in each schematic SVG and fails on
any shared pixels — passed on the good schematic and all 4 schematic
mutant panels (it flagged 30 overlapping pairs on the pre-fix
schematic: `#PWR0x`/`#FLG0x` references and J1/R/C ref+value text
stacked at the symbol origins; all fixed by re-placing fields at the
stock library anchors and hiding power-symbol references).

## result.png (2400x1200)

- Left panel is the real `kicad-cli pcb render --side top --quality
  high --background opaque` image: green 40x30 mm board with J1, U1
  (NE555), R1-R4, C1, D1 and visible silkscreen — reads as a PCB.
- Right panel is the gate table rendered from `data/good.json`:
  G1 `0 errors, 19 warn (lib_symbol_issues)`, G2 `0 viol, 0 unconn`,
  G3 `7 nets sch==pcb, 0 unrouted`, G4 `closed; 4 items, 0 open`,
  G5 `7/7 layers, extents dmax=0.0 mm`, G6 `2 tools, 11/11 hits,
  0 holes w/o drill`, `overall: PASS`. Cross-checked against the
  JSON — identical.

## loop.png (2400x1200)

- 9 rows (`good` + 8 mutants) x 6 gates (G1..G6); cell colours match
  `data/*.json` verdicts exactly.
- Red cells carry the measured value, e.g. `viol=12 unconn=0`
  (drc_short), `warn endpoint_off_gridx2` (erc_off_grid),
  `errors=1 (pin_to_pin)` + `pcb:VCC` (erc_power_short),
  `errors=1 (pin_not_connected)` + `float=1` (erc_unconnected_pin),
  `sch:TRIGX pcb:TRIG` (netlist_mismatch), `open=2 closed=False`
  (outline_open), `unrouted=1` (drc_unconnected), and for
  drill_no_tools both `viol=2 unconn=0` (G2) and `no drill pads=2
  vias=9` (G6 — the board's holes have no drills; KiCad still emits a
  fallback 0.4 mm via tool, which is why hit/tool counts alone never
  caught it).
- Header shows kill rate 8/8 = 100 % vs the >= 90 % requirement.

## demo.mp4 (1920x1080, 30 fps, 46 s, 0.87 MB — ffprobe-verified)

Frames inspected at full size:

- n=30 — intro: title + real 3D board render, no slide-only text.
- n=160 — grading frame: real `pcb export svg` render (F.Cu/B.Cu/
  F.SilkS/Edge.Cuts) beside the measured gate table; all-green gate
  chips along the bottom.
- n=320 — mutant 1/8 `drc_short`: good vs mutant board,
  `DRC error: tracks_crossing (2 marked)` circled at the shorted VCC
  stub / C1 pad region (items at ~128,120 and ~125.5,117 mm).
- n=440 — mutant 2/8 `drc_unconnected`: `unconnected_items (2 marked)`
  circled at R1 pad 2 (128, 110.09) and the orphaned VCC track end
  (128, 106) — coordinates from `data/drc_unconnected.drc.json`.
- n=550 — mutant 3/8 `drill_no_tools`: `through_hole_pad_without_hole`
  circled at J1 pad 1; gate chips show G2 **and** G6 red.
- n=630 — mutant 4/8 `erc_off_grid`: schematic before/after,
  `ERC warning: endpoint_off_grid` circled at the moved vertex
  (97.79, 86.41).
- n=870 — mutant 6/8 `erc_unconnected_pin`: `ERC error:
  pin_not_connected` circled at R1 pin 1 (85.09, 96.52 — ERC report
  pos 0.8509/0.9652 x 100 = schematic mm).
- n=1040 — mutant 7/8 `netlist_mismatch`: `renamed net label
  (TRIG -> TRIGX)` circled at the TRIGX label.
- n=1230 — closing kill matrix, all 8 mutants red on >= 1 gate.

Every mutant frame shows the real before/after artifact, the marker
coordinates taken from the raw ERC/DRC JSON, and the per-gate chips
matching the verdict JSON.

## Regeneration provenance

`media/data/` is committed in full (verdict + raw ERC/DRC JSONs +
mutant project copies under `data/mutants/` — text-only KiCad files).
A fresh clone of this branch + `bash judge/setup.sh` +
`bash media/make_media.sh` succeeds end-to-end (verified 2026-10-14;
run output in the task receipt / git history).
