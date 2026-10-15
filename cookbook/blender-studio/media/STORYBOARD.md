# Storyboard (written before cutting the video)

Master: 1920×1080, 30 fps, 30 seconds. All scene imagery comes from Cycles CPU
rendered frames of the graded scene, seed 17. Captions use >=64 px type.
Background panels and cropping are presentation only, never substitute geometry.

| seconds | frame content | source / command | burned-in caption |
| --- | --- | --- | --- |
| 0–2 | full-frame finished real studio hero, no introductory card | `blender … -P media/render.py -- --out media/source --seed 17`, frame 1 | none |
| 2–6 | hero with left-side spec prompt, real result still visible | frame 1, good verdict | “Center it. Loop it. Prove it.” / measured frame coverage |
| 6–10 | close-up of red paint and glass, then the wide scene | crop of frame 1, no invented geometry | “Car paint / glass / gold” |
| 10–16 | actual 12-frame turntable, repeated at six frames/s | full-resolution frames 1–12, period 12 | “Real Cycles turntable · 6 fps playback” |
| 16–20 | full-resolution linked/unlinked A/B, then direct light-linking probes | frame 1 and unlinked.png; selftest good and unlinked_rim rim-on.png | measured backdrop deltas / “Products-only rim” |
| 20–23 | real off-center mutant beside repaired good; sped-up replay of measured sandbox selftest output rows | selftest.json and mutant hero.png | “Self-test output replay · measured runtime / 3 s speed” |
| 23–27 | PASS, five gate metrics and nine-mutant kill matrix | selftest.json, good verdict | “PASS 5/5 · 9/9 mutants caught” only if measured |
| 27–30 | static launch card over real hero | frame 1 | `python3 run.py` |

Planned cuts at 2, 6, 10, 16, 20, 23, 27 seconds; visual layouts deliberately
change, not merely tiny caption edits. The machine gate measures actual cuts.
The final three seconds are static. No labels imply that the 12 pose samples
were rendered at 30 fps: the master repeats actual render frames.
The process slot replays measured self-test output, not a screen recording or
an autonomous agent session. The lead reviews that presentation explicitly.
