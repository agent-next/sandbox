# Independent reproduction

- Model family and date: Claude (Anthropic), 2026-10-15. The demo was
  built by a GPT-6.1 Sol agent (OpenAI), so this is a different family.
- Commit: `5ef90b8cf01af22dabaafe81130adfcca228cc0f`.

## 1. The one-command run, twice

`python3 cookbook/video-edit-mlt/run.py --ref sbx/demo-video-edit-mlt`, two fresh
sandboxes started 5 s apart:

| step | RUN-A | RUN-B |
|---|---|---|
| `sbx create --timeout-min 120` | exit 0, 1.9 s | exit 0, 2.6 s |
| `git clone` | exit 0, 13.1 s | exit 0, 12.9 s |
| `judge/setup.sh` from nothing | exit 0, 83.2 s | exit 0, 77.7 s |
| `judge/selftest.sh` (27 unit tests, 11 mutants, determinism, integrity) | exit 0, 196.1 s | exit 0, 203.0 s |
| kill rate | 11/11, each at its intended gate | 11/11, same gates |
| final grade | exit 0, 25.7 s | exit 0, 23.8 s |
| cleanup | `killed and confirmed gone` | `killed and confirmed gone` |
| total | 323.0 s, exit 0 | 322.5 s, exit 0 |

Both runs printed the same summary line:

```text
run: SUMMARY passed=True dissolve=0.041486 ducking=11.948775 edl=0 loudness={'integrated_lufs': -16.0, 'true_peak_dbtp': -8.5}
```

All of these match RECEIPT.md exactly. The discrete checks match, and so do
the continuous numbers: −16.0 LUFS, −8.5 dBTP, a duck of 11.948775 dB, a
dissolve error of 0.041486 and a logo minimum of 0.999981 on frames.

## 2. Solving the task from the README alone

In a third fresh sandbox the reproducer ran `judge/setup.sh` and wrote its
own `edit.mlt` from SPEC.md, spec.json and the README prompt, without
opening `examples/good/edit.mlt`. It differs from the example in its
ducking curve (−14 dB steps) and in using a master volume filter for
loudness. It took four grades:

| attempt | verdict | what the judge said | fix |
|---|---|---|---|
| 1 | FAIL at security | `non-allowlisted mlt_service`: producers had no `mlt_service` | named `avformat` / `qimage` |
| 2 | FAIL at security | `missing output tractor`: no `producer=` on the root `<mlt>` | `<mlt producer="main">` |
| 3 | FAIL at loudness | −10.2 LUFS against −16 ±1; every other gate passed | master `level` −6.2 dB |
| 4 | **PASS** | all gates: EDL 0 mismatches, dissolve 0.041486, logo on 0.999981 / off ≤ 0.079241, ducking 13.97 dB, −16.4 LUFS, −8.9 dBTP | — |

Each grade took about 25 s.

README-only problems found: the prompt did not say that every producer
needs an `mlt_service` and that the root `<mlt>` must name the output
tractor. Both errors were reported clearly by the security gate, so the
reproduction was still possible. The README prompt now says both. It
also pointed at the development branch; it now clones `main`.

## Deviations

- Section 1 used `--ref sbx/demo-video-edit-mlt` because the demo was not
  yet on `main`.
- The third sandbox was killed by hand after the passing grade, and a
  successful `sbx list` no longer showed its id.
