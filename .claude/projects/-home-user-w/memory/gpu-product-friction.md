---
name: gpu-product-friction
description: Live-verified defects in the agent-next GPU sandbox API found on 2026-10-16
metadata:
  type: project
---

# GPU sandbox API — verified defects (measured 2026-10-16)

Base `https://api.sbx.agent-next.com`, header `X-API-Key`. Template `omniverse`, class `nvidia.5090`, 6 GB.

## PUT /files path prefix is DOUBLED inside OUTPUT_DIR  ← the big one

- `OUTPUT_DIR` (exec global) = `/mnt/data/sbx-local/leases/<id>/out`.
- `PUT /files/out/<name>` physically lands at `.../leases/<id>/out/out/<name>` — the
  supplied name is appended literally, so the `out/` prefix adds a SECOND `out/`.
- `PUT /files/<name>` lands at `.../leases/<id>/out/<name>` (correct: this is the path to use).
- `GET /files` lists names relative to `OUTPUT_DIR`, so `out/<name>` is listed as `<name>`:
  the name you PUT is NOT the name you GET. Bytes round-trip, so a strided downloader
  silently misses the directory nesting.

## Everything GET-served is synced, not live

`GET /files` reflects a sync snapshot: a file PUT during this exec was listed by
`GET /files` but NOT visible to the exec's own `OUTPUT_DIR` walk... (verified
directly the reverse case: PUT'd file appeared on the lease filesystem, and
`GET /files` also listed it — the sync is one-way from the lease out).

## Upload throughput is NOT 200 MB/s

50 MB `PUT` took 38.4 s = **1.3 MB/s**. PRODUCT-FRICTION.md's earlier "~200 MB/s"
measurement was a small-file artifact (0.1 s for 21 MB reads as fast but the
large-bundle case is 30x slower). Plan minutes, not seconds, for a 109 MB bundle.

## 409 seat starvation is real and cross-tenant

`{"code":409,"error_code":"gpu_capacity_exhausted","retry_after_s":5,"class":"nvidia.5090"}`.
`GET /sandboxes` returns `[]` (own inventory empty) while 409 keeps coming —
another tenant holds the single seat, and nothing tells the caller.

## 503 gateway restart, no idempotency

`{"error":"gateway is restarting","code":"restarting","retry_after_s":5}` — retry
5xx like 409. No `Idempotency-Key`/`metadata.name` on create, so a lost reply is
unresolvable (record, never auto-adopt/delete).

## What works

- `POST /sandboxes` → 201 in ~2.5 s with `sandboxID` when a seat is free.
- `DELETE` → 200 + meters; `GET` afterwards → 404 in <1 s.
- exec: `cwd="/"`, python `/opt/omniverse/bin/python` 3.12.3, `OUTPUT_DIR` global,
  `report` dict rides back verbatim in the reply.
- `ovrtx` 0.5.1, `ovstage`, `pxr`, `PIL`, `numpy`, `av` 19.0.1 importable.
  **No ffmpeg/ffprobe/zstandard** → tar.gz bundles + PyAV encoding.
- `Renderer.step(self, render_products: set[str], delta_time: float, *, ordinal=None)`
  matches render_job.py; `FrameOutput` exposes `converged`/`progression`;
  `MappedRenderVar` exposes `data`/`unmap`.
- Meters dict is rich: running_s, resident_s, billed_s, busy_s, idle_active_s,
  exec_wall_s, idle_timeout_s, stray_compute...
