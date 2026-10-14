# Archify codebase map

**[archify](https://github.com/tt-a1i/archify)** (~83k GitHub stars, MIT)
turns an idea, plan or codebase into an interactive architecture diagram,
driven by an agent skill that renders a JSON intermediate representation
("IR") to a self-contained HTML viewer.

This demo shows the whole loop inside a disposable agent-next sandbox:

1. A real, well-known Python package (**httpx 0.28.1**) is cloned at a
   pinned commit.
2. Its true top-level module-dependency graph is derived with Python's
   `ast` module (so the judge has ground truth the agent cannot see).
3. An archify **architecture** diagram (17 modules, 63 import edges) is
   authored as JSON-IR, rendered with archify v3.0.1, and screenshotted in
   headless Chromium.
4. The judge grades the artifact on **four** numeric gates and proves it
   can fail (8 scripted mutants, 100% kill rate).

The point: the sandbox runs everything a human session needs (Node,
Chromium, the archify skill) in ~3 minutes, and the verdict is a single
JSON the agent cannot sweet-talk.

## Ask your agent

> In an agent-next sandbox, clone <https://github.com/agent-next/sandbox>,
> `cd cookbook/archify-codebase-map`, run `bash judge/setup.sh`, then read
> `examples/good/httpx-map/diagram.json` and reproduce the flow with
> **archify** on a repo of my choice. For httpx itself, show me the verdict
> from `bash judge/grade.sh examples/good/httpx-map`. Now point archify at
> a small repo I give you (target 15–60 top-level modules), author the
> JSON-IR with `sources[].path` per node (the module file), render it, and
> serve the HTML so I can click around.

## One-command run

```
export SBX_API_KEY=<your key>     # or E2B_API_KEY
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
python3 run.py                   # clones, sets up, self-tests, grades
python3 run.py --keep            # leaves the sandbox up for exploring
```

Measured wall time in the builder's sandbox (2 vCPU, ~3 GB RAM):

| step | wall |
|---|---|
| `judge/setup.sh` (apt + two sha256-checked tarballs) | ~50–90 s |
| `judge/selftest.sh` (good × 2 + 8 mutants) | ~3 min |
| `judge/grade.sh examples/good/httpx-map` | ~25 s |

## The artifact

A directory the agent ships, with exactly two files:

```
<artifact>/diagram.json   # archify architecture JSON-IR (schema_version 1)
<artifact>/diagram.html   # `archify render architecture diagram.json -` output
```

`diagram.json` is the narrative; `diagram.html` is a promise it renders.
The judge regenerates the HTML and diffs it byte-for-byte, so a hand-edited
screenshot-friendly HTML cannot fake a render.

## What the judge checks

1. **valid + reproducible:** `archify validate` passes; a fresh
   `archify render` of `diagram.json` is byte-identical to the shipped
   `diagram.html` (when one is shipped).
2. **renders clean in headless Chromium:** no console errors, and the
   1280x800 screenshot has pixel stdev >= 8 (a blank page measures < 1).
3. **node recall >= 0.9 + no hallucination:** every graded component's
   `sources[0].path` must resolve to a real file under the pinned httpx
   tree; the set of resolved stems must cover >= 16 of 17 top-level
   modules; nothing unknown (no `httpx/_telemetry.py`).
4. **edge precision >= 0.8, recall >= 0.6, direction correct:** claimed
   `connections` (resolved through node sources) are compared against the
   true direct-import edges parsed with `ast`. Any exactly-reversed pair
   fails the gate outright.

## Limits

- Only the **top-level** `httpx/*.py` files are graded (17 modules).
  The `httpx/_transports/` subpackage, tests and docs are excluded from
  the ground truth; archify diagrams that include them are not penalised,
  but they don't gain recall either.
- Third-party (`httpcore`, `certifi`) and stdlib imports are not graded —
  draw them as `"type":"external"` nodes if you want them visible.
- The judge never calls an LLM; no keys are needed beyond the sandbox API.
- The judge itself runs in ~25 s on 2 vCPU.

## Credits

- **archify** — <https://github.com/tt-a1i/archify>, release
  [v3.0.1](https://github.com/tt-a1i/archify/releases/tag/v3.0.1),
  commit `2ab3cae`, **MIT** licence (text in
  `third_party/archify-LICENSE.txt`).
- **httpx** — <https://github.com/encode/httpx>, release
  [0.28.1](https://github.com/encode/httpx/releases/tag/0.28.1),
  commit `26d48e0`, **BSD-3-Clause** licence (see the cloned tree).
