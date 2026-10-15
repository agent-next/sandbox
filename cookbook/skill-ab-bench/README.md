# Skill A/B bench

Does an agent skill actually help? Sixteen file-parsing questions are
answered three times over — once with a regex-cookbook skill package on the
desk, once with nothing, once with a placebo that only adds a README — and
the judge decides with a bootstrap confidence interval on the pass-rate
delta, an exact test, and a placebo control that stops the bench from
crowning a skill that does nothing. Measured: **16/16 vs 4/16, delta +75.0
pts, CI [0.500, 0.938], Fisher p = 1.6e-05**; the placebo lands at 5/16
(−6.2 pts, CI [−0.375, 0.250], contains 0) and is not crowned.

A sandbox helps because an A/B test is only worth reading if the experiment
that produced it is reproducible: the sandbox pins the toolchain, gives every
run the same pinned corpus and the same seed, and is destroyed afterwards, so
the numbers are a property of the bench rather than of the machine it ran on.

## One-command run

From this repository's root, with Python 3.10+ and the `sbx` CLI
(`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and `SBX_API_KEY` exported:

```bash
python3 cookbook/skill-ab-bench/run.py              # default ref main
python3 cookbook/skill-ab-bench/run.py --ref main   # explicit ref
python3 cookbook/skill-ab-bench/run.py --seed 7     # another bootstrap seed
python3 cookbook/skill-ab-bench/run.py --keep       # leave the sandbox up
```

It creates a sandbox, clones this repo at `--ref`, installs the pinned tools,
runs the bench, runs the judge self-test, grades both the fresh record and
the committed example, prints the verdict with each gate's numbers, then
kills the sandbox and confirms it is gone. Measured wall time per step on a
2 vCPU machine (see RECEIPT.md): clone seconds, setup ~1.4 s when jq is
already present (cold: ~14 s to download, verify and install the three
pinned `.deb`s), bench ~9 s, self-test ~24 s, grade ~2.3 s.

To run the judge on your own machine instead:

```bash
bash cookbook/skill-ab-bench/judge/setup.sh       # pinned jq in ~/; stdlib judge
bash cookbook/skill-ab-bench/judge/bench.py /tmp/bench   # 48 pairs -> results.json
bash cookbook/skill-ab-bench/judge/selftest.sh    # known-good passes, 11/11 mutants killed
                                                  # (also: stats vs published values, corpus vs policies)
bash cookbook/skill-ab-bench/judge/grade.sh /tmp/bench --json /tmp/v.json
```

## What the judge checks (short form)

| gate | rule |
|---|---|
| G1 record shape | schema, seed, exactly the 16 task ids from `judge/tasks.json`, every arm block well-formed, each policy string matching its arm's label |
| G2 arm isolation | the arms differ, and no task shares an answer between the skill and no-skill arms with different verdicts |
| G3 verifier replay | the judge re-runs each task's own oracle on the recorded answer and requires the verdict to match the record |
| G4 task identifiability | the reference answer passes, and every single-edit near-miss of it fails |
| G5 power | two-sided Fisher exact test on the 2×2 table: p < 0.05 |
| G6 effect size | delta ≥ 25.0 pts and the bootstrap CI lower bound > 0 |
| G7 placebo control | the placebo's delta has a CI containing 0 and is < 10.0 pts in absolute value |
| G8 judge integrity | the artifact is graded from a copy, and `judge/` is checksummed before and after |

The artifact is one directory holding one file, `results.json` — the bench's
experiment record. The judge never trusts it: it grades a copy, replays every
verifier, and recomputes the counts, the exact test and the bootstrap CI from
the verdicts it verified itself. See `SPEC.md` for the exact rules.

## Ask your agent

With the sandbox plugin installed, paste this prompt. The agent builds and
fixes the bench itself in a sandbox and iterates with `judge/grade.sh` until
it passes — that loop is the demo:

> Create a fresh sandbox. Inside it, clone
> https://github.com/agent-next/sandbox at ref `main`, then read
> `cookbook/skill-ab-bench/SPEC.md` carefully. You are to make the skill A/B
> bench honest and green: `judge/bench.py` must run a 16-task × 3-arm
> experiment (a skill arm, a no-skill arm and a placebo arm) and write
> `results.json`; `judge/grade.py` must grade it against all nine gates and
> exit 0 only if every one passes. First run `judge/setup.sh`, then
> `python3 -I judge/bench.py /tmp/bench` to produce a record, then iterate:
> `bash judge/grade.sh /tmp/bench --json /tmp/v.json` and read the verdict
> JSON until every gate passes. If a gate fails, fix the *bench*, not the
> gate — the gates are the specification. The skill package is
> `examples/good/skill/`; the judge's own self-test shows what it rejects, so
> run `judge/selftest.sh` once and read which mutant each gate kills. When
> the good record passes and the self-test reports a 100 % kill rate, report
> both pass rates, the delta with its confidence interval, the Fisher p and
> the placebo delta, then kill the sandbox and confirm it is gone. If you
> cannot get a gate to pass, say exactly which gate and what you tried, and
> stop.

## Limits, stated plainly

- **No agent and no LLM are driven.** The "arms" are arm policies: short
  deterministic scripts that answer the tasks, one of which consults the
  skill package. This demo measures the *bench* — its interval, its placebo
  control and its judge — not a model's sensitivity to a skill. The delta is
  a fact of the pinned corpus (16/16 vs 4/16 by construction), not a finding
  about any model.
- **One sandbox per run, not one per pair.** The pairs are isolated by fresh
  interpreters with their own working directory inside one disposable
  sandbox. 48 sandboxes would re-clone this repository 48 times to re-run 48
  stateless policy scripts; the sandbox is spent on the pinned-toolchain
  boundary instead.
- **16 tasks is a small sample.** The bar is set for that sample: a 25 pt gap
  at 16/16 vs 12/16 is a real difference that Fisher refuses to call
  significant (p = 0.101), and the bench fails rather than report it. A
  larger corpus would lower the effect size a bench could resolve.
- **The judge grades numbers, not pedagogy.** Whether the skill teaches
  anything *well* is out of scope; the arms are written so that one is a
  little cleverer than the other, not so that either is a good parser.
- The placebo's one rule changes exactly one task's answer, deliberately: a
  placebo that changed nothing would make G7 trivially true.

## Reproducibility

- Pinned: `judge/setup.sh` installs jq 1.6-2.1+deb12u2 from three
  sha256-checked Debian `.deb`s and records what it installed in
  `judge/VERSIONS.txt`. The judge engine is Python 3.10+ standard library
  only — no packages, no scipy, no numpy.
- Deterministic: every random choice takes `--seed` (default `20261014`), and
  the bench's answers and verdicts are identical run to run; only the `ms`
  timings vary. `judge/selftest.sh` checks that two `--seed 1` grades are
  byte-identical (excluding `timing`) and that a different seed moves the CI.
- Traceable: every number in this file and in `RECEIPT.md` names the command
  and the seed that produced it.

## Media

Not in this task: figures and the video are produced by a later task (see
`media/` when it lands).
