# layerfs-race — 8 agents race on copy-on-write LayerFS branches; the Store holds 0.30× the source and the judge re-runs the suite itself

Eight agents race to fix the same injected bug in a real express checkout
(pinned tag), each on its own copy-on-write branch inside one LayerFS Store
in a disposable agent-next sandbox. Each agent mounts its branch in a
LayerFS Sandbox, applies its candidate patch, runs the full pinned mocha
suite (1238 tests), and commits. The run publishes the one green branch to
`main`. The judge then reads the Store through the SDK — it never trusts
`race.json` — forks `main`, re-runs the suite on the published tree and on
every losing branch, checks the layer chain, the merge-conflict refusal,
Store bytes and fork latency. A manifest that only *claims* a winner cannot
fool it.

**Hero result:** judge verdict PASS — `main` re-tested at 1238/1238 passing,
each of the 7 losing branches independently red, Store = 0.30× the source
tree, median `branch.fork` 0.0006 s (see RECEIPT.md).

## Ask your agent

> Clone https://github.com/agent-next/sandbox into this sandbox and run
> `bash cookbook/layerfs-race/judge/setup.sh`. Then write a LayerFS SDK
> script like `examples/good/race.mjs` (contract: SPEC.md — init the bugged
> repo, fork `agent-0..7`, mount each in its own Sandbox, apply the
> candidate patch, run the suite, commit, publish the green one, write
> `race.json`). Iterate with `judge/grade.sh <dir>` until it prints `"PASS"`.

## One-command run

```bash
python3 run.py            # clones this repo at main into a fresh sandbox
python3 run.py --ref my-branch --keep
python3 run.py --local    # upload the local checkout (no push needed)
```

Needs the `sbx` CLI (`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and `SBX_API_KEY` (or `E2B_API_KEY`) in the environment.

Measured on a 2 vCPU / 4 GB sandbox (see RECEIPT.md):

| step | wall time |
|---|---|
| setup (rust build + express clone + baseline) | ~9 min |
| selftest (10 mutants + determinism) | ~25 min |
| grade the good artifact | ~3 min |
| **time-to-result (README -> hero)** | ~12 min |

## How the judge works

- `judge/setup.sh` — builds LayerFS v0.1.7 from source (Rust 1.85.1, offline
  locked build), builds the runtime image (`node:24.21.0-bookworm` pinned by
  digest), clones express v5.2.1 (commit-verified), installs deps (resolved
  tree recorded; `send` pinned to 1.1.0), and measures the clean-baseline
  pass count.
- `judge/grade.sh <artifact-dir>` — applies `examples/bug.patch` to a copy
  of the pinned tree, runs `race.mjs` against a fresh Store volume, then
  `judge/grader.mjs` checks all 8 SPEC gates + artifact/manifest and
  bug-scope gates through the SDK (list_commits, diff_branches,
  inspect.snapshot, fs.read, merge, publish, its own Sandboxes) and re-runs
  the suite on `main` and every losing branch. Prints one JSON verdict.
- `judge/selftest.sh` — the good artifact must pass, each of the 10
  single-edit mutants from `judge/mutants.py` must fail ≥1 gate (kill rate
  100% here; ≥90% required), and two grades of the good artifact are
  byte-identical outside `timing`.

## Limits

- No figures or video yet: this entry ships the judge, the one-command run
  and the receipts only.
- Time-to-result is about 38 min on the default 2 vCPU sandbox (setup ~5 min
  builds LayerFS from source; the 10-mutant self-test ~30 min), well over the
  5 min cookbook target, because LayerFS 0.1.7 publishes no binaries.

- The demo fixes deterministic patches — no LLM writes candidate fixes; the
  demo shows the branching substrate, not patch generation.
- LayerFS 0.1.7 is a preview: no durability/crash-recovery/multi-host Store
  claims (upstream marks these unsupported). The Store here is Disposable
  profile — it lives only for one sandbox run.
- Store bytes and timings are measured on a 2 vCPU sandbox; absolute numbers
  vary with hardware. Gates use SPEC-fixed thresholds, not the measured
  receipt values.
