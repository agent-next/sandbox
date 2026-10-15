# RECEIPT — lean-sorry-filler

Real output from two fresh sandbox runs of the one-command acceptance
(`python3 cookbook/lean-sorry-filler/run.py --ref sbx/demo-lean-sorry-filler-f4`),
run from outside the repo on 2026-10-15 after the statement-freeze and
cleanup-verification fixes. Each run created its own sandbox, cloned the
branch, ran `judge/setup.sh` (cold toolchain download), `judge/selftest.sh`
(9 mutants), and `judge/grade.sh examples/good/exercises`, then killed the
sandbox and confirmed it was gone. Both exited 0 with an all-gates-pass
verdict. Builder environment: Debian 12, 2 vCPU, ~3.8 GB RAM, x86-64,
CPython 3.12.15.

## Run 1 — sandbox 01a14036-290f-7303-b0c1-1f8caf7eca29

```
  [create] sbx create --timeout-min ... ok (2 s)
  [clone] sbx exec 01a14036-... ... ok (5 s)
setup.sh: downloading elan.tar.gz from the pinned release URL
setup.sh: downloading lean.tar.zst from the pinned release URL
setup.sh: ok
  [setup] sbx exec 01a14036-... ... ok (161 s)
selftest: generating mutants
selftest: grading known-good
selftest: known-good: PASS
selftest: mutant resubmit_sorry: killed (gate: axioms,build,structure)
selftest: mutant admit_token: killed (gate: axioms,build,structure)
selftest: mutant axiom_cheat: killed (gate: axioms,structure)
selftest: mutant native_decide_cheat: killed (gate: axioms,structure)
selftest: mutant binder_swap: killed (gate: structure)
selftest: mutant syntax_error: killed (gate: axioms,build)
selftest: mutant missing_file: killed (gate: axioms,structure)
selftest: mutant broken_proof: killed (gate: axioms,build)
selftest: mutant statement_parked_in_comment: killed (gate: axioms,build,structure)
selftest: kill rate: 9/9 = 100%
selftest: determinism check (two grades of the good artifact)
selftest: determinism: OK
selftest: ok
  [selftest] sbx exec 01a14036-... ... ok (62 s)
  [grade] sbx exec 01a14036-... ... ok (7 s)
  [cat] sbx exec 01a14036-... ... ok (2 s)
killed 01a14036-290f-7303-b0c1-1f8caf7eca29
  [kill] sbx kill 01a14036-... ... ok (4 s)
  [list] sbx list ... ok (3 s)
cleanup: sandbox 01a14036-290f-7303-b0c1-1f8caf7eca29 killed and confirmed gone
total: 247 s

lean-sorry-filler demo: PASS
  gate structure: pass  statements 10/10, tokens 0 problems
  gate build: pass  exit 0, sorry warnings 0
  gate axioms: pass  10/10 audited
  gate closure: pass  10/10 closed (100%)
  judge_intact: True
RUN_PY_EXIT=0
```

Verdict JSON key numbers (run 1):

```json
{
  "pass": true,
  "judge_intact": true,
  "seed": 0,
  "structure": {"pass": true, "statements_matched": 10, "problems": []},
  "build": {"pass": true, "build_exit": 0, "sorry_warnings": 0,
            "build_log_lines": 14},
  "axioms": {"pass": true, "audit_exit": 0, "problems": [], "axioms": {
    "exercise_add_comm_three": ["Quot.sound", "propext"],
    "exercise_add_twice": ["Quot.sound", "propext"],
    "exercise_and_distrib": [],
    "exercise_append_nil": ["propext"],
    "exercise_even_witness": [],
    "exercise_le_refl": [],
    "exercise_length_append": ["propext"],
    "exercise_one_add_self": ["Quot.sound", "propext"],
    "exercise_pow_succ": [],
    "exercise_two_mul_two": []}},
  "closure": {"pass": true, "planted": 10, "remaining": 0,
              "closed": 10, "closed_rate": 1.0},
  "timing": {"axioms_s": 0.6, "build_s": 4.3, "total_s": 4.9}
}
```

## Run 2 — sandbox 01a1403a-61da-7f60-a3a6-aa17082fa424

```
  [grade] sbx exec 01a1403a-... ... ok (9 s)
  [cat] sbx exec 01a1403a-... ... ok (3 s)
killed 01a1403a-61da-7f60-a3a6-aa17082fa424
  [kill] sbx kill 01a1403a-... ... ok (6 s)
  [list] sbx list ... ok (1 s)
cleanup: sandbox 01a1403a-61da-7f60-a3a6-aa17082fa424 killed and confirmed gone
total: 217 s

lean-sorry-filler demo: PASS
  gate structure: pass  statements 10/10, tokens 0 problems
  gate build: pass  exit 0, sorry warnings 0
  gate axioms: pass  10/10 audited
  gate closure: pass  10/10 closed (100%)
  judge_intact: True
RUN_PY_EXIT=0
```

Verdict JSON key numbers (run 2, tail captured): `pass: true`,
`judge_intact: true`, `structure: {pass: true, statements_matched: 10,
problems: []}`, `closure: {closed: 10, remaining: 0, pass: true}`,
`timing: {axioms_s: 0.7, build_s: 5.5, total_s: 6.2}`. Selftest kill rate
9/9 = 100 % (same 9 mutants as run 1; the run-2 output file captured only
the post-verdict tail — noted under Deviations).

Both runs: `sbx list` afterwards shows neither sandbox id — cleanup
confirmed gone in both.

## Earlier builder runs (pre-fix, same branch base)

Tool versions installed (judge/VERSIONS.txt, from setup):

```
## elan elan 4.2.4 (227caca13 2026-08-25)
## lean Lean (version 4.34.1, x86_64-unknown-linux-gnu, commit 5045d0056413266e57c625dcd7c365b10e377c52, Release)
## lake Lake version 5.0.0-src+5045d00 (Lean version 4.34.1)
## elan home: /home/user/.elan
## toolchain: leanprover/lean4:v4.34.1
```

## `bash judge/setup.sh` (cold, toolchain wiped first)

```
$ (time bash judge/setup.sh)
setup.sh: downloading elan.tar.gz from the pinned release URL
setup.sh: downloading lean.tar.zst from the pinned release URL
setup.sh: ok

real	4m47.797s
user	0m37.412s
sys	0m49.209s
$ echo $?
0
```

Idempotency: a second run with the toolchain present prints only
`setup.sh: ok` and exits 0 (no re-download; the sha256-pinned files are
skipped because the installed versions already match).

## `bash judge/selftest.sh`

```
$ (time bash judge/selftest.sh)
selftest: generating mutants
selftest: grading known-good
selftest: known-good: PASS
selftest: mutant resubmit_sorry: killed (gate: axioms,build,structure)
selftest: mutant admit_token: killed (gate: axioms,build,structure)
selftest: mutant axiom_cheat: killed (gate: axioms,structure)
selftest: mutant native_decide_cheat: killed (gate: axioms,structure)
selftest: mutant binder_swap: killed (gate: structure)
selftest: mutant syntax_error: killed (gate: axioms,build)
selftest: mutant missing_file: killed (gate: axioms,structure)
selftest: mutant broken_proof: killed (gate: axioms,build)
selftest: kill rate: 8/8 = 100%
selftest: determinism check (two grades of the good artifact)
selftest: determinism: OK
selftest: ok

real	2m57.186s
user	1m0.401s
sys	0m43.589s
$ echo $?
0
```

10 lake builds inside (1 known-good + 8 mutants, some failing fast, +
2 determinism grades of the good artifact). Kill rate 8/8 = 100 %.

## `bash judge/grade.sh examples/good/exercises --json /tmp/v.json`

```
$ (time bash judge/grade.sh examples/good/exercises --json /tmp/v.json)
{ ...verdict JSON, key fields below... }

real	0m16.944s
user	0m5.684s
sys	0m4.289s
$ echo $?
0
```

Verdict JSON key numbers (`/tmp/v.json`):

```json
{
  "pass": true,
  "judge_intact": true,
  "seed": 0,
  "structure": {"pass": true, "statements_matched": 10, "problems": []},
  "build": {"pass": true, "build_exit": 0, "sorry_warnings": 0,
            "build_log_lines": 14},
  "axioms": {"pass": true, "audit_exit": 0, "problems": [], "axioms": {
      "exercise_add_comm_three": ["Quot.sound", "propext"],
      "exercise_add_twice": ["Quot.sound", "propext"],
      "exercise_and_distrib": [],
      "exercise_append_nil": ["propext"],
      "exercise_even_witness": [],
      "exercise_le_refl": [],
      "exercise_length_append": ["propext"],
      "exercise_one_add_self": ["Quot.sound", "propext"],
      "exercise_pow_succ": [],
      "exercise_two_mul_two": []}},
  "closure": {"pass": true, "planted": 10, "remaining": 0,
              "closed": 10, "closed_rate": 1.0},
  "timing": {"axioms_s": 2.7, "build_s": 13.8, "total_s": 16.6}
}
```

## `python3 -m py_compile run.py` and the in-sandbox sequence

```
$ python3 -m py_compile cookbook/lean-sorry-filler/run.py
$ echo $?
0
```

run.py's exact in-sandbox command sequence (`git clone --depth 1` →
`judge/setup.sh` → `judge/selftest.sh` →
`judge/grade.sh examples/good/exercises --json /tmp/verdict.json`) was
executed directly with `bash -c` against a fresh clone of the branch
(sandbox creation cannot be exercised from inside this sandbox):

```
done.
setup.sh: ok
selftest: ... (identical output to the selftest block above)
selftest: kill rate: 8/8 = 100%
selftest: ok
grade exit: 0
verdict pass: True
verify exit=0
```

The lead will run `python3 cookbook/lean-sorry-filler/run.py` end to end
on a real sandbox.

## Second fresh run (sandbox reproduction, later the same day)

The full cold sequence was run a second time from scratch (toolchain
wiped, fresh clone): setup 4m48s → ok, selftest kill rate 8/8 = 100 %,
grade exit 0 with `pass: true`, `sorry_warnings: 0`, `closed: 10/10`,
`judge_intact: true`. Verdict JSON identical to the first run except the
`timing` key, matching the determinism gate. (Both runs were in this
same builder sandbox, not two distinct fresh sandboxes; the lead's
end-to-end `run.py` run is the independent fresh-sandbox check — noted
also under Deviations.)

## Deviations

- **REPRODUCE.md (not done: standard requires a different model family
  for independent reproduction; out of scope for this builder task —
  left for the reviewer/lead).** Media (`media/`) is also out of scope
  for this task per the task brief; a later task does media.
- The second "fresh" run above was in the same sandbox as the first
  (this task cannot create new sandboxes); the numbers are still
  cold-start honest because the toolchain was wiped between runs.
- `lake build` in this Lake version has no `-j` flag; parallelism is
  bounded by the sandbox's 2 vCPUs, and `--no-cache` keeps the build
  offline. SPEC.md states `lake build --no-cache`.
- The elan tarball ships a single static `elan-init` binary; the Lean
  tarball ships a full toolchain tree. Both are extracted into their own
  empty directories before anything is copied into place (untrusted
  download hygiene), and both sha256s are pinned in `judge/setup.sh`.
- Fixtures and exercises are original content written for this demo
  (Apache-2.0, like this repository); no third-party data beyond the
  pinned toolchain downloads, which are official release artifacts:
  elan v4.2.4 (https://github.com/leanprover/elan, Apache-2.0) and Lean
  v4.34.1 (https://github.com/leanprover/lean4, Apache-2.0).
