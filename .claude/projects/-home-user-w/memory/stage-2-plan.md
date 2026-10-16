---
name: stage-2-plan
description: Stage-2 deliverables status and execution plan for omniverse-rtx-scenes
metadata:
  type: project
---

# Stage 2 — omniverse-rtx-scenes (current state 2026-10-16)

## Already written (committed on sbx/flagship-render-r2)

- `run.py` — stdlib-only CPU→GPU driver (build → create lease → PUT upload → exec render → download → judge → delete + verify 404). Reads SBX_API_URL/SBX_API_KEY (GPU_* fallbacks).
- `render/render_job.py` — runs inside the lease; ovrtx RTX path tracer, wrapper authoring, PyAV mp4, hero pick.
- `judge/grade_frames.py`, `mutate_frames.py`, `project.py`, `validate_scenes.py`, `bake_physics.py` — stage-2 + stage-1 gates.
- `judge/setup.sh`, `grade.sh`, `selftest.sh`, `judge-requirements.txt`, `requirements.txt`, `VERSIONS.txt`.
- `media/make_media.sh`, `make_video.py`, `make_figures.py`, `make_manifest.py`, `STORYBOARD.md`.
- `README.md`, `SPEC.md`, `PRODUCT-FRICTION.md`, `RECEIPT.md` (stage-1 only), `REPRODUCE.md` (pending), `assets.lock.json`, `scenes/`, `build_scenes.py`.

## Still must be PRODUCED (the actual Stage 2 run)

1. Install judge venv (`bash judge/setup.sh`) — needs pip network (usd-core, numpy, Pillow).
2. Build scenes locally (`python3 scenes/build_scenes.py --no-bake`) — downloads ~250 MB NVIDIA assets from HF/S3.
3. **Run `python3 run.py` end-to-end** (RUN 1) — real GPU lease on api.sbx.agent-next.com, render 600 frames, download, judge, delete+verify. This is the big unknown: single 5090 seat may be contended (409 retries up to 45 min), render time unknown.
4. **Run `python3 run.py` a second time** (RUN 2) for RECEIPT.md "two fresh runs".
5. Build media from a real run dir (`bash media/make_media.sh <run_dir>`) → result.png, loop.png, demo.mp4, MANIFEST.json; run video_gate.py on demo.mp4.
6. Fill RECEIPT.md with both verbatim runs; update REPRODUCE.md; media/REVIEW.json (two blind judge verdicts — cannot run external vision models locally; see note).
7. Small commits, push after each passing step. Delete scratch + both test sandboxes before finishing.

## Constraints

- HARD RULE: delete only sandbox ids my own code created in this run; never delete by listing/picking.
- Only files under cookbook/omniverse-rtx-scenes/ may be committed.
- Never commit downloaded assets or rendered frames except shipped media.
- Env: GPU_API_URL=https://api.sbx.agent-next.com, GPU_API_KEY set (read as SBX_API_KEY/GPU_API_KEY).
- No ffmpeg/zstd in the omniverse image → tar.gz bundles + PyAV (F4, already handled in code).
- Seat is single-tenant nvidia.5090; 409 retries.

## Notes / risks

- REPRODUCE.md notes a foreign lease `gl-cafaec-2` held the seat idle since 2026-10-16T04:11Z (F3). May still block creates → 409 retry loop.
- run.py falls back to system python for judge if `~/.venv-omnv-judge` missing → grade_frames needs numpy/PIL/pxr which system python likely lacks → setup.sh is a hard prerequisite.
- media/REVIEW.json requires two vision-model blind judgments; not achievable locally — decide at the end (GOAL_BLOCKED or document limitation).
