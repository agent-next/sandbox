# Media Review — control-tuning

Generated 2026-10-15 04:53:17 UTC by `make_media.sh`.

## Files produced
| file | sha256 | bytes |
|------|--------|-------|
| result.png | bca3e2cb01acf97e33ad6a745d062c6c2b7d365ceaddd7d61e03480b09479617 | 820438 |
| loop.png | f84a7ae2aa36f696b91d36d7df6fbcab3a758c2a1e5828c753c0f7e8dc0e8861 | 660791 |
| demo.mp4 | f9d93dc4f8185312937f2be2921d4dea8efd0942b4581023f5ad532070f9817d | 4456362 |

## 3-D render provenance (DEMO-STANDARD)
- All motion in demo.mp4 and the result.png hero frame is rendered by
  `mujoco.Renderer` (mujoco 3.14.0, pinned in judge/requirements.txt)
  from `scripts/cartpole.xml`.
- GL backend used on this build host: **osmesa** (egl probed first,
  osmesa fallback).
- The poses are a kinematic replay: qpos=[x, theta] is set from the
  judge's own `--trace` CSV rows (linear interpolation to 30 fps);
  the nonlinear plant is never re-simulated by the media pipeline.
- Overlays (PIL, drawn on the rendered RGB): t, θ, x, |F|, |τ| at the
  frame's trace time; the scenario gate line (settle band + limit);
  a PASS/FAIL tag at the measured settle time; a sparkline of the
  gated variable over the full 10 s window.
- The settle band is drawn in the scene: translucent green geoms on
  the rail at |x| ≤ band (0.01 m for S1, 0.02 m for S2), resized per
  scenario.

## Video checks (ffprobe)
- Duration: 53.034000 s
- Resolution: 1920,1080
- Frame rate: 30/1
- Size: 4456362 bytes (4 MB) — under 8 MB limit: PASS
- Codec: h264, yuv420p, +faststart

## PNG verification (opened at full size)
- **result.png**: 13×12.6 in @ 200 dpi
  - Top: hero frame — the MuJoCo render of good/s1_trace.csv at
    t = 0.70 s (the measured θ settle time) with HUD numbers, gate
    card and PASS tag overlaid; the translucent green strip on the
    rail is the ±0.01 m x-settle band.
  - Bottom-left: gate table with 10 rows — all PASS, values match
    data/good/verdict.json exactly.
  - Bottom-right: MC scatter (200 dots) with red limits at x = 7 s,
    θ = 8 s — 200/200 = 1.000 ≥ 0.95.
  - The two S1/S2 trace plots from the previous revision were
    superseded by the hero render (a sparkline of θ(t) is overlaid
    inside the hero frame itself).
- **loop.png**: 13×9.6 in @ 200 dpi
  - Left: 4×18 gate matrix (too-aggressive, too-sluggish, mc-marginal,
    good) — ✓/✕ per gate from verdict JSONs
  - Middle-left: too-aggressive vs good torque demand (S2) — red
    ±1 N·m lines, orange exceeds at 2.52 N·m
  - Middle-right: too-sluggish vs good cart position (S2) — green
    band, orange never settles (10 s)
  - Right-top: first-failing gate per step with measured values
  - Right-bottom: selftest bars — 9/9 mutants killed

## Layout gate
`make_result.py` and `make_loop.py` call `common.check_layout(fig)`
before savefig: all text artists and legends must lie inside the canvas,
and no two text bounding boxes (or text/legend pair) may overlap — the
build fails if it trips.

## Frame extraction check (6 frames)
Commands (run from `cookbook/control-tuning/`):

    for t in 2 10 20 30 40 50; do
      ffmpeg -y -hide_banner -loglevel error -ss $t -i media/demo.mp4 \
        -frames:v 1 media/master/frame_${t}s.png
    done

| t | what the frame shows |
|---|----------------------|
| 2 s  | title card — "LQR cart-pole control tuning" |
| 10 s | S2 replay start: MuJoCo cart at x = 1 m, pole upright; HUD shows t, θ, x, \|F\|, \|τ\|; green settle strip at x = 0 ahead on the rail; sparkline x(t) with playhead |
| 20 s | side-by-side S2 — too-aggressive (left) vs good (right); the torque gate's FAIL tag "peak \|τ\| = 2.52 N·m > 1 N·m" pinned on the left half |
| 30 s | side-by-side S2 at 1.7× — too-sluggish (left) vs good (right); good's cart already inside the green band, sluggish still short of it |
| 40 s | media/loop.png proof frame — mutant × gate matrix, killer traces, selftest bars |
| 50 s | closing card — "every number is a judge measurement" |

## Numbers traceability
Every plotted/overlaid number was spot-checked against its source file:
- 3-D overlay θ/x/|F|/|τ| ↔ the same row of media/data/<name>/s*_trace.csv
- gate cards & PASS/FAIL tags ↔ data/<name>/verdict.json gate values
- sparkline curve ↔ the full trace CSV column
- result.png gate table ↔ data/good/verdict.json
- result.png MC panel ↔ data/good/mc_samples.csv + verdict.json mc_pass/mc_n
- loop.png matrix cells ↔ each candidate's verdict.json gate pass flags
- loop.png killer traces ↔ data/too-aggressive/s2_trace.csv (τ demand),
  data/too-sluggish/s2_trace.csv (x position)
- loop.png selftest bars ↔ selftest.sh output (9/9 = 100%)

All match. No synthesised data.
