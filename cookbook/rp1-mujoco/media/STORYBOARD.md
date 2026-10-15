# demo.mp4 storyboard — rp1-mujoco

1590 frames at 30 fps = 53.0 s. Every robot frame is a real headless MuJoCo
(EGL) render of the pinned RP1 scene, loaded with the exact state the judge
recorded at that instant (`media/data/traces/<name>/trace.csv`, written by
`grade.sh --trace`, seed 20261014). Nothing is re-simulated and no number
on screen is invented: captions quote the trace columns or the verdict JSONs
in `media/data/verdicts/`.

| slot | t in video | what fills the frame | source data / command | caption (burned in) |
|---|---|---|---|---|
| hook | 0.0–2.0 s | the RP1 standing, mid push-recovery pose | `traces/good` @ t=5.15 s | "RP1 humanoid — stands, and takes a 30 N push" |
| input -> output | 2.0–6.0 s | the judged episode: prompt + spec left, real render right; camera dolly-in | `traces/good` t 0.3–3.3 s | "write controller.py — stand 10 s, survive a 30 N push" |
| stand (2x) | 6.0–12.0 s | the good controller standing | `traces/good` t 3.0–6.0 s | "good controller — standing (2.0x real time)" |
| push (real time) | 12.0–17.0 s | the 30 N push at t=5, the lean, the recovery; tilt readout live | `traces/good` t 7.0–12.0 s (= sim 4.5–9.5) | "30 N push at t=5 s — real time" + live t / tilt |
| recovery (annotate) | 17.0–20.5 s | slow push window, close view | `traces/good` t 4.7–8.2 s | "tilt peaks, then back under 5 deg by t=7 s — the push gate" |
| verb / verdict | 20.5–23.5 s | verdict card over a frozen render | `verdicts/good.json` | "PASS — all 10 judge gates (real grade.sh --json)" |
| mutant 1 | 23.5–28.5 s | **zero_torque** falls (u=0, the statics oracle) | `traces/zero_torque` t 0–5 s, real time | "mutant zero_torque — u=0; the judge's stand gate kills it" + failed-gate card |
| mutant 2 | 28.5–33.5 s | **no_balance** falls (balance law deleted) | `traces/no_balance` t 0–5 s | "mutant no_balance — deletes the balance law; stand + push fail" |
| mutant 3 | 33.5–38.5 s | **weak_balance** survives the push but does not recover enough | `traces/weak_balance` t 0.5–10 s (1.9x) | "mutant weak_balance — stands, but 7.2 deg > 5 deg after the push; push gate fails" |
| proof | 38.5–48.5 s | the kill matrix (all 10 gates), then the kill rate | `verdicts/*.json` via fig_loop.py | "self-test: 8/8 mutants killed — the known-good passes" |
| end card | 48.5–53.0 s | static end card | — | "try it: python3 cookbook/rp1-mujoco/run.py" |

Checks the cut is built against (`make_video.py` asserts them):

- first frame is the real 3D render (the hook), not a card — passes
  `video_gate.py`'s not-a-solid-colour check by construction; the script
  also asserts the decoded luma spread of frame 0.
- camera moves during the stand/push/recovery slots (azimuth/lookat sweeps)
  so the background never sits static during motion scenes.
- burn-in captions are >= 4 % cap-height of the 1080-px frame (>= 43 px);
  `make_video.py` draws at FS_BODY 34 / FS_BIG 46 on a 1920x1080 canvas
  (>= 3.1 % / 4.3 % of frame height) and verifies caption heights.
- last 2.5 s is one static end-card frame (video_gate's static-tail check
  passes); the script asserts the last 75 frames are identical.
- ffmpeg web encode: libx264 crf 18 -preset slow -pix_fmt yuv420p
  -movflags +faststart, from a lossless crf 0 master in media/master/
  (git-ignored); the script asserts 25 s <= duration <= 60 s and
  size <= 8 MB.
