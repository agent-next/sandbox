# Storyboard — physx-drop-test

Slot order and craft rules: `cookbook/DEMO-STANDARD.md` (Media). Machine
check: `cookbook/tools/video_gate.py media/demo.mp4`; blind panel verdicts:
`media/REVIEW.json`. Total 42.0 s, 1920×1080 @ 30 fps, 1260 frames; every
frame is derived from a real judge output (`media/judge_runs/`, sha256 in
`media/MANIFEST.json`). Hard cuts only — no crossfades. Cut list (9):
2.0, 10.0, 14.0, 18.0, 22.0, 30.0, 34.0, 36.5, 39.0 s.

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0–2 s | hook — finished real result | full-frame 3D render of the settled scene (box + ball resting on the ground, slow 6° orbit); two measured chips, no title card | `judge/simulate.py examples/good/scene.usda` → `judge_runs/traces/good/traj.npz` (frames at t=10 s); chips from `judge_runs/verdicts/good.json` (seed 42) | "all 7 gates pass — 2 400 PhysX steps vs closed-form Newtonian mechanics" |
| 2–10 s | input -> output | left: verbatim excerpt of `examples/good/scene.usda` (the authored input); right: the same scene simulated, 0.15× slow motion, analytic free-fall ghost + y_rest pass line | `examples/good/scene.usda`; `traj.npz` t ∈ [0, 1.2 s]; ghost = y₀ − g t²/2 computed from SPEC constants | "input: one authored USD scene → output: the exact trajectory the judge grades (0.15× slow motion)" |
| 10–14 s | escalate — free fall | close 3/4 camera on the falling box; translucent ghost box at the analytic y₀ − ½gt²; trail | `traj.npz` box_y t ∈ [0, 0.38 s]; `verdicts/good.json` G2 detail (g_fit 9.81, residual 0.0000 m) | "G2 free fall: fitted g = 9.81 m/s², max residual 0.0000 m — rule: ≤ 1 %" |
| 14–18 s | escalate — contact | ground-level close-up of the box meeting the ground; green ±1-frame contact band on a time bar | `traj.npz` t ∈ [0.35, 0.42 s]; G3 detail (0.3750 s vs analytic 0.37773 s, Δ 0.65 fr) | "G3 contact: 0.3750 s — Δ 0.65 frame ≤ 1 frame of √(2Δh/g)" |
| 18–22 s | escalate — bounce apex | camera tracks the ball's first rebound; dashed analytic apex line at 0.375 m | `traj.npz` t ∈ [0.42, 0.75 s]; G5 detail (0.3733 m, 0.43 %) | "G5 bounce: apex 0.3733 m vs e²·Δh = 0.375 m (0.43 % ≤ 10 %)" |
| 22–30 s | escalate — real sandbox run, Nx speed | dark terminal panel, the real `bash judge/selftest.sh` log scrolling; speed label computed from the measured wall time | `bash judge/selftest.sh` fresh run, tee'd to `judge_runs/selftest.log`; wall seconds in `judge_runs/selftest.time` | "real sandbox run: bash judge/selftest.sh — {N}× speed (measured {W} s)" |
| 30–34 s | escalate — energy | the measured E/E₀ curve drawing across both bodies with the +0.5 % pass band | `traj.npz` box/ball y, vy; G6 detail (max step gain 0.068 % E₀) | "G6 energy: E = mgy + ½mv² never gains more than 0.068 % of E₀ (limit 0.5 %)" |
| 34–36.5 s | proof — verdict | the judge's verdict table: G1–G7, measured value, rule, PASS | `verdicts/good.json` gates + bodies detail | "the verdict: every gate a number, every number inside its rule" |
| 36.5–39 s | proof — kill matrix | mutant × gate matrix, 10 rows, red = failed gate, kill-rate banner | `verdicts/<mutant>.json` × 10, `mutants/mutants/mutants.json` | "the self-test: 10 single-edit mutants, 10 killed by a gate — 100 %" |
| 39–42 s | end card | static dark card, one command centred | — | "python3 cookbook/physx-drop-test/run.py" |

Checklist: 16:9 1920×1080 @ 30 fps | 42.0 s (25–60) | 9 hard cuts ≈ 2.1
per 10 s (≥ 0.8) | caption cap height ≥ 4 % of frame height (≥ 43.2 px —
all captions ≥ 46 pt ≈ 46 px cap) | payoff visible by ≤ 2 s | readable
muted on a phone | every number traces to RECEIPT.md.

Why the render is not the simulator's own: the pinned `ovphysx` 0.6.3
wheel is simulation-only — it exposes no renderer (its package contains
`PhysX`/`types`/`population`/`schemas` modules only; no render API, and
the PhysX tensor API has no debug render buffer). The 3D shots therefore
render the exact per-step samples the judge graded (`traj.npz`, sha256 in
MANIFEST.json) with a deterministic software renderer (perspective
projection, Lambert shading) at the authored geometry — a 3D view of the
real trajectory, not a 2D plot or stick figure of it.
