# REPRODUCE — notebook-exec-report

VERDICT: **REPRODUCED**

## Environment

- Debian GNU/Linux 12 (bookworm), Linux 6.1.175 x86_64, 2 vCPU / ~3 GB
- `python3 3.12.15`, pip 25.0.1
- `sbx` CLI installed with the README's command, entry point
  `~/.local/bin/sbx` (`export PATH="$HOME/.local/bin:$PATH"`)
- Working dir `/tmp/nbrepro`, **outside** the repo tree; `run.py` itself
  runs inside a fresh disposable sandbox, per the README
- Reproducer process: a subagent — an independent agent session with none
  of the builder's context, following only `README.md` (+ `SPEC.md` for the
  judge step). Same model family as the builder; a genuinely cross-family
  reproduction is the lead's merge-time step (stated as a deviation below).
  No demo file was modified; `RECEIPT.md` was read only after every number
  below was collected.

## Commands

```bash
git clone --depth 1 -b sbx/demo-notebook-exec-report-f5 \
  https://github.com/agent-next/sandbox repo   # in /tmp/nbrepro
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export PATH="$HOME/.local/bin:$PATH"

# the README's literal one-command run, no --ref (it clones main):
python3 /tmp/nbrepro/repo/cookbook/notebook-exec-report/run.py
# -> exit 1 (see "README defect" below)

# retry with the documented --ref flag:
python3 /tmp/nbrepro/repo/cookbook/notebook-exec-report/run.py \
    --ref sbx/demo-notebook-exec-report-f5
# -> exit 0
export PATH="$HOME/.local/bin:$PATH"; sbx list   # no run sandbox remains
```

## Run A — the README's literal command (exit 1)

```
run: [   2.2s] sbx create --timeout-min 30 -> exit 0
run: sandbox 01a1408f-0e11-7f61-ae0f-59f9e3a3a7a6
run: [   4.9s] git clone -> exit 0
run: [   1.8s] judge/setup.sh -> exit 1
run: FAILED: judge/setup.sh failed (exit 1):
/bin/bash: line 1: cd: notebook-demo-repo/cookbook/notebook-exec-report: No such file or directory
run: killed and confirmed gone: 01a1408f-0e11-7f61-ae0f-59f9e3a3a7a6
EXIT_CODE=1
```

**README defect (fixed in the same commit as this file):** the README's
command block omitted `--ref`, so `run.py` cloned `main`, where
`cookbook/notebook-exec-report/` does not exist yet. The README now states
that `--ref` must name a ref that carries the demo directory (branch while
under review, `main` after merge).

## Run B — one-command run with `--ref` (exit 0, 282 s total)

```
run: [   1.8s] sbx create --timeout-min 30 -> exit 0
run: sandbox 01a1408f-9751-7ff2-9e6e-a84c36a9b01b
run: [   3.3s] git clone -> exit 0
run: [  71.6s] judge/setup.sh -> exit 0
run: [ 178.5s] judge/selftest.sh -> exit 0
selftest: kill rate 7/7 = 100%
selftest: determinism OK (two --seed 1 runs identical except timing)
selftest: OK
run: [  23.1s] judge/grade.sh examples/good/analysis.ipynb -> exit 0
run: SUMMARY passed=True rmse_test=0.295283 (refit 0.29528270224052927) r2_test=0.877895157 coef_recovery=0.018015198777351894 blind_ratio=0.9933903285423452 figures=3
run: killed and confirmed gone: 01a1408f-9751-7ff2-9e6e-a84c36a9b01b
EXIT_CODE=0
```

Step wall times (71.6 / 178.5 / 23.1 s) are well under the README's
measured ranges; the numbers are what reproduce, the timings only vary.

## Verdict numbers vs RECEIPT.md

| quantity | this run | RECEIPT | match |
|---|---|---|---|
| `rmse_test` (notebook) | 0.295283 | 0.295283 | exact |
| oracle refit `rmse_test` | 0.29528270224052927 | 0.29528270224052927 | exact (gate 1e-6) |
| `r2_test` | 0.877895157 | 0.877895157 | exact (gate 1e-9) |
| coefficient recovery | 0.018015198777351894 | 0.018015198777351894 | exact (gate 0.05) |
| blind ratio | 0.9933903285423452 | 0.9933903285423452 | exact (gate 1.25) |
| kill rate | 7/7 = 100 % | 7/7 = 100 % | exact (req. 90 %) |
| split | 1280 / 320 | 1280 / 320 | exact |
| dataset sha256 | 83029ea2…dae799c | 83029ea2…dae799c | exact |
| figure bytes (3) | 37072 / 58534 / 48488 | 37072 / 58534 / 48488 | exact |
| verdict `passed` | true | true | match |

All SPEC tolerances pass; no deviation in any gate.

## Sandboxes

Both sandboxes (`01a1408f-0e11-7f61-ae0f-59f9e3a3a7a6` failed run,
`01a1408f-9751-7ff2-9e6e-a84c36a9b01b` successful run) were killed and
confirmed absent from `sbx list` after the runs.
