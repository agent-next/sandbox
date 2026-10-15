# RECEIPT — taste-skill-landing

Run inside a disposable Debian sandbox, 2 vCPU, ~4 GB RAM, 2026-10-14.
Tool versions (recorded by `judge/setup.sh` into
[`judge/VERSIONS.txt`](judge/VERSIONS.txt)):
**Playwright 1.63.0** (pip, `--require-hashes`,
[`judge/requirements.txt`](judge/requirements.txt)),
**Chromium 153.0.8010.12** (browser build pinned by the playwright
package),
**axe-core 4.10.3** (npm tarball, sha256
`0f2b4d7dcdf7d1219df8d1959ad68e565f51d14c3f0d88bb71cd59abeb956292`),
Python 3.12.12. Upstream skill: Leonxlnx/taste-skill (MIT), commit
`f624f37a8c650b9cc550253104925efe4c8de246`.

## `bash judge/setup.sh` — exit 0, 51 s (fresh toolchain)

The sandbox had no judge toolchain
(`~/.taste-judge` and `~/.cache/ms-playwright` purged first). Real output
(download progress bars elided; untrimmed log kept in the working session):

```
$ rm -rf ~/.taste-judge ~/.cache/ms-playwright && time bash judge/setup.sh
[setup] Fetching apt package lists...
[setup] python3-venv present
[setup] Creating venv with pinned playwright 1.63.0 (hashed)...
[setup] playwright 1.63.0 installed (hash-verified wheels)
[setup] Installing Chromium (build pinned by playwright 1.63.0)...
[setup] chromium executable: /home/user/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome
[setup] Fetching axe-core 4.10.3 (sha256-checked)...
[setup] axe-core 4.10.3 verified (sha256 0f2b4d7dcdf7d121...)
[setup] judge toolchain installed: playwright 1.63.0, chromium 153.0.8010.12, axe-core 4.10.3
[setup] (versions recorded in judge/VERSIONS.txt)

real    0m51.174s
EXIT=0
```

## `bash judge/selftest.sh` — exit 0, 51 s, kill rate 100 % (8/8)

```
$ time bash judge/selftest.sh
[selftest] Regenerating mutants...
Created 8 mutants in /home/user/w/cookbook/taste-skill-landing/examples/bad

[selftest] Known-good site (must PASS):
[selftest]   good/site  PASS

[selftest] Determinism (same seed twice, verdict minus 'timing'):
[selftest]   identical

[selftest] No-skill baseline (expected FAIL, informational):
[selftest]   baseline/site  fails: no_overflow,contrast_aa,no_default_fonts,type_scale_max_5,spacing_scale_4px,alt_text,tap_targets_44px,no_gradients,no_shadows_at_rest,no_thin_rules,no_index_numbering,running_text_16px,image_floor_4,axe_a11y

[selftest] Known-bad mutants (must FAIL):
[selftest]   low_contrast  killed (failed: contrast_aa,axe_a11y)
[selftest]   fixed_container  killed (failed: no_overflow)
[selftest]   missing_section  killed (failed: brief_sections)
[selftest]   console_error  killed (failed: clean_load)
[selftest]   default_font  killed (failed: no_default_fonts)
[selftest]   tiny_taps  killed (failed: tap_targets_44px)
[selftest]   img_no_alt  killed (failed: alt_text,axe_a11y)
[selftest]   gradient_button  killed (failed: no_gradients)

[selftest] ============================================
[selftest] good passed     : 1
[selftest] determinism     : 1
[selftest] mutants killed  : 8/8 (100%)
[selftest] ============================================
[selftest] SUCCESS

real    0m51.194s
EXIT=0
```

## `bash judge/grade.sh examples/good/site --seed 42` — exit 0, 6 s, ALL gates pass

```
$ time bash judge/grade.sh examples/good/site --seed 42 --json /tmp/verdict-good.json
[grade] artifact : /home/user/w/cookbook/taste-skill-landing/examples/good/site
[grade] seed     : 42
[grade] exit code: 0 (0 = all gates passed)

real    0m5.879s
EXIT=0
```

Key numbers from `/tmp/verdict-good.json` (seed 42):

| gate | passed | key numbers |
|---|---|---|
| clean_load | true | 0 console errors, 0 failed requests, 0 non-localhost requests at 375/768/1440 px |
| no_overflow | true | scrollWidth == clientWidth at every width |
| contrast_aa | true | min ratio **5.19:1** (sample text "Plan a route") |
| brief_sections | true | all 7 brief sections present; body ground `#F4F1EA` |
| taste_rules (14 sub-checks) | true | 14/14 pass (typefaces ≤ 2, no default fonts, ≤ 5 type sizes, 4px spacing multiples, alt text, ≥ 44 px tap targets, no gradients/shadows/thin rules, no monospace leak, no index numbering, ≥ 16 px running text, ≤ 2 headline lines, ≥ 4 raster images) |
| axe_a11y | true | 0 critical/serious violations (axe-core 4.10.3 at 1440 and 375 px) |

## `bash judge/grade.sh examples/baseline/site --seed 42` — exit 1, 4 s, FAILS (expected)

```
$ time bash judge/grade.sh examples/baseline/site --seed 42 --json /tmp/verdict-baseline.json
[grade] artifact : /home/user/w/cookbook/taste-skill-landing/examples/baseline/site
[grade] seed     : 42
[grade] exit code: 1 (0 = all gates passed)

real    0m4.299s
EXIT=1
```

Failing gates: `no_overflow`, `contrast_aa`, `taste_rules` (11 of 14),
`axe_a11y` — the before/after story in the README table. `clean_load` and
`brief_sections` do pass: the baseline is a complete, loading page — it is
merely out of taste.

## `run.py` verification

- `python3 -m py_compile run.py` — **passes**.
- The in-sandbox command sequence `run.py` sends to `sbx exec` was
  verified directly in this sandbox: the same
  `bash -c 'cd repo/cookbook/taste-skill-landing && bash judge/…'` steps
  above (this sandbox cannot itself create sandboxes).
- `python3 run.py` without `SBX_API_KEY`/`E2B_API_KEY` exits with
  `run.py: export SBX_API_KEY (or E2B_API_KEY) first` (expected guard).
- End-to-end cloud run: **(not done: no SBX_API_KEY in this environment;
  the lead runs run.py end to end).**

## `media/` frames

`media/site-375.png`, `media/site-768.png`, `media/site-1440.png` and
`media/scroll-00..09.png` are real browser screenshots of
`examples/good/site` taken headlessly by
[`media/make_frames.py`](media/make_frames.py) (Playwright 1.63.0 /
Chromium 153), committed 2026-10-14 in commit `0956bd0` ("real browser
frames of the taste-skill good site"). Sizes 44–280 KB each, all real
browser output (nothing synthesized). `demo.mp4` and `MANIFEST.json`
arrived with the Hardening pass below.

## Hardening — 2026-10-15 (this sandbox, toolchain from the run above)

Two defects found by the lead's acceptance run were fixed and re-proven:

1. **Exit-code contract.** `grade.sh` now exits 0 only when every gate
   passes (any failed gate → rc 1 with the verdict JSON still written).
   `run.py` recovers the grader's rc through a JSON envelope and checks rc
   AND the verdict identically for both artifacts (good: rc 0 +
   `all_gates_passed`; baseline: rc != 0 + ≥ 1 failed gate). `selftest.sh`
   asserts a failing site exits non-zero and leaves a readable verdict.
2. **Wind-widget content.** The hero widget printed negative savings
   ("saves you -103 minutes"). `main.js` now computes both directions and
   returns `worst - best` under a stated model (still-air 24 km/h; tailwind
   adds half the wind speed, headwind costs the full wind; 8 km/h floor),
   so the saving is always ≥ 0 and ≤ the still-air time. New gate
   `wind_widget_sane` reads the rendered `#wind-result` text at three
   slider positions and every wind direction and fails on any negative,
   NaN or missing "N minutes" figure; the `wind_sign_bug` mutant
   reintroduces the ordered difference and is killed by it.

`bash judge/selftest.sh` — exit 0, 67 s, kill rate 100 % (9/9):

```
$ time bash judge/selftest.sh
[selftest] Regenerating mutants...
Created 9 mutants in /home/user/w/cookbook/taste-skill-landing/examples/bad

[selftest] Known-good site (must PASS):
[selftest]   good/site  PASS

[selftest] Determinism (same seed twice, verdict minus 'timing'):
[selftest]   identical

[selftest] No-skill baseline (MUST exit non-zero — the grader's
[selftest] exit-code contract: any failed gate => grade.sh rc != 0):
[selftest]   baseline/site  exit != 0, fails: no_overflow,contrast_aa,no_default_fonts,type_scale_max_5,spacing_scale_4px,alt_text,tap_targets_44px,no_gradients,no_shadows_at_rest,no_thin_rules,no_index_numbering,running_text_16px,image_floor_4,axe_a11y

[selftest] Known-bad mutants (must FAIL):
[selftest]   low_contrast  killed (failed: contrast_aa,axe_a11y)
[selftest]   fixed_container  killed (failed: no_overflow)
[selftest]   missing_section  killed (failed: brief_sections)
[selftest]   console_error  killed (failed: clean_load)
[selftest]   default_font  killed (failed: no_default_fonts)
[selftest]   tiny_taps  killed (failed: tap_targets_44px)
[selftest]   img_no_alt  killed (failed: alt_text,axe_a11y)
[selftest]   wind_sign_bug  killed (failed: wind_widget_sane)
[selftest]   gradient_button  killed (failed: no_gradients)

[selftest] ============================================
[selftest] good passed     : 1
[selftest] determinism     : 1
[selftest] baseline fails  : 1 (contract: rc != 0 + verdict JSON)
[selftest] mutants killed  : 9/9 (100%)
[selftest] ============================================
[selftest] SUCCESS

real    1m6.721s
EXIT=0
```

`judge/grade.sh` — good exit **0** (6.5 s), baseline exit **1** (4.5 s):

```
$ bash judge/grade.sh examples/good/site --seed 42 --json /tmp/verdict-good.json
[grade] artifact : .../examples/good/site
[grade] exit code: 0 (0 = all gates passed)   # 7/7 pass, incl. wind_widget_sane
$ bash judge/grade.sh examples/baseline/site --seed 42 --json /tmp/verdict-baseline.json
[grade] artifact : .../examples/baseline/site
[grade] exit code: 1 (0 = all gates passed)   # fails no_overflow, contrast_aa,
                                              # taste_rules, axe_a11y
```

The good site's widget now renders, at 18 km/h west: *"the 40 km loop
flips to 92 minutes one way round, 160 the other — the wind saves you 68
minutes if you ride it the right way."* (Every direction × slider
position probed by gate 7 is in the verdict's `wind_widget_sane.detail`.)

`python3 run.py` end-to-end — **exit 0**. This sandbox has no
`SBX_API_KEY`, so `run.py` was driven through a thin local `sbx` shim
(`sbx exec` runs the command locally); clone at the pushed ref
`sbx/demo-taste-skill-landing-hm`, selftest (76 s, 9/9 kills), both
grades and the verdict/exit-code checks all ran for real — only the
sandbox transport was mocked:

```
[run] git clone --depth 1 -b sbx/demo-taste-skill-landing-hm    2.0s  exit=0
[run] judge/setup.sh                      0.7s  exit=0   (warm toolchain)
[run] judge/selftest.sh                  76.1s  exit=0   (9/9, baseline rc != 0)
[run] grade good/site                     6.8s  exit=0   ALL GATES PASS
[run] grade baseline/site                 6.6s  exit=0   FAILS 4/7 (rc != 0)
[run] confirmed: sbx-shim-5571 is gone
RUNPY_EXIT=0
```

Media was regenerated from the fixed site
(`media/site-375/768/1440.png`, `scroll-00..09.png`) and `demo.mp4`
(30.4 s, 1920×1080, H.264 crf 18 +faststart, 788 KiB; lossless master in
gitignored `media/master/`) now builds via
[`media/make_media.sh`](media/make_media.sh), which re-grades both sites
for the verdict captions; per-file sha256 in
[`media/MANIFEST.json`](media/MANIFEST.json).

## Deviations

- **No Lighthouse.** The accessibility oracle is axe-core 4.10.3 (0
  critical/serious violations at 1440 and 375 px), the demo brief's
  explicitly sanctioned "equivalent axe-core check". The verdict's
  `axe_a11y.detail.note` says so, and SPEC.md gate 6 records it.
- **Two-fresh-sandbox reproduction.** Setup/selftest/grade were run once
  locally in a fresh state (toolchain purged first) in this sandbox; the
  second fresh-sandbox run is the lead's end-to-end `run.py` run (pending;
  see above).
- **REPRODUCE.md (not done: independent reproduction by a different agent
  is a separate task; README + one-command path are complete and the
  commands above were re-verified in this sandbox.**)
- **Setup wall time (~51 s)** reflects a warm Debian/npm mirror and warm
  venv caching path in this sandbox image; a colder sandbox may take a few
  minutes for the Chromium download.
- Favicon: `examples/good/site/assets/img/favicon.png` is generated by a
  tiny real Pillow script (`media/make_favicon.py`, committed) because the
  good site references it; it is a real 32×32 raster, not a stub.
