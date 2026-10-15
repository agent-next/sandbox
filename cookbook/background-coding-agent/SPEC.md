# SPEC — `cookbook/background-coding-agent/`

An agent is handed a small pinned repository with an open issue and works
it the way a background coding agent does: it edits the code inside a
disposable sandbox, runs the project's own tests, and hands back a branch
— a `delivery.patch` plus a `PR.md`. A judge it cannot fool applies that
patch to a clean checkout of the pinned repository and decides whether the
delivery is correct: the old tests still pass, a **hidden** acceptance
suite passes, lint is clean, the JSON the new feature prints agrees with
statistics the judge computes itself from the raw data, and the PR
description actually describes the change. The agent never sees the
acceptance suite or the judge's reference implementation, so "it ran and
printed something" is not enough to pass.

## Goal

Deliver a working implementation of `fixture/ISSUE.md` as a patch against
the pinned fixture, together with a pull-request description, such that
the judge's gates all pass.

## Non-goals

- The patch's *style*: any implementation that satisfies the gates is
  accepted. No reward for margin, cleverness or minimality beyond the
  pass rules.
- Commit history, branches, rebases, or how the agent produced the patch
  inside its sandbox. Only the two delivered files are graded.
- New third-party dependencies. The fixture is stdlib-only and the issue
  requires that it stays that way.
- Performance beyond a wall-clock timeout (each CLI invocation must
  finish within 20 s).
- Anything the patch or `PR.md` *claims* in prose. Only the changed
  bytes and the measured behaviour count.

## Artifact

Two files, delivered side by side:

| file | what |
|---|---|
| `delivery.patch` | a unified diff (`git diff` format, `a/`…`b/` prefixes) that applies to a clean checkout of `fixture/` |
| `PR.md` | the pull-request description: a summary and a test plan |

`judge/grade.sh <delivery.patch>` grades the patch and looks for `PR.md`
next to it; `--pr <path>` overrides that lookup. Paths in the patch may be
rooted at the fixture (`measurectl/cli.py`) or at the repository
(`cookbook/background-coding-agent/fixture/measurectl/cli.py`); the judge
normalizes the repository-rooted form.

The known-good example is `examples/good/delivery.patch` +
`examples/good/PR.md`; a correct delivery does not have to resemble it.

## The pinned fixture

`fixture/` is a vendored snapshot of a small stdlib-only project
(`measurectl`, a CSV summariser) plus its own test suite and one sample
input. It is pinned by content: `judge/FIXTURE.sha256` lists the sha256 of
every fixture file, and the judge **fails closed** if the fixture it is
about to grade differs from that manifest. The judge copies the fixture to
a temp directory, applies the patch there, and never writes to `fixture/`.

## Judge gates (`judge/grade.sh <delivery.patch> [--seed N] [--json out.json]
[--pr PR.md]`)

All gates are numeric and deterministic. Exit 0 only if every gate passes.

- **G1 `patch`** — the fixture matches `judge/FIXTURE.sha256`; the patch is
  a parseable unified diff; `git apply --check` and the real `git apply`
  both succeed on the clean checkout; the patch changes **1..20** files,
  **≥ 1** of them under `measurectl/`, and at most **2000** added+removed
  lines in total; `PR.md` exists and is **≥ 200** characters.
- **G2 `integrity`** — the patch touches no file under `tests/` and no
  tool-configuration file (`pyproject.toml`, `setup.py`, `setup.cfg`,
  `tox.ini`, `pytest.ini`, `conftest.py`, `ruff.toml`, `.ruff.toml`), adds
  no new file with one of those names or with an interpreter-startup name
  (`sitecustomize.py`, `usercustomize.py` — the checkout root is on
  `PYTHONPATH` for the graded subprocesses), and contains no path that
  escapes the checkout root (absolute, `..`, or outside `fixture/`). The
  judge additionally re-hashes the checkout's `tests/` against the fixture
  manifest after applying the patch.
- **G3 `regression`** — the fixture's own pinned suite runs on the patched
  checkout and passes: **0 failed**, **0 errors**, **≥ 12** tests
  collected. The judge supplies its own pytest configuration and
  `PYTHONPATH`, so configuration changes in the patch cannot affect this.
- **G4 `acceptance`** — the judge's hidden suite (`judge/acceptance/`,
  copied into the checkout after the patch is applied) passes: **0
  failed**, **0 errors**, **≥ 18** tests collected.
- **G5 `lint`** — pinned ruff with the judge's own configuration
  (`judge/ruff.toml`) reports **0** diagnostics on the patched checkout.
- **G6 `oracle`** — for each input in {the fixture's sample CSV, two CSVs
  the judge synthesises from `--seed`}: run the patched CLI as
  `python -m measurectl --json <csv>` and compare the emitted document
  against the judge's **own independent computation** from the raw CSV.
  Required: the schema mask holds (exact key sets, types, integer counts,
  metrics sorted by name), every numeric field agrees with the judge's
  reference to **≤ 1e-9** relative error (counts exactly), and the
  invariants `min ≤ mean ≤ max`, `count` = the number of data rows, and
  `|sum − count·mean| ≤ 1e-9·max(1, |sum|)` all hold. `--json` must exit
  **0** on all three inputs.
- **G7 `pr`** — `PR.md` contains a summary section and a test-plan
  section (headings matched case-insensitively on `summary` and
  `test plan`/`test plan`/`testing`) and mentions **100 %** of the files
  the patch changes, each as its fixture-relative path or its basename.

A failed gate is reported with its own name, the offending numbers, and
the first few offending entries; the gates already run stay in the verdict.

## Acceptance oracle (independent of "the tool ran")

The fixture computes its statistics with a plain accumulation loop over
`float`s. The judge does **not** import, call or copy that code — if it
did, a patch could corrupt `stats.py` and the judge would agree with it.
Instead:

1. **Independent reference implementation.** `judge/reference.py` parses
   the same CSV grammar and computes every statistic a second time with
   `statistics.fmean` / `statistics.mean`, which are correctly rounded and
   take a different code path from the fixture's naive loop. The emitted
   JSON is compared field by field against *that*.
2. **Spec mask.** The document's key sets, value types, integer-ness of
   `count`, and the sorted-by-name ordering of `metrics` are checked
   structurally, so a missing field, an extra field, a stringly-typed
   number or a non-deterministic ordering fails regardless of the values.
3. **Mathematical invariants.** `min ≤ mean ≤ max`, `count` equals the
   number of data rows the judge counted, and `sum` is consistent with
   `count · mean` — identities that must hold whatever the implementation,
   checked against the raw data.
4. **Seeded, unseen inputs.** Two of the three graded inputs are generated
   by the judge from `--seed` (default 20261015): several metrics, a
   single-row metric, negative values, a metric whose name sorts before
   and after the sample's, and magnitudes spanning decades. A patch that
   hardcodes the sample answers, or only handles the shapes the sample
   happens to contain, passes nothing.
5. **Determinism.** With a fixed seed the two generated inputs and the
   verdict JSON are byte-identical between runs; `selftest.sh` checks it.

## Self-test (`judge/selftest.sh`)

- The known-good example passes all gates.
- **≥ 5** known-bad mutants, generated by `judge/mutants.py` as exactly
  one edit each of the good delivery, each fail at least one gate. The
  set covers every gate:
  `empty-patch` (G1), `touches-tests` and `startup-hook` (G2),
  `breaks-old-test` (G3), `json-missing-field` and `json-count-as-float`
  (G4), `lint-unused-import` (G5), `mean-sign-dropped` (G6),
  `pr-omits-file` and `pr-no-test-plan` (G7).
- `mean-sign-dropped` is the mutant that justifies the oracle: it drops
  the sign of `mean` (so a metric with negative values reports
  `abs(mean)`), which the fixture's own tests never see and the hidden
  suite's negative-value test does not assert on — it passes the old
  suite, passes the hidden suite, passes lint, and still fails, because
  the judge's seeded inputs contain negative values and the
  `sum = count · mean` identity breaks.
- Kill rate **≥ 90 %** printed by the self-test; exit non-zero otherwise.
- Determinism: two `grade.sh` runs with the same seed produce
  byte-identical verdict JSON; checked on every self-test run.

`hardcoded-output` is the mutant that justifies the oracle: it passes the
old tests, passes lint, passes the acceptance suite and produces the right
numbers for the sample CSV — and still fails, because the judge grades it
on data it has never seen.

## Judge-integrity rule

The artifact under test is never executed inside `judge/`. The patch is
applied to a temp copy of the fixture; the judge hashes its own `judge/`
tree before and after every grade and fails closed if anything changed;
the hidden acceptance suite and the reference implementation live in
`judge/` and are copied into the checkout read-only.

## Out of scope for the judge

- Whether the change is *good engineering* beyond the gates (naming,
  structure, docstrings, added tests of the agent's own).
- The agent's sandbox, its iteration count, or how it found the answer.
- Anything `PR.md` claims that is not also true of the patch.

## Tools (pinned by `judge/setup.sh`)

Installed idempotently into `$HOME` from sha256-checked wheels, nothing
newer than two weeks before the demo's merge:

| tool | version | licence |
|---|---|---|
| ruff | 0.16.9 | MIT |
| pytest | 9.1.1 | MIT |
| pluggy | 1.6.0 | MIT |
| iniconfig | 2.3.1 | MIT |
| packaging | 26.3 | Apache-2.0 / BSD-2-Clause |
| Pygments | 2.21.0 | BSD-2-Clause |

Python ≥ 3.10 (stdlib only) runs the judge itself. `judge/VERSIONS.txt`
records what `setup.sh` actually installed.

## Tolerances

`delivery.patch` and `PR.md` are the only inputs. The numeric tolerance
between the artifact and the judge's reference is **1e-9 relative**; a
correct implementation lands ~1e-16 away, so the bound is loose enough to
accept any honest float arithmetic and tight enough to reject rounded or
truncated output. Wall times in the README are measured, not guaranteed.
