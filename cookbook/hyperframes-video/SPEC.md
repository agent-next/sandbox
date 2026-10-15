# SPEC: agent-written HTML composition rendered to MP4 with HyperFrames

## Goal

Demonstrate an agent-next sandbox turning a short product-teaser brief
(`brief.md`) into a [HyperFrames](https://github.com/heygen-com/hyperframes)
composition — plain HTML/CSS/JS with `data-*` timing attributes and a
paused, seekable GSAP timeline — and rendering it headless to MP4, graded
by a judge the agent cannot fool.

Pinned upstream: `hyperframes` npm package **0.8.61** (published
2026-09-22, Apache-2.0), installed through a committed
`judge/package-lock.json` (every transitive dependency pinned with its
registry integrity hash); the tarball sha256 is recorded in
`judge/npm-sha256.txt` and checked by `judge/setup.sh`.

The scenario: an agent reads `brief.md` (a 20 s teaser: title beat,
3 feature beats, end card, brand colours), writes `composition/index.html`,
and renders `output.mp4`. Every fact the judge checks (duration,
resolution, fps, beat texts, beat timestamps, brand colours) comes from a
machine-readable `spec.json` the agent writes from the brief — the judge
never hard-codes content that the artifact can rewrite.

## Non-goals

- Audio tracks (the good example is silent; the judge does not listen).
- Live-preview workflows (`hyperframes preview`) or cloud/Lambda rendering.
- Teaching composition aesthetics; the judge checks the brief on screen,
  not taste.
- HyperFrames versions other than the pinned 0.8.61.
- Anything outside `composition/` + `spec.json`: the artifact is a plain
  directory; the judge brings its own Node, Chrome Headless Shell,
  FFmpeg and tesseract.

## Artifact

```
<artifact>/
├── spec.json          # machine-readable brief the agent derived
└── composition/
    └── index.html     # HyperFrames composition (may add assets/*.js, css)
```

`spec.json`:

```json
{
  "title": "Aurora Notes",
  "duration_s": 20,
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "brand_colors": ["#4F46E5", "#F59E0B"],
  "beats": [
    {"label": "title", "text": "Aurora Notes", "start_s": 0.4, "hold_s": 2.6},
    {"label": "beat1", "text": "Capture ideas in one keystroke", "start_s": 3.4, "hold_s": 4.0},
    {"label": "beat2", "text": "Sync across every device",      "start_s": 7.8, "hold_s": 3.8},
    {"label": "beat3", "text": "Search everything instantly",    "start_s": 12.0, "hold_s": 4.0},
    {"label": "endcard", "text": "Try it free today",            "start_s": 16.4, "hold_s": 3.4}
  ]
}
```

Rules the artifact must satisfy (validated before grading; invalid input
is rejected, not clamped):

- `duration_s` in [20, 30]; `width` in [320, 7680]; `height` in [320, 4320];
  `fps` one of 24, 30, 60; beats in on-screen order, non-overlapping,
  `start_s + hold_s <= duration_s`.
- `brand_colors`: 1–4 colours, each `#RRGGBB`.
- `composition/index.html` must declare a stage with `data-composition-id`,
  `data-start="0"`, and `data-duration` equal to `duration_s`. A
  composition whose JS throws fails gate 1 (the render fails).
- The composition may not fetch anything over the network: the good
  example vendors `gsap.min.js` (pinned by `judge/setup.sh` into the
  render copy); a composition that does not, fails gate 1 in an offline
  sandbox.

Known-good artifact: `examples/good/` (hand-written against
`examples/good/brief.md`).

## Gates (numeric pass rules)

`judge/grade.sh <artifact> --seed N [--json out.json]` copies the artifact
to a scratch dir, renders it twice, and evaluates every gate; a single
verdict JSON lists each gate with its measured numbers.

### Gate 1 — render
- `hyperframes render` exits 0 within 15 min and produces `output.mp4`
  (the good example takes ~4 min on 2 vCPU at 1920×1080/30 fps).

### Gate 2 — container format (ffprobe)
- Duration within ±0.11 s of `spec.duration_s` (frame quantisation:
  HyperFrames emits exactly `round(duration*fps)` frames — measured
  20 s in → 20.000000 s / 600 frames out at 30 fps).
- Resolution exactly `width`×`height`; fps exactly `spec.fps`.
- Video codec `h264`, pixel format `yuv420p`.

### Gate 3 — beat text on screen (tesseract OCR)
- For each beat: sample the frame at `start_s + hold_s/2` (ffmpeg) and OCR
  it with tesseract 5.3.0. OCR is run on three rendered variants of the
  same frame — raw (2× lanczos upscale), light-text (luminance ≥ 200
  thresholded to black-on-white) and dark-text (luminance ≤ 80,
  inverted) — because a valid teaser may put white text on a brand-coloured
  band or dark text on a light card, and tesseract alone misses the first
  (measured: raw OCR read the title but not the white-on-indigo band).
- Pass if **any** variant, normalised (lowercase, keep letters/digits),
  contains ≥ 0.9 of the beat `text`'s character 3-grams (containment
  |OCR∩text|/|text| — extra on-screen text such as the end card's product
  name must not dilute the match; a symmetric Jaccard was measured to fail
  exactly that valid case at 0.52). A missing or garbled beat fails every
  variant.

### Gate 4 — no black gaps, no frozen holds (ffmpeg filters)
- `blackdetect` (pic_th 0.98): no black interval longer than 0.5 s.
- `freezedetect` (n=0.001): no frozen interval longer than 2.0 s — the
  brief demands continuous motion, so no hold exemption is granted
  (measured: the good example's animated progress bar keeps every frame
  changing; an earlier static-text version froze 3.6 s per beat and was
  rejected by this gate).

### Gate 5 — brand colours on screen
- For each sampled beat frame (one per beat) and each declared brand
  colour: the share of pixels within CIE76 ΔE ≤ 25 of that colour must be
  ≥ 1.0 % (frames downscaled to 160×90 by ffmpeg before measuring).
  Measured on the good example: indigo 1.8–12.6 %, amber 1.5–9.2 % per
  frame — the gate threshold has ≥ 1.5× headroom against the weakest
  frame and a rotated-palette mutant measures ~0 %.

### Gate 6 — frame motion (sampled frame diffs)
- The judge samples render 1 on a 0.5 s grid, downscaled to 320×180 gray.
  A consecutive pair "moves" when ≥ 0.4 % of pixels differ by more than
  24 gray levels — real motion (typing, counters, transitions, drifting
  geometry), not encoder noise. Pass requires ≥ 60 % of pairs to move.
  Rationale: `freezedetect` counts *any* pixel change, so a composition
  with a tiny decoy element can keep it quiet while every hold is
  visually static — this gate measures *meaningful* change. Measured on
  the good example: 39/39 pairs move; the `static-composition` mutant
  (a 50 px teleporting square) moves ~5/39 and is killed here only.
  Reported as `moved_pct` quantised to 10 % (verdict determinism).

### Gate 7 — no text overflow (DOM audit in headless Chrome)
- The judge injects an audit script into a scratch copy of the
  composition, loads it in the pinned chrome-headless-shell
  (`--dump-dom`, virtual-time), seeks `window.__timelines.main` every
  0.2 s across the whole duration, and inspects every text-bearing
  element (a direct non-whitespace text node) that is effectively visible
  (combined opacity ≥ 0.5, not `display:none`). A violation is a box
  leaving the stage by > 2 px, or an element with `overflow:hidden/clip`
  whose scroll size exceeds its client size by > 2 px. Pass requires
  **zero violations**. Measured: the good example reports 991 element
  checks, 0 violations; the `text-overflow` mutant (170 px headline +
  clipped typed line) reports 52.

### Gate 8 — determinism (two renders, self-compared)
- HyperFrames is **not** byte-deterministic on this stack (measured: two
  renders of the same composition, sha256 `9d7665d3…` vs `87d45642…`).
  The gate is the documented fallback: the judge's two renders must reach
  **SSIM (All) ≥ 0.995 and PSNR ≥ 40 dB** over the full frame sequence
  (measured on the good example: SSIM 0.999988, PSNR 74.2 dB). A
  composition that reads wall-clock time, `Math.random()` or network
  state renders visibly different passes and fails here; so do two renders
  of different duration, which make the ssim filter itself error out.
  Gate 8 runs only when gates 1–7 all pass (the second render is skipped
  once the artifact is already dead, saving ~4 min).

## Acceptance oracle

- Gates 2–4 oracles are `ffprobe`/`ffmpeg` measurements of the rendered
  file against numbers in the artifact's own `spec.json`, which the judge
  validates (schema + ranges) **before** grading.
- Gate 3's oracle is OCR of frames the harness itself decodes, fuzzily
  matched against the brief text; the threshold tolerates font-raster
  noise while failing a missing or wrong beat.
- Gate 5's oracle is perceptual distance to the declared brand colours in
  frames the harness itself decodes.
- Gate 6's oracle is frame-to-frame pixel change in frames the harness
  itself decodes.
- Gate 7's oracle is the DOM audit the harness itself runs inside the
  pinned chrome-headless-shell on a scratch copy of the composition.
- Gate 8's oracle is a second render the judge makes itself.

Nothing passes because "it rendered" — a black screen renders fine and
fails gates 3–5.

## Mutants (`judge/mutants.py`)

Single-edit mutants of `examples/good/`, generated into `examples/bad/`
(gitignored):

1. `wrong-duration` — stage `data-duration` 16 s, spec keeps 20 s.
2. `missing-beat` — beat 2 element removed from the DOM (spec keeps it).
3. `black-gap` — 1.5 s all-black interval inserted via an opaque overlay.
4. `wrong-resolution` — stage rendered at 640×360, spec keeps 1920×1080.
5. `off-brand-colors` — brand colours rotated to non-brand values.
6. `broken-js` — `window.__timelines` never registered; render fails.
7. `frozen-video` — the motion script is swapped for instant opacity
   toggles; static holds freeze past the gate 4 limit (gate 6 also kills
   it).
8. `nondeterministic` — a `Math.random()`-driven jitter on the timeline;
   two renders diverge, SSIM drops below the gate.
9. `static-composition` — same static timeline as `frozen-video` plus a
   60 px square teleporting every 0.5 s: enough per-frame change to keep
   `freezedetect` quiet, but under gate 6's meaningful-diff floor — gate
   6 is its only killer.
10. `text-overflow` — headline font tripled so words leave the stage, and
    the typed line clipped by a fixed-width `overflow:hidden` box — gate
    7 reports dozens of violations.

Selftest requires the good example to pass and kill rate ≥ 9/10 (≥ 90 %).
