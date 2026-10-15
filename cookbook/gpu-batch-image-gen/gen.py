#!/usr/bin/env python3
"""Render the pinned 16-prompt batch with sd-turbo on a GPU.

This is the generator the agent runs on the lease; it is *not* the judge.
It writes the artifact contract from SPEC.md:

    <out>/
      meta.json
      images/img_00.png .. img_15.png
      rerenders/img_03.png, rerenders/img_11.png
      contact_sheet.png

Determinism is the point: one CUDA generator per prompt, seeded from the
pinned table, 1 inference step, guidance_scale 0.0, fp16, 512x512. Running
this twice on the same GPU class must give byte-identical PNGs, which is
what the judge's determinism gate re-checks from the artifact alone.

    python3 gen.py --weights DIR --out DIR

The weights are the sha256-pinned stabilityai/sd-turbo fp16 diffusers files
(see judge/weights-manifest.json); this script only reads them locally — the
lease has no network.
"""

import argparse
import json
import os
import time

# The pinned batch. Index i -> prompt i, seed 1000 + 7*i. Duplicated in
# judge/_grade.py on purpose: the judge must not import the artifact's code.
PROMPTS = [
    "a red sports car on a mountain road at sunset",
    "a bowl of ramen soup with chopsticks on a wooden table",
    "an astronaut standing on the moon with earth in the sky",
    "a cozy wooden cabin in a snowy pine forest at night",
    "a sailing ship on a stormy sea with lightning in the sky",
    "a field of sunflowers under a blue summer sky",
    "a plate of sushi on a black stone counter",
    "a steam locomotive crossing a stone bridge in autumn",
    "a modern glass skyscraper against a clear morning sky",
    "a giraffe on the african savanna beside an acacia tree",
    "a lighthouse on a rocky cliff in a thunderstorm",
    "a hot air balloon floating over green hills at sunrise",
    "a close-up of a wooden chess board with scattered pieces",
    "a vintage record player with vinyl records on a desk",
    "a red apple on a white plate on a kitchen table",
    "a stack of old books with reading glasses on a library table",
]
SEEDS = [1000 + 7 * i for i in range(16)]
RERENDER_IDX = (3, 11)

MODEL = "stabilityai/sd-turbo"
STEPS = 1
GUIDANCE = 0.0
WIDTH = HEIGHT = 512


def render(pipe, torch, prompt, seed, generator_device):
    gen = torch.Generator(generator_device).manual_seed(seed)
    out = pipe(prompt, num_inference_steps=STEPS, guidance_scale=GUIDANCE,
               width=WIDTH, height=HEIGHT, generator=gen)
    return out.images[0]


def contact_sheet(images, Image):
    """4x4 grid of the 16 images in order, no gaps, 2048x2048."""
    sheet = Image.new("RGB", (WIDTH * 4, HEIGHT * 4))
    for i, im in enumerate(images):
        sheet.paste(im, ((i % 4) * WIDTH, (i // 4) * HEIGHT))
    return sheet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True,
                    help="directory with the pinned sd-turbo diffusers files")
    ap.add_argument("--out", required=True, help="artifact directory to write")
    args = ap.parse_args()

    import torch
    from diffusers import StableDiffusionPipeline
    from PIL import Image

    if not torch.cuda.is_available():
        raise SystemExit("gen.py: no CUDA device on this lease")
    device = "cuda"
    timings = {}

    t0 = time.monotonic()
    pipe = StableDiffusionPipeline.from_pretrained(
        args.weights, torch_dtype=torch.float16, local_files_only=True,
        safety_checker=None, requires_safety_checker=False)
    pipe = pipe.to(device)
    pipe.set_progress_bar_config(disable=True)
    # 1 step, guidance 0.0: the scheduler must not add noise the seed table
    # does not account for.
    pipe.scheduler.set_timesteps(STEPS, device=device)
    timings["load_s"] = round(time.monotonic() - t0, 2)

    imgdir = os.path.join(args.out, "images")
    rrdir = os.path.join(args.out, "rerenders")
    os.makedirs(imgdir, exist_ok=True)
    os.makedirs(rrdir, exist_ok=True)

    images = []
    t0 = time.monotonic()
    torch.cuda.reset_peak_memory_stats()
    for i, prompt in enumerate(PROMPTS):
        im = render(pipe, torch, prompt, SEEDS[i], device)
        images.append(im)
        im.save(os.path.join(imgdir, f"img_{i:02d}.png"))
    timings["render_s"] = round(time.monotonic() - t0, 2)
    timings["peak_vram_mib"] = round(torch.cuda.max_memory_allocated() / 2 ** 20, 1)

    t0 = time.monotonic()
    for i in RERENDER_IDX:
        im = render(pipe, torch, PROMPTS[i], SEEDS[i], device)
        im.save(os.path.join(rrdir, f"img_{i:02d}.png"))
    timings["rerender_s"] = round(time.monotonic() - t0, 2)

    contact_sheet(images, Image).save(os.path.join(args.out, "contact_sheet.png"))

    meta = {
        "model": MODEL,
        "dtype": "float16",
        "steps": STEPS,
        "guidance_scale": GUIDANCE,
        "width": WIDTH,
        "height": HEIGHT,
        "prompts": PROMPTS,
        "seeds": SEEDS,
        "gpu": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "timings": timings,
        "throughput_images_per_s": round(16 / timings["render_s"], 3),
    }
    with open(os.path.join(args.out, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    print(json.dumps({"rendered": 16, "rerendered": list(RERENDER_IDX),
                      "gpu": meta["gpu"], "timings": timings}, indent=2))


if __name__ == "__main__":
    main()
