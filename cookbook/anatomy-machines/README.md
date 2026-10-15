# Anatomy machines — interactive isometric engine figure, judged headlessly

Showcases the [anatomy](https://github.com/wheresryan22/anatomy) agent
skill (MIT licence, pinned commit `e6600ffc4e8e`) — "describe a machine in
one line, get an interactive isometric illustration you can rotate and
inspect" — running end to end inside a disposable agent-next sandbox. The
artifact is one self-contained HTML file: a raw-WebGL isometric figure
of a four-stroke engine with shaded solid parts (per-part materials,
key/fill/hemisphere lighting, a thin edge overlay), drag-to-orbit
camera, clickable labelled parts, and a `?shot` showcase capture mode
(exploded view, gutter labels with leader lines) used for the gallery
media below. A judge the figure cannot fool decides whether it is real:
headless Chromium (Playwright 1.60.0 + Chrome Headless Shell
148.0.7778.96, sha256-checked, SwiftShader WebGL on CPU) drags the
canvas itself, screenshots the pixels, reads the parts list out of the
DOM, clicks every part, counts animation frames, and audits the capture
mode. A sandbox helps because the whole browser toolchain (~120 MB
download plus system libraries) is installed, run and thrown away
without touching your machine — no GPU, no X server.

Gates and thresholds are in [SPEC.md](SPEC.md); measured results and real
command output are in [RECEIPT.md](RECEIPT.md).

## Media

![Exploded view of the four-stroke engine with labels and the judge's
verdict band](media/result.png)

- [`media/result.png`](media/result.png) — the real figure exploded to
  72 %, labels with leader lines, plus the measured gate values.
- [`media/assembled.png`](media/assembled.png) — the same scene fully
  assembled (raw real screenshot).
- [`media/demo.mp4`](media/demo.mp4) — 21 s turntable +
  exploded-view animation, assembled from 630 real rendered frames
  (no interpolation), H.264 crf 18.
- [`media/loop.png`](media/loop.png) — the good figure plus all 7
  mutants against the 6 gates, from real verdict JSONs.
- [`media/MANIFEST.json`](media/MANIFEST.json) — sha256 + provenance;
  [`media/make_media.sh`](media/make_media.sh) regenerates everything
  (renders the real scene headless; data collection in
  [`media/collect_data.sh`](media/collect_data.sh)).

## What the judge saw

The judge's own canvas captures of a passing run (seed 42) are kept in
[`media/data/shots-good/`](media/data/shots-good/) (`angle_0..2.png`
after successive 240 px drags, `spin_*.png` mid-drag frames) alongside
the raw verdict JSONs.

- Canvas variance **1361 / 1328 / 1303** at the three angles (floor 50) —
  not blank.
- Rotation is real: **8.5 / 10.2** mean pixel difference and **9–11 %**
  of pixels changed between angles (floor 3.0 / 2 %).
- Parts recall **17/17** vs the textbook reference list
  (`judge/reference/four-stroke-engine.json`, sources cited inside);
  floor 0.8, zero duplicates.
- Clicking all 17 parts shows the name + description; **17/17** pass.
- Frame rate under SwiftShader on 2 vCPU: **~13–17 FPS** measured
  (floor 10).
- Capture mode audited: **1920 px** wide, **~13 %** non-background
  pixels (floor 8 %), **0** label-chip overlaps.
- Self-test kills **7/7** known-bad mutants (blank canvas, missing parts,
  console error, frozen camera, wrong labels, dead interaction,
  shrunken capture).

## Ask your agent

> Create a CPU sandbox. In it, clone https://github.com/agent-next/sandbox
> and run `bash cookbook/anatomy-machines/judge/setup.sh` to install the
> pinned headless-Chromium judge. Then, using the anatomy skill
> (https://github.com/wheresryan22/anatomy), build a figure directory for
> "a four-stroke engine": one self-contained HTML file with a WebGL
> isometric figure you can drag to orbit, a parts list of
> `data-part` elements, a `data-part-info` panel that shows each
> part's name and description on click, and a `?shot=1&labels=1&explode=0.7`
> showcase mode that renders the same scene fullscreen (shaded solids,
> `.lbl` label chips with leader lines, no page chrome or tooltips).
> Iterate with
> `bash cookbook/anatomy-machines/judge/grade.sh <your-figure-dir>` until
> every gate passes. Report the final verdict JSON and kill the sandbox
> when done.

## One-command run (with sandbox API)

```bash
export SBX_API_KEY=<your key>
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
python3 cookbook/anatomy-machines/run.py        # add --ref <branch> or --keep
```

`run.py` creates a sandbox, clones this repo at `--ref` (default `main`),
runs `judge/setup.sh`, `judge/selftest.sh`, grades the known-good figure,
prints the verdict JSON, and kills the sandbox (verifying it is gone)
unless `--keep` is given.

## In-sandbox / no API key (any Debian 12 box, 2 vCPU, ~3 GB RAM)

```bash
# 1. Install the pinned judge toolchain (~40 s warm mirror)
bash judge/setup.sh

# 2. Self-test: proves the judge can fail (good + 7 mutants, ~5 min)
bash judge/selftest.sh

# 3. Grade the known-good figure (seed 42 for reproducibility)
bash judge/grade.sh examples/good/four-stroke-engine \
    --json /tmp/verdict.json --seed 42

# 4. Regenerate the media (real judge data, then the headless render)
bash media/collect_data.sh   # ~6 min: selftest + verdict JSONs + shots
bash media/make_media.sh     # renders the real figure, encodes demo.mp4
```

### `judge/grade.sh` flags

| flag | purpose | example |
|---|---|---|
| `--json FILE` | write verdict JSON to `FILE` | `--json /tmp/v.json` |
| `--seed N` | seed recorded in the verdict JSON | `--seed 42` |
| `--shots DIR` | save the canvas screenshots the judge takes (3 angles + an 8-frame drag series) | `--shots /tmp/shots` |

The judge is deterministic at any fixed seed: SwiftShader renders
identically and the drags are scripted pixel-exact. Only wall time and
measured FPS (under `timing`) vary between runs.

## Measured wall times (2 vCPU, Debian bookworm, this sandbox)

| step | wall time |
|---|---|
| `judge/setup.sh` (cold, incl. ~119 MB browser download) | ~40 s |
| `judge/selftest.sh` (2 good grades + 7 mutants) | ~5 m |
| `judge/grade.sh examples/good/four-stroke-engine` | ~40 s |
| `media/collect_data.sh` (selftest + verdicts + shots) | ~6 m |
| `media/make_media.sh` (630 real frames + encode) | ~30 m |

## Sources and credit

- Upstream project: **anatomy**, https://github.com/wheresryan22/anatomy,
  MIT licence, pinned commit
  `e6600ffc4e8e6620eeb45bf49bcdbd5e4b84163f` (licence vendored at
  `judge/anatomy-upstream/LICENSE`).
- The reference parts list is a standard textbook four-stroke
  description (Heywood, *Internal Combustion Engine Fundamentals*, ch. 1.2
  — cited in `judge/reference/four-stroke-engine.json`).
- The known-good figure was written for this demo in the kit's format;
  the judge cares only about the DOM contract in SPEC.md, not who drew
  the engine.

## Limits

- SVG/isometric figures only — upstream's beta 3D mode is out of scope.
- Only `four-stroke-engine` ships as a graded machine; adding another
  means writing `judge/reference/<machine>.json` from a cited source.
- The judge grades the DOM contract, not the drawing's engineering
  fidelity — it verifies a real rotating labelled WebGL figure, not that
  every wire is in the right place.
- `run.py` needs the `sbx` CLI and `SBX_API_KEY`; without them use the
  in-sandbox commands above.
