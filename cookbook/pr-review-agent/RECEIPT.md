# RECEIPT — `cookbook/pr-review-agent/`

Real command output from two fresh runs (a fresh pytest venv under `$HOME`
each time) on a Debian agent-next sandbox, 2 vCPU / ~4 GB. Every number below
is pasted from `/tmp/timed_run.log` (run 1) and `/tmp/timed_run2.log` (run 2)
except where a line says otherwise. Nothing here is estimated.

**Path substitution:** the pasted blocks replace the sandbox's home and
checkout directories with `$HOME` and `$REPO` — the only edit made to any
pasted line, so that this public file carries no absolute local path. The
judge itself prints `$HOME` in its own messages (`judge/setup.sh`), and
`judge/VERSIONS.txt` records `pytest venv: $HOME/.pr-review-agent/venv`.

Sandbox: `Linux x86_64`, `python3 3.12.15`, `git 2.39.5`, `pytest 8.4.2`
(the exact version `judge/setup.sh` pins), date `2026-10-15` (UTC).

## Run 1 — `bash judge/setup.sh` (fresh venv, no `$HOME/.pr-review-agent`)

```
=== SETUP (fresh venv) ===
setup: pr-review-agent judge (Linux x86_64)
setup: creating venv $HOME/.pr-review-agent/venv
setup: installing pytest 8.4.2 from PyPI (hashes pinned)
make_fixture: OK (6 diffs + oracle match)
setup: tool versions
# pr-review-agent judge: versions installed by judge/setup.sh
# (Linux x86_64), 2026-10-15T03:17:22Z
pytest 8.4.2
pytest venv: $HOME/.pr-review-agent/venv
python3 3.12.15
git 2.39.5
setup: wrote $REPO/cookbook/pr-review-agent/judge/VERSIONS.txt
setup: done

real	0m41.642s
user	0m13.680s
sys	0m2.223s
```

Exit code: **0**. Idempotent re-run (same command, venv present):

```
=== SETUP idempotent re-run ===
setup: pytest 8.4.2 already installed in $HOME/.pr-review-agent/venv (skipping download)
make_fixture: OK (6 diffs + oracle match)
...
real	0m5.773s
```

Exit code: **0**. (`make_fixture.py --check` re-verifies the 6 diffs and the
answer key against the pristine tree on every setup, so a stale fixture fails
setup rather than grading.)

## Run 1 — `bash judge/grade.sh examples/good/review --json /tmp/verdict_receipt.json`

```
grade: PR 1 buggy tree -- FAILED tests/test_pr1.py::test_a_full_page_is_not_truncated - assert [3, 4] =...
grade: PR 2 buggy tree -- FAILED tests/test_pr2.py::test_a_customer_name_is_data_not_sql - assert [2, 1...
grade: PR 3 buggy tree -- FAILED tests/test_pr3.py::test_tax_of_a_missing_order_is_none_not_a_crash - T...
grade: PR 4 buggy tree -- FAILED tests/test_pr4.py::test_concurrent_increments_are_not_lost - assert 59...
{ ... verdict JSON, see below ... }
real	0m28.583s
GRADE_EXIT=0
```

Exit code: **0**. Key numbers read out of the verdict JSON (the `grade: ...`
lines above are the judge's stderr note of *why* the buggy-tree tests failed;
the stdout JSON is deterministic and carries none of them):

```
passed True
g2 caught 4 / 4
g3 majors on clean 0
g4 pass True g5 pass True
timing {'materialize_trees_s': 0.166, 'g1_shape_s': 0.015, 'g4_g5_pytest_s': 27.658, 'g6_isolation_s': 0.015, 'total_s': 28.008}
  PR1: buggy exit=1 failed=1 | fixed exit=0 passed=1
  PR2: buggy exit=1 failed=1 | fixed exit=0 passed=1
  PR3: buggy exit=1 failed=1 | fixed exit=0 passed=1
  PR4: buggy exit=1 failed=1 | fixed exit=0 passed=2
  PR5: buggy exit=0 failed=0 | fixed exit=0 passed=1
  PR6: buggy exit=0 failed=0 | fixed exit=0 passed=1
```

## Run 1 — `bash judge/selftest.sh`

```
selftest: fixture generator is deterministic
make_fixture: OK (6 diffs + oracle match)
selftest: grading known-good $REPO/cookbook/pr-review-agent/examples/good/review
grade: PR 1 buggy tree -- FAILED tests/test_pr1.py::test_a_full_page_is_not_truncated - assert [3, 4] =...
grade: PR 2 buggy tree -- FAILED tests/test_pr2.py::test_a_customer_name_is_data_not_sql - assert [2, 1...
grade: PR 3 buggy tree -- FAILED tests/test_pr3.py::test_tax_of_a_missing_order_is_none_not_a_crash - T...
grade: PR 4 buggy tree -- FAILED tests/test_pr4.py::test_concurrent_increments_are_not_lost - assert 59...
selftest: known-good PASSED all gates
mutants: wrote 10 mutants to /tmp/tmp.7bcQrYcMS9/mutants
mutants:   missed-off-by-one
mutants:   wrong-kind-none-deref
mutants:   wrong-line-race
mutants:   downgraded-sql-injection
mutants:   invalid-severity
mutants:   false-positive-on-clean
mutants:   test-passes-on-buggy
mutants:   test-fails-on-fixed
mutants:   test-collection-error
mutants:   test-skipped
selftest: killed    downgraded-sql-injection (gate: g2_coverage)
selftest: killed    false-positive-on-clean (gate: g3_clean_prs)
selftest: killed    invalid-severity (gate: g1_shape)
selftest: killed    missed-off-by-one (gate: g2_coverage)
selftest: killed    test-collection-error (gate: g4_failing_test)
selftest: killed    test-fails-on-fixed (gate: g5_passing_test)
selftest: killed    test-passes-on-buggy (gate: g4_failing_test)
selftest: killed    test-skipped (gate: g4_failing_test)
selftest: killed    wrong-kind-none-deref (gate: g2_coverage)
selftest: killed    wrong-line-race (gate: g2_coverage)
selftest: kill rate 10/10 = 100%
grade: PR 1 buggy tree -- FAILED tests/test_pr1.py::test_a_full_page_is_not_truncated - assert [3, 4] =...
grade: PR 2 buggy tree -- FAILED tests/test_pr2.py::test_a_customer_name_is_data_not_sql - assert [2, 1...
grade: PR 3 buggy tree -- FAILED tests/test_pr3.py::test_tax_of_a_missing_order_is_none_not_a_crash - T...
grade: PR 4 buggy tree -- FAILED tests/test_pr4.py::test_concurrent_increments_are_not_lost - assert 50...
grade: PR 1 buggy tree -- FAILED tests/test_pr1.py::test_a_full_page_is_not_truncated - assert [3, 4] =...
grade: PR 2 buggy tree -- FAILED tests/test_pr2.py::test_a_customer_name_is_data_not_sql - assert [2, 1...
grade: PR 3 buggy tree -- FAILED tests/test_pr3.py::test_tax_of_a_missing_order_is_none_not_a_crash - T...
grade: PR 4 buggy tree -- FAILED tests/test_pr4.py::test_concurrent_increments_are_not_lost - assert 53...
selftest: determinism OK (two --seed 1 runs identical but for timing)
selftest: OK
real	7m15.207s
user	2m21.550s
sys	0m16.475s
SELFTEST_EXIT=0
```

Exit code: **0**. Kill rate **10/10 = 100 %** (requirement ≥ 90 %). Every
gate is exercised by at least one mutant: G1 `invalid-severity`,
G2 four mutants (missed / wrong kind / wrong line / downgraded),
G3 `false-positive-on-clean`, G4 `test-passes-on-buggy`, `test-skipped`,
`test-collection-error`, G5 `test-fails-on-fixed`.

## Run 2 — second fresh sandbox run (fresh venv again)

Same commands, `$HOME/.pr-review-agent` removed first, output in
`/tmp/timed_run2.log`.

| step | run 1 wall | run 2 wall |
|---|---|---|
| `judge/setup.sh` (fresh) | 37.6 s | 30.8 s |
| `judge/grade.sh examples/good/review` | 23.7 s | 19.9 s |
| `judge/selftest.sh` | 343.2 s | 266.3 s |

Run 2 verdict: `passed: true`, all six gates pass, `caught 4/4`, `0` major
findings on clean PRs, self-test kill rate `10/10 = 100 %`, determinism OK,
every command exit 0. The only variation between runs is wall time, which the
SPEC excludes from the compared JSON (it lives under the `timing` key,
stripped by `selftest.sh`).

## Verdict JSON for `examples/good/review` (run 1, `--seed 20261015`)

Pasted from `/tmp/verdict_receipt.json`, with the two large nested blocks
elided (`g4_failing_test.prs` — the per-PR buggy/fixed counts shown above —
and the `matched` list of the four matched defects). Every key/value left in
is verbatim:

```json
{
  "artifact": "$REPO/cookbook/pr-review-agent/examples/good/review",
  "seed": 20261015,
  "passed": true,
  "failed_gate": null,
  "gates": {
    "g1_shape": {
      "passed": true,
      "problems": [],
      "prs_graded": [1, 2, 3, 4, 5, 6]
    },
    "g2_coverage": {
      "passed": true,
      "caught": 4,
      "planted": 4,
      "matched": [ "…4 entries, elided…" ],
      "missed": []
    },
    "g3_clean_prs": {
      "passed": true,
      "major_findings_on_clean_prs": 0,
      "findings": [],
      "clean_prs": [5, 6]
    },
    "g4_failing_test": {
      "passed": true,
      "prs": { "…6 PRs, see the per-PR counts above…" },
      "failures": [],
      "rule": "buggy tree: pytest exit 1 with >= 1 failed test"
    },
    "g5_passing_test": {
      "passed": true,
      "failures": [],
      "rule": "fixed tree: pytest exit 0 with >= 1 passed test (defect PRs: the pristine tree; clean PRs: the PR tree, which is already clean)"
    },
    "g6_isolation": { "passed": true, "problems": [] }
  },
  "timing": {
    "materialize_trees_s": 0.166,
    "g1_shape_s": 0.015,
    "g4_g5_pytest_s": 27.658,
    "g6_isolation_s": 0.015,
    "total_s": 28.008
  },
  "tool": {
    "pytest_python": "$HOME/.pr-review-agent/venv/bin/python",
    "python": "3.12.15"
  }
}
```

## Not done in this run

- **(not done: no sandbox-create credentials in this environment)** `run.py`
  was not executed end to end: this sandbox cannot create sandboxes, and no
  `SBX_API_KEY` is present. It was verified with `python3 -m py_compile
  run.py` and by running its exact in-sandbox command sequence by hand from a
  fresh `git clone` (`judge/setup.sh` → `judge/selftest.sh` →
  `judge/grade.sh examples/good/review`), which is what produced the numbers
  above. The lead runs `run.py` end to end.
- **(not done: a later task does media)** `media/` is intentionally absent:
  `DEMO-STANDARD.md`'s figure/video step is a separate task.
- **(not done: needs a second agent in a fresh sandbox)** `REPRODUCE.md`: an
  independent reproduction by a different agent is required before merge and
  is not something this run can do for itself.

## Deviations from `DEMO-STANDARD.md`

- **Fixture is generated, not a clone of a public repo.** The standard's
  reproducibility rules assume a pinned upstream; the brief for this demo
  asks for "a small pinned repo plus 6 PR diffs ... generated by a script",
  so `judge/fixture/repo/` is a small service written for the demo and the
  PRs are generated by `judge/fixture/make_fixture.py`. It is pinned by
  `judge/fixture/PINS.json`-style hashes in `judge/oracle/GROUND_TRUTH.json`
  (`pristine_sha256` + per-PR `pr_sha256`), and every grade re-checks them.
  The SPEC's "upstream" paragraph describes this rather than a git SHA.
- **No Debian packages.** `judge/setup.sh` installs nothing from apt: this
  image's apt lists are empty, and the judge needs only Python and `git`
  (both already present) plus one PyPI wheel set.
- **Only one third-party tool, one version.** `pytest==8.4.2` is the sole
  pinned download (`judge/requirements.txt`, `--require-hashes`). It is the
  version already present in the base image, so the in-sandbox and
  developer runs match.
- **`selftest.sh` is slow (~7 min).** It runs 13 full grades, and each grade
  spawns 12 pytest processes. This is a property of the demo (the reviewer's
  tests are the expensive part), not of the judge engine; the single good
  grade is ~28 s.
- **Line matching tolerance is ±2, kind matching is exact.** This is the
  brief's rule, written into SPEC G2 and enforced mechanically.
- **The `race` fixture is file-backed.** A plain in-memory `+= 1` on a small
  int does not lose updates under CPython 3.12 (measured 0/5 trials at 50 000
  iterations), so the planted race is a lost update on a JSON-file counter,
  which reproduces 8/8 trials on the buggy tree. Recorded here so nobody
  "simplifies" it back into a test that never fails.
