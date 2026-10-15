# Storyboard — cad-to-usd

Slot order and craft rules: `cookbook/DEMO-STANDARD.md` (Media). Machine
check: `python3 cookbook/tools/video_gate.py media/demo.mp4`; blind panel
verdicts: `media/REVIEW.json`. Filled in before the video was cut; the
render script (`media/render_media.py`, run by `media/make_media.sh`)
follows this table slot for slot.

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0–2 s | hook — finished real result | full-frame shaded 3D render of the converted Futaba servo USD mesh (real triangles from `examples/good/Servo_Futaba_S3003_v6_step.usda`, re-verified by the judge's conversion_script gate), slow turntable | `media/data/meshes.npz` ← pxr read of the judged `.usda`; verdict `media/data/verdict-good.json` seed 42 | "Real CAD → OpenUSD. Checked by an independent kernel." |
| 2–6 s | input -> output (servo) | split frame: left, the real STEP file header (cropped, zoomed, actual bytes of `Servo Futaba S3003 v6.step`); right, the same part's converted USD mesh rotating | `media/data/sources/Servo Futaba S3003 v6.step`; `media/data/meshes.npz` | "in: STEP (NVIDIA RC-Car-CAD)" / "out: .usda — millimetres, Z-up" |
| 6–9.5 s | input -> output (shock tower) | same split, `_ShockTowerFront.stp` and its converted mesh | `media/data/sources/ShockTowerFront/_ShockTowerFront.stp` | "same pipeline, third part" |
| 9.5–13 s | escalate — close-up | close-up turntable of the shock tower mesh (9 meshes, 5,015 triangles from the verdict) | `media/data/meshes.npz`, counts from `media/data/verdict-good.json` | "ShockTowerFront — 9 meshes, 5,015 triangles" |
| 13–22 s | escalate — sandbox run at speed | real terminal capture of the actual judge run (`setup.sh`, `selftest.sh`, `grade.sh examples/good --seed 42`), cropped/zoomed, scrolling the run's real output | `media/data/selftest.log`, `media/data/grade-good.log`, wall times from verdict `timing` | "the judge, run for real — {N}x speed" (N = measured run seconds / segment seconds, printed as measured) |
| 22–24.5 s | proof — verdict | judge verdict card: six gate names each with PASS, from the real verdict JSON | `media/data/verdict-good.json` | "all 6 gates PASS — OpenCASCADE oracle vs USD" |
| 24.5–29 s | proof — kill matrix | mutant kill matrix: 10 mutants, the gate that killed each, 10/10, real selftest output | `media/data/selftest.log` | "self-test: 10/10 mutants killed by a judge gate" |
| 29–32 s | end card — static | static frame, one-command launch + the "Ask your agent" prompt | `README.md` | "$ python3 run.py" |

Checklist: 16:9 1920x1080 @ 30 fps | 32 s (25–60 s) | 8 hard cuts ≈ 2.5/10 s
(>= 0.8) | caption cap height 46 px = 4.3 % of 1080 (>= 4 %) | payoff at
0 s (<= 2 s) | readable muted on a phone | every number traces to
RECEIPT.md (gate names and counts from the verdict JSON, mutant list
from the selftest log, wall times from the verdict `timing` key).

Craft notes: hard cuts only (no crossfades — every slot boundary is a
cut detected by the gate); the first frame is the lit 3D render, not a
title card; the end card is fully static for the last 3 s; the terminal
slot shows only real command output lines at monospace 30 px, zoomed to
the active region.
