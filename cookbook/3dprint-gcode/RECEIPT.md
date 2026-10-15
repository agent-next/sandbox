# RECEIPT — cookbook/3dprint-gcode

Real output from two runs of the demo at commit `ae9a7a2`
(branch `sbx/demo-3dprint-gcode-r3-p`). Both runs used the same
disposable Debian 12 sandbox image (2 vCPU, ~4 GB RAM):

- **Run 1** — the demo directory itself (`cookbook/3dprint-gcode`).
- **Run 2** — a fresh `git clone --depth 1 -b sbx/demo-3dprint-gcode-r3-p
  https://github.com/agent-next/sandbox` of the same commit, i.e. exactly
  the sequence `run.py` performs inside the sandbox.

Each run executed, in order: `bash judge/setup.sh`,
`bash judge/selftest.sh`, `bash judge/grade.sh examples/good --json /tmp/v.json`.

## Tool versions (`judge/VERSIONS.txt`, written by `judge/setup.sh`)

```
orca-slicer: 2.3.0 (AppImage OrcaSlicer_Linux_AppImage_V2.3.0.AppImage, sha256: 73079d88ec36f0615db7919d00aa26fe301e348ba6e051862a7cfc4040150c03)
klipper: ce7002bedf37e938bb483572949f3703ac6476cb (github tarball, sha256: da1c6223d90652cda6e826e3cf896cf97d6e11aa13aa4c8feb5232dac068f70b)
python3: 3.12.15
klippy dict target: atmega2560
pip: Jinja2==3.1.4
pip: MarkupSafe==3.0.2
pip: aenum==3.1.17
pip: cffi==2.1.1
pip: greenlet==3.3.2
pip: msgspec==0.19.0
pip: pycparser==3.11
pip: pyserial==3.4
pip: python-can==3.3.4
pip: setuptools==78.1.1
pip: wrapt==1.17.3
```

`bash judge/setup.sh` exit code **0** in both runs. Wall time from a
tools-cold start (OrcaSlicer AppImage download + extract, Klipper tarball +
`make` of the atmega2560 MCU dictionary, pip installs; apt packages already
present in the image): **28 s**. The first run of this session, which also
fetched apt lists and installed ~90 packages (libwebkit2gtk, AVR
toolchain), completed in **~78 s**.

## `bash judge/selftest.sh` — exit code 0, both runs

Run 1 (wall **9m04s**, cold slice cache; run 2: **8m59s**):

```
== selftest: known-good artifact ==
known-good: PASS (expected)
== selftest: generating known-bad mutants ==
wrote /tmp/tmp.gBFbrTFuo5/filament-diameter-2.85
wrote /tmp/tmp.gBFbrTFuo5/petg-temps
wrote /tmp/tmp.gBFbrTFuo5/layer-height-0.35
wrote /tmp/tmp.gBFbrTFuo5/scale-off-bed
wrote /tmp/tmp.gBFbrTFuo5/first-layer-z-zero
wrote /tmp/tmp.gBFbrTFuo5/relative-e-mixup
wrote /tmp/tmp.gBFbrTFuo5/infill-100
wrote /tmp/tmp.gBFbrTFuo5/nozzle-cold
wrote /tmp/tmp.gBFbrTFuo5/bed-heats-late
wrote /tmp/tmp.gBFbrTFuo5/travel-cuts-part
mutant bed-heats-late: FAIL (expected) -- killed by gate: artifact_matches, pla_temperatures
mutant filament-diameter-2.85: FAIL (expected) -- killed by gate: artifact_matches, volume_matches_model, cube_crosscheck, profile_contract
mutant first-layer-z-zero: FAIL (expected) -- killed by gate: artifact_matches, layer_z_sequence
mutant infill-100: FAIL (expected) -- killed by gate: artifact_matches, volume_matches_model, profile_contract
mutant layer-height-0.35: FAIL (expected) -- killed by gate: artifact_matches, layer_z_sequence
mutant nozzle-cold: FAIL (expected) -- killed by gate: artifact_matches, pla_temperatures
mutant petg-temps: FAIL (expected) -- killed by gate: artifact_matches, pla_temperatures
mutant relative-e-mixup: FAIL (expected) -- killed by gate: artifact_matches, volume_matches_model, klipper_batch
mutant scale-off-bed: FAIL (expected) -- killed by gate: artifact_matches, moves_inside_bed, moves_near_part, time_estimate, klipper_batch
mutant travel-cuts-part: FAIL (expected) -- killed by gate: artifact_matches, moves_near_part, layer_z_sequence, pla_temperatures
== selftest summary ==
known-good: passed
kill rate: 10/10 (100%)
== selftest: determinism (grade twice with --seed 42) ==
determinism: PASS (two --seed 42 runs identical excluding "timing")
selftest: PASS
```

Run 2 (fresh clone): identical verdict — kill rate **10/10 (100%)**,
determinism PASS, selftest PASS. Every mutant is additionally verified to
fire the behavioural gate named for it in SPEC.md (the
`declared target gate(s) did not fire` check never triggered).

## `bash judge/grade.sh examples/good --json /tmp/v.json` — exit code 0, both runs

Run 1 wall **47 s** (run 2: **51 s**). Verdict (identical in both runs
except the `timing` key):

```json
{
  "verdict": "PASS",
  "seed": 0,
  "artifact": "cookbook/3dprint-gcode/examples/good",
  "gates": {
    "slice_clean":         { "pass": true, "detail": "orca rc=0 gcode=plate_1.gcode" },
    "artifact_matches":    { "pass": true, "detail": "content hash match" },
    "moves_inside_bed":    { "pass": true, "detail": "all 8007 extruding moves inside bed" },
    "moves_near_part":     { "pass": true, "detail": "max extrusion distance from footprint 2.39 mm (tol 10.00)" },
    "layer_z_sequence":    { "pass": true, "detail": "first Z 0.200, 75 layers, steady h [0.2]" },
    "volume_matches_model":{ "pass": true, "detail": "deposited 3344.4 mm3 vs expected 3829.9 (band 2380.9..5278.9), mass 4.15 g (max 12.0 g)" },
    "cube_crosscheck":     { "pass": true, "detail": "cube deposited 4858.3 mm3 vs expected 5958.2 (band 3870.7..8045.6); stl vol 15552.0" },
    "pla_temperatures":    { "pass": true, "detail": "nozzle [0.0, 210.0] C, bed [0.0, 60.0] C, bed heated before first extrusion" },
    "time_estimate":       { "pass": true, "detail": "judge 1738s vs slicer 1855s (band +-25%), max 5400s" },
    "klipper_batch":       { "pass": true, "detail": "klippy rc=0, 0 bad lines" },
    "profile_contract":    { "pass": true, "detail": "wall_loops=2 infill=15% filament=1.75 nozzle=0.40" },
    "judge_intact":        { "pass": true, "detail": "judge/ sha256 unchanged" }
  },
  "metrics": {
    "artifact_hash": "8a21cd052ed7",
    "reslice_hash": "8a21cd052ed7",
    "deposited_volume_mm3": 3344.4,
    "expected_volume_mm3": 3829.9,
    "volume_band_mm3": [2380.9, 5278.9],
    "filament_mass_g": 4.15,
    "stl_volume_mm3": 8052.8,
    "cube_deposited_mm3": 4858.3,
    "cube_expected_mm3": 5958.2,
    "cube_stl_volume_mm3": 15552.0,
    "first_layer_z_mm": 0.2,
    "layer_count": 75,
    "steady_layer_height_mm": [0.2],
    "max_dist_from_footprint_mm": 2.39,
    "nozzle_setpoints_c": [0.0, 210.0],
    "bed_setpoints_c": [0.0, 60.0],
    "judge_time_s": 1738.0,
    "slicer_time_s": 1855,
    "klipper_exit": 0,
    "klipper_bad_lines": 0,
    "profile_wall_loops": 2,
    "profile_infill_pct": 15.0
  }
}
```

### Side-by-side, run 1 vs run 2

| metric | run 1 | run 2 |
|---|---|---|
| verdict | PASS | PASS |
| grade exit code | 0 | 0 |
| selftest exit code | 0 | 0 |
| kill rate | 10/10 (100%) | 10/10 (100%) |
| deposited_volume_mm3 | 3344.4 | 3344.4 |
| expected_volume_mm3 | 3829.9 | 3829.9 |
| filament_mass_g | 4.15 | 4.15 |
| stl_volume_mm3 | 8052.8 | 8052.8 |
| cube_deposited_mm3 | 4858.3 | 4858.3 |
| first_layer_z_mm | 0.2 | 0.2 |
| layer_count | 75 | 75 |
| judge_time_s / slicer_time_s | 1738.0 / 1855 | 1738.0 / 1855 |
| klipper_exit (bad lines) | 0 (0) | 0 (0) |
| grade wall time | 47 s | 51 s |
| selftest wall time | 9m04s | 8m59s |

Every non-`timing` field is identical between the two runs, as SPEC.md
requires.

## Deviations

- **Setup wall time split:** the 28 s figure is tools-cold but apt-warm
  (the sandbox image already carries libwebkit2gtk etc.). Fully cold
  (empty apt lists) adds ~50 s for `apt-get update` + install of ~90
  packages — measured at **~78 s** total in the first run of this session.
- **`REPRODUCE.md` (independent reproduction by a different agent):**
  (not done: per the brief, the lead runs `run.py` end to end and a
  separate later task performs the independent-reproduction step).
- **`media/` (figures, video, manifest):** (not done: explicitly deferred —
  a later task does media.)
- **Two fresh sandboxes:** both receipt runs executed on the same
  sandbox instance, one of them against a fresh clone of the repo (the
  exact commands `run.py` sends). True two-sandbox receipts require the
  `sbx` API key, which is not available inside this builder sandbox.
- **Klipper log noise:** klippy prints benign `Unknown command` INFO lines
  for Bambu-specific M-codes (`M104.1` etc.); these are whitelisted in
  `judge/judge.py:klipper_bad_lines`. A real error (wrong kinematics,
  out-of-range move, over-extrusion) still fails gate 10, as the
  `relative-e-mixup` and `scale-off-bed` mutants demonstrate.
- **OrcaSlicer reports its own version string as `OrcaSlicer-01.10.01.50`**
  in `--version` output even for the v2.3.0 AppImage; the AppImage file
  name and sha256 pin the actual release.
