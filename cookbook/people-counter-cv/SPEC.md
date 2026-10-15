# people-counter-cv: classical CV people counting — SPEC

An agent works inside a disposable sandbox on a real computer-vision
engineering problem: given only a neutral sensor spec, write a classical-CV
people counter that watches a grayscale overhead walkway clip and reports
every pedestrian crossing of a tripwire, with times and directions. A judge
the agent cannot fool scores the output against the **analytic ground
truth** — the clip is scripted, so every true crossing time is known in
closed form from the trajectories — and against the judge's own
independently implemented reference counter. The judge never accepts "the
detector ran": counts, recall, precision, crossing-time error and
direction accuracy all have numeric pass rules.

## Goal

- Artifact: one Python file (`counter.py`) that reads `spec.json` (the
  neutral sensor spec below), reads the clip at `spec["video"]["file"]`,
  and writes `crossings.csv`: one row per tripwire crossing by a
  pedestrian, columns `t_cross_s,east,west` (exactly one of east/west is
  1 per row, rows sorted by time).
- Judge: `judge/grade.sh` generates the deterministic clip, runs the
  artifact from a copy, then scores the CSV with numeric, deterministic
  pass rules, plus cross-method agreement with the judge's own MOG2
  reference counter.
- Self-test: `judge/selftest.sh` proves the judge fails known-bad counters.

## Non-goals

- Deep learning detectors (YOLO & co.): the demo's point is that a
  classical pipeline — background subtraction, size filtering, centroid
  tracking, an edge-triggered tripwire — solves a well-specified counting
  task exactly. The judge only pins the toolchain (OpenCV + NumPy), not
  the method; any approach that meets the gates passes.
- Pedestrian re-identification or identity tracking across cameras: one
  camera, one line, counts and times only.
- Counting anything that is not a pedestrian: the spec's size range is
  the contract; trolleys wider than `body_w_px` must **not** be counted.
- Occlusion reasoning, crowds, night mode: the scene is deliberately
  sparse enough that the analytic oracle is unambiguous.

## The neutral sensor spec (`spec.json`, committed in `judge/`)

The agent sees `spec.json` and nothing else — it describes the sensor and
the population, and **no expected counts**:

| item | value |
|---|---|
| clip | `input/video.avi`, 640×360 grayscale, 12 fps, 60 s, MJPG |
| tripwire | vertical line at `x_fraction × width` = 320 px; east = +x |
| pedestrians | body 12–22 px wide, 18–24 px tall, head radius 2–3 px, speed 55–100 px/s |
| population | ~15–25 distinct pedestrians; some only linger or turn back |
| background | static textured floor (intensity 200 ± 8), per-frame sensor noise σ = 6, global illumination drift ±12 over 20 s |
| artifact output | `crossings.csv`, header `t_cross_s,east,west`, one-hot, sorted; "anything wider than the body_w_px range must not be counted" |

## The scene (judge-internal, agents never see this)

`judge/gen_scene.py` builds the clip deterministically from the spec and a
seed. 25 actors on 8 lanes:

| actor type | count | behaviour | truth events |
|---|---|---|---|
| ordinary crossers | 18 | walk straight through on 5 lanes | 1 each |
| double-crosser | 1 | crosses east, turns well past the line, crosses back west | 2 |
| decoys | 2 | walk toward the line, turn back before it | 0 |
| standers | 2 | walk in and stand 12 px from the line for the rest of the clip | 0 |
| trolleys | 2 | 54×16 px, wider than any pedestrian, one each way | 0 (must not be counted) |

For seed 0 (the default): 20 truth events — 11 east, 9 west — at
t = 6.10, 7.65, 9.80, 12.60, 14.05, 15.80 W, 18.96, 20.51, 22.02, 23.75,
25.21, 28.61, 31.30 W, 33.85 W, 35.30 W, 36.75 W, 38.20 W, 40.65 W,
44.57 W, 46.68 W (seconds; W = westbound). Every trajectory is piecewise
linear, so these times are analytic, not measured from pixels — that is
the demo's acceptance oracle. Scene invariants are verified at generation
time (lane exclusivity, ≥ 1.4 s between consecutive truth events, events
inside (0.5 s, duration − 0.5 s)) and raise if violated. Rendering is
byte-deterministic for a fixed (spec, seed); the good counter matches all
20 events on seeds 0 and 1 with worst deviation 0.016 s.

## The artifact contract

`counter.py` is a Python program that:

1. reads `spec.json` from the current directory;
2. decodes the clip with `cv2.VideoCapture`;
3. writes `crossings.csv` with exactly the spec's columns and row rules.

Rules the judge enforces structurally: the counter must be cv2-based and
decode the clip itself (not, say, parse a dumped frame directory), must
read the spec at runtime (not hardcode the sensor), and must not
hardcode truth times (≥ 3 numeric literals within 2 % of a truth event
time is rejected — see gate 1). The judge runs the artifact from a copy
in a fresh temp dir; sha256 checksums of `judge/` before and after must
match.

## Judge gates (numeric pass rules)

`judge/grade.sh <artifact> [--seed N] [--json out.json] [--skip-run]`
exits 0 only if gates 1–5 all pass. `--seed` (default: the spec's) is
recorded in the verdict. `--skip-run` re-scores a `crossings.csv` already
present next to the artifact (loop bookkeeping only; selftest never uses
it).

1. **structure** — `counter.py` is at most 96 KiB, byte-compiles, uses
   the `cv2` package and `VideoCapture`, reads the spec at runtime, and
   contains no hardcode-scanned truth time (any ≥ 3 float literals within
   2 % of truth event times).
2. **run** — the artifact runs in the judge venv and exits 0 within
   300 s, writing `crossings.csv`.
3. **csv-shape** — header exactly `t_cross_s,east,west`; every row has 3
   fields, times parse as finite floats inside [0, duration], east/west
   are one-hot 0/1, rows sorted by time, at least one row. Malformed
   input raises (it is never silently skipped).
4. **oracle** — against the analytic truth, pairing each artifact event
   to a same-direction truth event within 0.5 s (greedy nearest; truth
   events are ≥ 1.4 s apart so pairing is unambiguous):
   - per-direction count error ≤ 1;
   - recall ≥ 0.98 and precision ≥ 0.98 (with 20 truth events: no
     misses and no phantoms — a counter must not double-count);
   - crossing-time MAE ≤ 0.15 s and max deviation ≤ 0.30 s;
   - direction accuracy 100 % (of artifact events with a same-time
     truth counterpart, every direction must agree).
5. **agreement** — the artifact's CSV is compared with the judge's own
   reference counter (`judge/ref_count.py`: MOG2 adaptive background
   instead of a static reference frame, run on the same clip): per
   direction count difference ≤ 1, every paired event within 0.35 s, at
   most 1 unpaired event per side. Two independent methods must give one
   answer.

The tolerances are loose enough that an honest classical pipeline passes
with margin (measured: good counter time MAE 0.007 s, max 0.015 s, zero
count error on every seed tried), tight enough that every scripted mutant
fails at least one gate.

## Acceptance oracle

Correctness is decided by the scripted trajectories (crossing times known
analytically), cross-checked by an independently implemented MOG2 counter.
An artifact that merely "runs" or that counts presence instead of
crossings fails.

## Known-bad examples (self-test)

`judge/mutants.py` derives 9 known-bad counters from the known-good one by
scripted single edits:

| mutant | edit | gate that kills it |
|---|---|---|
| line_shifted | tripwire 30 px right of the spec's | oracle (times shift > 0.30 s) |
| width_filter_off | width cap 30 → 60 px | oracle (counts both trolleys: precision, counts) |
| direction_flip | east/west swapped | oracle (direction accuracy 0 %) |
| threshold_high | foreground threshold 25 → 130 | oracle (loses pedestrians: recall) |
| presence_counting | proximity to the line instead of a crossing | oracle (standers + repeated fires: precision) |
| missing_clip | opens `video.avi.missing` | run (non-zero exit) |
| hardcoded_truth | pastes the 20 truth times in | structure (hardcode scan) |
| fps_wrong | fps × 1.5 | oracle (all times −33 %) |
| reverse_order | rows written unsorted | csv-shape |

`judge/selftest.sh` grades the known-good (must pass) and every mutant
(each must fail ≥ 1 gate), prints the kill rate, and checks determinism
(two grades of the good artifact produce byte-identical verdicts except
the `timing` key). It exits non-zero unless the kill rate is ≥ 90 %.

## Determinism

Scene generation, rendering, the good counter and the reference counter
are all deterministic for a fixed (spec, seed). Two grades of the same
artifact give byte-identical verdict JSON except `timing` — enforced by
`selftest.sh`.

## Toolchain (pinned, sha256-checked)

`judge/setup.sh` installs into `$HOME/.venvs/people-counter-cv/` exactly:
opencv-python-headless 4.13.0.92 and numpy 2.5.3, every wheel pinned with
sha256 through pip's `--require-hashes` mode (`judge/requirements.lock`,
regenerable via `judge/genlock.py` from the PyPI JSON API). Wheels cover
CPython 3.10–3.13 on x86-64 Linux; every pinned release predates
2026-09-30 (nothing published in the two weeks before this demo was
built; numpy pinned to 2.5.3 because 2.5.4 is 2026-10-10).
`judge/VERSIONS.txt` records what setup actually installed.
