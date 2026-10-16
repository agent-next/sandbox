# STORYBOARD.md — omniverse-rtx-scenes `demo.mp4`

Written before the video is cut; `media/make_video.py` cuts exactly this
slot table and prints the realised timings next to it. Every frame is real
output from the pinned `run.py` run in `RECEIPT.md`.

| # | slot | time | what fills the frame | source | caption (burned, ≥4 % frame height) |
|---|------|------|----------------------|--------|------------------------------------|
| 1 | hook | 0–1 s | the best finished RTX hero frame, full screen — the payoff, no title card | `out/frames/arm/*.png` (lease render) | "RTX path tracing on a disposable GPU" / "NVIDIA official SimReady scenes · 1920×1080 · 30 fps" |
| 2 | input → output | 1–~9 s | Scene A: warehouse dolly plays forward, 8 s real clip | `out/warehouse.mp4` | "Scene A · UR10 warehouse dolly · 8 s" / "SimReady rack, pallet, crates · RTX path tracer" |
| 3 | escalate | ~9–15 s | Scene B: PhysX crate collapse, real baked trajectory | `out/physics.mp4` | "Scene B · PhysX crate collapse · 6 s" / "baked rigid-body trajectory · RTX path tracer" |
| 4 | escalate | ~15–21 s | Scene C: robot arm hero turntable | `out/arm.mp4` | "Scene C · UR10 hero turntable · 6 s" / "official Isaac Sim UR10 · RTX path tracer" |
| 5 | process | ~21–26 s | `run.py`'s **real stdout**, scrolled as a terminal, labelled "8× speed" — real sandbox id, real MB/s, real render seconds | `out/run.log` | "run.py driving the GPU lease · 8× speed" |
| 6 | proof | ~26–31 s | Scene B **keeps moving** while the judge's verdict and the mutant kill matrix ride on top as a HUD | `out/physics.mp4` + `verdict.json` + `selftest.txt` | panel: "JUDGE PASS" / "silhouette-vs-bbox IoU min X.XXX (≥0.900)" / the 7-mutant kill list |
| 7 | end card | last 3 s | static: `python3 run.py` | generated | (none; the launch line is the frame) |

Craft rules honoured: the only static shot is the end card; slots 2–6 are all
moving real renders or a real terminal log; ≥ 0.8 scene cuts per 10 s comes
from the 7 hard cuts; captions are burned into every non-end-card slot at
≥ 4 % frame height; no matplotlib stand-in for the 3D output (the hero panel
is the renderer's own frame).

Numbers on screen and their sources:

| on screen | comes from |
|-----------|------------|
| scene names, durations | `render/render_job.py` `SCENES` table |
| "8× speed" | the terminal scroll rate in `make_video.py` |
| sandbox id, MB/s, render seconds | `run-receipt.json` (from the real GPU replies) |
| JUDGE PASS | `verdict.json` |
| IoU min | `verdict.json` `G1_silhouette.iou_min` |
| mutant kill list | `selftest.txt` (mutants are single edits of the real frames) |
