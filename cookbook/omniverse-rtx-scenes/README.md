# omniverse-rtx-scenes — NVIDIA SimReady scenes, photoreal, on a disposable GPU

An agent builds three USD scenes out of NVIDIA's official SimReady / Isaac
Sim assets (a UR10 warehouse dolly, a PhysX crate collapse, a robot-arm
hero turntable), uploads them to an **agent-next GPU sandbox** (RTX 5090
slice, `omniverse` template), renders all three photorealistically with
the **RTX path tracer** (ovrtx, 1920×1080 × 30 fps), and a judge that
cannot be flattered decides the frames are real: silhouette-vs-bbox IoU,
no missing textures, no frozen or black frames, physics settled. The GPU
lease exists for the length of the render and is then deleted and its
death verified — you pay for seconds of GPU, not for an idle VM.

Why a sandbox: the render needs an RTX 5090, NVIDIA's Omniverse stack and
~250 MB of licensed assets. The lease has **no network**, so everything
the renderer needs rides inside the uploaded bundle — the same
self-contained contract any customer render farm would demand.

## The one-command run

```bash
export SBX_API_KEY=<your key>        # agent-next control plane key
bash judge/setup.sh                  # once: pinned venv for the judge
python3 run.py                       # CPU build -> GPU render -> judge -> delete
```

`run.py` is standard library only. It reads `SBX_API_URL` (default
`https://api.sbx.agent-next.com`) and `SBX_API_KEY` (fallbacks:
`E2B_API_KEY`/`GPU_API_KEY`). Every step prints its wall time; the run
ends non-zero on any failure, naming the sandbox id if cleanup could not
be confirmed.

What it does, step by step (wall times measured on the receipt runs,
RECEIPT.md):

| step | what | measured |
|------|------|----------|
| build | `scenes/build_scenes.py --no-bake` → 3 scene folders | 2.3 s |
| bundle | `tar.gz` per scene (89 MB max; the image has no zstd — F4) | ~10 s |
| create lease | `POST /sandboxes` `{"accel":{"vram_gb":6,"template":"omniverse"}}` | 2.5 s when a seat is free; **409 retries up to 45 min** when the single 5090 seat is taken (F1) |
| upload | `PUT /sandboxes/{id}/files/out/<scene>.tar.gz` | 89 MB at ~200 MB/s |
| render | one `exec` (3600 s budget): untar, author the RTX wrapper, 600 frames path-traced, mp4 via PyAV | see RECEIPT.md |
| download | `GET /files` + per-file; frames sub-sampled 1-in-15 | see RECEIPT.md |
| judge | `judge/grade_frames.py` G1–G4 + the 7-mutant selftest | ~1 min |
| delete | `DELETE` both leases, then `GET` until 404 — unconfirmed is failure | 0.2 s |

Limits, stated plainly:

- **One seat.** The GPU class `nvidia.5090` has a single seat on this
  account; `run.py` retries `409 gpu_capacity_exhausted` for ~45 min and
  then fails loudly. There is no queue and no idle reaper
  (PRODUCT-FRICTION.md F1/F3).
- **No network in the lease.** Assets, MDL chain and HDRI must be inside
  the bundle; `build_scenes.py` localises everything (`assets.lock.json`
  pins url + sha256 + licence per file).
- **512 MiB upload cap** per `PUT`; each bundle is ≤ 300 MB by spec.
- First run downloads ~250 MB of NVIDIA assets (cached under `assets/`).

## Ask your agent

> Run the omniverse-rtx-scenes demo in cookbook/omniverse-rtx-scenes:
> `bash judge/setup.sh`, then `python3 run.py` with SBX_API_KEY set.
> It builds three SimReady USD scenes, rents an RTX 5090 sandbox slice
> for the render, path-traces 600 frames at 1080p30, grades them with the
> silhouette/texture/temporal judge, kills all 7 known-bad mutants, and
> deletes the lease. Show me the verdict JSON, the billed GPU seconds and
> the mutant kill table; if any gate fails, fix the render — not the judge.

## The judge

`judge/grade_frames.py` (exit 0 only on full pass):

| gate | rule |
|------|------|
| G1 silhouette | rendered silhouette ∩ analytic projected bbox **IoU ≥ 0.90** per tracked prim |
| G2 texture | magenta ≤ 0.002 of pixels, default-grey ≤ 0.30 (bound materials) |
| G3 temporal | consecutive frames differ (YDIF ≥ 1.0), no black frames |
| G4 scene USD | stage-1 USD gates + PhysX settle check re-run on the same scenes |

`judge/selftest.sh <run_dir>` re-grades the run's own frames mutated one
defect at a time (magenta texture, grey, black frame, frozen, camera
shifted, underexposed, wrong units) — all 7 must die. Kill rate is
printed; below 90 % is a failure.

## Files

`SPEC.md` (gates + contracts) · `PRODUCT-FRICTION.md` (every product
defect found, with requests and timings) · `RECEIPT.md` (two fresh runs,
verbatim) · `REPRODUCE.md` (independent reproduction) · `media/`
(result.png, loop.png, demo.mp4, STORYBOARD.md, MANIFEST.json).
