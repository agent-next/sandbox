# RECEIPT — `cookbook/solidcraft-cad/`

Real output of `python3 cookbook/solidcraft-cad/run.py --ref sbx/demo-solidcraft-cad`
at commit `2aa6eaf`, run twice on 2026-10-15. Each run created a fresh sandbox
(agent-next default template, Debian 12, 2 vCPU) and installed everything from
nothing. The two runs were started 5 s apart.

## Two fresh-sandbox runs side by side

| | RUN-1 | RUN-2 |
|---|---|---|
| `sbx create --timeout-min 30` | exit 0, 1.1 s | exit 0, 1.6 s |
| `git clone` | exit 0, 7.6 s | exit 0, 5.4 s |
| `judge/setup.sh` (SolidCraft tarball + hashed pip install) | exit 0, 115.3 s | exit 0, 131.6 s |
| `judge/selftest.sh` | exit 0, 812.4 s | exit 0, 784.3 s |
| unit tests (`tests/`, stdlib) | 16 OK | 16 OK |
| known-good designs (3) | all PASSED | all PASSED |
| kill rate | **19/19 = 100 %** | **19/19 = 100 %** |
| determinism (two `--seed 1` grades) | byte-identical outside `timing` | same |
| `judge/grade.sh examples/good/design.json` | exit 0, 55.0 s | exit 0, 66.4 s |
| cleanup | `killed and confirmed gone` | `killed and confirmed gone` |
| `run.py` exit / wall | 0 / 16 m 36 s | 0 / 16 m 33 s |

The verdict JSON of the two runs is identical except for the per-gate `timing`
values. The killed-mutant lines are identical, gate for gate.

Key numbers (both runs):

| number | value | limit |
|---|---|---|
| OCCT volume / analytic | 16644.9 / 16644.9 mm³, rel. dev. 6.94266e-10 | 0.2 % |
| bounding box max deviation | 1e-07 mm | 0.01 mm |
| bolt holes Ø / PCD / spacing / nominal position | 4.9e-15 mm / 7.1e-15 mm / 2.8e-14° / 8.9e-15 mm | 0.02 mm / 0.05 mm / 0.1° / 0.05 mm |
| wall checks (exact OCCT booleans) | 20 of 20 pass | — |
| min edge distance | 7.8 mm | ≥ 5 mm |
| mass (6061, 2.70 g/cm³) | 44.9412 g | ≤ 52 g |
| SolidCraft vs OCCT: volume / area / centre of mass | 1.2234e-06 / 4.89179e-07 / 9.82488e-06 mm | 0.1 % / 0.1 % / 0.01 mm |
| parametric `thickness` 6 → 8 mm: ΔV, analytic | 5124.18 / 5124.18 mm³ (rel. 5.13871e-12), rebuilt part: valid, bbox dev. 1e-07 mm, 20 wall checks pass | 0.2 % |
| STL | 3772 triangles, 0 non-manifold edges/vertices, 0 degenerate, volume 0.013085 % from STEP | 0.5 % |

Self-test lines (RUN-1; RUN-2 identical apart from the sandbox id):

```text
selftest: unit tests (judge functions, run.py fault injection)
Ran 16 tests in 62.460s
OK
selftest: grading known-good …/examples/good/design-csg.json
selftest: known-good PASSED all gates
selftest: grading known-good …/examples/good/design-renamed.json
selftest: known-good PASSED all gates
selftest: grading known-good …/examples/good/design.json
selftest: known-good PASSED all gates
selftest: killed    bore_missing (gate: volume)
selftest: killed    boss_height (gate: occt_shape)
selftest: killed    broken_command (gate: build)
selftest: killed    csg_blocked_holes (gate: features)
selftest: killed    csg_bore_shifted (gate: features)
selftest: killed    csg_corner_missing (gate: volume)
selftest: killed    csg_shift_on_rebuild (gate: parametric)
selftest: killed    csg_thin_web (gate: features)
selftest: killed    file_export (gate: build)
selftest: killed    font_outside (gate: build)
selftest: killed    hole_extra (gate: volume)
selftest: killed    hole_missing (gate: volume)
selftest: killed    hole_off_pcd (gate: features)
selftest: killed    hole_rotated (gate: features)
selftest: killed    hole_small (gate: volume)
selftest: killed    holes_all_rotated (gate: features)
selftest: killed    literal_thickness (gate: parametric)
selftest: killed    no_fillet (gate: volume)
selftest: killed    too_thick (gate: occt_shape)
selftest: kill rate 19/19 = 100%
selftest: determinism OK (two --seed 1 runs byte-identical outside timing)
selftest: OK
run: SUMMARY passed=True volume=16644.9 mm3 (analytic 16644.9) mass=44.9412 g bolt_holes=4 kernels_agree=1.2234e-06 param_dV=5124.18 mm3
```

## Versions (`judge/VERSIONS.txt`, written by setup.sh; same in both runs)

```text
solidcraft-cli 0.10.1
solidcraft release sha256 2dee82978900dab0f50d092446eef924f4fd6da99121aa6e0fa041c224ca700b
python3 3.12.15
cadquery-ocp==8.0.1.0.0
matplotlib==3.11.2
numpy==2.5.3
vtk==9.6.2
```

## How the judge got here

- An independent agent (REPRODUCE.md) modelled the part 12 times. Ten valid
  designs failed the first judge because SolidCraft exports some cylinders as
  B-spline faces. The features gate now fits those (`b5d7771` test, `fe4f92d` fix).
- Two rounds of independent code review (GPT-6.1 Sol) found false passes. Each
  is now a mutant or unit test that fails on the old judge:
  - A bolt pattern turned 10° as a whole.
  - Webs of 0.5 mm and 0.1 mm blocking the bolt holes.
  - A part that moves only when `thickness` changes.
  - A `sketch.text` that reads a font file outside the work dir.
  - A bore that bulges between sampled angles.
  - Two STL shells that touch at one vertex.
  - Deeply nested params.
  - A failed `sbx list` taken as cleanup.

  They also found false fails: a renamed `thickness` parameter, and a short-arc
  circle fit. On the old judge (`8e2ad25`), all four new CAD mutants passed and
  `design-renamed.json` failed at parametric. The fixes are in `bc5dca2` → `8826a1c`
  and `c654583` → `f65a450`.
- All 12 of the independent agent's designs were re-graded with this judge by
  `media/make_media.sh` (`media/data/agent_run.json`). Attempts 1–10 and 12 pass all
  8 gates. Attempt 11 fails at build, which is the agent's own unit error.

## Deviations

- **SolidCraft is younger than two weeks.** The standard asks for releases at
  least two weeks old, and SolidCraft v0.10.1 was released 2026-10-14. The project
  itself only started on 2026-10-07, so no release meets the rule. The tarball
  is pinned by sha256. All Python wheels are older, pinned and hash-checked.
- **Earlier runs at older commits were superseded.** Runs at `8e2ad25` passed
  (14/14 mutants). Two runs at `ed1bc4e` failed: their point-sampling wall
  probes made the self-test overrun `run.py`'s 1800 s step limit. The exact
  boolean wall checks that replaced them at `f65a450` made the self-test 13–14
  min. Logs are kept in the lane's receipts outside this repo.
- **The unit tests take 60 s in the sandbox**, against 5 s on a workstation.
  Most of that is the grid-integrated fake part in `tests/test_judge.py`.
