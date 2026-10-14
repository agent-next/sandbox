# Material studio with a physical judge

An agent designs three OpenPBR spheres on a studio floor. A fixed browser
harness path-traces the scene with [MuTracer 0.1.1](https://github.com/pissang/mutracer)
(MIT), and a numeric judge checks an analytic furnace, material energy,
Monte Carlo convergence, deterministic HDR hashes and an image-quality budget.
A disposable sandbox isolates the browser and dependencies. Geometry and
lighting are procedural; rendering uses no network assets.

**Status: PARTIAL.** Two fresh CPU sandboxes pass setup but lose the WebGPU
device before the first HDR frame. The included scene is not verified good.
See the real failed grades in `RECEIPT.md`; do not treat this as an accepted demo.

## Ask your agent

> In an agent-next CPU sandbox, clone the agent-next/sandbox repository and work
> in cookbook/render-pathtrace. Read SPEC.md and run `sh judge/setup.sh`.
> Design your own `scene.json`, not JavaScript: place three to five spheres with
> distinct OpenPBR materials on a floor, and choose a camera, constant or
> procedural environment, and rect/sphere lights. Start at 64×64 and 32 spp.
> Use examples/good/scene.json only as a schema example. Do not edit judge/.
> Run `sh judge/grade.sh scene.json --seed 17 --json verdict.json`, inspect the
> numeric failures, and iterate on the scene until every gate passes.
> Keep the scene and verdict, report the backend, furnace numbers, convergence
> slope, image metrics and wall time, and destroy the sandbox afterward.
> No models, textures, external render requests or media production.

## One command

On your workstation, Python 3.10+ and the standard-library-only runner need
the `sbx` CLI and an existing sandbox API key:

```sh
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY='<your key>'
python3 cookbook/render-pathtrace/run.py --ref sbx/demo-render-pathtrace --seed 17
```

The default `--ref` is `main`. Use the feature branch until the demo is merged.
The runner creates a sandbox, clones the requested ref, runs setup, self-test
and grade as detached jobs, prints their real output and wall times, and
always destroys the sandbox in `finally`. It confirms deletion with `sbx list`;
cleanup failure is a nonzero exit naming the sandbox. `--keep` deliberately
leaves it running and prints its id.

## Inside a CPU sandbox

The supported image provides CPython 3.12 on Linux x86_64, Python Playwright
1.63.0 and Chromium 153.0.8010.12 under `/opt/ms-playwright`.
Setup fails clearly if these browser prerequisites are missing or mismatched.
It installs hash-pinned NumPy 2.2.6 and the prebuilt MuTracer UMD distribution
under `$HOME/.local/share/render-pathtrace`, preserving its licence files.
No Node build, npm install, browser download or third-party scene assets.

```sh
cd cookbook/render-pathtrace
sh judge/setup.sh
python3 -m py_compile run.py judge/*.py
$HOME/.local/share/render-pathtrace/venv/bin/python -m unittest discover -s judge -p test_contract.py
sh judge/selftest.sh --seed 17
sh judge/grade.sh examples/good/scene.json --seed 17 --json verdict.json \
  --hdr-out studio.npy
```

`studio.npy` is linear RGBA float32, top row first, including alpha. The judge
tone maps RGB with unit-exposure linear clipping, not an artistic highlight
shoulder. Buffers and verdict dumps are ignored by git.

The trusted harness serves itself and the downloaded `dist/` over loopback
HTTP. It blocks nonlocal browser requests. `--backend cpu` forces SwiftShader;
`--backend gpu` removes that override for a future GPU lease. The actual
MuTracer backend and adapter are recorded in the verdict. An explicit
`--api webgl` flag exists for diagnosing the WebGL fallback; default is WebGPU.
Results from different APIs are not interchangeable.

## Measured wall time and limits

Commands below use seed 17; actual output belongs in `RECEIPT.md`.

| step | measured wall time |
| --- | --- |
| fresh setup, monitored runs A/B | 18 / 17 s |
| eleven contract/oracle/cleanup unit tests | 0.034 s (test body) |
| initial WebGPU grade, 120 s stage timeout | 125.806 s, failed before a frame |
| WebGPU grade, 300 s stage timeout | 306.199 s, failed before a frame |
| real self-test A/B | 411 / 391 s, both exit 1 |
| real grade A/B | 317 / 511 s, both exit 1 before HDR |

This is software rendering on two CPU cores with about 3 GB RAM, not GPU
performance. The image budget is intentionally small, 64–128 pixels per side
and 16–64 spp. Compilation counts toward the 600 s grade budget. Reference
renders use 128 spp; the final artifact's spp budget is separate.
The final wrapper enforces a 595 s process deadline and kills its own browser
descendants on expiry; that deadline path is regression-tested, not a render pass.

The furnace is an independent physical cross-check, not proof of every OpenPBR
effect. G2 checks mean reflected energy, not a directional maximum. The floor
noise patch is fixed and independently ray-checked; designs must keep it on
the floor. Random PCG sampling is intentional so the expected slope is -0.5,
not the different low-discrepancy rate of Sobol sampling. `--seed` controls
disjoint 65,536-sample sequence blocks for all stochastic tests.

GPU sandbox integration, independent cross-family reproduction and media are
not claimed here. See `REPRODUCE.md`, `SPEC.md` and `RECEIPT.md`.

## Source and licence

MuTracer: <https://github.com/pissang/mutracer>, npm `@meimu/mutracer` exactly
0.1.1, MIT; bundled dependency licences remain in its installed package.
The release's npm SHA-512 integrity and SHA-256 are checked before extraction.
This 2026-10-14 release is an owner-requested exception to the demo standard's
two-week dependency-age rule. The scene is hand-authored procedural data;
no third-party models or textures are distributed.
