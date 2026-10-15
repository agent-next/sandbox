#!/usr/bin/env python3
"""Write known-bad single-edit mutants of the known-good artifact.

    mutants.py <good_dir> <out_dir> [--seed N]

Every mutant is the good artifact with one property broken, so the judge
either kills it on the gate that property belongs to or the mutant survives
and the self-test reports a real gap.  The required negative controls (a
1-frame static GIF, a QR encoding the wrong string) are included.

The mutants are written from the good artifact by this script, not committed,
so they stay in step with it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import viral_judge as J  # noqa: E402


def _fresh(good: str, out: str, name: str) -> str:
    d = os.path.join(out, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    shutil.copytree(good, d)
    return d


def _write_wav(path: str, samples: np.ndarray, sr: int = J.SR) -> None:
    pcm = np.clip(np.round(samples * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _read_wav(path: str) -> np.ndarray:
    return J.read_pcm_mono(path)


# --- WAV mutants ------------------------------------------------------------
def mut_steady_tone(good: str, out: str, seed: int) -> str:
    """A plain steady tone: no glide, no octave span."""
    d = _fresh(good, out, "wav_steady_tone")
    n = int(J.SR * 22.0)
    t = np.arange(n) / J.SR
    _write_wav(os.path.join(d, "shepard.wav"),
               0.8 * np.sin(2 * np.pi * 220.0 * t))
    return d


def mut_plain_sweep(good: str, out: str, seed: int) -> str:
    """A monotone log sweep that never returns to its starting pitch class."""
    d = _fresh(good, out, "wav_plain_sweep")
    n = int(J.SR * 22.0)
    t = np.arange(n) / J.SR
    T = 22.0
    f0 = 200.0
    # 2.5 octaves: rises, but closes on a different pitch class
    A = T / (2.5 * np.log(2.0))
    phase = 2 * np.pi * f0 * A * (np.exp2(2.5 * t / T) - 1.0)
    _write_wav(os.path.join(d, "shepard.wav"), 0.8 * np.sin(phase))
    return d


def mut_too_short(good: str, out: str, seed: int) -> str:
    """The good tone, truncated below the 20 s minimum."""
    d = _fresh(good, out, "wav_too_short")
    x = _read_wav(os.path.join(good, "shepard.wav"))
    _write_wav(os.path.join(d, "shepard.wav"), x[: int(J.SR * 12.0)])
    return d


def mut_wrong_rate(good: str, out: str, seed: int) -> str:
    """The good tone resampled at 16 kHz (a WAV the spec does not allow)."""
    d = _fresh(good, out, "wav_wrong_rate")
    x = _read_wav(os.path.join(good, "shepard.wav"))
    m = int(len(x) * 16000 / J.SR)
    idx = np.linspace(0, len(x) - 1, m)
    _write_wav(os.path.join(d, "shepard.wav"), np.interp(idx, np.arange(len(x)), x),
               sr=16000)
    return d


# --- GIF mutants ------------------------------------------------------------
def _gif_frames(path: str):
    frames, loop = J.read_gif_frames(path)
    return [Image.fromarray(f["rgb"], "RGB") for f in frames], loop


def _good_palette(good: str) -> list[tuple[int, int, int]]:
    """The good GIF's 5 colours, in a stable order."""
    frames, _ = J.read_gif_frames(os.path.join(good, "ball.gif"))
    cols = set()
    for f in frames:
        cols |= set(J.frame_colours(f))
    return sorted(cols)


def _to_paletted(im: Image.Image, pal: list[tuple[int, int, int]]):
    """Map an RGB frame onto the given palette (nearest colour, exact set)."""
    a = np.asarray(im.convert("RGB"), dtype=np.int32)
    p = np.array(pal, dtype=np.int32)
    flat = a.reshape(-1, 3)
    d = ((flat[:, None, :] - p[None, :, :]) ** 2).sum(axis=2)
    idx = d.argmin(axis=1).astype(np.uint8).reshape(a.shape[:2])
    out = Image.fromarray(idx, mode="P")
    out.putpalette(bytes(c for rgb in pal for c in rgb))
    return out


def _save_gif(frames, path: str, duration: int, loop: int = 0,
              pal: list[tuple[int, int, int]] | None = None) -> None:
    """Save frames as a GIF on an exact palette, so a mutant only breaks the
    one property it is meant to break."""
    if pal is None:
        pal = sorted({tuple(int(c) for c in v)
                      for f in frames
                      for v in np.unique(np.asarray(f), axis=0)})
    imgs = [_to_paletted(f, pal) for f in frames]
    imgs[0].save(path, save_all=True, append_images=imgs[1:],
                 duration=duration, loop=loop, optimize=False)


def mut_static_one_frame(good: str, out: str, seed: int) -> str:
    """Negative control: a single static frame, no motion to measure."""
    d = _fresh(good, out, "gif_static_one_frame")
    frames, _ = _gif_frames(os.path.join(good, "ball.gif"))
    _save_gif(frames[:1], os.path.join(d, "ball.gif"), duration=60,
              pal=_good_palette(good))
    return d


def mut_too_few_frames(good: str, out: str, seed: int) -> str:
    """24 frames: an animation, but shorter than the 48-frame minimum."""
    d = _fresh(good, out, "gif_too_few_frames")
    frames, _ = _gif_frames(os.path.join(good, "ball.gif"))
    _save_gif(frames[:24], os.path.join(d, "ball.gif"), duration=60,
              pal=_good_palette(good))
    return d


def mut_six_colours(good: str, out: str, seed: int) -> str:
    """A sixth colour painted into one frame."""
    d = _fresh(good, out, "gif_six_colours")
    frames, _ = _gif_frames(os.path.join(good, "ball.gif"))
    dr = ImageDraw.Draw(frames[3])
    dr.rectangle([2, 2, 40, 40], fill=(255, 0, 255))
    pal = _good_palette(good) + [(255, 0, 255)]
    _save_gif(frames, os.path.join(d, "ball.gif"), duration=60, pal=pal)
    return d


def mut_flat_ball(good: str, out: str, seed: int) -> str:
    """The ball slides along the floor: motion, but never bounces.

    The scene keeps the good artifact's full 5-colour set (background, floor,
    floor edge, ball trail, ball) so the only property this mutant breaks is
    the bounce geometry.
    """
    d = _fresh(good, out, "gif_flat_ball")
    frames, _ = _gif_frames(os.path.join(good, "ball.gif"))
    bg, ball, floor = (24, 26, 38), (235, 87, 87), (242, 201, 76)
    edge, trail = (60, 110, 200), (86, 207, 165)
    out_frames = []
    for i, f in enumerate(frames):
        im = Image.new("RGB", f.size, bg)
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, f.size[1] - 40, f.size[0] - 1, f.size[1] - 1],
                     fill=floor)
        dr.line([0, f.size[1] - 40, f.size[0] - 1, f.size[1] - 40],
                fill=edge, width=3)
        cx = 40 + 3 * i
        cy = f.size[1] - 1 - 16
        # a trail blob in the fifth colour, as in the good artifact
        dr.ellipse([cx - 24, cy - 12, cx - 12, cy], fill=trail)
        dr.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=ball)
        out_frames.append(im)
    _save_gif(out_frames, os.path.join(d, "ball.gif"), duration=60,
              pal=_good_palette(good))
    return d


def mut_finite_loop(good: str, out: str, seed: int) -> str:
    """The animation plays once instead of looping forever."""
    d = _fresh(good, out, "gif_finite_loop")
    frames, _ = _gif_frames(os.path.join(good, "ball.gif"))
    _save_gif(frames, os.path.join(d, "ball.gif"), duration=60, loop=1,
              pal=_good_palette(good))
    return d


# --- QR mutants -------------------------------------------------------------
def mut_qr_wrong_string(good: str, out: str, seed: int) -> str:
    """Negative control: a perfectly scannable QR encoding the wrong string."""
    d = _fresh(good, out, "qr_wrong_string")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools"))
    import qr  # noqa: E402
    m = qr.encode(f"VIRAL-MICROGEN-{seed + 1}")
    scale, border = 10, 4
    n = len(m)
    im = Image.new("RGB", ((n + 2 * border) * scale,) * 2, (255, 255, 255))
    dr = ImageDraw.Draw(im)
    for r in range(n):
        for c in range(n):
            if m[r][c]:
                x0, y0 = (c + border) * scale, (r + border) * scale
                dr.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1],
                             fill=(0, 0, 0))
    im.save(os.path.join(d, "qr.png"))
    return d


def mut_qr_corrupt(good: str, out: str, seed: int) -> str:
    """A QR whose data area is painted over: neither library can read it."""
    d = _fresh(good, out, "qr_corrupt")
    p = os.path.join(d, "qr.png")
    im = Image.open(p).convert("RGB")
    dr = ImageDraw.Draw(im)
    w, h = im.size
    dr.rectangle([w // 3, h // 3, 2 * w // 3, 2 * h // 3], fill=(255, 255, 255))
    im.save(p)
    return d


# --- palette mutants --------------------------------------------------------
def mut_palette_invented(good: str, out: str, seed: int) -> str:
    """A swatch colour that appears nowhere in the GIF."""
    d = _fresh(good, out, "palette_invented")
    p = os.path.join(d, "palette.png")
    im = Image.open(p).convert("RGB")
    a = np.asarray(im).copy()
    vals, cts = np.unique(a.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-cts)
    # recolour the first non-background swatch to an invented colour
    swatch = vals[order[1]]
    a[np.all(a == swatch, axis=2)] = np.array([1, 2, 3], dtype=np.uint8)
    Image.fromarray(a).save(p)
    return d


def mut_palette_missing(good: str, out: str, seed: int) -> str:
    """A GIF colour absent from the card: two swatches share one colour."""
    d = _fresh(good, out, "palette_missing")
    p = os.path.join(d, "palette.png")
    im = Image.open(p).convert("RGB")
    a = np.asarray(im).copy()
    vals, cts = np.unique(a.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-cts)
    src, dst = vals[order[1]], vals[order[2]]
    a[np.all(a == dst, axis=2)] = src
    Image.fromarray(a).save(p)
    return d


def mut_palette_four_swatches(good: str, out: str, seed: int) -> str:
    """One swatch painted out: four swatches, not five."""
    d = _fresh(good, out, "palette_four_swatches")
    p = os.path.join(d, "palette.png")
    im = Image.open(p).convert("RGB")
    a = np.asarray(im).copy()
    vals, cts = np.unique(a.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-cts)
    bg = vals[order[0]]
    swatch = vals[order[1]]
    a[np.all(a == swatch, axis=2)] = bg
    Image.fromarray(a).save(p)
    return d


# --- structural mutant ------------------------------------------------------
def mut_missing_file(good: str, out: str, seed: int) -> str:
    """A required file removed: validation must fail before any gate runs."""
    d = _fresh(good, out, "missing_file")
    os.remove(os.path.join(d, "palette.png"))
    return d


MUTANTS = [
    ("wav_steady_tone", "shepard_property", mut_steady_tone),
    ("wav_plain_sweep", "shepard_property", mut_plain_sweep),
    ("wav_too_short", "wav_format", mut_too_short),
    ("wav_wrong_rate", "wav_format", mut_wrong_rate),
    ("gif_static_one_frame", "ball_bounces", mut_static_one_frame),
    ("gif_too_few_frames", "gif_animation", mut_too_few_frames),
    ("gif_six_colours", "gif_animation", mut_six_colours),
    ("gif_flat_ball", "ball_bounces", mut_flat_ball),
    ("gif_finite_loop", "gif_animation", mut_finite_loop),
    ("qr_wrong_string", "qr_scans", mut_qr_wrong_string),
    ("qr_corrupt", "qr_scans", mut_qr_corrupt),
    ("palette_invented", "palette_match", mut_palette_invented),
    ("palette_missing", "palette_match", mut_palette_missing),
    ("palette_four_swatches", "palette_match", mut_palette_four_swatches),
    ("missing_file", None, mut_missing_file),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("good_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    index = []
    for name, gate, fn in MUTANTS:
        d = fn(args.good_dir, args.out_dir, args.seed)
        index.append(dict(name=name, expected_gate=gate,
                          artifact=os.path.relpath(d, args.out_dir)))
        print(f"mutants: wrote {name} (expected gate: {gate})")
    with open(os.path.join(args.out_dir, "mutants.json"), "w") as f:
        json.dump(index, f, indent=2)
    print(f"mutants: {len(index)} mutants in {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
