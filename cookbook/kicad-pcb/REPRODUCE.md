# REPRODUCE — kicad-pcb

This file records an **independent** reproduction: a different agent
(model family different from the builder's) following only `README.md`
in a fresh sandbox.

## Instructions given to the reproducer

> Follow `cookbook/kicad-pcb/README.md` in a fresh sandbox: run
> `bash judge/setup.sh`, `bash judge/selftest.sh`, and
> `bash judge/grade.sh examples/good/555-blinker --json /tmp/v.json`.
> Paste the exit codes, wall times, kill rate, and the verdict JSON
> below.

## Tolerances (from SPEC.md)

Expected on the known-good example: `overall_pass: true`,
`erc_errors: 0`, `drc_violations: 0`, `drc_unconnected_items: 0`,
`unrouted_items: 0`, `open_endpoints: 0`, `drill_hits: 11`,
`tools: 2`, kill rate 7/7. Gerber aperture/op counts may vary +-20 %
if the artifact was regenerated.

## Reproduction results

(not done: requires a post-merge run by a different agent family in a
fresh sandbox — the builder cannot spawn sibling sandboxes)

| metric | builder (RECEIPT) | reproducer |
|---|---|---|
| setup exit / time | 0 / ~17 s | (not done) |
| selftest exit / kill rate | 0 / 100 % | (not done) |
| grade exit / overall_pass | 0 / true | (not done) |
| erc_errors | 0 | (not done) |
| drc_violations | 0 | (not done) |
| unrouted_items | 0 | (not done) |
| drill_hits / tools | 11 / 2 | (not done) |
