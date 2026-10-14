# SPEC: Archify codebase map (module dependency diagram of httpx)

## Goal

Demonstrate an agent inside a disposable agent-next sandbox using the
upstream **archify** skill (JSON-IR → interactive HTML diagram, MIT
licence) to turn a real, small, well-known Python repository into an
architecture map, and a judge the agent cannot fool deciding whether the
map matches the repository's true module-dependency graph.

- Upstream: <https://github.com/tt-a1i/archify>, pinned to release
  **v3.0.1** (commit `2ab3cae7ac2c2a55d7386ca789d03c4fcd31816c`,
  published 2026-09-28), MIT licence (see `third_party/archify-LICENSE.txt`).
- Render path used by the judge: `archify render architecture
  <diagram.json> <output.html>` — the deterministic, LLM-free half of the
  skill. An agent in a real session supplies the JSON-IR by reading the
  repo; the judge supplies the ground truth by parsing imports statically.
- Target repository: **httpx 0.28.1**
  (`encode/httpx` commit `26d48e0634e6ee9cdc0533996db289ce4b430177`),
  a flat package of 16 top-level modules. Only top-level modules of the
  `httpx` package are graded.

The shipped known-good artifact `examples/good/httpx-map/` was produced
by running exactly this pipeline in a sandbox: clone the target, derive
the import graph with Python `ast`, author an archify architecture
JSON-IR from it, render, and screenshot the result in headless Chromium.

## Non-goals

- Grading natural-language quality of labels or the diagram's visual
  beauty (the renderer's own layout engine is trusted once the JSON is valid).
- Sub-modules (`httpx._models.requests` style) — the graded graph is
  top-level module to top-level module.
- Third-party (`httpcore`, `certifi`, ...) and stdlib imports — excluded
  from ground truth and forbidden as nodes (use `type:"external"` only
  if an agent insists; they play no part in the numeric gates).
- Transitive correctness: judge compares direct import edges only.
- Running an LLM inside the judge. The judge needs no API keys.

## Artifact

A directory containing exactly two files:

```
<artifact>/
├── diagram.json   # archify architecture JSON-IR (schema_version 1)
└── diagram.html   # the result of `archify render architecture diagram.json diagram.html`
```

- Every graded `components[].id` **must equal the module file's stem**
  (`_client` for `httpx/_client.py`, `__init__` for `httpx/__init__.py`).
  If a `components[].sources[].path` entry is present it must be
  `httpx/<id>.py`. Nodes without a `sources` path are still graded by id.
- Every graded `connections[]` is `{"from": "<module>", "to": "<module>"}`
  and asserts that module `from` imports module `to` directly.
- The judge re-derives ground truth from the pinned httpx source tree
  (downloaded, sha256-checked, in `judge/setup.sh`); nothing about the
  answer key is stored in the repo.

## Gates (numeric pass rules)

All gates run in `judge/grade.sh <artifact_dir> [--seed N] [--json out.json]`.
`out.json` carries per-gate results and an `all_gates_passed` boolean.

### Gate 1 — artifact is a valid archify diagram
- `diagram.json` parses and validates against the pinned
  `architecture.schema.json` (via `archify validate` exit 0).
- `diagram.html` (if shipped) is byte-identical to a fresh
  `archify render` of `diagram.json`; if it is not shipped the judge
  renders one into scratch. A byte-mismatch fails: the narrative must be
  reproducible, not hand-edited.

### Gate 2 — renders in headless Chromium, non-blank, no console errors
- The diagram HTML is rendered with Chromium (pinned Debian package) in
  headless mode with `--enable-logging` console capture; any
  `console.error` or uncaught exception fails the gate.
- A 1280x800 screenshot's pixel standard deviation must be >= 8.0
  (a blank canvas measures < 1) and it must contain >= 3 distinct
  saturated pixels coming from node fills (non-background).

### Gate 3 — node recall + no hallucination
- Ground truth: the 16 top-level module stems of the pinned httpx tree
  (computed, not hard-coded).
- Node recall = |graded nodes ∩ truth| / |truth| must be >= 0.9
  (>= 15 of 16 modules present).
- No hallucinated components: every graded node id must be a real
  module stem (each `sources[].path`, when present, must also resolve to
  a file in the pinned tree). Counts more than 16 "module" nodes fail.

### Gate 4 — edge precision and recall with correct direction
- Ground truth: the directed module→module import edges of the pinned
  tree (63 edges at this pin; computed with `ast`).
- precision = |edges ∩ truth| / |edges| >= 0.8
- recall    = |edges ∩ truth| / |truth| >= 0.6
- direction: every claimed edge that matches an undirected truth pair
  but not the directed set (i.e. exactly reversed) fails this gate
  outright, regardless of the precision/recall margins.

## Acceptance oracle

`bash judge/selftest.sh` exits 0 only if:
1. the known-good example passes all gates twice with byte-identical JSON
   (outside `timing`),
2. every scripted mutant in `judge/mutants.py` (≥ 8) fails at least one
   gate — kill rate must be >= 90 %,
3. `judge/` checksums are unchanged after grading.

## Tolerances

Deterministic: grades are pure functions of the artifact and the pinned
inputs. Two runs at the same seed must be byte-identical outside the
`timing` key. Wall-time numbers may vary; the only float gates (pixel
stdev, recall/precision ratios) are integer-driven and independent of
timing.
