# Storyboard — cad-verify-back

Filled in before cutting `media/demo.mp4`. Slot order and craft rules:
`cookbook/DEMO-STANDARD.md` (Media). Machine check:
`python3 cookbook/tools/video_gate.py media/demo.mp4` (PASS, all 15 checks).

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0–8.5 s | hook — finished real result | the delivered `part.stl` turntable, full-frame, VTK offscreen orbit | `examples/good/part.stl` (vtkSTLReader → vtkRenderWindow, offscreen under Xvfb); verdict from `media/data/verdicts/good.json` (`judge/grade.sh examples/good --json`, seed 20261014) | "the delivered part — verdict PASS, 14/14 gates" |
| 8.5–15.5 s | escalate — camera push-in | zoom onto the bolt circle, full-frame | same STL; gate numbers from `good.json` (`step_pcd`, `angular_spacing`, `step_volume`) | "PCD err ‹measured› ≤ 0.02 mm · angular dev ‹measured›° ≤ 0.05° · volume rel err ‹measured›" |
| 15.5–23 s | proof — every gate vs the spec | `media/result.png` full-frame | `media/data/verdicts/good.json`, `examples/good/part.stl` + `part.dxf`, `judge/spec.json` | "every gate, measured against the spec" + "14/14 gates pass — XOR vs the spec-built reference: ‹measured› mm³ (rule ≤ 1%)" |
| 23–24.5 s | interstitial | dark card, so both figure cuts read as hard cuts | — | "now stress the judge" |
| 24.5–32 s | proof — judge stressed | `media/loop.png` full-frame: the agent loop + the mutant × gate kill matrix | all 11 `media/data/verdicts/*.json`; kill rate from `media/data/selftest.log` | "and it fails bad parts — kill rate 10/10" + "determinism PASS (same seed -> identical verdict)" |
| 32–34.7 s | end card | static: the one-command launch | README "one-command run" | "python3 cookbook/cad-verify-back/run.py" |

Checklist: 16:9 1920×1080 @ 30 fps | 34.7 s | 6 shots, 4 scene cuts (≈1.4/10 s) |
primary burned-in captions 52 px, supporting 44 px (≥ 44 px rule) |
payoff on screen from frame 0 | readable muted | every number traces to
`media/data/` verdicts written by `judge/grade.sh` (RECEIPT.md commands).
Machine check: `python3 cookbook/tools/video_gate.py media/demo.mp4` — PASS
on all 15 checks.
