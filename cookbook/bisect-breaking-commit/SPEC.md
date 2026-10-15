# SPEC — `cookbook/bisect-breaking-commit/`

An agent works on a real regression-bisection problem inside disposable
agent-next sandboxes: a test broke and nobody knows when. One sandbox per
suspect commit reposes the fixture repo and runs the suite in parallel, and the
culprit commit is named with the receipts. A judge it cannot fool (a planted
regression + an analytic oracle + a negative control + a measured-speedup gate)
decides whether the result is right.

## Goal

Given a fixture repo whose history contains exactly one regression (a
whitespace-sensitive parse change), identify the exact commit that introduced
it, evidenced by its neighbours (N−1 passes, N fails), produce the diff of that
commit, and show that the parallel sweep beats a single-machine serial baseline
by a numeric factor.

## Non-goals

- Real-world VCS forensics: no `git bisect` walk, no binary search, no
  real-repo archaeology. The task is a fixed range of 11 commits (20..30).
- Any build system, dependency management, or language runtime beyond the
  stdlib. The fixture is pure Python; the judge shells out to `git` and
  `python3`.
- The parallel-orchestration *mechanism* (threads, subprocesses, sandbox API):
  the artifact is the verdict, not the orchestrator.

## Fixture (`fixture/make_fixture.py`, seeded, offline)

- 31 commits (`NUM_COMMITS = 31`), subjects `chore: bump version to <i>`;
  `version.txt` holds the commit number.
- The commit at `PLANTED_INDEX = 25` is the planted regression: the parser's
  terminator check changes from `line == END` to `line.strip() == END`, so an
  indented `\tENDCASE` is silently accepted instead of rejected.
- **Deterministic SHAs**: every commit is written with pinned
  `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` (base `2026-01-01T00:00:00Z` + i min),
  fixed author and fixed tree content. Any two builds of the fixture at the
  same seed produce byte-identical commit SHAs — this is what lets the judge,
  the sweep sandboxes and the known-good example agree on a SHA without
  sharing state.
- The suite carries a fixed settle delay (`SOAK_S = 2.0` s) standing in for
  real-suite I/O, so per-commit cost is latency-dominated (as real test suites
  and sandbox lifecycles are). This is what the speedup gate overlaps; on
  2 vCPU the CPU work alone caps at ~1.2×.
- `--revert-planted` writes the same history with the planted change reverted
  (the negative-control fixture: no regression in range).

## Artifact

A single JSON file (what `judge/grade.sh <artifact>` grades):

```json
{
  "identified_commit": "<40-hex SHA of the commit the sweep blames>",
  "identified_index": 25,
  "evidence": {"n_minus_1_passes": true, "n_fails": true},
  "diff": "<git show --format= output at the identified commit>",
  "serial_seconds": <wall of the 11-commit sweep on one machine, serially>,
  "parallel_seconds": <wall of the 11-sandbox parallel sweep>,
  "speedup": serial_seconds / parallel_seconds,
  "sandboxes_used": 11
}
```

The known-good example is produced by the sweep (the same command sequence
`run.py` sends to its sandboxes) against the fixture at the pinned seed.

## Judge gates (`judge/grade.sh <artifact> [--seed N] [--json out.json]`)

All gates are numeric and deterministic; checked in order, first failure wins.
Exit 0 only if every gate passes.

- **G1 structure**: valid JSON object with every field above present and
  correctly typed; `identified_commit` is 40 hex chars; timings positive;
  `sandboxes_used` an int.
- **G2 timing arithmetic**: `speedup` equals `serial_seconds /
  parallel_seconds` within 1 % — no invented numbers.
- **G3 identified**: the judge rebuilds the fixture at the pinned seed (same
  SHAs by construction) and requires `identified_commit` == the planted SHA
  (`git rev-parse HEAD~5`) and `identified_index` == 25. No other SHA is
  accepted — a neighbour with a plausible diff still fails.
- **G4 neighbours**: the judge sweeps the range 20..30 itself (fresh clone per
  commit, suite per commit) and requires index 24 to pass and 25 to fail; the
  artifact's `evidence` booleans must match those measurements exactly.
- **G5 diff**: `diff` equals `git show --format=` at the planted commit
  (whitespace-normalised comparison — the planted change *is* whitespace, both
  sides are normalised the same way).
- **G6 negative control**: the judge runs the *same sweep logic* against the
  `--revert-planted` fixture; it must report `"no regression in range"` —
  never a commit SHA. A sweep that always names a commit fails here.
- **G7 speedup**: (a) the artifact's own `speedup` ≥ 3.0 (its receipts), and
  (b) the judge's own measurement — the same 11-commit sweep serially vs in
  parallel on the grading machine — ≥ 3.0. Measured walls live under `timing`
  in the verdict; the pass flag is the only timing-derived verdict bit, stable
  because the fixture's settle delay gives ≥ 2× margin over the 3.0 threshold
  on 2 vCPU.
- **G8 sandboxes**: `sandboxes_used` == 11, one sandbox per suspect commit.

## Acceptance oracle (independent of "it ran")

1. **Planted regression**: the fixture is regenerated from the pinned seed and
   the planted SHA is derived from the build itself (`git rev-parse`), not
   from the artifact or from a stored expected value.
2. **Sweep, not trust**: the judge re-runs the suite at every commit in the
   range in fresh clones and derives the first-failing index itself; the
   artifact only matches or fails.
3. **Negative control**: the identical sweep code path on the reverted fixture
   must find no failing commit. This proves the oracle detects *absence* of a
   regression rather than always naming index 25.
4. **Speedup**: both serial and parallel walls are measured, not asserted —
   the artifact's pair and the judge's own pair; each pair's ratio must clear
   3.0× by overlapping per-commit latency (settle delay; in the sandbox run,
   sandbox create/clone/exec latency), which is the honest physics of parallel
   sandbox bisection on 2 vCPU.

## Self-test (`judge/selftest.sh`)

- The known-good artifact passes all gates.
- ≥ 5 known-bad single-edit mutants of the good artifact (generated by
  `judge/mutants.py`, one edit each: wrong SHAs, wrong index, flipped
  evidence, trimmed diff, broken speedup arithmetic, sub-threshold speedup,
  wrong sandbox count, missing field) each fail ≥ 1 gate.
- Kill rate ≥ 90 % printed; exit non-zero otherwise.
- Determinism: two `grade.sh` runs with the same seed produce identical
  verdict JSON after removing the `timing` key.

## Judge-integrity rule

The artifact under test is copied to a scratch dir before grading; `judge/` is
sha256-checksummed before and after every grade and the grade fails closed if
anything changed.

## Tools (pinned by `judge/setup.sh`)

- git **1:2.39.5-0+deb12u3** (Debian bookworm, sha256-checked `.deb` from
  `judge/package-sha256.txt`; installed only if the system git does not match
  the pin) — idempotent, exact-version.
- Python ≥ 3.10, stdlib only, for the judge math.
- No third-party Python packages, no network access at grade time.
