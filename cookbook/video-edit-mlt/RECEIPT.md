# RECEIPT — video-edit-mlt

2026-10-15, official default CPU sandboxes, seed 1. RUN-1 and RUN-2
cloned `f5651a00087e1b22e085b81076dce83420dccdf4`; the successful retry,
RUN-3, cloned `82e7bde6a44b0efcc7e0ec365e2df0b12402d8b5`.
Installation progress is omitted from these verbatim excerpts; no measured
verdict or failure is omitted.

Command for each fresh run:

```bash
python3 cookbook/video-edit-mlt/run.py --ref sbx/demo-video-edit-mlt
```

## Fresh runs

| step | RUN-1, success | RUN-2, failed | RUN-3, success |
|---|---|---|---|
| create | exit 0, 2.7 s | exit 0, 3.2 s | exit 0, 1.2 s |
| clone | exit 0, 26.6 s | exit 0, 16.0 s | exit 0, 10.7 s |
| setup from nothing | exit 0, 189.1 s | exit 0, 122.2 s | exit 0, 118.9 s |
| selftest | exit 0, 634.7 s | exit 0, 353.5 s | exit 0, 277.4 s |
| unit tests | 24 OK | 24 OK | 24 OK |
| mutants at intended gates | 11/11, 100% | 11/11, 100% | 11/11, 100% |
| determinism / judge integrity | OK / OK | OK / OK | OK / OK |
| final grade | exit 0, 30.7 s | runner timeout, exit 1, 330.0 s | exit 0, 28.7 s |
| sandbox cleanup | confirmed gone | confirmed gone | confirmed gone |
| total | 890.4 s | 861.6 s, failed | 439.2 s, exit 0 |

RUN-1 and RUN-3 are the two successful fresh reproductions. Their complete
verdicts are identical after removing `timing`, verified by parsing both
real run logs. RUN-2 is retained as a failed run, not counted as a pass.

### RUN-1 output

```text
run: [2.7s] sbx create --timeout-min 120 -> exit 0
01a1401d-45c9-71d1-b300-aa3ac696b6f6
run: sandbox 01a1401d-45c9-71d1-b300-aa3ac696b6f6
run: [26.6s] git clone -> exit 0
Cloning into '/tmp/repo'...
f5651a00087e1b22e085b81076dce83420dccdf4
run: [189.1s] setup -> exit 0
setup: OK
run: [634.7s] selftest -> exit 0
Ran 24 tests in 0.978s
OK
selftest: known-good PASSED all gates
selftest: killed off_by_one_cut (gate: edl; intended: edl)
selftest: killed wrong_in_point (gate: edl; intended: edl)
selftest: killed clip_order_swapped (gate: edl; intended: edl)
selftest: killed hard_cut (gate: dissolve; intended: dissolve)
selftest: killed short_dissolve (gate: dissolve; intended: dissolve)
selftest: killed logo_wrong_corner (gate: logo; intended: logo)
selftest: killed logo_too_long (gate: logo; intended: logo)
selftest: killed no_ducking (gate: ducking; intended: ducking)
selftest: killed too_loud (gate: loudness; intended: loudness)
selftest: killed wrong_fps (gate: format; intended: format)
selftest: killed wrong_resolution (gate: format; intended: format)
selftest: kill rate 11/11 = 100%
selftest: determinism OK (two --seed 1 grades, excluding timing)
selftest: judge integrity OK
selftest: OK
run: [30.7s] grade -> exit 0
```

Full RUN-1 verdict:

```json
{
  "failed_gate": null,
  "gates": {
    "dissolve": {
      "errors": [],
      "measured": 0.041486,
      "pass": true,
      "threshold": "max ramp error <=0.20; endpoints <=0.15 and >=0.85; decrease <=0.05",
      "weights": [
        0.0, 0.041137, 0.082828, 0.113051, 0.154188,
        0.205476, 0.236137, 0.27517, 0.315983, 0.35712,
        0.398256, 0.439948, 0.481085, 0.518915, 0.559289,
        0.601304, 0.639458, 0.683254, 0.724391, 0.763423,
        0.793761, 0.841627, 0.882764, 0.916848, 0.958863
      ]
    },
    "ducking": {
      "measured": 11.948775,
      "pass": true,
      "rms_inside": 0.03609479,
      "rms_outside": 0.14309144,
      "threshold": ">=8.0 dB; outside music RMS >1e-5",
      "window_depths_db": [11.948775, 11.97804]
    },
    "edl": {
      "blend_barcode_limit": 0.12,
      "blend_barcode_max_error": 0.008642,
      "checked_frames": 225,
      "errors": [],
      "measured": 0,
      "pass": true,
      "threshold": "0 mismatched output frames"
    },
    "format": {
      "measured": {
        "audio": {"channels": 2, "codec_name": "aac", "sample_rate": "48000"},
        "codec_name": "h264",
        "field_order": "progressive",
        "height": 720,
        "nb_read_frames": "225",
        "pix_fmt": "yuv420p",
        "r_frame_rate": "25/1",
        "sample_aspect_ratio": "1:1",
        "width": 1280
      },
      "pass": true,
      "threshold": {
        "acodec": "aac", "channels": 2, "fps_den": 1, "fps_num": 25,
        "frames": 225, "height": 720, "sample_rate": 48000,
        "vcodec": "h264", "width": 1280
      }
    },
    "integrity": {"measured": 0, "pass": true, "threshold": "0 changed judge files"},
    "logo": {
      "measured": {"max_off": 0.079241, "min_on": 0.999981},
      "pass": true,
      "threshold": "on >=0.85, off <0.30 on every frame"
    },
    "loudness": {
      "measured": {"integrated_lufs": -16.0, "true_peak_dbtp": -8.5},
      "pass": true,
      "threshold": {"lufs": [-17.0, -15.0], "true_peak_max_dbtp": -1.0}
    },
    "power": {
      "frames": 450, "measured": 0, "pass": true,
      "threshold": "0 barcode errors across 450 raw frames"
    },
    "security": {"measured": 0, "pass": true, "threshold": "0 unsafe XML constructs"}
  },
  "passed": true,
  "schema": "video-edit-mlt/verdict@1",
  "seed": 1,
  "timing": {"total_s": 24.112},
  "verdict": "PASS"
}
```

Whitespace in the JSON above is compacted; every key and value is preserved.

```text
run: SUMMARY passed=True dissolve=0.041486 ducking=11.948775 edl=0 loudness={'integrated_lufs': -16.0, 'true_peak_dbtp': -8.5}
run: killed and confirmed gone: 01a1401d-45c9-71d1-b300-aa3ac696b6f6
run: total wall 890.4s
```

### RUN-2 output

```text
run: [3.2s] sbx create --timeout-min 120 -> exit 0
01a1401d-46ad-7741-a3c3-c8abea475dec
run: sandbox 01a1401d-46ad-7741-a3c3-c8abea475dec
run: [16.0s] git clone -> exit 0
Cloning into '/tmp/repo'...
f5651a00087e1b22e085b81076dce83420dccdf4
run: [122.2s] setup -> exit 0
setup: OK
run: [353.5s] selftest -> exit 0
Ran 24 tests in 0.875s
OK
selftest: known-good PASSED all gates
selftest: killed off_by_one_cut (gate: edl; intended: edl)
selftest: killed wrong_in_point (gate: edl; intended: edl)
selftest: killed clip_order_swapped (gate: edl; intended: edl)
selftest: killed hard_cut (gate: dissolve; intended: dissolve)
selftest: killed short_dissolve (gate: dissolve; intended: dissolve)
selftest: killed logo_wrong_corner (gate: logo; intended: logo)
selftest: killed logo_too_long (gate: logo; intended: logo)
selftest: killed no_ducking (gate: ducking; intended: ducking)
selftest: killed too_loud (gate: loudness; intended: loudness)
selftest: killed wrong_fps (gate: format; intended: format)
selftest: killed wrong_resolution (gate: format; intended: format)
selftest: kill rate 11/11 = 100%
selftest: determinism OK (two --seed 1 grades, excluding timing)
selftest: judge integrity OK
selftest: OK
run: [330.0s] grade -> exit 1
run: FAILED: grade: grade timed out after 300s
run: killed and confirmed gone: 01a1401d-46ad-7741-a3c3-c8abea475dec
run: total wall 861.6s
```

There is no final RUN-2 verdict to paste. A successful selftest is not a
substitute for the missing final grade.

### RUN-3 output, successful retry

```text
run: [1.2s] sbx create --timeout-min 120 -> exit 0
01a14032-80ce-7ad2-a8e4-62877fa95ab3
run: sandbox 01a14032-80ce-7ad2-a8e4-62877fa95ab3
run: [10.7s] git clone -> exit 0
Cloning into '/tmp/repo'...
82e7bde6a44b0efcc7e0ec365e2df0b12402d8b5
run: [118.9s] setup -> exit 0
setup: OK
run: [277.4s] selftest -> exit 0
Ran 24 tests in 0.692s
OK
selftest: known-good PASSED all gates
selftest: killed off_by_one_cut (gate: edl; intended: edl)
selftest: killed wrong_in_point (gate: edl; intended: edl)
selftest: killed clip_order_swapped (gate: edl; intended: edl)
selftest: killed hard_cut (gate: dissolve; intended: dissolve)
selftest: killed short_dissolve (gate: dissolve; intended: dissolve)
selftest: killed logo_wrong_corner (gate: logo; intended: logo)
selftest: killed logo_too_long (gate: logo; intended: logo)
selftest: killed no_ducking (gate: ducking; intended: ducking)
selftest: killed too_loud (gate: loudness; intended: loudness)
selftest: killed wrong_fps (gate: format; intended: format)
selftest: killed wrong_resolution (gate: format; intended: format)
selftest: kill rate 11/11 = 100%
selftest: determinism OK (two --seed 1 grades, excluding timing)
selftest: judge integrity OK
selftest: OK
run: [28.7s] grade -> exit 0
```

Full RUN-3 verdict (whitespace compacted, all keys and values preserved):

```json
{
  "failed_gate": null,
  "gates": {
    "dissolve": {
      "errors": [],
      "measured": 0.041486,
      "pass": true,
      "threshold": "max ramp error <=0.20; endpoints <=0.15 and >=0.85; decrease <=0.05",
      "weights": [
        0.0, 0.041137, 0.082828, 0.113051, 0.154188,
        0.205476, 0.236137, 0.27517, 0.315983, 0.35712,
        0.398256, 0.439948, 0.481085, 0.518915, 0.559289,
        0.601304, 0.639458, 0.683254, 0.724391, 0.763423,
        0.793761, 0.841627, 0.882764, 0.916848, 0.958863
      ]
    },
    "ducking": {
      "measured": 11.948775,
      "pass": true,
      "rms_inside": 0.03609479,
      "rms_outside": 0.14309144,
      "threshold": ">=8.0 dB; outside music RMS >1e-5",
      "window_depths_db": [11.948775, 11.97804]
    },
    "edl": {
      "blend_barcode_limit": 0.12,
      "blend_barcode_max_error": 0.008642,
      "checked_frames": 225,
      "errors": [],
      "measured": 0,
      "pass": true,
      "threshold": "0 mismatched output frames"
    },
    "format": {
      "measured": {
        "audio": {"channels": 2, "codec_name": "aac", "sample_rate": "48000"},
        "codec_name": "h264", "field_order": "progressive", "height": 720,
        "nb_read_frames": "225", "pix_fmt": "yuv420p", "r_frame_rate": "25/1",
        "sample_aspect_ratio": "1:1", "width": 1280
      },
      "pass": true,
      "threshold": {
        "acodec": "aac", "channels": 2, "fps_den": 1, "fps_num": 25,
        "frames": 225, "height": 720, "sample_rate": 48000,
        "vcodec": "h264", "width": 1280
      }
    },
    "integrity": {"measured": 0, "pass": true, "threshold": "0 changed judge files"},
    "logo": {
      "measured": {"max_off": 0.079241, "min_on": 0.999981},
      "pass": true, "threshold": "on >=0.85, off <0.30 on every frame"
    },
    "loudness": {
      "measured": {"integrated_lufs": -16.0, "true_peak_dbtp": -8.5},
      "pass": true,
      "threshold": {"lufs": [-17.0, -15.0], "true_peak_max_dbtp": -1.0}
    },
    "power": {
      "frames": 450, "measured": 0, "pass": true,
      "threshold": "0 barcode errors across 450 raw frames"
    },
    "security": {"measured": 0, "pass": true, "threshold": "0 unsafe XML constructs"}
  },
  "passed": true,
  "schema": "video-edit-mlt/verdict@1",
  "seed": 1,
  "timing": {"total_s": 19.292},
  "verdict": "PASS"
}
```

```text
run: SUMMARY passed=True dissolve=0.041486 ducking=11.948775 edl=0 loudness={'integrated_lufs': -16.0, 'true_peak_dbtp': -8.5}
run: killed and confirmed gone: 01a14032-80ce-7ad2-a8e4-62877fa95ab3
run: total wall 439.2s
receipt: run.py exit 0
```

## Versions

Setup output from the fresh runs:

```text
ffmpeg version n8.1.2-34-g9b6c8969e0 Copyright (c) 2000-2026 the FFmpeg developers
ffprobe version n8.1.2-34-g9b6c8969e0 Copyright (c) 2007-2026 the FFmpeg developers
Python 3.12.15
numpy 2.2.6
Pillow 11.3.0
libegl1 1.6.0-1
libopengl0 1.6.0-1
Shotcut 26.8.1 sha256 c4befab2240964389df6139f00aae0b92949f398fd98083b922f3aabd8b7a844
```

`QT_QPA_PLATFORM=offscreen Shotcut.app/melt --version`, measured in the
development sandbox with the same checked official archive:

```text
melt 7.41.0
```

RUN-3's setup also records `melt 7.41.0` directly.

## Regression proof

The new `Barcode.test_source_frame_size` was run against the previous
generator loaded from Git, not against a failing import:

```text
test_source_frame_size (test_edl.Barcode.test_source_frame_size) ... FAIL
AssertionError: 2795520 != 2764800
Ran 1 test in 0.071s
FAILED (failures=1)
regression proof: expected assertion failure on old source generator confirmed
```

The unchanged test passes on the corrected generator in both fresh runs.

## Final unit and shared-tool checks

After the fresh runs, three additional tests cover silent EBU R128 output,
missing summaries, and integrity of bytecode files. The good-artifact
measurements are unchanged.

```text
Ran 27 tests in 1.108s
OK
guard: good passed= True failed_gate= None loudness= {'integrated_lufs': -16.0, 'true_peak_dbtp': -8.5}
guard: silent passed= False failed_gate= loudness loudness= {'integrated_lufs': -70.0, 'true_peak_dbtp': '-inf'}
```

The intentionally silent render exits 1, reports its actual `-inf` peak
as a JSON string, and dies at loudness, rather than crashing the parser.
Warm `judge/setup.sh` also exits 0 after re-verifying the installed tool
tree, checked archive and all 450 cached source frames, without another
download or pip install.

Repository shared tools, inside the media sandbox:

```text
$ python3 cookbook/tools/test_video_gate.py
direct_script_exit=0
$ python3 -m pytest -q cookbook/tools/test_video_gate.py cookbook/tools/test_result.py
...........................................................              [100%]
59 passed in 495.93s (0:08:15)
```

```text
manifests: 108 JSON files valid; marketplace path and all required fields passed
receipt: both full pasted verdicts agree outside timing
result.png dpi (199.9996, 199.9996)
loop.png dpi (199.9996, 199.9996)
caption cap height: 47 px >= 43.2 px
```

The direct script invocation defines tests but does not collect them;
the pytest invocation above is the actual regression suite.

Media commands:

```bash
bash judge/grade.sh examples/good/edit.mlt --seed 1 \
  --export media/data --json media/data/verdict.json
bash media/make_media.sh --reuse
```

Real output excerpts:

```text
OK media/result.json
OK cookbook/video-edit-mlt/media/result.json
final media: 15/15 video checks pass; 12 manifest hashes verified; Python syntax OK
final video bytes: 1880436
```

`media/video_gate.json` records all 15 checks passing: 1920×1080,
44.0 s, 30 fps, H.264/yuv420p, 1.7933 MiB, faststart,
first-frame luma mean 93.3114 / std 49.2037, 1.8182 scene cuts per 10 s,
and end-card YDIF 0.0. The silent web video is intentional; its audio
proof comes from the judge's measurements of the actual AAC render.

Not run: unrelated CLI Python 3.10/3.13 matrix; no CLI files changed.

## Development iteration measurements

`bash judge/grade.sh examples/good/edit.mlt --export media/data --json /tmp/good.json`
initially reported the following real measurements. These drive the first
bar of `media/data/history.json`; the second bar is RUN-1's full verdict.

| gate | initial measurement | pass |
|---|---|---|
| security | 0 unsafe constructs | yes |
| power | 450 source frames, 0 decode errors | yes |
| format | 1280×720, 25 fps, 225 frames | yes |
| EDL | 75 colour mismatches | no |
| dissolve | maximum ramp error 0.065222 | yes |
| logo | min on 0.999993, max off 0.057121 | yes |
| loudness | −20.2 LUFS, −13.2 dBTP | no |
| ducking | 11.992593 dB | yes |
| integrity | 1 changed judge file | no |

The sources originally omitted BT.709 metadata, and the master gain was
too low. The integrity guard also caught setup still writing VERSIONS.txt
during that first development grade. Sequencing setup before grading,
explicit source colour metadata and measured gain calibration fixed the
three failures. This is a two-edit builder history, not an autonomous
agent session.

## Final cleanup

All seven sandboxes created during this work were killed. The successful
runner cleanup lines are pasted above. Development and superseded runs
were also explicitly killed, not abandoned.

Last cleanup command:

```text
$ sbx kill 01a14032-8177-7d11-afa8-cb8a2fa650bf
killed 01a14032-8177-7d11-afa8-cb8a2fa650bf
$ sbx list
```

The final listing exited 0 and printed no rows. Sandbox scratch files and
the ignored lossless master were removed with their disposable sandboxes.

## Deviations

- The complete proof suite exceeds the standard's five-minute CPU target:
  successful runs took 7m19s and 14m50s. Single grades took 19.292–24.112 s
  of sandbox computation.
  Network, download, checksum and repeated-mutant work are included in the
  one-command total, not hidden.
- The first development selftest rejected 10/11 (91%) but correctly exited
  1 because this demo requires 100%. MLT ignored the attempted hard-cut
  mutant's luma `start/end` edit. Removing the actual compositor fixed
  it, a regression test now covers that, and both recorded fresh selftests
  reject all eleven at their intended gates.
- Two earlier fresh runs at `31a96085` were stopped during setup after
  discovering that ineffective mutant. Both sandboxes were explicitly
  killed and a successful inventory showed neither id.
- A sandbox API outage caused RUN-2's final grade retrieval to time out.
  Subsequent `sbx list` calls returned `ProxyError: 502 Bad Gateway`.
  No successful verdict is inferred from those transport errors.
- After the recorded commit, setup's library-cache lookup uses
  `/sbin/ldconfig` (not always on PATH) and its version receipt uses
  `melt --version` instead of a query listing. Neither changes pixels,
  PCM or the judge thresholds.
- Post-receipt robustness fixes parse silent audio's `-inf` true peak
  without crashing and checksum every judge file, including bytecode.
  These add three unit tests without changing the good edit's numbers.
- Independent reproduction and two-family blind video review remain
  explicitly unperformed in REPRODUCE.md and media/REVIEW.json.
