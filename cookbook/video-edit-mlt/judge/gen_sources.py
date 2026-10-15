#!/usr/bin/env python3
"""Generate the demo's synthetic sources, deterministically:

    assets/clip_a.mp4, clip_b.mp4, clip_c.mp4  -- flat hue + barcode band
    assets/music.wav                           -- 9 s of 220 Hz stereo
    assets/voice.wav                           -- 1 kHz bursts in the
                                                  spec's voice windows
    assets/logo.png                            -- 160x80 checker pattern

Usage: gen_sources.py [--ffmpeg PATH] [--assets DIR] [--verify]

Everything is computed locally (raw frames are streamed into the pinned
ffmpeg); nothing is downloaded.  --verify decodes every source frame's
barcode and checks it -- the judge's power check on the raw material.
"""

import argparse
import json
import math
import os
import struct
import subprocess
import sys
import wave
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edl  # noqa: E402

DEMO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = json.load(open(os.path.join(DEMO, "spec.json")))
W, H = edl.W, edl.H
FPS = SPEC["format"]["fps_num"]
DUR_S = SPEC["format"]["frames"] / FPS   # audio length = timeline length

FFMPEG = os.environ.get("VIDEO_EDIT_FFMPEG", "ffmpeg")


def frame_bytes(clip_id, frame, rgb):
    """One 1280x720 rgb24 source frame: flat hue, barcode band on top."""
    band = edl.band_row(edl.encode_code(clip_id, frame)) * edl.BAND_H
    body = bytes(rgb) * (W * (H - edl.BAND_H))
    pad = bytes(rgb) * (W * edl.BAND_Y)
    return pad + band + body


def rgb_to_png(rgb, width=W, height=H):
    """rgb24 bytes -> PNG (colour type 2, filter 0)."""
    stride = width * 3
    rows = b"".join(b"\x00" + rgb[y * stride:(y + 1) * stride]
                    for y in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR",
                        struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(rows, 1))
            + png_chunk(b"IEND", b""))


def gen_clip(path, clip_id, rgb, frames, work):
    # Frame PNGs, then image2 -> mp4.  (Piping rawvideo into ffmpeg n8.x
    # misaligns frames: its demuxer demands whole-frame packets, and a
    # pipe can't deliver 2.7 MB reads.)
    for f in range(frames):
        with open(os.path.join(work, "%04d.png" % f), "wb") as fh:
            fh.write(rgb_to_png(frame_bytes(clip_id, f, rgb)))
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error",
         "-framerate", str(FPS), "-i", os.path.join(work, "%04d.png"),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", path],
        check=True)


def gen_wav(path, freq, windows, amp):
    """Sine at `freq` Hz, only inside `windows` ([] = everywhere)."""
    n = int(round(DUR_S * 48000))
    buf = bytearray(n * 4)
    for i in range(n):
        t = i / 48000
        if windows and not any(lo <= t < hi for lo, hi in windows):
            continue  # silence
        s = int(amp * 32767 * math.sin(2 * math.pi * freq * t))
        struct.pack_into("<hh", buf, i * 4, s, s)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(bytes(buf))


def png_chunk(tag, data):
    c = tag + data
    return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))


def gen_logo(path, lw=160, lh=80):
    """High-contrast 20 px checkerboard with a magenta border, RGB8 PNG."""
    rows = bytearray()
    for y in range(lh):
        rows.append(0)  # filter: none
        for x in range(lw):
            if x < 4 or y < 4 or x >= lw - 4 or y >= lh - 4:
                rows += bytes((255, 0, 255))
            else:
                on = ((x // 20) + (y // 20)) % 2
                rows += bytes((255, 255, 255) if on else (0, 0, 0))
    png = (b"\x89PNG\r\n\x1a\n"
           + png_chunk(b"IHDR", struct.pack(">IIBBBBB", lw, lh, 8, 2, 0, 0, 0))
           + png_chunk(b"IDAT", zlib.compress(bytes(rows), 9))
           + png_chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def verify(assets):
    """Decode every frame's barcode in each source clip. Power check."""
    ok = True
    for name, s in SPEC["sources"].items():
        path = os.path.join(assets, os.path.basename(s["file"]))
        raw = subprocess.run(
            [FFMPEG.replace("ffmpeg", "ffprobe") if FFMPEG.endswith("ffmpeg")
             else "ffprobe",
             "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries", "stream=nb_read_frames",
             "-of", "csv=p=0", path],
            capture_output=True, text=True).stdout.strip()
        p = subprocess.Popen(
            [FFMPEG, "-loglevel", "error", "-i", path,
             "-vf", f"crop={W}:{edl.BAND_H}:0:{edl.BAND_Y}",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE)
        band_size = W * edl.BAND_H * 3
        n, bad = 0, 0
        while True:
            band = p.stdout.read(band_size)
            if len(band) < band_size:
                break
            if edl.decode_band(band) != (s["clip_id"], n):
                bad += 1
                print(f"verify: {name} frame {n}: decode "
                      f"{edl.decode_band(band)}", file=sys.stderr)
            n += 1
        p.wait()
        print(f"verify: {path}: {n} frames decoded, {bad} bad "
              f"(container says {raw})")
        if bad or n != s["frames"]:
            ok = False
    return ok


def main():
    global FFMPEG
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ffmpeg", default=FFMPEG)
    ap.add_argument("--assets", default=os.path.join(DEMO, "assets"))
    ap.add_argument("--verify", action="store_true",
                    help="only verify existing assets")
    args = ap.parse_args()
    FFMPEG = args.ffmpeg
    assets = args.assets
    os.makedirs(assets, exist_ok=True)

    if not args.verify:
        import tempfile
        for name, s in SPEC["sources"].items():
            out = os.path.join(assets, os.path.basename(s["file"]))
            print(f"gen: {out} ({s['frames']} frames)")
            with tempfile.TemporaryDirectory() as work:
                gen_clip(out, s["clip_id"], s["rgb"], s["frames"], work)
        m = os.path.join(assets, "music.wav")
        print(f"gen: {m} (220 Hz, {DUR_S:.3f} s)")
        gen_wav(m, SPEC["audio"]["music_hz"], [], 0.28)
        v = os.path.join(assets, "voice.wav")
        print(f"gen: {v} (1 kHz bursts {SPEC['audio']['voice_windows']})")
        gen_wav(v, 1000, SPEC["audio"]["voice_windows"], 0.45)
        l = os.path.join(assets, "logo.png")
        print(f"gen: {l}")
        gen_logo(l)

    if not verify(assets):
        raise SystemExit("gen_sources: barcode verification FAILED")
    print("gen_sources: all sources verified")


if __name__ == "__main__":
    main()
