# demo.mp4 storyboard — rp1-mujoco

900 frames at 30 fps = 30.0 s. Every robot frame is a real headless MuJoCo
render of the pinned RP1 scene (EGL on a host with a GPU, OSMesa software
rasterisation otherwise — `make_media.sh` picks), loaded with the exact
state the judge recorded at that instant (`media/data/traces/<name>/trace.csv`,
written by `grade.sh --trace`, seed 20261014). Nothing is re-simulated and
no number on screen is invented: captions quote the trace columns or the
verdict JSONs in `media/data/verdicts/`.

| slot | t in video | what fills the frame | source data / command | caption (burned in) |
|---|---|---|---|---|
| the result | 0.0–4.0 s | turntable orbit of the good controller standing at its final judged pose | `traces/good` @ t=9.9 s, 120 frames (`vid_render.py turntable`) | "RP1 humanoid — stands through a 30 N push" |
| the episode | 4.0–9.0 s | the judged episode t = 3.8–9.8 s real time, dolly-in, live t / tilt / pelvis-z readout, "30 N PUSH" flash in the push window | `traces/good`, 180 frames (`vid_render.py episode`) | "the judged episode — real time" + live readout |
| result card | 9.0–12.5 s | `result.png`, full frame (the render + every gate's trace vs its pass line) | `media/result.png` | "the judged run, and every pass line" |
| the mutant dies | 12.5–16.5 s | **zero_torque** collapsing from t = 0, live t / tilt / pelvis-z readout | `traces/zero_torque` t 0–2 s, 90 frames (`vid_render.py fall`) | "mutant zero_torque — the judge kills it"; "gate stand: z 0.051 m < 0.702 m" |
| loop card | 16.5–20.5 s | `loop.png`, full frame (agent-loop replay + the mutant × gate kill matrix) | `media/loop.png` | "the judge can fail: 8/8 mutants killed" |
| verdict card | 20.5–23.5 s | the 10 gates of `good` quoted in two columns: gate, measured, rule | `verdicts/good.json` | "judge verdict: PASS" + one cell per gate |
| end card | 23.5–30.0 s | static end card | — | "try it: python3 cookbook/rp1-mujoco/run.py" |

Checks the cut is built against (`make_video.py` asserts them):

- first frame is the real 3D render, not a card — passes `video_gate.py`'s
  not-a-solid-colour check by construction.
- the camera moves during every 3D slot (azimuth/distance/elevation
  sweeps in `vid_render.py`), so those sections carry real motion; the
  card slots are static stills between cuts.
- burn-in captions keep a cap height >= 4 % of the 1080-px frame
  (>= 44 px): `make_video.py` draws at FS_CAP 60 / FS_BIG 66 and verifies
  every caption's cap height, refusing to shrink a caption below the
  floor to make it fit.
- the last 6.5 s is one static end-card frame (video_gate's static-tail
  check); the script asserts all 195 end frames are byte-identical.
- ffmpeg web encode: libx264 crf 18 -preset slow -pix_fmt yuv420p
  -movflags +faststart, from a lossless crf 0 master in media/master/
  (git-ignored); the script asserts 25 s <= duration <= 40 s and
  size < 8 MB.
