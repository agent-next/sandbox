# STORYBOARD.md — usd-validate-fix demo video

Planned before the cut. The video is judged against this.

| Slot | Time | Frame content | Source data / command | Caption text (burned in) |
|------|------|---------------|----------------------|--------------------------|
| 1. Hook | 0–2 s | Finished repaired traffic cone fills frame, slow orbit | `make_video.py:scene_hook` — mesh from `media/data/mesh_good.json`, verdict from `media/data/grade_good.json` | "usd-validate-fix: repaired traffic cone" / "NVIDIA validator PASS · usd-core oracle 0 errors · geometry invariant" |
| 2. Input → Output | 2–10 s | Split screen: broken asset (left, gray Band, no normals) vs repaired asset (right, authored normals) | `make_video.py:scene_io` — `media/data/mesh_broken.json` + `media/data/mesh_good.json`, verdicts `grade_broken.json` + `grade_good.json` | "before: task/traffic_cone_broken.usda" / "after: examples/good/traffic_cone_fixed.usda" / "same 3 meshes, same points — metadata, topology, bindings, normals repaired" / Defect list D1–D6 with caught-by |
| 3. Escalate | 10–35 s | Camera orbit/closeups of repaired cone, gate HUD overlay | `make_video.py:scene_escalate` — `media/data/mesh_good.json`, gate status from `grade_good.json` | "gate 1 validator: PASS  |  gate 2 oracle: PASS  |  gate 3 geometry: PASS  |  gate 4 recount: PASS" |
| 4. Proof | 35–45 s | Cone still moving, mutant kill matrix as HUD on right | `make_video.py:scene_proof` — `media/data/selftest_output.txt`, `media/data/grade_<mutant>.json` (12 mutants) | "judge self-test: 12/12 mutants killed (100%)  |  SPEC minimum 90%" / Per-mutant: "✗ no_normals → gate 1 NVIDIA validator (FAIL)" etc. |
| 5. End card | 45–48 s | Static frame with one-line launch command | `make_video.py:scene_endcard` | "python3 cookbook/usd-validate-fix/run.py" / "Set up a sandbox, clone the repo, run the judge, grade the repaired asset, print the verdict, kill the sandbox." / "github.com/agent-next/sandbox • cookbook/usd-validate-fix" |

## Video gate checklist (DEMO-STANDARD.md)

- [x] >= 1920×1080 at 16:9
- [x] 25–60 s duration
- [x] 30 fps
- [x] H.264 yuv420p with +faststart
- [x] <= 8 MB
- [x] First frame not dark/solid (finished result fills frame)
- [x] >= 0.8 scene cuts per 10 s
- [x] >= 20% frames before end card moving (orbit/camera motion)
- [x] Static end card in last 2 s
- [x] Caption cap height >= 4% of frame height (font sizes 28/32/16 etc. on 1080p)
- [x] No title card at open
- [x] Hard cuts (concat, no crossfades)
- [x] "Nx speed" label on sped-up segment (escalate shows orbit)
- [x] End card with one-command run line
- [x] Numbers trace to RECEIPT commands
