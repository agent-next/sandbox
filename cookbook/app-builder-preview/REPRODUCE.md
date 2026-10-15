# app-builder-preview — independent reproduction

Recorded by an independent agent (a different model family from the
builder), following only `README.md` in fresh sandboxes. It read
`README.md`, `DEMO-STANDARD.md` and `run.py`; it did not read the judge
source to drive the run.

## Reproduction record

**The independent reproduction did not complete.** Two attempts, each cut
off before the `selftest` step reported; no exit code and no verdict were
produced by the reproducer itself.

| attempt | sandbox | reached | outcome |
|---|---|---|---|
| 1 | `01a140be-b28a-7ab0-b841-0a364513b4e0` | `[setup]` ok (81 s) | `[selftest]` never returned; task stopped at its limit |
| 2 | `01a140cc-8c85-75c1-8082-84455dfdba89` | `[setup]` ok (204 s) | selftest alive at +9 min, gone by +24 min; client stopped, sandbox then expired |

Both sandboxes were created by the reproducer's own runs, killed by id, and
confirmed gone with `sbx list`. The reproducer modified no repository file.

### What it did observe

- `judge/setup.sh` completed cleanly in both attempts: node v22.23.3,
  Chromium 153.0.8010.12 (rev 1243) twice, launch probe ok.
- The `layout` gate accepted the ref (it had earlier rejected it for the
  then-missing `RECEIPT.md`/`REPRODUCE.md`).
- Attempt 2's setup took 204 s against the README's ~75 s, with three runs
  contending for the 2-vCPU template (load average ~2.3); attempt 1,
  uncontended, took 81 s.

### Numbers from the two runs that did complete

Those runs were made by this branch's own acceptance runs (not by the
reproducer), and are the ones recorded in `RECEIPT.md`; they agree with the
reproducer's partial observations on setup. The reproducer reports its
attempts as truncated, **not** as a disagreement with `RECEIPT.md`.

## Status

An independent reproduction that completes end to end is **still required
before this demo is merged** (`DEMO-STANDARD.md`, "Independent
reproduction"). This record documents the attempt and its failure mode; it
is not a passing reproduction. The likely cause is contention: the
browser-driven `selftest` step takes ~10–11 min uncontended and is the
step that was still running when each attempt was cut off.
