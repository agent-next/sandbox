#!/usr/bin/env python3
"""Grade a rendered batch (the artifact directory). See SPEC.md for gates.

    judge/_grade.py <artifact_dir> [--seed N] [--json out.json] [--judge-dir D]

Exits 0 only if all five gates pass; prints one JSON verdict on stdout. The
artifact is graded read-only from a copy; sha256 of judge/ before and after
must match. Determinism: same inputs twice give byte-identical JSON except
the `timing` key (single-threaded torch, fixed thread counts).
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time

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
RETRIEVAL_MIN = 14          # of 16
PSNR_MIN_DETERMINISM = 40.0  # dB, same-seed re-renders
PSNR_MAX_DISTINCT = 40.0     # dB, different images must stay below this
BLANK_STD_MIN = 3.0          # grayscale std (0-255 scale)
CLIP_TAG = "ViT-B-32"
CLIP_PRETRAINED = "openai"

META_REQUIRED = {
    "model": "stabilityai/sd-turbo",
    "dtype": "float16",
    "steps": 1,
    "guidance_scale": 0.0,
    "width": 512,
    "height": 512,
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_sha(root):
    entries = []
    for dirpath, _dirnames, filenames in sorted(os.walk(root)):
        for name in sorted(filenames):
            p = os.path.join(dirpath, name)
            entries.append((os.path.relpath(p, root), sha256_file(p)))
    return sorted(entries)


def psnr(a, b):
    """PSNR in dB between two same-shaped uint8 arrays (any channel count)."""
    diff = a.astype("float64") - b.astype("float64")
    mse = float((diff * diff).mean())
    if mse == 0.0:
        return float("inf")
    return 10.0 * math.log10(255.0 * 255.0 / mse)


def gate_structure(art):
    problems = []
    meta_path = os.path.join(art, "meta.json")
    meta = None
    if not os.path.isfile(meta_path):
        problems.append("meta.json missing")
    else:
        try:
            with open(meta_path) as fh:
                meta = json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.append(f"meta.json not valid JSON: {exc}")
            meta = None
    if isinstance(meta, dict):
        for key, want in META_REQUIRED.items():
            got = meta.get(key)
            if got != want:
                problems.append(f"meta.{key}={got!r}, want {want!r}")
        if meta.get("prompts") != PROMPTS:
            problems.append("meta.prompts does not match the pinned batch")
        if meta.get("seeds") != SEEDS:
            problems.append("meta.seeds does not match the pinned seeds")
    for i in range(16):
        p = os.path.join(art, f"images/img_{i:02d}.png")
        if not os.path.isfile(p):
            problems.append(f"images/img_{i:02d}.png missing")
    for i in RERENDER_IDX:
        p = os.path.join(art, f"rerenders/img_{i:02d}.png")
        if not os.path.isfile(p):
            problems.append(f"rerenders/img_{i:02d}.png missing")
    cs = os.path.join(art, "contact_sheet.png")
    if not os.path.isfile(cs):
        problems.append("contact_sheet.png missing")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--judge-dir", default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()

    t0 = time.monotonic()
    verdict = {
        "artifact": os.path.basename(os.path.normpath(args.artifact)),
        "seed": args.seed,
        "gates": {},
        "timing": {},
    }

    judge_before = dir_sha(args.judge_dir)
    art = os.path.abspath(args.artifact)

    import torch
    torch.set_num_threads(1)
    torch.set_grad_enabled(False)
    from PIL import Image
    import numpy as np

    # ---- gate 1: structure -------------------------------------------------
    problems = gate_structure(art)
    verdict["gates"]["structure"] = {
        "pass": not problems,
        "problems": problems,
    }

    # ---- gate 2: validity (every PNG decodes, 512x512, RGB, non-blank) -----
    problems = []
    image_arrays = {}
    image_hashes = {}
    names = [f"images/img_{i:02d}.png" for i in range(16)] + \
        [f"rerenders/img_{i:02d}.png" for i in RERENDER_IDX] + ["contact_sheet.png"]
    for name in names:
        p = os.path.join(art, name)
        if not os.path.isfile(p):
            continue                      # gate 1 already reported it
        try:
            with Image.open(p) as im:
                im.load()
                mode, size = im.mode, im.size
                gray = np.asarray(im.convert("L"), dtype=np.float64)
                rgb = im.convert("RGB") if name != "contact_sheet.png" else None
        except Exception as exc:
            problems.append(f"{name}: not a decodable PNG ({exc.__class__.__name__}: {exc})")
            continue
        if name != "contact_sheet.png":
            if mode != "RGB":
                problems.append(f"{name}: mode {mode}, want RGB")
            if size != (512, 512):
                problems.append(f"{name}: size {size[0]}x{size[1]}, want 512x512")
            std = float(gray.std())
            if std < BLANK_STD_MIN:
                problems.append(f"{name}: blank/flat image (gray std {std:.2f} < {BLANK_STD_MIN})")
            image_arrays[name] = np.asarray(rgb, dtype=np.uint8)
            image_hashes[name] = sha256_file(p)
        else:
            if size != (2048, 2048):
                problems.append(f"{name}: size {size[0]}x{size[1]}, want 2048x2048")
    verdict["gates"]["validity"] = {
        "pass": not problems,
        "problems": problems,
    }

    can_score = all(f"images/img_{i:02d}.png" in image_arrays for i in range(16))

    # ---- gate 3: CLIP retrieval -------------------------------------------
    problems = []
    retrieval = {"accuracy": None, "per_image": None}
    if can_score:
        import open_clip
        ckpt = os.path.join(os.environ.get("GPU_IMAGE_GEN_WEIGHTS",
                                           os.path.expanduser("~/.gpu-image-gen-weights")),
                            "open_clip_model.safetensors")
        model, _, preprocess = open_clip.create_model_and_transforms(
            CLIP_TAG, pretrained=ckpt)
        model.eval()
        tokenizer = open_clip.get_tokenizer(CLIP_TAG)
        with torch.no_grad():
            text = tokenizer(PROMPTS)
            text_feats = model.encode_text(text)
            text_feats = text_feats / text_feats.norm(dim=-1, keepdim=True)
            img_t = torch.stack([preprocess(Image.fromarray(image_arrays[f"images/img_{i:02d}.png"]))
                                 for i in range(16)])
            img_feats = model.encode_image(img_t)
            img_feats = img_feats / img_feats.norm(dim=-1, keepdim=True)
            sim = (img_feats @ text_feats.T).float().cpu().numpy()
        per_image = []
        correct = 0
        for i in range(16):
            row = sim[i]
            own = float(row[i])
            others = [float(x) for j, x in enumerate(row) if j != i]
            best_other = max(others)
            best_other_idx = int(row.argmax()) if int(row.argmax()) != i else \
                max((j for j in range(16) if j != i), key=lambda j: row[j])
            ok = own > max(others)
            correct += int(ok)
            per_image.append({
                "i": i, "ok": bool(ok), "own": round(own, 4),
                "best_other": round(best_other, 4),
                "margin": round(own - best_other, 4),
                "argmax": best_other_idx,
            })
        retrieval = {"accuracy": correct, "min_required": RETRIEVAL_MIN,
                     "per_image": per_image}
        if correct < RETRIEVAL_MIN:
            wrong = [e["i"] for e in per_image if not e["ok"]]
            problems.append(f"top-1 retrieval accuracy {correct}/16 < {RETRIEVAL_MIN}; wrong: {wrong}")
    else:
        problems.append("cannot run: 512x512 RGB images missing (see gate 1/2)")
    verdict["gates"]["clip_retrieval"] = {
        "pass": not problems, "problems": problems, **{k: v for k, v in retrieval.items() if k != "per_image"},
    }
    if retrieval["per_image"] is not None:
        verdict["gates"]["clip_retrieval"]["per_image"] = retrieval["per_image"]

    # ---- gate 4: determinism (re-renders match originals) -------------------
    problems = []
    det = []
    if can_score:
        for i in RERENDER_IDX:
            name = f"rerenders/img_{i:02d}.png"
            p = os.path.join(art, name)
            if name not in image_arrays or f"images/img_{i:02d}.png" not in image_arrays:
                continue
            h_img = image_hashes[f"images/img_{i:02d}.png"]
            h_rr = sha256_file(p)
            if h_img == h_rr:
                det.append({"i": i, "identical": True, "psnr_db": None})
                continue
            a = image_arrays[f"images/img_{i:02d}.png"]
            b = image_arrays[name]
            value = psnr(a, b)
            ok = value > PSNR_MIN_DETERMINISM
            det.append({"i": i, "identical": False, "psnr_db": round(value, 2), "ok": bool(ok)})
            if not ok:
                problems.append(f"img_{i:02d}: re-render PSNR {value:.2f} dB <= {PSNR_MIN_DETERMINISM} dB and hashes differ")
    else:
        problems.append("cannot run: images missing")
    verdict["gates"]["determinism"] = {"pass": not problems, "problems": problems, "pairs": det}

    # ---- gate 5: distinctness ----------------------------------------------
    problems = []
    dups = []
    if can_score:
        seen = {}
        for i in range(16):
            h = image_hashes[f"images/img_{i:02d}.png"]
            if h in seen:
                dups.append({"i": seen[h], "j": i, "kind": "identical sha256"})
            seen[h] = i
        if not dups:
            worst = None
            for i in range(16):
                for j in range(i + 1, 16):
                    a = image_arrays[f"images/img_{i:02d}.png"]
                    b = image_arrays[f"images/img_{j:02d}.png"]
                    value = psnr(a, b)
                    if worst is None or value > worst[0]:
                        worst = (value, i, j)
                    if value > PSNR_MAX_DISTINCT or math.isinf(value):
                        dups.append({"i": i, "j": j, "kind": f"PSNR {value:.2f} dB > {PSNR_MAX_DISTINCT}"})
            verdict["gates"]["distinctness"] = {
                "pass": not dups, "problems": ([f"{d['i']}/{d['j']}: {d['kind']}" for d in dups] or
                                               ["none"]),
                "closest_pair_psnr_db": round(worst[0], 2) if worst else None,
                "closest_pair": [worst[1], worst[2]] if worst else None,
            }
        else:
            verdict["gates"]["distinctness"] = {
                "pass": False, "problems": [f"{d['i']}/{d['j']}: {d['kind']}" for d in dups],
                "closest_pair_psnr_db": None, "closest_pair": None,
            }
    else:
        verdict["gates"]["distinctness"] = {"pass": False, "problems": ["cannot run: images missing"]}

    judge_after = dir_sha(args.judge_dir)
    verdict["judge_intact"] = judge_before == judge_after
    verdict["timing"]["grade_s"] = round(time.monotonic() - t0, 2)
    verdict["timing"]["torch_threads"] = 1

    all_pass = all(g.get("pass") for g in verdict["gates"].values()) and verdict["judge_intact"]

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
