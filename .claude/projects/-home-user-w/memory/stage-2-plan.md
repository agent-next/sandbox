---
name: stage-2-plan
description: Stage-2 deliverables status and execution plan for omniverse-rtx-scenes
metadata:
  type: project
---

# Stage 2 — omniverse-rtx-scenes (current state 2026-10-16, evening)

## Key discovery (changes the render design)

ovrtx's offline **PathTracing** render mode accumulates up to
`omni:rtx:pt:samplesPerPixel` samples INSIDE one `renderer.step()` and runs
the OptiX denoiser (`omni:rtx:pt:denoising:enabled`, default true) — both are
**RenderProduct USD attributes** authored in `author_wrapper()`, no Python API
(the 0.5.1 binding exposes no denoiser). RealTimePathTracing measured 4.14
s/frame but converged 0%, luma_std ~16 (visibly noisy). Docs:
nvidia-omniverse.github.io/ovrtx/sensors/cameras/render_modes/path_tracing.html
(the site's own /rendermodes/… links 404).

## Pipeline state

- `render/render_job.py` — switched to PathTracing (`--render-mode`, `--spp`,
  `--no-denoise`); rtpt + steps-per-frame kept for sweeps.
- `run.py` — now ONE EXEC PER SCENE (each gets its own 3600 s budget;
  job-result-<scene>.json for the 502-poll path), per-scene `SCENE_SPP`
  table, download skips the uploaded tar.gz + bundle/ (166 MB saved).
- `scratch/pt_probe.py` — one-lease spp-vs-noise probe (arm@rtpt/16/32/64/128
  + 64-raw, warehouse@32), downloads one frame for visual check.
- Judge venv installed; scenes built; bundles in /tmp/smoke (arm 52 MB,
  physics 21 MB, warehouse 93 MB).
- PRODUCT-FRICTION.md: F1–F12 now (F9 upload 0.385 MB/s vs 200 MB/s, F10 exec
  black box, F11 ovrtx doc skew, F12 OUTPUT_DIR code-global trap).

## Remaining

1. Probe returns → pick per-scene spp (fit: 240 f × X s/frame < 3600 s
   warehouse; 180 f others; warehouse ≈ 2× arm cost at same spp, measure).
2. RUN 1 + RUN 2 of `python3 run.py` (nohup + poll run.log — a background
   Bash task is capped at 2 h and a kill skips run.py's finally/cleanup).
   Expect ~7.5 min uploads (F9) + renders + possible 409 waits.
3. `bash media/make_media.sh <run_dir>`; video_gate.py must pass.
4. RECEIPT.md (two verbatim runs), REPRODUCE.md, REVIEW.json (two blind
   vision verdicts — not achievable locally; document or GOAL_BLOCKED).
5. Update README/SPEC numbers; commit+push per passing step; delete scratch
   and any lease run.py could not confirm deleted.

## Constraints

- HARD RULE: delete only sandbox ids my own code created in this run; never
  delete by listing/picking.
- Only commit files under cookbook/omniverse-rtx-scenes/.
- Never commit downloaded assets or rendered frames except shipped media.
- Env: GPU_API_URL=https://api.sbx.agent-next.com, GPU_API_KEY set.
- Seat single nvidia.5090; 409 cross-tenant contention recurs (F1).
