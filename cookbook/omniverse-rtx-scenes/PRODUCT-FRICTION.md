# PRODUCT-FRICTION.md — the agent-next GPU sandbox, as a paying customer

This demo's whole point is the product path: an agent builds a `tar.gz` on a
CPU sandbox, uploads it, renders on a 6 GB RTX 5090 slice in the `omniverse`
template, downloads the frames and pays for seconds of GPU. This file records
every place that path was **slow, confusing, undocumented or broken**, with the
exact request, the exact reply and the measured timing.

All request/response pairs below were observed on
`https://api.sbx.agent-next.com` on 2026-10-16, header `X-API-Key: <key>`.
Requests were made with the Python standard library only. Sandbox ids are this
document's own; every lease it created was deleted and verified 404.

---

## F1. 15-minute 409 seat starvation with no progress signal

**Request:** `POST /sandboxes {"accel":{"vram_gb":6,"template":"omniverse","reserve":"exec"}}`
**Reply (measured 3×):**

```json
{"code":409,"message":"lease create failed: no GPU node has a free seat (1/1 answered the probe)",
 "error_code":"gpu_capacity_exhausted","error":"gpu_capacity_exhausted","retry_after_s":5,"class":"nvidia.5090"}
```

This build spent **~15 minutes polling** (30 attempts at a 30 s backoff)
before it got a seat. Observations:

- `retry_after_s: 5` is advisory-only. Polling at 5 s for a single-seat
  `nvidia.5090` node is pointless and just burns the caller's thread; 30 s
  is what works, but it is a guess, not documented.
- The message gives no way to know **who** holds the seat, whether it is a
  long render or an abandoned lease, or what the queue position is.
- There is **no documented way to wait for a seat** other than tight-polling
  a POST. A long-running-friendly alternative (a wait/queue parameter on the
  create, or a `position` field in the 409) is absent.
- `"1/1 answered the probe"` is the only hint that there is exactly **one**
  GPU node on the whole plane. Combined with F2, this means a single node
  outage blocks every GPU customer at once.

### F1 (update, 2026-10-16, the full receipt run)

The end-to-end run dwarfs the 15 min above. A supervisor restarted
`run.py` (90 attempts × 30 s ≈ 45 min per process, ~6 h total) across an
afternoon in which the seat was effectively never free, and the picture
is worse than "wait your turn":

- `GET /sandboxes` on this account repeatedly returned **`[]`** — *no
  lease of ours exists* — while `POST` still answered 409 with
  `"1/1 answered the probe"`. The 409 therefore reports **cross-tenant**
  contention (another account's render on the single shared node), and a
  customer has **no way to see that**: their own inventory says they own
  nothing, so the failure reads as "the product is broken" rather than
  "the fleet is busy".
- No estimate, no position, no projected wait. The caller cannot choose
  between "keep a thread parked for 6 h" and "come back tomorrow".
- `reserve: "exec"` vs omitting it produced byte-identical 409s: the field
  buys nothing observable at create time.
- What a customer actually needs: a `GET /gpu/availability` (node, class,
  free seats, expected wait) and a create that can *block* until a seat
  frees instead of forcing the caller to re-invent a retry loop with an
  undocumented 30 s backoff.

## F2. `503 node unreachable` after a 198 s hang, with a misleading link

**Request:** same create as F1.
**Reply:**

```json
{"code":503,"message":"lease create failed: no GPU node reachable (1 configured): {'pc-5090': 'node unreachable: ReadError: '}",
 "status":"https://sla-prober.robert-alexander37899.workers.dev"}
HTTP 503, time_total = 198.224 s
```

Three separate problems in one reply:

1. **198 seconds to fail.** A flapping node is not discovered for over three
   minutes; the caller cannot tell "still trying" from "hanging". Every caller
   must implement its own long-poll timeout around a call that should fail
   fast.
2. `'node unreachable: ReadError: '` — the inner error is an **empty, truncated
   exception string**. Not "connection refused", not "TLS", not "timeout". The
   customer cannot distinguish node-down from network-split.
3. `status: https://sla-prober.robert-alexander37899.workers.dev` — a link that
   looks like a personal/throwaway domain (not `*.agent-next.com`). In a
   public repo that reads as a suspicious link and cannot be trusted; it is
   also not documented anywhere. It should be a documented status page under
   the company domain.

## F3. No idle reaper: a crashed caller bills forever

**Observed (2×):** after an interrupted run, a lease created by an earlier attempt
(`gl-0c86c5-3`, template `omniverse`, 6 GB) stayed resident for **1680 s**
(~28 min) with `exec_wall_s: 0.0`, `busy_s: 0.0`, `0` files, while its owner
was already gone — and while it held **the only GPU seat**, so every other
create returned the F1 409.

- There is no idle timeout on the lease for `reserve: "exec"` (the meters
  report `idle_timeout_s: 0.0`, `auto_paused: 0`).
- A customer that loses connectivity loses money *and* removes capacity from
  the shared pool at the same time. The `create` retry loop in F1 and this
  interact badly: the same caller blocks itself out of its own seat.
- **The product should expose an idle reaper** (or honour the `timeout-min`
  semantics of the CPU product) and **the 409 message should carry the age**
  of the incumbent so the caller can tell "another render running" from
  "another tenant died".

**Second occurrence (same day, 2026-10-16T07:0xZ):** the same failure mode
with `gl-4bed02-33`, resident **3018 s (~52 min)** with
`exec_wall_s` at zero until our probes ran, `idle_timeout_s: 0.0`, holding
the single seat through an entire retry budget. It was identified as our own
earlier attempt's artifact (only our own probe scripts `job_1..5.py` were
inside it) and deleted; a customer without that forensics has no safe action
available at all (see F8 on ownership proofs).

## F4. `ffmpeg` and `zstd` are missing from the `omniverse` image; only `av` is there

**Request:** `POST /sandboxes/{id}/exec {"code":"import shutil, glob; ..."}`

```json
{"ffmpeg_which": null, "ffprobe_which": null, "zstd": null, "tar": "/usr/bin/tar",
 "PATH": "/opt/omniverse/bin:/usr/local/nvidia/bin:/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}
```

A graphics/render image with **no video encoder on PATH** while shipping PyAV
19.0.1 (FFmpeg's own Python binding, which bundles its own libraries) is an
odd split: encoding is possible, but only by using the binding's API, not the
tool every customer knows. Documented nowhere. Effect on this demo: the render
job had to be rewritten to encode with `av` instead of shelling out to
`ffmpeg`.

Same for archive handling: `zstandard` is not importable either
(`ModuleNotFoundError: No module named 'zstandard'`), so the `.tar.zst` bundle
format the task specified **cannot be unpacked on the lease** and had to be
changed to `.tar.gz` (3× the bytes for these textures, paid for twice: upload
download).

## F5. The exec filesystem root is a guess, not an input

`OUTPUT_DIR` is injected as a global into the exec body and resolves to
`/mnt/data/sbx-local/leases/<id>/out`. What is *not* documented:

- `PUT /files/<name>` lands at the **lease root**, `PUT /files/out/<name>`
  lands at `<lease>/out` — two prefixes, both work, only discovered by
  probe. `GET /files` then lists OUT-relative names (`out/probe2.txt` was
  listed as `probe2.txt`), so the name the caller PUT is **not** the name it
  GETs back.
- `exec` runs with `cwd = "/"`, so no relative path works; a job that wants
  to find its inputs must either take `OUTPUT_DIR` as a global, or walk the
  filesystem looking for its uploaded files.
- The path name `sbx-local` in `/mnt/data/sbx-local/...` is an internal
  implementation name that a customer has no reason to know.

## F6. Small verbosity problems that multiply into confusion

- `PUT` returns a **200 with no `sandboxID`** while `POST /exec` returns it on
  every reply. Tracking a request across the API requires remembering which
  routes echo the id.
- `DELETE` returns the final meters dict but **no id**; the caller has to keep
  its own id (which it does) and verify by GET, as the reference runner does.
- `GET /files` returns `{"sandboxID":..., "files":[...]}` while
  `GET /files/{name}` returns the **raw bytes with no envelope at all** —
  status-code only, so a truncated download looks like an empty file, not a
  failing request. The reference runner therefore compares `len(data)` to the
  listing's `size` per file.
- No `X-Request-Id`/correlation id on any reply, so a 503 that took 198 s
  cannot be traced with support.

## F7. No honest GPU telemetry

`GET /sandbox/{id}` returns a `gpu` block whose useful fields are all null on
a live lease:

```json
"gpu": {"class": "nvidia.5090", "device_name": null, "vram_slice_gib": 6.0,
        "vram_used_mib": null, "vram_peak_mib": null, "util_pct": null,
        "sampled_at": null}
```

A customer renting a 6 GB **RTX 5090** cannot see whether the render actually
used the GPU (util %), how much VRAM it peaked at, or which device it got —
only the class enum. `billed_s` is there, `util_pct` is not. For a product
whose value proposition is "pay for seconds of GPU", the telemetry that
proves the GPU was used is the first thing a customer looks for and cannot
get.

---

## F8. A lost create reply is unresolvable: no idempotency key

`POST /sandboxes` (this run, 2026-10-16T04:52Z, attempt 87 of the retry
loop):

```
run.py: GPU create failed: {'status': 503, 'body': {'error': 'gateway is
restarting', 'code': 'restarting', 'retry_after_s': 5}, 'attempt': 87}
```

Two problems in one:

1. **The 503 was fatal in the first driver version.**  A control-plane
   restart is transient — the lease was *not* created — but any non-409
   status aborted the whole 45-minute retry loop at attempt 87 of 90, five
   minutes before the budget would have carried it through the restart.
   `run.py` now retries 5xx like it retries 409s (respecting
   `retry_after_s`).

2. **A *lost* reply (read timeout) is worse: it may have created a lease.**
   There is no idempotency key, no client-supplied name, and every lease
   shows the same `clientID: "gpu-lease"`, so a lease that appears in the
   inventory after a timed-out POST **cannot be proven to be yours** — a
   parallel agent creating at the same moment is indistinguishable. The
   only safe behaviour is to record the suspect id and refuse to
   auto-adopt or delete it (deleting a lease you cannot prove you created
   can destroy someone else's work). One lost reply earlier today left
   `gl-0c86c5-3` holding the account's single seat for **24 h of idle
   billing** (F3) precisely because cleanup could not be proven safe
   automatically.

   An `Idempotency-Key` header on create (or a client-settable
   `metadata.name`) would make the lost-reply case a one-line lookup
   instead of a judgement call.

---

## F9. Upload throughput is unpredictable by 500×

**Same route, same account, same day (2026-10-16):**

| when | bytes | wall | throughput |
| --- | --- | --- | --- |
| stage-1 probe | 21 MB (`physics.tar.gz`) | ~0.1 s | **~200 MB/s** |
| render smoke | 52,440,519 B (`arm.tar.gz`) | 136.24 s | **0.385 MB/s** |

`PUT /sandboxes/{id}/files/arm.tar.gz` → `200` both times. There is no
documented throughput class, no progress signal during a multi-minute PUT
(the caller's HTTP client just blocks), and no size limit between "works"
(512 MiB documented cap) and "fast". For this demo the three bundles are
166 MB together: at the measured 0.385 MB/s that is **~7.5 minutes of pure
upload** on every run — 3× the cost of the render itself at 64 spp. A
customer cannot budget a run without knowing which of the two regimes they
will hit.

## F10. A long exec is a black box: no progress, no partial log

`POST /sandboxes/{id}/exec {"code": ..., "timeout_s": 3600}` returns
`result.stdout`/`result.stderr` only **when the job finishes**. The reply
envelope (measured):

```json
{"result": {"ok": true, "seq": 3, "nonce": "…", "code_wall_s": 2512.9,
            "stdout": "…", "stderr": "…", "chk": true, "report": {…}}}
```

During the 42-minute render there is **no way to read partial stdout** — the
job's own log file is written under OUTPUT_DIR, but that only helps for
files, and the gateway syncs the listing on its own schedule. `seq`, `nonce`
and `chk` are undocumented (they look like an execution-ordering/checksum
scheme the caller is never told how to use). A job that renders 600 frames
cannot report "frame 240/600" to its operator except by polling file
listings — which is what `run.py` ends up doing.

## F11. The `omniverse` template's renderer stack is undocumented and version-skewed

The lease ships `ovrtx 0.5.1`. Nothing in the product docs describes it;
the upstream docs at `nvidia-omniverse.github.io/ovrtx` describe a newer
build, and two of their own links (`/rendermodes/pathtracing.html`,
`/configuration.html`) 404 — the real pages live under
`/sensors/cameras/render_modes/…`. Discovering how to get clean path-traced
frames required: reading the ovrtx Python API on the lease (`dir(ovrtx)` —
no denoiser), downloading the 0.6.0 sdist from PyPI (C/C++ only), and only
then finding that **the OptiX denoiser and sample counts are USD attributes
on the RenderProduct** (`omni:rtx:pt:samplesPerPixel`,
`omni:rtx:pt:denoising:enabled`), not Python API surface at all. A template
that exists to run this renderer should pin and document its render settings
surface; the difference between the shipped 0.5.1 and the documented 0.6
behavior is exactly the kind of thing that costs a customer an afternoon.

## F12. `OUTPUT_DIR` is a code global, not an environment variable

`os.environ.get("OUTPUT_DIR")` inside an exec returns `None`; the value is
injected as a **global in the exec body's namespace**. Any job that follows
the universal convention of reading its config from the environment (12-factor
style, works identically in Docker/CI) silently gets `None` and builds paths
from the wrong root. Combined with `cwd = "/"` (F5), a job has exactly one
correct way to find its files and no documented way to learn it.

---

## What worked well (for contrast)

- `POST /sandboxes` → 201 in **2.5 s** when a seat was free, with a clean id.
- `PUT` of a small file is effectively instant when the fast path is hit
  (see F9 for when it is not).
- The exec contract (`code` + `timeout_s` → `{ok, result, report, meters}`)
  is simple and the `report` dict rides along untouched; the whole render
  job's metrics reach the caller in one field, stdout and stderr included.
- `DELETE` → `GET` 404 confirmed cleanup in **~0.2 s total**.
- The 409/503 both arrive as machine-readable `error_code`s, which made the
  retry logic in `run.py` straightforward.
