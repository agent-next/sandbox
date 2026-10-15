# ci-test-matrix — a test matrix across Python versions, graded by a judge

An agent has to *build* a CI primitive, not just run a test suite: produce a
`matrix.yaml` plus a `run_matrix.py` that runs one pinned library's pytest
suite across five CPython versions (3.9, 3.10, 3.11, 3.12, 3.13) — one
disposable sandbox cell per version, uv-managed interpreters — collects a
JUnit XML file per cell, aggregates them into a pass/fail matrix table, and
detects the fixture's deliberately version-specific failure: a module using
`match` syntax, which is a `SyntaxError` on Python 3.9 and below. The judge is
not "it ran": the verdict is checked against an independent oracle (the
Python language specification — `match` becomes a keyword in 3.10), a
measured per-cell interpreter-identity stamp, and an exit-code gate, so a
runner that silently skips a cell, reuses one interpreter, or masks a failure
cannot pass. A disposable sandbox is the right place for this: the agent
needs five real interpreters, a throwaway filesystem per cell to iterate in,
and the graded artifact is two small files it hands back.

## Results

The key numbers from the judge verdict (`examples/good/`, toggle on) are
below. The `media/` figures (`result.png`, `loop.png`) and `demo.mp4` ship
in a follow-up PR; this page will embed them when they land.

- **Failing cell**: exactly `3.9` (the `match`-syntax `SyntaxError`), the
  other four pass
- **Test count per cell**: 7 (6 executed + 1 toggle-skipped; identical on
  every version — pytest's JUnit `tests` attribute counts the skipped test)
- **Interpreter identity**: 3.9.25, 3.10.21, 3.11.2, 3.12.14, 3.13.15 —
  five distinct interpreters, each matching its cell (the judge checks
  major.minor per SPEC; the exact patches are what uv fetched at setup time,
  measured on the acceptance runs of 2026-10-15)
- **Exit codes**: 0 with the toggle off, 1 with the toggle on
- **Self-test kill rate**: 9/9 = 100 % (requirement ≥ 90 %)

## Ask your agent

> Set up a sandbox and solve the demo in `cookbook/ci-test-matrix/` of
> https://github.com/agent-next/sandbox (clone it first). Run
> `bash cookbook/ci-test-matrix/judge/setup.sh`, read
> `cookbook/ci-test-matrix/SPEC.md`, then design the artifact yourself: a
> `matrix.yaml` naming the cells, the fixture, the toggle and the JUnit
> directory, plus a `run_matrix.py` that runs the fixture suite under each
> version in its own uv-managed interpreter, writes one JUnit XML file per
> cell, aggregates them into a matrix table, and exits non-zero when any
> cell fails. Iterate with
> `bash cookbook/ci-test-matrix/judge/grade.sh <your-dir> --json v.json`
> until it exits 0, then paste the final verdict JSON. Do not edit anything
> under `judge/`; if you believe the judge is wrong, say so instead of
> working around it. Kill the sandbox when you are done.

The known-good example in `examples/good/` is a hand-written runner that
shells out to `uv` and `pytest`; a working answer does not have to be.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/ci-test-matrix/run.py          # --ref main --keep supported
```

Creates a sandbox, clones the repo, installs pinned tools, runs the judge
self-test, grades `examples/good/`, prints the verdict JSON, then kills the
sandbox and confirms it is gone. Stdlib only; exits non-zero on any failure,
naming the sandbox id if cleanup cannot be confirmed.

## Measured wall time (Debian sandbox, 2 vCPU)

| step | wall time |
|---|---|
| `git clone --depth 1` | ~6-10 s |
| `judge/setup.sh` (fresh install) | ~6-12 s (a cold cache downloads and sha256-checks the uv tarball) |
| `judge/selftest.sh` (good + 9 mutants + determinism) | ~4.5-5.5 min |
| `judge/grade.sh examples/good/` | ~25-35 s |

Whole run, including sandbox create and kill: ~5.5-6.5 minutes. The three
fresh acceptance runs of 2026-10-15 (`RECEIPT.md`) all printed the same
verdict, kill rate and per-step times. `run.py` prints a per-step timing
line.

## Limits, plainly

- The fixture is hand-written and pinned: 7 tests (6 executed + 1
  toggle-skipped), pure stdlib, with one deliberately version-specific
  failure (`match` syntax, a `SyntaxError` below 3.10). Real package
  installation from PyPI is out of scope — only the one pinned,
  hash-checked `pytest` wheel set is installed per cell.
- Interpreters are uv-managed CPython 3.9–3.13; uv fetched `3.9.25`,
  `3.10.21`, `3.11.2`, `3.12.14`, `3.13.15` on the acceptance runs of
  2026-10-15 (recorded in `judge/VERSIONS.txt` — uv installs the latest
  patch it knows for each requested major.minor, which can drift as new
  patches ship), and the judge checks each cell's interpreter is distinct
  and matches its cell on major.minor (see SPEC.md). A base image without
  those downloads needs network access for `uv`.
- The judge grades what SPEC.md grades: the seven gates G1–G7. Parallelism,
  caching and reporting style beyond a machine-parseable YAML table are not
  rewarded.
- `uv` needs to download the five interpreters and the pinned wheels on a
  fresh machine; that is the one network dependency, sha256-checked on the
  `uv` binary and hash-checked on every wheel.
