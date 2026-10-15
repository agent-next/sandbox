# STORYBOARD — `cookbook/ci-test-matrix/media/demo.mp4`

Planned before the video was cut; `make_media.sh` builds every shot below
from the judge output files in `media/data/` and fails if one is missing.
Every number and every line of terminal text on screen is real judge
output (`judge/grade.sh --seed 42`, `judge/selftest.sh`) from the run
recorded in `media/data/`; the fixing sequence is a **replay** of real
grade verdicts, labelled as such on screen.

Source data (all written by the judge in this sandbox):

| file | written by |
|---|---|
| `data/verdict-good.json` | `judge/grade.sh examples/good --seed 42 --json` |
| `data/verdict-<mutant>.json` (9) | `judge/grade.sh media/scratch/mutants/<mutant> --seed 42 --json` |
| `data/selftest.log` | `judge/selftest.sh` (real transcript) |
| `data/grade-good.txt` | `judge/grade.sh examples/good` stdout (the verdict JSON) |
| `data/loop.json` | the replay plan (order + stage labels only; numbers come from the verdict JSONs) |

## Slot table

| # | time | slot | fills the frame | source data / command | caption (burned in) |
|---|---|---|---|---|---|
| 1 | 0.0–2.5 s | **hook** — the finished result | the five-cell matrix table with the real interpreter stamps, the 3.9 cell in red (`FAIL: match SyntaxError`), a PASS stamp and a highlight band sweeping the rows | `data/verdict-good.json` → `metrics.cells`, `metrics.aggregated_table.on` | 5 CPython cells, 7 tests each — the judge fails exactly the 3.9 cell |
| 2 | 2.5–6.0 s | **input** — what the agent writes | `examples/good/matrix.yaml` scrolling (real artifact file) beside the four keys the judge parses | `examples/good/matrix.yaml` | the whole artifact: one matrix.yaml + one run_matrix.py |
| 3 | 6.0–10.0 s | **input -> output** — the matrix builds | the five cells appear one per beat with their measured interpreter stamp and pass/fail fill, a progress bar runs under the table | `data/verdict-good.json` → `metrics.cells` | each cell: its own uv interpreter — 3.9.25 … 3.13.15 |
| 4 | 10.0–16.5 s | **escalate** — the judge streaming | terminal panel, the real `selftest.log` transcript streaming line groups (known-good PASS, nine `killed by gate:` lines), a kill counter climbing 0 → 9 | `data/selftest.log` (real `judge/selftest.sh` output) | judge self-test, real output — 8× speed |
| 5 | 16.5–21.0 s | **escalate** — the verdict streaming | terminal panel, `grade-good.txt` (the verdict JSON the judge prints) streaming, gates flipping PASS down the JSON | `data/grade-good.txt` | grade.sh prints one verdict — 8× speed |
| 6 | 21.0–27.0 s | **escalate** — the replayed fix loop | three grade runs as iterations: gate badges count 1/8 → 7/8 → 8/8 with the failing gates named, labelled a replay | `data/loop.json` + the three real verdict JSONs | replay of real grade verdicts (not a live agent trace) |
| 7 | 27.0–33.0 s | **escalate** — the kill matrix | rows of the 9-mutant × 8-gate kill matrix fill one mutant per beat; red cells carry the judge's own measured detail; kill-rate bar fills to 9/9 | the 9 `data/verdict-<mutant>.json` | every single-edit mutant killed — 9/9, floor 90 % |
| 8 | 33.0–36.2 s | **proof** — PASS over moving bars | the mask bars (`on` → fail at 3.9; `off` → all pass) fill from the JSON while the PASS verdict, exit codes and interpreter stamps ride on top | `data/verdict-good.json` → `metrics.mask_on`, `mask_off`, `exit_codes`, `cells` | verdict PASS — mask matches the CPython-3.10 oracle |
| 9 | 36.2–39.2 s | **end card** (static) | one-line launch + the ask-your-agent prompt on a still frame | — | run it: `python3 cookbook/ci-test-matrix/run.py` |

## Craft checks the cut must satisfy

- Every shot before the end card moves: line groups pop and the terminal
  scrolls in shots 4–5, cells and matrix rows fill in 1, 3, 6–8, progress
  and mask bars grow every frame in 3 and 8.
- >= 0.8 scene cuts per 10 s: 8 cuts in 39.2 s = 2.0 / 10 s.
- Captions >= 4 % of frame height (46 px cap height on 1080 px); terminal
  text zoomed to the active region of the log.
- The end card is the only static frame and holds >= 2.5 s (the gate
  measures the last 2 s).
- The judge's PASS verdict and the kill rate appear large enough to read on
  a phone (>= 60 px digits).
