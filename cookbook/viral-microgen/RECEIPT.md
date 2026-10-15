# RECEIPT — two fresh-sandbox runs of the one-command run

Both runs below were started from a clean shell outside any sandbox, each with
a brand-new sandbox created by `run.py` itself (nothing pre-installed: the
sandbox image provides only git, curl, python3 and apt). Nothing the runs
touched survived: `run.py` killed each sandbox and confirmed with `sbx list`
that the id was gone (last line of each run).

Command (identical for both runs, from the repo root):

```bash
python3 cookbook/viral-microgen/run.py --ref sbx/demo-viral-microgen-f4
```

`sbx` CLI 0.0.1
(`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`),
`SBX_API_KEY` in the environment, seed 42 (the default).

## Step exit codes and wall times

| step (as timed by `run.py`) | run 1 exit | run 1 time | run 2 exit | run 2 time |
|---|---|---|---|---|
| `sbx create --timeout-min 30` | 0 | 4.0 s | 0 | 3.7 s |
| `git clone --depth 1 -b sbx/demo-viral-microgen-f4` | 0 | 11.5 s | 0 | 8.7 s |
| `judge/setup.sh` | 0 | 83.5 s | 0 | 88.4 s |
| `judge/selftest.sh` | 0 | 111.8 s | 0 | 109.6 s |
| `judge/grade.sh examples/good --seed 42` | 0 | 9.8 s | 0 | 11.3 s |
| `sbx kill` + confirmed gone via `sbx list` | 0 | (in exit path) | 0 | (in exit path) |
| **whole run, shell wall clock** | **0** | **231 s** | **0** | **230 s** |

Run 1 sandbox `01a1400a-9c26-7da3-bcae-b3e8fd63f356`, run 2 sandbox
`01a14010-7d8e-7871-87cc-c1b1fb6f8b3f`; both killed and confirmed gone
(`run: killed and confirmed gone: <id>` in each log).

## Self-test (both runs identical)

```
selftest: known-good PASSED all gates
selftest: determinism OK (two grades byte-identical except timing)
selftest: expected-gate check 15/15
selftest: killed    gif_finite_loop (gate: gif_animation)
selftest: killed    gif_flat_ball (gate: ball_bounces)
selftest: killed    gif_six_colours (gate: gif_animation)
selftest: killed    gif_static_one_frame (gate: gif_animation)
selftest: killed    gif_too_few_frames (gate: gif_animation)
selftest: killed    missing_file (gate: validation)
selftest: killed    palette_four_swatches (gate: palette_match)
selftest: killed    palette_invented (gate: palette_match)
selftest: killed    palette_missing (gate: palette_match)
selftest: killed    qr_corrupt (gate: qr_scans)
selftest: killed    qr_wrong_string (gate: qr_scans)
selftest: killed    wav_plain_sweep (gate: shepard_property)
selftest: killed    wav_steady_tone (gate: shepard_property)
selftest: killed    wav_too_short (gate: wav_format)
selftest: killed    wav_wrong_rate (gate: wav_format)
selftest: kill rate 15/15 = 100%
selftest: OK
```

`gif_static_one_frame` is killed by `gif_animation` first (1 frame < 48);
`ball_bounces`, the gate it is aimed at, also fails it — the expected-gate
check grades against the full `failed_gates` list, and it passed 15/15.

## Verdict: key numbers, run 1 vs run 2 (identical)

`passed=true`, `failed_gates=[]`, `qr_expected=VIRAL-MICROGEN-42`, seed 42.

| gate | number | run 1 | run 2 |
|---|---|---|---|
| `wav_format` | duration | 22.0 s | 22.0 s |
| `shepard_property` | span | 3.9998 oct | 3.9998 oct |
| `shepard_property` | slope | 0.181809 oct/s | 0.181809 oct/s |
| `shepard_property` | fit R² | 0.999998 | 0.999998 |
| `shepard_property` | pitch-class return | 3.9998 oct | 3.9998 oct |
| `shepard_property` | mid/tail band energy | 14.732 dB | 14.732 dB |
| `gif_animation` | frames / colours / loop | 60 / 5 / 0 | 60 / 5 / 0 |
| `ball_bounces` | bounces / rise / travel | 7 / 213 px / 172.0 px | 7 / 213 px / 172.0 px |
| `ball_bounces` | floor row | 269 | 269 |
| `qr_scans` | zbar 0.23.92 | `VIRAL-MICROGEN-42` | `VIRAL-MICROGEN-42` |
| `qr_scans` | zxing-cpp 2.3.0 | `VIRAL-MICROGEN-42` | `VIRAL-MICROGEN-42` |
| `palette_match` | swatches vs GIF colour set | exact match | exact match |

The graded artifact is the committed `examples/good` — the verdict's
`artifact_sha256` matches the files in git in both runs:

```
ball.gif     8d5bcf72dfe052e019c30b93ee815ddc988f8bd9ce2e60f5a9dade69e0f18bb6
palette.png  701b343cb3dddc3dd5b6103f5b5a92d4d1558f0db18687ce8e17758e15dd58fd
qr.png       cb0551dcc964d4342e17c193c6cc07189204d8b9c8473995c88395502c880160
shepard.wav  6cb95eda5ee35ed2de88756144f33592161970d963421b3cce9edd7040a6e03c
```

## Tool versions (as installed by `judge/setup.sh`, echoed by run 2)

```
zbarimg 0.23.92
zbar-tools debian package: 0.23.92-7+deb12u1
zxing-cpp 2.3.0
numpy 2.1.3
Pillow 11.0.0
python3 3.12.15
venv /home/user/.viral-microgen-venv
```

Both `.deb` downloads and the zxing-cpp wheel were sha256-checked
(`sha256sum -c` printed `OK` for all three; any mismatch makes `setup.sh`
exit non-zero). Sandbox image `agent-full-tini-20261011`, 4 vCPU, Python
3.12.15, Linux x86_64.

## Deviations

- The two runs cloned the branch at two commits: run 1 at `7b358af`, run 2 at
  the branch tip after two documentation/`run.py` commits (`b3a8e64`,
  `54d908f`: SPEC wording, `examples/bad/README.md`, `run.py` echoing
  the setup output). The `judge/` tree is byte-identical between those
  commits, and the verdicts came out byte-identical except `timing`.
- Run 1 did not echo `VERSIONS.txt` (the `run.py` echo change landed between
  the runs); the versions above are run 2's. Run 1's `setup.sh` enforced the
  same pins — it exits non-zero on any version mismatch — and both runs
  printed `setup: done`.
- `judge/setup.sh` took ~85 s here (cold `apt-get update` + venv build in a
  fresh sandbox); an earlier builder run with a warm apt cache saw 21.6 s.
  Same pinned versions either way.
- The last line of each run is the sandbox-kill confirmation, so the exit
  path (kill + `sbx list` check) is included in the whole-run wall clock, not
  timed as its own step.

Raw logs: both runs' full output was captured by the builder; the verdict
JSON above is pasted from run 1, and every number was diffed against run 2
(no differences outside `timing`).
