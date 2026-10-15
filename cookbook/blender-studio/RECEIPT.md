# Acceptance receipt, 2026-10-15

The final judge passed `python3 run.py` twice from fresh `blender` sandboxes,
strictly sequentially, seed 17. Both processes exited 0, caught 10/10 mutants,
and produced byte-identical verdicts excluding `timing`. Both sandbox deletions
were confirmed by `sbx list`. The shipped media comes from one fresh, complete
sandbox capture and passes the mechanical video gate, the blind two-judge
review panel and an independent reproduction (`media/REVIEW.json`,
`REPRODUCE.md`).

## Versions

Actual `judge/setup.sh` output, identical in both fresh sandboxes:

```text
Blender 5.2.2 LTS
Blender build d13f752e3b9c
PIN numpy=2.3.4 python=3.13.13
Python 3.13.5
setup PASS (pinned image tools; no downloads)
```

The local launcher uses Python 3.12.3 and sbx 0.0.1. Media composition uses
Pillow 10.2.0 and ffmpeg/ffprobe 6.1.1-3ubuntu5. Both launch and media transfer
use stdlib and `sbx`. An e2b 2.40.0 streaming transfer was tried during media
development and removed after slow progress. No key is uploaded, printed or
written to a file.

Clone commit in both launch runs:
`253df342fa4fd1c772d4eb3e801e87f1bb5f1a01` (public `main` at run time).
Both upload the identical judge/scene snapshot:
`ae8e9e7a46fa60fcbef87c503282e742b571757540207b5cd20528bb16688cff`.

## Launch measurements

Command for each run: `python3 run.py` from `cookbook/blender-studio`, seed 17.

| step | run A exit / wall s | run B exit / wall s |
| --- | --- | --- |
| create | 0 / 1.2 | 0 / 6.1 |
| clone | 0 / 10.1 | 0 / 11.5 |
| snapshot | 0 / 2.3 | 0 / 20.5 |
| setup | 0 / 13.8 | 0 / 17.3 |
| selftest | 0 / 142.1 | 0 / 154.4 |
| grade | 0 / 22.8 | 0 / 23.5 |
| time-to-result | 192.3 | 233.2 |
| cleanup (total minus time-to-result) | confirmed / 6.4 | confirmed / 3.2 |
| total process | 0 / 198.7 | 0 / 236.4 |

Both launches meet the standard's <300 s CPU time-to-result target.
Times are wall measurements on a shared CPU pool, not isolated CPU benchmarks.

### Run A, real stdout

```text
create: sandbox=01a13f01-3ad6-7f63-b842-1b3893b56362 template=blender wall=1.2s
Cloning into '/tmp/studio-repo'...
253df342fa4fd1c772d4eb3e801e87f1bb5f1a01

clone: exit=0 wall=10.1s
source snapshot sha256=ae8e9e7a46fa60fcbef87c503282e742b571757540207b5cd20528bb16688cff

snapshot: exit=0 wall=2.3s
Blender 5.2.2 LTS
Blender build d13f752e3b9c
PIN numpy=2.3.4 python=3.13.13
Python 3.13.5
setup PASS (pinned image tools; no downloads)

setup: exit=0 wall=13.8s
MUTANT unlinked_rim: killed=True failed=G3_backdrop,G5_linking
MUTANT wrong_period: killed=True failed=G4_loop
MUTANT off_center: killed=True failed=G1_framing,G3_backdrop
MUTANT overexposed: killed=True failed=G2_exposure
MUTANT clipped_hero: killed=True failed=G1_framing,G3_backdrop,G5_linking
MUTANT visible_seam: killed=True failed=G3_backdrop
MUTANT high_seam: killed=True failed=G3_backdrop
MUTANT filtered_seam: killed=True failed=G3_backdrop
MUTANT orbiting_hero: killed=True failed=G1_framing
MUTANT unlinked_halo: killed=True failed=G2_exposure,G5_linking
GOOD pass=True repeat=True byte_identical=True
SELFTEST killed=10/10 kill_rate=100.0% exit=0 wall=137.12s
GOOD_VERDICT {"blender": "5.2.2 LTS", "gates": {"G1_framing": {"bbox_fraction": 0.171453, "center": [0.465763, 0.514999], "checked_frames": 12, "failed_frames": [], "inside_margin": true, "pass": true}, "G2_exposure": {"clipped_fraction": 0.0, "mean_display_luminance": 0.481615, "pass": true}, "G3_backdrop": {"backdrop_visibility_fraction": 1.0, "max_second_difference": 0.013453, "pass": true, "unexpected_filter_rays": 0, "unexpected_primary_pixels": 0, "verified_pixels": 4320}, "G4_loop": {"endpoint_mean_abs_diff": 2e-06, "frames": 12, "max_step_error_radians": 3.7e-07, "pass": true}, "G5_linking": {"backdrop_direct_delta": 0.000296, "halo_receivers": ["Cyclorama"], "pass": true, "product_direct_delta": 0.020933, "rim_receivers": ["GlassOrb", "GoldRing", "Hero", "Plinth"]}}, "judge_unchanged": true, "pass": true, "render": {"device": "CPU", "engine": "CYCLES", "resolution": [256, 144], "samples": 8, "threads": 4}, "seed": 17, "timing": {"total_seconds": 12.902}}

selftest: exit=0 wall=142.1s
{"blender": "5.2.2 LTS", "gates": {"G1_framing": {"bbox_fraction": 0.171453, "center": [0.465763, 0.514999], "checked_frames": 12, "failed_frames": [], "inside_margin": true, "pass": true}, "G2_exposure": {"clipped_fraction": 0.0, "mean_display_luminance": 0.481615, "pass": true}, "G3_backdrop": {"backdrop_visibility_fraction": 1.0, "max_second_difference": 0.013453, "pass": true, "unexpected_filter_rays": 0, "unexpected_primary_pixels": 0, "verified_pixels": 4320}, "G4_loop": {"endpoint_mean_abs_diff": 2e-06, "frames": 12, "max_step_error_radians": 3.7e-07, "pass": true}, "G5_linking": {"backdrop_direct_delta": 0.000296, "halo_receivers": ["Cyclorama"], "pass": true, "product_direct_delta": 0.020933, "rim_receivers": ["GlassOrb", "GoldRing", "Hero", "Plinth"]}}, "judge_unchanged": true, "pass": true, "render": {"device": "CPU", "engine": "CYCLES", "resolution": [256, 144], "samples": 8, "threads": 4}, "seed": 17, "timing": {"total_seconds": 10.52}}

grade: exit=0 wall=22.8s
PASS: five gates; seed=17; Blender 5.2.2 LTS; time-to-result=192.3s
cleanup confirmed: 01a13f01-3ad6-7f63-b842-1b3893b56362 absent from sbx list
run: exit=0 wall=198.7s

PROCESS_EXIT=0
```

### Run B, real stdout

```text
create: sandbox=01a13f04-53e0-7a22-a898-31233a39eb6d template=blender wall=6.1s
Cloning into '/tmp/studio-repo'...
253df342fa4fd1c772d4eb3e801e87f1bb5f1a01

clone: exit=0 wall=11.5s
source snapshot sha256=ae8e9e7a46fa60fcbef87c503282e742b571757540207b5cd20528bb16688cff

snapshot: exit=0 wall=20.5s
Blender 5.2.2 LTS
Blender build d13f752e3b9c
PIN numpy=2.3.4 python=3.13.13
Python 3.13.5
setup PASS (pinned image tools; no downloads)

setup: exit=0 wall=17.3s
MUTANT unlinked_rim: killed=True failed=G3_backdrop,G5_linking
MUTANT wrong_period: killed=True failed=G4_loop
MUTANT off_center: killed=True failed=G1_framing,G3_backdrop
MUTANT overexposed: killed=True failed=G2_exposure
MUTANT clipped_hero: killed=True failed=G1_framing,G3_backdrop,G5_linking
MUTANT visible_seam: killed=True failed=G3_backdrop
MUTANT high_seam: killed=True failed=G3_backdrop
MUTANT filtered_seam: killed=True failed=G3_backdrop
MUTANT orbiting_hero: killed=True failed=G1_framing
MUTANT unlinked_halo: killed=True failed=G2_exposure,G5_linking
GOOD pass=True repeat=True byte_identical=True
SELFTEST killed=10/10 kill_rate=100.0% exit=0 wall=144.451s
GOOD_VERDICT {"blender": "5.2.2 LTS", "gates": {"G1_framing": {"bbox_fraction": 0.171453, "center": [0.465763, 0.514999], "checked_frames": 12, "failed_frames": [], "inside_margin": true, "pass": true}, "G2_exposure": {"clipped_fraction": 0.0, "mean_display_luminance": 0.481615, "pass": true}, "G3_backdrop": {"backdrop_visibility_fraction": 1.0, "max_second_difference": 0.013453, "pass": true, "unexpected_filter_rays": 0, "unexpected_primary_pixels": 0, "verified_pixels": 4320}, "G4_loop": {"endpoint_mean_abs_diff": 2e-06, "frames": 12, "max_step_error_radians": 3.7e-07, "pass": true}, "G5_linking": {"backdrop_direct_delta": 0.000296, "halo_receivers": ["Cyclorama"], "pass": true, "product_direct_delta": 0.020933, "rim_receivers": ["GlassOrb", "GoldRing", "Hero", "Plinth"]}}, "judge_unchanged": true, "pass": true, "render": {"device": "CPU", "engine": "CYCLES", "resolution": [256, 144], "samples": 8, "threads": 4}, "seed": 17, "timing": {"total_seconds": 13.973}}

selftest: exit=0 wall=154.4s
{"blender": "5.2.2 LTS", "gates": {"G1_framing": {"bbox_fraction": 0.171453, "center": [0.465763, 0.514999], "checked_frames": 12, "failed_frames": [], "inside_margin": true, "pass": true}, "G2_exposure": {"clipped_fraction": 0.0, "mean_display_luminance": 0.481615, "pass": true}, "G3_backdrop": {"backdrop_visibility_fraction": 1.0, "max_second_difference": 0.013453, "pass": true, "unexpected_filter_rays": 0, "unexpected_primary_pixels": 0, "verified_pixels": 4320}, "G4_loop": {"endpoint_mean_abs_diff": 2e-06, "frames": 12, "max_step_error_radians": 3.7e-07, "pass": true}, "G5_linking": {"backdrop_direct_delta": 0.000296, "halo_receivers": ["Cyclorama"], "pass": true, "product_direct_delta": 0.020933, "rim_receivers": ["GlassOrb", "GoldRing", "Hero", "Plinth"]}}, "judge_unchanged": true, "pass": true, "render": {"device": "CPU", "engine": "CYCLES", "resolution": [256, 144], "samples": 8, "threads": 4}, "seed": 17, "timing": {"total_seconds": 14.37}}

grade: exit=0 wall=23.5s
PASS: five gates; seed=17; Blender 5.2.2 LTS; time-to-result=233.2s
cleanup confirmed: 01a13f04-53e0-7a22-a898-31233a39eb6d absent from sbx list
run: exit=0 wall=236.4s

PROCESS_EXIT=0
```

## Measured gates and power tests

| metric | run A | run B | acceptance |
| --- | --- | --- | --- |
| frame-1 bbox fraction | 0.171453 | 0.171453 | 0.07–0.22 at every pose |
| frame-1 center | (0.465763, 0.514999) | same | x 0.5±0.055; y 0.5±0.12 |
| checked / failing poses | 12 / none | 12 / none | all 12 pass; 4% margins |
| mean display luminance | 0.481615 | 0.481615 | 0.15–0.65 |
| clipped fraction | 0 | 0 | <=0.005 at >=253/255 |
| backdrop second difference | 0.013453 | 0.013453 | <=0.055 |
| backdrop visibility / pixels | 1.0 / 4320 | same | >=0.995 / >=4000 |
| unexpected primary / filter rays | 0 / 0 | 0 / 0 | zero |
| endpoint RGB difference | 0.000002 | 0.000002 | <=0.003 |
| angular step error, rad | 0.00000037 | same | <=0.00001 |
| rim-only backdrop / product delta | 0.000296 / 0.020933 | same | <=0.001 / >=0.001 |

Receiver lists are exact in both runs: rim
`GlassOrb, GoldRing, Hero, Plinth`; halo `Cyclorama`.
All mutants fail measured numeric gates, not runtime errors. Scene parsing
rejects executable edits; judge SHA-256 checks pass before/after every grade.

Independent cross-family execution review initially
found seam and orbit bypasses. The reviewer independently confirmed their
fixes at `5a2bf96`: `findings[]=[]`, `VERDICT: SHIP`. Good passed twice locally;
the high seam produced 1024 primary hits, and the filtered seam produced 520
filter-band hits, each failing only G3. The orbit mutant fails only G1.
Two runner regressions prove the atomic completion marker and lost-create
warning fail their named assertions with the old runner substituted.
This code review is **not** the independent README reproduction or media panel.

## Media

**Fresh complete capture, one sandbox.** `sh media/make_media.sh` created
sandbox `01a13f64-e3c8-7212-b22b-337a431caa5f`, uploaded the source snapshot
(sha256 `ae8e9e7a46fa60fcbef87c503282e742b571757540207b5cd20528bb16688cff`),
ran setup and the ten-mutant self-test, then rendered all thirteen 1920×1080
images at seed 17, 8 samples, Cycles CPU, four threads:

```sh
blender -b --factory-startup --python-exit-code 1 -t 4 \
  -P media/render.py -- --out media/source --seed 17
```

Real output excerpts:

```text
setup: exit=0 wall=37.2s
SELFTEST killed=10/10 kill_rate=100.0% exit=0 wall=108.186s
selftest: exit=0 wall=117.4s
media-render: exit=0 wall=838.4s
cleanup confirmed: 01a13f64-e3c8-7212-b22b-337a431caa5f absent from sbx list
```

All 37 collected files (renders, render.json, self-test verdicts and mutant
heroes) were transferred in bounded CLI chunks and each matched its remote
size and SHA-256 before replacing local evidence (`media/data/transfers.json`).
The proof data in the video (`media/data/selftest.json`) is this sandbox's
self-test output, not a local run. Per-image render seconds
(`media/source/render.json`, total 824.6 s):

| source file | measured seconds |
| --- | --- |
| frame-01.png | 44.679 |
| frame-02.png | 55.052 |
| frame-03.png | 46.229 |
| frame-04.png | 44.084 |
| frame-05.png | 51.307 |
| frame-06.png | 68.0 |
| frame-07.png | 66.908 |
| frame-08.png | 70.623 |
| frame-09.png | 60.92 |
| frame-10.png | 89.003 |
| frame-11.png | 83.601 |
| frame-12.png | 69.163 |
| unlinked.png | 75.019 |

An earlier attempt the same day rendered successfully but lost its collection
to a service-side interruption; nothing from it is shipped. Media PNGs need
not be byte-identical across re-renders; only verdict JSON must be
byte-identical excluding `timing`. `result.png` and `loop.png` regenerated
byte-identical from this capture.

Composition and gate:

```sh
sh media/make_media.sh
```

Font DejaVuSans.ttf is SHA-256 pinned:
`ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280`.
Result and loop figures are 1920×1080 at 200 dpi. The ignored lossless master
uses CRF 0; the web encode uses CRF 18, preset slow, yuv420p and faststart.

### Mechanical video gate, real output

```json
{
  "file": "demo.mp4",
  "passed": true,
  "failed": [],
  "checks": [
    {"name": "width", "measured": 1920, "threshold": ">= 1920", "pass": true},
    {"name": "height", "measured": 1080, "threshold": ">= 1080", "pass": true},
    {"name": "aspect_ratio", "measured": 1.7778, "threshold": "16:9 +/- 1%", "pass": true},
    {"name": "duration_s", "measured": 30.0, "threshold": "25-60 s", "pass": true},
    {"name": "fps", "measured": 30.0, "threshold": "29.969-30.001", "pass": true},
    {"name": "codec", "measured": "h264", "threshold": "== h264", "pass": true},
    {"name": "pix_fmt", "measured": "yuv420p", "threshold": "== yuv420p", "pass": true},
    {"name": "size_mib", "measured": 3.1902, "threshold": "<= 8 MiB", "pass": true},
    {"name": "faststart", "measured": "moov@32 mdat@11672", "threshold": "moov atom before mdat", "pass": true},
    {"name": "first_frame_luma_mean", "measured": 122.9183, "threshold": ">= 20", "pass": true},
    {"name": "first_frame_luma_std", "measured": 30.0096, "threshold": ">= 12", "pass": true},
    {"name": "first_frame_not_solid", "measured": 255, "threshold": ">= 8 (luma max-min)", "pass": true},
    {"name": "scene_cuts_per_10s", "measured": 2.6667, "threshold": ">= 0.8", "pass": true},
    {"name": "endcard_static", "measured": 0.0, "threshold": "<= 0.5 (mean YDIF, last 2 s)", "pass": true},
    {"name": "audio", "measured": "absent", "threshold": "optional", "pass": true}
  ]
}
```

Whitespace is compacted above; values are unchanged. Composition exited 0:
`media: 900 frames / 30 s / 3345167 bytes`.

## Repository tests

Each discovered cookbook test module was run in a separate pytest process
(local Python 3.12.3, pytest 9.1.1) to respect their existing sibling imports.
Real summary output before final media capture:

```text
cookbook/img2threejs-showcase/test_run.py: exit=0; 2 passed in 0.38s
cookbook/sim-engine-arena/test_run.py: exit=0; 3 passed in 0.02s
cookbook/gpu-kernel/media/test_make_figures.py: exit=0; 3 passed in 1.17s
cookbook/tools/test_video_gate.py: exit=0; 17 passed in 80.51s (0:01:20)
cookbook/render-pathtrace/test_runner.py: exit=0; 13 passed in 0.03s
cookbook/sim-engine-arena/media/test_media.py: exit=1; 5 failed, 3 passed in 0.43s
cookbook/render-pathtrace/media/test_frames.py: exit=0; 2 passed in 0.03s
cookbook/render-pathtrace/judge/test_contract.py: exit=0; 15 passed in 1.17s
cookbook/blender-studio/test_studio_transfer.py: exit=0; 3 passed in 0.02s
cookbook/blender-studio/test_studio_contract.py: exit=0; 10 passed, 12 subtests passed in 0.03s
```

`cd cli && python3 -m pytest -q tests/test_small_gpu_recipe.py` (the only CLI
test module referencing cookbook files):

```text
6 passed in 0.02s
```

The five pre-existing `sim-engine-arena/media/test_media.py` failures concern
missing trajectory CSVs, missing render-checks JSON/work directory, and a
missing ignored lossless master. Those files are unchanged by this branch. The all-cookbook
`--import-mode=importlib` attempt also had two sibling-import collection errors;
per-module invocation resolves those imports, not the missing fixtures.
Final checks after composition:

```text
python3 -m pytest -q cookbook/blender-studio/test_studio_contract.py cookbook/blender-studio/test_studio_transfer.py cookbook/blender-studio/test_studio_media.py
18 passed in 0.26s
PROCESS_EXIT=0

pytest -q cookbook/tools/test_video_gate.py
17 passed in 140.04s (0:02:20)
PROCESS_EXIT=0
```

The second video-suite run includes the shipped Blender clip in the committed
demo baseline. No baseline exception was added for this demo.
Full CLI Python-version CI matrices were not run (no CLI change).

## Sandboxes and cleanup

Final accepted runs:

| sandbox | purpose | cleanup |
| --- | --- | --- |
| `01a13f01-3ad6-7f63-b842-1b3893b56362` | final run A | killed; confirmed absent by `sbx list` |
| `01a13f04-53e0-7a22-a898-31233a39eb6d` | final run B | killed; confirmed absent by `sbx list` |
| `01a13f18-bae3-7ee1-b05e-ada941a5ae7c` | completed fresh render, download blocked | killed; confirmed absent by `sbx list` |

Additional sandboxes created in this resumed round, all killed and confirmed:
`01a13ee9-44e7-7901-b3df-a9664ee0100d`,
`01a13ef1-2ebf-7092-a272-f3671cc52a4b` (7-mutant pre-hardening runs);
`01a13ef5-2179-7781-ad1b-605004b677ac`,
`01a13efa-18d9-7d30-b0e3-f0bc145c85e8` (9-mutant pre-filter-border runs).
These are historical checks, not substitutes for the two final launches.

Sandboxes from earlier interrupted runs (none still listed at the end):
`01a13e49-d3ca-7723-8469-c5a62c0aaf13`,
`01a13e81-7f3d-7530-91f7-04623e80a1f5`,
`01a13e86-43d5-7e03-a059-ffbd2232d842`,
`01a13e90-0220-7883-8936-c3f03ad3ca30`,
`01a13eb6-692b-73c1-85dd-c3125c804ee5`,
`01a13ebc-30f1-7893-b8e0-b6517a934892`,
`01a13ed4-1df7-7700-913e-ba80402277ed`,
`01a13edd-8a23-7a53-acd7-06fb38d2fb5e`.
The last was still listed at resume and was explicitly killed in this round.
The others are no longer listed; historical cleanup lines exist except for the
incomplete earlier launch. No unattended sandbox-creation retry loop was used.

Final `sbx list` succeeded with empty output. Both requested scratch directories,
`/tmp/studio-work` and `/tmp/studio-repo`, were removed or already absent. The
recovered render was copied into ignored media/source before deleting scratch.
Four generated interrupted-download partial files were also removed. No other
worktree was changed.

## Public artifact checks

Real final check output:

```text
JSON validity: PASS (70 tracked JSON files).
Public artifact hygiene: PASS (34 changed files; no workstation paths, internal hosts, or key patterns).
Largest changed file: cookbook/blender-studio/media/demo.mp4 (3345167 bytes).
Requested scratch directories: absent.
```

Source and output SHA-256s pass the studio provenance tests. All three media
deliverables are below 5 MB; source frames, build environments, proof renders
and the lossless master are ignored, not committed. The font is hash pinned.
No key, private hostname, workstation path, or person name was added.

## Deviations

1. `run.py` clones public `main` then overlays the exact local judge/scene
   snapshot. This documented pre-publication path avoids pushing an unpublished
   branch. The clone SHA and snapshot digest are both printed.
2. The artifact is a constrained Blender scene script with eight literal
   settings, not arbitrary executable Python. The judge rebuilds trusted
   geometry. Visibility is sampled; it is not a continuous/subpixel guarantee.
3. Tools are verified from the pinned `blender` image instead of installed or
   downloaded by `setup.sh`. The exact build and embedded/host dependencies
   are checked; no archives or pip packages are fetched.
4. Media PNGs need not be byte-identical across re-renders; only verdict JSON
   must be byte-identical excluding `timing`. Every shipped file has a recorded
   SHA-256 verified against the sandbox copy.
5. The 30 fps master repeats twelve real poses at six poses/second. The process
   slot is a labelled compressed replay of measured self-test output, not an
   autonomous-agent screen recording.
6. Five unrelated pre-existing media tests fail as reported above; no other
   demo or its evidence was changed to conceal them.
7. Review panel and independent reproduction: see `media/REVIEW.json` and
   `REPRODUCE.md`.
