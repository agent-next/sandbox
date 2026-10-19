# Storyboard — layerfs-race

Fill this in before cutting `media/demo.mp4`. Slot order and craft rules:
`cookbook/DEMO-STANDARD.md` (Media). Machine check:
`cookbook/tools/video_gate.py`; blind panel verdicts: `media/REVIEW.json`.

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0-2 s | hook — finished real result | | | |
| 2-10 s | input -> output | | | |
| 10-35 s | escalate + sandbox run "Nx speed" | | | |
| proof | judge PASS + mutant kill matrix as HUD on moving footage (no text slide) | | | |
| last 2-3 s | end card — `python3 run.py` | | | |

Checklist: 16:9 >= 1920x1080 @ 30 fps | 25-60 s | >= 0.8 cuts/10 s |
every shot is moving real output (no slides, stills, text-only frames) |
caption cap height >= 4 % of frame height | payoff visible by <= 2 s |
readable muted on a phone | every number traces to RECEIPT.md.
