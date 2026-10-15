# SPEC — `cookbook/skill-ab-bench/`

Does an agent skill actually help? An agent answers 16 file-parsing questions
in a disposable agent-next sandbox. The questions are answered twice — once with
a skill package available beside the working copy, once without — each
(`skill`, `task`) pair in its own sandbox, and a bootstrap confidence interval on
the pass-rate *delta* decides. It is an A/B test for agent skills, with a real
significance bar and a placebo control that stops the bench from crowning a
skill that does nothing.

## Goal

Grade a skill package honestly:

- the demo's own bench (the *harness*, `judge/bench.py`) runs a 2-arm × 16-task
  experiment end to end and writes one experiment record;
- the judge (`judge/grade.sh` → `judge/grade.py`) grades that record: it
  re-runs every task verifier itself, recomputes the pass counts, computes a
  **bootstrap CI on the delta** (pinned seed) and applies the numeric gates
  below;
- the gates are chosen so that a harness that *cheats* — reuses one arm's
  answers, fabricates verifier results, drops failing tasks, or reports a
  cannabis-free delta — cannot pass.

## Non-goals

- No agent is driven and no LLM is called. The two "arms" are *arm policies*:
  scripts that answer the tasks, one of which consults the skill package and
  one of which does not. Everything is deterministic; the demo is about the
  *bench*, its interval, its placebo control and its judge — not about
  measuring a real model's skill sensitivity.
- No network: the skill package and the task corpus are generated locally by
  `judge/gen_inputs.py` from a pinned recipe.
- No claim about *why* a delta is what it is. The demo reports whether the
  measured delta clears the bar, not a causal model.
- No parallelism requirement: the bench is single-threaded on purpose (see
  Size below).

## The artifact

One directory (the argument of `judge/grade.sh <dir>`), e.g.
`examples/good/`, containing **exactly one** experiment record:

- `results.json` — the bench's output, a JSON object with the keys listed in
  [Experiment record](#experiment-record) below.

Nothing else in the directory is read. The artifact must be produced by
`judge/bench.py` inside the run (`run.py` and the README both do: run
`bench.py`, then grade the directory it wrote).

### Experiment record

```text
{
  "schema":   "skill-ab-bench/1",
  "arms":     {"skill": "<label>", "noskill": "<label>", "placebo": "<label>"},
  "seed":     <int>,              # pinned bench seed
  "tasks":    [ <16 task records> ]
}
```

Each task record:

```text
{
  "task_id":     "kv01" … "kv16",   # exactly the 16 ids in judge/tasks.json
  "skill":       {"passed": <bool>, "answer": <str>, "ms": <number>,
                  "policy": "<label>"},
  "noskill":     {"passed": <bool>, "answer": <str>, "ms": <number>,
                  "policy": "<label>"},
  "placebo_flag": <bool>            # true iff "placebo" key present as well
}
```

`placebo` (same shape as `skill`) appears only when `placebo_flag` is true.
Every field is required; the record is rejected otherwise.

## Judge gates

`judge/grade.sh <dir> [--seed N] [--json out.json] [--arms skill,noskill[,
placebo]] [--bootstrap N]`

All gates are numeric and deterministic. **Exit 0 only if every gate passes.**
Gates run in order and the first failure stops grading, so a record that is
structurally wrong never reaches the statistics.

| gate | rule |
|---|---|
| **G1 record shape** | `schema` is `skill-ab-bench/1`; `seed` is an int; `tasks` has exactly 16 entries, ids unique and exactly the ids in `judge/tasks.json`; every entry has `skill` and `noskill` with `passed` bool, `answer` str, `ms` a finite number ≥ 0, `policy` str; `placebo` present exactly when `placebo_flag` is true and `policy` matches the arm label. |
| **G2 arm isolation** | The two arm policies differ, and **no task record shares an answer string between the `skill` and `noskill` arms when the verdicts differ** — the same answer with different pass verdicts across arms means at least one verdict is fabricated. Verdict-equality must hold whenever answers are equal. |
| **G3 verifier replay (independent oracle)** | For each task, the judge looks up the task's own verifier (below), runs it on the recorded `answer` string, and requires its verdict to **equal** the recorded `passed`. Any mismatch fails the grade. The judge never trusts a verdict it did not recompute. |
| **G4 task identifiability (oracle)** | For each task, at least the *known-good reference answer* class passes **and** every single-edit known-bad reference answer fails. The judge holds the independent reference answers (`judge/reference.json`, with the exact expected output bytes) and recomputes its own verifier verdicts on them, so a task whose verifier cannot tell good from bad fails the grade — the bench cannot be saved by a verifier that passes everything. |
| **G5 power / sample size** | With `n_skill`, `n_noskill` = the two arms' pass counts over 16 tasks, and `p̂ = (n_skill + n_noskill)/32`, the two-sided exact binomial test (Fisher, computed with the hypergeometric pmf in stdlib `math`, no scipy) must reach **p < 0.05**. A bench that calls a 3-of-16 vs 2-of-16 difference significant does not pass. |
| **G6 effect size** | delta = (n_skill − n_noskill)/16 in pass-rate points must be **≥ 25.0 pts** and the bootstrap CI (two-sided, percentile method, **10 000 resamples**, seeded by `--seed` default `20261014`, resampling *tasks* independently within each arm) must have its **lower bound > 0**. |
| **G7 placebo control** | When a `placebo` arm is present (the good record has one): delta_placebo = (n_noskill − n_placebo)/16 must have a bootstrap CI **containing 0**, and its absolute delta must be **< 10.0 pts** in absolute value. A bench that hands the win to a placebo fails. |
| **G8 determinism / integrity** | Two grade runs with the same seed produce byte-identical verdict JSON (checked by `judge/selftest.sh`, not by the grade itself); the artifact directory is copied to a temp dir before grading and `judge/` is checksummed before and after. |

The judge prints, for every gate, the numbers it used (pass counts, delta,
CI bounds, Fisher p, per-task replay results) and the verdict is a single JSON
object on stdout.

## Acceptance oracle (independent of "the tool ran")

1. **Independent verifiers, keyed by task id.** The task corpus is a set of
   *pinned, seeded inputs* (generated by `judge/gen_inputs.py` from a fixed
   recipe described in SPEC; no third-party data, so no URL/licence is owed).
   Each task ships a small **oracle** — a closed-form expected value computed
   from the input alone, e.g. the exact expected `key=value` output of a config
   snippet, the exact match spans of a regex, the exact CSV field counts. The
   judge recomputes the oracle in-process (`judge/verify.py`) and compares it to
   the recorded answer. A harness's pass verdict is only accepted if the
   oracle agrees; a task the judge cannot verify analytically fails the grade
   (fail closed).
2. **The oracle is two-sided.** `judge/reference.json` holds the reference
   answers the judge itself computes, plus the expected verdict per arm. G3
   catches a harness that flips verdicts; G4 catches a harness whose verifiers
   are so loose that a wrong answer passes.
3. **Significance, not rate.** G5 requires p < 0.05 by an exact test the judge
   computes from the counts (Fisher's exact test via the hypergeometric pmf),
   and G6 requires the *effect* (delta ≥ 25 pts, CI excludes 0) — so a good
   pass rate alone is not a pass.
4. **Placebo control as a gate.** G7 requires that swapping the real skill for
   a README-only placebo does **not** produce a significant delta. This is the
   gate that makes the bench a bench rather than a banner.
5. **CI reproducibility.** The bootstrap is seeded from `--seed`; the same seed
   always yields the same bounds, verified byte-for-byte by the self-test.

## The skill under test and the placebo

The demo grades a bench of a **regular-expression cookbook skill** (the skill
mentioned in the demo brief): a `SKILL.md` that teaches backreference-safe
alternation, anchors, greedy-vs-lazy choices and case-insensitive matching, plus
a handful of tested snippets. The placebo is the same skill directory with the
technique replaced by a README that adds no technique. Both packages are
generated by `judge/gen_skill.py` into the bench's scratch tree; both are pinned
content in this repo (no network, no licence owed).

- `examples/good/skill/` — the real skill package (checked in, so the demo runs
  offline).
- `examples/bad/` and `judge/mutants.py` — ≥ 5 single-edit mutants of the good
  experiment record, each of which must fail ≥ 1 gate (see self-test).

## Self-test (`judge/selftest.sh`)

- The known-good record passes every gate.
- Every scripted mutant fails at least one gate; ≥ 5 mutants, generated by
  `judge/mutants.py` (single edits of `examples/good/results.json`), covering at
  least: a fabricated verdict (G3), a shared answer across arms (G2), a dropped
  task (G1), a fake bootstrap bound (G6), a significant placebo (G7), a
  too-small sample (G5).
- Kill rate ≥ 90 % printed; exit non-zero otherwise.
- Determinism: two grade runs with the same seed are byte-identical.

## Judge-integrity rule

The artifact under test is copied to a temp dir before grading; the judge
compares the `sha256` of its own `judge/` tree before and after and fails closed
if anything changed. The artifact never executes judge code.

## Out of scope for the judge

- Whether the skill is *good pedagogy*. Only the numbers are graded.
- Any claim about a real agent's behaviour; the arms are policies.
- Optimality of the arm policies: the skill policy is written to be a little
  cleverer than the naive one, not to be the best possible parser.

## Size

16 tasks × 3 arms × one deterministic run = 48 verifications per experiment,
each milliseconds — single-threaded on 2 vCPU / ~3 GB RAM, a full bench is
seconds and a full grade is under a second.
