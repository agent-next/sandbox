# RECEIPT — `cookbook/background-coding-agent/`

Real command output, pasted as produced. Both runs below were produced by
the committed code on this branch, in a Debian GNU/Linux 12 (bookworm)
sandbox (2 vCPU, ~4 GB RAM, Linux x86_64) at this repo's working tree.
Each run started from nothing: `$HOME/.local/share/measurectl-judge` (the
only thing `judge/setup.sh` installs) was removed first, so the wheels and
both venvs were re-created from scratch.

## Two fresh-setup runs side by side

| | RUN-A | RUN-B |
|---|---|---|
| `judge/setup.sh` | exit 0, 70 s (download + 2 venvs) | exit 0, 65 s |
| `judge/selftest.sh` | exit 0, 216 s | exit 0, 221 s |
| `judge/grade.sh examples/good/delivery.patch` | exit 0, 17 s | exit 0, 23 s |
| sha256 of every wheel | verified by `setup.sh` (`sha256-verified` ×6) | same, ×6 |
| ruff / pytest installed | 0.16.9 / 9.1.1 | 0.16.9 / 9.1.1 |
| kill rate | **11/11 = 100 %** | **11/11 = 100 %** |
| determinism (`--seed 1` twice) | byte-identical | byte-identical |
| verdict JSON | see below | identical (`diff` empty) |
| regression tests | 26 collected, 0 failed | 26 collected, 0 failed |
| acceptance tests | 23 collected, 0 failed | 23 collected, 0 failed |
| oracle cases | 3/3 agreed, 1e-9 rel | 3/3 agreed, 1e-9 rel |

`diff RUN-A_verdict.json RUN-B_verdict.json` → **no differences**.

### `bash judge/setup.sh` (fresh, RUN-A)

```text
setup: downloading pinned wheels into /home/user/.local/share/measurectl-judge
setup:   pluggy 1.6.0 downloaded and sha256-verified
setup:   iniconfig 2.3.1 downloaded and sha256-verified
setup:   packaging 26.3 downloaded and sha256-verified
setup:   pygments 2.21.0 downloaded and sha256-verified
setup:   pytest 9.1.1 downloaded and sha256-verified
setup:   ruff 0.16.9 downloaded and sha256-verified
setup: creating venvs
setup: tool versions
ruff 0.16.9
pytest 9.1.1
Python 3.12.15
setup: wrote .../judge/VERSIONS.txt
setup: done
[setup exit 0, 70 s]
```

`judge/VERSIONS.txt` (written on every install; byte-identical in RUN-A and
RUN-B):

```text
# background-coding-agent judge: versions installed by judge/setup.sh
# (Linux x86_64)
ruff 0.16.9
pytest 9.1.1
python3 3.12.15
```

### `bash judge/selftest.sh` (RUN-A)

```text
selftest: grading known-good .../examples/good/delivery.patch
selftest: known-good PASSED all gates
mutants: empty-patch/  expects gate patch: the patch is emptied
mutants: touches-tests/  expects gate integrity: the patch also edits a file under tests/
mutants: breaks-old-test/  expects gate regression: the running count is doubled, breaking an existing test
mutants: json-missing-field/  expects gate acceptance: the per-metric document loses its `max` field
mutants: startup-hook/  expects gate integrity: a planted sitecustomize.py is added (interpreter startup hook)
mutants: json-count-as-float/  expects gate acceptance: `count` is emitted as a float, not an integer
mutants: lint-unused-import/  expects gate lint: an unused import is added (ruff F401)
mutants: mean-sign-dropped/  expects gate oracle: the sign of `mean` is dropped; only the judge's seeded inputs carry negative values
mutants: mean-not-sum-over-count/  expects gate oracle: `sum` is rounded to 3 places, breaking the exact comparison
mutants: pr-omits-file/  expects gate pr: PR.md stops naming measurectl/jsonout.py
mutants: pr-no-test-plan/  expects gate pr: PR.md loses its test-plan heading
mutants: wrote 11 mutants to /tmp/.../mutants
selftest: killed    breaks-old-test (gate: regression)
selftest: killed    empty-patch (gate: patch)
selftest: killed    json-count-as-float (gate: acceptance)
selftest: killed    json-missing-field (gate: acceptance)
selftest: killed    lint-unused-import (gate: lint)
selftest: killed    mean-not-sum-over-count (gate: oracle)
selftest: killed    mean-sign-dropped (gate: oracle)
selftest: killed    pr-no-test-plan (gate: pr)
selftest: killed    pr-omits-file (gate: pr)
selftest: killed    startup-hook (gate: integrity)
selftest: killed    touches-tests (gate: integrity)
selftest: kill rate 11/11 = 100%
selftest: determinism OK (two --seed 1 runs byte-identical)
selftest: OK
[selftest exit 0, 216 s]
```

**Kill rate 11/11 = 100 %** (requirement ≥ 90 %, ≥ 5 known-bad). Every
gate has at least one mutant that dies on it: `patch`, `integrity` (×2),
`regression`, `acceptance` (×2), `lint`, `oracle` (×2), `pr` (×2).

### `bash judge/grade.sh examples/good/delivery.patch --json /tmp/v.json`

```json
{
  "patch": "examples/good/delivery.patch",
  "pr": "examples/good/PR.md",
  "seed": 20261015,
  "passed": true,
  "gates": {
    "patch":      { "passed": true, "files": 2, "added_lines": 47,
                    "removed_lines": 0, "hunks": 4, "repo_rooted": false },
    "integrity":  { "passed": true, "unsafe_paths": [],
                    "protected": "tests/ + tool config" },
    "regression": { "passed": true, "tests_collected": 26, "failed": 0,
                    "pytest": "9.1.1" },
    "acceptance": { "passed": true, "tests_collected": 23, "failed": 0,
                    "pytest": "9.1.1" },
    "lint":       { "passed": true, "findings": 0, "ruff": "0.16.9",
                    "config": "judge/ruff.toml" },
    "oracle":     { "passed": true,
                    "reference": "judge/reference.py (statistics.fsum)",
                    "tolerance": "1e-09 relative",
                    "cases": [ {"input": "sample.csv", "metrics": 4,
                                "total_count": 9, "agreed": true},
                               {"input": "synthetic-a.csv", "metrics": 3,
                                "total_count": 8, "agreed": true},
                               {"input": "synthetic-b.csv", "metrics": 3,
                                "total_count": 8, "agreed": true} ] },
    "pr":         { "passed": true, "chars": 1253, "summary_heading": true,
                    "test_plan_heading": true, "files_mentioned": 2 }
  }
}
[grade exit 0, 17 s]
```

The verbatim verdict JSON (with the `rule` strings the abridged form above
drops) is byte-identical between RUN-A and RUN-B.

## Criterion-by-criterion evidence

1. **Pinned, sha256-checked tools.** `judge/setup.sh` downloads six
   wheels, each verified with `sha256sum -c` against a hash that is also
   in `judge/requirements.txt` (installed with `pip --require-hashes`, so a
   swapped wheel cannot land). `judge/VERSIONS.txt` records what was
   actually installed. Nothing is fetched from `latest`; every pin was
   published more than two weeks before this demo merged (dates and
   licences in `SPEC.md`).
2. **Independent oracle.** `judge/reference.py` recomputes every statistic
   from the raw CSV with `csv` + `statistics.fsum`/`fmean` — a different
   parser and a different accumulation from the fixture's own loop — and
   the judge compares the emitted JSON to it field by field, plus the
   schema mask and the `min ≤ mean ≤ max` / `sum = count · mean`
   identities. The `mean-sign-dropped` and `mean-not-sum-over-count`
   mutants are killed by exactly this gate.
3. **Determinism.** `selftest.sh` runs `grade.sh --seed 1` twice and
   compares the verdict JSON byte-for-byte; the verdict has no wall-time
   field, so the two files are fully identical (`determinism OK` above).
4. **Two fresh-setup runs.** Side-by-side table above; both verdicts
   identical, nothing to explain.
5. **Judge strength.** Kill rate 100 % over 11 scripted single-edit
   mutants, one gate each. The `startup-hook` mutant (a planted
   `sitecustomize.py`, which `site` would import at interpreter startup
   because the checkout root is on `PYTHONPATH`) is refused by the
   integrity gate.
6. **`run.py`.** `python3 -m py_compile run.py` → OK; `--help` renders.
   This sandbox cannot create cloud sandboxes, so the exact in-sandbox
   command sequence `run.py` sends to `sbx exec` was executed directly
   here — `bash judge/setup.sh` (exit 0), `bash judge/selftest.sh` (exit 0,
   100 %), `bash judge/grade.sh examples/good/delivery.patch --pr
   examples/good/PR.md --json /tmp/inseq.json` (exit 0, `"passed": true`) —
   and the lead runs `run.py` end to end.

## Deviations

- **`REPRODUCE.md` is a placeholder.** The standard wants an independent
  reproduction by a different agent; the builder cannot satisfy that by
  reproducing its own work, so the file records the exact steps and is
  left for a second agent before merge.
- **`run.py` was not run end to end.** No `sbx` CLI and no API key in this
  authoring sandbox; its in-sandbox command sequence was run directly
  instead (above). The lead runs it end to end.
- **The acceptance suite is hidden in the repo sense, not cryptographically.**
  It lives at `judge/acceptance/test_acceptance.py` in the same checkout
  the agent works in, so an agent that ignores the "do not edit `judge/`"
  instruction can read it. The demo models a background agent that is
  handed `fixture/` and asked for a patch; the judge additionally refuses
  any patch that touches `tests/` or the tool config, and the oracle
  grades on seeded inputs the acceptance file does not contain. A
  production version would keep the suite out of the agent's checkout
  entirely.
- **The fixture is vendored, not a third-party project.** No external
  source is cited because none is used; `measurectl` is original to this
  demo (see README "The fixture").
- **Wall times are network-bound.** Fresh `setup.sh` ranged 48–93 s across
  the runs in this session depending on PyPI latency (65–70 s in the two
  runs above); the idempotent re-run is ~5 s. Grading one delivery is
  17–23 s. The self-test grades 14 deliveries (good + 11 mutants + two
  determinism re-runs).
- **A repo-rooted patch is accepted by re-rooting, not by grading from the
  repo root.** A patch whose paths carry the
  `cookbook/background-coding-agent/fixture/` prefix is rewritten onto the
  fixture root before `git apply`; `judge/grade.sh` reports
  `"repo_rooted": true`. This was verified by hand but is not exercised by
  a mutant.
