# SPEC — `cookbook/llm-eval-harness/`

An agent works on a real LLM-evaluation engineering problem inside a disposable
agent-next sandbox: build a code-generation eval harness that executes model
completions against MBPP test cases in isolated subprocesses and computes
pass@1 and the unbiased pass@k estimator, where a judge it cannot fool
(a reference oracle + cross-check on the arithmetic) decides whether the
numbers are right.

## Goal

Given a fixed benchmark of 30 MBPP problems (pinned dataset, sha256-checked)
and a set of code completions (`samples.jsonl`, one JSON object per line with
fields `task_id` and `solution`), build `eval.py` that:

1. Executes each solution in an isolated subprocess with a wall-clock timeout.
2. Counts a solution as passing for a task if every one of that task's MBPP
   test assertions passes (after all setup code has run).
3. Computes pass@1 = (fraction of tasks with ≥1 passing sample) and the
   unbiased pass@k estimator:

   pass@k = 1 − C(n−c, k) / C(n, k)

   where n = total samples per task and c = number of correct samples for
   that task (Chen et al., 2021, "Evaluating Large Language Models Trained on
   Code", arXiv:2107.03374).  pass@1 is computed with the same formula at k=1.

## Non-goals

- Running any actual LLM inference (the completions are provided, not generated).
- Grading solution *quality* beyond test-pass (style, efficiency, elegance).
- Any network access from inside the evaluation subprocesses.
- MBPP tasks that use imports beyond the Python standard library.

## Artifact

The agent produces two files (graded by `judge/grade.sh <samples.jsonl> <eval.py>`):

1. **`samples.jsonl`** — one JSON object per line. Each line has:
   - `task_id`: integer matching a problem in the pinned dataset.
   - `solution`: a string containing the full Python source for that task
     (may be multi-line; the string is written verbatim to a temp `.py` file).
   Exactly one sample per task is required for the artifact to be gradeable
   (n=1 per task; the judge enforces this). Solutions must be Python source
   that either defines the required function(s) or is a self-contained script.

2. **`eval.py`** — a Python 3.10+ stdlib-only script that:
   - Reads a path to `samples.jsonl` and a path to the pinned dataset
     `data/mbpp_subset.jsonl` (passed as command-line arguments:
     `python3 eval.py <samples.jsonl> <dataset.jsonl>`).
   - Executes each sample against its task's tests in a `subprocess` with a
     per-sample wall-clock timeout (default 10 s).
   - Prints exactly two lines to stdout: `pass@1: <float>` and `pass@k: <float>`
     where k = total_samples / num_tasks (the estimator uses the actual n and c
     per task, averaged over tasks).
   - Exit code 0 on success; non-zero on unreadable input, malformed JSON, or
     a sample that cannot be executed at all (before timeout).

## Judge gates (`judge/grade.sh <samples.jsonl> <eval.py> [--seed N] [--json out.json]`)

All gates are numeric and deterministic. Exit 0 only if every gate passes.

- **G1 format**: `samples.jsonl` is valid JSONL; every line has integer
  `task_id` and string `solution`; every `task_id` exists in the pinned
  dataset; exactly one sample per task. `eval.py` is syntactically valid
  Python (`py_compile`).
- **G2 execution**: for every (task_id, sample) pair, the judge runs the
  solution in an isolated subprocess (fresh `python3` process, `cwd` = temp
  dir, 10 s wall-clock timeout, no network via `socket` monkey-patch guard
  unavailable — solutions are stdlib-only by dataset construction). A sample
  passes its task if all that task's MBPP `test_list` assertions evaluate
  without error after exec'ing the solution source. The judge records
  per-task pass counts `c_task` and total `n`.
- **G3 eval.py runs**: `eval.py` runs to completion (exit 0, ≤ 120 s) and
  prints its own pass@1 and pass@k on stdout.
- **G4 numbers match**: the judge recomputes pass@1 and pass@k independently
  using the exact estimator from the Goal above over its own per-task counts
  and requires |eval.py's value − judge's value| ≤ **1e-9** for both metrics.
- **G5 timeout counts as failure**: the judge inserts one deliberately
  non-terminating sample (infinite loop) into a copy of the dataset and
  confirms `eval.py` still completes with exit 0 and reports that sample as
  failing (its pass@1 must drop by at least 1/num_tasks vs the original run).
  This is checked by the judge, not by a gate on the artifact directly: the
  gate passes if `eval.py` handles the timeout correctly.

Violating any gate fails with the offending numbers printed.

## Acceptance oracle (independent of "it ran")

1. **Analytic / closed-form reference**: the judge recomputes both metrics
   from first principles using Python's `fractions.Fraction` exact arithmetic
   for the combinatorial terms C(n−c,k)/C(n,k), so the comparison does not
   rely on floating-point agreement with `eval.py`'s own code path. The
   judge also cross-checks its pass@1 against a direct recomputation from
   per-task counts (sum of indicator(c_task ≥ 1) / num_tasks).
2. **Convergence / self-consistency**: when every sample passes (the
   known-good example), both metrics must be exactly 1.0; when no sample
   passes, both must be exactly 0.0. The judge asserts these boundary
   conditions internally before trusting its own numbers.
3. **Independent re-execution**: the judge runs each sample itself (G2) and
   compares its own per-task pass/fail decisions against what `eval.py`
   implicitly reports through the two printed numbers. Any sample that
   `eval.py` counts as passing but the judge's own execution shows failing
   (or vice versa) causes G4 to fail with the discrepancy printed.

## Self-test (`judge/selftest.sh`)

- The known-good artifact passes all gates.
- ≥ 5 known-bad single-edit mutants of the good `eval.py` each fail ≥ 1 gate;
  mutants generated by `judge/mutants.py` (one edit each).
- Kill rate ≥ 90 % printed by the self-test; exit non-zero otherwise.
- Determinism: two `grade.sh` runs with the same seed produce byte-identical
  verdict JSON (excluding the `timing` key).

## Judge-integrity rule

The artifact under test is copied to a temp dir before grading; the judge
compares sha256 of its own `judge/` tree before and after every grade and
fails closed if anything changed.

## Out of scope for the judge

- Whether solutions are *idiomatic* or *efficient*.
- The content of `samples.jsonl` beyond the schema above (any task_ids from
  the pinned dataset, any valid Python source).

## Tools (pinned by `judge/setup.sh`)

- Python 3.10+ (stdlib only) — already present on Debian bookworm.
- No additional packages required; the judge uses `subprocess`, `json`,
  `math`, `fractions`, `tempfile`, `pathlib`, `hashlib` from the stdlib.
