# sim-tuner / overlaid slow-motion cut

One MuJoCo view fills every shot. Solid teal is tuned; orange surface
outlines are default; translucent white surface outlines are hidden truth.
All three share the same camera, world coordinates and captured timestep.
Surface outlines avoid coplanar-face flicker without shifting or enlarging
any geometry. Solid teal traces and dashed white traces follow the actual
paths. The floor, shadows, perspective and moving camera are real 3D renders.

| time | moving picture | animated HUD and evidence |
|---|---|---|
| 0–4 s, hook | Largest-miss box slide, close camera, states 75–194 | Default drifts / tuned matches, live horizontal misses in cm; presentation test 1/4; aggregate normalized RMS and PASS limit |
| 4–8 s | Next-largest miss, contrasting light floor, states 60–179 | Test 2/4; same parameters, same comparison |
| 8–12 s | Third-largest miss, dark floor, states 30–149 | Test 3/4; no exaggerated displacement |
| 12–16 s | Fourth-largest miss, light floor, states 0–119 | Test 4/4; landing and slide |
| 16–21 s | Close two-link arm, states 251–400, same fit after the servo command step | Joint damping, then armature; test 1/4 replay, not a fifth unseen test |
| 21–24 s, proof | Largest-miss box again, states 110–199 | G1–G4 PASS; 18/18 wrong fits caught; CPU/GPU agree; 0.02206 < 0.025 across all four tests |
| 24–26.2 s, only static card | Freeze the final real render | Receipt result and `python3 cookbook/sim-tuner/run.py` |

The five parameter rows rotate over the moving footage: sliding friction
(0–5 s), contact response time (5–10 s), contact damping ratio (10–16 s),
joint damping (16–18.5 s), joint armature (18.5–21 s). Each shows its units
and the real **default → tuned → truth** values, not fabricated in-between
optimization values. The progress accent is elapsed viewing time.

Presentation tests 1/4, 2/4, 3/4, 4/4 map to original held-out recordings
3, 4, 1, 2. `collect.py` ranks them by the largest actual default/truth
horizontal box gap over the complete recorded second. This is presentation
ordering only: the judge still scores all seven signals across all four
recordings. The arm segment and final proof explicitly replay test 1/4.

Every video frame advances one captured 2 ms state at 30 fps, accurately
labelled **0.06x speed**. No pose interpolation, coordinate offsets, time
warping within a shot, loop reset, still plot, screenshot or simulated
optimization recording is used. The camera also moves during every shot.

Sources: `data/trajectories.npz` captured inside CPU grading, SHA-256 and
exact shot indices in `data/render-checks.json`; numeric values and source
formulas in `result.json`; accepted G1–G4 and mutant evidence in
`data/run-1.json` and `../RECEIPT.md`. The live cm misses are horizontal
box distances, **not** the unitless normalized RMS acceptance metric.
