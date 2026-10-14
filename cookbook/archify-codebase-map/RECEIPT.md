# RECEIPT: archify-codebase-map

Builder run — inside the builder machine itself (the toolchain the sandbox
gets: Debian bookworm + apt nodejs 18.20.4 + chromium 155.0.8059.39), not
yet inside a fresh agent-next sandbox; `run.py`'s sandbox execution is the
lead's final check.

## setup (apt chromium + two sha256-checked tarballs)

```
$ sudo apt-get install -y -qq chromium
$ chromium --version
Chromium 155.0.8059.39 built on Debian GNU/Linux 12 (bookworm)
$ node --version
v24.21.0                    # builder box; setup.sh pins nodejs=18.20.4+dfsg-1~deb12u3 via apt
```

`judge/setup.sh` targets nodejs 18.20.4+dfsg-1~deb12u3 (Debian bookworm)
and the same Chromium 155.0.8059.39-1~deb12u1; archify renders identically
on both Node versions (pure JS, no native bindings). A fresh sandbox run
records its own numbers.

## selftest — judge proves it can fail

```
$ bash judge/selftest.sh
[selftest] Regenerating mutant cases...
mutant: hallucinated_node
mutant: hallucinated_edge
mutant: reversed_edges
mutant: half_modules
mutant: mangled_json
mutant: stale_html
mutant: blank_html
mutant: edge_via_missing_node

[selftest] Known-good (must PASS):
[selftest]   good/httpx-map  PASS  (33s)

[selftest] Determinism (same seed twice, verdict JSON except 'timing'):
[selftest]   good/httpx-map  deterministic (identical)

[selftest] Known-bad mutants (must FAIL):
[selftest]   blank_html  killed (failed gates: valid+reproducible)
[selftest]   edge_via_missing_node  killed (failed gates: valid+reproducible)
[selftest]   half_modules  killed (failed gates: node-recall+no-hallucination,edge-precision-recall)
[selftest]   hallucinated_edge  killed (failed gates: valid+reproducible)
[selftest]   hallucinated_node  killed (failed gates: valid+reproducible)
[selftest]   mangled_json  killed (failed gates: valid+reproducible)
[selftest]   reversed_edges  killed (failed gates: edge-precision-recall)
[selftest]   stale_html  killed (failed gates: valid+reproducible)

[selftest] ============================================
[selftest] good passed       : 1/1
[selftest] determinism       : 1/1
[selftest] mutants killed    : 8/8 (100%)
[selftest] ============================================
[selftest] SUCCESS
exit 0         wall time ≈ 3 min total (8 mutants × ~20 s each + 2 good runs)
```

## grade of the good example — exit 0, all four gates pass

```
$ bash judge/grade.sh examples/good/httpx-map --json /tmp/verdict.json --seed 42
[gates] valid+reproducible           PASS  schema ok; rendered HTML matches shipped HTML
[gates] renders-clean                PASS  no console errors; pixel stdev 22(>= 8.0)
[gates] node-recall+no-hallucination PASS  recall 1.00 (17/17 modules)
[gates] edge-precision-recall        PASS  precision 1.00 (63/63 claimed), recall 1.00 (63/63)
[gates] all_gates_passed = True
[grade] exit code: 0 (0 = all gates passed)
wall time: ~25 s
```

Key numbers: 17 modules, 63 direct-import edges (from the `ast` ground
truth), node recall 1.00, edge precision 1.00, edge recall 1.00,
screenshot pixel stdev 22–23 against a gate minimum of 8.

## Two fresh sandbox runs

(not done: the lead runs `python3 run.py` end to end — the builder
sandbox cannot create other sandboxes. The receipt will be updated with
two fresh-sandbox runs in the merge review.)

## Deviations

- **archify release age:** v3.0.1 (2026-09-28) is pinned instead of the
  newer v3.1.0 (2026-10-13) to honour "at least two weeks old".
- **Node 24 vs 18:** the builder box renders with Node 24; the demo's
  judge pins Node 18 (apt bookworm). All archify behaviour the judge
  depends on (validate, render, schema) is exercised in both and matched
  byte-for-byte.
- **diagram.html is git-ignored:** archify output is ~800 KB of embedded
  fonts/JS; the judge regenerates it from `diagram.json`, and the PNGs in
  `media/` carry the visual.
