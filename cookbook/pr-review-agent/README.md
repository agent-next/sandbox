# pr-review-agent — a code review a judge can grade

An agent has to *review six pull requests* against a small pinned Python
service: localize every planted defect (file, line, severity, kind) in a
machine-readable `review.json`, and — the hard part — ship a test that
**fails on the PR as given and passes on the fix**. The judge runs the
reviewer's own tests both ways, so a finding you cannot demonstrate is worth
nothing: a review that "looks right" but whose test passes on the buggy code
too fails, and so does a confident `major` finding on one of the two clean
PRs. A disposable sandbox is the right place for this because the agent
needs a throwaway checkout to run tests in and a fixture it cannot tamper
with; the graded artifact is a handful of small files it hands back.

The fixture is 6 generated PR diffs against one pinned tree: 4 carry one
planted defect each (`off-by-one`, `sql-injection`, `none-deref`, `race`)
and 2 are clean — one a behaviour-preserving refactor, one an added function
with its test, so "any diff is a defect" is not a usable heuristic.

## Ask your agent

> Set up a sandbox and solve the demo in `cookbook/pr-review-agent/` of
> https://github.com/agent-next/sandbox (clone it first). Run
> `bash cookbook/pr-review-agent/judge/setup.sh`, read
> `cookbook/pr-review-agent/SPEC.md`, then do the review yourself: for each
> PR `k` in `1..6` read `judge/fixture/pr<k>.diff`, work out whether it
> introduces a defect, and write an artifact directory with
> `pr<k>/review.json` (findings: `file`, `line` — 1-based in the
> post-change file, `severity`, `kind`) and `pr<k>/tests/test_pr<k>.py`, a
> pytest module that FAILS on the PR as given and PASSES on the fix. Do not
> read `judge/oracle/` — that is the answer key and using it is cheating.
> Iterate with
> `bash cookbook/pr-review-agent/judge/grade.sh <your-dir> --json v.json`
> until it exits 0, then paste the final verdict JSON. Do not edit anything
> under `judge/`; if you believe the judge is wrong, say so instead of
> working around it. Kill the sandbox when you are done.

The known-good example in `examples/good/review/` is one working answer; a
working answer does not have to be written the same way.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/pr-review-agent/run.py          # --ref main --keep supported
```

Creates a sandbox, clones the repo, installs the pinned tools, runs the
judge self-test, grades `examples/good/review`, prints the verdict JSON and
a one-line summary, then kills the sandbox and confirms it is gone. Stdlib
only; exits non-zero on any failure, naming the sandbox id if cleanup could
not be confirmed.

## Key numbers from the judge verdict (`examples/good/review`)

- **Defects caught**: 4/4 (rule: all 4 planted defects matched at
  `|Δline| <= 2` with the right `kind` and `severity >= major`)
- **`major` findings on the 2 clean PRs**: 0 (rule: exactly 0)
- **Reviewer tests failing on the buggy PR**: 4/4 (pytest exit 1, ≥ 1 failed)
- **Reviewer tests passing on the fixed version**: 4/4 (pytest exit 0, ≥ 1 passed)
- **Self-test kill rate**: 10/10 = 100 % (requirement ≥ 90 %)
- **Verdict determinism**: two `--seed 1` runs identical but for `timing`

## Measured wall time (Debian sandbox, 2 vCPU / 4 GB)

| step | wall time |
|---|---|
| `git clone --depth 1` | ~1 s |
| `judge/setup.sh` (fresh venv + wheels) | ~40 s (idempotent re-run: ~6 s) |
| `judge/grade.sh examples/good/review` | ~28 s |
| `judge/selftest.sh` (good + 10 mutants + determinism) | ~7 min |

Grading is dominated by the reviewer's own tests: 12 pytest processes (6 PRs
× buggy/fixed) at ~2 s each, single-threaded. `run.py` prints a per-step
timing line.

## Limits, plainly

- The fixture is **generated and pinned by this demo**, not a clone of a
  public repository: `judge/fixture/make_fixture.py` writes the 6 diffs and
  the answer key from the pristine tree, and `setup.sh` re-checks that they
  agree (`make_fixture.py --check`). It is small on purpose, so a grade
  finishes in seconds.
- The judge grades **localization and demonstration**, not review prose: a
  finding is scored on `file`/`line`/`kind`/`severity` only, and comments,
  rationale and suggested patches are ignored.
- Line matching is deliberately forgiving (`±2` lines) and `kind` matching
  is exact; the four planted classes are the only ones that count.
- The race defect is a lost update on a **file-backed** counter, which
  reproduces under CPython's GIL; a purely in-memory `+=` on a small int
  often does not, so the fixture uses the file-backed form.
- `pytest` is the only downloaded tool (8.4.2, SHA256-pinned wheels). The
  demo needs **no** Debian packages — this image's apt lists are empty and
  the judge deliberately does not depend on apt.
- The reviewer's tests run in a copy of the tree with `judge/` absent, and
  the judge hashes its own tree before and after every grade; an artifact
  that tries to read the answer key or edit the judge fails closed.
