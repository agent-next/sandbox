# spreadsheet-recalc — independent reproduction

Per `cookbook/DEMO-STANDARD.md`, before merge a different agent (different
model family from the builder) follows only `README.md` in a fresh sandbox
and records its numbers here. Numbers must match `RECEIPT.md` within the
tolerances stated in `SPEC.md` (NPV within ±0.5 % of the closed form;
negative-control move ≥ 1 %; kill rate ≥ 90 %).

Reproducer: GLM-5.3 (builder of record was a Claude-family agent).
Procedure: the one-command run from README.md only —

```
python3 cookbook/spreadsheet-recalc/run.py --ref sbx/demo-spreadsheet-recalc-f1
```

in a fresh agent-next sandbox, `sbx` CLI 0.0.1, `SBX_API_KEY` from the
environment, 2026-10-15.

## Result

Exit code 0. Verdict printed by run.py:

```
spreadsheet-recalc demo: PASS
  artifact: dcf_model.xlsx
  seed: 0
  gate judge_intact: pass
  gate negative_control: pass
  gate oracle: pass
  gate recalc: pass
  gate structure: pass
  NPV @ 8%: computed=2753.3913 oracle=2753.3913 err=0.0%
  NPV @ 10%: computed=2276.4838 oracle=2276.4838 err=0.0%
  NPV @ 12%: computed=1828.0794 oracle=1828.0794 err=0.0%
  negative control: NPV moved 33.6063%
```

Self-test inside the run: known-good PASS, 6/6 mutants killed, kill rate
100 %, determinism OK.

## Numbers vs RECEIPT.md

| quantity | REPRODUCE (this run) | RECEIPT (fresh runs) | match |
|---|---|---|---|
| NPV @ 8 % | 2753.3913 | 2753.3913 | exact |
| NPV @ 10 % | 2276.4838 | 2276.4838 | exact |
| NPV @ 12 % | 1828.0794 | 1828.0794 | exact |
| oracle err at each rate | 0.0 % | 0.0 % | exact |
| negative-control move | 33.6063 % | 33.6063 % | exact |
| kill rate | 6/6 = 100 % | 6/6 = 100 % | exact |
| verdict | PASS, exit 0 | PASS, exit 0 | exact |

All numbers match the RECEIPT exactly (well inside the SPEC tolerances):
the judge is deterministic for a given LibreOffice build, and both runs
used the pinned toolchain from `judge/setup.sh`.

Wall time: ~330 s end to end (setup ~100 s, selftest ~50 s, grade ~20 s,
remainder sandbox create/clone/kill).

## Deviations

None.
