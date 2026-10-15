# FDM 3D-print toolpath: OrcaSlicer G-code judged by an independent interpreter + Klipper

An agent produces a real FDM 3D-print toolpath — a slicer profile plus the
G-code **OrcaSlicer** (slicing with the bundled *Bambu Lab A1 0.4 nozzle*
system profile) generates for a fixed L-bracket — and a judge it cannot fool
decides whether the result is right. A disposable sandbox helps because the
toolchain (OrcaSlicer AppImage, a pinned Klipper firmware build, the AVR
cross-compiler for the MCU data dictionary) installs in ~1-2 minutes, slices
a part in ~5 s and grades in ~1 min, and none of it pollutes your machine.

The judge never trusts the slicer's own statistics: a from-scratch G-code
interpreter (stdlib Python, `judge/interp.py`) replays the artifact and
measures every extruding move, layer Z sequence, deposited volume and
temperature against the analytic STL model, and **Klipper batch mode** —
the actual printer-firmware host stack — replays the same G-code through its
motion planner to prove it runs on real firmware within kinematic limits.

## One-command run

```bash
python3 run.py            # needs the sbx CLI + SBX_API_KEY; ~12 min total
```

Steps and measured wall time (fresh sandbox, 2 vCPU / ~3 GB RAM):

| step | what | wall time |
|---|---|---|
| `sbx create` | disposable sandbox | ~10 s |
| `judge/setup.sh` | OrcaSlicer 2.3.0 AppImage + Klipper (pinned commit) + apt libs | ~1.5 min |
| `judge/selftest.sh` | known-good passes; 10 single-edit mutants killed | ~9 min |
| `judge/grade.sh examples/good` | 12 gates, full verdict JSON | ~1 min |

Limits, plainly: slicing needs ~1.5 GB RAM peak; the whole grade fits in the
default 30-minute sandbox; nothing here prints plastic — see SPEC.md
non-goals.

## The task an agent gets

Inside the sandbox, `task/` holds `make_stl.py` (generates `bracket.stl`,
40 x 20 x 15 mm L-bracket at bed position 20,20, and the 25 mm calibration
cube) and `spec.json` (the print contract: PLA, 1.75 mm filament, 0.4 mm
nozzle, layer height band, max print time 90 min, max filament 12 g,
walls >= 2, bed 250 x 210 mm).

The artifact is a directory with two files the agent designs itself:

```
profile.ini    OrcaSlicer setting overrides (flat "key = value")
part.gcode     the G-code OrcaSlicer produces from bracket.stl with that profile
```

The judge merges `profile.ini` over its fixed base preset and **re-slices the
part itself**: the shipped G-code must match the re-slice (so a hand-edited
or fabricated G-code fails), and every behavioural gate is measured on
**both** the shipped G-code and the judge's re-slice — a bad G-code is
caught on the shipped file, a bad profile on its re-slice.

### Ask your agent

> In an agent-next sandbox, clone this repo at the `3dprint-gcode` demo and
> `cd cookbook/3dprint-gcode`. Read `SPEC.md` and `task/spec.json`, then run
> `bash judge/setup.sh` once. Your job: design `profile.ini` and produce
> `part.gcode` for `task/bracket.stl` (generate the STL with
> `python3 task/make_stl.py`) using the installed OrcaSlicer
> (`~/tools/orca/bin/orca-slicer --slice 0 --arrange 0 --orient 0
> --load-settings <machine.json;<filament.json;<your-process.json>
> --outputdir <dir> task/bracket.stl`), meeting every gate in SPEC.md.
> Slice with the Bambu Lab A1 0.4 nozzle machine preset and Bambu PLA Basic
> filament preset the judge uses. Iterate with
> `bash judge/grade.sh <your-artifact-dir> --json /tmp/v.json` until the
> verdict is PASS. The judge re-slices with your profile and compares G-codes,
> so make sure `part.gcode` is exactly what your `profile.ini` slices.

## The judge

`judge/grade.sh <dir> [--seed N] [--json out.json]` — 12 numeric gates, one
verdict JSON, exit 0 only if all pass:

1. `slice_clean` — OrcaSlicer exits 0 slicing the bracket with the profile
2. `artifact_matches` — the artifact's G-code equals the judge's re-slice
   (comment-stripped, whitespace-normalised)
3. `moves_inside_bed` — every extruding move endpoint in 250 x 210 mm, z >= 0
4. `moves_near_part` — every extruding move within 10 mm of the STL footprint
5. `layer_z_sequence` — layer Z monotonic; first layer 0.10–0.30 mm;
   steady heights <= 0.8 x nozzle and inside the spec band
6. `volume_matches_model` — deposited volume (E length x filament area, from
   the interpreter) inside the analytic band from the STL raster model
   (walls + infill from the profile) and filament mass <= 12 g
7. `cube_crosscheck` — the same measurement on the calibration cube must
   land in the cube's analytic band (judge self-consistency, fails the judge
   not the agent)
8. `pla_temperatures` — nozzle set points 180–230 °C, bed 35–70 °C while
   printing; bed heat precedes first extrusion
9. `time_estimate` — interpreter's constant-velocity time vs the slicer's
   own estimate within ±25 %, and <= 90 min
10. `klipper_batch` — `klippy.py printer.cfg -i part.gcode -o out.serial -v
    -d klipper.dict` exits 0 with no ERROR/shutdown lines
11. `profile_contract` — wall_loops >= 2, infill 10–40 %, 1.75 mm filament,
    0.4 mm nozzle
12. `judge_intact` — sha256 of `judge/` before == after

`judge/selftest.sh` proves the judge can fail: the known-good artifact
passes, 10 known-bad single-edit mutants (2.85 mm filament, PETG temps,
0.35 mm layers, X shifted off the bed, first layer Z0, relative/absolute E
mix-up, 100 % infill, cold nozzle, bed heats late, a travel cut through the
part) each fail at least one gate **and** the specific behavioural gate
named for it in SPEC.md; kill rate >= 90 % required, plus a determinism
check (same-seed verdicts byte-identical excluding `timing`) and a
judge-tamper check.

## Reproduce the numbers

All numbers in RECEIPT.md come from fresh-sandbox runs of the three
commands above; tool versions and download hashes are pinned in
`judge/setup.sh` and recorded in `judge/VERSIONS.txt`. Tolerances for
independent reproduction are in SPEC.md.
