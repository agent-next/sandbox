# REPRODUCE — nanousd-render

Independent reproduction of `cookbook/nanousd-render/` from `README.md` +
`SPEC.md` only, in a fresh sandbox, by an agent that is not the builder
(different model family). RECEIPT.md is read only after every number
below is collected. The template below is the shape to fill in.

**Status: (not done: independent reproduction happens before merge, by a
different agent than the builder — DEMO-STANDARD.md "Reproducibility".
Nothing below this line is filled in yet; no numbers have been recorded.)**

## Environment

- (sandbox shape: distro, vCPU, RAM; python3 version; repo commit checked
  out)

## `bash judge/setup.sh`

- exit code, wall time, VERSIONS.txt highlights (nanousd commit,
  usd-core/numpy/pillow versions, mesa version)

## `bash judge/selftest.sh`

- known-good verdict, mutants killed / total, kill rate, determinism OK

## `bash judge/grade.sh examples/good/scene.usda --json /tmp/v.json`

- exit code, per-gate pass, key numbers (rendered_frac, per-mesh
  illuminance k, own_dev), wall time

## Comparison against RECEIPT.md

| number | RECEIPT | this run | within SPEC tolerance |
|---|---|---|---|

## README issues

- (anything that needed a hint not in the README — the README is then
  wrong and gets fixed, not annotated around)
