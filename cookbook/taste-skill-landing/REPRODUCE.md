# REPRODUCE — taste-skill-landing

Independent reproduction of the demo by a second agent, following
[README.md](README.md) only. Two real records:

1. **The lead's `run.py` run** — a real agent-next cloud sandbox,
   owner-try key, reviewed head `0886a35` (pre-review-fix).
2. **This sandbox's run** — a fresh agent-next sandbox (Debian 12,
   toolchain installed from nothing), post-fix head `35c3d14`, using the
   README's in-sandbox path. `run.py` end-to-end needs
   `SBX_API_KEY`/`E2B_API_KEY`, which this review sandbox does not have;
   every command `run.py` drives was run for real here, and the keyed
   one-command re-run is
   `python3 cookbook/taste-skill-landing/run.py --ref sbx/demo-taste-skill-landing-hm3`.

## The exact commands

```bash
# one-command run (needs an sbx API key)
export SBX_API_KEY=<your key>
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
python3 cookbook/taste-skill-landing/run.py --ref <branch>

# or, inside any Debian 12 box / sandbox (what this record used)
git clone --depth 1 -b <branch> https://github.com/agent-next/sandbox
cd sandbox/cookbook/taste-skill-landing
bash judge/setup.sh
bash judge/selftest.sh
bash judge/grade.sh examples/good/site --seed 42 --json /tmp/v-good.json
bash judge/grade.sh examples/baseline/site --seed 42 --json /tmp/v-base.json
```

## Record 1 — lead's real `run.py`, head `0886a35`, 2026-10-15

Real agent-next sandbox, owner-try key:

```
head 0886a35
[run] sbx create --timeout-min 30         1.1s  exit=0
[run] sandbox id: 01a13d74-15d4-7f42-b9b2-609d17bd6279
[run] git clone --depth 1 -b sbx/demo-taste-skill-landing-hm2    8.0s  exit=0
[run] judge/setup.sh                    315.8s  exit=0
[run] judge/selftest.sh                 244.6s  exit=0
[selftest] mutants killed  : 10/10 (100%)
[run] grade good/site                    15.9s  exit=0
[run] grade baseline/site                16.5s  exit=0
[run] ======== verdicts ========
[run] good: ALL GATES PASS
[run]   pass  clean_load
[run]   pass  no_overflow
[run]   pass  contrast_aa
[run]   pass  brief_sections
[run]   pass  taste_rules
[run]   pass  axe_a11y
[run]   pass  wind_widget_sane
[run] baseline: FAILS
[run]   pass  clean_load
[run]   FAIL  no_overflow
[run]   FAIL  contrast_aa
[run]   pass  brief_sections
[run]   FAIL  taste_rules
[run]   FAIL  axe_a11y
[run]   pass  wind_widget_sane
[run] sbx kill                            3.3s  exit=0
[run] sbx list                            1.2s  exit=0
[run] confirmed: 01a13d74-15d4-7f42-b9b2-609d17bd6279 is gone
RUN_RC=0
```

## Record 2 — this sandbox, head `35c3d14`, 2026-10-15

`bash judge/setup.sh` — exit 0, ~3 min (Chromium 153 already in the
image's browser cache; venv + axe-core from the network). Real output:

```
[setup] python3-venv present
[setup] Creating venv with pinned playwright 1.63.0 (hashed)...
[notice] A new release of pip is available: 25.1.1 -> 26.2.1
[setup] playwright 1.63.0 installed (hash-verified wheels)
[setup] Installing Chromium (build pinned by playwright 1.63.0)...
[setup] chromium executable: /home/user/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome
[setup] Fetching axe-core 4.10.3 (sha256-checked)...
[setup] axe-core 4.10.3 verified (sha256 0f2b4d7dcdf7d121...)
[setup] judge toolchain installed: playwright 1.63.0, chromium 153.0.8010.12, axe-core 4.10.3
[setup] (versions in judge/VERSIONS.txt)
```

`bash judge/selftest.sh` — exit 0, ~9 min, 22/22 mutants killed
(the fixed selftest requires the declared check in a real verdict JSON;
0 survivors):

```
[selftest] Regenerating mutants...
Created 22 mutants in .../examples/bad

[selftest] Known-good site (must PASS):
[selftest]   good/site  PASS

[selftest] Determinism (same seed twice, verdict minus 'timing'):
[selftest]   identical

[selftest] No-skill baseline (MUST exit non-zero — the grader's
[selftest] exit-code contract: any failed gate => grade.sh rc != 0):
[selftest]   baseline/site  exit != 0, fails: no_overflow,contrast_aa,no_default_fonts,type_scale_max_5,spacing_scale_4px,alt_text,tap_targets_44px,no_gradients,no_shadows_at_rest,no_thin_rules,no_index_numbering,running_text_16px,image_floor_4,axe_a11y

[selftest] Known-bad mutants (must FAIL their declared check):
[selftest]   boxed_shadow  killed (no_shadows_at_rest; failed: no_shadows_at_rest)
[selftest]   clipped_control  killed (control_text_fits; failed: control_text_fits)
[selftest]   console_error  killed (clean_load; failed: clean_load)
[selftest]   default_font  killed (no_default_fonts; failed: no_default_fonts)
[selftest]   few_images  killed (image_floor_4; failed: image_floor_4)
[selftest]   fixed_container  killed (no_overflow; failed: no_overflow)
[selftest]   gradient_button  killed (no_gradients; failed: no_gradients)
[selftest]   hairline  killed (no_thin_rules; failed: no_thin_rules)
[selftest]   img_no_alt  killed (alt_text; failed: alt_text,axe_a11y)
[selftest]   long_headline  killed (headlines_two_lines; failed: headlines_two_lines)
[selftest]   low_contrast  killed (contrast_aa; failed: contrast_aa,axe_a11y)
[selftest]   missing_section  killed (brief_sections; failed: brief_sections)
[selftest]   mono_body  killed (no_monospace_outside_code; failed: two_typefaces_max,no_default_fonts,no_monospace_outside_code)
[selftest]   numbered_step  killed (no_index_numbering; failed: no_index_numbering)
[selftest]   off_grid  killed (spacing_scale_4px; failed: spacing_scale_4px)
[selftest]   patched_styles  killed (no_shadows_at_rest; failed: no_shadows_at_rest)
[selftest]   remote_asset  killed (clean_load; failed: clean_load) (3 external request(s) route-aborted, 0 escaped; nothing left the box)
[selftest]   third_typeface  killed (two_typefaces_max; failed: two_typefaces_max)
[selftest]   tiny_taps  killed (tap_targets_44px; failed: tap_targets_44px)
[selftest]   tiny_text  killed (running_text_16px; failed: running_text_16px)
[selftest]   type_scale_burst  killed (type_scale_max_5; failed: type_scale_max_5)
[selftest]   wind_sign_bug  killed (wind_widget_sane; failed: wind_widget_sane)

[selftest] ============================================
[selftest] good passed     : 1
[selftest] determinism     : 1
[selftest] baseline fails  : 1 (contract: rc != 0 + verdict JSON)
[selftest] mutants killed  : 22/22 (100%)
[selftest] ============================================
[selftest] SUCCESS
```

`bash judge/grade.sh examples/good/site --seed 42 --json
/tmp/v-good.json` — exit **0**, 24.3 s, all 7 gates pass; `grade.sh`
stdout is now the verdict JSON itself (parses cleanly).

`bash judge/grade.sh examples/baseline/site --seed 42 --json
/tmp/v-base.json` — exit **1**; fails `no_overflow`, `contrast_aa`,
`taste_rules` (11/15 sub-checks), `axe_a11y`.

`python3 run.py` in this box exits at the documented key guard:
`run.py: export SBX_API_KEY (or E2B_API_KEY) first` — no sandbox API key
is present here, so Record 1 is the real end-to-end run.

## Record 3 — second review agent, head `63ab8ea` (post-review wip), 2026-10-15

Same box, toolchain removed (`~/.taste-judge`, `~/.cache/ms-playwright`)
and rebuilt from the network. `bash judge/setup.sh` — exit 0, installed
playwright 1.63.0 (hash-verified), Chromium 153.0.8010.12, axe-core
4.10.3 (`judge/VERSIONS.txt` re-recorded 2026-10-15T05:38Z).

`bash judge/selftest.sh` — exit 0, ~9 min, **22/22 mutants killed, 0
survivors** (full per-mutant list identical in shape to Record 2; the
tail):

```
[selftest]   boxed_shadow  killed (no_shadows_at_rest; failed: no_shadows_at_rest)
[selftest]   clipped_control  killed (control_text_fits; failed: control_text_fits)
...
[selftest]   remote_asset  killed (clean_load; failed: clean_load) (3 external request(s) route-aborted, 0 escaped; nothing left the box)
...
[selftest]   wind_sign_bug  killed (wind_widget_sane; failed: wind_widget_sane)

[selftest] ============================================
[selftest] good passed     : 1
[selftest] determinism     : 1
[selftest] baseline fails  : 1 (contract: rc != 0 + verdict JSON)
[selftest] mutants killed  : 22/22 (100%)
[selftest] ============================================
[selftest] SUCCESS
```

`bash media/make_media.sh` — exit 0, ~10 min: verdicts + fresh
selftest, the verdict card in `media/demo.mp4` then read the parsed
kill count ("22/22 mutants killed", verified by frame extraction), and
`media/MANIFEST.json` lists 14 hashed entries.

`python3 run.py` here again stops at the key guard
(`run.py: export SBX_API_KEY (or E2B_API_KEY) first`) — this box has
none. `python3 -m py_compile run.py` and `python3 -m sbx.cli --help`
(sbx CLI importable) both pass.

## Match against RECEIPT.md / SPEC.md tolerances

| measure | RECEIPT (pre-fix head) | this reproduction (post-fix) |
|---|---|---|
| good site | ALL GATES PASS | ALL GATES PASS (7/7) |
| baseline | FAILS 4/7 | FAILS same 4/7 |
| determinism | identical verdicts | identical verdicts |
| kill rate | 10/10 (mutant set then) | 22/22 — the review added mutants for every taste rule |
| setup | 51 s warm / 315.8 s cold | ~3 min (browser cache warm, network cold) |

Gate profile and verdict shape are identical to SPEC.md's contract;
kill count differs only because the mutant set grew (10 → 22), as
required by the review.
