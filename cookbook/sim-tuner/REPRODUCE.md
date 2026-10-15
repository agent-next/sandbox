VERDICT: REPRODUCED

# sim-tuner: independent reproduction from README.md

Reproducer run on 2026-10-15 (UTC) by a Claude-family model. The demo's code was written by a GPT-family model.

- Commit: `0b02301c`. Its judge and runner code is byte-identical to `73128bc3`; the commits after that change only docs and media.
- Command: the README's one-command run, from a fresh checkout, with `SBX_API_KEY` exported:

```bash
python3 cookbook/sim-tuner/run.py --report-json out.json
```

- RECEIPT.md was compared only after the numbers below were in hand.
- The single GPU seat was busy with another user's lease. The runner was re-invoked every 30 s until creation succeeded. Only the final, successful invocation is reported.

## Output (excerpt)

```
created gl-0bd598-5 in 5.1 s
lease job done in 96 s
  [stack-check] rc=0 (0.4 s)
  [selftest] rc=0 (87.4 s)
  [grade] rc=0 (7.6 s)
selftest: kill rate: 18/18 = 100%
selftest: determinism: OK
sim-tuner demo: PASS (seed 7)
  gate G1_ranges: pass
  gate G2_train: pass
  gate G3_heldout: pass  heldout_err 0.02206 (< 0.025; frac of default 0.1862 < 0.3)
  gate G4_gpu_cpu_agree: pass  gpu 0.016322 vs cpu 0.016299 (abs 2.3e-05, rel 0.001441)
destroyed gl-0bd598-5; verified GET 404
total: 102 s
```

## Claimed vs reproduced

| result | RECEIPT (fresh runs 1 / 2) | reproduced |
|---|---|---|
| runner exit | 0 / 0 | 0 |
| G1 / G2 / G3 / G4 | PASS x4 / PASS x4 | PASS x4 |
| held-out error | 0.022060 / 0.022060 | 0.02206 |
| CPU train error | 0.016299 / 0.016299 | 0.016299 |
| mutants killed | 18/18 / 18/18 | 18/18 |
| selftest seconds | 67.9 / 71.4 | 87.4 |
| grade seconds | 5.6 / 5.7 | 7.6 |
| lease creation seconds | 4.1 / 3.0 | 5.1 |
| full runner seconds | 90 / 90 | 102 |
| lease cleanup | DELETE + GET 404 | DELETE + GET 404 |

Every gated number matches exactly. Wall times are 13-29 % slower. The likely cause is contention: other workloads were running on the same GPU host. No gate depends on wall time.
