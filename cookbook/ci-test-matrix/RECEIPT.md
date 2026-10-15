# RECEIPT — `cookbook/ci-test-matrix/`

Real command output from four fresh-sandbox acceptance runs, pasted as
produced. Run 4 is the exact committed head of this branch (`36eea06`); runs
1–3 predate only doc-only commits (measured interpreter patches, RECEIPT +
REPRODUCE) that do not change any judged behaviour. All runs use the exact
way the lead does:

```bash
python3 cookbook/ci-test-matrix/run.py --ref <this-branch>
```

from outside, in a disposable agent-next sandbox. Every run printed the same
verdict JSON byte-for-byte except the `timing.wall_s` field.

| | RUN 1 | RUN 2 | RUN 3 | RUN 4 |
|---|---|---|---|---|
| `sbx create --timeout-min 30` | exit 0, 4.4 s | exit 0, 5.0 s | exit 0, 4.0 s | exit 0, 3.9 s |
| `git clone --depth 1` | exit 0, 7.1 s | exit 0, 9.5 s | exit 0, 6.0 s | exit 0, 7.6 s |
| `judge/setup.sh` | exit 0, 10.2 s | exit 0, 11.7 s | exit 0, 6.0 s | exit 0, 7.4 s |
| `judge/selftest.sh` | exit 0, 328.5 s | exit 0, 267.7 s | exit 0, 299.5 s | exit 0, 261.2 s |
| `judge/grade.sh examples/good` | exit 0, 31.5 s | exit 0, 24.5 s | exit 0, 35.8 s | exit 0, 25.3 s |
| verdict | **PASS** | **PASS** | **PASS** | **PASS** |
| kill rate | 9/9 = 100 % | 9/9 = 100 % | 9/9 = 100 % | 9/9 = 100 % |
| mask on | `[fail, pass, pass, pass, pass]` | same | same | same |
| mask off | `[pass, pass, pass, pass, pass]` | same | same | same |
| tests per cell | 7 (6 executed + 1 toggle-skipped) | 7 | 7 | 7 |
| exit codes (on/off) | 1 / 0 | 1 / 0 | 1 / 0 | 1 / 0 |
| interpreter stamps | 3.9.25, 3.10.21, 3.11.2, 3.12.14, 3.13.15 | same | same | same |
| cleanup | killed + confirmed gone | killed + confirmed gone | killed + confirmed gone | killed + confirmed gone |

`diff` of all four verdicts (excluding `timing`): **no differences**.

## Tool versions (from `judge/VERSIONS.txt`)

- `uv 0.12.16 (x86_64-unknown-linux-gnu)` — GitHub release tarball,
  sha256-pinned (`8e5c6e55…`).
- Interpreters: uv-managed CPython (uv fetched the latest patches it knew on
  2026-10-15 — `3.9.25`, `3.10.21`, `3.11.2`, `3.12.14`, `3.13.15`).
- pytest 8.4.2 + pinned wheels from `judge/requirements.txt` (all
  `--require-hashes`).

## Full run-4 transcript (the committed head `36eea06`)

```text
run: [   3.9s] sbx create --timeout-min 30 -> exit 0
run: sandbox 01a1406f-b4af-7b40-8309-582fb328e0fb
run: [   7.6s] git clone -> exit 0
run: [   7.4s] judge/setup.sh -> exit 0
run: [ 261.2s] judge/selftest.sh -> exit 0
== selftest: known-good artifact ==
known-good: PASS (expected)
== selftest: generating known-bad mutants ==
9 mutants generated
mutant cell-skipped: FAIL (expected) -- killed by gate: parse, coverage, identity, detection, counts, table, mask, exit_code
mutant failure-masked: FAIL (expected) -- killed by gate: exit_code
mutant junit-missing: FAIL (expected) -- killed by gate: coverage, identity, detection, mask, exit_code
mutant no-runner: FAIL (expected) -- killed by gate: parse, coverage, identity, detection, counts, table, mask, exit_code
mutant no-versions-key: FAIL (expected) -- killed by gate: parse, coverage, identity, detection, counts, table, mask, exit_code
mutant same-interpreter: FAIL (expected) -- killed by gate: identity
mutant shared-mask: FAIL (expected) -- killed by gate: table
mutant toggle-swapped: FAIL (expected) -- killed by gate: detection, mask, exit_code
mutant wrong-count: FAIL (expected) -- killed by gate: table
== selftest summary ==
mutants: 9 listed, 9 graded
kill rate: 9/9 (100%)
== selftest: determinism (grade the good artifact twice with --seed 42) ==
determinism: PASS (two --seed 42 runs identical excluding "timing")
selftest: PASS
run: [  25.3s] judge/grade.sh examples/good -> exit 0
{
  "verdict": "PASS",
  "timing": {
    "wall_s": 20.5
  },
  "gates": {
    "parse": {
      "pass": true,
      "detail": "matrix.yaml has ['python_versions', 'fixture', 'toggle', 'junit_dir'] and python_versions == ['3.9', '3.10', '3.11', '3.12', '3.13'] (5 cells, no duplicates)"
    },
    "coverage": {
      "pass": true,
      "detail": "one non-empty JUnit XML per cell: cell-3.9.xml=7 tests, cell-3.10.xml=7 tests, cell-3.11.xml=7 tests, cell-3.12.xml=7 tests, cell-3.13.xml=7 tests"
    },
    "identity": {
      "pass": true,
      "detail": "each cell ran under its own interpreter: 3.9=3.9.25, 3.10=3.10.21, 3.11=3.11.2, 3.12=3.12.14, 3.13=3.13.15"
    },
    "detection": {
      "pass": true,
      "detail": "toggle on: exactly the 3.9 cell fails, 3.10, 3.11, 3.12, 3.13 pass (the fixture's match-statement module is a SyntaxError below Python 3.10); toggle off: all five cells pass"
    },
    "counts": {
      "pass": true,
      "detail": "all 5 cells report the same test count (7 tests per cell)"
    },
    "table": {
      "pass": true,
      "detail": "the aggregated table matches the collected JUnit XML on every cell (status and test count)"
    },
    "mask": {
      "pass": true,
      "detail": "the pass/fail pattern matches the expected mask: on -> [pass, pass, pass, pass, fail] (the 3.9 SyntaxError), off -> [pass, pass, pass, pass, pass]"
    },
    "exit_code": {
      "pass": true,
      "detail": "run_matrix.py exits 0 when all cells pass and non-zero when one fails (a runner that always exits 0 cannot pass this gate)"
    }
  },
  "metrics": {
    "versions": ["3.9", "3.10", "3.11", "3.12", "3.13"],
    "junit_files_per_state": {
      "on": 5,
      "off": 5
    },
    "tests_per_cell": 7,
    "aggregated_table": {
      "on": {
        "3.9": {"status": "fail", "tests": 7},
        "3.10": {"status": "pass", "tests": 7},
        "3.11": {"status": "pass", "tests": 7},
        "3.12": {"status": "pass", "tests": 7},
        "3.13": {"status": "pass", "tests": 7}
      },
      "off": {
        "3.9": {"status": "pass", "tests": 7},
        "3.10": {"status": "pass", "tests": 7},
        "3.11": {"status": "pass", "tests": 7},
        "3.12": {"status": "pass", "tests": 7},
        "3.13": {"status": "pass", "tests": 7}
      }
    },
    "mask_on": ["fail", "pass", "pass", "pass", "pass"],
    "mask_off": ["pass", "pass", "pass", "pass", "pass"],
    "exit_codes": {"on": 1, "off": 0},
    "cells": {
      "3.9": {"tests": 7, "stamp": "3.9.25", "failed": true},
      "3.10": {"tests": 7, "stamp": "3.10.21", "failed": false},
      "3.11": {"tests": 7, "stamp": "3.11.2", "failed": false},
      "3.12": {"tests": 7, "stamp": "3.12.14", "failed": false},
      "3.13": {"tests": 7, "stamp": "3.13.15", "failed": false}
    }
  }
}
run: SUMMARY verdict=PASS mask_on=['fail', 'pass', 'pass', 'pass', 'pass'] mask_off=['pass', 'pass', 'pass', 'pass', 'pass'] tests_per_cell=7 exit_codes={'on': 1, 'off': 0}
run: failing cell(s): 3.9 (expected: exactly 3.9, the match-syntax SyntaxError)
run: killed and confirmed gone: 01a1406f-b4af-7b40-8309-582fb328e0fb
```

## Cleanup confirmation

Every run killed its sandbox and confirmed it was gone (`sbx list` no longer
contained the id) before `run.py` exited 0. Runs 1–4 created and destroyed
sandboxes `01a1404b-0ffe-7dd0-a5a0-261997592c96`,
`01a14054-61a6-7bc1-a3f9-9d26e21c9785`, `01a1405c-7608-79f3-afd5-db7bd8c592a7`,
`01a1406f-b4af-7b40-8309-582fb328e0fb` respectively; none remain in `sbx
list`. The fail-closed cleanup path was additionally proven with a mock `sbx`
shim: when `sbx kill` and `sbx list` exit non-zero (the reviewer's 503-blip
repro), `run.py` exits 1 and prints
`run: FAILED cleanup: sbx kill exit 1, sbx list exit 2; run sbx kill <id>`
instead of claiming success.

## Deviations

- `judge/setup.sh` measures 6.0–11.7 s across the four runs (the `sbx exec`
  round-trip plus the sha256-pinned uv download when the cache is cold).
- Interpreter patches are what uv fetched on 2026-10-15 (`3.11.2`, not the
  `3.11.16` an earlier draft claimed); `judge/VERSIONS.txt` records the
  measured set. The judge grades major.minor identity, per SPEC.md.
- `judge/grade.sh` wall time varies (24.5–35.8 s), hence the README's
  `~25-35 s` band; the verdict is identical every time.