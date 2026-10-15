# SPEC.md — omniverse-rtx-scenes flagship cookbook demo (Stage 1)

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

## 5. Deliverables (this branch, under `cookbook/omniverse-rtx-scenes/`)

- `SPEC.md`            (this file)
- `scenes/build_scenes.py`     (fetch → verify → localise → author)
- `scenes/asset_types.py`      (fetch + sha256 helpers + licence lines)
- `assets.lock.json`           (url, sha256, bytes, license per file)
- `scenes/warehouse/scene.usda`
- `scenes/arm/scene.usda`
- `scenes/physics/template.usda`  (physics template; not rendered)
- `scenes/physics/scene.usda`     (baked trajectory; rendered)
- `judge/validate_scenes.py`      (USD-level gates + mutant selftest)
- `judge/bake_physics.py`         (offline PhysX bake, pinned venv)
- `judge/requirements.txt`        (pinned toolchain)
- `judge/mutants/`                (≥5 known-bad .usda files)
- `RECEIPT.md`                    (verbatim outputs: bundle bytes, dep counts, gate results)

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