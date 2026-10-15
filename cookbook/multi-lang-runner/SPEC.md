# multi-lang-runner: one sandbox, six languages, judged against an independent oracle

## Goal

An agent writes solutions to three fixed algorithmic problems in **six
languages** (Python, Node.js, Go, Rust, Bash, C) inside one disposable
sandbox, plus a `run_all.sh` driver. A judge it cannot fool then installs the
pinned toolchains, compiles and runs every solution on deterministic seeded
input cases, and compares stdout **byte-for-byte** against an independent
reference implementation (a Python oracle written from the problem
statements, sharing no code with any solution). The judge also records
compile and run wall time per language into a table.

The point of using a sandbox: the agent installs six toolchains, builds and
runs code in all of them, and iterates against the judge in an isolated,
disposable environment. Nothing it does can touch the real machine, and the
judge is unmodified by anything the artifact does.

## The three problems (fixed, deterministic)

All problems read from stdin and write to stdout. Input formats are exact;
output is compared byte-for-byte (exact bytes, including trailing newline).

### P1 — `sumsq`

Sum of squares with a cap.

Input: first line an integer `n` (1 ≤ n ≤ 10000). Then `n` lines, each one
integer `x` in [-10^9, 10^9]. Output: one line, the decimal value of
`min(sum(x_i^2), 10^18)` — i.e. the sum of squares, capped at 10^18
(values above the cap print `1000000000000000000`).

### P2 — `rle`

Run-length encode, then decode round-trip check.

Input: one line of printable ASCII (length 1..10000, no spaces). Output:
the run-length encoding as `count`+`char` pairs concatenated, e.g. `aaabb`
→ `3a2b`. A single occurrence prints just the char with count `1`
(e.g. `a` → `1a`).

### P3 — `primes`

Segmented sieve count in a range.

Input: one line with two integers `lo hi` (0 ≤ lo ≤ hi ≤ 10^7, hi - lo ≤
10^6). Output: one line, the number of primes p with lo ≤ p ≤ hi.

## Non-goals (explicitly out of scope)

- No networking, no filesystem side effects beyond reading stdin / writing
  stdout, no subprocess spawning from solutions.
- No floating-point output anywhere: all three problems are exact integer or
  ASCII text, so stdout comparison is byte-exact with no tolerance.
- No parallelism inside solutions: each solution is a single program run
  once per case. (The judge runs languages sequentially; wall time is
  measured per language, not per solution.)
- No interactive use, no REPL, no REPL-checked output: the artifact is a set
  of files compiled and run non-interactively.
- No third-party libraries in solutions: Python stdlib only, Node builtins
  only, Go stdlib only, Rust stdlib only (no crates), Bash coreutils only,
  C standard library only.

## Artifact

The agent produces, under `solutions/`:

```
solutions/
  python/sumsq.py  python/rle.py  python/primes.py
  node/sumsq.js    node/rle.js    node/primes.js
  go/sumsq.go      go/rle.go      go/primes.go
  rust/sumsq.rs    rust/rle.rs    rust/primes.rs
  bash/sumsq.sh    bash/rle.sh    bash/primes.sh
  c/sumsq.c        c/rle.c        c/primes.c
  run_all.sh
```

Plus `run_all.sh` at the artifact root: a driver that, when run with
`bash run_all.sh <case_dir>`, compiles (where needed) and runs every
solution on every `<case_dir>/<prob>.in` file, writing each program's
stdout to `<case_dir>/../out/<lang>_<prob>.txt` (creating `out/` if
needed). The judge does not use `run_all.sh` for grading (it drives each
solution itself, so a broken driver cannot mask a broken solution), but
`run_all.sh` must work: the judge runs it once as a smoke gate.

Required interface per solution (the judge relies on this):

| language | file | how the judge runs it |
|---|---|---|
| python | `sumsq.py` etc. | `python3 <file>` (interpreted) |
| node | `sumsq.js` etc. | `node <file>` (interpreted) |
| go | `sumsq.go` etc. | compiled once per problem: `go build -o <tmp>/sumsq go/sumsq.go` |
| rust | `sumsq.rs` etc. | compiled once per problem: `rustc -O -o <tmp>/sumsq rust/sumsq.rs` |
| bash | `sumsq.sh` etc. | `bash <file>` (interpreted) |
| c | `sumsq.c` etc. | compiled once per problem: `gcc -O2 -o <tmp>/sumsq c/sumsq.c -lm` |

Each program reads the whole of stdin and writes exactly the expected bytes
to stdout. Exit code 0 on success.

## Judge gates (numeric pass rules)

The judge (`judge/grade.sh` → `judge/grade.py`) runs the following gates.
Every gate must pass for a green verdict.

| # | gate | numeric rule |
|---|---|---|
| G1 | **structure** | all 18 solution files + `run_all.sh` exist under the artifact root |
| G2 | **compiles** | every compiled language (go, rust, c) builds every problem with the pinned compiler, exit 0, within 60 s per build |
| G3 | **oracle match** | for each of the 18 (language, problem) pairs and each seeded case, the program's stdout is **byte-identical** to the Python oracle's stdout on the same input |
| G4 | **case count** | each problem has ≥ 3 seeded cases (edge + random), generated with `--seed` |
| G5 | **run time** | each interpreted/compiled run finishes within 10 s wall (a timeout fails the gate) |
| G6 | **run_all.sh smoke** | `bash run_all.sh <case_dir>` exits 0 and produces 18 non-empty output files |
| G7 | **timing table** | compile and run wall time recorded per language into the verdict JSON `timing` key |

The oracle (`judge/oracle.py`) is an independent Python implementation of
the three problems, written from the problem statements above. It shares no
code with any solution. The judge generates cases with
`judge/gencases.py --seed N` (deterministic: same seed → same cases).

## Acceptance oracle

The judge fails (non-zero exit) if any gate fails. The self-test
(`judge/selftest.sh`) proves the judge can fail: the known-good example in
`examples/good/` must pass all gates, and each of the six single-edit mutants
generated by `judge/mutate.py` must fail at least one gate. The required kill
rate is ≥ 90 % (6/6 = 100 %).

## Tools (pinned by the judge)

| tool | what | how pinned |
|---|---|---|
| Python 3.12 | oracle + judge + interpreted solutions | system python3 (Debian bookworm) |
| Node.js 24.x | interpreted solutions | system node (Debian bookworm) |
| Go 1.27.x | compiled solutions | system go (Debian bookworm) |
| Rust 1.98.x | compiled solutions | system rustc/cargo (Debian bookworm) |
| gcc 12.2.0 | compiled C solutions | system gcc (Debian bookworm) |
| Bash 5.2 | interpreted solutions | system bash (Debian bookworm) |

All tools are already present in the Debian bookworm image the judge runs
in; `judge/setup.sh` verifies each tool's presence and exact version, and
fails if any is missing or mismatched. No tool is downloaded with `latest`;
no network fetch is needed at grade time.

## Deviations from the brief (lead's ask)

The brief said "compiles/runs every solution with fixed stdin cases
(generated with a seed, judge holds a reference implementation)". Here the
reference implementation is `judge/oracle.py` (Python, stdlib only), the
cases are generated by `judge/gencases.py --seed N`, and the comparison is
byte-exact stdout equality per (language, problem, case). The brief's
"records compile and run wall time per language into a table" is gate G7.
