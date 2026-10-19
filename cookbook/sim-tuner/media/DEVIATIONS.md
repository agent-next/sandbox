# Recut deviations log, 2026-10-15

- **Compositor fallback:** neither Remotion nor HyperFrames is installed
  (CLI, global packages or locally resolvable modules). Used the existing
  MuJoCo + Pillow + ffmpeg compositor, as the owner permits. No plotting
  library, still-image animation, fabricated rollout or search capture.
- **Evidence reused, not re-judged:** the accepted fresh-lease GPU gate and
  18/18 self-test evidence remain unchanged in `data/run-1.json`.
  `collect.py` runs CPU grading again and requires G1–G3 to equal that
  receipt. This recut does not claim another fresh GPU run.
- **Presentation selection:** all four actual unseen recordings remain in
  the video, ordered by their maximum default/truth horizontal box gap.
  Labels 1/4 through 4/4 denote that presentation order, not new recordings.
  No displacement, time interpolation or physics parameter was exaggerated.
- **Standard process slot:** no sped-up agent screen recording is included.
  The owner's moving-MuJoCo-only rule takes precedence. The real historical
  CPU search and mutant matrix remain in `loop.png`; the proof rides on
  moving 3D output.
- **Validation retry:** one HUD test initially read `trajectories.npz`
  while the media build was rewriting it (14 passed, one `BadZipFile`).
  Running after capture completed passed all 15 then-current media tests.
  This was a validation scheduling error, not accepted as a passing check.
- **Rejected first full encode:** `make_media.sh` exited 1. Motion was
  0.1254 and cut density 0.6623 per 10 s, both below the mechanical gate.
  A real 120-degree close-camera orbit tested at 1.0 opening-shot motion.
  The recut uses that orbit and higher-contrast studio floors between
  actual shots. These are rendering changes, not modified trajectories.
- **Web budget:** simplified the real floor material and shortened each
  box shot from five to four seconds. The resulting 26.2 s cut retains
  all four tests, all five parameter comparisons, the arm command and
  the 2.2 s end card. Encoding remains CRF 18 / preset slow, not a reduced
  quality setting used to hide an oversized render.
- **Command spelling:** the literal `python .../video_gate.py` check
  could not start because this host has no `python` executable on PATH
  (exit 127). Used `python3` for the same unchanged gate, as
  `make_media.sh` does.
- **Panel authority:** the previous cut's failed verdicts are invalidated,
  not converted into passing scores. The new hash is pending a fresh blind
  panel from the lead. No merge or media-panel acceptance is claimed.

## Final verification

`make_media.sh` exited 0. The 26.2 s web encode is 7,911,485 bytes;
the video gate passes with 0.7821 motion and 1.9084 cuts per 10 s.
All 26 one-second frames were opened and inspected. Only the 2.2 s end
card is static. The final media suite passes 16 tests; the full demo
regression run passed 44 tests and the standalone rendered-job check.
Removed generated review frames, preview experiments and intermediate
clips after inspection. Retained the lossless master and captured inputs.
