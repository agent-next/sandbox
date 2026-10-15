# REVIEW — anatomy-machines media

How the media was produced and what was checked by eye. All inputs come
from real judge runs; `media/collect_data.sh` regenerates `media/data/`
and `media/make_media.sh` regenerates the renders, figures, video and
manifest.

## Provenance of the numbers

- `media/data/verdict-*.json` — real `judge/grade.sh --seed 42 --json`
  output for `examples/good` and for each of the 7 artifacts generated
  by `judge/mutants.py`, preserved from a real `judge/selftest.sh` run
  (`SELFTEST_OUT`). Every gate value drawn in `result.png`'s verdict
  band and every `loop.png` cell is read from these files.
- `media/data/selftest.log` — real `judge/selftest.sh` output:
  good figure passes, same-seed verdicts byte-identical outside
  `timing`, 7/7 mutants killed.
- `media/data/shots-good/` — the judge's own gate-2 canvas screenshots
  of the good figure (`grade.sh --shots`): `angle_0..2.png` after three
  240 px drags, `spin_00..07.png` mid-drag.
- `result.png` — the photo is `media/master/exploded.png`, a real
  Playwright screenshot of `four-stroke-engine.html` at
  `?shot=1&labels=1&explode=0.72&yaw=35` in Chrome Headless Shell +
  SwiftShader at 1920×1080 (`render_media.py`); `fig_result.py` appends
  the verdict band below it.
- `assembled.png` — a raw real screenshot of the same scene at
  `explode=0`, no annotation.
- `demo.mp4` — 630 real `#stageView` screenshots (30 fps × 21 s):
  `render_media.py` drives `__fig.set({yaw, explode, labels})` along a
  fixed timeline (assembled turntable → explode → labelled hold →
  reassemble) and screenshots each step. Encoded from a lossless
  `-crf 0` master (`media/master/master.mp4`, git-ignored) to
  `-crf 18 -preset slow -movflags +faststart`. No synthesized or
  interpolated frames; no hover tooltips (`?shot` hides them).
- `loop.png` — mutant × gate matrix drawn by `media/fig_loop.py` from
  `verdict-*.json`; red cells show the measured value that broke the
  gate.

## What was checked by eye

- `result.png` at full size: exploded engine readable at 1920 px,
  per-part material colours, labels in both gutters with leader lines,
  no chip overlaps, no page chrome or tooltips.
- `assembled.png`: the same 17 parts fully nested — piston inside the
  cylinder, head closed, manifolds seated.
- `demo.mp4` scrubbed: smooth turntable, monotonic explode/reverse,
  label fade-in only during the exploded hold, no torn frames.
- `loop.png`: 8 rows × 6 gates; each mutant row red in the gate(s) its
  single edit targets (`blank_canvas` 2+6, `missing_parts` 3,
  `console_error` 1+2+3+4+6, `static_camera` 2, `wrong_labels` 3+4,
  `no_interaction` 4, `tiny_capture` 6).

## Deliberate choices

- Capture resolution is 1920×1080 and the gate-6 floor is 1280 px:
  `tiny_capture` shrinks the stage to 40 % (≈768 px) and fails on width
  alone.
- The gate-6 non-background floor is 8 %: the good figure measures
  ~13 %; a flat-colour page or the old sparse wireframe scores near
  zero.
- `media/.venv` (matplotlib, `requirements.txt`) is local to media and
  git-ignored; the render itself reuses the pinned judge venv.
