# GPU batch image generation: 16 pinned prompts, a judge the generator cannot fool

An agent works on a real batch-generation engineering problem inside a
disposable sandbox: render a fixed 16-prompt text-to-image batch with
pinned `stabilityai/sd-turbo` weights on a short-lived GPU slice, and hand
the batch to a CPU-side judge that decides whether the images actually
match the prompts. The judge never accepts "the pipeline ran": every image
is scored against an independent vision-language model (OpenAI **CLIP
ViT-B-32**, served by `open_clip` — an encoder the generator's own text
encoder knows nothing about), checked for structural validity (a decodable
512×512 RGB bitmap, not a flat field), cross-checked for duplicates, and
re-render determinism is verified pixel-wise. A batch whose images are
swapped, blanked, resized, duplicated or stale dies at a named gate.

A sandbox helps because this is exactly the workload you do not want on
your own machine: a GPU lease with a hard VRAM slice, multi-gigabyte model
weights you would rather not keep, and generator code you should not run
locally. The judge runs anywhere — it is CPU-only, pinned and
deterministic — so the artifact and its verdict are separable: render on
the GPU lease, grade on any CPU box.

## One-command run

From this repository's root, with Python 3.10+ and the `sbx` CLI
(`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and `SBX_API_KEY` exported:

```bash
python3 cookbook/gpu-batch-image-gen/run.py                    # judge lane, CPU sandbox
python3 cookbook/gpu-batch-image-gen/run.py --ref sbx/my-branch # other repository ref
python3 cookbook/gpu-batch-image-gen/run.py --render           # GPU lane: render the batch
python3 cookbook/gpu-batch-image-gen/run.py --grade render-out/batch --ref sbx/my-branch
```

The default (judge) lane creates a disposable CPU sandbox, clones this
repository at `--ref` inside it, installs the pinned judge toolchain
(`judge/setup.sh`), proves the judge can fail (`judge/selftest.sh`), grades
the known-good batch and prints the verdict JSON. The sandbox is always
killed afterwards and its absence is confirmed against `sbx list`. Measured
wall time per step in a fresh sandbox is in RECEIPT.md.

`--render` is the GPU lane: it sha256-verifies the pinned sd-turbo weights
on this machine, creates a 6 GiB VRAM lease over the REST API, uploads the
weights in ≤400 MiB chunks, renders the pinned batch on the lease,
downloads the artifact, and deletes the lease — confirming the deletion.
Every lease id is recorded in the report JSON (`--report`).

## Ask your agent

With the sandbox plugin installed, paste this prompt. The agent renders
the batch on a GPU lease and iterates against the judge until it passes —
that loop is the demo:

> Create a fresh sandbox. Inside it, clone
> https://github.com/agent-next/sandbox at ref `main`, then read
> `cookbook/gpu-batch-image-gen/SPEC.md` carefully: you are to produce one
> *batch* artifact — 16 rendered PNGs, 2 re-renders, a `meta.json` manifest
> and a 4×4 contact sheet — by rendering the 16 pinned prompts at the
> pinned seeds with `stabilityai/sd-turbo` (fp16, 1 step, guidance 0.0,
> 512×512) on a GPU lease. The prompts, seeds and generator settings are
> part of the spec and are not yours to choose. First run
> `cookbook/gpu-batch-image-gen/judge/setup.sh` to install the judge, then
> produce the batch, then iterate: `bash
> cookbook/gpu-batch-image-gen/judge/grade.sh /path/to/your/batch --json
> /tmp/v.json` and read the verdict JSON until every gate passes
> (structure, validity, clip_retrieval, determinism, distinctness). The
> judge's self-test shows what it rejects — run `judge/selftest.sh` once to
> see 8 broken batches die. When every gate passes, report the verdict JSON
> (retrieval accuracy, per-image margins, closest-pair PSNR, wall times),
> then delete every GPU lease you created and confirm it is gone. If you
> cannot get a gate to pass, say exactly which gate and what you tried, and
> stop.

## What the judge checks (short form)

| gate | rule |
|---|---|
| structure | `meta.json` parses and every pinned field matches; 16 + 2 PNGs and the 2048×2048 contact sheet exist |
| validity | every PNG decodes with Pillow, is exactly 512×512 RGB, grayscale std ≥ 3.0 (a flat/corrupt/resized image dies here) |
| clip_retrieval | CLIP ViT-B-32 cosine similarity: image *i*'s own prompt is the argmax over all 16 → **≥ 14/16** |
| determinism | for i ∈ {3, 11}: sha256(images/img_i) == sha256(rerenders/img_i) **or** PSNR > 40 dB |
| distinctness | all 16 sha256 distinct and every pair PSNR < 40 dB (no duplicates or near-identical renders) |

The artifact is graded from a read-only copy and sha256 checksums of
`judge/` are compared before and after — the artifact cannot tamper with
its own judge. `judge/selftest.sh` grades the known-good batch and 8
scripted single-edit mutants (prompt-swap, blank image, wrong resolution,
wrong seed, duplicate image, stale re-render, truncated PNG, resized
contact sheet), and checks that two grades are byte-identical except the
`timing` key; kill rate 8/8 = 100 %.

## Try the judge locally (CPU only)

Run all three from this repository's root:

```bash
bash cookbook/gpu-batch-image-gen/judge/setup.sh      # pinned venv in ~/.venvs/gpu-image-gen
bash cookbook/gpu-batch-image-gen/judge/selftest.sh   # good passes, 8/8 mutants killed
bash cookbook/gpu-batch-image-gen/judge/grade.sh cookbook/gpu-batch-image-gen/examples/good/batch
```

## The pinned batch

Prompts and seeds are part of the spec (index i, seed 1000 + 7·i): a red
sports car at sunset, a bowl of ramen, an astronaut on the moon, a snowy
cabin, a ship in a storm, sunflowers, sushi, a steam locomotive, a glass
skyscraper, a giraffe, a lighthouse, a hot-air balloon, a chess board, a
record player, a red apple, a stack of old books. The full table is in
SPEC.md and duplicated verbatim in `judge/_grade.py` — the judge does not
import the artifact's code.

## Media

![CLIP retrieval margins with the judge's 14/16 pass line](media/result.png)

[Watch the agent loop](media/demo.mp4) · [Agent loop and kill rate](media/loop.png).
Regenerate with `bash cookbook/gpu-batch-image-gen/media/make_media.sh`.

## Limits, stated plainly

- The batch is exactly 16 prompts at 512×512. No arbitrary resolutions,
  batch sizes, animation, img2img, ControlNet or LoRA.
- The judge scores *retrieval*, not aesthetics: image *i* must match its
  own prompt best among the 16. It is not an image-quality gate.
- Throughput and VRAM are measured and reported in RECEIPT.md, never gated
  (they vary by GPU class).
- The GPU lane needs a key with GPU access and a free seat; a 429/503 from
  the lease API is a capacity condition, not a demo failure.

## Third-party weights and licences

- `stabilityai/sd-turbo` (diffusers fp16 safetensors), CreativeML Open
  RAIL++-M licence — <https://huggingface.co/stabilityai/sd-turbo>. The
  licence text ships as `weights-licence.md` and is downloaded and
  sha256-checked by the GPU lane.
- OpenAI CLIP ViT-B-32 via `open_clip` ("openai" pretrained), MIT licence —
  <https://github.com/mlfoundations/open_clip>. Pinned download URL and
  sha256 are in `judge/setup.sh`.
