# layerfs-race — independent reproduction

A different agent from the builder ran the README's one-command path from
the pushed branch, in a fresh default sandbox (2 vCPU, ~4 GB), with no local
files uploaded:

```
python3 cookbook/layerfs-race/run.py --ref sbx/layerfs-race-20261019
```

Commit under test: `d26d748b3f6ea13448f9119d8f0a642c0690d67e`.

## Output (verbatim step lines)

```
[  0.6s] sandbox 01a157f7-4258-7cc1-b213-6e9e81cf3af9
[   3.0s] clone: ok
[   0.6s] clone-commit: ok
[ 286.0s] setup: ok
[3307.2s] selftest: ok
    selftest: mutant KILLED: claim-wrong-winner (failing gates: winner-is-a-branch)
    selftest: mutant KILLED: cp-a (failing gates: artifact,artifact-exit)
    selftest: mutant KILLED: doctored-base (failing gates: base-intact)
    selftest: mutant KILLED: fix-main-fs (failing gates: artifact,artifact-exit)
    selftest: mutant KILLED: fs-write-only (failing gates: branches)
    selftest: mutant KILLED: lie-volume (failing gates: artifact)
    selftest: mutant KILLED: merge-markers (failing gates: winner-green)
    selftest: mutant KILLED: publish-loser (failing gates: main-isolation,winner-is-a-branch,oracle-intact,base-intact,winner-green,losers-red)
    selftest: mutant KILLED: publish-nothing (failing gates: main-isolation,winner-is-a-branch,oracle-intact,base-intact,winner-green,losers-red)
    selftest: mutant KILLED: seven-branches (failing gates: branches,oracle-intact,losers-red)
    selftest: mutant KILLED: shift-candidates (failing gates: main-isolation,winner-is-a-branch,oracle-intact,base-intact)
    selftest: kill rate: 11/11 (100%)
    selftest: determinism PASS (same seed -> identical verdict outside timing)
[ 334.5s] grade: ok
commit: d26d748b3f6ea13448f9119d8f0a642c0690d67e
verdict: PASS
sandbox 01a157f7-4258-7cc1-b213-6e9e81cf3af9 removed
```

## Gates of the final grade

| gate | pass | detail |
|---|---|---|
| artifact | yes | manifest ok (winner claim agent-3) |
| bug-scope | yes | 2 failing on the bugged tree (allowed 1-50) |
| branches | yes | agent-0..7 present, each with `via:exec` commits |
| main-isolation | yes | main moved only via publish (layer source agent-3) |
| winner-is-a-branch | yes | empty diff vs main: agent-3; claimed agent-3; expected agent-3 |
| oracle-intact | yes | every branch/main change vs the bugged base is confined to `/lib/` |
| base-intact | yes | pre-publish base tree byte-identical to the judge's bugged tree |
| winner-green | yes | main: 1238 passing / 0 failing, suite exit 0 (baseline 1238) |
| losers-red | yes | failing tests per loser: agent-0:3 agent-1:2 agent-2:5 agent-4:5 agent-5:5 agent-6:5 agent-7:2 |
| storage | yes | Store / source = 0.3002 |
| conflict-refused | yes | `Conflict` on `/lib/application.js` |
| fork-latency | yes | median `branch.fork` 0.0006 s |

## Comparison with RECEIPT.md (tolerances from SPEC.md)

| quantity | RECEIPT (f551e9df, `--local`) | this run (d26d748b, `--ref`) | within tolerance |
|---|---|---|---|
| verdict | PASS | PASS | yes |
| mutants killed | 11/11 | 11/11 | yes |
| main passing / failing | 1238 / 0 | 1238 / 0 | yes (exact) |
| Store / source | 0.2991 | 0.3002 | yes (+-20 %) |
| median fork | 0.0007 s | 0.0006 s | reported only |
| setup / selftest / grade | 289.8 / 3309.3 / 331.3 s | 286.0 / 3307.2 / 334.5 s | reported only |

Between the two commits the judge changed only in how the verdict travels
(stdout instead of a file), what the tree digest covers (types, modes and
symlink targets as well) and how express dependencies resolve
(`npm install --before`); the numbers agree.
