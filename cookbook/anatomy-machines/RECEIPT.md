# RECEIPT — anatomy-machines

Run inside a disposable Debian 12 (bookworm) sandbox, 2 vCPU, ~4 GB RAM,
2026-10-14. Toolchain: Python 3.12.15, playwright 1.60.0 (pip hashes),
pillow 11.3.0, Chrome Headless Shell 148.0.7778.96 r1223 (zip sha256
`88817c57…d636ce`), SwiftShader WebGL. Full record: `judge/VERSIONS.txt`.

## `bash judge/setup.sh` — exit 0, ~40 s (cold incl. browser download)

```
$ time bash judge/setup.sh
[setup] installing pinned judge toolchain into /home/user/.anatomy-judge
[setup] Fetching apt package lists...
[setup] Installing base packages (python3-venv, unzip, curl, ca-certificates)...
[setup] Installing pinned python packages (pip --require-hashes)...
[setup] Installing headless-shell system libraries (playwright install-deps)...
[setup] Downloading https://cdn.playwright.dev/builds/cft/148.0.7778.96/linux64/chrome-headless-shell-linux64.zip
[setup] sha256 OK: chrome-headless-shell-linux64.zip
[setup] Smoke test: headless launch + WebGL context under SwiftShader...
[setup]   chromium 148.0.7778.96, webgl=True
[setup] done — versions recorded in judge/VERSIONS.txt

real    0m39.949s
EXIT=0
```

Idempotent second run:

```
$ time bash judge/setup.sh
[setup] toolchain already installed and pinned (playwright 1.60.0, headless shell 148.0.7778.96 r1223)

real    0m1.065s
EXIT=0
```

## `bash judge/selftest.sh` — exit 0, 2 m 18 s, kill rate 6/6 (100 %)

```
$ time bash judge/selftest.sh
[selftest] Regenerating mutants...
Created 6 mutants in /home/user/w/cookbook/anatomy-machines/examples/bad

[selftest] Known-good figure (must PASS):
[selftest]   good/four-stroke-engine  PASS  (21s)

[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):
identical
[selftest]   deterministic

[selftest] Known-bad mutants (must FAIL):
[selftest]   blank_canvas  killed (failed gates: 2)
[selftest]   missing_parts  killed (failed gates: 3)
[selftest]   console_error  killed (failed gates: 1,2,3,4)
[selftest]   static_camera  killed (failed gates: 2)
[selftest]   wrong_labels  killed (failed gates: 3,4)
[selftest]   no_interaction  killed (failed gates: 4)

[selftest] ============================================
[selftest] good figure passed : 1/1
[selftest] determinism        : identical
[selftest] mutants killed     : 6/6 (100%)
[selftest] ============================================
[selftest] SUCCESS

real    2m18.339s
EXIT=0
```

## `bash judge/grade.sh examples/good/four-stroke-engine --json /tmp/good.json --seed 42` — exit 0, ~19 s

```json
{
  "artifact": "four-stroke-engine.html",
  "machine": "four-stroke-engine",
  "seed": 42,
  "gates": [
    {"gate": 1, "name": "loads_clean", "http_ok": true,
     "canvas_w": 762, "canvas_h": 522, "webgl": true,
     "console_errors": 0, "passed": true},
    {"gate": 2, "name": "rotates_nonblank", "variance_min": 50.0,
     "mad_min": 3.0, "changed_min": 0.02,
     "variances": [661.2, 652.7, 668.1],
     "mean_abs_diffs": [5.2, 5.5],
     "changed_fractions": [0.0599, 0.0609], "passed": true},
    {"gate": 3, "name": "parts_coverage", "recall_min": 0.8,
     "n_scene_parts": 17, "n_reference": 17, "recall": 1.0,
     "duplicates": 0, "passed": true},
    {"gate": 4, "name": "interaction", "desc_min": 20,
     "info_ok": 17, "info_total": 17, "passed": true},
    {"gate": 5, "name": "frame_rate", "fps_floor": 10.0,
     "fps_pass": true, "passed": true}
  ],
  "all_gates_passed": true,
  "timing": {"wall_seconds": 18.717, "measured_fps": 45.8}
}
```

`[grade] exit code: 0 (0 = all gates passed)`

A second grade inside a **fresh `git clone` of the pushed branch**
(`/tmp/arepo`, the exact `bash -c "cd repo/cookbook/anatomy-machines && …"`
sequence `run.py` sends over `sbx exec`) produced the same verdict with
every gate value byte-identical (variances 661.2/652.7/668.1, mean abs
diffs 5.2/5.5, changed fractions 0.0599/0.0609, recall 1.0); only
`timing` differed (wall 22.225 s, fps 46.6). Media frames for `media/`
were captured in a third identical run via `--shots`.

## Key numbers

| metric | value | threshold |
|---|---|---|
| canvas grayscale variance (3 angles) | 661.2 / 652.7 / 668.1 | >= 50 each |
| mean abs pixel diff between angles | 5.2 / 5.5 | >= 3.0 |
| fraction of pixels changed >30 levels | 0.0599 / 0.0609 | >= 0.02 |
| parts recall vs textbook reference | 17/17 = 1.0 | >= 0.8 |
| duplicate part names | 0 | == 0 |
| part info panels shown | 17/17 | all |
| measured FPS (SwiftShader, 2 vCPU) | 45.8 / 46.6 | >= 10 |
| mutant kill rate | 6/6 (100 %) | >= 90 % |
| determinism, same seed twice | byte-identical excl. `timing` | required |

## run.py verification

`python3 -m py_compile run.py` passes. The in-sandbox command sequence it
sends to `sbx exec` was run directly in this sandbox against a fresh
`git clone --depth 1 -b sbx/demo-anatomy-machines` of the pushed branch:
`bash judge/setup.sh` (idempotent path, exit 0) and
`bash judge/grade.sh examples/good/four-stroke-engine --json … --seed 42`
(exit 0, verdict above). The end-to-end cloud run is left to the
maintainer — no `SBX_API_KEY` exists inside this sandbox.

## Deviations

- **run.py not driven end to end** — `sbx` cannot create sandboxes from
  inside this sandbox; verified by `py_compile` plus a real run of the
  exact in-sandbox command sequence on a fresh clone (above).
- **"Two fresh sandboxes" emulated** — the reproduction run used a fresh
  clone of the pushed branch on this same machine rather than a second
  cloud sandbox; gate numbers were byte-identical outside `timing`.
- **Independent reproduction (`REPRODUCE.md`)** — not done: the standard
  requires a different agent/model family; left for the reproduction
  task.
- **Media** — `result.png`, `loop.png`, `demo.mp4` and
  `media/make_media.sh` are produced by the follow-up media task; what
  ships here is the judge's own real screenshots (`media/angle_*.png`,
  `media/spin_*.png`) with sha256s in `media/MANIFEST.json`.
- **apt dependencies are not individually sha256-pinned** — they come
  from Debian's signed bookworm repos via `playwright install-deps` (the
  dep list is fixed by the pinned playwright version). What *is*
  sha256-checked: every pip wheel (`--require-hashes`) and the browser
  archive itself (`judge/browser-sha256.txt`).
- **Gate-5 floor (10 FPS)** sits ~4.6× under the measured 45.8–46.6 FPS.
  Headless shell on this image vsyncs near 47 Hz rather than 60; the
  floor still separates a live renderer from a stalled page.
