# Storyboard — aicad-freecad-mcp

Fill this in before cutting `demo.mp4`. Slot order and craft rules:
`cookbook/DEMO-STANDARD.md` (Media). Machine check:
`cookbook/tools/video_gate.py`; blind panel verdicts: `media/REVIEW.json`.

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0–2 s | hook — finished real result | the rendered bushing (real FreeCAD mesh, pyrender+OSMesa turntable) filling the frame, warm steel, edges drawn | `examples/good/bushing/bushing.stl`, renderer in `media/tools/render.py` (run by `media/make_media.sh`) | "FreeCAD built this from a 30-line spec — through an MCP server" |
| 2–10 s | input → output | left: the text spec (`specs/bushing.md` key lines, Pillow-rendered); right: the rendered bushing; then plate and bracket renders slide in beside their spec lines | `specs/*.md`; `examples/good/*/ *.stl` renders | "bushing: Ø20 bore, Ø36 hub × 40, Ø60 flange × 8" · "plate: 100×80×10, Ø30 bore, 6×Ø5.5 on R35" · "bracket: L-shape, R8 fillet" |
| 10–35 s | escalate + sandbox run "Nx speed" | MCP tool-call log lines (real driver replay) typing in beside the part each one built; per-part turntable with the build result; mutants: one render shot per mutant with its defect (bore 22, no flange, 5 holes, 3° drift, ×25.4, no fillet, STL gap, flipped facets) and the gate line that killed it | `media/data/mcp_replay.json` (replay of the real `tools/call execute_code_headless` drives), `media/data/bad_*.json` verdicts, `examples/bad/*/` meshes (mutant renders re-built by `make_media.sh` via `judge/mutants.py`) | "agent drives FreeCAD over MCP — execute_code_headless ×4 (replay)" · each mutant: name + "killed by <gates>" (e.g. "bushing_bore_22 — killed by brep, features, stl_topology, xor_reference") |
| proof | judge PASS + mutant kill matrix | big PASS card per part with volume vs analytic and XOR fraction (from verdict JSONs), then the 7×gate kill matrix with measured vs limit, red/green; kill-rate bar 7/7 = 100 % | `media/data/good_*.json`, `media/data/bad_*.json`, `media/loop.png` matrix | "judge: PASS all gates — bushing 42625.13 mm³ (rel 0.0), XOR 3.6e-4 ≤ 1%" · "self-test kill rate: 7/7 = 100%" |
| last 2–3 s | end card — `python3 run.py` | static dark card, the one-line launch | — | "python3 run.py" |

Craft checklist: 16:9 1920×1080 @ 30 fps | 36 s | ≥ 0.8 cuts/10 s (plan ≈ 3/s
achieved via shot changes) | caption cap height ≥ 4 % of frame height (≥ 44 px)
| payoff visible by ≤ 2 s | readable muted on a phone | every number traces
to `media/data/*.json` (same numbers as RECEIPT.md) | every part frame is a
pyrender+OSMesa render of the real FreeCAD-built mesh — no matplotlib in the
video, matplotlib only for the gate-matrix/kill-bar panels in `loop.png`.

Timing plan (36.0 s, cuts marked ✂):

- ✂ 0.0–2.0 hook: bushing turntable filling the frame
- ✂ 2.0–5.5 bushing: spec text → render, MCP line types in
- ✂ 5.5–8.5 plate: spec text → render, MCP line
- ✂ 8.5–11.5 bracket: spec text → render, MCP line
- ✂ 11.5–16.0 all three parts orbiting (the delivered artifact set)
- ✂ 16.0–18.5 mutant bushing_bore_22: defect render + killed-by line
- ✂ 18.5–21.0 mutant plate_hole_count_5: defect render + killed-by
- ✂ 21.0–23.5 mutant bracket_no_fillet: defect render + killed-by
- ✂ 23.5–26.0 mutant plate_hole_drift / plate_scale_25_4 / stl mutants (rapid cut card)
- ✂ 26.0–29.0 proof: three PASS cards with measured numbers
- ✂ 29.0–33.0 kill matrix + kill-rate bar (camera pans over `loop.png` panels)
- ✂ 33.0–36.0 end card: `python3 run.py` (static, last 2 s YDIF ≈ 0)

Every render frame comes from `media/tools/render.py` output (pinned stack:
pyrender 0.1.45, PyOpenGL 3.1.10, libosmesa6 22.3.6-1+deb12u2, trimesh 4.6.6,
numpy 2.2.6, Pillow; fonts DejaVu). Mutant meshes for the defect shots are
rebuilt by `make_media.sh` via `judge/mutants.py` into `examples/bad/` (git
scratch) and rendered the same way.
