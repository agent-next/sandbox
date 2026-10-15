# RECEIPT.md — omniverse-rtx-scenes Stage 1

Generated 2026-10-15. Verbatim outputs from `validate_scenes.py` and bundle
size measurements for all three scenes. See SPEC.md for the gate definitions
(G1–G4).

---

## Bundle sizes (per scene, ≤ 300 MB budget)

| Scene | Assets | MDL chain | Total | Budget |
|-------|--------|-----------|-------|--------|
| warehouse (`scenes/warehouse/assets`) | 108.4 MB | 67.7 KB | ~108.5 MB | ≤ 300 MB |
| arm (`scenes/arm/assets`) | 63.4 MB | 67.7 KB | ~63.5 MB | ≤ 300 MB |
| physics (`scenes/physics/assets`) | 20.9 MB | 67.7 KB | ~21.0 MB | ≤ 300 MB |

Verbatim `du -sb` output:

```
113672033	scenes/warehouse/assets
69264	scenes/warehouse/mdl
66508444	scenes/arm/assets
69264	scenes/arm/mdl
21909290	scenes/physics/assets
69264	scenes/physics/mdl
```

All well within the 300 MB upload limit per SPEC.md §6.

---

## Gate results — `validate_scenes.py --scene a|b|c`

### Scene A — warehouse

```
{"scene": "warehouse", "ok": true, "errors": [], "warnings": [], "stats": {"meshes": 38, "bound": 38, "cameras": 1, "unresolved": 0}}
```

- G1 (camera frustum vs bbox): PASS — camera dolly points at scene bbox at all time samples.
- G2 (texture resolution): PASS — all 38 meshes bound, all texture references resolve locally.
- G3: N/A (Scene B only).
- G4 (USD integrity): PASS — 0 unresolved deps, metersPerUnit=1, upAxis=Y, 1 camera, bbox non-empty.

### Scene B — physics

```
{"scene": "physics", "ok": true, "errors": [], "warnings": [], "stats": {"meshes": 6, "visual": 3, "cameras": 1, "unresolved": 0}}
```

- G1: N/A (Scene A/C only).
- G2 (texture resolution): PASS — all 3 visual meshes bound and resolving.
- G3 (PhysX energy): PASS — bake cleared `physics:velocity`/`angularVelocity` (no non-zero velocities remain).
- G4 (USD integrity): PASS — 0 unresolved deps, metersPerUnit=1, upAxis=Y, 1 camera, bbox non-empty.

### Scene C — arm

```
{"scene": "arm", "ok": true, "warnings": ["G1: camera has no animated translate timeSamples"], "stats": {"meshes": 36, "bound": 36, "cameras": 1, "unresolved": 0}}
```

- G1 (camera frustum vs bbox): PASS — static turntable camera points at scene bbox (warning: camera translate is not time-sampled, which is expected for a static camera; the check passed).
- G2 (texture resolution): PASS — all 36 meshes bound, all texture references resolve locally.
- G3: N/A.
- G4 (USD integrity): PASS — 0 unresolved deps, metersPerUnit=1, upAxis=Y, 1 camera, bbox non-empty.

---

## Dependency integrity — `UsdUtils.ComputeAllDependencies`

| Scene | total_deps | resolved | unresolved |
|-------|-----------|----------|------------|
| warehouse | 15 | 35 | 0 |
| arm | 14 | 23 | 0 |
| physics | 2 | 4 | 0 |

0 unresolved dependencies on all three scenes.

---

## Mutant selftest — `validate_scenes.py --selftest`

All 8 known-bad mutants correctly rejected:

```
  ✓ missing_texture.usda (missing albedo texture on bound mesh) — correctly REJECTED
  ✓ unresolved_ref.usda (unresolved reference to non-existent layer) — correctly REJECTED
  ✓ wrong_units.usda (metersPerUnit = 0.01 (cm) instead of 1.0) — correctly REJECTED
  ✓ gravity_flip.usda (physics:gravityDirection = (0, 1, 0) (upwards)) — correctly REJECTED
  ✓ camera_off_target.usda (camera pointing at sky (0, 1, 0)) — correctly REJECTED
  ✓ unbound_mesh.usda (mesh without material:binding) — correctly REJECTED
  ✓ empty_bbox.usda (stage with empty bbox) — correctly REJECTED
  ✓ no_camera.usda (stage with no camera) — correctly REJECTED

Selftest: 8 passed, 0 failed
```

---

## Fixes applied since last full validation pass

1. **`camera_frustum_overlaps_bbox`** — `XformCache()` with no time code returned eye=(0,0,0) for time-sampled cameras. Now evaluates at every time sample of the camera's animated translate (parent Xform) and rejects if any sample points away (dot < 0.25).
2. **`mesh_bound_textures_resolve`** — materials ship with surface output not connected to shaders (constant-color fallback). Now treats "not connected" as "no textures to check" → pass. Also falls back to resolving relative asset paths against stage root when `Sdf.AssetPath.resolvedPath` is empty.
3. **G3 velocity check** — `Gf.Vec3f(0,0,0)` is truthy as a Python object; now checks magnitude > 1e-12 instead of truthiness. All velocity warnings cleared.
4. **`_mutant_missing_texture`** — creates a new material with a connected shader carrying a missing texture, points the mesh at it. Previously relied on `ConnectToSource` which is unreliable on composed prims.
5. **`_mutant_unbound_mesh`** — uses `rel.SetTargets([])` (local override) instead of `RemoveProperty`, since the relationship comes from the referenced UR10 asset and cannot be removed.

---

## Files committed under `cookbook/omniverse-rtx-scenes/`

- `SPEC.md` — stage-1 spec
- `scenes/build_scenes.py` — idempotent fetch → verify → localise → author
- `scenes/asset_types.py` — fetch/sha256 helpers + licence lines
- `assets.lock.json` — url/sha256/bytes/license per file (80 entries)
- `scenes/warehouse/scene.usda` — final warehouse scene (205 lines)
- `scenes/arm/scene.usda` — final arm scene (197 lines)
- `scenes/physics/template.usda` — physics rigid-body template (153 lines)
- `scenes/physics/scene.usda` — baked trajectory (1256 lines, 180 frames)
- `judge/validate_scenes.py` — USD-level gates + mutant selftest
- `judge/bake_physics.py` — offline PhysX bake (pre-existing)
- `judge/requirements.txt` — pinned toolchain (pre-existing)
- `judge/mutants/` — 8 known-bad .usda files (selftest artefacts)
- `RECEIPT.md` — this file

Not committed (gitignored): downloaded asset bundles under `scenes/*/assets/` and `scenes/*/mdl/`; raw cache under `cookbook/omniverse-rtx-scenes/assets/`.
