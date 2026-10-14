# RECEIPT.md — Real command output from fresh runs

Exact output of the demo pipeline, run twice from a wiped install
(`rm -rf ~/.cnc-gcode` before each run), per the DEMO-STANDARD.
Environment: 2 vCPU, ~4 GB, Debian bookworm, Python 3.12.15, Linux x86_64.

## Run 1 — fresh install

### `bash judge/setup.sh`

```
setup: creating venv + installing pinned numpy

[notice] A new release of pip is available: 25.0.1 -> 26.2.1
[notice] To update, run: python3 -m pip install --upgrade pip
Collecting numpy==2.5.3 (from -r /home/user/w/cookbook/cnc-gcode/judge/requirements.txt (line 8))
  Downloading numpy-2.5.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (16.7 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 16.7/16.7 MB 57.8 MB/s eta 0:00:00
Installing collected packages: numpy
Successfully installed numpy-2.5.3

[notice] A new release of pip is available: 25.0.1 -> 26.2.1
[notice] To update, run: python3 -m pip install --upgrade pip
setup: downloading pinned debs for LinuxCNC rs274 (sha256-checked)
setup: extracted linuxcnc-uspace 2.9.0~pre1+git20230208.f1270d6ed7-1+deb12u2
setup: extracted libboost-python1.74.0 1.74.0+ds1-21
setup: extracted libpython3.11 3.11.2-6+deb12u9
setup: tool versions
Python 3.12.15
numpy 2.5.3
rs274 (LinuxCNC) 2.9.0~pre1+git20230208.f1270d6ed7-1+deb12u2 (Debian bookworm)
setup: wrote /home/user/w/cookbook/cnc-gcode/judge/VERSIONS.txt
setup: done
```

**Exit code:** 0 — wall **24.6 s** (fresh venv + pinned numpy + 3 pinned debs)

### `bash judge/selftest.sh`

```
selftest: known-good PASS
mutate: wrote 7 mutants to /tmp/tmp.QWyyyERtzV/mutants
selftest: mutant KILLED: deep_pass  (caught by: stepdown)
selftest: mutant KILLED: hot_feed  (caught by: process)
selftest: mutant KILLED: inch_mode  (caught by: units)
selftest: mutant KILLED: no_tool_offset  (caught by: gouge)
selftest: mutant KILLED: rapid_into_stock  (caught by: rapid_safety)
selftest: mutant KILLED: swapped_arcs  (caught by: residual)
selftest: mutant KILLED: wide_stepover  (caught by: stepover, residual)
selftest: kill rate 7/7 (100%)
selftest: determinism PASS (same seed -> identical verdict)
selftest: PASS
```

**Exit code:** 0 — wall **40.5 s**. Every mutant is killed by a **named gate**
(`inch_mode` by the `units` gate; a kill with no gate flagged fails the
self-test, and there were none).

### `bash judge/grade.sh examples/good/cam.py --json /tmp/rc_verdict1.json` (seed 20261014)

```
grade: PASS (all gates)
{
  "demo": "cnc-gcode",
  "artifact": "examples/good/cam.py",
  "seed": 20261014,
  "randomness": "none (deterministic judge; seed recorded but unused)",
  "gates": {
    "artifact": { "pass": true, "bad_imports": [], "imports": ["argparse", "json", "math"],
                  "cam_exit": 0, "cam_stderr_tail": "", "nc_bytes": 5718 },
    "units": { "pass": true, "g20_lines": [], "first_g21_line": 3 },
    "program": { "pass": true, "has_g21": true, "has_g90": true, "has_g17": true,
                 "m3_line": 4, "first_feed_line": 7, "m5_line": 258,
                 "last_feed_line": 255, "feed_moves": 183 },
    "envelope": { "pass": true, "first_violation": null, "moves": 250 },
    "stepdown": { "pass": true, "max_axial_mm": 2.0, "limit_mm": 2.0, "worst_move_line": 7 },
    "stepover": { "pass": true, "max_spacing_mm": 2.5, "limit_mm": 3.0,
                  "tolerance_mm": 0.05, "worst_move_line": 18,
                  "exempt_first_pass_moves": 36 },
    "process": { "pass": true, "chip_load_mm_per_tooth": [0.025, 0.1],
                 "limits": [0.02, 0.2], "spindle_moves_out_of_band": 0,
                 "feed_moves_out_of_band": 0, "spindle_rpm": 8000 },
    "rapid_safety": { "pass": true, "rapids_below_safe_z": 0, "max_rapid_hit_mm": 0.0,
                      "tolerance_mm": 0.01, "worst_move_line": null },
    "residual": { "pass": true, "residual_cells": 0, "residual_area_mm2": 0.0,
                  "worst_residual_mm": 0.0, "tolerance_mm": 0.05,
                  "unreachable_allowance_cells": 0 },
    "gouge": { "pass": true, "gouge_cells": 0, "gouged_area_mm2": 0.0,
               "worst_gouge_mm": 0.0, "tolerance_mm": 0.01 },
    "simulator_selfcheck": { "pass": true,
                 "line_slot_widths_mm": [6.0, 6.0, 6.0, 6.0, 6.0],
                 "circle_slot_widths_mm": [5.9569, 5.9819, 5.9569, 5.9819,
                                           5.9569, 5.9819, 5.9569, 5.9819],
                 "expected_mm": 6.0, "tolerance_mm": 0.05 },
    "reference": { "pass": true, "ref_exit": 0, "ref_units_mm": true,
                   "ref_tool": "LinuxCNC rs274 2.9.0~pre1+git20230208.f1270d6ed7-1+deb12u2",
                   "tolerance_mm": 0.001,
                   "feeds_diff": 0, "rapids_diff": 0, "arcs_diff": 0,
                   "z_max_diff_mm": 0.0, "z_min_diff_mm": 0.0,
                   "bbox_diff_mm": [0.0, 0.0, 0.0, 0.0] }
  },
  "summary": { "nc_lines": 258, "moves": 250, "cutting_moves": 174,
               "cells_cleared": 713592, "area_cleared_mm2": 1783.98,
               "stock_removed_mm3": 10703.9, "max_axial_engagement_mm": 2.0,
               "max_pass_spacing_mm": 2.5, "worst_residual_mm": 0.0,
               "worst_gouge_mm": 0.0 },
  "timing": { "cam_s": 0.17, "simulate_s": 1.31, "selfcheck_s": 0.14,
              "reference_s": 0.11, "total_s": 3.89 },
  "pass": true
}
```

**Exit code:** 0 — wall **4.5 s** (all 12 gates).

## Run 2 — fresh install again (`rm -rf ~/.cnc-gcode` first)

### `bash judge/setup.sh`

Same transcript as Run 1 (numpy venv + 3 pinned debs + sha256 checks).
**Exit code:** 0 — wall **20.2 s**.

### `bash judge/selftest.sh`

```
selftest: known-good PASS
mutate: wrote 7 mutants to /tmp/tmp.i8XDCm6H2z/mutants
selftest: mutant KILLED: deep_pass  (caught by: stepdown)
selftest: mutant KILLED: hot_feed  (caught by: process)
selftest: mutant KILLED: inch_mode  (caught by: units)
selftest: mutant KILLED: no_tool_offset  (caught by: gouge)
selftest: mutant KILLED: rapid_into_stock  (caught by: rapid_safety)
selftest: mutant KILLED: swapped_arcs  (caught by: residual)
selftest: mutant KILLED: wide_stepover  (caught by: stepover, residual)
selftest: kill rate 7/7 (100%)
selftest: determinism PASS (same seed -> identical verdict)
selftest: PASS
```

**Exit code:** 0 — wall **26.3 s**.

### `bash judge/grade.sh examples/good/cam.py --json /tmp/rc_verdict2.json`

```
grade: PASS (all gates)
```

**Exit code:** 0 — wall **3.1 s**. The full JSON equals Run 1's **byte for
byte, excluding the `timing` key** (checked with
`python3 -c` comparing the two parsed files after `pop("timing")` → `True`).

## Side-by-side

| | Run 1 (fresh) | Run 2 (fresh) |
|---|---|---|
| `setup.sh` exit / wall | 0 / 24.6 s | 0 / 20.2 s |
| `selftest.sh` exit / wall | 0 / 40.5 s | 0 / 26.3 s |
| kill rate | 7/7 (100%), all named gates | 7/7 (100%), all named gates |
| determinism line | PASS | PASS |
| `grade.sh` exit / wall | 0 / 4.5 s | 0 / 3.1 s |
| verdict JSON | PASS, 12/12 gates | **identical to Run 1** (excl. `timing`) |
| area cleared | 1783.98 mm² | identical |
| worst residual / gouge | 0.0 / 0.0 mm | identical |
| reference diffs (feeds/rapids/arcs, Z, bbox) | all 0 | identical |

## Reference cross-check details (LinuxCNC rs274)

- Tool: `rs274` from Debian bookworm `linuxcnc-uspace`
  `2.9.0~pre1+git20230208.f1270d6ed7-1+deb12u2` (LinuxCNC, GPLv2+,
  https://github.com/LinuxCNC/linuxcnc), plus its two runtime library debs
  (`libboost-python1.74.0 1.74.0+ds1-21`, `libpython3.11 3.11.2-6+deb12u9`).
  All three URLs + sha256 pins: `judge/reference_packages.tsv`; installed
  rootless by `setup.sh` (curl + sha256sum -c + dpkg-deb -x, no apt, no root).
- Good program: accepted (exit 0), canonical listing 458 calls, mm units;
  counts 165 feeds / 67 rapids / 18 arcs, Z ∈ [−6.000, +5.000], XY bbox
  [0, 0, 65, 45] — every field equal to the judge's own move list (diffs 0).
- Mutant note (required by the brief): the six semantically-bad mutants are
  syntactically valid G-code, so rs274 parses them without error (exit 0) —
  their defects are geometric/process-level, caught by the judge's analytic
  gates:

  | mutant | caught by judge gate(s) | rs274 |
  |---|---|---|
  | `deep_pass` | stepdown | accepted (syntax fine) |
  | `hot_feed` | process | accepted |
  | `inch_mode` | **units** | parses, but reports `USE_LENGTH_UNITS INCH` → also rejected by the reference semantics (mm job) |
  | `no_tool_offset` | gouge | accepted |
  | `rapid_into_stock` | rapid_safety | accepted |
  | `swapped_arcs` | residual | accepted |
  | `wide_stepover` | stepover, residual | accepted |

## Tool versions (judge/VERSIONS.txt, regenerated by each run)

```
# cnc-gcode judge: versions installed by judge/setup.sh
# (Linux x86_64)
Python 3.12.15
numpy 2.5.3
rs274 (LinuxCNC) 2.9.0~pre1+git20230208.f1270d6ed7-1+deb12u2 (Debian bookworm)
libboost-python1.74.0 1.74.0+ds1-21
libpython3.11 3.11.2-6+deb12u9
```

## Deviations

- **media/**: not yet created (`result.png`, `loop.png`, `demo.mp4`,
  `MANIFEST.json`, `make_media.sh`) — later task, tracked by the owner.
- **REPRODUCE.md**: not yet created — needs an independent agent (different
  model family) to follow README.md in a fresh sandbox; later task.
- **run.py end-to-end via `sbx`**: not executed here — no `SBX_API_KEY` in
  this environment. The in-sandbox command sequence it drives
  (clone + setup.sh + selftest.sh + grade.sh) was run directly instead,
  twice from a wiped install; `run.py` was syntax-checked
  (`python3 -m py_compile`) and its `shlex_quote` duplication removed.
- **examples/bad/**: not a separate directory; the seven known-bad artifacts
  are single-edit mutants generated on the fly by `judge/mutate.py`
  (SPEC.md allows "examples/bad/ or judge/mutants.py").
- **Reference candidates tried before rs274** (owner direction: prefer
  mature OSS): CAMotics — needs Qt/X11 and a long source build, does not
  install cleanly headless on 2 vCPU / 4 GB; building rs274 from the LinuxCNC
  source tree — needs the full linuxcnc build system. The packaged standalone
  `rs274` interpreter installed in minutes and is what gate `reference` uses.
