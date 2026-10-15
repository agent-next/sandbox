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
| G1 | `kicad-cli sch erc` JSON | 0 errors, and every warning type is in the allow-list (SPEC.md) |
| G2 | `kicad-cli pcb drc` JSON | 0 violations, 0 unconnected items |
| G3 | schematic vs PCB netlists | exact net-set equality, 0 unrouted, 555 + LED placed, same part references |
| G4 | Edge.Cuts parsed from `.kicad_pcb` | outline is a closed loop, no open segment ends |
| G5 | gerber export (7 layers) | >=1 aperture + >=1 op per layer; Edge.Cuts extents match the board to 0.1 mm |
| G6 | Excellon drill export | every through-hole pad/via has a drill, a matching tool exists, hits cover all holes |

## Measured wall time (this sandbox, 2 vCPU / 4 GB)

Two cold runs on different days; network speed dominates `setup.sh`.

| step | time |
|---|---|
| `judge/setup.sh` (cold, downloads 208 MB) | 18-34 s |
| `judge/selftest.sh` (good x2 + 8 mutants) | 26-46 s |
| `judge/grade.sh` on the good example | 3-6 s |

## Rebuilding the media

`media/make_media.sh` needs `judge/setup.sh` run first (kicad-cli renders
the board), the judge outputs from `bash media/make_data.sh`, and `ffmpeg`
plus `ffprobe` on PATH. Python deps install hash-pinned into
`media/.venv`. Then `bash media/make_media.sh` rewrites `result.png`,
`loop.png`, `demo.mp4` and `MANIFEST.json`.

See `RECEIPT.md` for pasted output and `REPRODUCE.md` for independent
reproduction.

## Layout

```
SPEC.md                   contract: gates, oracle, tolerances
judge/setup.sh            pinned KiCad 9.0.9 install (sha256-checked)
judge/VERSIONS.txt        what setup.sh installed (tool --version output)
judge/requirements.txt    hash-pinned pip deps (media only; judge is stdlib)
judge/grade.sh            runs kicad-cli + oracle, emits verdict JSON
judge/oracle.py           stdlib-only independent checker
judge/selftest.sh         determinism + mutant kill-rate (>= 90%)
judge/mutants.py          8 single-edit mutants of the good board
examples/good/555-blinker/  known-good project (~83 KB, self-contained)
tools/                    generators that produced the example
media/                    result.png, loop.png, demo.mp4, make_media.sh
run.py                    one-command sandbox run
```

## Limits

- ERC/DRC check the *files'* rules. The good board reports 19 ERC
  warnings, all `lib_symbol_issues` — inherent to a self-contained
  artifact (symbols embedded, no library table) graded headless; the G1
  gate fails on every other warning type (see SPEC.md's allow-list).
- The judge does not simulate the circuit (no timing/frequency check).
- Gerber/drill parsing is deliberately shallow: it verifies real
  geometry exists on every exported layer, not fabrication readiness.
- `run.py` requires the `sbx` CLI and `SBX_API_KEY`/`E2B_API_KEY`.
