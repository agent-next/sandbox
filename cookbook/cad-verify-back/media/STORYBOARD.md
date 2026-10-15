# Storyboard — cad-verify-back

Filled in before cutting `media/demo.mp4`. Slot order and craft rules:
`cookbook/DEMO-STANDARD.md` (Media). Machine check:
`cookbook/tools/video_gate.py`; blind panel verdicts: `media/REVIEW.json`.

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0–2.6 s | hook — finished real result | the delivered `part.stl` turntable, full-frame; verdict badge bottom-left | `examples/good/part.stl` parsed by trimesh 5.1.1; verdict from `media/data/verdicts/good.json` (`judge/grade.sh examples/good --json`, seed 20261014) | "verdict PASS — 14/14 gates on the delivered STEP · STL · DXF" |
| 2.6–10 s | input → output | `judge/spec.json` verbatim (left) → the part mesh + its `part.dxf` drawing (right) | `judge/spec.json`; `examples/good/part.stl`, `part.dxf` (ezdxf 1.4.4) | "in: one spec JSON → out: part.step · part.stl · part.dxf" |
| 10–14 s | escalate — camera push-in | zoom to the bolt circle; spec PCD ring + the verdict's measured centres projected onto the moving mesh | `good.json` gates `step_pcd`, `angular_spacing`, `step_holes.bolt_centres` | "G5 PCD err ≤ 0.02 mm · G6 angular dev ≤ 0.05°" (measured values on screen) |
| 14–18.5 s | escalate — sandbox run at ~10× | the fixing-agent loop chart building point by point, "~10× speed" | `media/data/replay/iter{1..4}_*.json` — real `grade.sh` verdicts in a fixing order (scale_inch_mm → boss_missing → tangential_hole_drift → good); labelled "replayed, not a live trace" | "the fixing loop, replayed through the judge — ~10× speed" |
| 18.5–31.5 s | escalate — judge stressed | one card per mutant: the mutant's own STL/DXF with the defect drawn (flipped facet, dropped facet, drifted hole arrow, missing DXF circle…) + the gate that caught it | `media/data/mutants/<m>/part.{stl,dxf}` + `media/data/verdicts/<m>.json` (`judge/mutants.py` + `grade.sh`) | "mutant k/10: ‹name›" + "caught by Gx ‹gate› — ‹pass rule›" + measured-vs-limit lines |
| 31.5–34.5 s | proof | PASS headline + the real mutant × gate kill matrix (green/red/grey cells from the verdict JSONs) | all 11 `media/data/verdicts/*.json`; kill rate from `media/data/selftest.log` | "verdict: PASS — all 14 gates, deterministic" · "kill rate 10/10" |
| 34.5–37 s | end card | static: the one-command launch | README "one-command run" | "python3 run.py" |

Checklist: 16:9 1920×1080 @ 30 fps | 37 s | ~15 scene cuts (≈4/10 s) |
primary burned-in captions 44 pt (cap height ≈ 4 % of frame height) |
payoff on screen from frame 0 | readable muted | every number traces to
`media/data/` verdicts written by `judge/grade.sh` (RECEIPT.md commands).
