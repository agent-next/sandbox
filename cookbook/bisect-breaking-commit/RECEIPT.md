# RECEIPT — `cookbook/bisect-breaking-commit/`

Two fresh acceptance runs of the one-command driver (`run.py`), which wraps
the judge steps below. Both runs were driven from a clean clone outside the
repo, on the builder's workstation (Debian bookworm, Python 3.12.15,
git 2.39.5, `sbx` CLI 0.0.1), against fresh sandbox instances (Debian
bookworm, 2 vCPU; the tools they ran record `judge/VERSIONS.txt`). Every
block below is pasted from a real run with its exit code; nothing is
invented.

## Fresh run 1 — 2026-10-15, ref `sbx/demo-bisect-breaking-commit-f6` (cd5280e)

```bash
git clone -q -b sbx/demo-bisect-breaking-commit-f6 https://github.com/agent-next/sandbox /tmp/acc2/repo
cd /tmp/acc2/repo/cookbook/bisect-breaking-commit
python3 run.py --ref sbx/demo-bisect-breaking-commit-f6   # exit 0
```

```
[run] create sandbox (utility: ref/selftest/serial/grade)    2.1s  exit=0
[run] clone repo (utility)                  4.6s  exit=0
[run] stage fixture/one_commit from ref     2.3s  exit=0
[run] judge/setup.sh                        2.7s  exit=0
[run] judge/selftest.sh                   166.9s  exit=0
[run] ref sbx/demo-bisect-breaking-commit-f6: sweeping commits 20..30 (11 sandboxes in parallel)
[run] created 11 sandboxes in 11.05s
[run]   commit 20: pass (4c9d39ae0923)
[run]   commit 21: pass (e8b5e7933178)
[run]   commit 22: pass (eb2f304dab48)
[run]   commit 23: pass (996f9abaf2f8)
[run]   commit 24: pass (dab148927932)
[run]   commit 25: FAIL (5095cf335e19)
[run]   commit 26: FAIL (ef111eef235c)
[run]   commit 27: FAIL (e2a676584c45)
[run]   commit 28: FAIL (7f78f4e896d6)
[run]   commit 29: FAIL (7576369ce269)
[run]   commit 30: FAIL (5cbb735dd30d)
[run] parallel sweep: 20.63s
[run] killed 11 sweep sandboxes in 13.42s
[run] serial commit 20 .. serial commit 30 (11 execs, one machine)   exit=0
[run] serial baseline: 94.1s over 11 commits (one exec each, 1 machine)
[run] negative control (reverted fixture)    7.9s  exit=0
[run] judge/grade.sh sweep_report.json     48.4s  exit=0
[run] culprit  : 5095cf335e19621f8bef90019c5c4381e574b581 (index 25)
[run] evidence : N-1 passes=True, N fails=True
[run] speedup  : 4.56x (serial 94.1s vs parallel 20.6s over 11 sandboxes)
[run] timings:
[run]   create_sandboxes_s            11.05s
[run]   grade_s                       48.45s
[run]   kill_sandboxes_s              13.42s
[run]   negative_control_s             7.93s
[run]   parallel_sweep_s              20.63s
[run]   selftest_s                   166.87s
[run]   serial_sweep_s               94.12s
[run] PASS
[run] confirmed: all 12 sandboxes this run created are gone (`sbx list` shows none of their ids)
RC=0
```

## Fresh run 2 — 2026-10-15, ref `sbx/demo-bisect-breaking-commit-f6` (7d8d7ec)

Same commands as run 1 (clone at `/tmp/acc3/repo`). Exit 0.

```
[run] create sandbox (utility: ref/selftest/serial/grade)    4.0s  exit=0
[run] clone repo (utility)                  5.7s  exit=0
[run] stage fixture/one_commit from ref     2.7s  exit=0
[run] judge/setup.sh                        2.6s  exit=0
[run] judge/selftest.sh                   180.6s  exit=0
[run] created 11 sandboxes in 16.79s
[run]   commit 20: pass (4c9d39ae0923)
[run]   commit 21: pass (e8b5e7933178)
[run]   commit 22: pass (eb2f304dab48)
[run]   commit 23: pass (996f9abaf2f8)
[run]   commit 24: pass (dab148927932)
[run]   commit 25: FAIL (5095cf335e19)
[run]   commit 26: FAIL (ef111eef235c)
[run]   commit 27: FAIL (e2a676584c45)
[run]   commit 28: FAIL (7f78f4e896d6)
[run]   commit 29: FAIL (7576369ce269)
[run]   commit 30: FAIL (5cbb735dd30d)
[run] parallel sweep: 22.33s
[run] killed 11 sweep sandboxes in 13.32s
[run] serial baseline: 97.1s over 11 commits (one exec each, 1 machine)
[run] negative control (reverted fixture)    9.0s  exit=0
[run] judge/grade.sh sweep_report.json     51.0s  exit=0
[run] culprit  : 5095cf335e19621f8bef90019c5c4381e574b581 (index 25)
[run] evidence : N-1 passes=True, N fails=True
[run] speedup  : 4.35x (serial 97.1s vs parallel 22.3s over 11 sandboxes)
[run] timings:
[run]   create_sandboxes_s            16.79s
[run]   grade_s                       51.01s
[run]   kill_sandboxes_s              13.32s
[run]   negative_control_s             9.03s
[run]   parallel_sweep_s              22.33s
[run]   selftest_s                   180.62s
[run]   serial_sweep_s               97.10s
[run] PASS
[run] confirmed: all 12 sandboxes this run created are gone (`sbx list` shows none of their ids)
RC=0
```

The per-commit receipts are byte-identical across both runs (seeded fixture,
pinned commit dates → pinned SHAs).

## Key numbers, side by side

| number | run 1 | run 2 | tolerance (SPEC.md) |
| --- | --- | --- | --- |
| culprit SHA | `5095cf33…b581` | `5095cf33…b581` | exact |
| culprit index | 25 | 25 | exact |
| pass/fail boundary | 24 pass, 25..30 fail | 24 pass, 25..30 fail | exact |
| artifact serial / parallel | 94.12 s / 20.63 s | 97.10 s / 22.33 s | walls may vary |
| artifact speedup (G7) | 4.56× | 4.35× | ≥ 3.0× |
| judge's own re-measure (G7) | 9.88× | 10.07× | ≥ 3.0× |
| sandboxes used (G8) | 11 | 11 | = 11 |
| selftest kill rate | 9/9 (100 %) | 9/9 (100 %) | ≥ 90 % |
| verdict | passed (8/8 gates) | passed (8/8 gates) | all gates |
| run.py exit | 0 | 0 | 0 |
| cleanup confirmed (`sbx list`) | yes, all 12 | yes, all 12 | required |

## Judge steps inside the run (fresh sandbox, exit codes from `run.py`)

- `judge/setup.sh` — exit 0 (2.7 s / 2.6 s):

  ```
  [setup] python3 3.12 (stdlib only, no packages to install)
  [setup] git 1:2.39.5-0+deb12u3 already installed
  git version 2.39.5
  ```

  The image already carries the pinned version; the download+install path is
  exercised by `--force` and sha256-pins every package against
  `judge/package-sha256.txt` (`2 packages match`, exit 0 — verified during
  development). Tools' own `--version` output: `judge/VERSIONS.txt`.

- `judge/selftest.sh` — exit 0 (166.9 s / 180.6 s). Real output (run 1;
  run 2 identical apart from walls):

  ```
  [selftest] Regenerating mutants...
  ... 9 mutants in .../examples/bad

  [selftest] Known-good artifact (must PASS):
  [selftest]   good/report.json  PASS  (45s)

  [selftest] Determinism check (same seed twice, verdict JSON except 'timing'):
  identical
  [selftest]   deterministic (verdicts identical apart from timing)

  [selftest] Known-bad mutants (must FAIL):
  [selftest]   false_evidence_n  killed (failed gate: neighbours)
  [selftest]   false_evidence_prev  killed (failed gate: neighbours)
  [selftest]   invented_speedup  killed (failed gate: timing_arithmetic)
  [selftest]   missing_field  killed (failed gate: structure)
  [selftest]   one_sandbox  killed (failed gate: sandboxes)
  [selftest]   trimmed_diff  killed (failed gate: diff)
  [selftest]   wrong_index  killed (failed gate: identified)
  [selftest]   wrong_sha_next  killed (failed gate: identified)
  [selftest]   wrong_sha_prev  killed (failed gate: identified)

  [selftest] ============================================
  [selftest] good artifact    : PASS
  [selftest] determinism      : identical
  [selftest] mutants killed   : 9/9 (100%)
  [selftest] ============================================
  [selftest] SUCCESS
  ```

- `judge/grade.sh sweep_report.json` — exit 0 (48.4 s / 51.0 s) on the
  artifact the sweep just wrote; verdict gate highlights (run 1):

  | gate | key numbers |
  | --- | --- |
  | G3 identified | planted `5095cf33…b581` == claimed `5095cf33…b581`, index 25/25 |
  | G4 neighbours | N−1 passed=true, N fails=true, judge sweep first_fail=25 |
  | G5 diff | expected/claimed len 520/520, whitespace-normalised equal |
  | G6 negative control | sweep on reverted fixture: `"no regression in range"`, 11 commits tested |
  | G7 speedup | artifact 4.56× (94.122 s / 20.63 s) ≥ 3.0; judge's own re-measure 9.88× (36.202 s / 3.666 s) ≥ 3.0 |
  | G8 sandboxes | 11/11 |

  ```
  "timing": {
    "parallel_sweep_s": 3.666,
    "negative_control_sweep_s": 3.619,
    "serial_sweep_s": 36.202,
    "judge_measured_speedup": 9.88,
    "wall_seconds": 45.879
  }
  ```

  (Run 2: artifact 4.35× (97.101 s / 22.33 s), judge re-measure 10.07×.)

The checked-in good example itself was produced by the sweep
(`python3 sweep/local_report.py examples/good/report.json`, seed 20261015):

```
culprit index 25 sha 5095cf335e19621f8bef90019c5c4381e574b581
serial 47.3s / parallel 8.1s = 5.85x over 11 workers
```

## Deviations

- An earlier acceptance run of the same driver (pre-cd5280e) failed G7 with
  artifact speedup 2.09×: the serial baseline then ran as one bash loop
  inside a single exec, which hides the per-exec gateway cost the parallel
  sweep pays 11×. cd5280e made the baseline one exec per commit — the same
  command the sweep sends each sandbox — and both runs above clear the gate.
- The suite's per-commit cost is a fixed 2.0 s settle delay standing in for
  real-suite I/O (stated in SPEC.md); this keeps each grade in minutes on
  2 vCPU.
- The fixture is generated by a seeded script; there are no third-party data
  downloads to cite beyond Debian's `git` package (bookworm,
  1:2.39.5-0+deb12u3, sha256 in `judge/package-sha256.txt`, Debian Free
  Software Licence / GPL-2.0 as packaged).
- Media are regenerated from run 1's outputs by `media/make_media.sh`; their
  numbers (speedup 4.56×, kill rate 9/9) therefore match run 1 above.
