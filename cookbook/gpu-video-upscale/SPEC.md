# gpu-video-upscale: video super-resolution demo — SPEC

An agent works inside a disposable sandbox on a real video-processing
engineering problem: run **Real-ESRGAN ×4 super-resolution** over a short
1080p public-domain clip so that the upscaled result beats plain bicubic
upscaling by a wide, measured PSNR margin on every sampled frame — and be
judged by a judge it cannot fool. The heavy step runs on a GPU slice lease;
the judge itself runs on CPU, so anyone can grade the artifact.

## Goal

- Artifact: one self-contained Python file (`upscale.py`) that loads a pinned
  Real-ESRGAN ×4plus checkpoint into a minimal pure-torch RRDBNet (no
  `basicsr` build, no extra services) and upscales a video.
- Judge: `judge/grade.sh <artifact>` with numeric, deterministic pass rules,
  running on CPU, that measures PSNR/SSIM of the artifact's output against
  the *original* frames and compares it against a bicubic baseline the judge
  computes itself.
- Self-test: `judge/selftest.sh` proves the judge fails known-bad
  artifacts (kill rate ≥ 90 %), including the exact cheats named in the
  brief.
- One-command run: `run.py` creates a GPU slice lease, uploads the pinned
  weights clip and judge, runs the real GPU inference, downloads the
  results, then destroys the lease and confirms it is gone.

## Non-goals

- Training, fine-tuning or retraining anything. Weights are frozen and
  pinned by sha256.
- Audio. The clip is silent (the source has no audio track).
- Higher scale factors than ×4, or scales other than 4 in the artifact's
  public API.
- Beating a published Real-ESRGAN benchmark number. The judge compares the
  artifact against a bicubic baseline it computes itself, not against a
  paper.
- Any product or company name other than the agent-next sandbox endpoints
  this demo runs on.
- Temporal super-resolution (frame interpolation), denoising models, or
  face restoration — single-image ×4 per frame, left to right, top to
  bottom, no cross-frame state.

## The artifact contract

`upscale.py` must define, with no third-party imports beyond `torch`
(and `numpy`), this API:

| name | what |
|---|---|
| `MODEL_SHA256` | sha256 hex of the pinned checkpoint this artifact expects (`4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1`) |
| `SCALE` | `4` |
| `build_model() -> torch.nn.Module` | returns a RRDBNet in eval mode with the Real-ESRGAN ×4plus architecture, parameters loaded from the checkpoint |
| `upscale_frames(model, frames: torch.Tensor) -> torch.Tensor` | takes `(N, 3, H, W)` float32 in **[0, 1]** on any device, returns `(N, 3, H×4, W×4)` float32 in **[0, 1]** on the same device; must not modify `frames` |

Rules the judge enforces:

- `upscale_frames` must not modify its input tensor (checked bitwise).
- The model must be used: the output must not be a pure interpolation of
  the input. The judge checks this directly by comparing the artifact's
  output against bicubic, nearest, and a "model swapped for identity"
  control.
- The artifact must not read, write, or shell out to anything: no file
  access, no network, no subprocess. Only `build_model`,
  `upscale_frames`, and module-level constants are used by the judge.
- Text must not contain references to other video-super-resolution model
  implementations, and must not import `basicsr` (the point of the
  minimal pure-torch reimplementation).
- At most 256 KiB, byte-compiles.

## Judge gates (numeric pass rules)

`judge/grade.sh <artifact> [--seed N] [--json out.json] [--clip PATH]
[--frames N] [--tile N]` exits 0 only if every gate below passes. `--seed`
(default 0) selects which frames are sampled, deterministically. Grading
runs the artifact from a copy in a fresh temp dir; sha256 checksums of
`judge/` before and after must match, else the run fails.

The judge works on a **lowered** problem: it takes the original clip
`, downscales it ×4 itself (deterministically, with a documented filter),
upgrades it back with the artifact, and compares against the original. This
is the classic super-resolution ground-truth protocol and it needs no
ground-truth upscaled data shipped in the repo.

1. **structure** — file ≤ 256 KiB; byte-compiles; defines callable
   `build_model` and `upscale_frames`, constants `MODEL_SHA256` (the pinned
   hash) and `SCALE == 4`; imports only `torch`/`numpy`/stdlib; text
   contains no `basicsr`, no `os.`, `subprocess`, `socket`, `urllib`,
   `requests`, `pathlib`, or `open(` calls; no other SR product names.

2. **weights-load** — `build_model()` runs, returns an `nn.Module` in eval
   mode, whose parameter sha256 (over sorted name→sha256 of every tensor)
   equals the sha256 of the pinned checkpoint's `params_ema` tensors. This
   proves the artifact really loaded the pinned weights, not a random init.
   The checkpoint path comes from `--weights` (default: the demo's
   `data/weights/RealESRGAN_x4plus.pth`), and its own sha256 is verified
   against `MODEL_SHA256` before loading.

3. **contract** — on a (2, 3, 48, 64) synthetic frame pair with a fixed
   seed: output shape is exactly `(2, 3, 192, 256)`, dtype float32, all
   finite, all values within `[-0.001, 1.001]` (the model may overshoot
   slightly; the judge clips before metric computation and says so), the
   input tensor is bit-identical after the call, and the output is *not*
   reproducible by bicubic or nearest upscaling of the input
   (`max|out − bicubic| > 1e-3`, i.e. the model genuinely ran).

4. **correctness (the headline gate)** — on the sampled frames of the real
   clip (see Sampling below):
   - `psnr(out, orig)` computed in float32 on the **[0, 1]** scale,
     8-bit-quantised per channel (`round(x * 255) / 255`) on both sides
     before the error, PSNR from the mean over the frame;
   - **`psnr_model − psnr_bicubic ≥ 1.0 dB` on every sampled frame** — no
     exception, no average-out;
   - `ssim(out, orig) ≥ ssim_bicubic + 0.005` on every sampled frame
     (SSIM as a second, independent opinion: a model that only matches
     PSNR by boosting contrast can still fail SSIM);
   - frame **count** preserved (the artifact returns exactly as many frames
     as it was given) and **resolution** exactly 4× the input's, on every
     sampled frame.

   The judge computes its own bicubic baseline with
   `torch.nn.functional.interpolate(..., mode='bicubic', antialias=True)`
   from the same downscaled input — the same code path the judge uses for
   the downscale, so the baseline is exact and reproducible.

5. **no-cheat** — three specific, individually failing checks:
   - the artifact's output must differ from the *input* by more than
     noise (a pass-through, i.e. "return the low-res frames as the
     high-res ones", fails: size mismatch);
   - the artifact's output must not equal any single resample filter's
     result (bicubic/nearest/bilinear/area all checked);
   - the artifact must not duplicate frames across the temporal axis to
     fake frame count: the judge checks that consecutive distinct input
     frames produce distinct outputs (`max|out[i] − out[j]| > 1e-3` for
     i≠j, on pairs of sampled frames), so a constant or frame-0-broadcast
     output fails.

### Sampling and reproducibility

- The clip is `data/clip/original.mp4` (5 s, 1920×1080, 30 fps, 150
  frames, H.264, no audio), taken from a cite-able public-domain source
  and committed (about 3 MB; under the 1 MB-per-mesh/size guidance this is
  a video, not a mesh, and it is the demo's input data — see
  Deviations).
- Frames sampled: with `--seed S`, sample `--frames N` (default 3) frames
  at deterministic indices `(k * stride + S) % total_frames` for k in
  range(N), so different seeds sample different frames and the default
  always samples the same three.
- The judge's downscale is exactly: `F.interpolate(frame, scale_factor=0.25,
  mode='bicubic', antialias=True)` — the inverse direction of the baseline
  upscale. This is the judge's own ground truth protocol, computed fresh
  every run, so nothing is cached or user-supplied.
- Decoding uses ffmpeg (pinned, sha256-checked in setup.sh) into raw RGB
  in a temp dir; the judge never writes into the demo directory.

### Metric definitions (so two runs agree)

- PSNR uses MSE over all channels of one frame: `10·log10(1/MSE)`, with
  MSE on the 8-bit-quantised [0,1] frames. A frame identical to the
  original gives infinity; the judge reports `null` and treats it as the
  best possible.
- SSIM uses a standard 11×11 Gaussian window (σ=1.5), C1=(0.01·L)²,
  C2=(0.03·L)² with L=1.0, computed per channel and averaged, on the
  quantised frames, with `valid`-style padding at the borders.
- All metric computation is float32, single-threaded (`torch.set_num_threads(1)`),
  so `--json` output is byte-identical between two runs with the same seed
  except the `timing` key.

## Acceptance oracle

The judge never trusts the artifact's own idea of correct. Correctness is
decided by three independent oracles:

1. **A reference tool**: the judge's own bicubic upscale of the same
   downscaled frame, computed with torch's `interpolate` — a tool the
   artifact does not control.
2. **A spec mask on an analytic quantity**: the ×4 scale is checked
   numerically against the input geometry (out height == 4 × in height),
   and the frame count against the input count.
3. **A convergence-style check on the metric gap**: the artifact must beat
   the reference by ≥ 1.0 dB on *every* sampled frame. A result that is
   merely "not worse on average" fails; the per-frame rule is the tight
   mask.

Plus the structural oracles in gates 2 and 3 (parameter-hash identity
proving the pinned weights were loaded, and the not-a-resample-filter
check proving a neural network produced the output).

## Known-bad examples (self-test)

`judge/mutants.py` derives ≥ 5 known-bad artifacts from the known-good one
by scripted single edits. The cheats named in the brief are all covered:

| mutant | edit | gate that must fail |
|---|---|---|
| `bicubic_as_model` | `upscale_frames` returns `F.interpolate(frames, scale_factor=4, mode='bicubic', antialias=True)` | correctness (PSNR gap 0, `not_a_filter` in `no-cheat`) |
| `drop_frames` | return every other frame | correctness / contract (frame count) |
| `wrong_scale` | upscale ×2 instead of ×4 | contract (resolution) |
| `channel_swap` | return `out[:, [2,1,0], ...]` | correctness (PSNR/SSIM) |
| `frame_reorder` | reverse the temporal axis | correctness + `no-cheat` temporal check |
| `identity_model` | `build_model` returns an untrained model (skip `load_state_dict`) | weights-load |
| `pass_through` | return `frames.repeat_interleave(4, dim=2).repeat_interleave(4, dim=3)` (nearest) | `no-cheat` (`not_a_filter`) |
| `mute_model` | zero the RRDB body so the network is a no-op | correctness (falls back to a sharp-ish bicubic, PSNR gap collapses) |

`judge/selftest.sh` grades the known-good example (must pass) and every
mutant (each must fail ≥ 1 gate), checks determinism (two grades of the
good artifact give byte-identical verdicts except `timing`), checks
`judge/` checksums are unchanged, and prints the kill rate. It exits
non-zero unless good passes, every mutant is killed, and the kill rate is
≥ 90 %.

## Toolchain (pinned, sha256-checked)

`judge/setup.sh` installs into `$HOME/.venvs/gpu-video-upscale/` exactly
what the judge needs and nothing else. Tried in this order, as the brief
requires:

1. **Official release tarballs** — the Real-ESRGAN weights come from the
   upstream project's GitHub release (`v0.1.0`, the release that still
   hosts `RealESRGAN_x4plus.pth`), sha256-verified into
   `data/weights/`. No code tarball is needed: the artifact ships its own
   minimal pure-torch RRDBNet.
2. **pip wheels with exact versions** — `torch==2.14.1+cpu` (one pinned
   wheel URL + sha256 per supported CPython, from the PyTorch CPU index)
   and `numpy==2.4.3`, with the full transitive closure pinned, installed
   with `pip --require-hashes`. Generated by `judge/genlock.py`.
3. **Debian packages** — `ffmpeg` is needed only to decode the clip. If
   `ffmpeg` is already on `PATH` (this builder sandbox has
   `5.1.9-0+deb12u1`), setup.sh records its version and moves on; if it is
   missing, setup.sh runs `apt-get update` **and checks that it actually
   fetched lists** before `apt-get install -y ffmpeg` (this image's apt
   lists may be empty), and verifies the installed version.

`judge/VERSIONS.txt` records what `setup.sh` actually installed, with the
`--version` output of each tool. Every pinned release predates 2026-10-01
(the demo was built on 2026-10-15, so nothing from the last two weeks).
`setup.sh` is idempotent and refuses unsupported platforms (x86-64 Linux,
CPython 3.10–3.13).

The judge needs no CUDA. The GPU is used by the artifact's own heavy
inference (the lead's GPU run below), not by grading: the judge always runs
on CPU, which is what makes it runnable by everyone.

## GPU path (the lead's run)

The heavy step — running the model over 150 frames of 1080p — runs on a
GPU slice lease created over the REST API, exactly the pattern in
`cookbook/small-gpu/run.py` and `cookbook/gpu-kernel/run.py`:

```
POST /sandboxes {"accel":{"vram_gb":8,"reserve":"exec"}}      # SBX_API_KEY
POST /sandboxes/{id}/files/...                                  # upload: clip, weights, judge, artifact
POST /sandboxes/{id}/exec {"code": <python>, "timeout_s": N}    # run inference + grade, CPU judge
GET  /sandboxes/{id}/files/...                                  # download: results + comparison mp4
DELETE /sandboxes/{id}
GET /sandboxes/{id} → 404 / phase dead                         # confirmed in a finally block
```

The lease has no internet, so everything it needs (pinned weights, clip,
judge scripts, the artifact) is uploaded from this CPU sandbox with the
file API. `run.py` packs them as a base64 tar.gz inside the exec code
where the HTTP file API is unavailable, always deletes the lease in a
`finally` block, and never deletes a lease whose id it did not create.

Measured GPU numbers to be pasted into `RECEIPT.md` by whoever runs it:
wall time, VRAM used (`torch.cuda.max_memory_allocated`), and per-frame
and end-to-end throughput (frames/s).

## Reproducibility

Grading is deterministic given `--seed`: two runs produce byte-identical
verdict JSON except the `timing` key — enforced by `selftest.sh`. The
metric definitions are pinned above so two machines agree to the last
decimal of the *reported* numbers except where floating-point summation
order differs (PSNR is reported to 2 decimals, SSIM to 4).
`RECEIPT.md` carries real pasted output of setup, selftest and grade with
exit codes, kill rate, key numbers and wall time of each, plus a
Deviations section.
