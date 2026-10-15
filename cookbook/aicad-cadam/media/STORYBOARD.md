# STORYBOARD — aicad-cadam demo.mp4 (v0)

Slot table per cookbook/DEMO-STANDARD.md, written before the video is cut.
Every frame is real output: meshes loaded from the shipped
`examples/good/<case>/part.stl` and rendered headless by the pinned
pyrender 0.1.45 / OSMesa stack (media/render.py — the frames are true
renders, never a matplotlib animation); every number on screen is read
from the verdict JSONs `media/data/*.json` written by `judge/grade.sh` /
`judge/selftest.sh` in this run (regenerate them with
`media/rerun_judge.sh`). The matrix and result cards are drawn at video
scale from the same JSONs by `media/make_frames.py`. Total 37 s at
30 fps, 1920x1080.

| slot | seconds | what fills the frame | source data | caption (burned in, 48 px) |
|---|---|---|---|---|
| hook | 0.0–4.0 | The three real parts (bushing, plate, bracket STLs) spinning on a dark stage, palette slots 1–3 | `examples/good/*/part.stl` | "text → OpenSCAD → STL / STEP / DXF, judged to 0.05 mm" |
| source→part | 4.0–12.0 | Left: the plate's real `part.scad` verbatim. Right: the plate turntable; gate lines (volume Δ, XOR limit, STEP validity) over a dark panel | `examples/good/plate/part.scad`, `media/data/good_plate.json` | "the agent writes the source — the pinned engine compiles it; the judge re-exports and measures" |
| part | 12.0–16.0 | Bushing turntable + its measured gate lines (volume, XOR, face radii, radial wall) | `media/data/good_bushing.json` | "bushing: every gate measured — 12/12 pass" |
| part | 16.0–20.0 | Bracket turntable + measured gate lines | `media/data/good_bracket.json` | "bracket: every gate measured — 12/12 pass" |
| proof | 20.0–27.0 | Kill matrix at video scale: 3 known-good + 11 single-edit mutants × 14 gates, ✓/✗ per cell, measured-vs-limit evidence column, kill-rate pills | `media/data/{good_*,mutant_*}.json`, `media/data/selftest.log` | "verdicts: media/data/*.json — mutants are single edits of the good parts (judge/mutants.py)" |
| result | 27.0–34.0 | The three parts re-rendered at video scale, each with its gate lines and pass pill | `media/data/good_*.json` | "STL / STEP / DXF graded against analytic volumes, an OCCT reference solid and feature readback" |
| end card | 34.0–37.0 | Static dark card, the one-command run | README one-command run | "python3 cookbook/aicad-cadam/run.py" |

Craft checks against the standard: scene cuts at 0.0 / 4.0 / 12.0 /
16.0 / 20.0 / 27.0 / 34.0 s = 7 cuts in 37 s ≈ 1.9 per 10 s (≥ 0.8);
captions 48 px ≥ 44 px on 1080; the physical thing — real CAD meshes —
turntables in four of seven slots; the final 3 s are a static end card;
every on-screen number traces to a verdict JSON recorded in this run.
v0 scope: the OCCT reference-solid overlay and per-mutant STL close-ups
from the earlier draft are deferred — the gate numbers those shots would
carry are already on screen, read from the same JSONs.
