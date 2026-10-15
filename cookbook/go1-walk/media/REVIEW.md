# Close-tracking recut review, 2026-10-15

This review supersedes the previous 7,200,578-byte cut. The current video
is **7,262,402 bytes**, 30 s, 1920×1080, 30 fps, H.264 yuv420p with
faststart. It uses CRF 22/preset slow/animation tuning from a CRF 0
lossless master.

## Builder visual inspection

Extracted every second of the **decoded final web encode** using
`ffmpeg -i demo.mp4 -vf fps=1`, then opened all 30 frames in five
high-resolution, six-frame contact sheets. Inspected the earlier
full-size close-up and gate/HUD compositions too.

| Video seconds | What I saw |
|---|---|
| 0–4 | A large orange-and-blue Go1 already walking in frame one. Each sampled frame has a new leg pose, shadow and floor position. The 0.768 m/s and falls 0/192 headline is readable muted. |
| 5–7 | A close side-angle walk, with only the measured 486.1 s PPO / 4 GiB training caption. No tiny plot, terminal, or telemetry card. |
| 8–9 | An actual random-initialization tumble on a charcoal floor. The shot cuts at the first failed control step, not after a frozen hold. |
| 10–13 | Seed 202 walks from the saved scored states. The 0.770 m/s, falls 0/64 caption stays separate from the moving legs. |
| 14–17 | Seed 303 walks from another close angle. Caption: 0.761 m/s, falls 0/64. |
| 18–23 | The robot keeps walking on the left. Five gate checks draw in individually on the right. The HUD does not cover the trunk or the gait. |
| 24–27 | The robot keeps walking. Plain-language broken-policy explanation, actual 11/11 result, and successively drawn checkmarks. No mutant jargon. |
| 28–29 | The single static final simulator frame, exact command, “GPU released after the run.” The end card begins at 27.5 s. |

Rejected the old slide-like specification/proof layouts and the 3 s
static tail. There are no pre-end-card stills, screenshot pans, image
zooms, plots, or text-only cards in this recut. The hero is a true MuJoCo
tracking camera bound to the trunk, at 0.98 m rather than the old 1.45 m.
The more distant shots remain within 1.15 m.

The primitive model and foot-only contacts remain unchanged. Charcoal
floor material, lighting/shadow resolution, camera angles and the gate
shot's sideways camera offset are render-only. No flattering episode
selection, replacement poses, retraining, or new grading took place.

## Machine evidence

`bash cookbook/go1-walk/media/make_media.sh --render-only` exited 0:
**9 media tests passed**. All **831 rendered views** match the original
judge qpos and qvel to 1e-9. The model, checkpoints, traces, trained and
untrained verdicts, and mutation self-test remain unchanged.

The unchanged upstream video gate passed all 16 checks:

| Check | Measured |
|---|---:|
| Duration | 30.0 s |
| Resolution / frame rate | 1920×1080 / 30 fps |
| Web size | 6.926 MiB, strictly below 8,000,000 bytes |
| Detected cuts per 10 s | 1.0 |
| Motion fraction | 0.9249 |
| Final 2 s mean luma difference | 0.0005 |
| Faststart | moov@32 before mdat@9436 |

The new tracking-camera regression test rejects the old free-camera
renderer with the explicit assertion “video camera must track the trunk
body”; the current renderer passes. The scene-schedule test also checks
every pre-card frame advances to a different scored state and never
replays past a fall.

### Resumed-worker verification

Kept the inherited renderer and final encode after inspecting their full
diff and source hashes. Reran the required gate suite: **20 passed**
in 1085.15 s. The final MP4 again passed all 16 gate checks with the
values above. All **9 media tests** and **16 Go1 regression tests**
passed in the existing pinned render environment.

Independently extracted another 30 decoded 1 fps frames and opened all
five contact sheets. The opening walk is already readable, the falling
comparison changes pose, and the gate and self-test overlays leave the
moving robot visible. No slide-like pre-card shot was accepted.
Temporary review frames and the verified upstream gate-tool copies were
removed after verification; cached scored states and the lossless master
remain available for rebuilding.

## Blind panel status

The owner's prior cut scored Gemini 8/7/8 and Opus 7/6/7. This recut
addresses the named issues, but **Gemini/Opus have not rescored it**.
No builder score or code-review result is claimed as a blind-panel pass.
The older reviews in `REVIEW.json` concern a superseded encode.

## Deviations

- Neither Remotion nor HyperFrames was installed; used the explicitly
  allowed existing MuJoCo/Pillow/ffmpeg compositor.
- CRF 18 produced an 11,996,858-byte first candidate. CRF 22 keeps the
  full-motion recut below the owner's strict 8 MB limit. The lossless
  master, 1080p30 output and original measured results are retained.
- This branch predates `cookbook/tools/`. Verification temporarily used
  the unchanged `video_gate.py` and `test_video_gate.py` from upstream
  commit `ecfbcfa1f67718a55a651e487b149be686ca0712`, without changing
  thresholds or adding unrelated tool sources to the PR.
