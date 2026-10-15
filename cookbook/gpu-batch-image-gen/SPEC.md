# gpu-batch-image-gen: batch text-to-image on a GPU slice — SPEC

An agent works inside a disposable sandbox on a real batch-generation problem:
render a fixed 16-prompt text-to-image batch with pinned Stable Diffusion
sd-turbo weights on a short-lived GPU slice, and hand the batch to an
unfoolable CPU-side judge. The judge never accepts "it ran": every image is
scored against an independent vision-language model (OpenAI CLIP ViT-B-32
served by open_clip), checked for structural validity, cross-checked for
duplicates, and re-render determinism is verified pixel-wise.

## Goal

- Artifact: one directory (the *batch*) with 16 rendered PNGs, 2 re-renders,
  a `meta.json` manifest and a contact sheet — produced by `gen.py`-style code
  on a GPU lease, graded by `judge/grade.sh` on any CPU machine.
- Judge: `judge/grade.sh <artifact> [--seed N] [--json out.json]` — five gates,
  numeric deterministic pass rules, exit 0 only if all pass.
- Self-test: `judge/selftest.sh` proves the judge kills 8 scripted single-edit
  mutants and that grading is deterministic.

## Non-goals

- Prompt engineering, image quality beyond "matches its own prompt best":
  CLIP retrieval decides, no aesthetic score.
- Arbitrary resolutions, batch sizes, animation/video, img2img, ControlNet,
  LoRA — exactly 16 fixed prompts at 512×512.
- Speed targets: throughput and VRAM are measured and reported, never gated.
- Re-implementation of the CLIP scorer: the judge uses pinned open_clip
  weights as its reference oracle.

## The pinned batch

Prompts and seeds are part of the spec (index i = 0..15, seed = 1000 + 7·i):

| i | prompt | seed |
|---|--------|------|
| 0 | a red sports car on a mountain road at sunset | 1000 |
| 1 | a bowl of ramen soup with chopsticks on a wooden table | 1007 |
| 2 | an astronaut standing on the moon with earth in the sky | 1014 |
| 3 | a cozy wooden cabin in a snowy pine forest at night | 1021 |
| 4 | a sailing ship on a stormy sea with lightning in the sky | 1028 |
| 5 | a field of sunflowers under a blue summer sky | 1035 |
| 6 | a plate of sushi on a black stone counter | 1042 |
| 7 | a steam locomotive crossing a stone bridge in autumn | 1049 |
| 8 | a modern glass skyscraper against a clear morning sky | 1056 |
| 9 | a giraffe on the african savanna beside an acacia tree | 1063 |
| 10 | a lighthouse on a rocky cliff in a thunderstorm | 1070 |
| 11 | a hot air balloon floating over green hills at sunrise | 1077 |
| 12 | a close-up of a wooden chess board with scattered pieces | 1084 |
| 13 | a vintage record player with vinyl records on a desk | 1091 |
| 14 | a red apple on a white plate on a kitchen table | 1098 |
| 15 | a stack of old books with reading glasses on a library table | 1105 |

Generator settings (fixed): `stabilityai/sd-turbo` fp16 diffusers weights
(safetensors, sha256-pinned, uploaded to the lease — the lease has no
internet), 1 inference step, guidance_scale 0.0, 512×512, one CUDA generator
per prompt seeded with the table above. Images whose two table neighbours are
re-rendered in a second exec: i = 3 and i = 11.

## The artifact contract

```
<artifact>/
  meta.json           # model, dtype, steps, guidance, size, prompts[], seeds[], gpu, timings
  images/img_00.png   # .. img_15.png, index i matches the table above
  rerenders/img_03.png, rerenders/img_11.png   # second exec, same settings
  contact_sheet.png   # 4x4 grid of images/img_00..15 in order, no gaps: 2048x2048
```

`meta.json` required fields: `model` == "stabilityai/sd-turbo", `dtype` ==
"float16", `steps` == 1, `guidance_scale` == 0.0, `width` == 512,
`height` == 512, `prompts` == the 16 pinned prompts in order, `seeds` ==
[1000, 1007, ..., 1105]. Extra fields (timings, gpu name, throughput) are
reported but not gated.

## Judge gates (numeric pass rules)

`grade.sh <artifact> --seed N` (default 0; the seed only labels the verdict
— the batch itself is pinned) exits 0 only if all five gates pass. The
artifact is graded from a read-only copy; sha256 of `judge/` before and after
must match.

1. **structure** — the layout above exists: `meta.json` parses, every
   required field equals its pinned value; 16 + 2 PNGs and the 2048×2048
   contact sheet are present.
2. **validity** — every PNG loads with Pillow, is exactly 512×512, RGB mode,
   and non-blank: grayscale standard deviation ≥ 3.0 (0–255 scale). A flat,
   corrupt, or resized image fails here.
3. **clip_retrieval** — pinned OpenAI CLIP ViT-B-32 via open_clip: embed all
   16 prompts and all 16 images (batch, no_grad, deterministic, CPU);
   cosine-similarity matrix 16×16; image i passes when its own prompt is the
   argmax over all 16 prompts. Gate: **top-1 accuracy ≥ 14/16**. Per-image
   argmax and margin (own − best other) are reported.
4. **determinism** — for i in {3, 11}: sha256(images/img_i) ==
   sha256(rerenders/img_i) **or** PSNR(img_i, rerender_i) > 40.0 dB.
   Both indices must pass.
5. **distinctness** — all 16 images have distinct sha256 and every pair
   i < j has PSNR < 40.0 dB (no duplicated or near-identical renders).

## Acceptance oracle

Correct is decided by things the artifact cannot negotiate with: an external
reference model (OpenAI CLIP ViT-B-32, weights pinned by sha256, unrelated to
the generator's internal text encoder), Pillow's decoder (a valid image is a
decodable 512×512 RGB bitmap), pixel statistics (blank/duplicate detection),
and PSNR/sha256 arithmetic for determinism. "The pipeline ran" is never a
pass condition.

## Known-bad examples (self-test)

`judge/mutants.py` derives 8 known-bad batches from the known-good one by
scripted single edits: `swap_prompts` (4-cycle of image filenames between
prompts), `blank_image` (one image replaced by flat gray), `wrong_resolution`
(one image resized to 256×256), `wrong_seed` (meta.json seed + 1),
`duplicate_image` (one image copied over its neighbour), `stale_rerender`
(rerender replaced by another image), `corrupt_png` (truncated PNG),
`bad_contact_sheet` (contact sheet resized). `selftest.sh` grades the
known-good (must pass) and every mutant (each must fail ≥ 1 gate), checks
that two grades of the good batch are byte-identical except the `timing`
key, and exits non-zero unless the kill rate is ≥ 90 %.

## Toolchain (pinned, sha256-checked)

`judge/setup.sh` installs into `$HOME/.venvs/gpu-image-gen/`: torch 2.14.0+cpu,
torchvision 0.29.0+cpu, open_clip_torch 3.3.0 and its closure, Pillow — every
package pinned with sha256 through pip's `--require-hashes`
(`judge/requirements.lock`, per-CPython wheel URLs for torch/torchvision).
It then downloads the OpenAI CLIP ViT-B-32 open_clip checkpoint (pinned URL +
sha256) into `$HOME/.gpu-image-gen-cache/`. Every pinned release predates
2026-10-01. `judge/VERSIONS.txt` records what actually installed. Idempotent;
x86-64 Linux, CPython 3.10–3.13.

## Third-party weights and licences

- `stabilityai/sd-turbo` (diffusers fp16 safetensors), CreativeML Open
  RAIL++-M licence — https://huggingface.co/stabilityai/sd-turbo; the licence
  text ships as `weights-licence.md` and in README.
- OpenAI CLIP ViT-B-32 (`open_clip` "openai" pretrained), MIT licence —
  https://github.com/mlfoundations/open_clip; pinned download URL + sha256 in
  `judge/setup.sh`.

## GPU path

`run.py --render` (and the builder's production run) follow
`cookbook/small-gpu/run.py`'s lease pattern exactly: POST /sandboxes
`{"accel":{"vram_gb":6,"reserve":"exec"}}` → upload sha256-verified chunked
weights via PUT /sandboxes/{id}/files/… (512 MiB per-request cap → 400 MiB
chunks reassembled and sha256-checked on the lease) → exec the pinned
generation job → download `out/` results via GET /sandboxes/{id}/files/… →
DELETE the lease and confirm GET → 404/dead in a `finally` block. GPU wall
time, VRAM peak and throughput land in RECEIPT.md; every lease id and its
deletion confirmation is logged there.

## Reproducibility

Same seed twice → byte-identical verdict JSON except `timing`
(enforced by `selftest.sh`). Numbers in README/RECEIPT name the command and
seed that produced them. REPRODUCE.md carries an independent agent's
fresh-sandbox numbers before merge.
