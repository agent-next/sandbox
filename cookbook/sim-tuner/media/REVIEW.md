# Media inspection

The recut replaces the old three-panel comparison with one close, overlaid
MuJoCo view. Orange default outlines visibly overshoot the solid teal box
and white truth outlines. Traces use actual past positions, not decorative
curves. Surface outlines eliminate coplanar-face flicker without modifying
geometry or physics.

All four held-out tests play in descending maximum box-miss order,
sequentially labelled 1/4 through 4/4. The receipt preserves their original
recording identities. The subsequent arm view and box proof replay test 1/4.
The five-parameter HUD names each quantity, gives its units, and shows the
actual default, tuned and truth values. The shot advances one exact graded
state per video frame, labelled 0.06x speed. Every video caption has at
least 44 px cap height at 1080p, checked by the media tests.

Every second before the sole 2.2 s end card is moving real 3D output.
There are no slides, still plots, screenshots, Ken-Burns moves or invented
search captures. The aggregate error remains normalized RMS, not cm;
the separately labelled live misses are horizontal box distances.

Regenerate with `bash cookbook/sim-tuner/media/make_media.sh`.
The script extracts one frame per second to `.frames/review-*.png`.
`video-gate.json` records mechanical checks; `data/render-checks.json`
binds the trajectory hash, state indices and exact-state assertions.
`DEVIATIONS.md` records the compositor fallback and validation retries.

## Final inspection and checks

Opened every extracted one-second frame, `review-01.png` through
`review-26.png`. The first 24 show changing real 3D views, poses and traces;
none is a slide, still plot or screenshot. The final two show the sole
static end card. The default/truth box gap is visible directly in the
overlaid geometry, not only in the readout. The actual arm discrepancy is
smaller and is not exaggerated.

- `make_media.sh`: exit 0.
- Final media contracts: 16 passed. Full demo regression run: 44 passed;
  the standalone rendered-job check also passed.
- 26.2 s, 1920×1080, 30 fps, H.264 yuv420p, faststart,
  **7,911,485 bytes**.
- Video gate: all checks pass; motion **0.7821**, cuts per 10 s
  **1.9084**, static-tail YDIF **0.0014**.
- 3,663 exact rendered-state checks, no interpolation; the source array
  SHA-256 and complete shot indices are in `data/render-checks.json`.

## Panel status

**Pending a new blind panel from the lead.** `REVIEW.json` is bound to
the new video hash and contains no verdicts copied from the previous cut.
A green mechanical gate is not blind-panel acceptance. Keep the PR draft.
