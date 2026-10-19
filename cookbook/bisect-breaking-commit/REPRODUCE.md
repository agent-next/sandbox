# REPRODUCE — `cookbook/bisect-breaking-commit/`

Independent reproduction of the demo from `README.md` alone, on 2026-10-15.

**Who ran it.** A second agent session, separate from the one that built the
demo (different provider/model than the build session; same machine account).
It received only: the repo URL, the branch name, the fact that `SBX_API_KEY`
was already in the environment (never printed), and the instruction "follow
README.md". It did not see the builder's scratch state, and ran everything
from a fresh clone at `/tmp/acc4/repo`, outside the working repo.

## Commands, exactly as run

```bash
git clone --depth 1 -b sbx/demo-bisect-breaking-commit-f6 \
  https://github.com/agent-next/sandbox /tmp/acc4/repo
cd /tmp/acc4/repo/cookbook/bisect-breaking-commit
python3 run.py --ref sbx/demo-bisect-breaking-commit-f6 2>&1 | tee /tmp/acc4/run.log
echo "exit=$?"
```

Environment: Debian bookworm driver, Python 3.12.15, git 2.39.5,
`sbx` CLI 0.0.1. Judge sandboxes: fresh Debian bookworm, 2 vCPU,
`judge/VERSIONS.txt` (git 2.39.5, Python 3.12.15).

## Real output (abridged to step lines; full log kept out of git)

```
[run] create sandbox (utility: ref/selftest/serial/grade)    2.1s  exit=0
[run] clone repo (utility)                  4.3s  exit=0
[run] stage fixture/one_commit from ref     1.8s  exit=0
[run] judge/setup.sh                        2.0s  exit=0
[run] judge/selftest.sh                   167.3s  exit=0
[selftest] mutants killed   : 9/9 (100%)
[selftest] SUCCESS
[run] created 11 sandboxes in 12.1s
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
[run] parallel sweep: 21.95s
[run] killed 11 sweep sandboxes in 9.28s
[run] serial baseline: 66.8s over 11 commits (one exec each, 1 machine)
[run] negative control (reverted fixture)    6.1s  exit=0
[run] judge/grade.sh sweep_report.json     50.2s  exit=0
[run] culprit  : 5095cf335e19621f8bef90019c5c4381e574b581 (index 25)
[run] evidence : N-1 passes=True, N fails=True
[run] speedup  : 3.04x (serial 66.8s vs parallel 21.9s over 11 sandboxes)
[run] timings:
[run]   create_sandboxes_s            12.10s
[run]   grade_s                       50.25s
[run]   kill_sandboxes_s               9.28s
[run]   negative_control_s             6.11s
[run]   parallel_sweep_s              21.95s
[run]   selftest_s                   167.34s
[run]   serial_sweep_s               66.81s
[run] PASS
[run] confirmed: all 12 sandboxes this run created are gone (`sbx list` shows none of their ids)
exit=0
```

## Numbers vs the RECEIPT runs

| number | this run | RECEIPT run 1 | RECEIPT run 2 | SPEC tolerance | match |
| --- | --- | --- | --- | --- | --- |
| culprit SHA | `5095cf33…b581` | same | same | exact | ✓ |
| culprit index | 25 | 25 | 25 | exact | ✓ |
| pass/fail boundary | 24 pass / 25..30 fail | same | same | exact | ✓ |
| artifact serial / parallel | 66.81 s / 21.95 s | 94.12 / 20.63 | 97.10 / 22.33 | walls may vary | ✓ |
| artifact speedup (G7) | 3.04× | 4.56× | 4.35× | ≥ 3.0× | ✓ |
| judge's own re-measure (G7) | 4.25× | 9.88× | 10.07× | ≥ 3.0× | ✓ |
| sandboxes used (G8) | 11 | 11 | 11 | = 11 | ✓ |
| selftest kill rate | 9/9 (100 %) | 9/9 | 9/9 | ≥ 90 % | ✓ |
| verdict / exit | passed, 0 | passed, 0 | passed, 0 | all gates, 0 | ✓ |
| cleanup confirmed | yes, all 12 | yes | yes | required | ✓ |

The wall times are the only numbers that moved, as SPEC.md allows: the serial
baseline wall is gateway-latency-bound and varied 66.8–97.1 s across the
three runs (same key, same commands); the artifact speedup stayed above the
3.0× gate in every run.

## Verdict

**REPRODUCED** — every gate passed, exit 0, culprit and receipts identical to
the RECEIPT runs, and all measured numbers within the tolerances SPEC.md
states.
