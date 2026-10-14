# SPEC: Anatomy machines — interactive isometric figure, judged headlessly

## Goal

Demonstrate the [wheresryan22/anatomy](https://github.com/wheresryan22/anatomy)
agent skill (MIT licence, ~9.9k stars) running end to end inside an
agent-next sandbox: an agent describes a machine in one line ("a four-stroke
engine"), the anatomy kit builds an interactive isometric illustration of it,
the sandbox serves it over HTTP, and a judge the figure cannot fool — headless
Chromium (Playwright 1.60.0, pinned) with SwiftShader WebGL on CPU — decides
whether the figure is real and correct.

The judge is fully headless and CPU-only: the demo must run on a 2 vCPU /
~3 GB sandbox with no GPU, no X server and no user watching.

## Non-goals

- The 3D mode (`turn.mjs`, beta upstream) — SVG/isometric figures only.
- Upstream's browser-checks / drive scripts — the judge has its own.
- Mobile browsers, dark/light theme both graded (light theme is graded; the
  kit renders both the same way).
- Machines other than the four-stroke engine in the graded artifact. The
  judge structure (`judge/reference/<machine>.json`) supports more, but only
  `four-stroke-engine.json` ships.
- Any LLM-in-the-loop judging: the judge is pure DOM/canvas pixel checks.

## Artifact

The agent's artifact is a **figure directory** — one self-contained HTML
file (plus nothing else) built with the pinned anatomy kit at commit
`e6600ffc4e8e` (MIT, LICENSE preserved at `judge/anatomy-upstream/`):

```
<figure_dir>/
└── four-stroke-engine.html   # self-contained: inline CSS+JS, no network
```

Required DOM contract (what the judge drives, as a user would):

- a `<canvas>` with a live WebGL context, >= 480 px wide and >= 360 px tall,
  rendering the machine as a rotatable isometric wireframe;
- camera rotation driven by pointer drag on the canvas and by the
  ←/→ keys;
- a parts list in the DOM: one element per part, carrying
  `data-part="<id>"`, whose text is the part's display name;
- clicking a `[data-part]` element selects that part: a
  `[data-part-info]` element then shows the part's name plus a
  description (>= 20 characters beyond the name);
- zero console errors on load.

The known-good artifact lives at `examples/good/four-stroke-engine/`.
`judge/grade.sh <figure_dir>` copies it to scratch, serves it over
`127.0.0.1` with Python's `http.server`, and never executes anything from
the artifact outside the browser.

## Judge gates (numeric pass rules)

All gates run in one Playwright pass over the served page, three fixed
camera angles per gate set (azimuth −30°, +30°, +90° from the figure's
default), `--seed` fixes every random choice (Playwright screenshots are
deterministic under SwiftShader at a fixed viewport).

- **Gate 1 — loads clean.** HTTP 200; the `<canvas>` exists, is
  >= 480x360 CSS px, and `canvas.getContext('webgl')` returns a context;
  console error count (severity `error`, plus uncaught page errors) == 0
  over the settle window.
- **Gate 2 — non-blank canvas that rotates.** The judge performs three
  identical pointer drags across the canvas (240 px in 12 steps) and
  screenshots the canvas after each. Per-pixel grayscale variance
  >= 50 (0–255 scale) at every angle (not blank), and between consecutive
  angles mean absolute pixel difference >= 3 **and** >= 2 % of pixels
  differing by more than 30 levels (rotation really changes the image; a
  sparse wireframe has a low mean but ~6 % of pixels move, while a frozen
  camera gives exactly 0).
- **Gate 3 — parts coverage vs a textbook reference.** The `[data-part]`
  names (casefolded, whitespace-trimmed) are matched against
  `judge/reference/four-stroke-engine.json` (16 reference parts from a
  standard textbook four-stroke description). Recall >= 0.8, and no
  duplicated names (a duplicate is a hallucination signal): duplicate
  count == 0.
- **Gate 4 — interaction.** Click every `[data-part]` element that matches
  a reference part: after each click, `[data-part-info]` innerText must
  contain the part's display name and >= 20 characters of description
  beyond it. All must succeed.
- **Gate 5 — frame rate.** `requestAnimationFrame` counted by the judge
  over a 3 s in-page window: FPS >= 10 (floor measured on the reference
  2 vCPU SwiftShader sandbox and recorded in `judge/VERSIONS.txt` and
  RECEIPT.md).

## Acceptance oracle

- Gates 2's threshold and gate 3's reference list are fixed by the judge,
  not by the artifact: the figure cannot tune itself under them.
- Gate 3's oracle is `judge/reference/four-stroke-engine.json`, a public
  textbook parts list (piston, crankshaft, connecting rod, …) written from
  standard four-stroke references (cited in the file); the judge recomputes
  recall from the DOM.
- Gate 5's floor (10 FPS) is a measured value: the good example measures
  ~2× above it on the reference 2 vCPU SwiftShader sandbox; the number is
  recorded in RECEIPT.md with the measurement command.

## Mutants (single-edit, judge/mutants.py)

Each is a copy of the good figure with one edit:

1. `blank_canvas` — CSS sets the figure background to flat white (gate 2).
2. `missing_parts` — registry reduced to 4 parts (gate 3).
3. `console_error` — page JS throws on load (gate 1).
4. `static_camera` — rotation controls disabled (gate 2's change check).
5. `wrong_labels` — every registry name replaced with `gizmo 1..n`
   (gate 3/4).
6. `no_interaction` — part elements lose their pointer events (gate 4).

A judge that cannot fail each of these is not done: `judge/selftest.sh`
must report a kill rate >= 90 %.

## Determinism and self-test

- Two grades at the same seed must produce byte-identical verdict JSON
  outside the `timing` key (checked by `judge/selftest.sh`).
- `judge/selftest.sh` grades the good example + all 6 mutants, prints the
  kill rate, and exits non-zero unless good passes, all mutants fail
  something, and determinism holds.
