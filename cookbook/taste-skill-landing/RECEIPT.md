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
- End-to-end cloud run: **done — the lead ran `run.py` on a real
  agent-next sandbox at head `0886a35`; full log in
  [REPRODUCE.md](REPRODUCE.md).**

## `media/` frames

`media/site-375.png`, `media/site-768.png`, `media/site-1440.png` and
`media/scroll-00..09.png` are real browser screenshots of
`examples/good/site` taken headlessly by
[`media/make_frames.py`](media/make_frames.py) (Playwright 1.63.0 /
Chromium 153), committed 2026-10-14 in commit `0956bd0` ("real browser
frames of the taste-skill good site"). Sizes 44–280 KB each, all real
browser output (nothing synthesized). `demo.mp4` and `MANIFEST.json`
arrived with the Hardening pass below; every file was regenerated again
in the Visual polish pass after the select fix (current sizes: site
shots 283–505 KB, scroll frames 43–118 KB).

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

`python3 run.py` end-to-end — **exit 0 on a real agent-next sandbox**
(the lead ran it at head `0886a35` with an owner-try key; the earlier
shimmed-transport note that stood here was wrong and is replaced by the
real log in [REPRODUCE.md](REPRODUCE.md)):

```
[run] judge/selftest.sh                 244.6s  exit=0
[selftest] mutants killed  : 10/10 (100%)
[run] grade good/site                    15.9s  exit=0
[run] grade baseline/site                16.5s  exit=0
[run] good: ALL GATES PASS / baseline: FAILS (4/7)
[run] confirmed: 01a13d74-15d4-7f42-b9b2-609d17bd6279 is gone
RUN_RC=0
```

Media was regenerated from the fixed site
(`media/site-375/768/1440.png`, `scroll-00..09.png`) and `demo.mp4`
(30.4 s, 1920×1080, H.264 crf 18 +faststart, 788 KiB; lossless master in
gitignored `media/master/`) now builds via
[`media/make_media.sh`](media/make_media.sh), which re-grades both sites
for the verdict captions; per-file sha256 in
[`media/MANIFEST.json`](media/MANIFEST.json).

## Visual polish — 2026-10-15 (this sandbox, same toolchain)

The lead's acceptance pass found one visible defect in
`media/site-1440.png`/`scroll-00.png`: in the hero "Try the wind math"
card the "Wind from" `<select>` showed its value clipped at the bottom —
`height: 48px` with `padding: 16px` left a 16 px content box for a ~22 px
text line box. Two changes:

1. **Site fix.** `.live-thing select` is now `padding: 12px 16px;
   line-height: 24px`, so the text box fills the 48 − 24 px content box
   and the option label sits vertically centred at 375/768/1440 px
   (verified in the regenerated frames; `media/site-1440.png`). The other
   controls were audited for the same clipping: the `input[type=range]`
   renders no text and the `.button` anchors have no fixed height, so
   neither can clip.
2. **Judge check.** New taste sub-check **5.15 `control_text_fits`**
   (cite: SKILL.md step 6.7 "Real links and buttons" — a control whose
   own text does not fit the box its padding leaves is clipped): every
   visible `input`/`select`/`button` that can display text (non-text
   input types skipped) must have a text line box <= `clientHeight`
   minus vertical padding. `line-height: normal` — which Chromium
   reports on `select` regardless of the declared value — is measured
   with an offscreen probe of the same font. New mutant
   `clipped_control` reintroduces the defect (`padding: 16px` under the
   48 px height) and is killed by exactly this check:
   `SELECT#wind-dir` line_box 20–22 px > content_box 16 px at every
   width.

`bash judge/selftest.sh` — exit 0, 3 m 9 s, kill rate 100 % (10/10):

```
$ time bash judge/selftest.sh
[selftest] Regenerating mutants...
Created 10 mutants in .../examples/bad

[selftest] Known-good site (must PASS):
[selftest]   good/site  PASS
[selftest] Determinism: identical
[selftest]   baseline/site  exit != 0, fails: no_overflow,contrast_aa,...
[selftest]   clipped_control  killed (failed: control_text_fits)
[selftest] mutants killed  : 10/10 (100%)
[selftest] SUCCESS

real    3m9.038s
EXIT=0
```

`judge/grade.sh` — good exit **0** (20.9 s), baseline exit **1** (13.9 s):
good passes 7/7 gates and 15/15 taste sub-checks (min contrast ratio
5.19:1); baseline still fails `no_overflow`, `contrast_aa`,
`taste_rules` (11/15), `axe_a11y` — the same 4/7 failed-gate profile.

`bash media/make_media.sh` — exit 0, 6 m 40 s: all frames regenerated
from the fixed site (`site-375/768/1440.png` at 283/390/505 KB — the two
over 300 KB stayed unquantised because Pillow is not in the judge venv;
`make_frames.py` prints a note and continues), `scroll-00..09.png`,
`demo.mp4` (30.4 s, 1920×1080, H.264 crf 18 +faststart, 789 KiB; the
verdict card now reads 10/10 mutants), and a refreshed `MANIFEST.json`.

## Deviations

- **No Lighthouse.** The accessibility oracle is axe-core 4.10.3 (0
  critical/serious violations at 1440 and 375 px), the demo brief's
  explicitly sanctioned "equivalent axe-core check". The verdict's
  `axe_a11y.detail.note` says so, and SPEC.md gate 6 records it.
- **Two-fresh-sandbox reproduction.** Done: setup/selftest/grade ran in
  this fresh sandbox (toolchain installed from scratch), and the lead's
  end-to-end `run.py` ran on a real agent-next sandbox — full logs in
  [REPRODUCE.md](REPRODUCE.md).
- **run.py from a third environment.** The post-fix `run.py` itself
  still needs one keyed re-run: this review sandbox has no
  `SBX_API_KEY`/`E2B_API_KEY`, so the guard output is all it can print
  here (`run.py: export SBX_API_KEY (or E2B_API_KEY) first`). Every step
  `run.py` drives — setup, selftest, both grades — was re-run for real
  here after the fixes (Review round 1 below).
- **Setup wall time (~51 s)** reflects a warm Debian/npm mirror and warm
  venv caching path in this sandbox image; a colder sandbox may take a few
  minutes for the Chromium download.
- Favicon: `examples/good/site/assets/img/favicon.png` is generated by a
  tiny real Pillow script (`media/make_favicon.py`, committed) because the
  good site references it; it is a real 32×32 raster, not a stub.

## Review round 1 — 2026-10-15 (cross-model findings on `0886a35`)

Re-verified in this sandbox on the real toolchain (Playwright 1.63.0 /
Chromium 153.0.8010.12 / axe-core 4.10.3, `judge/VERSIONS.txt`), head
`35c3d14`. `bash judge/selftest.sh` — exit 0, ~9 min, **22/22 mutants
killed, 0 survivors**:

```
[selftest] good passed     : 1
[selftest] determinism     : 1
[selftest] baseline fails  : 1 (contract: rc != 0 + verdict JSON)
[selftest] mutants killed  : 22/22 (100%)
[selftest] SUCCESS
```

1. **[P1] External requests recorded, never blocked.** `check_gates.py`
   now installs `ctx.route("**/*")` before `goto`: anything outside the
   scratch server's exact origin (scheme+host+port from the served URL;
   `data:`/`blob:`/`about:` exempt as non-network) is recorded in
   `external_requests` and `route.abort()`ed before it can leave the
   box; a second `external_unblocked` list catches anything the route
   missed and must be empty. New mutant `remote_asset` loads
   `<script src="https://cdn.taste-mutant.invalid/remote.js">`:

   ```
   [selftest]   remote_asset  killed (clean_load; failed: clean_load)
                (3 external request(s) route-aborted, 0 escaped;
                nothing left the box)
   ```

   Its verdict shows the blocked URL at all three widths and
   `external_unblocked: []` — the request never reached DNS.

2. **[P1] Collector ran in the artifact's JS context.** All measurement
   — the DOM collector, axe-core, the wind-widget probe — now runs in a
   CDP isolated world (`Page.createIsolatedWorld` → `Runtime.evaluate`
   with `contextId`, `awaitPromise`). Verified directly: after the page
   sets `window.getComputedStyle = () => ({backgroundColor:'POISONED'})`,
   the main world returns `POISONED` while the isolated world still
   returns `rgb(244, 241, 234)`. New tampering mutant `patched_styles`
   ships a real `box-shadow` plus a main-world `getComputedStyle` proxy
   that reports `'none'` — it would survive under the old judge:

   ```
   [selftest]   patched_styles  killed (no_shadows_at_rest;
               failed: no_shadows_at_rest)
   ```

3. **[P1] A kill counted any non-zero exit; survivors allowed; uncovered
   taste rules.** `mutants.py` now writes `examples/bad/manifest.json`
   mapping each mutant to the one check it must trip. `selftest.sh`
   counts a kill only when `grade.sh` exits non-zero **and** the verdict
   JSON parses **and** the declared check is in the failed set — a crash
   (rc 2, no JSON), a missing verdict or a kill by the wrong check is a
   survivor, and the run requires 22/22 (0 survivors). Every measurable
   check now has a dedicated mutant — 10 new taste-rule mutants
   (`third_typeface`, `type_scale_burst`, `off_grid`, `boxed_shadow`,
   `patched_styles`, `hairline`, `mono_body`, `numbered_step`,
   `tiny_text`, `long_headline`, `few_images`) plus `remote_asset`;
   headline wrapping and image count included:

   ```
   [selftest]   boxed_shadow  killed (no_shadows_at_rest; ...)
   [selftest]   clipped_control  killed (control_text_fits; ...)
   [selftest]   console_error  killed (clean_load; ...)
   [selftest]   default_font  killed (no_default_fonts; ...)
   [selftest]   few_images  killed (image_floor_4; ...)
   [selftest]   fixed_container  killed (no_overflow; ...)
   [selftest]   gradient_button  killed (no_gradients; ...)
   [selftest]   hairline  killed (no_thin_rules; ...)
   [selftest]   img_no_alt  killed (alt_text; failed: alt_text,axe_a11y)
   [selftest]   long_headline  killed (headlines_two_lines; ...)
   [selftest]   low_contrast  killed (contrast_aa; failed: contrast_aa,axe_a11y)
   [selftest]   missing_section  killed (brief_sections; ...)
   [selftest]   mono_body  killed (no_monospace_outside_code; ...)
   [selftest]   numbered_step  killed (no_index_numbering; ...)
   [selftest]   off_grid  killed (spacing_scale_4px; ...)
   [selftest]   patched_styles  killed (no_shadows_at_rest; ...)
   [selftest]   remote_asset  killed (clean_load; ...)
   [selftest]   third_typeface  killed (two_typefaces_max; ...)
   [selftest]   tiny_taps  killed (tap_targets_44px; ...)
   [selftest]   tiny_text  killed (running_text_16px; ...)
   [selftest]   type_scale_burst  killed (type_scale_max_5; ...)
   [selftest]   wind_sign_bug  killed (wind_widget_sane; ...)
   ```

4. **[P2] grade.sh verdict JSON never printed; run.py printed only
   summaries.** `grade.sh` stdout is now the verdict JSON itself
   (seed+`timing` stamped; `--json` still writes the file; `[grade]`
   status lines moved to stderr). `run.py` prints both verdict JSONs
   under a `======== verdict JSONs ========` header after the summaries —
   matching the README promise:

   ```
   $ bash judge/grade.sh examples/good/site --seed 42 >/tmp/v.json
   [grade] artifact : .../examples/good/site
   [grade] exit code: 0 (0 = all gates passed)
   $ python3 -c 'import json; json.load(open("/tmp/v.json"))'   # parses
   ```

   Real grades after the fixes: good exit **0** (24.3 s, 7/7 gates),
   baseline exit **1** (fails `no_overflow`, `contrast_aa`,
   `taste_rules` 11/15, `axe_a11y` — the same 4/7 profile).

5. **[P1] Mocked transport + pending second run; no REPRODUCE.md.** The
   shim paragraph is replaced by the lead's real run on a real
   agent-next sandbox (head `0886a35`, sandbox
   `01a13d74-15d4-7f42-b9b2-609d17bd6279`, setup 315.8 s / selftest
   244.6 s / grades ~16 s, `RUN_RC=0`) — full log in the new
   [REPRODUCE.md](REPRODUCE.md), which also records this sandbox's
   independent re-verification of every in-sandbox step after the fixes.
   A second agent then re-ran everything again from a fresh toolchain
   (head `63ab8ea`): `judge/setup.sh` from nothing, `selftest.sh`
   exit 0, 22/22 (0 survivors), both grades — full log in
   REPRODUCE.md Record 3. `run.py` itself could not be re-run
   end-to-end from either review box (no
   `SBX_API_KEY`/`E2B_API_KEY` — it exits at the documented guard); a
   keyed re-run of `python3 cookbook/taste-skill-landing/run.py --ref
   sbx/demo-taste-skill-landing-hm3` remains a one-command check for
   the reviewer with a key (Record 1 is that run's proof at the
   pre-fix head).

6. **[P2] make_media.sh hardcoded "10/10 mutants killed".** The verdict
   card now runs `judge/selftest.sh` and parses the real
   `mutants killed  : N/N` line (fails hard if selftest fails or the
   count is missing); `--skip-grade` reads a gitignored cache
   (`media/selftest-kills.txt`) written by the last full run. Full
   regeneration ran for real here (head `63ab8ea`):

   ```
   $ bash media/make_media.sh            # exit 0, ~10 min
   [media] verdicts: grade.sh examples/{good,baseline}/site --seed 42
   [media] selftest: judge/selftest.sh (real kill count for the card)
   [media] demo.mp4: 788 KiB (30.400000 s)
   [media] MANIFEST.json: 14 entries
   ```

   The regenerated `demo.mp4` verdict card reads "judge self-test -
   22/22 mutants killed, a failing site exits non-zero" (verified by
   frame extraction), and `MANIFEST.json` was refreshed. Note: the
   in-flight commit `63ab8ea` ("wip") shipped the script change but
   the old 10/10 video — the media regeneration above is what the wip
   run timed out before finishing.

7. **[P2] Unpinned pip upgrade.** `judge/setup.sh` installs
   `pip==25.1.1` (well past the two-week rule); the real install prints
   `A new release of pip is available: 25.1.1 -> 26.2.1`, i.e. the pin
   held. `judge/VERSIONS.txt` re-recorded by the real setup run.

8. **OFL.txt:21 trailing space.** Kept verbatim: upstream
   `undercasetype/Fraunces` `OFL.txt` (master) has the identical
   `embedded, ` trailing space at line 21 — stripping it would make the
   copy diverge from the licence text.

## Review round 2 — 2026-10-15 (cross-model findings on `9dc6e80`)

Re-verified in a fresh sandbox on the real toolchain (Playwright 1.63.0 /
Chromium 153.0.8010.12 / axe-core 4.10.3, `judge/VERSIONS.txt`
re-recorded by the run below). `bash judge/setup.sh` — exit 0, 82 s
from nothing; `bash judge/selftest.sh` — exit 0, 2 m 12 s, **23/23
mutants killed, 0 survivors**; `bash judge/grade.sh
examples/good/site --seed 42` — exit 0, 7.4 s, 7/7 gates:

```
[selftest]   ws_external  killed (clean_load; failed: clean_load)
             (3 external WebSocket(s) mocked, 0 request(s) escaped;
              zero bytes left the box)
[selftest] ============================================
[selftest] good passed     : 1
[selftest] determinism     : 1
[selftest] baseline fails  : 1 (contract: rc != 0 + verdict JSON)
[selftest] mutants killed  : 23/23 (100%)
[selftest] ============================================
[selftest] SUCCESS
```

1. **[P1] `ctx.route()` intercepts HTTP only — WebSocket egress was
   invisible.** `check_gates.py` now also installs
   `ctx.route_web_socket("**")` before `goto`. The handler never calls
   `connect_to_server()`, so every WebSocket is fully mocked — the page
   still sees `onopen` — and zero bytes leave the box (it never calls
   `close()` either, which deadlocks the playwright 1.63.0 sync shim).
   Attempts are bucketed per verdict key: `websocket_remote` (non-scratch
   origin) fails `clean_load`; `websocket_local` (exact scratch
   host+port, cannot exfiltrate) is recorded only. The remaining
   non-HTTP channel, WebRTC, cannot honour routing either, so Chromium
   launches with `--force-webrtc-ip-handling-policy=
   disable_non_proxied_udp` — with no proxy configured no ICE channel can
   connect. EventSource and `navigator.sendBeacon` are plain HTTP and
   already pass through the existing route guard.
   New mutant `ws_external` opens `new
   WebSocket("wss://cdn.taste-mutant.invalid/socket")` and, in `onopen`,
   fires a fetch() tripwire to a second external URL. The selftest
   asserts a kill requires `websocket_remote` non-empty (a socket that
   bypassed the route would leave it empty) **and**
   `external_unblocked` empty — i.e. the tripwire fetch and every other
   non-local request were route-aborted. Real verdict excerpt:

   ```
   "websocket_remote": ["wss://cdn.taste-mutant.invalid/socket"],
   "external_requests": ["https://cdn.taste-mutant.invalid/onopen"],
   "external_unblocked": []
   ```
