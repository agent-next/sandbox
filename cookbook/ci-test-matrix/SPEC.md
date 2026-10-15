# SPEC — `cookbook/ci-test-matrix/`

An agent works on a real CI problem inside a disposable agent-next sandbox:
produce a **test matrix runner** that runs one pinned library's pytest suite
across many Python versions — one disposable sandbox cell per version,
uv-managed interpreters — collects a JUnit XML file per cell, and aggregates
them into a matrix table that a judge it cannot fool decides is correct. A
judge that "runs" is not enough: the verdict is checked against an
independent oracle (a hand-computed expectation of which cell must fail and
why), a measured per-cell mask, and a coverage/identity gate, so a runner
that silently skips a cell, reuses one interpreter, or masks a failure cannot
pass.

## Goal

Design and fix a matrix runner, expressed as one `matrix.yaml` plus one
`run_matrix.py`, that:

- runs a fixture library's pytest suite across **Python 3.9, 3.10, 3.11,
  3.12, 3.13** (5 cells), each under its own uv-managed interpreter;
- collects **one JUnit XML file per cell**;
- aggregates every cell into a pass/fail **matrix table**;
- detects the fixture's deliberately **version-specific failure** (a module
  using `match` syntax, which is a `SyntaxError` on Python 3.9 and below)
  in **exactly the 3.9 cell** when its toggle is on.

## Non-goals

- Real package installation from PyPI, dependency resolution beyond one
  pinned `pytest` wheel, or building the fixture library.
- Network access inside the sandbox beyond `uv` fetching interpreters and the
  one pinned pytest wheel.
- Test-framework features beyond collection, execution, and JUnit XML.
- The matrix table's visual style (spacing, alignment) beyond being a
  machine-parseable YAML mapping.
- Optimisation: no reward for running cells faster than the pass rules.

## Artifact

Two files (the files graded by `judge/grade.sh <artifact-dir>`):

1. **`matrix.yaml`** — the matrix definition, containing:
   - `python_versions`: the list of Python versions to run (the cells);
   - `fixture`: path to the fixture library's test package;
   - `toggle`: name of the fixture's version-specific-failure toggle;
   - `junit_dir`: directory where per-cell JUnit XML files are written.

2. **`run_matrix.py`** — the runner, stdlib only, which:
   - reads `matrix.yaml`;
   - for each version in `python_versions`, creates a uv venv with that
     interpreter, installs the pinned pytest, runs the fixture suite, and
     writes `<junit_dir>/cell-<version>.xml`;
   - parses every cell's JUnit XML and aggregates pass/fail into a matrix
   table;
   - prints the table and writes it to `matrix.yaml` (or a sibling
   `matrix-result.yaml`);
   - exits non-zero if any cell fails.

The known-good example is a hand-written runner that shells out to `uv` and
`pytest`; the gates below apply to *any* runner the agent produces.

## Judge gates (`judge/grade.sh <artifact-dir> [--seed N] [--json out.json]`)

All gates are numeric and deterministic. Exit 0 only if every gate passes.

- **G1 parse**: `matrix.yaml` is valid YAML with the four required keys, and
  `python_versions` lists **exactly** `["3.9", "3.10", "3.11", "3.12",
  "3.13"]` (5 cells, no duplicates).
- **G2 coverage**: `run_matrix.py` runs and produces a JUnit XML file for
  **every** version in `python_versions` (5 files), each non-empty.
- **G3 interpreter identity**: each cell's JUnit XML records a `python`
  version string (the `hostname` attribute or a `properties` block) matching
  the version in `python_versions` for that cell — no two cells share the
  same interpreter.
- **G4 failure detection**: when the fixture's toggle is **on**, the
  aggregated matrix table shows **exactly one** failing cell, at version
  `3.9`, and the other four cells pass. When the toggle is **off**, all five
  cells pass.
- **G5 count equality**: every cell's JUnit XML reports the **same** number
  of tests (the fixture has the same test count on every version).
- **G6 mask**: the aggregated table's pass/fail pattern matches the
  expected mask: `[pass, pass, pass, pass, fail]` with toggle on,
  `[pass, pass, pass, pass, pass]` with toggle off.
- **G7 sanity**: `run_matrix.py` exits 0 when the toggle is off (all pass)
  and non-zero when the toggle is on (one failure). A runner that always
  exits 0 is masking a failure.

Violating any gate fails with the offending numbers printed.

## Acceptance oracle (independent of "it ran")

1. **Analytic reference**: the fixture library is hand-written and pinned.
   Its test count is known (6 tests), and its failure behaviour is known
   exactly: the `match`-syntax module fails to import on Python 3.9 and
   below (a `SyntaxError`), so with the toggle on, exactly the 3.9 cell
   fails. The judge computes this expectation from first principles (the
   Python language specification: `match` is a keyword from 3.10) and
   compares the aggregated table against it. This catches a runner that
   reports all-pass when it actually skipped the 3.9 cell.
2. **Interpreter identity**: the judge inspects each JUnit XML file for a
   version stamp (the `hostname` attribute, which the runner sets to the
   interpreter version). It checks that all five versions are distinct and
   match `python_versions`. This catches a runner that runs every cell under
   one interpreter.
3. **Spec mask**: the pass/fail pattern in the aggregated table must match
   the expected mask (G6), computed from the fixture's known behaviour, not
   asserted by the artifact or its comments.
4. **Monte-Carlo reproducibility**: with the fixed seed the pass fraction
   must be identical between two consecutive grade invocations
   (deterministic RNG seeding); `--seed` overrides it.

## Self-test (`judge/selftest.sh`)

- The known-good example passes all gates.
- ≥ 5 known-bad single-edit mutants of the good artifact each fail ≥ 1
  gate; mutants generated by `judge/mutants.py` (one edit each), including
  `cell-skipped` (3.9 removed from `python_versions`),
  `same-interpreter` (all cells stamped 3.12),
  `failure-masked` (runner exits 0 despite a failing cell),
  `junit-missing` (no JUnit XML written for one cell),
  `wrong-count` (aggregated table reports 5 tests instead of 6).
- Kill rate ≥ 90 % printed by the self-test; exit non-zero otherwise.
- Determinism: two `grade.sh` runs with the same seed produce
  byte-identical verdict JSON; checked by the self-test on every run.

## Judge-integrity rule

The artifact under test is copied to a temp dir before grading; the judge
compares `sha256` of its own `judge/` tree before and after every grade and
fails closed if anything changed.

## Out of scope for the judge

- Whether the runner is *good engineering* beyond the gates (parallelism,
  caching, reporting style).
- Anything the artifact claims in comments.

## Tools (pinned by `judge/setup.sh`)

- uv **0.12.16** (GitHub release tarball, SHA256-pinned download),
  installed idempotently. Python 3.10+ (stdlib only) for the judge math.
- Interpreters: CPython 3.9.25, 3.10.21, 3.11.16, 3.12.14, 3.13.15
  (uv-managed, exact patches).
- pytest **8.4.2** (PyPI wheel, hash-pinned via `uv pip install --require-hashes`).
