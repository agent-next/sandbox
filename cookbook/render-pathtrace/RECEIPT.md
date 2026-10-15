# GPU acceptance, 2026-10-14

**PASS on two fresh GPU `browser` leases.** Both ran `python3 run.py` (seed 17)
from this checkout. Every judge, scene and runner file's SHA-256, as recorded by
the lease in `runner.json`, matches commit `193f632`. Later commits add media
and documentation only.

## Versions (judge/VERSIONS.txt, identical in both leases)

```text
Python 3.12.3
Playwright 1.55.0
Chromium 140.0.7339.16
numpy 2.2.6
MuTracer 0.1.1 (MIT)
MuTracer SHA-256 a84ec7913ae95e49b1172ea0cba45f20179f4a5d0cce08768d4812348e3e7b4a
```

Adapter in both verdicts:
`{"architecture": "blackwell", "vendor": "nvidia"}`, backend `webgpu`.
`setup.log` ends with `MuTracer 0.1.1 SHA-512 and SHA-256 verified` … `setup PASS`.

## Steps and wall times (seconds)

| step | lease A exit / s | lease B exit / s |
| --- | --- | --- |
| upload (3.78 MB MuTracer in 29 parts + 23 kB source; PUT) | — / 37.7 since start | — / 38.3 since start |
| setup (offline; image NumPy reused, no wheel upload) | 0 / 1.093 | 0 / 0.905 |
| judge unit tests (15) | 0 / 1.215 | 0 / 1.191 |
| runner unit tests (13) | 0 / 0.071 | 0 / 0.091 |
| self-test | 0 / 31.771 | 0 / 29.643 |
| grade | 0 / 6.240 | 0 / 5.826 |
| caller total, create → GET 404 | 100.205 | 124.413 |

Cleanup, both leases: `DELETE 200; GET 404`. Lease meters: 76.8 s and 75.0 s
billed at a 2 GiB slice, `stray_compute: false`.
The run is dominated by the upload: the public files route measured about
0.1 MB/s per lease regardless of chunk size.

## Gate results (identical in both leases)

| gate | measured | pass rule |
| --- | --- | --- |
| G1 furnace, rho 0.18 / 0.5 / 0.8 | 0.17946 / 0.49849 / 0.79764; background max error 0.0 | \|mean − rho\| ≤ 0.01716 / 0.02099 / 0.02459 |
| G2 energy, max channel | clay 0.617, coat 0.305, floor 0.621, metal 0.942, velvet 0.347 | ≤ 1.05 |
| G3 RMSE at 1/2/4/8 spp vs 128-spp reference | 0.20883 / 0.14836 / 0.10612 / 0.07621; slope −0.48463 | slope in [−0.65, −0.35] |
| G4 HDR SHA-256, same seed ×2 | `b82318c76632e81d9e27cc5fabcc8907e101efa46a97edf8f1c752210d8355e4` ×2; seed 18 → `0a6bd2fd…` | identical; other seed differs |
| G5 median / clipped / floor noise | 0.61611 / 0.00486 / 0.02046; non-finite 0; 512×512, 128 spp | [0.08, 0.85] / ≤ 0.10 / ≤ 0.15 |

The final `studio.npy` hash is byte-identical across the two leases
(`b82318c7…55e4`), so cross-lease agreement is exact, not merely within 1e-4.

## Self-test (identical verdicts in both leases, timing removed)

```text
{"kill_rate": 1.0, "killed": 8, "selftest_pass": true, "total": 8, "verdict_determinism": true, "wrong_albedo_rejected": true}
```

| mutant | rejected by |
| --- | --- |
| energy_gain (baseColor 1.6) | schema: `number outside [0, 1]` |
| hidden_emission (floor) | schema: `G2: undeclared emission` |
| clipping (lights ×100) | G5 render gate |
| underexposed (lights and environment ÷200) | G5 render gate |
| one_sample | schema: `spp budget` |
| inside_sphere | schema: `camera inside sphere` |
| nan_material | `non-finite JSON: NaN` |
| resolution | schema: `number outside [64, 512]` |
| wrong-albedo renderer control | G1: rho 0.18 rendered 0.08973 |

Two mutants (clipping, underexposed) and the renderer control need a real HDR
render to be caught; the rest are rejected before rendering.

## Media (seed 17, `sh media/make_media.sh`)

`media/frames.py` rendered the good scene at 1–256 spp on one more GPU lease
(cleanup `GET 404`), measured against a 1024-spp reference with a different
sample stream:

| spp | 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RMSE | 0.2095 | 0.1472 | 0.1049 | 0.0748 | 0.0529 | 0.0375 | 0.0270 | 0.0196 | 0.0145 |

`media/MANIFEST.json` lists each file's source data and SHA-256.

## Deviations

1. MuTracer 0.1.1 was published 2026-10-14, inside the standard's two-week
   exclusion window; the owner pinned it. Its npm SHA-512 integrity and a
   SHA-256 are checked on the caller and again in the lease before extraction.
2. `run.py` uses the public REST API instead of the `sbx` CLI for the GPU path,
   because GPU leases are created with an `accel` body and run Python through
   `exec`. It uploads the local checkout rather than cloning a ref, since the
   GPU lease has no network. Cleanup still runs in `finally` and needs GET 404.
3. The CPU backend (SwiftShader WebGPU) lost its device before any HDR frame
   in every attempt (six bounded runs plus two fresh monitored runs, 306–511 s
   each, `A valid external Instance reference no longer exists`). It stays a
   documented diagnostic path, not an accepted backend.
4. A GPU lease whose Chromium silently fell back to SwiftShader ran into the
   556 s timeout once during development. The driver now rejects a non-NVIDIA
   adapter at start (`test_gpu_backend_fails_fast_on_software_adapter_at_start`).
5. `loop.png` shows the self-test matrix rather than a per-iteration score
   history: the scene was tuned by hand while the judge was being calibrated,
   so no agent iteration log exists to plot.
