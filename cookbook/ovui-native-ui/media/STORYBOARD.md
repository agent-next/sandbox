# Storyboard — ovui-native-ui

Filled in before cutting `media/demo.mp4`. Slot order and craft rules:
`cookbook/DEMO-STANDARD.md` (Media). Machine check:
`cookbook/tools/video_gate.py`; blind panel verdicts: `media/REVIEW.json`.

Every shot before the end card is the same real 1280x720 lavapipe render of
the known-good panel (`media/data/render.png`, captured by the judge's own
harness and sha-checked against the graded determinism sha), animated by a
real camera move: the window is repositioned and resized across the offscreen
surface, so the pixels change every frame. Nothing is interpolated, morphed,
synthesised or drawn by hand; the only static frame in the video is the end
card.

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0–2 s | hook — finished real result | the finished render, camera pushing in on the panel, no title card, no logo, no terminal; the payoff stamped on the HUD from frame 0 — built / checked / attacked rows and the PASS verdict card with the determinism sha | `media/data/render.png` (sha256-checked against the graded determinism sha by `make_data.py`); camera frames from `media/make_frames.py`; stamp from `media/data/grade_good.json` + `selftest.txt` | "a native omni.ui panel — rendered headless on a CPU" |
| 2–6 s | input -> output | the spec text (420x360 "Tool Panel", three sliders 0..10/0..20/0..50, swatch rgba(0.2,0.5,0.9) 140x24, checkbox, "Apply" button) on a dark HUD panel; the moving render the spec produced stays visible behind and beside it | `SPEC.md` "Fixed spec for the panel"; `examples/good/panel.py` | "the spec -> the render the judge graded" |
| 6–13 s | escalate — widget gate | the moving render with the judge's measured widget bboxes drawn on it, labelled | `media/data/facts.json` (measured bboxes); `judge/reference.json` (expected bboxes) | "widget gate: every ref live, bboxes ±8 px" |
| 13–20 s | escalate — pixel gate | hard cut to a close-up crop of the real swatch region, with its measured rect; the measured median RGB beside the analytic sRGB target and the judge's +/-12 mask | `media/data/grade_good.json` (`swatch_median`), `media/data/facts.json` (swatch rect), `judge/reference.json` (`swatch_rgb`, `swatch_tol`) | "swatch median is exactly the analytic target" |
| 20–27 s | sandbox run "Nx speed" | the verbatim self-test log on a terminal HUD panel, scrolling past as the frames advance (a terminal capture, not a slide), with the measured wall time it compresses and the speed-up named | `media/data/selftest.txt` (verbatim), `media/data/timings.json` (measured selftest wall seconds) | "the judge's own self-test, Nx speed" (N = measured wall / shot length, computed at cut time) |
| 27–35 s | proof — verdict + kill matrix | the four gates, each with its measured number and a PASS tag, over the still-moving render; the kill rate and the mutant count | `media/data/grade_good.json`, `media/data/selftest.txt`, `media/data/mutants.json` | "judge verdict: PASS 4/4 gates, render byte-identical" |
| 35.5–38 s | end card — `python3 run.py` | static frame: the one-command launch and the "Ask your agent" pointer | `README.md` | "python3 cookbook/ovui-native-ui/run.py" |

Cuts: hard cuts only. A full-frame black flash (16 frames, 0.53 s) separates
every pair of neighbouring shots — 12 flash separators, of which the gate's
scene detector confirms 11 as cuts over 38.0 s = **2.36 per 10 s**
(machine-measured by `video_gate.py`; gate minimum 0.8). No crossfades: two
views of the same render score below the scene detector's 0.3 threshold, so
the flash is what makes the join a detectable cut.

Checklist: 16:9 1920x1080 @ 30 fps | 38.0 s (25-60 s) | 2.36 cuts/10 s
(>= 0.8) | every shot before the end card is moving real output (no slides,
stills, text-only frames) | caption cap height >= 4 % of frame height
(>= 43.2 px on 1080p: captions are rendered at 60-62 pt DejaVu Sans Bold,
cap height ~0.729 em = ~45 px; terminal log lines ride as a 34 px
mini-terminal on a dark HUD panel, the way a terminal capture is cropped to
its active region) | payoff visible by <= 1 s | readable muted on a phone |
every number traces to a RECEIPT command | first frame is the real render
(not dark, not a solid colour) | last 2 s static (end card) | H.264
yuv420p, `-movflags +faststart`, under 8 MB.
