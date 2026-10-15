# SPEC — `cookbook/pr-review-agent/`

An agent does a real code-review job inside a disposable agent-next sandbox:
review 6 pull-request diffs against a small pinned repository, report each
defect as a machine-readable finding, and *prove* each finding with a test
that fails on the buggy PR and passes on the fix. A judge the agent cannot
fool decides whether the review is right.

## Goal

Produce, for each of 6 PRs, a `review.json` that localizes every planted
defect (file + line + severity + kind) and ships a `tests/test_pr<k>.py`
that fails on the PR as given and passes on the fixed version. The judge
runs the reviewer's tests both ways and grades the findings against the
planted ground truth it holds privately.

## Non-goals

- Reviewing a *large* real repository or a live GitHub PR. The surface is
  the 6 pinned PRs below, nothing else.
- Style, formatting, naming, docs, performance, and every defect kind other
  than the four planted classes. A finding whose `kind` is not the planted
  kind does not count (see G2).
- Auto-fixing the PRs. The agent reports and writes tests; it does not have
  to patch the fixture (the *fixed* side of every PR is the judge's private
  ground truth).
- Whether the reviewer is a model, a linter, or a human. The artifact is the
  JSON + tests, not the method.

## Fixture (pinned, generated)

The fixture is a small pure-Python service repo (`orders`: a tiny
sqlite-backed store, pagination, config lookup, a worker and a shared
counter) written for this demo and shipped in `judge/fixture/`. It is
*pinned* two ways:

- `judge/fixture/repo/` is the pristine tree; its `sha256` (path + content
  over every file) is recorded as `pristine_sha256` in
  `judge/oracle/GROUND_TRUTH.json`, and `grade.sh` fails closed if the tree
  on disk does not match — before any test runs.
- The 6 PRs are **single-hunk unified diffs** (`judge/fixture/pr<k>.diff`)
  applied on top of the pristine tree, produced by the committed,
  deterministic generator `judge/fixture/make_fixture.py`. Each applied PR
  tree is hashed and checked against `pr_sha256` in the same answer key, so
  a diff that does not land fails closed. Same pristine tree → byte-identical
  diffs and answer key; `selftest.sh` re-checks this on every run
  (`make_fixture.py --check`).

Four PRs each carry exactly one planted defect, one per class:

- `off-by-one` — a slice bound shifted by one (pagination drops an item);
- `sql-injection` — a value interpolated into a query string with `%`
  instead of a bound parameter;
- `none-deref` — a config lookup that can return `None` used without a
  check;
- `race` — read-modify-write on a shared counter with no lock.

Two PRs are **clean**: one is a behaviour-preserving refactor, the other
adds a function plus its test. "Any diff is a defect" is therefore not a
usable heuristic.

The answer key (`judge/oracle/GROUND_TRUTH.json`: file, line, kind,
severity per defect, and the pristine tree hash) lives outside
`judge/fixture/` and is never copied into the tree the reviewer's tests run
against.

## Artifact

The artifact is a directory. For each PR `k` in `1..6` it contains:

- `pr<k>/review.json` — one object per PR:
  ```json
  {
    "pr": 1,
    "findings": [
      {"file": "orders/pagination.py", "line": 7,
       "severity": "major", "kind": "off-by-one"}
    ]
  }
  ```
  - `file`: repo-relative path as it appears in the diff's `+++` header.
  - `line`: 1-based line number **in the PR (post-change) file**.
  - `severity`: one of `info`, `minor`, `major`, `critical`.
  - `kind`: one of `off-by-one`, `sql-injection`, `none-deref`, `race`,
    `other`.
- `pr<k>/tests/test_pr<k>.py` — a `pytest` module the judge runs twice:
  once against the PR tree (must **fail**) and once against the fixed
  version (must **pass**). For the 4 defect PRs the fixed version is the
  pristine tree; for the 2 clean PRs it is the PR tree itself, which is
  already clean — the test still has to pass there, so a module that cannot
  even import against the tree it was written for fails closed.

Graded with `judge/grade.sh <artifact-dir>`.

## Judge gates

All gates are numeric and deterministic. Exit 0 only if every gate passes.

- **G1 shape**: the artifact dir has `pr1..pr6`, each with exactly
  `review.json` and `tests/test_pr<k>.py`; every `review.json` parses, names
  its own PR, and every finding carries a `file` that exists in that PR's
  tree, an integer `line` inside that file, a valid `severity` and a valid
  `kind`. Malformed input fails here, before any scoring.
- **G2 coverage** (planted defect `d` with file `f_d`, line `l_d`, kind
  `k_d`): a finding *matches* `d` iff `file == f_d`, `|line - l_d| <= 2`,
  `severity >= major`, and `kind == k_d`. Let `C` = number of the 4 planted
  defects matched by at least one distinct finding. Pass iff **`C == 4`**.
- **G3 clean-PR false positives**: let `F` = number of findings on the 2
  clean PRs with `severity >= major`. Pass iff **`F == 0`**.
- **G4 failing test on the buggy PR**: for each of the 4 defect PRs,
  `pytest tests/test_pr<k>.py` run against that PR's tree must exit
  **non-zero** with **>= 1 failed** test. A collection error, an internal
  error or a skip is not a failure and does not satisfy G4.
- **G5 passing test on the fixed version**: the same `tests/test_pr<k>.py`
  run against the judge's private fixed tree (the pristine tree) must exit
  **0** with **>= 1 passed** test. G4 + G5 together mean the test is a real
  oracle, not `assert False`.
- **G6 isolation**: the reviewer's tests run in a copy of the tree with
  `judge/` and the artifact's other PRs removed, working directory set to
  the copy; the judge hashes its own tree before and after grading and fails
  closed if anything changed.

Pass = G1 ∧ G2 ∧ G3 ∧ G4 ∧ G5 ∧ G6. The verdict JSON lists every gate's
measured numbers and the first failing gate.

## Acceptance oracle (independent of "it ran")

The judge trusts neither the reviewer's prose nor even its own successful
run. It compares against three independent things:

1. **A private answer key** (`judge/oracle/GROUND_TRUTH.json`), generated by
   the same deterministic script that generated the diffs. Findings are
   scored against the key, never against the diff text the agent can read.
2. **A two-way reference run of the reviewer's own tests** (buggy tree,
   fixed tree). A test that passes on both, or fails on both, is evidence of
   nothing and fails G4 or G5. This is the convergence check: the test must
   *discriminate* the two trees, and the tree it fails on is the one the
   finding blames.
3. **A spec mask over severities**: the `severity >= major` threshold is
   fixed in this SPEC and applied mechanically, so a review that labels
   everything `critical` fails G3 on the clean PRs, and one that labels
   everything `info` fails G2.

Known-good and known-bad artifacts are graded by `judge/selftest.sh` to
prove every gate can fail.

## Self-test (`judge/selftest.sh`)

- `examples/good/review/` (written by hand: all 4 defects caught, 0 clean-PR
  false positives, 4 discriminating tests) passes every gate.
- >= 6 known-bad artifacts, generated as single-edit mutants of the good
  artifact by `judge/mutants.py`, each fail >= 1 gate, with at least one
  mutant per gate: a review missing one defect; a false-positive `major` on
  a clean PR; a test that passes on the buggy code; a finding whose line is
  off by more than 2; a finding with the wrong `kind`; and a test that fails
  on the fixed tree too.
- Kill rate printed; exit non-zero if below **90 %**.
- Determinism: two `grade.sh` runs with the same `--seed` produce
  byte-identical verdict JSON except the `timing` key; checked every run.

## Judge-integrity rule

The artifact is copied to a temp dir before grading. The judge hashes its
own tree before and after every grade and fails closed on any change. The
answer key is never placed inside the tree handed to the reviewer's tests.

## Out of scope for the judge

- Anything the review says beyond the four fields above (comments, rationale,
  suggested patches).
- Whether the reviewer used a model, a linter or grep.
- Defects the demo did not plant.

## Tools (pinned by `judge/setup.sh`)

- `pytest` **8.4.2** — exact version, SHA256-pinned wheel from PyPI
  (`--require-hashes`), installed into a venv at
  `$HOME/.pr-review-agent/venv`; the judge runs it as
  `<venv>/bin/python -m pytest`.
- Python **3.10+** (judge engine and `run.py` are stdlib only) and `git`
  (to materialize PR trees from the diffs) — both already present in the
  agent-next base image; `setup.sh` checks and names them.
- No Debian packages: this image's `apt-get` lists are empty, and the demo
  deliberately needs nothing from apt.
