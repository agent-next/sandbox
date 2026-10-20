# layerfs-race — spec

## Goal

Eight agents race to fix the same bug in a real Node.js repository, each on
its own copy-on-write branch inside one disposable agent-next sandbox, using
[LayerFS](https://github.com/Ephemeral-AI-Lab/layerfs) (MIT) for the
branches. Each agent edits, runs the full test suite and commits on its
branch; the run publishes the one branch whose tests all pass to `main`.
The judge reads the LayerFS Store directly and re-runs the tests itself, so
it cannot be fooled by a manifest that only claims a winner.

## Fixed problem statement (judge constants)

| quantity | value |
|---|---|
| repository | `expressjs/express`, a pinned release tag and its commit SHA (recorded in `judge/VERSIONS.txt`), dependencies installed with `npm ci` from its lockfile, or `npm install` with the resolved tree recorded if the tag has no lockfile |
| LayerFS | tag `v0.1.7` (commit `e7713d03`), built from source in `judge/setup.sh` with Rust `1.85.1` |
| runtime image | `node:24.21.0-bookworm` pinned by digest (upstream `dsh/tools/history/runtime/Dockerfile`) |
| injected bug | one single-line edit in `lib/` that makes >= 1 and <= 50 tests of the pinned suite fail, applied to `main` before the race (`examples/bug.patch`) |
| candidate fixes | 8 patches in `examples/good/candidates/`, exactly 1 correct; the 7 others each leave >= 1 test failing |
| agents | K = 8, one branch and one LayerFS Sandbox each, running concurrently |

## Non-goals

- No LLM writes the candidate fixes: they are fixed patches, so the run is
  deterministic. The demo shows the branching substrate, not patch generation.
- LayerFS durability, crash recovery and multi-host Stores (upstream marks
  these as not supported in 0.1.7).
- Performance claims beyond the measured numbers in RECEIPT.md.

## Artifact

`examples/good/race.mjs`, a LayerFS SDK script. Run in the sandbox after
`setup.sh`, it initializes the project from the bugged repository, forks
`agent-0` .. `agent-7`, mounts each in its own Sandbox, applies candidate
`i`, runs the test suite, commits, merges two candidates once to show a
conflict, and publishes the winning branch to `main`. It writes
`race.json` (project name, Store volume, claimed winner, per-step timings)
and leaves the project and its Store volume for the judge.

## Judge gates (all must pass)

`judge/grade.sh <dir-with-race.mjs>` runs the artifact and then checks:

1. **branches** — 8 branches `agent-0..7` exist, each with >= 1 commit made
   with `via: "exec"` (from `branch.list_commits`, not from `race.json`).
2. **winner-green** — the judge mounts `main` in a fresh Sandbox and runs the
   pinned test suite itself: 0 failing, and the passing count equals the
   clean-baseline passing count measured in `setup.sh`.
3. **winner-is-a-branch** — `branch.diff_branches(main, <winner>)` is empty for
   exactly one `agent-i`, and that `i` names the correct candidate.
4. **losers-red** — for each of the other 7 branches the judge runs the
   suite on that branch: >= 1 failing test each.
5. **main-isolation** — at the Layer before publish, `main` equals the bugged
   source tree (bugged file byte-identical); no `agent-*` commit touched
   `main` except through `branch.publish`.
6. **conflict-refused** — a judge-run `branch.merge` of two candidates
   that edit the same hunk is refused with code `Conflict`, naming the file.
7. **storage** — Store volume bytes (`du -sb`) after the race <= 0.25 x
   K x source-tree bytes (measured 2026-10-19: 0.036).
8. **fork-latency** — median `branch.fork` time over forks 2..8 <= 0.050 s
   (measured 2026-10-19: 0.001 s).

Timing values live under the verdict's `timing` key; gates 7-8 compare
measured numbers against fixed thresholds.

## Acceptance oracle

The pinned express test suite, run by the judge on the published `main` and
on each losing branch, plus the clean-baseline pass count from an unbugged
checkout measured in `setup.sh`. The manifest's claimed winner is checked
against the Store, never trusted.

The oracle is protected from the artifact: the judge runs mocha with
`--no-config --no-package` on an explicit, judge-fixed test file list, and
the `oracle-intact` gate fails when any agent branch or `main` changes
anything outside `lib/` versus the bugged base (the judge diffs every ref
against a branch forked from the pre-publish layer). A submitted
`.mocharc`, test edit or `node_modules` swap cannot rig the result. The
suite's exit status is preserved and `winner-green` requires exit 0 *and*
0 failing *and* the baseline passing count. The artifact runs in a staged
directory without the grader; the grader itself runs from a private copy
whose sha256 is checked before and after, and a non-zero artifact or
grader exit forces an overall FAIL.

## Self-test

`judge/selftest.sh` requires `examples/good` to pass and >= 90 % of the
mutants from `judge/mutants.py` to fail at least one gate. Mutants are
single edits of `race.mjs`, at least: publish a losing branch; publish
nothing; write the fix to `main` with `fs.write` instead of a branch;
claim the wrong winner in `race.json`; skip `exec` (write files with
`fs.write` only); plain `cp -a` copies instead of LayerFS branches; merge
with markers left in and publish that. Two grades of `examples/good`
must give byte-identical verdict JSON outside `timing`.

## Tolerances for reproduction

Gates are pass/fail. Reproduced numbers: test counts exact; storage ratio
within +-20 % of RECEIPT; timings are reported but not compared.
