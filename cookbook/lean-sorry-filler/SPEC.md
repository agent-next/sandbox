# lean-sorry-filler: Lean 4 `sorry`-closing demo — SPEC

An agent works inside a disposable sandbox on a real formalization chore:
a fixture Lean 4 repository ships Mathlib-style exercise files in which
every exercise theorem is left as a `sorry`. The agent crawls the repo for
the `sorry` admissions, writes a real tactic proof for each, and iterates
`lake build` until the compiler reports zero sorries. The judge is Lean
itself: the pinned compiler must accept every file, the build log must
contain no `declaration uses 'sorry'` warning, and the judge's own kernel
audit (`#print axioms` on every exercise theorem, run from a file the
agent never touches) must show each proof rests on nothing beyond Lean's
three standard axioms. The theorem statements themselves are part of the
fixture and may not change, so a proof of a weaker statement is rejected.

## Goal

- Fixture: `judge/fixture/` — a minimal lake package (`exercises`) with a
  root `Exercises.lean` importing `Exercises/Ex01.lean` … `Ex10.lean`;
  10 exercise theorems, one planted `sorry` each.
- Artifact: a directory with the fixture's exact file set in which every
  `sorry` is replaced by a proof the pinned Lean compiler accepts. Only
  proof bodies may differ from the fixture.
- Judge: `judge/grade.sh <artifact>` builds the artifact from a fresh
  copy with the pinned toolchain and applies the five gates below.
- Self-test: `judge/selftest.sh` proves the judge fails known-bad
  submissions (8 scripted mutants, kill rate ≥ 90 % required).

## Non-goals

- Mathlib itself: the fixture is Mathlib-*style* (named exercises, tactic
  proofs, arithmetic / logic / list statements) but imports nothing
  beyond Lean core, so a build is seconds, not hours. Building Mathlib in
  the judge sandbox is explicitly out of scope (≈ 100 GB, days).
- Automation quality: any proof the kernel accepts under the stated
  gates passes; elegance is not scored.
- Discovery metrics (how many compile–fix cycles the agent needed): the
  judge grades the final artifact only.
- `exact?` / `apply?` search tooling: not present in core Lean; the
  negative-control mutants cover their spirit (`native_decide`, added
  `axiom`).

## The artifact contract

The artifact is a directory containing **exactly** the fixture's file set
(`lakefile.toml`, `lean-toolchain`, `Exercises.lean`,
`Exercises/Ex01.lean` … `Ex10.lean`), with:

1. every exercise theorem statement byte-identical to the fixture's
   (whitespace included — the statement text is frozen; only the proof
   after `:= by` may change);
2. no occurrence of the tokens `sorry`, `admit`, `sorryAx`,
   `native_decide`, or `axiom` anywhere in the submitted sources
   (word-boundary match);
3. each file ≤ 64 KiB;
4. `lake build` succeeding with the pinned toolchain and reporting zero
   sorry warnings.

Third-party inputs: none beyond the pinned elan/Lean toolchain downloads
(URLs, versions and licences in `judge/setup.sh`); all fixture content is
written for this demo (Apache-2.0, like the rest of this repository).

## Judge gates (numeric pass rules)

`judge/grade.sh <artifact> [--seed N] [--json out.json]` copies the
artifact's file set into a fresh temp dir, adds the judge's own
`JudgeCheck.lean`, and exits 0 only if all five gates pass. `--seed`
(default 0) is recorded in the verdict; nothing in grading is random, so
the seed has nothing to perturb (stated here so the flag is honest).

1. **structure** — file set identical to the fixture's (all 13 files
   present; no extra files); all 10 statements found verbatim on their
   own line in the matching file (count must equal 10); forbidden-token
   regex over submitted sources matches 0 times; every file ≤ 64 KiB.
2. **build** — `lake build -j 2` exits 0 within 600 s on the fresh copy,
   and the captured log contains 0 lines matching
   `declaration uses 'sorry'` (the no-sorry regex; a re-submitted
   `sorry` or `admit` compiles with exit 0 but dies here).
3. **axioms** — the judge's `JudgeCheck.lean` (never part of the
   artifact) is elaborated with `lake env lean`; for each of the 10
   exercise theorems, `#print axioms` must report either "does not
   depend on any axioms" or an axiom set ⊆ {propext, Classical.choice,
   Quot.sound}. An added `axiom` declaration, `sorryAx`, or
   `native_decide` (which pulls in `Lean.ofReduceBool`) fails this gate.
4. **closure** — planted sorries N = 10 (counted from the pristine
   fixture at grade time); remaining admissions R counted in the
   submitted sources by the same regex as gate 1; closed fraction
   (N − R)/N ≥ 0.60. Measured from source text, independently of the
   build log, so the two numbers can disagree only if one gate is
   broken.
5. **judge_intact** — sha256 of every file under `judge/` (fixture
   included) identical before and after the grade; the artifact is built
   from a copy and can never write into the judge.

Verdict JSON carries: files found/expected, statements matched,
forbidden-token hits per file, build exit code, sorry-warning count,
per-theorem axiom sets (sorted), closure counts and rate, judge_intact,
seed. Wall times live only under `timing`. Two grades of one artifact
are byte-identical except `timing` (checked by `selftest.sh`).

## Acceptance oracle

The oracle is the Lean kernel plus the judge's statement freeze. A
submission "works" iff the pinned compiler elaborates every file with
zero sorry warnings (gate 2), every proof's kernel-level axiom
dependency set is within Lean's standard three (gate 3 — impossible to
satisfy with `sorryAx`, a smuggled `axiom`, or `native_decide`), and the
proved statements are still the planted ones (gates 1 and 4). "The build
ran" is never sufficient: `lake build` exits 0 on a file full of
sorries, which is exactly what the demo is about catching.

## Known-bad examples (self-test)

`judge/mutants.py` derives 8 known-bad artifacts from `examples/good/`
by scripted single edits:

| mutant | edit | gate that kills it |
|---|---|---|
| resubmit_sorry | Ex01 proof → `sorry` | structure + build (sorry warning) + closure |
| admit_token | Ex02 proof → `admit` | structure + build + closure |
| axiom_cheat | Ex03 theorem → `axiom` declaration | structure (token) + axioms |
| native_decide_cheat | Ex05 proof `decide` → `native_decide` | structure + axioms (`Lean.ofReduceBool`) |
| binder_swap | Ex07 statement binders swapped (still compiles) | structure (statement freeze) |
| syntax_error | stray `!` in Ex08 | build |
| missing_file | Ex09.lean deleted | structure (file set) + build (broken import) |
| broken_proof | Ex10 proof → `rfl` (does not hold by `rfl`) | build |

`judge/selftest.sh` grades the known-good (must pass) and every mutant
(each must fail ≥ 1 gate), prints the kill rate, checks determinism
(two grades → byte-identical verdicts except `timing`), and checks
`judge/` checksums. It exits non-zero unless good passes, every mutant
dies, and the kill rate is ≥ 90 %.

## Determinism

Nothing in the judge is random: the toolchain is pinned, `lake build`
runs with `-j 2` on a fresh copy, gate results are counts and sets, and
the verdict JSON is written with sorted keys. The `--seed` flag exists
for interface uniformity across demos and is recorded, unused.

## Toolchain (pinned, sha256-checked)

`judge/setup.sh` installs into `$HOME/.elan/`, idempotently, from
official release tarballs only:

| tool | version | source |
|---|---|---|
| elan | v4.2.4 (2026-08-25) | https://github.com/leanprover/elan/releases/download/v4.2.4/elan-x86_64-unknown-linux-gnu.tar.gz (sha256 pinned) |
| Lean 4 + lake | v4.34.1 (2026-09-24) | https://github.com/leanprover/lean4/releases/download/v4.34.1/lean-4.34.1-linux.tar.zst (sha256 pinned) |

The Lean tarball is extracted straight into elan's toolchain store as
`leanprover/lean4:v4.34.1` and set as the default, so `lake` resolves
the fixture's `lean-toolchain` file with no further network access.
Both releases predate 2026-10-01 (nothing published in the two weeks
before this demo was built). `judge/VERSIONS.txt` records what setup
actually installed. Licence: both are Apache-2.0.
