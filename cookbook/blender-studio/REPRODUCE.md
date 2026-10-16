VERDICT: REPRODUCED

# Independent reproduction, 2026-10-15

An independent agent from a different model family than the builder followed
README.md ("One-command run") and SPEC.md, collected its own numbers, and only
then compared them with RECEIPT.md. No demo files were modified.

## Environment and source

- Fresh local clone of the demo branch at commit
  `d6d49c8c12de5655e6a1ec8faf791075d58eda03`; the sandbox cloned public
  `main` at `0a58d7e7f73e67d5a29eded0276fbb4c8c5c423e` and received the
  source snapshot `ae8e9e7a46fa60fcbef87c503282e742b571757540207b5cd20528bb16688cff`.
- `sbx` CLI already installed, so the README's `pip install` step was skipped.
- `SBX_API_KEY` from the environment; template `blender`.

Later commits on the branch change only media capture and composition;
`judge/`, `run.py`, `examples/` and `SPEC.md` are unchanged since this commit.

## Command

```sh
cd cookbook/blender-studio
python3 run.py
```

## Real output (excerpts)

```text
clone: exit=0 wall=9.7s
snapshot: exit=0 wall=6.7s
Blender 5.2.2 LTS
Blender build d13f752e3b9c
setup PASS (pinned image tools; no downloads)
setup: exit=0 wall=17.9s
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
SELFTEST killed=10/10 kill_rate=100.0% exit=0 wall=142.365s
selftest: exit=0 wall=163.2s
grade: exit=0 wall=31.6s
PASS: five gates; seed=17; Blender 5.2.2 LTS; time-to-result=234.1s
cleanup confirmed: 01a13fab-785d-7342-b8a0-a7e44c75019e absent from sbx list
run: exit=0 wall=241.8s
```

## Comparison with RECEIPT.md

The final grade verdict, with `timing` removed, is byte-identical to both
receipt runs (A and B). That is stricter than the cross-sandbox tolerances in
SPEC.md ("Cross-sandbox comparison tolerances").

| metric | this run | receipt A / B | SPEC tolerance |
| --- | --- | --- | --- |
| G1 bbox_fraction | 0.171453 | 0.171453 | 0.00001 |
| G1 center | 0.465763, 0.514999 | same | 0.00001 |
| G2 mean_display_luminance | 0.481615 | 0.481615 | 0.002 |
| G2 clipped_fraction | 0.0 | 0.0 | 0.002 |
| G3 max_second_difference | 0.013453 | 0.013453 | 0.002 |
| G4 max_step_error_radians | 3.7e-07 | 3.7e-07 | 0.000001 |
| G4 endpoint_mean_abs_diff | 2e-06 | 2e-06 | 0.002 |
| G5 backdrop_direct_delta | 0.000296 | 0.000296 | 0.01 |
| G5 product_direct_delta | 0.020933 | 0.020933 | 0.002 |
| G5 rim / halo receivers | GlassOrb, GoldRing, Hero, Plinth / Cyclorama | same | must agree |
| mutants killed | 10/10 | 10/10 | 100% required |
| time-to-result | 234.1 s | 192.3 s / 233.2 s | < 300 s target |

## Deviations

1. `pip install` skipped because the CLI was already installed.
2. Two earlier attempts the same day were refused at create time by the
   service (`503: host disk nearly full: refusing new sandbox starts`), before
   any sandbox existed. A third attempt passed but its log was truncated and
   is not counted. This record is the fourth attempt, run once, full log kept.
