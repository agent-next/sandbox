# REPRODUCE — `cookbook/climate-glacier-model/`

Independent reproduction, per `cookbook/DEMO-STANDARD.md`: a different agent
on a different model family follows **only `README.md`** in a fresh sandbox
and records its numbers here. The builder does not fill this in.

Status: **(not done: to be completed by an independent agent before merge —
the builder's own numbers are in `RECEIPT.md` and do not count as
independent reproduction).**

## What the reproducing agent must do

1. Follow `README.md` alone: create a sandbox, `git clone` this repo at the
   reviewed SHA, run `judge/setup.sh`, then `judge/grade.sh examples/good`.
   Do not read the builder's `RECEIPT.md` first, and do not edit anything
   under `judge/`.
2. Record, side by side with `RECEIPT.md`:

| quantity | RECEIPT (builder) | this run | within tolerance? |
|---|---|---|---|
| `judge/setup.sh` exit code | | | must be 0 |
| `judge/selftest.sh` exit code | | | must be 0 |
| kill rate | | | must be ≥ 90 % |
| `warm_2p0` crossing year | | | ±3 yr of 96.007 |
| `warm_2p4` crossing year | | | ±3 yr of 81.670 |
| `warm_2p8` crossing year | | | ±3 yr of 71.426 |
| `warm_2p0` `V(100)` km³ | | | within 2 % of 2.831981 |
| `warm_2p4` `V(100)` km³ | | | within 2 % of 2.042855 |
| `warm_2p8` `V(100)` km³ | | | within 2 % of 1.201889 |
| zero-melt worst deviation | | | ≤ 1e-9 relative |
| `verdict["passed"]` | | | must be `true` |

3. Note any step in `README.md` that was ambiguous or wrong, and any
   difference from `RECEIPT.md` that the tolerances above do not explain.
   Unexplained differences are a bug in the demo, not in the reproduction.
