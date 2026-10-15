# skill-ab-bench demo — receipt

Real output from this builder sandbox (Debian, x86-64, 2 vCPU, ~4 GB RAM,
CPython 3.12.15, jq 1.6). Commands run from `cookbook/skill-ab-bench/`
unless stated. Wall times are from `time` around each whole command, on an
otherwise idle machine.

The one part of this demo this sandbox **cannot** run is `run.py`: creating
an agent-next sandbox needs `SBX_API_KEY` and the `sbx` CLI, and a sandbox
cannot create sandboxes. Everything `run.py` sends into the sandbox was run
here directly instead — see "In-sandbox command sequence" below, which is
the same command list, in the same order, with the same arguments.

## bash judge/setup.sh

```
$ time bash judge/setup.sh --force          # cold path: download + verify + install
setup: checking the platform
setup: refreshing apt lists (a fresh image ships them empty)
setup: downloading jq_1.6-2.1+deb12u2_amd64.deb
/tmp/tmp.QdhpW05Vs0/jq_1.6-2.1+deb12u2_amd64.deb: OK
setup: downloading libjq1_1.6-2.1+deb12u2_amd64.deb
/tmp/tmp.QdhpW05Vs0/libjq1_1.6-2.1+deb12u2_amd64.deb: OK
setup: downloading libonig5_6.9.8-1_amd64.deb
/tmp/tmp.QdhpW05Vs0/libonig5_6.9.8-1_amd64.deb: OK
(Reading database ... 30273 files and directories currently installed.)
Preparing to unpack .../libonig5_6.9.8-1_amd64.deb ...
Unpacking libonig5:amd64 (6.9.8-1) over (6.9.8-1) ...
Preparing to unpack .../libjq1_1.6-2.1+deb12u2_amd64.deb ...
Unpacking libjq1:amd64 (1.6-2.1+deb12u2) over (1.6-2.1+deb12u2) ...
Preparing to unpack .../jq_1.6-2.1+deb12u2_amd64.deb ...
Unpacking jq (1.6-2.1+deb12u2) over (1.6-2.1+deb12u2) ...
Setting up libonig5:amd64 (6.9.8-1) ...
Setting up libjq1:amd64 (1.6-2.1+deb12u2) ...
Setting up jq (1.6-2.1+deb12u2) ...
setup: checking the generated corpus and reference answers
gen_inputs: judge/tasks.json is up to date (16 tasks)
gen_reference: judge/reference.json is up to date (16 tasks)
setup: tool versions
jq-1.6
jq debian package: 1.6-2.1+deb12u2
Python 3.12.15
setup: wrote /home/user/w/cookbook/skill-ab-bench/judge/VERSIONS.txt
setup: done

real    0m13.553s
exit=0
```

All three `.deb`s printed `OK` from `sha256sum -c`, so the pinned hashes
match the pool. `sudo: unable to resolve host ...` is a harmless warning
from this container's hostname, not from the install.

Second run (idempotent — the pinned version is already present):

```
$ time bash judge/setup.sh
setup: jq 1.6-2.1+deb12u2 already installed (skipping download)
...
setup: done

real    0m0.760s
exit=0
```

`judge/VERSIONS.txt` as written:

```
# skill-ab-bench judge: versions installed by judge/setup.sh
# (Linux x86_64)
jq 1.6
jq debian package: 1.6-2.1+deb12u2
libjq1 debian package: 1.6-2.1+deb12u2
python3 3.12.15
judge engine: python3 standard library only (no packages installed)
```

## bash judge/selftest.sh

```
$ time bash judge/selftest.sh
selftest: statistics engine
test_stats: Fisher's exact test (two-sided)
  ok   tea-tasting [[3,1],[1,3]]: 0.4857142857142857
  ok   worked example [[1,9],[11,3]]: 0.002759456185220083
  ok   symmetric under arm swap: 0.002759456185220083
  ok   perfect separation [[16,0],[0,16]]: 3.3273419550419868e-09
  ok   balanced [[8,8],[8,8]]: 0.9999999999999999
  ok   bench table [[16,0],[4,12]] < 0.05: True
       (bench table p = 1.6121e-05)
  ok   marginal [[16,0],[12,4]] >= 0.05: True
       (marginal table p = 0.101224)
test_stats: bootstrap CI on the pass-rate delta
  ok   point estimate is the measured delta: 0.75
  ok   lower bound > 0 for a 75 pt gap: True
  ok   upper bound <= 1: True
  ok   resamples recorded: 10000
  ok   lower bound is exactly 0.5: 0.5
  ok   same seed -> identical bounds: {...'lo': 0.5, 'hi': 0.9375, 'seed': 20261014}
  ok   different seed -> different bounds: True
  ok   seed 5 lower bound is 0.5625: 0.5625
  ok   placebo CI contains 0: True
  ok   placebo |delta| < 10 pts: True
  ok   identical arms -> point estimate 0: 0.0
  ok   identical arms -> CI contains 0: True
test_stats: input validation
  ok   negative cell rejected
  ok   empty table rejected
  ok   empty arm rejected
  ok   resamples=0 rejected
test_stats: all checks passed
selftest: corpus vs arm policies
test_corpus: the skill policy reproduces the oracle
  ok   skill policy == oracle on all 16 tasks
test_corpus: the no-skill policy reproduces the pinned answers
  ok   no-skill policy == pinned naive_answer on all 16 tasks
test_corpus: the difficulty flag matches the verdicts
  ok   easy tasks are exactly ['kv01', 'kv06', 're01', 're08']
  ok   12 hard tasks; the skill-no-skill delta is 75.0 pts
test_corpus: the placebo is a real control
  ok   placebo differs from no-skill on exactly ['kv05']
  ok   the placebo never does worse than the no-skill arm
test_corpus: no arm disagrees with itself across a shared answer
  ok   every shared answer across arms has matching verdicts
test_corpus: all checks passed
selftest: grading known-good /home/user/w/cookbook/skill-ab-bench/examples/good
selftest: known-good PASSED all gates
mutants: records/fabricated-verdict/results.json  [G3_verifier_replay]  kv02.noskill.passed False -> True (answer left wrong)
mutants: records/shared-answer-arms/results.json  [G2_arm_isolation]  kv03.noskill.answer <- kv03.skill.answer (verdict left False)
mutants: records/dropped-task/results.json  [G1_record_shape]  tasks: 16 -> 15 (kv04 dropped)
mutants: records/arms-swapped/results.json  [G6_effect_size]  skill <-> noskill answers/verdicts (delta becomes -75 pts)
mutants: records/marginal-win/results.json  [G5_power]  noskill adopts 8 skill answers (16/16 vs 12/16, p=0.101)
mutants: records/significant-placebo/results.json  [G7_placebo_control]  placebo adopts 4 skill answers (noskill-placebo = -31.25 pts)
mutants: records/policy-relabelled/results.json  [G1_record_shape]  kv05.placebo.policy <- arms.skill (label mismatch)
mutants: judge/reference-drift/  [G4_task_identifiability]  reference.json: re04.expected -> '::1' (oracle drift)
mutants: judge/no-bad-answers/  [G4_task_identifiability]  reference.json: kv07.bad -> [] (no known-bad answers)
mutants: judge/unverifiable-task/  [G3_verifier_replay]  tasks.json: re05.params.how -> 'no_such_technique' (oracle raises)
selftest: killed    records/arms-swapped (gate: G6_effect_size)
selftest: killed    records/dropped-task (gate: G1_record_shape)
selftest: killed    records/fabricated-verdict (gate: G3_verifier_replay)
selftest: killed    records/marginal-win (gate: G5_power)
selftest: killed    records/policy-relabelled (gate: G1_record_shape)
selftest: killed    records/shared-answer-arms (gate: G2_arm_isolation)
selftest: killed    records/significant-placebo (gate: G7_placebo_control)
selftest: killed    judge/no-bad-answers (gate: G4_task_identifiability)
selftest: killed    judge/reference-drift (gate: G4_task_identifiability)
selftest: killed    judge/unverifiable-task (gate: G3_verifier_replay)
selftest: kill rate 10/10 = 100%
selftest: determinism OK (two --seed 1 runs byte-identical)
selftest: --seed changes the bootstrap CI as expected
selftest: OK

real    0m24.251s
exit=0
```

**Kill rate 10/10 = 100 %** (≥ 90 % required). Every mutant died at the gate
it names: the fabricated verdict at G3, the shared answer at G2, the dropped
task at G1, the arms-swapped record at G6 (every answer and verdict in it is
genuine — only the direction is wrong), the marginal 25 pt win at G5, the
"working" placebo at G7, and all three mutated judges at the gate that
notices the judge itself is broken.

## bash judge/grade.sh examples/good --json /tmp/v.json

```
$ time bash judge/grade.sh examples/good --json /tmp/v.json
{ ... full verdict JSON, see below ... }

real    0m2.298s
exit=0
```

Key numbers from the verdict (`judge/grade.sh examples/good --json /tmp/v.json`,
seed 20261014, 10000 resamples — the same values as the committed
`examples/good/results.json` produced):

| gate | number | rule | pass |
|---|---|---|---|
| G1 | 16 tasks, ids kv01–kv08 + re01–re08 | exactly the 16 ids in `tasks.json` | yes |
| G2 | 0 tasks share an answer across arms | none may, when verdicts differ | yes |
| G3 | **48** verdicts replayed by the oracle | all must match the record | yes |
| G4 | **16** tasks checked, 127 single-edit near-misses rejected | every task must separate good from bad | yes |
| G5 | **p = 1.6121e-05** | p < 0.05 | yes |
| G6 | **delta = +75.0 pts, CI [0.500, 0.938]** | delta ≥ 25.0 and CI lower bound > 0 | yes |
| G7 | **delta = −6.25 pts, CI [−0.375, 0.250]** | CI contains 0 and \|delta\| < 10.0 | yes |
| G8 | judge sha256 `17391532136fa243ebca9f4c3480d6c5f889a93854c3645f107b01131bb770c4`, graded from a copy | unchanged before and after | yes |

Verdict `"pass"`, `failed_gate: null`, wall 1.196 s inside the judge
(2.3 s for the shell wrapper). G7's delta is negative because the placebo
(5/16) beats the no-skill arm (4/16) on one task — the interval spans zero
and the gate passes, which is exactly what a placebo control is for.

## Two fresh runs, side by side

Two independent bench + grade runs, each from a clean temp directory, same
seed (`20261014`):

| | run A | run B |
|---|---|---|
| bench wall | 9.4 s | 9.8 s |
| skill arm | 16/16 (100.0 pts) | 16/16 (100.0 pts) |
| no-skill arm | 4/16 (25.0 pts) | 4/16 (25.0 pts) |
| placebo arm | 5/16 (31.2 pts) | 5/16 (31.2 pts) |
| delta skill − noskill | +75.0 pts | +75.0 pts |
| G5 Fisher p | 1.6121e-05 | 1.6121e-05 |
| G6 CI | [0.500, 0.938] | [0.500, 0.938] |
| G7 CI | [−0.375, 0.250] | [−0.375, 0.250] |
| G8 judge sha256 | `17391532136fa243…` | `17391532136fa243…` |
| verdict | pass | pass |

The two verdict JSONs are equal field for field apart from `timing`
(checked with a JSON comparison, `timing` popped). The only per-run variation
in the experiment record itself is the `ms` field of each arm block, which is
a measured duration and is not part of any gate.

## In-sandbox command sequence

`run.py` sends this list to `sbx exec`, in this order. Run here directly,
from a clean directory, it produced:

```
$ bash judge/setup.sh                                    # rc=0   1.4 s
$ python3 -I judge/bench.py /tmp/bench --seed 20261014    # rc=0   9.4 s
bench: 16 tasks x 3 arms = 48 pairs in 9.4 s
  skill    16/16 pass (100.0 pts)
  noskill  4/16 pass (25.0 pts)
  placebo  5/16 pass (31.2 pts)
bench: delta skill-noskill = +75.0 pts
bench: wrote /tmp/bench/results.json
$ bash judge/selftest.sh                                 # rc=0  24.3 s
$ bash judge/grade.sh /tmp/bench --json /tmp/verdict.json           # rc=0  2.3 s
$ bash judge/grade.sh examples/good --json /tmp/verdict-good.json   # rc=0  2.3 s
```

Both grades exited 0 with verdict `pass`. The record the bench wrote to
`/tmp/bench/results.json` is identical to the committed
`examples/good/results.json` in every task, answer, verdict and policy
string; only the `ms` timings differ.

## Deviations

- **`run.py` has not been run end to end.** This sandbox cannot create
  sandboxes. It is verified by `python3 -m py_compile` and by running its
  in-sandbox command sequence directly (above), and the lead will run it
  against a real sandbox. *(not done: no `sbx` CLI / API key inside a
  sandbox.)*
- **One sandbox per run, not one per (arm, task) pair.** The brief said 32
  sandboxes (16 tasks × 2 arms); the spec and README say why the demo spends
  its sandbox on the pinned-toolchain boundary and isolates the pairs by
  process instead. 48 pairs × a `git clone` each would be the same
  deterministic scripts re-run 48 times, which measures the clone, not the
  skill. If the lead wants the literal 32-sandbox shape, `run.py` is the
  place to change it.
- **A third arm was added.** The brief specified 16 tasks × 2 arms; the
  placebo control needs a third arm to exist at all (16 × 3 = 48 pairs), and
  the lead asked for the placebo gate. The placebo is not a copy of the
  no-skill arm: its one rule changes exactly one task's answer, so the
  control is a real one.
- **The corpus is 4 easy + 12 hard, not 10 + 6.** The checked-in draft
  (`gen_inputs.py`'s `TASK_TABLE`) asserted a 10/6 split and a set of naive
  answers that the arm policies did not actually produce — the generator
  could not run. The corpus and the policies are now checked against each
  other (`gen_inputs.py` asserts it; `judge/arm_runner.py` runs all three
  arms over all 16 tasks in the bench), giving 16/16 vs 4/16 = 75.0 pts. The
  bar in SPEC.md (≥ 25 pts) is unchanged and is cleared with margin.
- **`examples/good/skill/` was extended with `SKILL.md`.** The brief asks for
  a skill, and a skill package is a `SKILL.md` plus its snippets; the draft
  had only `reference.py`.
- **Media is not in this task.** `media/` (result.png, loop.png, demo.mp4,
  MANIFEST.json, make_media.sh) and `REPRODUCE.md` are left for the later
  tasks named in the brief. *(not done: assigned to a later task.)*
- **The placeholder text in `SPEC.md` that read "a cannabis-free delta" is
  gone** — it was a typo in the draft, replaced with what the gate actually
  rejects.
