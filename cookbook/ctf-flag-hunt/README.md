# ctf-flag-hunt — build a CTF range a judge can grade

An agent has to *build* a security target, not just break one: produce five
self-contained C services, each vulnerable in exactly one specified way
(off-by-one, path traversal, weak crypto, config leak, logic bug), where the
flag of each service is reachable **only** by exploiting it. The judge is a
scripted reference exploit plus independent oracles — an out-of-range note
id, a `../` path, a token recomputed in Python from public inputs, a
misparsed admin mode — and it compares each captured flag by sha256 against
the flag it generated for that run. A range that "runs fine" but leaks its
flags on the legitimate path fails the negative control; a range that fixes
a vulnerability fails the oracle. A disposable sandbox is the right place
for this: the agent needs a compiler, a throwaway filesystem to run the
range in, and a judge it cannot tamper with — and the graded artifact is
five small source files it hands back.

## Results

The judge verdict for `examples/good` (seed `20261015`):

- **Flags captured**: 5/5, each matched by `sha256` against its plant
- **Independent oracle checks**: 5/5 (token recomputed in Python, files
  read differentially, out-of-range ids refused)
- **Negative control**: 0/5 flags on the legitimate action set, and 0
  hits from a flag sweep over the artifact, the binaries and the docroot
- **Blast radius**: clean — no file added, removed or modified
- **Self-test kill rate**: 7/7 = 100 % (requirement ≥ 90 %)

The judge writes one JSON verdict; every gate above is a numeric pass rule
(see `SPEC.md`). Figures and video are produced by a later task and are not
part of this one.

## Ask your agent

> Set up a sandbox and solve the demo in `cookbook/ctf-flag-hunt/` of
> https://github.com/agent-next/sandbox (clone it first). Run
> `bash cookbook/ctf-flag-hunt/judge/setup.sh`, read
> `cookbook/ctf-flag-hunt/SPEC.md`, then write the artifact yourself: five
> C services — `notes.c` (off-by-one), `retrieve.c` (path traversal),
> `token.c` (weak crypto), `status.c` (config leak), `admin.c` (logic bug)
> — each vulnerable exactly as the SPEC pins it, each releasing its flag
> only when its own exploit is used and refusing every other input. The
> judge plants `range.conf`, the notes file, the document root and the flag
> files; your sources must not contain them. Iterate with
> `bash cookbook/ctf-flag-hunt/judge/grade.sh <your-dir> --json v.json`
> until it exits 0, then paste the final verdict JSON. Do not edit anything
> under `judge/`; if you believe the judge is wrong, say so instead of
> working around it. Kill the sandbox when you are done.

The known-good range in `examples/good/` is one valid answer; any
implementation that meets the pinned interfaces and observables passes.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/ctf-flag-hunt/run.py          # --ref main --keep supported
```

Creates a sandbox, clones the repo, installs the pinned tools, runs the
judge self-test, grades `examples/good`, prints the verdict JSON, then kills
the sandbox and confirms it is gone. Stdlib only; exits non-zero on any
failure, naming the sandbox id if cleanup cannot be confirmed.

## Measured wall time (Debian sandbox, 2 vCPU)

| step | wall time |
|---|---|
| `git clone --depth 1` | ~1 s |
| `judge/setup.sh` (fresh install) | ~20 s (idempotent re-run: 0.3 s) |
| `judge/selftest.sh` (good + 7 mutants + determinism) | 23 s |
| `judge/grade.sh examples/good` | 2.7 s |

Grading is seconds; the self-test is ~24 s because it grades the good range
plus seven mutants plus two determinism runs, each a full compile-and-
exploit pass. `run.py` prints a per-step timing line.

## Limits, plainly

- **Deliberately vulnerable, by design.** The five services are the target,
  not the solution: each has exactly one planted flaw. What is graded is
  that the flaw is the specified one and that no *other* input leaks a flag.
- **Local only, no network.** Every exploit is a process invocation (argv
  or stdin); nothing binds a port. C1 is a logical out-of-bounds table
  index, not memory corruption, so ASLR and stack layout are irrelevant.
- **The judge pins the vulnerability, not its discovery.** The class and
  observable of each flaw are fixed in `SPEC.md` so the judge is
  deterministic; the agent's freedom is in the implementation.
- **Flag secrecy is not graded against the operator.** The judge hands each
  service its flag in `CTF_FLAG`; a user who can read `/proc/<pid>/environ`
  can read it. The negative control covers *service* behaviour, not the
  environment — see SPEC non-goals.
- **The judge pins gcc 12.2.0** (`gcc-12` Debian bookworm) and needs
  `sudo` once for the install; a non-Debian base image would need a
  different pin.
- **Determinism is per seed.** Two `grade.sh` runs with the same `--seed`
  produce byte-identical verdict JSON except the `timing` key; the flags
  change with the seed, so no constant can match.
