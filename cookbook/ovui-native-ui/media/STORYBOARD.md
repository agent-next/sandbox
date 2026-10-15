# Storyboard — ovui-native-ui

Filled in before cutting `media/demo.mp4`. Slot order and craft rules:
`cookbook/DEMO-STANDARD.md` (Media). Machine check:
`cookbook/tools/video_gate.py`; blind panel verdicts: `media/REVIEW.json`.

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0–2.5 s | hook — finished real result | the real 1280×720 headless render, full-frame, no overlay, no title card | `media/data/render.png` (sha256-checked against the graded determinism sha by `make_data.py`) | "a native omni.ui panel — rendered headless on a CPU" |
| 2.5–9 s | input -> output | left half: the fixed spec (420×360 "Tool Panel", three sliders 0–10/0–20/0–50, swatch rgba(0.2, 0.5, 0.9) 140×24, checkbox, "Apply" button); right half: the same render | `SPEC.md` "Fixed spec for the panel" table; `media/data/render.png` | "the spec → the render the judge graded" |
| 9–15 s | escalate — widget gate | the render with the judge's measured bboxes, camera pushing in on the three slider rows (hard cut in, continuous zoom) | `media/data/render.png` + `media/data/facts.json` (measured bboxes) | "widget gate: every ref a live widget, bboxes within ±8 px" |
| 15–21 s | escalate — pixel gate | hard cut to the swatch close-up with its measured rect, then hard cut to the swatch chart: measured median RGB vs the judge's ±12 mask around the analytic target | `media/data/facts.json`, `media/data/grade_good.json` (`swatch_median`), `judge/reference.json` | "swatch median [51 128 230] — exactly the analytic sRGB target" |
| 21–29 s | sandbox run "Nx speed" | terminal replay of the real self-test log (setup line, 11 mutant kills, kill rate), scrolling fast, cropped to the active region; the label names the speed and the real run it compresses | `media/data/selftest.txt` (verbatim), `media/data/timings.json` (measured self-test wall time) | "in the sandbox: judge self-test — NN s replayed in 8 s (8× speed)" |
| 29–33.5 s | proof — verdict | the four gates, each with its measured number and a PASS tag | `media/data/grade_good.json` | "judge verdict: PASS 4/4 gates, render byte-identical" |
| 33.5–37 s | proof — kill matrix | 12 rows: known-good PASS + the 11 mutants with the gate(s) that killed each, and the kill rate | `media/data/mutants.json`, `media/data/selftest.txt` | "11/11 mutants killed by the judge gates" |
| 37–40 s | end card — `python3 run.py` | static frame: the one-command launch and the "Ask your agent" pointer | `README.md` | "python3 cookbook/ovui-native-ui/run.py" |

Cuts: hard cuts only, at every slot boundary plus the swatch-close-up →
chart change inside the pixel-gate slot — 8 cuts over 40 s ≈ 2.0 per 10 s
(gate minimum 0.8). No crossfades.

Checklist: 16:9 >= 1920x1080 @ 30 fps | 25-60 s | >= 0.8 cuts/10 s |
caption cap height >= 4 % of frame height (>= 43.2 px on 1080p: every
burned caption uses >= 44 pt at the video's 100 dpi) | payoff visible by
<= 2 s | readable muted on a phone | every number traces to RECEIPT.md.
