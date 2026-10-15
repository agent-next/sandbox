# Known-bad examples

Every mutant below is `examples/good` with **one** property broken, written by
`judge/mutants.py` (they are generated, not committed, so they stay in step
with the good artifact). `judge/selftest.sh` requires each to be killed by the
gate it is aimed at — a gate firing for the wrong reason is reported as
`WRONG GATE` and fails the self-test — and the kill rate to be at least 90 %.

| mutant | broken property | gate that must kill it |
|---|---|---|
| `wav_steady_tone` | a plain 220 Hz sine: no glide, no octave span | `shepard_property` |
| `wav_plain_sweep` | a 2.5-octave log sweep: rises, never returns to its pitch class | `shepard_property` |
| `wav_too_short` | the good tone truncated to 12 s | `wav_format` |
| `wav_wrong_rate` | the good tone resampled to 16 kHz | `wav_format` |
| `gif_static_one_frame` | **negative control**: one static frame, no motion | `ball_bounces` |
| `gif_too_few_frames` | 24 frames, below the 48-frame minimum | `gif_animation` |
| `gif_six_colours` | a sixth colour painted into one frame | `gif_animation` |
| `gif_flat_ball` | the ball slides on the floor, never bounces | `ball_bounces` |
| `gif_finite_loop` | the animation plays once, does not loop | `gif_animation` |
| `qr_wrong_string` | **negative control**: a scannable QR of `VIRAL-MICROGEN-43` | `qr_scans` |
| `qr_corrupt` | the QR data area painted over: neither decoder reads it | `qr_scans` |
| `palette_invented` | a swatch colour that appears nowhere in the GIF | `palette_match` |
| `palette_missing` | two swatches share a colour; a GIF colour is missing | `palette_match` |
| `palette_four_swatches` | one swatch painted out: four, not five | `palette_match` |
| `missing_file` | `palette.png` deleted: validation must fail before any gate | validation |

Regenerate and grade them:

```bash
python3 judge/mutants.py examples/good /tmp/mutants --seed 42
bash judge/selftest.sh        # kills 15/15 = 100 %
```
