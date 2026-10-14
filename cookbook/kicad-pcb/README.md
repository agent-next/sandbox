# kicad-pcb — judge a small PCB design in a disposable sandbox

The agent designs a real 2-layer board — a 555 astable LED blinker —
in KiCad s-expression format, and a judge it cannot fool decides whether
the result is right. KiCad runs headless (`kicad-cli` 9.0.9, SHA256-pinned
official AppImage), and every gate is checked by an independent
stdlib-Python oracle (`judge/oracle.py`) that parses the reports and the
exported Gerber/Excellon files itself — "the tool ran" is never the pass
criterion.

A disposable sandbox helps because KiCad is a heavy GUI toolchain: the
judge installs a verified 200 MB AppImage, runs ERC/DRC/gerber/drill
exports, and throws it all away. Nothing touches the host or the repo.

## Ask your agent

> In a fresh sandbox, clone this repo and go to `cookbook/kicad-pcb/`.
> Run `bash judge/setup.sh`, then look at `SPEC.md`. Design (or fix) a
> small 2-layer KiCad project — a 555 astable LED blinker, board
> <= 50 x 50 mm — as `examples/good/555-blinker/` (`.kicad_pro`,
> `.kicad_sch`, `.kicad_pcb`). Iterate with
> `bash judge/grade.sh examples/good/555-blinker --json /tmp/v.json`
> until `overall_pass` is `true`. The judge is in `judge/`; do not modify
> it. Finish with `bash judge/selftest.sh`.

## One-command run

```bash
python3 run.py            # clones --ref (default main) in a sandbox
python3 run.py --ref my-branch --keep
```

`run.py` creates an `sbx` sandbox, clones the repo, runs `setup.sh`,
`selftest.sh`, and `grade.sh`, prints the verdict JSON and per-step wall
times, then always kills the sandbox and verifies it is gone.

## What is checked (gates)

| gate | check | pass rule |
|---|---|---|
| G1 | `kicad-cli sch erc` JSON | 0 error-severity violations |
| G2 | `kicad-cli pcb drc` JSON | 0 violations, 0 unconnected items |
| G3 | schematic vs PCB netlists | exact net-set equality, 0 unrouted |
| G4 | Edge.Cuts parsed from `.kicad_pcb` | outline is a closed loop |
| G5 | gerber export (7 layers) | each layer has >=1 aperture + >=1 op |
| G6 | Excellon drill export | >=1 tool, >=1 drilled hole |

## Measured wall time (this sandbox, 2 vCPU / 4 GB)

| step | time |
|---|---|
| `judge/setup.sh` (cold, downloads 208 MB) | ~17 s |
| `judge/selftest.sh` (good x2 + 7 mutants) | ~23 s |
| `judge/grade.sh` on the good example | ~3 s |

See `RECEIPT.md` for pasted output and `REPRODUCE.md` for independent
reproduction.

## Layout

```
SPEC.md                   contract: gates, oracle, tolerances
judge/setup.sh            pinned KiCad 9.0.9 install (sha256-checked)
judge/grade.sh            runs kicad-cli + oracle, emits verdict JSON
judge/oracle.py           stdlib-only independent checker
judge/selftest.sh         determinism + mutant kill-rate (>= 90%)
judge/mutants.py          7 single-edit mutants of the good board
examples/good/555-blinker/  known-good project (~83 KB, self-contained)
tools/                    generators that produced the example
media/                    result.png, loop.png, demo.mp4, make_media.sh
run.py                    one-command sandbox run
```

## Limits

- ERC/DRC check the *files'* rules; the schematic carries embedded
  symbols, so symbol-library warnings (`lib_symbol_issues`,
  `endpoint_off_grid`) are expected and non-fatal — the gate counts
  errors only.
- The judge does not simulate the circuit (no timing/frequency check).
- Gerber/drill parsing is deliberately shallow: it verifies real
  geometry exists on every exported layer, not fabrication readiness.
- `run.py` requires the `sbx` CLI and `SBX_API_KEY`/`E2B_API_KEY`.
