# Media review

## Builder inspection, 2026-10-15

Opened `result.png` and `loop.png` at full size, and opened six frames
decoded from the final H.264 file at **0, 1, 4, 11, 25 and 28 seconds**.
These are the `media/work/review-*s.png` files written by
`make_media.sh`, not just the lossless render inputs.

- The hero figure contains six actual MuJoCo views: trained and random
  initialization, seeds 101/202/303 at 2/5/8 s. Speed and fall limits
  are readable. The figure is 2400 px wide, 200 dpi.
- The loop figure has the measured PPO curve, all five retained policy
  grades (including failures), and all eleven actual mutant kills.
  Labels, rows and the 90% pass line do not overlap.
- The video opens on a real walking robot. Orange body, blue legs,
  textured lit floor, visible contact shadows and sky give an
  unambiguous 3D scene.
- The comparison shows the trained gait and an actual random-init fall.
  “FALL / state frozen” explains the terminated episode. The model has
  foot-only contacts, so fallen non-foot geometry can intersect the
  floor. This is disclosed, not concealed with a replacement animation.
- The proof shot leaves the robot visible between the two readable HUD
  panels. Gate values and mutation names match the real JSON.
- The last three seconds are static and display the exact launch command.
  No title-only opening, fabricated conversation or fake terminal
  recording appears.

The shipped primitive collision geometry has a deliberately simple
appearance and a few self-shadow speckles. It is not a downloaded,
retouched or mesh-substituted robot.

### Resumed inspection of the final decoded frames

Opened both full-resolution figures and all six decoded 1920×1080 frames
again before publication:

| File / time | Visible content |
|---|---|
| `result.png` | Six lit, shadowed 3D robot views. The trained row is upright; the random-init row has fallen. Each tile names its seed, time, measured speed/falls and pass limits. |
| `loop.png` | Pillow-drawn PPO reward curve, five real policy grades and eleven killed-mutant rows. The kill-rate bar has a visible 90% pass line. |
| 0 s | Orange-and-blue 3D Go1 on the checker floor, with the walking-result headline and measured 0.768 m/s / 0.0% falls. |
| 1 s | A different leg pose and floor position under the same readable headline, with shadows below the feet. |
| 4 s | Real robot replay beside the command, held-out seeds and archived PPO telemetry. This is not a terminal recording. |
| 11 s | Seed-202 split view: trained robot upright on the left, random-init robot tipped into a frozen fall on the right. Speed and fall limits are unobstructed below both views. |
| 25 s | The trained robot remains visible between the five measured gate results and eleven rejected mutants. |
| 28 s | Final simulator still above the large one-command launch caption; no terminal or title-only replacement. |

## Automated checks

`bash cookbook/go1-walk/media/make_media.sh --render-only` exited 0:
six media tests passed. The web encode is **7,200,578 bytes**, 30 s,
1920×1080, 30 fps, H.264 yuv420p, CRF 18/preset slow with animation
tuning and faststart, derived from a CRF 0 lossless master.

Current-main `cookbook/tools/video_gate.py` passed every check:
1.3333 scene cuts/10 s, motion fraction 0.2217, and last-two-second
mean luma difference 0.0003. Exact-state checks cover **1176 rendered
views**; every qpos and qvel agrees with the saved judged state to 1e-9.
Rendering used EGL on NVIDIA RTX 5090, OpenGL 4.6, driver 580.95.05.

The media manifest binds every displayed metric to judge outputs,
checkpoint/model/trace hashes, source code and pinned render tools.
Uncompressed clips, master and decoded review frames are ignored.

## Blind panel

Two saved reviews used the current-main blind prompt and thirty sampled
frames, isolated from the README. Their raw answers and method are in
`REVIEW.json`. One scored quality/wow/clarity 8/8/9. The other scored
6/4/4 but described an opening terminal and eight seconds of logs that
do not exist in this video. Its account is inconsistent with the decoded
frames, so this is **not claimed as a passing blind panel**. Neither
review used native video playback. Continuous motion is checked
separately by the machine video gate. No builder score replaces either
saved answer.
