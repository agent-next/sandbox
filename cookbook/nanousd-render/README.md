# nanousd-render — two USD implementations agree, and a CPU render proves it

An agent authors a small USD scene (five colored meshes, a camera, a light) to a
spec inside a disposable agent-next sandbox, and a judge it cannot fool decides
whether the file is right: **two independent USD implementations — NVIDIA's
experimental C-ABI nanousd and Pixar's usd-core — must parse it and agree
exactly** on mesh paths, point counts, world transforms and bounding boxes
(G2), and a **headless CPU render** (nanousd's OpenGL ES renderer on Mesa
llvmpipe, no GPU, no X) must land every mesh exactly where an independent numpy
pinhole-projection oracle says it must, painted the color the file declares
(G4). A sandbox helps because the toolchain (cmake + ninja build of nanousd,
the GLES renderer, a pinned pip venv) is disposable, self-contained and cheap to
rebuild from nothing — and the whole point is that the agent iterates on its own
work against a judge, not against a human.

## Ask your agent

Paste this into any agent-next sandbox with the repo cloned:

> Read `cookbook/nanousd-render/SPEC.md` and write `my_scene.usda` that passes
> `bash cookbook/nanousd-render/judge/grade.sh my_scene.usda` with exit 0. First
> run `bash cookbook/nanousd-render/judge/setup.sh` once to install the pinned
> tools. Iterate: author or fix the scene yourself, grade it, read the JSON
> verdict (it names the gate and the exact number that failed — a mesh out of
> frame, a color too close to another, a camera the two readers disagree on),
> and fix your scene until every gate passes. Do not edit anything under
> `judge/` — the judge hashes its own tree and fails closed if it changed.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
SBX_API_KEY=<your key> python3 cookbook/nanousd-render/run.py [--ref main]
```

Creates a sandbox, clones this repo, builds the pinned toolchain, runs the
self-test (kill rate) and grades the known-good example, then kills the sandbox
and confirms it is gone. Measured wall times are in RECEIPT.md; the big step
is the toolchain build (~17 min on 2 vCPU, see Limits), then the self-test,
which grades thirteen mutants (~2 s per grade).

## Limits, stated plainly

- **Time to result misses the standard's target.** DEMO-STANDARD.md asks for
  < 5 min on CPU to the hero result; the measured one-command run takes about
  20 min wall (setup ~17 min, everything else ~40 s). The setup step builds
  nanousd and the OpenGL ES renderer from source with their pinned
  FetchContent dependencies (MaterialX, meshoptimizer); there is no faster
  pinned path that still builds the real thing. Re-running `setup.sh` on an
  existing prefix is idempotent and takes ~12 s, and
  `judge/grade.sh` alone is ~2 s once the toolchain is in place.
- Headless CPU only: the render runs on Mesa llvmpipe (EGL pbuffer); no GPU, no
  X, no NVIDIA account, no network beyond the pinned downloads.
- `media/make_media.sh` regenerates every figure, `media/result.json` and the
  video from judge outputs; `python3 test_run.py` unit-tests run.py's `sbx`
  argv contract against the installed CLI.
- 2 vCPU / ~4 GB RAM is enough; the builds use `ninja -j2`.
- The artifact is USDA text only — no USDC/USDZ, no materials, no composition
  arcs (the SPEC rejects them: two readers can disagree about composition, and
  the whole demo is that they don't).
- The judge is fully deterministic; `--seed` exists for interface uniformity.
- The artifact is only ever parsed and rendered by out-of-process helpers
  (the C dumper, a usd-core dumper, the C renderer driver) — it cannot
  touch the judge's own process, and the judge re-derives every graded
  number from those helpers' output.

See `SPEC.md` for the gates and numeric pass rules, `judge/` for the judge,
`RECEIPT.md` for real measured output from two fresh sandboxes.
