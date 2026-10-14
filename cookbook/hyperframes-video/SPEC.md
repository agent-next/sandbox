# SPEC: agent-written HTML composition rendered to MP4 with HyperFrames

## Goal

Demonstrate an agent-next sandbox turning a short product-teaser brief
(`brief.md`) into a [HyperFrames](https://github.com/heygen-com/hyperframes)
composition — plain HTML/CSS/JS with `data-*` timing attributes and a
paused, seekable GSAP timeline — and rendering it headless to MP4, graded
by a judge the agent cannot fool.

Pinned upstream: `hyperframes` npm package **0.8.61** (published
2026-09-24, Apache-2.0), installed from the npm registry with an exact
version pin; the tarball sha256 is recorded in `judge/npm-sha256.txt` and
checked by `judge/setup.sh`.

The scenario: an agent reads `brief.md` (a 24 s teaser: title beat,
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
- Node.js installed in the sandbox at render time: the whole toolchain
  (Node 22 + Chromium + hyperframes engine) runs **on the host** against
  `localhost` URLs; the media inside the sandbox is served over HTTP.
  This demo's judge runs everything in the sandbox itself — the good
  example ships a `composition/` directory only.

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
  "duration_s": 24,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "brand_colors": ["#4F46E5", "#F59E0B"],
  "beats": [
    {"label": "title", "text": "Aurora Notes", "start_s": 0.5, "hold_s": 3.0},
    {"label": "beat1", "text": "Capture ideas in one keystroke", "start_s": 4.0, "hold_s": 4.0},
    {"label": "beat2", "text": "Sync across every device",      "start_s": 9.0, "hold_s": 4.0},
    {"label": "beat3", "text": "Search everything instantly",    "start_s": 14.0, "hold_s": 4.0},
    {"label": "endcard", "text": "Try it free today",            "start_s": 19.0, "hold_s": 4.0}
  ]
}
```

Rules the artifact must satisfy:

- `duration_s` in [20, 30]; `width` in [320, 7680]; `height` in [320, 4320];
  `fps` one of 24, 30, 60; beats in on-screen order, non-overlapping,
  `start_s + hold_s <= duration_s`.
- `brand_colors`: 1–4 colours, each `#RRGGBB`.
- `composition/index.html` must declare a stage with `data-composition-id`,
  `data-start="0"`, and `data-duration` equal to `duration_s`. The stage's
  JS globals must not be overridden after `index.html` loads except through
  registered adapters (checked by rendering; a composition that throws
  fails gate 1).

Known-good artifact: `examples/good/` (hand-written against
`examples/good/brief.md`).

## Gates (numeric pass rules)

`judge/grade.sh <artifact> --seed N [--json out.json]` copies the artifact
to a scratch dir, renders it once, and evaluates every gate against that
single render.

### Gate 1 — render
- `hyperframes render` exits 0 within 15 min CGROUP-limited and produces
  `output.mp4`.

### Gate 2 — container format (ffprobe)
- Duration within ±0.11 s of `spec.duration_s` (frame-quantisation at 24 fps;
  HyperFrames emits exactly `round(duration*fps)` frames — measured 7.3 s in →
  7.3 s out at 30 fps).
- Resolution exactly `width`×`height`; fps exactly `spec.fps`.
- Video codec `h264`, pixel format `yuv420p`.

### Gate 3 — beat text on screen (tesseract OCR)
- For each beat: sample a frame at `start_s + hold_s/2`, OCR it, normalise
  (lowercase, collapse whitespace) and require character 3-gram Jaccard
  similarity ≥ 0.9 against the beat `text`.

### Gate 4 — no black gaps (ffmpeg blackdetect)
- No `blackdetect` interval longer than 0.5 s over the whole video.

### Gate 5 — brand colours on screen
- For each brand colour: at least one sampled frame (one per beat) whose
  dominant colour is within CIE76 ΔE ≤ 25 of the brand colour; at least
  half the frames (rounded up) must show **some** brand colour within
  ΔE ≤ 25.

### Gate 6 — determinism
- The composition is rendered a second time in a fresh scratch dir; the
  two MP4s must be **byte-identical** (sha256 equal). Pinned hyperframes
  0.8.61 + the setup-pinned Chrome/libx264 + a GSAP-only composition gave
  byte-identical renders in the builder's measurements; a composition that
  reads wall-clock, `Math.random()` or network state at load fails here.

## Acceptance oracle

- Gates 2–4 oracles are `ffprobe`/`ffmpeg` measurements of the rendered
  file against numbers in the artifact's own `spec.json`, which the judge
  validates (schema + ranges) **before** grading — invalid input is
  rejected, not clamped.
- Gate 4's threshold and Gate 3's fuzzy match tolerate real rendering and
  font-raster noise while still failing a missing or wrong beat (mutant
  corpus proves it: kill rate ≥ 90 %).
- Gate 5's oracle is perceptual distance to the declared brand colours in
  frames the harness itself decodes.
- Gate 6's oracle is a second render the judge makes itself.

Nothing passes because "it rendered" — a black screen renders fine and
fails gates 3–5.

## Mutants (`judge/mutants.py`)

Single-edit mutants of `examples/good/`, generated into scratch:

1. `wrong-duration` — stage `data-duration` and `spec.duration_s` −4 s.
2. `missing-beat` — beat 2 element removed from the DOM (spec keeps it).
3. `black-gap` — 1.5 s all-black interval inserted via an opaque overlay.
4. `wrong-resolution` — stage and spec at 640×360 instead of declared.
5. `off-brand-colors` — brand colours rotated to non-brand values.
6. `broken-js` — `window.__timelines` never registered; render fails/times out at gate 1.
7. `wrong-fps` — spec/artifact fps 24 vs judge expectation path (fails gate 2 vs declared format only if inconsistent; the mutant declares 30 but renders content at mismatched duration timing).
8. `short-beats` — every beat `hold_s` shrunk so OCR samples land in fades (fails gate 3).

Selftest requires kill rate ≥ 7/8 and >= 90% overall with the good example
passing.
