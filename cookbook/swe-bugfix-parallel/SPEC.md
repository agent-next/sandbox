# swe-bugfix-parallel: fix six real bugs in a pinned library, judged by its own tests

## Goal

An agent fixes six real, independently-verified bugs in a pinned commit of a
public, permissively-licensed Python library (`more-itertools`, BSD-3-Clause),
producing one `patches/<task>.diff` per task. A judge it cannot fool applies
each patch to a clean checkout at the task's pinned commit, runs the upstream
test suite, and decides — with numeric rules — whether the bug is fixed
without breaking anything that already worked.

The point of using a sandbox: the agent clones the pinned library, reads the
failing tests, writes a minimal fix, and iterates against the judge in an
isolated, disposable environment. Nothing it does can touch the real machine,
and the judge is unmodified by anything the artifact does.

This is the SWE-bench pattern (FAIL_TO_PASS / PASS_TO_PASS) run on real
upstream bug fixes, with the sandbox providing the disposable CPU-light
environment the pattern needs.

## Non-goals (explicitly out of scope)

- No GPU, no large data, no network services, no web UI.
- No contribution to the upstream library itself; patches are demo artifacts.
- No grading of code style, commit messages, or patch formatting beyond the
  mechanical rules below.
- No parallelism *within* a task; the "parallel" in the name refers to the
  six independent tasks a user may fan out across sandboxes (see run.py).

## Artifact

The agent produces six files, `patches/<task>.diff`, one per task. Each is a
unified diff that applies cleanly with `git apply` to a clean checkout of the
upstream library at that task's pinned commit, and that changes only files
under `more_itertools/` (the library source). A patch that touches
`tests/`, `docs/`, or any other path is rejected before grading.

The six tasks, their pinned commits, and the upstream fix commits they
revert (cited, with licence):

| task | pinned commit (base) | fix commit reverted | what breaks |
|---|---|---|---|
| `ichunked-zero-n` | `790bb0bb2c03e7a07282e5f16f4b1fde35b8fcf5` | `f89d7a3331ba6b5421273e556c0a738e3dd1dd35` | `ichunked(iterable, 0)` and negative `n` raise instead of matching `chunked` |
| `bucket-falsey-validator` | `1ea82a711c69f590054987b5cb194157f8ce8ac4` | `67fcf640477c78605580f5ee703a54c73c1e7a8a` | `bucket` with a falsey-but-valid callable validator silently accepts every key |
| `sliced-negative-n` | `ed86a1528aa015f219f8d3385ea2ebd3f63a5212` | `958990e22c4ab6daf434d89cf2b86d7a4a7a9e3c` | `sliced(seq, -1)` returns the whole sequence instead of raising |
| `one-only-falsy-exception` | `9ed3dbb0ae527230cd156d91d0af305478558fba` | `def2dabea858b6ecb84ee0c52e6e07929f2c409c` | `one()`/`only()` drop a falsy user-supplied exception |
| `interleave-evenly-empty` | `5d946b3590bfe92f1465c1b9b9830dd434745c84` | `f51a53bfd2fe9504063a33ef5f4a73e30d82d0e2` | `interleave_evenly()` with no iterables raises instead of returning an empty iterator |
| `numeric-range-reversed-empty` | `247e15b3a489d5805375c95dfa79486c9bd0eb1b` | `edb3346f835ca917efbfda5e2d6664ab952da369` | `reversed(numeric_range(0))` raises instead of returning an empty iterator |

Upstream: <https://github.com/more-itertools/more-itertools>, BSD-3-Clause
licence. Each task's base commit is the parent of the cited fix commit, so
the base checkout contains the bug and the fix commit's tests fail on it.

## Judge gates (numeric pass rules)

The judge (`judge/grade.sh` → `judge/grade.py`) runs, for each of the six
tasks, a deterministic pipeline against a clean checkout of the upstream
library at that task's pinned commit:

1. **Patch applies** — `git apply --check` succeeds on a pristine checkout.
2. **Patch is source-only** — the diff touches only paths under
   `more_itertools/`; a patch touching `tests/`, `docs/`, or any other path
   fails this gate.
3. **FAIL_TO_PASS** — the specific upstream tests that fail on the base
   checkout (listed in `tasks.json`) all pass after the patch. The count of
   these tests that pass must equal the total (6/6 tasks, each 100 %).
4. **PASS_TO_PASS** — a fixed list of upstream tests that pass on the base
   checkout (listed in `tasks.json`) all still pass after the patch. The
   count must equal the total (no regressions).
5. **Judge integrity** — the checksum of `judge/` is unchanged after
   grading.

A task is **resolved** iff gates 1–4 all pass. The demo verdict is **pass**
iff all six tasks are resolved (6/6). The self-test
(`judge/selftest.sh`) proves the judge can fail: the known-good artifact
(all six reference patches) must pass, and each of the known-bad mutants must
fail at least one gate. Required kill rate ≥ 90 %.

## Acceptance oracle

The judge fails (non-zero exit) if any gate fails. The self-test is mandatory
and must show the judge failing on bad inputs. The acceptance oracle is the
upstream project's own test suite (`pytest`), which is an independent oracle:
the tests were written by the upstream maintainers, not by this demo, and
they encode the correct behaviour of each function.

## Tools (pinned by the judge)

| tool | what | how pinned |
|---|---|---|
| Python 3.10+ | runs the judge and the upstream test suite | system `python3` (Debian bookworm 3.11) |
| pytest 8.4.2 | test runner | `judge/requirements.txt` (exact version, hash-pinned wheel) |
| git | clones the upstream library, applies patches | Debian bookworm package |
| more-itertools @ base commit | the library under test | `git clone` + `git checkout <sha>`; the sha is pinned in `tasks.json` |

No tool is fetched with `latest`. The upstream library is cloned at an exact
commit sha recorded in `tasks.json`. `judge/VERSIONS.txt` records what
`setup.sh` actually installed.

## Reproducibility

- **Pinned everything:** exact pytest version (hash-pinned), exact upstream
  commit shas in `tasks.json`.
- **Deterministic:** the test suite is deterministic (no randomness in the
  six tasks' tests). `grade.sh` run twice gives byte-identical verdict JSON
  (excluding wall-time fields under a `timing` key). `selftest.sh` checks
  this.
- **Fresh-sandbox reproduction:** `RECEIPT.md` has two runs from two fresh
  sandboxes (setup from nothing), with verdicts and key numbers side by side.
- **Independent reproduction:** before merge, a different agent follows only
  `README.md` in a fresh sandbox and records its numbers in `REPRODUCE.md`.

## Deviations from the brief (lead's ask)

The brief suggested `patches/<task>.diff` per task with the judge applying
each to a clean checkout. This is exactly what is implemented. The brief's
mutant list (empty patch, patch deleting the failing test, patch breaking a
PASS_TO_PASS test, patch to wrong file, syntax-error patch) is implemented
as `judge/mutants.py`, which generates single-edit mutants of the known-good
artifact.
