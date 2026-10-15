# REPRODUCE — physx-drop-test

Independent reproduction, recorded 2026-10-15. The reproducing agent is a
different model family from the demo's builder (Claude, built by Anthropic;
the builder was GLM, built by Z.ai) and had **no context beyond README.md**:
it received a copy of `README.md`, `SPEC.md`, `judge/`, `examples/` and
`run.py` in a scratch directory, no RECEIPT, and followed only the README's
"In-sandbox / no API key" section. Its raw notes (verbatim transcripts,
verdict JSON, deviations) are summarized below.

## What it ran

- Linux x86_64, 2 vCPU, 3.8 GiB RAM, AVX, Python 3.12.15 — same class of
  box as the RECEIPT runs.
- `export PHYSX_DROP_TEST_VENV=$HOME/.venvs/physx-reproduce` (a fresh venv;
  the README default path was in use by the builder's own run). The wheels
  were sha256-verified by `pip --require-hashes` as usual; pip's HTTP wheel
  cache on the machine was warm, so setup downloaded nothing.
- From the demo directory, exactly the README's three commands:

| step | exit | wall |
|---|---|---|
| `bash judge/setup.sh` | 0 | 27.410 s (warm pip cache) |
| `bash judge/selftest.sh` | 0 | 53.462 s |
| `bash judge/grade.sh examples/good/scene.usda --json /tmp/repro/verdict.json` | 0 | 4.594 s (`timing.wall_seconds` 4.488) |

## Verdict and kill rate (verbatim)

```
[selftest] 3/4 kill rate (killed by a gate / total): 10/10 = 100%
[selftest] PASS: judge kills 10/10 mutants by a gate, good passes, deterministic
```

```
"all_gates_passed": true
```

## Key numbers vs RECEIPT (SPEC tolerance in brackets)

| quantity | reproducer | RECEIPT run A | tolerance | match |
|---|---|---|---|---|
| G2 fitted gravity, both bodies (`g_fit`) | 9.81 | 9.81 | ±1 % of 9.81 | ✓ |
| G2 max residual, both bodies | 0.0 m | 0.0 m | ≤ 1 % + 0.5 mm | ✓ |
| G3 box contact `t_sim` / Δ | 0.375 s / 0.65 fr | 0.375 s / 0.65 fr | Δ ≤ 1 frame | ✓ |
| G3 ball contact `t_sim` / Δ | 0.47083 s / 0.65 fr | 0.47083 s / 0.65 fr | Δ ≤ 1 frame | ✓ |
| G4 resting height, both | 0.1 m, error 0.0 mm | 0.1 m, error 0.0 mm | ≤ 1 mm | ✓ |
| G5 ball apex `apex_sim_m` / `rel_error` | 0.3733 / 0.0043 | 0.3733 / 0.0043 | ≤ 10 % | ✓ |
| G6 box E₀ / E_final / max step gain | 31.3853 / 3.924 / 0.02142 J | identical | gain ≤ 0.5 % E₀ | ✓ |
| G6 ball E₀ / E_final / max step gain | 11.7703 / 0.981 / 0.00019 J | identical | gain ≤ 0.5 % E₀ | ✓ |
| G7 contract violations | 0 | 0 | must be 0 | ✓ |
| selftest kill rate | 10/10 = 100 % | 10/10 = 100 % | ≥ 90 % | ✓ |

Every physics number is identical to the RECEIPT (the judge is
deterministic); only wall times differ (warm caches on the reproducer's
box: its setup took 27 s against ~2 min cold; selftest 53 s; grade 4.6 s).
The verdict JSON's sha256 in the reproducer's run matched the structure
byte-for-byte apart from `timing.wall_seconds`, exactly as the
determinism rule requires.

> Editor's note (builder, 2026-10-15): this reproduction ran against the
> demo as it was when the reproducer received it — 10 mutants. The 11th
> (`planted-verdict`, forged judge outputs beside the scene) was added
> afterwards; every physics gate number above is unaffected by it
> (it is killed by G7 alone). The current selftest output, 11/11 = 100 %,
> is in [RECEIPT.md](RECEIPT.md).

## Reproducer README findings (and what changed)

1. `PHYSX_DROP_TEST_VENV` was honored by `setup.sh` but undocumented — the
   README now documents it next to the in-sandbox commands.
2. The wall-time table overstated the reproducer's runs (warm caches) —
   the README table now carries a warm-cache row and a note.
3. The `--json` file carries `seed` and `timing` keys that stdout omits —
   noted in the README's determinism paragraph.

Everything else — the three copy-pasteable commands, no sudo, the flags
table, the AVX failure mode — was reported unambiguous and correct.

## Deviations

- The reproduction ran in the same disposable sandbox as the build (a
  second *machine* was not available from here), but in a fresh venv and
  from a cold copy of the demo directory, following only the README. The
  standard's cross-machine check is the lead's end-to-end `run.py`
  execution in a real agent-next sandbox (see RECEIPT.md).
- pip's HTTP wheel cache was warm on the machine (wheels still
  sha256-verified by `--require-hashes`); a cold pip cache reproduces the
  RECEIPT's ~2 min setup instead.
