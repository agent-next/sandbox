# Independent reproduction — viral-microgen

This is an independent reproduction of the demo per `cookbook/DEMO-STANDARD.md`,
run on 2026-10-15 by a different agent family (Claude) than the builder, following
`README.md` only (its "One-command run" section). `RECEIPT.md`, `judge/`
internals and the demo's git history were not read before or during the run.

## Command run

```bash
export PATH="$HOME/.local/bin:$PATH" && cd /home/user/w && \
  python3 cookbook/viral-microgen/run.py --ref sbx/demo-viral-microgen-f4
```

Full stdout/stderr captured to `/tmp/vm-reproduce/repro.log`. **Exit code: 0.**
All six gates PASS; the run reported `run: killed and confirmed gone:
01a14018-38dc-74d0-a17e-112a632880ed`, and a post-run `sbx list` did not show
that id (independently confirmed gone). The whole-run shell wall clock, from the
capture file's creation-to-last-write span, was **200 s**.

## Measured key numbers

| metric | value |
|---|---|
| Shepard span | 3.9998 oct |
| Shepard slope | 0.181809 oct/s |
| Shepard R² | 0.999998 |
| Shepard return | 3.9998 oct |
| Shepard mid/tail | 14.732 dB |
| Ball bounces | 7 |
| Ball rise | 213 px |
| Ball travel | 172.0 px |
| Ball floor row | 269 |
| GIF frames | 60 |
| GIF colours | 5 |
| GIF loop | 0 |
| QR (zbar) | `VIRAL-MICROGEN-42` |
| QR (zxing) | `VIRAL-MICROGEN-42` |
| Self-test kill rate | 15/15 = 100% |

WAV format (from the verdict JSON): 22050 Hz, mono (1 channel), 16-bit
(sampwidth 2), 22.0 s, 485100 frames. Palette: 5 swatches, exact RGB set match
with the GIF.

## Per-step wall times (as reported by run.py)

| step | this run |
|---|---|
| `sbx create --timeout-min 30` | 6.0 s |
| `git clone` | 10.7 s |
| `judge/setup.sh` | 73.1 s |
| `judge/selftest.sh` (15 mutants) | 92.3 s |
| `judge/grade.sh examples/good` | 9.9 s |
| whole run, shell wall clock | 200 s |

## Tool versions echoed by judge/setup.sh

```
zbarimg 0.23.92
zbar-tools debian package: 0.23.92-7+deb12u1
zxing-cpp 2.3.0
numpy 2.1.3
Pillow 11.0.0
python3 3.12.15
venv /home/user/.viral-microgen-venv
```

## Comparison with README.md

Deterministic numbers vs the "The gates" table in README.md:

| number | README.md | this run | match |
|---|---|---|---|
| WAV 22050 Hz mono 16-bit, 22.0 s | yes | yes | yes |
| Shepard span | 3.9998 oct | 3.9998 oct | yes |
| Shepard R² | 0.999998 | 0.999998 | yes |
| Shepard return | 3.9998 oct | 3.9998 oct | yes |
| GIF frames | 60 | 60 | yes |
| GIF colours | 5 | 5 | yes |
| GIF loop | 0 | 0 | yes |
| Ball bounces | 7 | 7 | yes |
| Ball rise | 213 px | 213 px | yes |
| Ball travel | 172 px | 172.0 px | yes |
| QR zbar version | 0.23.92 | 0.23.92 | yes |
| QR zxing-cpp version | 2.3.0 | 2.3.0 | yes |
| QR string (both decoders) | `VIRAL-MICROGEN-42` | `VIRAL-MICROGEN-42` | yes |
| Palette | 5 swatches, exact match | 5 swatches, exact match | yes |
| Self-test | 15/15 killed, 100% | 15/15 killed, 100% | yes |
| Image / Python | `agent-full-tini-20261011`, Python 3.12.15 | same (per versions block) | yes |

Wall times vs the "Measured wall time" table (run-dependent, not required to
match):

| step | README run 1 | README run 2 | this run |
|---|---|---|---|
| `sbx create --timeout-min 30` | 4.0 s | 3.7 s | 6.0 s |
| `git clone --depth 1` | 11.5 s | 8.7 s | 10.7 s |
| `judge/setup.sh` | 83.5 s | 88.4 s | 73.1 s |
| `judge/selftest.sh` | 111.8 s | 109.6 s | 92.3 s |
| `judge/grade.sh examples/good` | 9.8 s | 11.3 s | 9.9 s |
| whole run | 231 s | 230 s | 200 s |

Every step sits within or close to the README's range; grade time (9.9 s) falls
between the two recorded runs. No step regressed beyond the recorded spread.

## Deviations

1. **`--ref` substitution (mandated):** README.md's one-command run says
   `--ref main`, but the demo is not yet merged; this reproduction ran with
   `--ref sbx/demo-viral-microgen-f4` as instructed by the reproduction task.
2. **Piping:** the command was wrapped in `tee /tmp/vm-reproduce/repro.log`
   with `echo EXIT=$?` appended to capture output and the exit code; this does
   not alter what run.py does.
3. **Whole-run wall clock:** measured as the capture file's creation-to-last-
   write span (~200 s) rather than a separate shell stopwatch, since the
   command was invoked through the tool harness.

MATCH
