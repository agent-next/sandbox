# Storyboard (written before cutting the revised video)

Master: 1920×1080, 30 fps, 32 seconds. All scene imagery is real Cycles CPU
output from one fresh sandbox, seed 17. Headline type is at least 64 px;
the proof grid uses 76 px row labels and 96 px gate headers.
Panels and close-up crops change presentation, never the geometry.

| seconds | frame content | source / command | burned-in caption |
| --- | --- | --- | --- |
| 0–2 | finished studio render fills frame, with one-line hook | `blender … -P media/render.py -- --out media/source --seed 17`, frame-01.png | “An AI agent built this in Blender. A judge checked it.” |
| 2–5 | one brief beside the finished scene | frame-01.png; scene settings and good verdict | “THE BRIEF” / “Center the hero” / “Keep the highlights” / “Use a smooth backdrop” / “Make a full turn” / “Rim light: products only” |
| 5–8 | two detailed crops of real red paint, glass and gold | frame-01.png | “Red car paint. Real reflections.” / “Glass and gold. Same scene.” |
| 8–14 | smooth spin, three complete revolutions | all 48 real 1080p poses, subframes 1, 1.25, …, 12.75 of the unchanged animation | “48 real Cycles poses · 24 poses/s” |
| 14–17 | side-by-side real full-resolution rim-light comparison | frame-01.png and unlinked.png | “Rim light hits only the products” / “Products only” / “Hits everything” |
| 17–19 | direct-only rim probe makes the difference obvious | selftest good and unlinked_rim rim-on.png | “The judge isolates the rim light” / “Backdrop stays dark: PASS” / “Backdrop lights up: FAIL”; measured deltas as supporting text |
| 19–22 | off-center failure beside centered repair; measured self-test rows revealed at labelled speed | off_center/hero.png, frame-01.png, data/selftest.json | “Broken → repaired” / “Off-center: 3/5” / “Centered: 5/5” / “Sandbox self-test replay / Nx speed” |
| 22–25 | large PASS moment over the real result | good verdict and selftest.json | “PASS 5/5” / “All five checks passed” / “10/10 deliberately broken versions caught” |
| 25–27.5 | first five rows of phone-readable proof grid | data/selftest.json | “JUDGE PROOF · 10/10 caught” / “Deliberately broken versions” / “G1 G2 G3 G4 G5”; plain failure labels |
| 27.5–30 | last five rows, same large labels and headers | data/selftest.json | same headers, remaining measured rows; blue = pass, orange = fail |
| 30–32 | one static launch card over the hero | frame-01.png | “Build it. Check it. Run it.” / `python3 run.py` |

Every turntable pose is independently rendered in Cycles. Playback repeats
actual poses at 24 poses/s inside a 30 fps master, without optical flow or
synthesized intermediate frames. Subframe sampling does not change the judge's
12-frame G4 contract. Render metadata records each sampled frame and angle.

The process slot is a labelled replay of measured sandbox self-test output,
not a screen recording or a recorded autonomous agent session. Failure labels
are plain-language names for the exact measured cases, not invented tests.
The proof grid is split into two pages to enlarge all ten rows. The final
two seconds are static. The machine gate measures actual cuts.
