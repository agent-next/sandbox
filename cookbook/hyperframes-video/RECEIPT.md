# RECEIPT: hyperframes-video

Real output from real runs on a fresh Debian bookworm sandbox
(2 vCPU, ~4 GB RAM). Every number below is pasted from command output
captured on 2026-10-15; nothing is written from memory.

Run environment: agent-next sandbox (Debian 12 bookworm), all commands run
from `cookbook/hyperframes-video/`.

## 1. Fresh sandbox run

Toolchain versions after `judge/setup.sh` (recorded by
`judge/versions.sh`, committed as `judge/VERSIONS.txt`):

```
node                  v22.23.3
hyperframes           0.8.61
chrome-headless-shell 152.0.7977.30 (Google Chrome for Testing)
ffmpeg/ffprobe        5.1.9-0+deb12u1
tesseract             5.3.0 (leptonica 1.82.0)
gsap (vendored)       3.14.2, sha256 c174bfce53a729418d57a8ad8625e7247c793a22fef8e2851e3cfa3de9cd8280
```

### `judge/setup.sh` (exit 0, 2m38s wall)

```
[setup] Fetching apt package lists...
[setup] Installing infra packages (curl, unzip, chrome runtime libs)...
[setup] Downloading pinned artifacts...
[setup] sha256 OK: all downloads match judge/package-sha256.txt
[setup] Installing pinned .debs (ffmpeg, tesseract, fonts-dejavu-core)...
[setup] Installing Node.js v22.23.3 -> /home/user/.hyperframes-judge/node
[setup] Installing hyperframes 0.8.61 (npm ci, judge/package-lock.json)

added 75 packages in 49s
[setup] Installing Chrome Headless Shell 152.0.7977.30 (sha256-verified zip)
[setup] toolchain installed: node v22.23.3, hyperframes 0.8.61, chrome-headless-shell 152.0.7977.30

real    2m38.354s
```

### `judge/grade.sh examples/good --seed 42` (exit 0, 6m04s wall)

```
[gates] gate 0 input-validation      PASS  {"checked": 0}
[gates] gate 1 render                PASS  {"output": "render1.mp4", "error": null}
[gates] gate 2 container-format      PASS  duration 24.0/24.0, 1280x720, fps 30.0, h264/yuv420p
[gates] gate 3 beat-text-ocr         PASS  5/5 beats, containment 1.0 each (raw variant)
[gates] gate 4 no-black-no-freeze    PASS  max_black 0.0 s, max_freeze 0.0 s
[gates] gate 5 brand-colors          PASS  indigo 1.5–11.5 %/frame, amber 2.0–10.0 %/frame
[gates] gate 6 determinism           PASS  ssim_all 1.0, psnr_db 100.0 (min 0.995 / 40)
[grade] exit code: 0 (0 = all gates passed)

real    6m4.498s
```

Key numbers from the verdict JSON (seed 42):

| metric | measured | gate limit |
|---|---|---|
| duration | 24.0 s (exactly 720 frames) | ±0.11 s of brief |
| resolution / fps | 1280×720 @ 30.0 | exact |
| OCR containment, each of 5 beats | 1.0 | ≥ 0.9 |
| longest black interval | 0.0 s | ≤ 0.5 s |
| longest frozen interval | 0.0 s | ≤ 2.0 s |
| brand pixel share, indigo | 1.5–11.5 % per beat frame | ≥ 1.0 % |
| brand pixel share, amber | 2.0–10.0 % per beat frame | ≥ 1.0 % |
| SSIM (All), render 1 vs 2 | 1.0 | ≥ 0.995 |
| PSNR, render 1 vs 2 | 100.0 dB (identical streams; see Deviations) | ≥ 40 dB |

### `judge/selftest.sh` (kill rate 8/8; determinism fixed afterwards)

```
[selftest] Known-good example (must PASS):
[selftest]   good  PASS  (336s)

[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):
[selftest]   good  NON-DETERMINISTIC

[selftest] Known-bad mutants (must FAIL):
[selftest]   wrong-duration     killed (failed gates: 0,1,2,3,4,5,6, 0s)
[selftest]   missing-beat       killed (failed gates: 3,5,6, 245s)
[selftest]   black-gap          killed (failed gates: 4,6, 277s)
[selftest]   wrong-resolution   killed (failed gates: 2,3,6, 147s)
[selftest]   off-brand-colors   killed (failed gates: 5,6, 212s)
[selftest]   broken-js          killed (failed gates: 3,5,6, 207s)
[selftest]   frozen-video       killed (failed gates: 4,6, 107s)
[selftest]   nondeterministic   killed (failed gates: 6, 310s)

[selftest] ============================================
[selftest] good example passed : 1/1
[selftest] determinism         : 0/1 identical
[selftest] mutants killed      : 8/8 (100%)
[selftest] ============================================
[selftest] FAIL: verdict JSON not deterministic at seed 42
[selftest] FAILURE

real    37m20.061s
```

The determinism failure was real and reproducible: the verdict recorded
the per-grade mktemp scratch path as `artifact`
(`/tmp/hf-judge.XXXXXX/case` vs a different one on the re-run), so the
two same-seed verdicts differed outside `timing`. Fixed in commit
`d2ed439` (`check_gates.py` now records only the basename). The
determinism check was then re-run against the fixed judge:

```
$ bash judge/grade.sh examples/good --json /tmp/det-run1.json --seed 42   # exit 0
$ bash judge/grade.sh examples/good --json /tmp/det-run2.json --seed 42   # exit 0
$ python3 -c 'import json,sys
a=json.load(open("/tmp/det-run1.json")); b=json.load(open("/tmp/det-run2.json"))
a.pop("timing"); b.pop("timing")
print("identical" if a==b else "DIFFER")'
identical
```

The verdict `artifact` field now reads `case` (the grade scratch copy's
basename) in both runs; the two same-seed verdicts are byte-identical
outside `timing` and both renders again passed every gate.

### `run.py` checks (builder sandbox cannot create sandboxes)

```
$ python3 -m py_compile run.py        # exit 0

$ bash -c 'git clone --depth 1 -b main https://github.com/agent-next/sandbox /tmp/hf-pycompile/repo'
Cloning into '/tmp/hf-pycompile/repo'...   (done, exit 0)

$ bash -n judge/setup.sh && bash -n judge/grade.sh && bash -n judge/selftest.sh
# all exit 0; the in-sandbox command sequence (clone -> setup -> selftest
# -> grade) was executed directly in this sandbox with the outputs above.
```

## Deviations

- **HyperFrames is not byte-deterministic.** Gate 6 uses the documented
  SSIM ≥ 0.995 / PSNR ≥ 40 dB fallback instead of frame-hash equality
  (see SPEC.md gate 6; the `nondeterministic` mutant exists to prove the
  gate still catches a visibly divergent composition).
- **PSNR `inf` is reported as 99.0** by the judge (identical streams are
  capped for reporting, `check_gates.py`), then quantised on the
  documented 5 dB grid, so the verdict shows 100.0 dB. In this run both
  renders of the good example were bit-equivalent (ffmpeg reported
  `average:inf`).
- **Chrome Headless Shell 152.0.7977.30** is the build hyperframes 0.8.61
  pins internally; the judge downloads that exact zip itself,
  sha256-checked against `judge/package-sha256.txt`, because hyperframes'
  own auto-download is not digest-verified.
- **Verdict numbers are quantised** on a documented grid in
  `judge/check_gates.py` (colour shares to 0.5 %, timing to 0.5 s, PSNR
  to 5 dB) so two grades of equivalent renders give byte-identical JSON
  outside the `timing` key; the self-test's determinism check verifies
  exactly that.
- **Second fresh-sandbox run:** (not done: a builder sandbox cannot run
  `sbx create`, so a second *fresh* sandbox can only be driven by
  `run.py` from outside, which is the lead's end-to-end check. This
  receipt records everything runnable from inside one fresh sandbox:
  cold `setup.sh`, `grade.sh` of the good example, `selftest.sh`, and
  the determinism re-check after the basename fix). Note the package
  downloads and `apt` layers of a second run share the same pinned
  sha256-checked artifacts, so gate numbers are expected identical — the
  quantised verdict grid makes them byte-identical by construction.
- **REPRODUCE.md** (independent reproduction by a different agent
  following README.md alone) is required by `cookbook/DEMO-STANDARD.md`
  before merge and is deliberately not written by the builder.
