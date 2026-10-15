# RECEIPT — anatomy-machines

Run inside a disposable Debian 12 (bookworm) sandbox, 2 vCPU, ~4 GB RAM,
2026-10-15. Toolchain: Python 3.12.15, playwright 1.60.0 (pip hashes),
pillow 11.3.0, Chrome Headless Shell 148.0.7778.96 r1223 (zip sha256
`88817c57…d636ce`), SwiftShader WebGL. Full record: `judge/VERSIONS.txt`.
Media figures additionally: matplotlib 3.10.5 in `media/.venv`
(`media/requirements.txt`), ffmpeg 5.1.9 (Debian bookworm).

## `bash judge/setup.sh` — exit 0 (cold incl. ~119 MB browser download)

```
$ bash judge/setup.sh
[setup] installing pinned judge toolchain into /home/user/.anatomy-judge
[setup] Fetching apt package lists...
[setup] Installing base packages (python3-venv, unzip, curl, ca-certificates)...
[setup] Creating venv at /home/user/.anatomy-judge/venv
[setup] Installing pinned python packages (pip --require-hashes)...
[setup] Installing headless-shell system libraries (playwright install-deps)...
[setup] Downloading https://cdn.playwright.dev/builds/cft/148.0.7778.96/linux64/chrome-headless-shell-linux64.zip
[setup] sha256 OK: chrome-headless-shell-linux64.zip
[setup] Smoke test: headless launch + WebGL context under SwiftShader...
[setup]   chromium 148.0.7778.96, webgl=True
[setup] done — versions recorded in judge/VERSIONS.txt
```

Idempotent second run:

```
$ time bash judge/setup.sh
[setup] toolchain already installed and pinned (playwright 1.60.0, headless shell 148.0.7778.96 r1223)

real    0m1.241s
EXIT=0
```

## `bash judge/selftest.sh` — exit 0, kill rate 7/7 (100 %)

Real output preserved verbatim at `media/data/selftest.log` (this run,
inside `media/collect_data.sh`; a standalone run measured 4 m 57 s):

```
[selftest] Regenerating mutants...
Created 7 mutants in /home/user/w/cookbook/anatomy-machines/examples/bad

[selftest] Known-good figure (must PASS):
[selftest]   good/four-stroke-engine  PASS  (56s)

[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):
identical
[selftest]   deterministic

[selftest] Known-bad mutants (must FAIL):
[selftest]   blank_canvas  killed (failed gates: 2,6)
[selftest]   missing_parts  killed (failed gates: 3)
[selftest]   console_error  killed (failed gates: 1,2,3,4,6)
[selftest]   static_camera  killed (failed gates: 2)
[selftest]   wrong_labels  killed (failed gates: 3,4)
[selftest]   no_interaction  killed (failed gates: 4)
[selftest]   tiny_capture  killed (failed gates: 6)

[selftest] ============================================
[selftest] good figure passed : 1/1
[selftest] determinism        : identical
[selftest] mutants killed     : 7/7 (100%)
[selftest] ============================================
[selftest] SUCCESS
```

## `bash judge/grade.sh examples/good/four-stroke-engine --json … --seed 42 --shots media/data/shots-good` — exit 0

Verbatim verdict (`media/data/grade-good.json`):

```json
{
  "artifact": "four-stroke-engine.html",
  "machine": "four-stroke-engine",
  "seed": 42,
  "gates": [
    {"gate": 1, "name": "loads_clean", "http_ok": true,
     "canvas_w": 860, "canvas_h": 840, "webgl": true,
     "console_errors": 0, "passed": true},
    {"gate": 2, "name": "rotates_nonblank", "variance_min": 50.0,
     "mad_min": 3.0, "changed_min": 0.02,
     "variances": [1361.1, 1327.8, 1303.0],
     "mean_abs_diffs": [8.5, 10.2],
     "changed_fractions": [0.0872, 0.1085], "passed": true},
    {"gate": 3, "name": "parts_coverage", "recall_min": 0.8,
     "n_scene_parts": 17, "n_reference": 17, "recall": 1.0,
     "duplicates": 0, "passed": true},
    {"gate": 4, "name": "interaction", "desc_min": 20,
     "info_ok": 17, "info_total": 17, "passed": true},
    {"gate": 5, "name": "frame_rate", "fps_floor": 10.0,
     "fps_pass": true, "passed": true},
    {"gate": 6, "name": "capture_quality", "width_min": 1280,
     "nonbg_min": 0.08, "w": 1920, "h": 1080,
     "nonbg_fraction": 0.1308, "n_labels": 17,
     "label_overlaps": 0, "passed": true}
  ],
  "all_gates_passed": true,
  "timing": {"wall_seconds": 64.941, "measured_fps": 13.1}
}
```

`[grade] exit code: 0 (0 = all gates passed)`

## Media — `bash media/collect_data.sh` then `bash media/make_media.sh`

`collect_data.sh` (6 m 50 s) re-ran the full self-test above, preserved
every verdict JSON into `media/data/`, and took the judge's own canvas
screenshots into `media/data/shots-good/` (`angle_0..2.png`,
`spin_00..07.png`).

`make_media.sh` then ran `media/render_media.py` in the pinned judge
venv: headless Chrome + SwiftShader served
`examples/good/four-stroke-engine` on `127.0.0.1`, screenshotted
`#stageView` at 1920×1080 — two stills plus 630 frames along a fixed
`__fig.set({yaw, explode, labels})` timeline (~2.4 s per real frame) —
then `fig_result.py`, `fig_loop.py` and `manifest.py` in `media/.venv`
(matplotlib 3.10.5). ffmpeg encoded `media/master/master.mp4`
(lossless `-crf 0`, git-ignored) and `media/demo.mp4` (`-crf 18
-preset slow -movflags +faststart`).

```
$ ffprobe -v error -show_entries format=duration,size \
    -of default=nw=1 media/demo.mp4
duration=21.000000
size=5103410
$ ffprobe -v error -select_streams v \
    -show_entries stream=codec_name,width,height,r_frame_rate \
    -of default=nw=1 media/demo.mp4
codec_name=h264
width=1920
height=1080
r_frame_rate=30/1
```

Shipped files (sha256 in `media/MANIFEST.json`): `result.png` 241 KiB
(exploded still + verdict band), `assembled.png` 143 KiB (raw still),
`loop.png` 138 KiB (mutant × gate matrix), `demo.mp4` 5.0 MB (21 s,
30 fps — inside 15–25 s and the 8 MB cap). Every video frame and still
is a real screenshot of the rendered scene; no synthesized or
interpolated frames; `?shot` hides page chrome and hover tooltips.

## Key numbers

| metric | value | threshold |
|---|---|---|
| canvas grayscale variance (3 angles) | 1361.1 / 1327.8 / 1303.0 | >= 50 each |
| mean abs pixel diff between angles | 8.5 / 10.2 | >= 3.0 |
| fraction of pixels changed >30 levels | 0.087 / 0.109 | >= 0.02 |
| parts recall vs textbook reference | 17/17 = 1.0 | >= 0.8 |
| duplicate part names | 0 | == 0 |
| part info panels shown | 17/17 | all |
| measured FPS (SwiftShader, 2 vCPU) | 13.1 / 17.3 | >= 10 |
| capture width | 1920 px | >= 1280 px |
| capture non-background fraction | 0.131 | >= 0.08 |
| label-chip overlaps | 0 / 17 chips | == 0 |
| mutant kill rate | 7/7 (100 %) | >= 90 % |
| determinism, same seed twice | byte-identical excl. `timing` | required |
| demo.mp4 | 21.0 s, 1920×1080, h264, 5.0 MB | 15–25 s, <= 8 MB |

## run.py verification

`python3 -m py_compile run.py` passes. The in-sandbox command sequence
it sends to `sbx exec` (`bash judge/setup.sh`, `bash judge/selftest.sh`,
`bash judge/grade.sh … --json … --seed 42`) is unchanged in behaviour —
`selftest.sh` only gained the optional `SELFTEST_OUT` preservation
hook — and each step was re-run for real in this sandbox (outputs
above). The end-to-end cloud run is left to the maintainer — no
`SBX_API_KEY` exists inside this sandbox.

## Deviations

- **run.py not driven end to end** — `sbx` cannot create sandboxes from
  inside this sandbox; verified by `py_compile` plus real runs of every
  in-sandbox command (above).
- **"Two fresh sandboxes" emulated** — reproduction used this same
  machine rather than a second cloud sandbox; gate values are
  deterministic at a fixed seed and `SELFTEST_OUT` now preserves the
  exact verdicts the media figures draw.
- **Independent reproduction (`REPRODUCE.md`)** — not done: the standard
  requires a different agent/model family; left for the reproduction
  task.
- **Gate-5 margin narrowed** — the shaded-solid scene renders at
  13–17 FPS here (floor 10), versus ~46 FPS for the earlier wireframe.
  The floor still separates a live renderer from a stalled page; on a
  slower sandbox the margin would thin further.
- **apt dependencies are not individually sha256-pinned** — they come
  from Debian's signed bookworm repos via `playwright install-deps`.
  What *is* sha256-checked: every pip wheel (`--require-hashes`) and
  the browser archive itself (`judge/browser-sha256.txt`).
- **media/.venv is git-ignored** — `media/make_media.sh` rebuilds it
  from `media/requirements.txt` (matplotlib 3.10.5); the judge toolchain
  stays separately pinned under `~/.anatomy-judge`.
