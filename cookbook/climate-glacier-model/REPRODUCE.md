# REPRODUCE — `cookbook/climate-glacier-model/`

Independent reproduction, per `cookbook/DEMO-STANDARD.md`: a different agent
followed **only `README.md`** in a fresh sandbox (it did not read
`RECEIPT.md` or `SPEC.md` first, and did not edit anything under `judge/`).
Its numbers are below, side by side with the builder's `RECEIPT.md`.

## What the reproducing agent did

From the repo root, on this branch:

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/climate-glacier-model/run.py --ref sbx/demo-climate-glacier-model-f4
```

One fresh sandbox (`01a13ff8-…ef66`), created, used and confirmed gone.

## Numbers, side by side

| quantity | RECEIPT (builder) | independent run | within tolerance? |
|---|---|---|---|
| `run.py` exit code | 0 | **0** | must be 0 — yes |
| `judge/setup.sh` exit code | 0 | **0** | must be 0 — yes |
| `judge/selftest.sh` exit code | 0 | **0** | must be 0 — yes |
| kill rate | 13/13 = 100 % | **13/13 = 100 %** | ≥ 90 % — yes |
| `warm_2p0` crossing year | 96.0076481835564 | **96.0076481835564** | ±3 yr of 96.007 — exact |
| `warm_2p4` crossing year | 81.60555821753714 | **81.60555821753714** | ±3 yr of 81.670 — exact |
| `warm_2p8` crossing year | 71.40555289612254 | **71.40555289612254** | ±3 yr of 71.426 — exact |
| `warm_2p0` `V(100)` km³ | 2.832 | **2.832** | within 2 % of 2.831981 — yes |
| `warm_2p4` `V(100)` km³ | 2.04288 | **2.04288** | within 2 % of 2.042855 — yes |
| `warm_2p8` `V(100)` km³ | 1.20192 | **1.20192** | within 2 % of 1.201889 — yes |
| zero-melt worst deviation | 0.0 | **0.0** | ≤ 1e-9 relative — yes |
| `verdict["passed"]` | `true` | **`true`** | must be `true` — yes |

Every graded number is **identical** to the builder's, not merely within
tolerance — as SPEC.md requires, the verdict is deterministic and does not
depend on host, wall time or load.

## Wall times (independent run)

| step | exit | wall time |
|---|---|---|
| `sbx create --timeout-min 30` | 0 | 3.8 s |
| `git clone --depth 1 -b <ref>` | 0 | 5.9 s |
| `judge/setup.sh` | 0 | 36.1 s |
| `judge/selftest.sh` | 0 | 80.0 s |
| `judge/grade.sh examples/good` | 0 | 13.2 s |
| `run.py` end to end | 0 | ~2 min 8 s |

These match the README's "Measured wall time" table within normal
machine-load variation (README says ~2 m 15 s end to end).

## Verbatim tail

```text
run: SUMMARY passed=True zero_melt_worst=0.0 rows=303 warm_2p0:V100=2.832/t50=96.0076481835564 warm_2p4:V100=2.04288/t50=81.60555821753714 warm_2p8:V100=1.20192/t50=71.40555289612254
run: killed and confirmed gone: 01a13ff8-c2ab-7f22-a920-884875d4ef66
```

## Cleanup

The sandbox the reproduction created (`01a13ff8-…ef66`) is confirmed gone
(both by `run.py`'s own "killed and confirmed gone" line and by `sbx list`
afterwards). No sandbox or lease created by the reproduction remains.

## README issues found

None that affected the run. The one-command section is accurate, the timing
table matches, and the promised kill-and-confirm happened. (The reproducer's
shell happened to start in a subdirectory, so the first attempt needed the
command run from the repo root as the README says — not a README defect.)
