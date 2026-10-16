# SPEC.md — omniverse-rtx-scenes flagship cookbook demo (Stages 1 + 2)

> **Owner:** quality is the only bar.  
> **Purpose:** Assemble three self-contained USD scenes that render on the GPU
> sandbox (Stage 2, `omniverse` template → ovrtx RTX renderer, RTX 5090 slice,
> **no internet inside the lease** → every texture, MDL, mesh must be localised
> into the bundle uploaded as one asset bundle).  
> **Assets:** NVIDIA OFFICIAL only — real robots, SimReady props, vMaterials 2 MDL,
> Environments Skies HDRI. No toy primitives, no matplotlib.

---

## 1. Asset sources (canonical, immutable)

| Source | Root URL | Description | License |
|--------|----------|-------------|---------|
| **HF Warehouse 01** | `https://huggingface.co/datasets/nvidia/PhysicalAI-SimReady-Warehouse-01/resolve/main/` | Industrial assets, SimReady Warehouse 01/02, Physics Demo Scenes, Showcase Scenes, Environments Skies HDRI | CC-BY-4.0 |
| **HF simready-assets** | `https://huggingface.co/datasets/nvidia/simready-assets/resolve/main/` | MDL base chain (`OmniPBR.mdl`, `OmniPBR_ClearCoat.mdl`, `OmniPBRBase.mdl`) | BSD-3-Clause (c) 2022 NVIDIA |
| **Isaac Sim 4.1 S3** | `http://omniverse-content-production.s3.us-west-2.amazonaws.com/Assets/Isaac/4.1/` | UR10 robot + materials | CC-BY-4.0 / NVIDIA sample content |

Every file used is recorded in `assets.lock.json` with `url`, `sha256`, `bytes`, `license`.

---

## 2. Scenes (3)

### A. `scenes/warehouse/` — Warehouse with robot
- **Robot:** UR10 (Isaac Sim 4.1) amid SimReady rack, pallet, 3 boxes.
- **Lighting:** Dome HDRI (`evening_road_01_4k.hdr`) + 2× RectLight (fill/rim) + DistantLight (sun).
- **Camera:** 8 s dolly @ 30 fps (240 frames), animated `CameraXform` translate.
- **Units / up:** `metersPerUnit = 1`, `upAxis = "Y"`, `framesPerSecond = 30`.
- **Bundle:** ~109 MB.

### C. `scenes/arm/` — Robot arm hero close-up
- **Robot:** UR10 on SimReady stainless table + 3 prop boxes.
- **Lighting:** Dome HDRI (same) + 2× RectLight (key/fill).
- **Camera:** 12 s turntable @ 30 fps (360 frames), animated `Turntable` rotate about Y.
- **Units / up:** same as A.
- **Bundle:** ~64 MB.

### B. `scenes/physics/` — Physics knock-over
- **Action:** 3 SimReady cardboxes (convex-hull colliders) knocked over.
- **Sim:** CPU PhysX (pinned `ovphysx==0.6.3`, `ovstage==0.2.0.377349`, `newton-usd-schemas==0.5.0`) at 240 Hz, sampled every 8th step → 30 fps × 6 s = 180 frames.
- **Baked:** Time-sampled `xformOp:translate` / `xformOp:orient` on each rigid body; no `physics:velocity` in output.
- **Camera:** Static hero view.
- **Units / up:** same.
- **Bundle:** ~21 MB.

---

## 3. Build reproducibility (Stage 1 contract)

```bash
cd cookbook/omniverse-rtx-scenes
python3 scenes/build_scenes.py          # idempotent: fetch → verify sha256 → localise → author
```

Requirements (pinned in `judge/requirements.txt`):
- `usd-core==25.8.0`
- `ovphysx==0.6.3`, `ovstage==0.2.0.377349`, `newton-usd-schemas==0.5.0`
- `warp-lang==1.17.0`, `numpy==2.2.6`, `packaging==23.2`

Output per scene:
```
scenes/<name>/
  scene.usda           # final (baked for B)
  template.usda        # physics template (B only)
  assets/              # all referenced assets, relative paths only
  mdl/                 # OmniPBR base chain (safety net)
```

No downloaded assets are committed — only `assets.lock.json`, `build_scenes.py`, the small `.usda` scenes, and judge artefacts.

---

## 4. Stage-2 render oracle (gates the GPU run)

The GPU sandbox renders each `scene.usda` with `ovrtx` (RTX 5090).  The judge
accepts the render **iff all** gates pass:

| Gate | Check | Known-bad mutants (≥5) |
|------|-------|------------------------|
| **G1: Silhouette vs bbox projection** | Rendered silhouette pixel coverage ≥ 0.5% of frame; bbox projection overlaps camera frustum. | camera 10 km away, camera inside geometry, camera pointing at sky. |
| **G2: No missing texture** | No magenta / default-grey on any **bound** material.  (Unbound meshes allowed; bound meshes must resolve.) | missing albedo texture, wrong UDIM tile, MDL chain not localised. |
| **G3: PhysX energy** | `scene B` total kinetic energy at frame 180 < 0.01 J (boxes settled). | gravity flipped, zero mass, collider disabled, restitution=1, 10× mass. |
| **G4: USD integrity (offline)** | `UsdUtils.ComputeAllDependencies` → 0 unresolved; every Mesh has `material:binding`; `metersPerUnit=1`, `upAxis=Y`; ≥1 Camera; bbox non-empty. | unresolved ref, wrong units, no camera, empty bbox, unbound mesh. |

Mutants live in `judge/mutants/` and are exercised by `validate_scenes.py --selftest`.

---

## 5. Deliverables (Stages 1 + 2, under `cookbook/omniverse-rtx-scenes/`)

Stage 1 (scenes and the USD judge):

- `scenes/build_scenes.py`     (fetch → verify → localise → author)
- `scenes/asset_types.py`      (fetch + sha256 helpers + licence lines)
- `assets.lock.json`           (url, sha256, bytes, license per file)
- `scenes/warehouse/scene.usda`
- `scenes/arm/scene.usda`
- `scenes/physics/template.usda`  (physics template; not rendered)
- `scenes/physics/scene.usda`     (baked trajectory; rendered)
- `judge/validate_scenes.py`      (USD-level gates + mutant selftest)
- `judge/bake_physics.py`         (offline PhysX bake, pinned venv)
- `judge/project.py`              (analytic bbox projection for the frame judge)
- `judge/requirements.txt`        (pinned toolchain)
- `judge/mutants/`                (≥5 known-bad .usda files)

Stage 2 (the GPU render, its judge and the media):

- `run.py`                           (one-command CPU build → GPU render → judge → delete)
- `render/render_job.py`             (runs inside the lease; the ovrtx render loop)
- `judge/grade_frames.py`            (G1–G4 over the downloaded frames)
- `judge/mutate_frames.py`           (7 known-bad frame mutants + `--selftest`)
- `media/make_media.sh`             (regenerates every media file from the run outputs)
- `media/result.png`, `loop.png`, `STORYBOARD.md`, `demo.mp4`, `REVIEW.json`, `MANIFEST.json`
- `PRODUCT-FRICTION.md`             (every GPU-sandbox defect, with the exact request/reply/timing)
- `RECEIPT.md`                       (verbatim outputs of two fresh end-to-end runs)
- `REPRODUCE.md`                    (independent reproduction)
- `README.md`                       (the one-command path and the "Ask your agent" prompt)

---

## 6. Size budget

| Scene | Assets | MDL | Total | Budget |
|-------|--------|-----|-------|--------|
| warehouse | 109 MB | 72 KB | ~109 MB | ≤ 300 MB |
| arm       |  64 MB | 72 KB |  ~64 MB | ≤ 300 MB |
| physics   |  21 MB | 72 KB |  ~21 MB | ≤ 300 MB |

All well within the 300 MB upload limit.

---

## 7. Known issues / constraints

- Rack asset (`RackLongEmpty_A1`) ships `<UDIM>` placeholders in its material
  layer.  `build_scenes.py` converts the binary USDC → text usda and pins every
  UDIM channel to tile `1001` (present in the lock).  The `_physics.usd`
  companion still references the binary `.usd` as a sublayer; the warning is
  benign (companion only adds collision schema; not needed for rendering).
- UR10 is Z-up; `build_scenes.py` applies a local `-90° X` tilt so the arm
  runs horizontally in the Y-up world.
- All assets fetched via HTTP range/streamed download; no full zip downloads.
---

## 8. Stage 2 — the GPU render and its oracle

Stage 2 renders the three Stage-1 scenes on the GPU sandbox and grades the
**rasterised output**, not the USD.  A render is accepted iff every gate below
passes for every scene (`judge/grade_frames.py` prints one JSON verdict).

### 8.1 What the run does (`run.py`, stdlib only)

| step | what |
|------|------|
| 1 | build the three scene bundles (`scenes/build_scenes.py --no-bake`) and `tar.czf` each one |
| 2 | create the GPU lease: `POST /sandboxes` with `{"accel":{"vram_gb":6,"template":"omniverse"}}` |
| 3 | upload each bundle: `PUT /sandboxes/{id}/files/out/<scene>.tar.gz` (raw body, ≤ 512 MiB) |
| 4 | render: one `POST /sandboxes/{id}/exec` at a time (`code`, `timeout_s: 3600`) — untar, author the RTX wrapper, render 8 s / 6 s / 6 s at 1920×1080 × 30 fps, write PNG frames + mp4 + `render_report.json` into `OUTPUT_DIR` |
| 5 | `GET /sandboxes/{id}/files` then `/files/{name}` per file; frames are sub-sampled to 1 in 15 |
| 6 | delete both leases in a `finally` and **verify** each with `GET` until 404 — an unconfirmed delete is a hard failure naming the sandbox id |

`meters` (GPU seconds, billed cost) is recorded from every reply.

### 8.2 The render contract (verified live on template `omniverse`)

- `python` inside the lease is `/opt/omniverse/bin/python` 3.12.3 with
  `ovrtx`, `ovstage`, `pxr`, `numpy`, `PIL` and `av` importable; **no**
  `ffmpeg`, `zstd`, `torch` (see PRODUCT-FRICTION.md F4).
- `exec` cwd is `/`; every path in the job is absolute.
- The RTX path tracer is switched on by `omni:rtx:rendermode = "RealTimePathTracing"`
  on the `UsdRender.Product`; stage-1 scenes carry no product, so the job
  authors a wrapper layer per scene that references `scene.usda` relatively.
- RTX exposure lives **on the camera** via `OmniRtxCameraExposureAPI_1`.  Without
  it a dome-lit frame maps to exactly 0 and every PNG is black.
- Animation comes from `ovstage.population.update_from_usd_time` with a **fresh
  renderer ordinal per frame** (a re-used ordinal is rejected `OP_FAILED` because
  the write floor has already advanced).
- Every render-var mapping must be copied out **and unmapped**: the renderer
  force-unmaps anything still alive at `destroy()` and the VRAM cap then kills
  the lease.

### 8.3 Render gates (the Stage-2 judge)

| Gate | Numeric rule | Known-bad mutants (all killed by `mutate_frames.py --selftest`) |
|------|--------------|--------------------------------------------------|
| **G1 silhouette vs bbox** | per tracked prim, rendered-silhouette ∩ analytic projected bbox **IoU ≥ 0.90** and silhouette coverage ≥ 0.5 % of frame | `camera_off` (frame shifted ¼ width) |
| **G2 no missing texture** | magenta fill ≤ 0.002 of pixels; default grey ≤ 0.30 on a **bound** material | `missing_texture` (magenta on the object), `untextured_grey` (flat 171 grey) |
| **G3 temporal** | consecutive frames differ (mean YDIF ≥ 1.0); no frame with black luma < 8 | `black_frame`, `frozen` (repeated midpoint) |
| **G4 scene USD** | the Stage-1 USD gates re-run on the same `scene.usda`, plus the baked PhysX settle check | `wrong_units` (0.01× scale), `underexposed` (×0.05) |

`mutate_frames.py` builds each mutant as a **single edit of the real downloaded
frames** (never a synthetic stand-in), then `grade_frames.py` must PASS the
untouched frames and kill all 7 mutants — the selftest exits non-zero otherwise.

### 8.4 Reproduction tolerances

Two fresh runs (RECEIPT.md) and any independent reproduction (REPRODUCE.md)
must agree as follows.  Judge gates are exact; timing tolerances cover CPU
contention, seat contention and GPU clock.

| number | must agree within |
|--------|-------------------|
| bundle bytes (max), per-scene sha256 | **exact** (same git SHA) |
| `render_report.converged_pct` | ±5 percentage points |
| G1 `iou_min` per scene | **≥ RECEIPT's value** (a stricter render is fine; lower is a regression) |
| G2/G3 gate outcomes, judge verdict | **exact** PASS |
| mutants killed by the selftest | **exact 7/7** |
| build / bundle upload MB/s | ±25 % |
| lease create seconds | no tolerance when 409s occurred; ±50 % otherwise |
| render seconds | ±20 % (RTX clock, steps/frame must be identical) |
| `billed_s` | ±5 % (meter sampling latency) |

### 8.5 Artifacts

| path | what |
|------|------|
| `run.py` | the one-command run (CPU build → GPU lease → render → download → delete) |
| `render/render_job.py` | runs inside the lease; the ovrtx render loop |
| `judge/grade_frames.py` | G1–G4 over downloaded frames, one JSON verdict |
| `judge/mutate_frames.py` | the 7 known-bad frame mutants + `--selftest` |
| `media/` | `result.png`, `loop.png`, `STORYBOARD.md`, `demo.mp4`, `make_media.sh` |
| `PRODUCT-FRICTION.md` | every place the GPU sandbox was slow, confusing, undocumented or broken |

### 8.6 Known issues / constraints for Stage 2

- The image has **no ffmpeg and no zstd**: the bundle is `tar.gz` (not the
  `tar.zst` the brief specified) and mp4 encoding goes through PyAV `libx264`.
- One `nvidia.5090` node holds a single seat: lease creation retries `409
  gpu_capacity_exhausted` for up to 45 min before giving up.  There is no queue
  position and no idle reaper — an orphan lease bills forever (see
  PRODUCT-FRICTION.md F3).
- The GPU lease has no network, so MDL base chain, textures and HDRI all ride
  inside the uploaded bundle.
