# background-coding-agent — a coding agent a judge can grade

The "assign an issue, get a pull request" workflow, made checkable. An
agent is handed a small pinned repository with an open issue and works it
inside a disposable sandbox: it edits the code, runs the project's own
tests, and hands back a branch — a `delivery.patch` and a `PR.md`. A judge
it cannot fool applies that patch to a clean checkout of the pinned
repository and decides whether the delivery is correct. The agent never
sees the hidden acceptance suite or the judge's reference implementation,
so "the tests passed and it printed something" is not enough: the judge
recomputes every statistic itself from the raw data and grades the
delivery on inputs the agent never saw. A disposable sandbox is the right
place for this: the agent needs a throwaway checkout to iterate in, and
the graded artifact is one small diff it hands back.

## Ask your agent

> Set up a sandbox and solve the demo in `cookbook/background-coding-agent/`
> of https://github.com/agent-next/sandbox (clone it first). Read
> `cookbook/background-coding-agent/SPEC.md` and
> `cookbook/background-coding-agent/fixture/ISSUE.md`. Then act as a
> background coding agent on the issue yourself: work in a scratch copy of
> `cookbook/background-coding-agent/fixture/`, add the `--json` output the
> issue describes, run `python -m pytest` and
> `ruff check --config cookbook/background-coding-agent/judge/ruff.toml .`
> until they are clean, and produce two files — `delivery.patch` (a
> `git diff` against the clean fixture) and `PR.md` (a summary and a test
> plan). Iterate with
> `bash cookbook/background-coding-agent/judge/grade.sh <your-delivery.patch> --json v.json`
> until it exits 0, then paste the final verdict JSON. Do not edit anything
> under `judge/`, and do not edit the fixture's `tests/` — the judge treats
> both as its own. If you believe the judge is wrong, say so instead of
> working around it. Kill the sandbox when you are done.

The known-good delivery in `examples/good/` adds a small `jsonout.py`
module and three lines to the CLI; a correct answer does not have to
resemble it.

## Results

Key numbers from the judge verdict (`examples/good/delivery.patch`, seed
`20261015`):

- **Patch gate**: 2 files, 47 added lines, 4 hunks (limits 1..20 files,
  ≤ 2000 lines)
- **Regression gate**: 26/26 of the fixture's own tests pass (needs 0
  failed, ≥ 12 collected)
- **Acceptance gate**: 23/23 hidden tests pass (needs 0 failed, ≥ 18
  collected)
- **Lint gate**: 0 ruff 0.16.9 diagnostics (judge-owned config)
- **Oracle gate**: 3/3 inputs agree with `judge/reference.py` to
  1e-9 relative — the sample plus two seeded synthetic files
- **PR gate**: 1253-char `PR.md`, both required sections, 2/2 changed
  files named
- **Self-test kill rate**: 11/11 = 100 % (requirement ≥ 90 %, ≥ 5 mutants)

Media (`media/`) is added by a later task; the numbers above come from the
verdict JSON pasted in `RECEIPT.md`.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/background-coding-agent/run.py    # --ref main --keep supported
```

Creates a sandbox, clones the repo, installs the pinned tools, runs the
judge self-test, grades `examples/good/delivery.patch`, prints the verdict
JSON and a one-line summary, then kills the sandbox and confirms it is
gone. Stdlib only; exits non-zero on any failure, naming the sandbox id if
cleanup cannot be confirmed.

## Measured wall time (Debian sandbox, 2 vCPU)

| step | wall time |
|---|---|
| `git clone --depth 1` | ~1 s |
| `judge/setup.sh` (fresh install) | 65–70 s (network-bound; idempotent re-run: ~5 s) |
| `judge/grade.sh examples/good/delivery.patch` | 17–23 s |
| `judge/selftest.sh` (good + 11 mutants + determinism) | ~3 min 40 s |

Grading one delivery is ~20 s: three pytest runs, one ruff run and three
CLI invocations. The self-test grades 14 deliveries (good + 11 mutants +
two determinism re-runs), so budget ~4 minutes. `run.py` prints a
per-step timing line.

## The fixture

`fixture/` is a vendored, stdlib-only snapshot of `measurectl` — a CSV
summariser with its own 26-test suite and one sample input. It is pinned
by content in `judge/FIXTURE.sha256` (12 files); the judge **fails closed**
if the checkout it is about to grade differs from that manifest. The issue
(`fixture/ISSUE.md`) asks for a `--json` output flag with a documented
schema. The fixture is original to this demo — no third-party code is
vendored, so there is nothing to cite.

## Limits, plainly

- The judge grades the two delivered files only. It does not look at the
  agent's sandbox, its commit history, or how it found the answer.
- The `--json` contract is graded structurally (key sets, types, ordering)
  and numerically (1e-9 relative against `judge/reference.py`). "Reasonable
  output" that is not the documented schema fails.
- `judge/setup.sh` downloads four pinned wheels from PyPI (ruff, pytest
  and their dependencies) and builds two venvs under
  `$HOME/.local/share/measurectl-judge`. A non-network base image would
  need those wheels vendored instead.
- The oracle's seeded inputs are generated from `--seed`; the default is
  fixed, so the graded inputs are deterministic and reproducible, but they
  are the judge's inputs, not a claim about every possible CSV.
- `run.py` needs `sbx` and a key and was verified here by running its exact
  in-sandbox command sequence directly (this authoring sandbox cannot
  create cloud sandboxes) — see `RECEIPT.md`.
