# Media inspection

Inspected the final `result.png`, `loop.png`, and full-size video frames at
0.30, 3.65, 6.65, 11.53, 16.40, 21.60 and 24.00 seconds.
Regenerate them with `bash cookbook/sim-tuner/media/make_media.sh`.

- The hero uses actual MuJoCo renders, with default, tuned and truth columns,
  box and arm close-ups, the measured held-out errors and the 0.025 pass line.
- The loop figure labels the inherited CPU search honestly. Its history and
  final rounded-artifact score are distinct; all eighteen real mutant failures
  appear alongside it.
- The video opens on three physical box close-ups, not a title or terminal.
  The box close-up, arm close-up and overhead held-out command are visible.
  Captions and role colours remain consistent.
- The opening already displays `PASS: tuned error 0.02206 < 0.025 limit`.
  The proof HUD reads `PASS 0.02206 < 0.025 held-out error` and
  `Judge rejected all 18 broken fits. CPU / GPU agree.` on the moving scene.
  The final frame shows the one-command launch.
- Limits: the calibrated and truth poses are deliberately close. Differences
  are subtle at full-rig scale. Translucent target ghosts make the box gap
  visible, but coincident surfaces can produce colour artifacts. An arm tip
  can leave a panel during a wide shot. Camera motion contributes to the
  motion-gate score. This is not
  hardware footage or evidence that every parameter is visually identifiable.

## Mechanical and physics checks

25 s, 1920×1080, 30 fps, H.264 yuv420p, faststart, 7,026,691 bytes.
`video-gate.json` passes every check: 1.2 cuts per 10 s, motion fraction
0.5457, final static-tail YDIF 0.0001.
`data/render-checks.json` records exact-state checks without interpolation.
`collect.py` requires every CPU gate to equal the fresh lease receipt.

The independent panel is recorded in `REVIEW.json`, including its actual
review method and any unmet standard. Frame-sequence review is not native
full-frame-rate playback; no stronger claim is made.

## Independent panel result: not accepted

| blind model | craft | wow | clarity | payoff | muted |
|---|---:|---:|---:|---:|---|
| Opus 5.5 | 6 | 4 | 6 | 0 s | yes |
| Gemini 3.1 Pro | 7 | 7 | 9 | 0 s | yes |
| required minimum | 8 | 7 | 7 | ≤ 2 s | yes |

The first Opus review exposed an unclear result; adding true-state ghosts,
cm gap readouts, closer cameras and an opening PASS improved that, but did
not meet the panel's craft/wow bar. Both final raw verdicts are retained,
including their inaccuracies and suggestions, not edited into a passing
score. In particular, converting normalized RMS into cm would be false
and was **not** done. GLM vision failed with HTTP 502 and supplied no score.

**The mechanical gate is green; the media standard is not. Keep this PR
draft.** Native video panel acceptance and independent README reproduction
remain pre-merge work.
