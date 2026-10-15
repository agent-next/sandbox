# Go1, from PPO to an independently judged walk

Written before the final cut. Every robot pose is episode zero of a saved
judge trajectory. Camera moves and lighting are render-only. There is no
fabricated agent conversation or terminal recording.

| Seconds | Real moving output | Caption and source |
|---|---|---|
| 0–2 | Full-frame trained Go1 walking, seed 101; gentle camera move | “4 GiB → Go1 learns to walk”, measured held-out mean speed and no falls. `data/trained.json`. |
| 2–8 | Final trained policy beside the input specification | Command 1.0 m/s, 4 GiB, held-out seeds. Actual PPO reward telemetry progressively revealed, labelled “81× overview”, from `examples/good/curve.json`. This is archived telemetry, not a screen recording. |
| 8–14 | Side-by-side trained and random-initialized robots, seed 202 | “1.67× speed”, per-seed 64-episode speed/fall numbers and pass limits. A fallen episode explicitly freezes. `data/{trained,untrained}-202.npz` and verdicts. |
| 14–20 | New angle, held-out seed 303, same genuine comparison | Same readouts for seed 303. `data/{trained,untrained}-303.npz`. |
| 20–27 | Still-moving trained Go1 behind a five-gate PASS HUD and all eleven rejected mutants | Real gate values from `data/trained.json`; actual killed mutants from `data/selftest.json`. |
| 27–30 | Static final simulator frame | `python3 cookbook/go1-walk/run.py`. |

`bash cookbook/go1-walk/media/make_media.sh` writes lossless 30 fps clips
under ignored `media/clips/`, concatenates them into the CRF 0 master,
and produces the CRF 18 H.264 web encode. `--render-only` uses the same
hash-verified cached states. No plotting library is used.
