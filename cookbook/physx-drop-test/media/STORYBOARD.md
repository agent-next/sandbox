# Storyboard — physx-drop-test

Slot order and craft rules: `cookbook/DEMO-STANDARD.md` (Media). Machine
check: `cookbook/tools/video_gate.py media/demo.mp4`; blind panel verdicts:
`media/REVIEW.json`. Total 43.0 s, 1920×1080 @ 30 fps, 1290 frames; every
frame is derived from a real judge output (`media/judge_runs/`, sha256 in
`media/MANIFEST.json`). Hard cuts only — no crossfades. Cut list (9):
2.5, 9.0, 13.5, 17.5, 22.5, 29.5, 33.5, 36.5, 40.0 s → 2.1 cuts / 10 s
(rule ≥ 0.8). Captions: cap height 48.6 px = 4.5 % of frame height (rule
≥ 4 %), measured from DejaVu Sans Bold metrics (see make_video.py).

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0–2.5 s | hook — finished real result | full-frame 3D render of the settled scene (box + ball resting on the ground, slow 8° orbit); two measured chips, no title card | `judge/simulate.py examples/good/scene.usda` → `judge_runs/traces/good/traj.npz` (frames at t=10 s); chips from `judge_runs/verdicts/good.json` (seed 42) | "all 7 gates pass — 2400 PhysX steps vs closed-form Newtonian mechanics" |
| 2.5–9 s | input -> output | left: verbatim excerpt of `examples/good/scene.usda` (the authored input) scrolling; right: the same scene simulated, 0.15× slow motion, analytic free-fall ghost + y_rest pass line | `examples/good/scene.usda`; `traj.npz` t ∈ [0, 1.2 s]; ghost = y₀ − g t²/2 computed from SPEC constants | "input: one authored USD scene -> the exact trajectory the judge grades" |
| 9–13.5 s | escalate — free fall | close 3/4 camera on the falling box; translucent ghost box at the analytic y₀ − ½gt²; trail; G2 chart panel alongside | `traj.npz` box_y t ∈ [0.055, 0.38 s]; `verdicts/good.json` G2 detail (g_fit 9.81, residual 0.0000 m) | "G2 free fall: fitted g = 9.81 m/s², max residual 0.0000 m" |
| 13.5–17.5 s | escalate — contact | ground-level close-up of the box meeting the ground; green ±1-frame contact band on the velocity-reversal chart | `traj.npz` t ∈ [0.30, 0.435 s]; G3 detail (0.3750 s vs analytic 0.37773 s, Δ 0.65 fr) | "G3 contact: 0.3750 s vs √(2Δh/g) = 0.3777 s — Δ 0.65 frame" |
| 17.5–22.5 s | escalate — bounce apex | camera tracks the ball's first rebound; dashed analytic apex line at 0.375 m; G5 chart alongside | `traj.npz` t ∈ [0.40, 0.82 s]; G5 detail (0.3733 m, 0.43 %) | "G5 bounce: apex 0.3733 m vs e²Δh = 0.375 m — 0.43 % (rule: ≤ 10 %)" |
| 22.5–29.5 s | escalate — real sandbox run, Nx speed | dark terminal panel, the real `bash judge/selftest.sh` log scrolling; "Nx speed" chip computed from the measured wall time | `bash judge/selftest.sh` fresh run, tee'd to `judge_runs/selftest.log`; wall seconds in `judge_runs/selftest.time` | "real sandbox run: bash judge/selftest.sh — the judge names the gate that kills every mutant" |
| 29.5–33.5 s | escalate — energy | the measured E/E₀ curve drawing across both bodies with the +0.5 % pass band, 3D view alongside | `traj.npz` box/ball y, vy; G6 detail (max step gain 0.068 % E₀ box) | "G6 energy: E = mgy + ½mv² never gains more than 0.068 % of E₀ (limit 0.5 %)" |
| 33.5–36.5 s | proof — verdict | the judge's verdict table (G1–G7, measured value) revealed row by row as a HUD over the still-orbiting settled scene | `verdicts/good.json` gates + bodies detail | "every number re-derived from sim output; nothing asks PhysX if PhysX is right" |
| 36.5–40 s | proof — kill matrix | mutant × gate matrix, 11 rows, red = failed gate, kill-rate banner, over the still-moving result | `verdicts/<mutant>.json` × 11, `mutants/mutants/mutants.json` | "the self-test: every cheat named by the gate that kills it — crash does not count" |
| 40–43 s | end card | static dark card, one command centred | — | "python3 cookbook/physx-drop-test/run.py" |

Checklist: 16:9 1920×1080 @ 30 fps | 43.0 s (25–60) | 9 hard cuts = 2.1
per 10 s (≥ 0.8) | caption cap height 48.6 px = 4.5 % of frame height
(≥ 4 %) | payoff visible at 0 s | readable muted on a phone | every
number traces to RECEIPT.md.

Why the render is not the simulator's own: the pinned `ovphysx` 0.6.3
wheel is simulation-only — it exposes no renderer (its package contains
`PhysX`/`types`/`population`/`schemas` modules only; no render API, and
the PhysX tensor API has no debug render buffer). The 3D shots therefore
render the exact per-step samples the judge graded (`traj.npz`, sha256 in
MANIFEST.json) with a deterministic software renderer (perspective
projection, Lambert shading) at the authored geometry — a 3D view of the
real trajectory, not a 2D plot or stick figure of it.
