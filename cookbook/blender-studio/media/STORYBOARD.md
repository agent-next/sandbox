# Storyboard

Master: 1920×1080, 30 fps, 28 seconds, composed in Remotion 4.0.531
(`media/video/src/Demo.tsx`). All scene imagery is real Cycles CPU output from
one fresh sandbox, seed 17. Every number on screen comes from
`media/master/props.json`, which `compose.py` writes from the judge's own
`data/selftest.json`.

| seconds | moving real output | animated HUD |
| --- | --- | --- |
| 0–3 | full-frame turntable, 48 real poses in order | kinetic hook “An AI agent built this in Blender. A judge checked it.”; “PASS 5/5” badge springs in |
| 3–8 | turntable continues | the five measured checks tick in one by one, each with its measured value |
| 8–12 | turntable under a slow push-in on the red paint, glass and gold | “Red car paint. Glass. Gold.” |
| 12–16 | animated wipe between the shipped pose and the same pose with the rim light unlinked | “Rim light: products only”; “unlinked = FAIL” |
| 16–24 | dimmed turntable behind the kill matrix | ten broken scenes appear one by one with their own hero renders and failed-gate cells; “caught k/10” counts up |
| 24–26 | turntable | “PASS 5/5”, “10/10 broken versions caught”, “Same seed. Same verdict.” |
| 26–28 | one static launch card over the hero | “Build it. Check it. Run it.” / `python3 run.py` |

Every turntable pose is independently rendered in Cycles and played at
24 poses/s, without optical flow or synthesized intermediate frames. Subframe
sampling does not change the judge's 12-frame G4 contract. Only the final two
seconds are static; `video_gate.py` measures motion and the static end card.
