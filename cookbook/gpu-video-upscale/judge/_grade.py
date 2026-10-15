#!/usr/bin/env python3
"""Judge driver for the gpu-video-upscale demo. Invoked by grade.sh.

Grades a copied artifact (the artifact under test never touches judge/):
  gate 1 structure    — size, byte-compile, API surface, no banned constructs
  gate 2 weights-load — build_model() params hash to the pinned checkpoint
  gate 3 contract     — shape/dtype/range/input-intact on a fixed probe
  gate 4 correctness  — PSNR/SSIM vs the original over sampled clip frames,
                        must beat the judge's own bicubic baseline by the
                        margin in SPEC.md on EVERY sampled frame
  gate 5 no-cheat     — output is not a resample filter and not a
                        frame-duplication of the input

Prints one JSON verdict on stdout; exit 0 only if every gate passes.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

import torch
import torch.nn.functional as F

# Fixed thread count, not adaptive: torch CPU kernels are deterministic
# run-to-run for a fixed count, and selftest's two-run byte-identity check
# enforces it. A single thread would need minutes per graded 960x540 frame
# on a sandbox CPU; the standard allows "fixed thread counts where results
# depend on it".
torch.set_num_threads(min(8, os.cpu_count() or 1))

VENV_DIR = os.path.join(os.path.expanduser("~"), ".venvs", "gpu-video-upscale")
if os.path.isdir(os.path.join(VENV_DIR, "lib")):
    sys.path.insert(0, VENV_DIR)

DEMO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DEFAULT_WEIGHTS = os.path.join(DEMO_DIR, "data", "weights", "RealESRGAN_x4plus.pth")
DEFAULT_CLIP = os.path.join(DEMO_DIR, "data", "clip", "original.mp4")

MAX_BYTES = 256 * 1024
PROBE_SHAPE = (2, 3, 48, 64)
FILTER_EPS = 1e-3
PSNR_MARGIN_DB = 1.0
SSIM_MARGIN = 0.005

BANNED_TOKENS = (
    "basicsr", "os.", "subprocess", "socket", "urllib", "requests",
    "pathlib", "open(", "BasicSR", "spandrel", "super_image",
    "hififace", "gfpgan", "realesrgan.", "from basicsr",
)


def die(msg):
    print(json.dumps({"error": msg}))
    sys.exit(2)


def check_shas(judge_dir):
    """sha256 of every judge/ source file, before and after the run.

    __pycache__ is excluded: importing the judge legitimately writes .pyc
    files, and they are not judge source.
    """
    digests = {}
    for root, dirs, files in os.walk(judge_dir):
        dirs.sort()
        if os.path.basename(root) == "__pycache__":
            dirs[:] = []
            continue
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(root, name)
            with open(path, "rb") as fh:
                digests[os.path.relpath(path, judge_dir)] = \
                    hashlib.sha256(fh.read()).hexdigest()
    return digests


def load_artifact(path):
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError("artifact exceeds 256 KiB")
    with open(path, "rb") as fh:
        source = fh.read()
    compile(source, path, "exec")          # gate 1 byte-compile, no import
    text = source.decode("utf-8", "replace")
    for bad in BANNED_TOKENS:
        if bad in text:
            raise ValueError(f"artifact text contains banned token {bad!r}")
    spec = importlib.util.spec_from_file_location(
        "artifact_under_test", os.path.abspath(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, text


def gate_structure(mod, text):
    problems = []
    if not callable(getattr(mod, "build_model", None)):
        problems.append("build_model is not callable")
    if not callable(getattr(mod, "upscale_frames", None)):
        problems.append("upscale_frames is not callable")
    if getattr(mod, "SCALE", None) != 4:
        problems.append(f"SCALE is {mod.SCALE!r}, expected 4")
    want_sha = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"
    if getattr(mod, "MODEL_SHA256", None) != want_sha:
        problems.append("MODEL_SHA256 is not the pinned checkpoint hash")
    return problems


def param_sha256(model):
    h = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        h.update(name.encode())
        h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def checkpoint_param_sha256(ckpt):
    params = ckpt["params_ema"] if "params_ema" in ckpt else ckpt
    h = hashlib.sha256()
    for name in sorted(params):
        h.update(name.encode())
        h.update(params[name].detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def gate_weights_load(mod, weights_path):
    """build_model() must return a module whose parameters equal the pinned
    checkpoint's params_ema tensors (sha256 over sorted name->bytes).

    Returns (model, problems); the model is reused by the later gates so
    the 64 MB checkpoint is loaded once per grade."""
    ckpt = torch.load(weights_path, map_location="cpu", weights_only=False)
    want = checkpoint_param_sha256(ckpt)
    # the artifact is graded from a copy in a temp dir, so its own relative
    # weights path cannot resolve; point it at the judge's --weights file
    # (the pinned checkpoint, sha256-verified above) before it builds.
    if hasattr(mod, "WEIGHTS_PATH"):
        mod.WEIGHTS_PATH = weights_path
    model = mod.build_model()
    if not isinstance(model, torch.nn.Module):
        return None, ["build_model() did not return an nn.Module"]
    if model.training:
        return model, ["model is not in eval mode"]
    got = param_sha256(model)
    if got != want:
        return model, [f"parameter sha256 {got} != pinned checkpoint {want}"]
    return model, []


def quant8(x):
    return (x.clamp(0.0, 1.0) * 255.0).round() / 255.0


def psnr(a, b):
    """PSNR (dB) of a vs b on 8-bit-quantised [0,1] float32 frames."""
    mse = float((quant8(a) - quant8(b)).pow(2).mean().item())
    if mse == 0.0:
        return None  # identical: the judge reports null, best possible
    return 10.0 * math.log10(1.0 / mse)


def _gaussian_window():
    coords = torch.arange(11, dtype=torch.float32) - 5.0
    g = torch.exp(-(coords ** 2) / (2 * 1.5 ** 2))
    g = g / g.sum()
    return g[:, None] * g[None, :]


def ssim(a, b):
    """SSIM with the standard 11x11 Gaussian window (sigma 1.5), valid
    padding, per channel averaged, L=1.0, on 8-bit-quantised [0,1] frames.
    Accepts (N, 3, H, W) batches (a single frame is N=1)."""
    a = quant8(a)
    b = quant8(b)
    if a.dim() == 3:  # (3, H, W) -> (1, 3, H, W)
        a = a.unsqueeze(0)
        b = b.unsqueeze(0)
    w = _gaussian_window().to(a.device)
    pad = torch.nn.ZeroPad2d(5)
    mu_a = F.conv2d(pad(a), w.unsqueeze(0).unsqueeze(0).expand(3, 1, 11, 11),
                   groups=3)
    mu_b = F.conv2d(pad(b), w.unsqueeze(0).unsqueeze(0).expand(3, 1, 11, 11),
                   groups=3)
    mu_a2, mu_b2, mu_ab = mu_a ** 2, mu_b ** 2, mu_a * mu_b
    sig_a = F.conv2d(pad(a * a), w.unsqueeze(0).unsqueeze(0).expand(3, 1, 11, 11),
                     groups=3) - mu_a2
    sig_b = F.conv2d(pad(b * b), w.unsqueeze(0).unsqueeze(0).expand(3, 1, 11, 11),
                     groups=3) - mu_b2
    sig_ab = F.conv2d(pad(a * b), w.unsqueeze(0).unsqueeze(0).expand(3, 1, 11, 11),
                     groups=3) - mu_ab
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    ssim_map = ((2 * mu_ab + c1) * (2 * sig_ab + c2)) / \
               ((mu_a2 + mu_b2 + c1) * (sig_a + sig_b + c2))
    return float(ssim_map.mean().item())


def bicubic_baseline(low):
    """The judge's own reference: bicubic upscale of the downscaled frame."""
    return F.interpolate(low, scale_factor=4, mode="bicubic", antialias=True)


def downscale(orig):
    """The judge's own ground-truth protocol: bicubic x0.25 downscale."""
    return F.interpolate(orig, scale_factor=0.25, mode="bicubic", antialias=True)


def clip_geometry(clip_path):
    """(width, height, nb_frames) of the clip, from ffprobe."""
    meta = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,nb_frames",
         "-of", "csv=p=0", clip_path], capture_output=True, text=True)
    if meta.returncode != 0:
        raise RuntimeError("ffprobe failed: " + meta.stderr[-300:])
    w, h, n = meta.stdout.strip().split(",")
    return int(w), int(h), int(n)


def decode_frames(clip_path, indices, geometry):
    """Decode ONLY the requested frame indices to (N,3,H,W) float32 [0,1].

    The clip is 600 frames of 1920x1080 (~4 GB as raw RGB, ~15 GB as
    float32); decoding everything to grade 3 of them would exhaust the
    sandbox's memory. One ffmpeg call per frame index keeps the judge in
    bounded memory and the sampled frames identical to a full decode
    (select, scale and the pixel format are deterministic).
    """
    import numpy as np  # local import; numpy is pinned by setup.sh
    w, h, _ = geometry
    frames = []
    for idx in indices:
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", clip_path,
             "-vf", f"select=eq(n\\,{idx})", "-vsync", "0",
             "-frames:v", "1",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True)
        if out.returncode != 0:
            raise RuntimeError(f"ffmpeg decode of frame {idx} failed: "
                               + out.stderr.decode()[-300:])
        buf = np.frombuffer(out.stdout, dtype=np.uint8)
        if buf.size != h * w * 3:
            raise RuntimeError(f"frame {idx}: decoded {buf.size} bytes, "
                               f"expected {h * w * 3}")
        frames.append(buf.reshape(1, h, w, 3).copy())
    stacked = np.concatenate(frames, axis=0)
    return torch.from_numpy(stacked).permute(0, 3, 1, 2).float() / 255.0


def gate_contract(mod, model):
    problems = []
    cases = []
    g = torch.Generator().manual_seed(1234)
    x = torch.rand(PROBE_SHAPE, generator=g)
    before = x.clone()
    try:
        out = mod.upscale_frames(model, x)
    except Exception as exc:
        return [f"upscale_frames raised {type(exc).__name__}: {str(exc)[:200]}"], []
    if not isinstance(out, torch.Tensor):
        return ["upscale_frames did not return a torch.Tensor"], []
    want_shape = (PROBE_SHAPE[0], 3, PROBE_SHAPE[2] * 4, PROBE_SHAPE[3] * 4)
    case = {"shape": list(out.shape), "want_shape": list(want_shape)}
    if tuple(out.shape) != want_shape:
        problems.append(f"output shape {tuple(out.shape)} != {want_shape}")
    if out.dtype != torch.float32:
        problems.append(f"output dtype {out.dtype} != torch.float32")
    case["finite"] = bool(torch.isfinite(out).all().item())
    if not case["finite"]:
        problems.append("output contains non-finite values")
    # range is checked on the raw output (clamping first would hide a
    # violation); only the metric computation clamps.
    case["in_range"] = bool((out >= -0.001).all().item()
                            and (out <= 1.001).all().item())
    if not case["in_range"]:
        problems.append("output values outside [-0.001, 1.001]")
    o = out.clamp(0.0, 1.0)
    case["input_intact"] = bool(torch.equal(x, before))
    if not case["input_intact"]:
        problems.append("input tensor was modified")
    # the model genuinely ran: not reproducible by bicubic/nearest
    if tuple(out.shape) == want_shape:
        bic = F.interpolate(x, scale_factor=4, mode="bicubic", antialias=True)
        near = F.interpolate(x, scale_factor=4, mode="nearest")
        case["max_abs_vs_bicubic"] = float((o - bic).abs().max().item())
        case["max_abs_vs_nearest"] = float((o - near).abs().max().item())
        if case["max_abs_vs_bicubic"] <= FILTER_EPS:
            problems.append("output equals bicubic upscaling of the input")
        if case["max_abs_vs_nearest"] <= FILTER_EPS:
            problems.append("output equals nearest upscaling of the input")
    cases.append(case)
    return problems, cases


CROP_H, CROP_W = 540, 960  # graded region of each 1920x1080 frame


def center_crop(frame):
    """Deterministic graded region: the centre CROP_H x CROP_W patch.

    The judge's lowered problem (SPEC.md): the region is cropped from the
    original frame, downscaled x4, upscaled by the artifact, and compared
    against the cropped original. Grading the region instead of the whole
    frame keeps CPU grading bounded (~4 s/frame instead of ~70 s) while
    using the real clip's content.
    """
    _, _, h, w = frame.shape
    if h < CROP_H or w < CROP_W:
        return frame  # clip smaller than the region: grade it whole
    top, left = (h - CROP_H) // 2, (w - CROP_W) // 2
    return frame[:, :, top:top + CROP_H, left:left + CROP_W]


def gate_correctness(mod, model, orig_by_index, total, seed, n_frames):
    """Sample frames, downscale x4, upscale with the artifact, and compare
    against the original with PSNR/SSIM against the bicubic baseline."""
    stride = max(1, total // n_frames)
    idxs = [(k * stride + seed) % total for k in range(n_frames)]
    frames = []
    worst = {"psnr_margin": None, "ssim_margin": None}
    for i in idxs:
        orig = center_crop(orig_by_index[i])
        low = downscale(orig)
        try:
            out = mod.upscale_frames(model, low)
        except Exception as exc:
            frames.append({"index": i, "error": f"{type(exc).__name__}: {str(exc)[:150]}"})
            continue
        entry = {"index": i}
        if out.shape != orig.shape:
            frames.append({"index": i, "error":
                           f"shape {tuple(out.shape)} != {tuple(orig.shape)}"})
            continue
        entry["shape_ok"] = True
        pm = psnr(out, orig)
        pb = psnr(bicubic_baseline(low), orig)
        sm = ssim(out, orig)
        sb = ssim(bicubic_baseline(low), orig)
        entry["psnr_model"] = pm
        entry["psnr_bicubic"] = pb
        entry["ssim_model"] = sm
        entry["ssim_bicubic"] = sb
        ok = True
        if pm is None:
            margin = None  # perfect reconstruction: best possible
        else:
            margin = pm - pb
            entry["psnr_margin"] = round(margin, 4)
            if margin < PSNR_MARGIN_DB:
                ok = False
        smargin = sm - sb
        entry["ssim_margin"] = round(smargin, 5)
        if smargin < SSIM_MARGIN:
            ok = False
        entry["pass"] = ok
        frames.append(entry)
        if margin is not None:
            worst["psnr_margin"] = margin if worst["psnr_margin"] is None \
                else min(worst["psnr_margin"], margin)
        worst["ssim_margin"] = smargin if worst["ssim_margin"] is None \
            else min(worst["ssim_margin"], smargin)
    return frames, worst


def gate_no_cheat(mod, model, orig_by_index):
    """The output must not be a resample filter and must not duplicate or
    reorder frames across the temporal axis.

    The temporal checks run on BOTH calling conventions the artifact
    contract allows: frame-by-frame (N=1 batches, as gate 4 samples them)
    and one multi-frame batch — an artifact that reorders or broadcasts
    frames only when handed a batch must not pass (SPEC.md names
    frame_reorder and frame-0-broadcast as cheats the judge must kill).
    """
    problems = []
    idxs = [i for i in (0, 1, 2) if i in orig_by_index]
    if len(idxs) < 2:
        idxs = sorted(orig_by_index)[:3]  # tiny clips: whatever was decoded
    lows = [downscale(center_crop(orig_by_index[i])) for i in idxs]
    try:
        outs = [mod.upscale_frames(model, l) for l in lows]
    except Exception as exc:
        return [f"upscale_frames raised {type(exc).__name__}: {str(exc)[:200]}"]
    filters = {
        "bicubic": lambda t: F.interpolate(t, scale_factor=4, mode="bicubic",
                                            antialias=True),
        "nearest": lambda t: F.interpolate(t, scale_factor=4, mode="nearest"),
        "bilinear": lambda t: F.interpolate(t, scale_factor=4, mode="bilinear",
                                             antialias=True),
        "area": lambda t: F.interpolate(t, scale_factor=4, mode="area"),
    }
    for name, fn in filters.items():
        diffs = []
        for low, out in zip(lows, outs):
            if out.shape != fn(low).shape:
                diffs.append(float("inf"))
                continue
            diffs.append(float((out.clamp(0, 1) - fn(low).clamp(0, 1)).abs()
                               .max().item()))
        if all(d <= FILTER_EPS for d in diffs):
            problems.append(f"output equals {name} resampling of the input")
    # temporal: distinct inputs must give distinct outputs
    for i in range(len(outs)):
        for j in range(i + 1, len(outs)):
            if outs[i].shape != outs[j].shape:
                continue
            d = float((outs[i].clamp(0, 1) - outs[j].clamp(0, 1)).abs()
                      .max().item())
            if d <= FILTER_EPS:
                problems.append(
                    f"outputs for distinct frames {idxs[i]}/{idxs[j]} are "
                    f"identical (max|diff|={d:.2e}): frame duplication")
    # batch path: the same frames in one batch must land in the same order
    # as graded one-by-one (kills reordering and frame-0 broadcast).
    batch = torch.cat(lows, dim=0)  # (3, 3, H, W), input order preserved
    before = batch.clone()
    try:
        out_batch = mod.upscale_frames(model, batch)
    except Exception as exc:
        problems.append(f"upscale_frames raised on a batch of {len(lows)} "
                        f"frames: {type(exc).__name__}: {str(exc)[:200]}")
        return problems
    if not torch.equal(batch, before):
        problems.append("input batch was modified")
        return problems
    if not isinstance(out_batch, torch.Tensor) or out_batch.shape[0] != len(lows):
        problems.append(f"batch of {len(lows)} frames produced "
                        f"{getattr(out_batch, 'shape', None)}: frame count "
                        "not preserved")
        return problems
    for k, single in enumerate(outs):
        if out_batch[k:k + 1].shape != single.shape:
            problems.append(f"batch output frame {k} has shape "
                            f"{tuple(out_batch[k:k + 1].shape)} != "
                            f"{tuple(single.shape)}")
            continue
        d = float((out_batch[k:k + 1].clamp(0, 1) - single.clamp(0, 1)).abs()
                  .max().item())
        if d > FILTER_EPS:
            problems.append(
                f"batch output frame {k} differs from the same frame graded "
                f"one-by-one (max|diff|={d:.2e}): frames reordered or "
                "swapped inside a batch")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--clip", default=DEFAULT_CLIP)
    ap.add_argument("--weights", default=DEFAULT_WEIGHTS)
    ap.add_argument("--frames", type=int, default=3)
    ap.add_argument("--tile", type=int, default=0,
                    help="tile size for the artifact run (0 = whole frame); "
                         "informational only, the judge runs whole frames")
    ap.add_argument("--judge-dir")
    args = ap.parse_args()

    judge_dir = os.path.abspath(args.judge_dir or
                                os.path.join(os.path.dirname(__file__)))
    sha_before = check_shas(judge_dir)

    tmp = tempfile.mkdtemp(prefix="gpu-video-upscale-artifact-")
    art_path = os.path.join(tmp, "upscale.py")
    shutil.copy(args.artifact, art_path)

    verdict = {"artifact": os.path.basename(args.artifact), "seed": args.seed,
               "gates": {}, "timing": {}}
    rc = 0
    try:
        try:
            mod, text = load_artifact(art_path)
        except Exception as exc:
            verdict["gates"]["structure"] = {"pass": False,
                                             "problems": [str(exc)[:300]]}
            rc = 1
        else:
            verdict["gates"]["structure"] = {
                "pass": True, "problems": gate_structure(mod, text)}
            if verdict["gates"]["structure"]["problems"]:
                verdict["gates"]["structure"]["pass"] = False
                rc = 1

        if rc == 0:
            # verify the checkpoint itself is the pinned one before loading
            try:
                with open(args.weights, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
                want = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"
                if digest != want:
                    verdict["gates"]["weights-load"] = {
                        "pass": False,
                        "problems": [f"weights file sha256 {digest} != pinned {want}"]}
                    rc = 1
            except OSError as exc:
                verdict["gates"]["weights-load"] = {
                    "pass": False, "problems": [f"weights unreadable: {exc}"]}
                rc = 1
            if rc == 0:
                import time
                t0 = time.monotonic()
                model = None
                try:
                    model, problems = gate_weights_load(mod, args.weights)
                except Exception as exc:
                    problems = [f"{type(exc).__name__}: {str(exc)[:300]}"]
                verdict["timing"]["build_model_s"] = round(time.monotonic() - t0, 3)
                verdict["gates"]["weights-load"] = {
                    "pass": not problems, "problems": problems}
                if problems:
                    rc = 1

        if rc == 0:
            import time
            t0 = time.monotonic()
            try:
                problems, cases = gate_contract(mod, model)
            except Exception as exc:
                problems, cases = [f"{type(exc).__name__}: {str(exc)[:300]}"], []
            verdict["timing"]["contract_s"] = round(time.monotonic() - t0, 3)
            verdict["gates"]["contract"] = {"pass": not problems,
                                            "problems": problems, "cases": cases}
            if problems:
                rc = 1

        orig_by_index = {}
        if rc == 0:
            import time
            try:
                geometry = clip_geometry(args.clip)
                w, h, total = geometry
                stride = max(1, total // max(1, args.frames))
                sample_idxs = sorted(set(
                    [(k * stride + args.seed) % total
                     for k in range(max(1, args.frames))] + [0, 1, 2]))
                t0 = time.monotonic()
                clip_frames = decode_frames(args.clip, sample_idxs, geometry)
            except Exception as exc:
                verdict["gates"]["correctness"] = {
                    "pass": False,
                    "problems": [f"clip decode failed: {str(exc)[:300]}"]}
                rc = 1
            else:
                orig_by_index = {i: clip_frames[k:k + 1]
                                 for k, i in enumerate(sample_idxs)}
                verdict["timing"]["decode_s"] = round(time.monotonic() - t0, 3)
                t0 = time.monotonic()
                try:
                    frames, worst = gate_correctness(mod, model, orig_by_index,
                                                     total, args.seed, args.frames)
                except Exception as exc:
                    frames, worst = [], {"error": str(exc)[:200]}
                verdict["timing"]["correctness_s"] = round(time.monotonic() - t0, 3)
                bad = [f for f in frames if not f.get("pass", False)]
                verdict["gates"]["correctness"] = {
                    "pass": not bad,
                    "cases": len(frames),
                    "crop": [CROP_H, CROP_W],
                    "failed": [f"{f['index']}:{f.get('error', 'metrics')}"
                               for f in bad],
                    "frames": frames, "worst": worst}
                if bad:
                    rc = 1

        if rc == 0:
            import time
            t0 = time.monotonic()
            try:
                problems = gate_no_cheat(mod, model, orig_by_index)
            except Exception as exc:
                problems = [f"{type(exc).__name__}: {str(exc)[:300]}"]
            verdict["timing"]["no_cheat_s"] = round(time.monotonic() - t0, 3)
            verdict["gates"]["no-cheat"] = {"pass": not problems,
                                            "problems": problems}
            if problems:
                rc = 1

        sha_after = check_shas(judge_dir)
        verdict["judge_intact"] = sha_before == sha_after
        if not verdict["judge_intact"]:
            rc = 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
