# SPEC — `cookbook/skill-ab-bench/`

Does an agent skill actually help? Sixteen file-parsing questions are answered
three times over — once with a skill package on the desk, once with nothing,
once with a placebo that only adds a README — and a bootstrap confidence
interval on the pass-rate *delta*, plus an exact test, decides. It is an A/B
test for agent skills with a real significance bar and a placebo control that
stops the bench from crowning a skill that does nothing.

Each (arm, task) pair is answered in its own fresh interpreter with its own
working directory, so no pair can see another's work; `run.py` runs the whole
experiment inside one disposable agent-next sandbox, which is the outer
boundary that pins the toolchain and is destroyed afterwards. One sandbox per
pair (48 of them) would re-clone this repository 48 times to re-run 48
deterministic policy scripts that share no state, so the demo spends its
sandbox on the boundary and its isolation on the process.

## Goal

Grade a skill package honestly:

- the demo's own bench (the *harness*, `judge/bench.py`) runs a 3-arm × 16-task
  experiment end to end and writes one experiment record;
- the judge (`judge/grade.sh` → `judge/grade.py`) grades that record: it
  re-runs every task verifier itself, recomputes the pass counts, computes a
  **bootstrap CI on the delta** (pinned seed) and applies the numeric gates
  below;
- the gates are chosen so that a harness that *cheats* — reuses one arm's
  answers, fabricates verifier results, drops failing tasks, or reports a
  delta the counts do not support — cannot pass.

## Non-goals

- No agent is driven and no LLM is called. The "arms" are *arm policies*:
  scripts that answer the tasks, one of which consults the skill package and
  one of which does not. Everything is deterministic; the demo is about the
  *bench*, its interval, its placebo control and its judge — not about
  measuring a real model's skill sensitivity.
- No network at bench time: the task corpus is generated locally by
  `judge/gen_inputs.py` from a pinned recipe, and the two skill packages are
  built by `judge/gen_skill.py` from the checked-in `examples/good/skill/`.
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
`bench.py`, then grade the directory it wrote). The bench builds the skill
packages in a temp directory, never inside the artifact, so `results.json` is
the only file there.

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
  "task_id":     "kv01" … "re08",   # exactly the 16 ids in judge/tasks.json
  "skill":       {"passed": <bool>, "answer": <str>, "ms": <number>,
                  "policy": "<label>"},
  "noskill":     {"passed": <bool>, "answer": <str>, "ms": <number>,
                  "policy": "<label>"},
  "placebo_flag": <bool>            # true iff "placebo" key present as well
}
```

`placebo` (same shape as `skill`) appears only when `placebo_flag` is true.
Every field is required; the record is rejected otherwise. Each arm's `policy`
must equal the label `arms` gives that arm, so a record cannot relabel the
arms it ran.

## Judge gates

`judge/grade.sh <dir> [--seed N] [--json out.json] [--arms skill,noskill[,
placebo]] [--bootstrap N]`

All gates are numeric and deterministic. **Exit 0 only if every gate passes.**

| gate | rule |
|---|---|
| **G1 record shape** | `schema` is `skill-ab-bench/1`; `seed` is an int; `tasks` has exactly 16 entries, ids unique and exactly the ids in `judge/tasks.json`; every entry has `skill` and `noskill` with `passed` bool, `answer` str, `ms` a finite number ≥ 0, `policy` str; `placebo` present exactly when `placebo_flag` is true and `policy` matches the arm label. |
| **G2 arm isolation** | The two arm policies differ, and **no task record shares an answer string between the `skill` and `noskill` arms when the verdicts differ** — the same answer with different pass verdicts across arms means at least one verdict is fabricated. Verdict-equality must hold whenever answers are equal. |
| **G3 verifier replay (independent oracle)** | For each task, the judge looks up the task's own verifier (below), runs it on the recorded `answer` string, and requires its verdict to **equal** the recorded `passed`. Any mismatch fails the grade. The judge never trusts a verdict it did not recompute. |
| **G4 task identifiability (oracle)** | For each task, at least the *known-good reference answer* class passes **and** every single-edit known-bad reference answer fails. The judge holds the independent reference answers (`judge/reference.json`, with the exact expected output bytes) and recomputes its own verifier verdicts on them, so a task whose verifier cannot tell good from bad fails the grade — the bench cannot be saved by a verifier that passes everything. |
| **G5 power / sample size** | With `n_skill`, `n_noskill` = the two arms' pass counts over the 16 tasks, the two-sided Fisher exact test on the 2×2 table `[[n_skill, 16 − n_skill], [n_noskill, 16 − n_noskill]]` (computed from the hypergeometric pmf in stdlib `math`, no scipy) must reach **p < 0.05**. A bench that calls a 16/16 vs 12/16 difference significant does not pass (p = 0.101). |
| **G6 effect size** | delta = (n_skill − n_noskill)/16 in pass-rate points must be **≥ 25.0 pts** and the bootstrap CI (two-sided, percentile method, **10 000 resamples**, seeded by `--seed` default `20261014`, resampling *tasks* independently within each arm) must have its **lower bound > 0**. |
| **G7 placebo control** | When a `placebo` arm is present (the good record has one): delta_placebo = (n_noskill − n_placebo)/16 must have a bootstrap CI **containing 0**, and its absolute delta must be **< 10.0 pts** in absolute value. A bench that hands the win to a placebo fails. |
| **G8 judge integrity** | The artifact directory is copied to a temp dir before grading, and `judge/` is checksummed (every file, by path and content) before and after: if anything moved, the grade fails closed. Determinism is not checked here — two runs of the same seed are compared byte-for-byte by `judge/selftest.sh`, which exits non-zero if they differ. |
| **G9 arm fidelity** | For every task, each arm's recorded `answer` must equal the answer the corpus defines for that arm: the `skill` arm's answer must equal the reference `expected`, the `noskill` arm's must equal the corpus's pinned `naive_answer`, and the `placebo` arm's must equal the placebo policy's output. G2 and G3 check the record against *itself*; this gate checks it against the corpus, so a harness that fabricates an arm out of answers the real policy never gives cannot pass. |

G8 always runs, even when an earlier gate stopped the grade, so a verdict
always carries the integrity result. The other eight run in order and the
first failure stops grading, so a record that is structurally wrong never
reaches the statistics.

The judge prints, for every gate, the numbers it used (pass counts, delta,
CI bounds, Fisher p, per-task replay results) and the verdict is a single JSON
object on stdout.

## Acceptance oracle (independent of "the tool ran")

1. **Independent verifiers, keyed by task id.** The task corpus is a set of
   *pinned inputs* (generated by `judge/gen_inputs.py` from a fixed recipe
   described in SPEC; no third-party data, so no URL/licence is owed — the
   inputs are short config snippets and log lines written for this demo).
   Each task ships a small **oracle** — a closed-form expected value computed
   from the input alone: the exact `key=value` a config snippet yields once
   sections, case and comments are read correctly, the exact port a greedy
   pattern swallows, the exact quoted string behind an escaped quote. The
   judge recomputes the oracle in-process (`judge/verify.py`, written as an
   explicit character scan, deliberately a different method from
   `gen_inputs.py`'s) and compares it to the recorded answer. A harness's pass
   verdict is only accepted if the oracle agrees; a task the judge cannot
   verify analytically fails the grade (fail closed).
2. **The oracle is two-sided.** `judge/reference.json` holds the reference
   answer per task, and every single-edit near-miss of it (delete a character,
   add whitespace, change case, swap two characters, change a digit). The
   judge checks that its own oracle still produces that reference answer (so
   the file cannot drift), that the task's verifier accepts it, and that the
   verifier rejects **every** near-miss. G3 catches a harness that flips
   verdicts; G4 catches a harness whose verifiers are so loose that a wrong
   answer passes.
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

The demo grades a bench of a **regular-expression cookbook skill**: a
`SKILL.md` that teaches section-scoped config lookups, case-sensitive keys,
escape-aware quotes, anchored matches (greedy vs. what the pattern should
actually stop at), word boundaries and comment stripping, plus
`reference.py` — the technique table those habits turn into, ten short
functions, one per task family.

The three desks are built by `judge/gen_skill.py` from one checked-in
directory, so they differ in exactly one way — what is on the desk:

| arm | desk |
|---|---|
| `skill` | `examples/good/skill/` (`SKILL.md` + `reference.py`), copied byte for byte |
| `noskill` | an **empty** directory; `arm_runner.py` refuses to answer if it is not empty |
| `placebo` | the same package with the two technique files replaced by a `README.md` whose one rule ("skip commented-out lines") is a plausible tip that changes exactly one task's answer |

All three are pinned content in this repo (no network, no licence owed).
`examples/good/skill/` is the real package, checked in so the demo runs
offline.

The corpus split is a pinned fact of the recipe, not a tuning knob: 4 tasks
both arms answer correctly and 12 where only the skill arm does, so the
measured delta is 16/16 vs 4/16 = **75.0 pass-rate points**, and the placebo
arm lands at 5/16.

## Self-test (`judge/selftest.sh`)

- The known-good record passes every gate.
- Every scripted mutant fails at least one gate, and — where the mutant names
  one — fails **that** gate. `judge/mutants.py` writes ≥ 8 of them:

  | mutant | must die at |
  |---|---|
  | a fabricated verdict (a hard task's no-skill verdict flipped to passed) | G3 |
  | the no-skill arm given the skill arm's answer, verdict left wrong | G2 |
  | a dropped task record | G1 |
  | the two arms reported the wrong way round (every answer and verdict genuine, delta −75 pts) | G6 |
  | a marginal 16/16 vs 12/16 win (a real 25 pt gap, Fisher p = 0.101) | G5 |
  | a placebo arm that inherits four skill answers (a placebo that "works") | G7 |
  | the placebo arm relabelled with the skill arm's policy name | G1 |
  | the no-skill arm's answers replaced with fabricated strings the real policy never gives (verdicts honest, G2 and G3 blind) | G9 |
  | a copy of `judge/` with a drifted reference answer | G4 |
  | a copy of `judge/` with a task's known-bad answers removed | G4 |
  | a copy of `judge/` with a task whose oracle cannot be computed | G3 |

  The last three are graded against the **good** artifact with a mutated
  judge: they prove the judge fails closed rather than that the record is bad.
- The statistics engine is tested against published values before anything is
  graded (`judge/tests/test_stats.py`: Fisher's tea-tasting p = 0.4857…, the
  `[[1,9],[11,3]]` worked example, a hand-derived bootstrap bound), and the
  corpus is tested against the arm policies that answer it
  (`judge/tests/test_corpus.py`: the skill policy reproduces the oracle on all
  16 tasks, the no-skill policy reproduces every pinned `naive_answer`, the
  difficulty flags match the verdicts, and the placebo differs from the
  no-skill arm on exactly one task).
- Kill rate ≥ 90 % printed; exit non-zero otherwise.
- Determinism: two grade runs with the same seed produce byte-identical
  verdict JSON (excluding the `timing` key), and a *different* seed must move
  the CI — otherwise `--seed` would be decorative.

## Judge-integrity rule

The artifact under test is copied to a temp dir before grading; the judge
compares the `sha256` of its own `judge/` tree before and after and fails closed
if anything changed. The artifact never executes judge code.

## Out of scope for the judge

- Whether the skill is *good pedagogy*. Only the numbers are graded.
- Any claim about a real agent's behaviour; the arms are policies.
- Optimality of the arm policies: the skill policy is written to be a little
  cleverer than the naive one, not to be the best possible parser.

## Layout

| path | what |
|---|---|
| `judge/gen_inputs.py` | the pinned task corpus → `judge/tasks.json` (`--check` for staleness) |
| `judge/verify.py` | the independent oracle: expected answer per task, by character scan |
| `judge/gen_reference.py` | reference answers + single-edit near-misses → `judge/reference.json` |
| `judge/arms.py` | the three arm policies |
| `judge/arm_runner.py` | answers one (arm, task) pair in a fresh process |
| `judge/bench.py` | runs all 48 pairs → the experiment record |
| `judge/stats.py` | Fisher's exact test + the seeded bootstrap CI |
| `judge/grade.py` / `grade.sh` | the gates; one JSON verdict on stdout |
| `judge/mutants.py` | the known-bad records and the mutated judges |
| `judge/tests/test_stats.py` | the statistics engine vs. published values |
| `judge/tests/test_corpus.py` | the corpus vs. the arm policies that answer it |
| `judge/gen_skill.py` | builds the three desks (skill, empty, placebo) |
| `examples/good/` | the known-good experiment record (produced by `judge/bench.py`) |
| `examples/good/skill/` | the skill package under test |
| `run.py` | the one-command run |

## Size

16 tasks × 3 arms = 48 pairs per experiment, each answered in its own
interpreter and verified in milliseconds — single-threaded on 2 vCPU /
~3 GB RAM, a full bench is seconds and a full grade is under a second. No
network, no GPU, no third-party data.
