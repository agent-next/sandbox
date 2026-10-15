# Storyboard (written before cutting the revised video)

Master: 1920×1080, 30 fps, 28 seconds. All scene imagery is real Cycles CPU
output from one fresh sandbox, seed 17. Every video caption is at least 64 px
(capital height at least 4% of the frame), including the single ten-row table.
Panels and close-up crops change presentation, never the geometry.

| seconds | frame content | source / command | burned-in caption |
| --- | --- | --- | --- |
| 0–2 | finished studio render fills frame, with one-line hook and verdict badge from frame zero | `blender … -P media/render.py -- --out media/source --seed 17`, frame-01.png; good verdict | “An AI agent built this in Blender. A judge checked it.” / “PASS 5/5” |
| 2–4 | the only brief hold, beside the finished scene | frame-01.png; scene settings and good verdict | “THE BRIEF” / “Center the hero” / “Keep the highlights” / “Use a smooth backdrop” / “Make a full turn” / “Rim light: products only” |
| 4–7 | two detailed crops of real red paint, glass and gold, 1.5 s each | frame-01.png | “Red car paint. Real reflections.” / “Glass and gold. Same scene.” |
| 7–10.2 | visibly rotating hero, two complete revolutions, 1.6 s per turn | all 48 real 1080p poses, subframes 1, 1.25, …, 12.75 of the unchanged animation | “48 real Cycles poses · 30 poses/s” |
| 10.2–13.2 | explain the judge over a side-by-side full-resolution rim-light comparison | frame-01.png and unlinked.png | “The judge: an automatic render checker” / “It measures the image.” / “Products only” / “Hits everything” / “Same scene. Only the rim light changes.” |
| 13.2–15.2 | direct-only rim probe makes the measured difference obvious | selftest good and unlinked_rim rim-on.png | “The judge isolates the rim light” / “Backdrop stays dark: PASS” / “Backdrop lights up: FAIL” |
| 15.2–18.2 | off-center failure beside centered repair; all ten measured self-test rows revealed at labelled speed | off_center/hero.png, frame-01.png, data/selftest.json | “Broken → repaired” / “Off-center: 3/5” / “Centered: 5/5” / “Caught: …” / “Sandbox self-test replay / Nx speed” |
| 18.2–21.2 | large PASS moment over the real result | good verdict and selftest.json | “PASS 5/5” / “All five checks passed” / “10/10 deliberately broken versions caught” / “Same seed. Same verdict.” |
| 21.2–26 | one static ten-row table, every broken version visible together | data/selftest.json | “JUDGE PROOF · 10/10 caught” / “Deliberately broken versions” / “Frame / Light / Sweep / Loop / Rim”; ten plain failure labels; “Blue = pass. Orange = fail.” |
| 26–28 | one static launch card over the hero | frame-01.png | “Build it. Check it. Run it.” / `python3 run.py` |

Every turntable pose is independently rendered in Cycles. Playback repeats
actual poses at 30 poses/s inside a 30 fps master, without optical flow or
synthesized intermediate frames. Subframe sampling does not change the judge's
12-frame G4 contract. Render metadata records each sampled frame and angle.

The process slot is a labelled replay of measured sandbox self-test output,
not a screen recording or a recorded autonomous agent session. Failure labels
are plain-language names for the exact measured cases, not invented tests.
Tiny change values, runtime/seed annotations and G1–G5 sub-labels are removed
from the video, not from its source evidence. The replay speed still derives
from measured self-test runtime divided by its three-second slot.
The final two seconds are static. The machine gate measures actual cuts.
