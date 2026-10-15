# Lean sorry-filler: the theorem machine's intern

An agent works on a real formalization chore inside a disposable sandbox:
a fixture Lean 4 repository ships ten Mathlib-style exercise files, each
with one theorem left as a `sorry` — the "admission" a mathematician
writes when the proof is owed later. The agent finds every sorry, writes
a tactic proof for each, and recompiles until `lake build` reports zero
sorry warnings. The judge is Lean itself: the pinned compiler must
elaborate every file, the build log must carry no
``declaration uses `sorry` `` warning, and the kernel's own
`#print axioms` audit must show every proof rests on nothing beyond
Lean's three standard axioms (`propext`, `Classical.choice`,
`Quot.sound`). The theorem statements are frozen, so proving something
easier is caught by a verbatim statement check.

A sandbox helps because a compile-check loop with untrusted agent
edits is exactly what you should not run on your own machine: the judge
builds the submission from a copy, checksums itself before and after,
and a broken proof can never touch anything local. The whole judge —
pinned elan 4.2.4 / Lean 4.34.1 toolchain, self-test with 8 mutants,
grading — runs from nothing in a fresh sandbox in a few minutes (the
Lean download is ~580 MB, ~1–3 min; everything after is seconds).

## One-command run

From this repository's root, with Python 3.10+ and the `sbx` CLI
(`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and `SBX_API_KEY` exported:

```bash
python3 cookbook/lean-sorry-filler/run.py
```

Each run prints wall time per step (clone, setup, selftest, grade), the
verdict JSON, and a short human summary, then kills the sandbox and
confirms it is gone. Measured in this sandbox (see RECEIPT.md): setup
cold ~2 min, selftest ~3 min (10 lake builds), grade ~19 s.

To try the judge locally on an x86-64 Linux box instead (all three from
this repository's root):

```bash
bash cookbook/lean-sorry-filler/judge/setup.sh
bash cookbook/lean-sorry-filler/judge/selftest.sh
bash cookbook/lean-sorry-filler/judge/grade.sh cookbook/lean-sorry-filler/examples/good/exercises
```

## Ask your agent

With the sandbox plugin installed, paste this prompt. The agent writes
the proofs itself in the sandbox and iterates with the judge until it
passes — that loop is the demo:

> Create a fresh sandbox. Inside it, clone
> https://github.com/agent-next/sandbox at ref `main`, then read
> `cookbook/lean-sorry-filler/SPEC.md` carefully. First run
> `bash cookbook/lean-sorry-filler/judge/setup.sh` to install the
> pinned Lean 4.34.1 toolchain. Then copy
> `cookbook/lean-sorry-filler/judge/fixture/` to your own working
> directory — it is a lake package with ten exercise theorems, one
> planted `sorry` each. Find every sorry, write a real tactic proof for
> each, and recompile (`lake build --no-cache`) until there are zero
> `declaration uses `sorry` warnings. The judge
> `bash cookbook/lean-sorry-filler/judge/grade.sh <your-copy>` decides:
> structure (statements verbatim, no `sorry`/`admit`/`axiom`/
> `native_decide` tokens), build (lake exit 0, zero sorry warnings),
> axioms (`#print axioms` within the standard three), and closure
> (≥ 60% of planted sorries closed). Iterate with
> `--json /tmp/v.json` until every gate passes, then report which
> sorries you closed and the proof term for the first one, then kill
> the sandbox and confirm it is gone. If you cannot get a gate to
> pass, say exactly which gate and what you tried, and stop.

## What the judge checks (short form)

| gate | rule |
|---|---|
| structure | exact fixture file set; all 10 statements verbatim; no `sorry`/`admit`/`sorryAx`/`native_decide`/`axiom` token; each file ≤ 64 KiB |
| build | `lake build --no-cache` exits 0 within 600 s and the log has 0 ``declaration uses `sorry` `` lines |
| axioms | `#print axioms` per theorem: no axioms, or ⊆ {propext, Classical.choice, Quot.sound} |
| closure | (planted − remaining)/planted ≥ 60 %, counted from source with the same regex as gate 1 |

The artifact is graded from a copy in a temp dir, and sha256 checksums
of `judge/` are compared before and after — the submission cannot
tamper with its own judge. `judge/selftest.sh` grades 8 scripted mutants
(re-submitted sorry, `admit`, smuggled `axiom`, `native_decide`,
statement binder swap, syntax error, missing file, broken proof) and a
determinism check (two grades → byte-identical verdicts except
`timing`); kill rate 8/8 = 100 %.

## Limits, stated plainly

- The fixture is Mathlib-*style* but imports nothing beyond Lean core:
  building Mathlib in the judge sandbox is explicitly out of scope
  (~100 GB, days). Every planted statement is provable with core
  tactics (`omega`, `simp`, `decide`, `rw`, `cases`, …).
- The judge never scores proof elegance; anything the kernel accepts
  under the gates passes.
- `native_decide` would let some statements "pass" by compiling a
  runtime check — gate 1's token regex and gate 3's axiom audit
  (`Lean.ofReduceBool`) both reject it.
- The judge runs on x86-64 Linux with CPython 3.10+; the toolchain
  download is ~585 MB, so a cold setup takes a few minutes.
