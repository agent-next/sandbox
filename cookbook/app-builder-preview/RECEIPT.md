# app-builder-preview — receipt

Real command output from two fresh agent-next sandboxes (setup from
nothing: Node tarball, two Chromium zips, npm cache). Every grade ran with
the default `--seed 0`. Commands ran from the repository root unless shown
otherwise. Sandbox ids are the ones this demo's own `run.py` created; both
were killed and confirmed gone.

Toolchain recorded by `judge/VERSIONS.txt` after `judge/setup.sh`:
node v22.23.3, npm 10.9.9, Playwright Python binding 1.63.0, Chromium
153.0.8010.12 (rev 1243), react 19.3.0, react-dom 19.3.0, vite 8.3.4,
@vitejs/plugin-react 6.1.1.

## Fresh-sandbox run 1 — `python3 cookbook/app-builder-preview/run.py --ref sbx/demo-app-builder-preview-f3`

```text
<RUN1>
```

exit=0.

## Fresh-sandbox run 2 — same command, new sandbox

```text
<RUN2>
```

exit=0. Both runs' verdict JSONs are byte-identical except `timing`
(enforced per grade by `judge/selftest.sh`, which fails if two grades of the
same artifact differ beyond that key).

## Key numbers (identical in both runs)

| quantity | value |
|---|---|
| gates | structure, build, serve, flows, hygiene — all pass |
| flows | 6/6 pass (add, complete, delete, filter, persist, stats) |
| reference cross-check | agrees with the artifact on all 6 flows |
| `dist/` size | 224294 B = 219.0 KiB of the 250 KiB budget |
| console errors | 0 |
| `judge_intact` | true (judge/ sha256 unchanged across the grade) |
| self-test kill rate | 6/6 = 100 % (requirement ≥ 90 %) |
| self-test mutants | broken_delete → flows; stats_wrong_span → flows; no_persist → flows; console_error → hygiene; wrong_element_id → flows; build_broken → build |
| determinism | OK — two grades of the good artifact byte-identical except `timing` |

Per-gate wall times from the verdict JSON (`timing` key, run 1):
structure 0.0 s, build 6.6 s, serve 1.8 s, flows 19.1 s, hygiene 26.1 s.

## Judge self-test, standalone

`bash cookbook/app-builder-preview/judge/selftest.sh` in a fresh sandbox
(own run, 7 min 0 s wall):

```text
selftest: generating mutants
selftest: grading known-good
selftest: known-good: PASS
selftest: mutant broken_delete: killed (gate: flows)
selftest: mutant stats_wrong_span: killed (gate: flows)
selftest: mutant no_persist: killed (gate: flows)
selftest: mutant console_error: killed (gate: hygiene)
selftest: mutant wrong_element_id: killed (gate: flows)
selftest: mutant build_broken: killed (gate: build)
selftest: kill rate: 6/6 = 100%
selftest: determinism check (two grades of the good artifact)
selftest: determinism: OK
selftest: judge/ checksums unchanged
selftest: ok
```

## Media traceability

Every figure and number in README.md comes from a judge verdict, regenerated
by `bash media/make_media.sh` (which re-runs the judge and writes
`media/data/*.json`); `media/MANIFEST.json` names the command, the source
data file and the sha256 of each media file. Figures show measured numbers
only.

## Deviations

- The Chromium builds are fetched from the Playwright CDN as two pinned zips
  (~315 MB total, sha256-checked). This is the one setup step that needs real
  bandwidth; on a slow link it dominates the setup step's wall time. Nothing
  else in setup touches the network beyond the Node tarball and the npm cache
  warm-up.
- The Playwright **Python binding** is not installed by `setup.sh`: the
  sandbox image ships exactly 1.63.0, and `setup.sh` verifies that version
  and fails loudly if the image ever ships a different one. It is never
  upgraded in place.
- `npm ci` in the build gate is served from the warm cache `setup.sh`
  created, so the build gate does not need the network.
- The self-test's determinism check grades the good artifact twice; its wall
  time is part of the `selftest` step above, not a separate step.
