# Small GPU sandbox

Run a tiny CUDA computation in a **1 GiB VRAM slice**, verify its answer, and
destroy the lease. This uses a slice of a shared host GPU; it does not select
a dedicated small GPU card. GPU access and GPU credit are required on your
key, and placement depends on available capacity.

From this repository's root, with Python 3.10 or newer (no extra packages):

```bash
export SBX_API_KEY=<your key>
python3 cookbook/small-gpu/run.py
```

The script uses the hosted REST API, creates a lease with
`{"accel":{"vram_gb":1,"reserve":"exec"}}`, runs a CUDA tensor sum with a
60-second job budget, and checks for the exact answer `523776`. It prints
the GPU name and allocated tensor bytes, then destroys the lease in a
`finally` block and confirms it is absent or dead. A failed job or unconfirmed
cleanup exits nonzero. This is a functional smoke check, not a performance
benchmark or a proof of tenant isolation.

GPU leases have no idle auto-pause through the plugin. If you interrupt or
lose the client, use `sandboxes_list` and `sandbox_kill` to release the id
printed by the script. CPU `--timeout-min` does not apply to this lease.
The CUDA allocation shown is the job's tensor allocation, not the enforced
VRAM cap. The requested 1 GiB slice caps the whole vGPU device: ~756 MiB is
used at rest (the vGPU baseline, measured 2026-10-15 on gpu-lease-v06) and
each CUDA process's context (~0.3 GiB) counts too, so only ~0.3–0.6 GiB is
allocatable. Rule of thumb: `vram_gb − ~0.4 GiB` for the first CUDA process and ~0.3 GiB less per additional CUDA process; this smoke check allocates ~4 KiB, which is why it fits.

Cleanup uses `DELETE /sandboxes/{id}`, followed by `GET /sandboxes/{id}`.
The check accepts HTTP 404 (absent), or HTTP 200 with `{"phase":"dead"}`
(a terminal lease record). A lost DELETE response still triggers the GET;
a running lease or failed confirmation is an error naming the id to kill.

With the plugin, ask your agent:

> List the live sandbox templates. Create a GPU sandbox with template `gpu`
> and `vram_gb: 1`. Run a small torch CUDA tensor sum and assert its answer.
> Report the actual GPU name and result, then kill the sandbox even if the
> command fails. Confirm that the sandbox is gone. Do not leave a GPU lease
> running.

The open-source MIT kit contains this client, the CLI, and the agent plugin.
The hosted GPU service requires an account; its backend and GPU infrastructure
are not included in this repository.
