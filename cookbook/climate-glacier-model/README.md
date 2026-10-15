# climate-glacier-model — a glacier retreat sweep a judge can grade

An agent has to *model* a glacier, not just plot a curve: run a 100-year
surface-mass-balance (SMB) sweep over a synthetic glacier under three
warming scenarios, and be graded by a judge it cannot fool. The judge
solves the same model in closed form and compares — an artifact whose
trajectory only *looks* plausible fails. It also re-runs the model with the
warming pinned to zero: a balanced glacier must not lose a single cubic
metre, so a hidden-state bug (a stale temperature, an anomaly applied
twice, a mask clamped wrongly) is caught even when the warming runs agree
with the analytic curve. A disposable sandbox is the right place for this:
the agent needs numpy and matplotlib, a throwaway filesystem to iterate in,
and nothing to keep afterwards.

The model is a single-length-variable SMB caricature in the spirit of the
OGGM constant-gradient flowline setup (Recinos, Maussion, Rothenberg &
Bush, *Geosci. Model Dev.* 12, 909–931, 2019,
doi:10.5194/gmd-12-909-2019). It is not OGGM and claims no OGGM numbers —
it is chosen because its yearly recurrence has an elementary closed-form
solution, which is what makes an exact oracle possible.

## Ask your agent

> Set up a sandbox and solve the demo in `cookbook/climate-glacier-model/`
> of https://github.com/agent-next/sandbox (clone it first). Run
> `bash cookbook/climate-glacier-model/judge/setup.sh`, read
> `cookbook/climate-glacier-model/SPEC.md`, then write the artifact
> yourself: `model.py`, a 100-year SMB sweep over the synthetic glacier in
> the spec, under three warming scenarios, writing `volumes.csv`,
> `crossings.json`, `retreat.png` and `run.json` into `--out`, and
> accepting `--seed N` and `--zero-melt`. Iterate with
> `bash cookbook/climate-glacier-model/judge/grade.sh <your-artifact-dir> --json v.json`
> until it exits 0, then paste the final verdict JSON and the crossing
> years. Do not edit anything under `judge/`; if you believe the judge is
> wrong, say so instead of working around it. Kill the sandbox when you
> are done.

The known-good example in `examples/good/` is one working answer; a
different structure that meets the spec is fine.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/climate-glacier-model/run.py     # --ref main --keep supported
```

Creates a sandbox, clones the repo, installs the pinned tools, runs the
judge self-test, grades `examples/good/`, prints the verdict JSON and a
one-line summary, then kills the sandbox and confirms it is gone. Stdlib
only; exits non-zero on any failure, naming the sandbox id if cleanup
cannot be confirmed.

## See the result without running anything

`media/` holds the figures and a short video, all regenerated from the
judge's own outputs by `bash media/make_media.sh` (never hand-edited):

- `media/result.png` — the three measured volume curves against the analytic
  oracle, the 50 %-crossing rule line, and the shape gate's ±2 % pass band
  with the measured deviation inside it.
- `media/loop.png` — the agent loop (gates failing per iteration of a real
  fix sequence, ending in PASS) and the self-test kill matrix (13/13).
- `media/demo.mp4` — 23 s, 1920×1080: the sweep animating year by year.
- `media/MANIFEST.json` — what each file shows, its command, source data and
  sha256.

## Measured wall time (Debian sandbox, 2 vCPU / 4 GB)

| step | wall time |
|---|---|
| `sbx create` | ~3–4 s |
| `git clone --depth 1` | ~5 s |
| `judge/setup.sh` (fresh venv) | 32–36 s (idempotent re-run: a few s) |
| `judge/grade.sh examples/good` | 10–13 s |
| `judge/selftest.sh` (good + 13 mutants + determinism) | 80–106 s |
| `run.py` end to end | ~2 m 10 s – 2 m 40 s |

Grading runs the model three times (nominal, repeat, zero-melt); each run
is ~3 s. `run.py` prints a per-step timing line. Times vary with machine
load; the graded numbers do not (see `RECEIPT.md`).

## Limits, plainly

- The model is a caricature: no ice flow, no calving, no real geometry, no
  real climate data. The scenario anomalies are prescribed numbers, not
  projections; see the SPEC non-goals.
- The judge compares against the closed form of *this* model, not against
  OGGM or observations. It says nothing about real glaciers.
- `retreat.png` is checked by its PNG header (width, dpi, size) and by the
  scenario names in `run.json`; the judge does not read the pixels and does
  not OCR the plot. It checks that a real, labelled, large figure exists —
  not that it is beautiful.
- The judge is stdlib-only on purpose, so a numpy version difference can
  never move a verdict. It does not import the artifact; it runs it as a
  subprocess with `python3 -I`.
- `judge/setup.sh` installs numpy 2.2.6 and matplotlib 3.10.6 (sha256-pinned
  wheels) into a venv under `$HOME`. It needs network once; grading needs
  none. Non-x86_64 or non-glibc-2.36 hosts need a different wheel pin.
