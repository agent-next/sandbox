# HyperFrames video — agent-written HTML composition rendered to MP4

A disposable agent-next sandbox installs a pinned, sha256-checked copy of
[HyperFrames](https://github.com/heygen-com/hyperframes) **0.8.61**
(Apache-2.0, ~63.6k GitHub stars) — the open-source tool that renders an
HTML/CSS/JS composition to MP4 headless — plus its own Node.js, Chrome
Headless Shell, FFmpeg and tesseract. The scenario: an agent reads
`brief.md` (a 24 s product teaser: title, three feature beats, end card,
brand colours) and writes `composition/index.html` — a paused, seekable
GSAP timeline on `window.__timelines` — then renders `output.mp4` in the
sandbox.

The judge it cannot fool renders the composition **twice itself** and
checks: the MP4's duration/resolution/fps/codec against the brief
(ffprobe), every beat's text on screen at its timestamp (ffmpeg frame
grabs + tesseract OCR on three contrast variants), no black gaps > 0.5 s
and no frozen holds > 2 s (blackdetect/freezedetect), the brand colours
present in sampled frames (CIE76 ΔE), and that the two renders agree
(SSIM ≥ 0.995, PSNR ≥ 40 dB — HyperFrames is not byte-deterministic,
documented in [SPEC.md](SPEC.md)). Gates and numeric thresholds are in
[SPEC.md](SPEC.md); real command output is in [RECEIPT.md](RECEIPT.md).

The artifact under test is a plain directory:

```
<artifact>/
├── spec.json          # machine-readable brief (duration, fps, beats, colours)
└── composition/
    └── index.html     # HyperFrames composition
```

`examples/good/` holds a known-good artifact written by hand against
`examples/good/brief.md`.

## Ask your agent

> Create a CPU sandbox (2 vCPU, 4 GB RAM). In it, clone
> https://github.com/agent-next/sandbox and run
> `bash cookbook/hyperframes-video/judge/setup.sh` to install the pinned
> HyperFrames toolchain. Read `cookbook/hyperframes-video/examples/good/brief.md`
> and write an artifact directory (`spec.json` + `composition/index.html`)
> for the teaser it describes: a paused GSAP timeline registered as
> `window.__timelines["main"]`, stage `data-duration` matching
> `spec.duration_s`, every beat legible at its timestamp, brand colours on
> screen, and something moving in every frame. Vendor `gsap.min.js` — the
> composition must not fetch anything. Iterate with
> `bash cookbook/hyperframes-video/judge/grade.sh <your-artifact>` until
> every gate passes, report the final verdict JSON, and kill the sandbox.

## One-command run (with sandbox API)

```bash
export SBX_API_KEY=<your key>
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
python3 cookbook/hyperframes-video/run.py        # add --ref <branch> or --keep
```

`run.py` creates a sandbox, clones this repo at `--ref` (default `main`),
runs `judge/setup.sh`, `judge/selftest.sh`, then grades `examples/good`,
prints the verdict JSON, and kills the sandbox (verifying it is gone)
unless `--keep` is given.

## In-sandbox / no API key (run inside any Debian 12 box)

```bash
# 1. Install the pinned toolchain (needs passwordless sudo for apt)
bash judge/setup.sh

# 2. Self-test: proves the judge can fail (good + 8 mutants, ~25 min)
bash judge/selftest.sh

# 3. Grade the known-good artifact (seed 42 for reproducibility)
bash judge/grade.sh examples/good --json /tmp/verdict.json --seed 42
```

### `judge/grade.sh` flags

| flag | purpose | example |
|---|---|---|
| `--json FILE` | write verdict JSON to `FILE` | `--json /tmp/v.json` |
| `--seed N` | seed recorded in the verdict JSON | `--seed 42` |

The seed is recorded for reproducibility tracking; the judge measures
physical properties of the rendered file. Verdict detail numbers are
quantised on a documented grid (see `judge/check_gates.py`) so two grades
of equivalent renders produce byte-identical verdict JSON outside the
`timing` key.

## Measured wall times (2 vCPU, ~4 GB RAM, Debian bookworm)

| step | wall time |
|---|---|
| `judge/setup.sh` (cold) | ~3 min |
| `judge/grade.sh examples/good` (2 renders + all gates) | ~8 min |
| `judge/selftest.sh` (good + determinism + 8 mutants) | ~25 min |

## Upstream credit

[HyperFrames](https://github.com/heygen-com/hyperframes) by HeyGen —
npm package `hyperframes` **0.8.61** (published 2026-09-22), Apache-2.0.
The vendored `judge/vendor/gsap.min.js` is [GSAP](https://gsap.com)
3.14.2 (standard "no charge" licence — see the file header), the same
version upstream's own blank template loads.

## Limits

- Silent MP4 only — the judge does not listen for audio.
- Renders use the pinned `chrome-headless-shell` 152.0.7977.30 on CPU
  (SwiftShader); no GPU, no cloud/Lambda path.
- The judge validates only what `spec.json` declares — it cannot detect a
  brief that was transcribed wrongly into `spec.json` (the good example's
  spec is hand-checked against `brief.md`).
- HyperFrames' renderer is not byte-deterministic; gate 6 uses the
  documented SSIM/PSNR fallback (see SPEC.md).
