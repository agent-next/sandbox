#!/usr/bin/env python3
"""Judge for cookbook/video-transcode-pipeline. Python 3.10+, stdlib only.

Grades one artifact (a directory holding pipeline.sh) against the gates in
SPEC.md. Every gate is a numeric comparison against something the artifact
does not control: the source fixture's own burned-in frame counter, the
known transcript of the speech clip, the analytic frame grid, or ffprobe's
reading of the bytes on disk.

    grade.sh <artifact> [--seed N] [--json out.json]

Exit 0 only when every gate passes. The verdict JSON is deterministic for a
given seed; the only non-deterministic fields live under "timing".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

# --------------------------------------------------------------------------
# Pins: the fixture's own numbers. These are properties of the committed
# inputs, not of any artifact, so the judge can hard-code them.
# --------------------------------------------------------------------------
SRC_WIDTH = 640
SRC_HEIGHT = 360
SRC_FPS = 24
SRC_DURATION = 20.0
KEYFRAME_INTERVAL = 4.0
KEYFRAME_TOL = 0.01          # 4 s +- 1 %
MIN_KEYFRAME_GAPS = 4
DURATION_TOL = 0.1           # G3: seconds
COUNTER_TOL = 2              # G5: frames
COUNTER_MIN_MATCH = 0.95     # G5: fraction of samples that must match
POSTER_MIN_PX = 100
POSTER_MIN_DISTINCT = 0.05   # G6: fraction of the 256 luminance levels present
POSTER_MIN_NONMODAL = 0.05   # G6: fraction of pixels off the background value
CAPTION_MIN_CUES = 4
CAPTION_MIN_COVERAGE = 0.80
WER_LIMIT = 0.20
RUN_TIMEOUT = 300            # G1: seconds

# The speech clip's transcript (identical to fixtures/TRANSCRIPT.txt). This
# is the ground truth for the word-error-rate gate.
SPEECH_TEXT = (
    "The quick brown fox jumps over the lazy dog. "
    "Pack my box with five dozen liquor jugs."
)

# Where the frame counter sits, as a fraction of the frame, and the
# normalised glyph grid the decoder reduces it to.
COUNTER_BOX = (16 / 640, 284 / 360, 248 / 640, 64 / 360)   # x, y, w, h
COUNTER_SCALE = (992, 256)
GLYPH_GRID = (16, 24)

REQUIRED = ["360p/index.m3u8", "720p/index.m3u8", "poster.png", "captions.vtt"]
RENDITIONS = {"360p": (640, 360), "720p": (1280, 720)}

NUM_WORDS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
             "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
             "10": "ten", "11": "eleven", "12": "twelve"}


class GateFailure(RuntimeError):
    """A gate did not pass; carries the gate name and a human reason."""

    def __init__(self, gate: str, reason: str):
        super().__init__(reason)
        self.gate = gate
        self.reason = reason


def run(cmd: list[str], timeout: float = 120, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed (exit {proc.returncode}): "
                           f"{(proc.stderr or proc.stdout).strip()[-400:]}")
    return proc


def ffprobe_json(args: list[str]) -> dict:
    proc = run(["ffprobe", "-v", "error", "-of", "json", *args])
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------
# G1: run the artifact
# --------------------------------------------------------------------------
def run_pipeline(artifact: Path, fixtures: Path, workdir: Path, seed: int) -> tuple[Path, float]:
    """Copy the artifact into a temp dir, run it, return its output dir."""
    if artifact.is_file():
        if artifact.name != "pipeline.sh":
            raise GateFailure("runs", f"{artifact} is not pipeline.sh")
        art_dir = artifact.parent
    else:
        art_dir = artifact
    src = art_dir / "pipeline.sh"
    if not src.is_file():
        raise GateFailure("runs", f"no pipeline.sh under {artifact}")

    run_dir = workdir / "run"
    run_dir.mkdir(parents=True)
    shutil.copy2(src, run_dir / "pipeline.sh")
    # The pipeline reads its speech fixture next to itself; give the copy one.
    shutil.copytree(fixtures, run_dir / "fixtures")
    out = run_dir / "out"

    start = time.monotonic()
    proc = subprocess.run(
        ["bash", str(run_dir / "pipeline.sh"),
         "--input", str(fixtures / "source.mp4"),
         "--out", str(out), "--seed", str(seed)],
        capture_output=True, text=True, timeout=RUN_TIMEOUT, cwd=run_dir)
    elapsed = time.monotonic() - start
    if proc.returncode != 0:
        raise GateFailure("runs", f"pipeline.sh exited {proc.returncode}: "
                                  f"{(proc.stderr or proc.stdout).strip()[-400:]}")
    missing = [f for f in REQUIRED if not (out / f).is_file()]
    if missing:
        raise GateFailure("runs", f"pipeline.sh did not create: {', '.join(missing)}")
    for name in RENDITIONS:
        if not (out / name / "index.m3u8").is_file():
            raise GateFailure("runs", f"no playlist under {name}/")
    return out, elapsed


# --------------------------------------------------------------------------
# G2/G3/G4: ffprobe on the renditions
# --------------------------------------------------------------------------
def playlist_segments(out: Path, name: str) -> list[Path]:
    """The segments a player would actually load, in playlist order.

    Reading the playlist rather than globbing the directory is the point:
    the .m3u8 is the artifact's declared output, so a segment the playlist
    omits is a segment the rendition does not have.
    """
    playlist = out / name / "index.m3u8"
    if not playlist.is_file():
        raise GateFailure("runs", f"{name}/index.m3u8 is missing")
    lines = [ln.strip() for ln in
             playlist.read_text(encoding="utf-8", errors="replace").splitlines()]
    if not lines or lines[0] != "#EXTM3U":
        raise GateFailure("playlist", f"{name}/index.m3u8 does not start with #EXTM3U")
    if "#EXT-X-ENDLIST" not in lines:
        raise GateFailure("playlist", f"{name}/index.m3u8 has no #EXT-X-ENDLIST")
    segs = []
    for ln in lines:
        if not ln or ln.startswith("#"):
            continue
        p = (playlist.parent / ln).resolve()
        if not p.is_file():
            raise GateFailure("playlist",
                              f"{name}/index.m3u8 references {ln}, which is not there")
        segs.append(p)
    if not segs:
        raise GateFailure("playlist", f"{name}/index.m3u8 lists no segments")
    return segs


def concat_arg(out: Path, name: str) -> str:
    return "concat:" + "|".join(str(s) for s in playlist_segments(out, name))


def probe_streams(target: str, select: str | None = None) -> list[dict]:
    args = ["-f", "mpegts", "-i", target, "-show_entries",
            "stream=codec_name,width,height,codec_type"]
    if select:
        args = ["-select_streams", select, *args]
    return ffprobe_json(args).get("streams", [])


def check_geometry(out: Path) -> dict:
    """G2: first segment and the concatenated stream report exact geometry."""
    detail = {}
    for name, (want_w, want_h) in RENDITIONS.items():
        segs = playlist_segments(out, name)
        first = probe_streams(str(segs[0]))
        whole = probe_streams(concat_arg(out, name))
        for label, streams in (("first", first), ("concat", whole)):
            v = [s for s in streams if s.get("codec_type") == "video"]
            a = [s for s in streams if s.get("codec_type") == "audio"]
            if not v:
                raise GateFailure("geometry", f"{name} {label} has no video stream")
            if not a:
                raise GateFailure("geometry", f"{name} {label} has no audio stream")
            if (v[0].get("width"), v[0].get("height")) != (want_w, want_h):
                raise GateFailure(
                    "geometry",
                    f"{name} {label} is {v[0].get('width')}x{v[0].get('height')}, "
                    f"expected {want_w}x{want_h}")
            if v[0].get("codec_name") != "h264":
                raise GateFailure("geometry",
                                  f"{name} {label} video codec is {v[0].get('codec_name')}, expected h264")
            if a[0].get("codec_name") != "aac":
                raise GateFailure("geometry",
                                  f"{name} {label} audio codec is {a[0].get('codec_name')}, expected aac")
        detail[name] = {"width": want_w, "height": want_h,
                        "video": "h264", "audio": "aac",
                        "segments": len(segs)}
    return detail


def check_duration(out: Path) -> dict:
    """G3: the decoded stream is as long as the source, within 0.1 s."""
    detail = {}
    for name in RENDITIONS:
        info = ffprobe_json(["-f", "mpegts", "-i", concat_arg(out, name),
                             "-show_entries", "format=duration"])
        got = float(info["format"]["duration"])
        dev = abs(got - SRC_DURATION)
        if dev > DURATION_TOL:
            raise GateFailure(
                "duration",
                f"{name} duration {got:.4f} s deviates {dev:.4f} s from the "
                f"source's {SRC_DURATION:.4f} s (limit {DURATION_TOL} s)")
        detail[name] = {"seconds": round(got, 4), "deviation_s": round(dev, 4)}
    return detail


def check_keyframes(out: Path) -> dict:
    """G4: keyframe gaps of 4 s +- 1 %, measured from the decoded PTS."""
    detail = {}
    for name in RENDITIONS:
        proc = run(["ffprobe", "-v", "error", "-f", "mpegts", "-i",
                    concat_arg(out, name), "-select_streams", "v",
                    "-skip_frame", "nokey", "-show_entries", "frame=pts_time",
                    "-of", "csv=p=0"])
        pts = sorted(float(x.strip().rstrip(",")) for x in proc.stdout.split()
                     if x.strip().rstrip(","))
        gaps = [round(b - a, 4) for a, b in zip(pts, pts[1:])]
        if len(gaps) < MIN_KEYFRAME_GAPS:
            raise GateFailure(
                "keyframes",
                f"{name} has {len(gaps)} keyframe gaps, need at least {MIN_KEYFRAME_GAPS} "
                f"(keyframes at {pts})")
        lo = KEYFRAME_INTERVAL * (1 - KEYFRAME_TOL)
        hi = KEYFRAME_INTERVAL * (1 + KEYFRAME_TOL)
        bad = [g for g in gaps if not lo <= g <= hi]
        if bad:
            raise GateFailure(
                "keyframes",
                f"{name} keyframe gaps {bad} outside {lo:.2f}-{hi:.2f} s "
                f"(4 s +- 1 %)")
        detail[name] = {"keyframes": len(pts), "gaps": gaps,
                        "min_gap": min(gaps), "max_gap": max(gaps)}
    return detail


# --------------------------------------------------------------------------
# G5: decode the source's burned frame counter back out of the renditions
# --------------------------------------------------------------------------
def counter_frames(path: str, w: int, h: int) -> list[bytes]:
    """Every frame's counter band, cropped and scaled for OCR, in one pass.

    Seeking into an HLS rendition is unreliable (the decoder lands on the
    preceding keyframe), so the whole stream is decoded once and the frames
    are indexed by their position in it. 480 frames of 640x360 take under a
    second, and the frame index is exactly what the burned counter encodes.
    """
    fx, fy, fw, fh = COUNTER_BOX
    cw, ch = COUNTER_SCALE
    vf = (f"crop={round(fw * w)}:{round(fh * h)}:{round(fx * w)}:{round(fy * h)},"
          f"scale={cw}:{ch}:flags=neighbor")
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "mpegts", "-i", path, "-vf", vf,
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, timeout=RUN_TIMEOUT)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"could not decode {path}: "
                           f"{proc.stderr.decode(errors='replace').strip()[-300:]}")
    size = cw * ch
    n = len(proc.stdout) // size
    if not n:
        raise RuntimeError(f"decoded no frames from {path}")
    return [proc.stdout[i * size:(i + 1) * size] for i in range(n)]


def counter_template_png(path: Path, digit: str) -> bytes:
    """Render one digit with the fixture's own drawtext settings."""
    font = os.environ.get("FIXTURE_FONT",
                          "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")
    if not os.path.isfile(font):
        raise GateFailure("counter", f"fixture font {font} not found")
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"color=c=black:size={SRC_WIDTH}x{SRC_HEIGHT}:rate=24:duration=1",
         "-vf", f"drawtext=fontfile={font}:text={digit}:x=24:y=290:"
                f"fontsize=48:fontcolor=white",
         "-frames:v", "1", "-vf", f"drawtext=fontfile={font}:text={digit}:x=24:y=290:"
                                  f"fontsize=48:fontcolor=white,"
                                  f"crop={round(COUNTER_BOX[2] * SRC_WIDTH)}:"
                                  f"{round(COUNTER_BOX[3] * SRC_HEIGHT)}:"
                                  f"{round(COUNTER_BOX[0] * SRC_WIDTH)}:"
                                  f"{round(COUNTER_BOX[1] * SRC_HEIGHT)},"
                                  f"scale={COUNTER_SCALE[0]}:{COUNTER_SCALE[1]}:flags=neighbor",
         "-f", "rawvideo", "-pix_fmt", "gray", str(path)])
    return path.read_bytes()


def binarize(buf: bytes, w: int, h: int) -> bytes:
    """Threshold a gray frame into 0x00/0x01 bytes at the mid-range."""
    lo, hi = min(buf), max(buf)
    if hi - lo < 60:
        raise ValueError(f"counter band has no contrast (min={lo} max={hi})")
    thr = lo + (hi - lo) // 2
    return bytes(p > thr for p in buf)


def glyph_boxes(bits: bytes, w: int, h: int) -> list[tuple[int, int, int, int]]:
    """Segment the digit glyphs by columns that contain no ink."""
    on = [x for x in range(w) if bits[x::w].count(1)]
    if not on:
        raise ValueError("counter band is blank")
    boxes, start = [], None
    for x in range(on[0], on[-1] + 2):
        ink = x <= on[-1] and bits[x::w].count(1)
        if ink and start is None:
            start = x
        elif not ink and start is not None:
            boxes.append((start, x))
            start = None
    out = []
    for x0, x1 in boxes:
        if x1 - x0 < 16:
            continue
        ys = [y for y in range(h) if bits[y * w + x0:y * w + x1].count(1)]
        out.append((x0, x1, ys[0], ys[-1] + 1))
    return out


def normalize(bits: bytes, box: tuple[int, int, int, int], w: int) -> list[int]:
    x0, x1, y0, y1 = box
    gw, gh = GLYPH_GRID
    cells = []
    for gy in range(gh):
        sy0 = y0 + (y1 - y0) * gy // gh
        sy1 = max(sy0 + 1, y0 + (y1 - y0) * (gy + 1) // gh)
        for gx in range(gw):
            sx0 = x0 + (x1 - x0) * gx // gw
            sx1 = max(sx0 + 1, x0 + (x1 - x0) * (gx + 1) // gw)
            tot = n = 0
            for y in range(sy0, sy1):
                row = bits[y * w + sx0:y * w + sx1]
                tot += row.count(1)
                n += len(row)
            cells.append(1 if tot * 2 >= n else 0)
    return cells


def templates(fixtures: Path, workdir: Path) -> dict[str, list[int]]:
    """Render each digit with the fixture's own drawtext settings and
    normalise it, so the classifier is built from the same font, size and
    crop the fixture used rather than from a hand-drawn bitmap."""
    cw, ch = COUNTER_SCALE
    out: dict[str, list[int]] = {}
    for d in "0123456789":
        raw = counter_template_png(workdir / f"tpl-{d}.raw", d)
        if len(raw) != cw * ch:
            raise GateFailure("counter", f"template for {d!r} is {len(raw)} bytes, "
                                         f"expected {cw * ch}")
        bits = binarize(raw, cw, ch)
        boxes = glyph_boxes(bits, cw, ch)
        if len(boxes) != 1:
            raise GateFailure("counter", f"template for {d!r} did not segment "
                                         f"cleanly ({len(boxes)} glyphs)")
        out[d] = normalize(bits, boxes[0], cw)
    return out


def read_counter(bits: bytes, tpl: dict[str, list[int]]) -> tuple[str, list[int]]:
    boxes = glyph_boxes(bits, *COUNTER_SCALE)
    if len(boxes) != 5:
        raise ValueError(f"expected 5 digits in the counter, segmented {len(boxes)}")
    digits, dists = [], []
    for box in boxes:
        cells = normalize(bits, box, COUNTER_SCALE[0])
        best, best_d = "?", 10 ** 9
        for d, t in tpl.items():
            dist = sum(1 for a, b in zip(cells, t) if a != b)
            if dist < best_d:
                best, best_d = d, dist
        digits.append(best)
        dists.append(best_d)
    return "".join(digits), dists


def check_counter(out: Path, fixtures: Path, workdir: Path) -> dict:
    """G5: the source's burned counter, read back out of the renditions.

    The counter is a pure function of the frame index, so the expected value
    at each sampled timestamp is analytic: round(t * 24). A dropped segment
    or a duplicated frame shifts every later reading and fails the gate.
    """
    tpl = templates(fixtures, workdir)
    detail: dict[str, dict] = {}
    for name, (w, h) in RENDITIONS.items():
        frames = counter_frames(concat_arg(out, name), w, h)
        # Decode the whole stream first: if the artifact produced fewer
        # frames than the source, that is the failure, not a decoding error.
        n_frames = len(frames)
        if n_frames < SRC_DURATION * SRC_FPS * 0.99:
            raise GateFailure(
                "counter", f"{name} decodes {n_frames} frames, the source has "
                           f"{int(SRC_DURATION * SRC_FPS)}")
        matched, checked, misses = 0, 0, []
        for idx in range(1, n_frames, 12):        # every half second at 24 fps
            checked += 1
            try:
                got, _ = read_counter(binarize(frames[idx], w, h), tpl)
                value = int(got)
            except ValueError as exc:
                misses.append({"frame": idx, "error": str(exc)})
                continue
            if abs(value - idx) <= COUNTER_TOL:
                matched += 1
            else:
                misses.append({"frame": idx, "read": value})
        frac = matched / checked
        if frac < COUNTER_MIN_MATCH:
            raise GateFailure(
                "counter",
                f"{name}: only {matched}/{checked} = {frac:.0%} of sampled frames "
                f"carry the frame number they should (need {COUNTER_MIN_MATCH:.0%}); "
                f"first misses: {misses[:4]}")
        detail[name] = {"frames": n_frames, "samples": checked, "matched": matched,
                        "match_fraction": round(frac, 4), "misses": misses[:4]}
    return detail


# --------------------------------------------------------------------------
# G6: poster
# --------------------------------------------------------------------------
def png_luminance(path: Path) -> tuple[int, int, list[list[int]]]:
    """Decode an 8-bit PNG with the standard library only."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise GateFailure("poster", "poster.png is not a PNG")
    pos, idat, hdr = 8, bytearray(), None
    while pos < len(data):
        if pos + 8 > len(data):
            raise GateFailure("poster", "poster.png is truncated")
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length:
            raise GateFailure("poster", "poster.png is truncated")
        if ctype == b"IHDR":
            hdr = body
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if hdr is None or not idat:
        raise GateFailure("poster", "poster.png has no IHDR/IDAT")
    w, h, depth, colour = (int.from_bytes(hdr[0:4], "big"),
                           int.from_bytes(hdr[4:8], "big"), hdr[8], hdr[9])
    if depth != 8 or colour not in (0, 2, 4, 6):
        raise GateFailure("poster", f"unsupported PNG: depth {depth}, colour type {colour}")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[colour]
    raw = zlib.decompress(bytes(idat))
    stride = w * channels
    if len(raw) < (stride + 1) * h:
        raise GateFailure("poster", "poster.png pixel data is short")
    rows, prev, off = [], bytearray(stride), 0
    for _ in range(h):
        ft = raw[off]
        line = bytearray(raw[off + 1:off + 1 + stride])
        off += 1 + stride
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            x = line[i]
            if ft == 1:
                x += a
            elif ft == 2:
                x += b
            elif ft == 3:
                x += (a + b) // 2
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                x += a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            elif ft != 0:
                raise GateFailure("poster", f"unknown PNG filter {ft}")
            line[i] = x & 0xFF
        rows.append(line)
        prev = line
    luma = []
    for y in range(h):
        row = rows[y]
        out = []
        for x in range(w):
            i = x * channels
            if channels == 1:
                out.append(row[i])
            else:
                r, g, b = row[i], row[i + 1], row[i + 2]
                out.append((299 * r + 587 * g + 114 * b) // 1000)
        luma.append(out)
    return w, h, luma


def check_poster(out: Path) -> dict:
    """G6: exists, big enough, and not a blank frame."""
    path = out / "poster.png"
    if not path.is_file():
        raise GateFailure("poster", "poster.png is missing")
    w, h, luma = png_luminance(path)
    if w < POSTER_MIN_PX or h < POSTER_MIN_PX:
        raise GateFailure("poster", f"poster.png is {w}x{h}, need at least "
                                    f"{POSTER_MIN_PX}x{POSTER_MIN_PX}")
    hist = [0] * 256
    for row in luma:
        for v in row:
            hist[v] += 1
    distinct = sum(1 for c in hist if c)
    distinct_frac = distinct / 256
    background = max(range(256), key=lambda v: hist[v])
    nonmodal = 1 - hist[background] / (w * h)
    centre = luma[h // 2][w // 2]
    if distinct_frac < POSTER_MIN_DISTINCT:
        raise GateFailure("poster", f"poster.png has only {distinct}/256 distinct "
                                    f"luminance values ({distinct_frac:.1%}), "
                                    f"need {POSTER_MIN_DISTINCT:.0%}")
    if nonmodal < POSTER_MIN_NONMODAL:
        raise GateFailure("poster", f"poster.png is {nonmodal:.1%} off its "
                                    f"background value, need {POSTER_MIN_NONMODAL:.0%}")
    if centre == background:
        raise GateFailure("poster", f"poster.png centre pixel luminance {centre} "
                                    f"is the background value -- looks blank")
    return {"width": w, "height": h, "distinct_levels": distinct,
            "distinct_fraction": round(distinct_frac, 4),
            "nonmodal_fraction": round(nonmodal, 4),
            "background_luma": background, "centre_luma": centre}


# --------------------------------------------------------------------------
# G7/G8: captions
# --------------------------------------------------------------------------
CUE_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})", re.M)


def parse_vtt(path: Path) -> tuple[list[tuple[float, float, str]], str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("WEBVTT"):
        raise GateFailure("captions", "captions.vtt does not start with WEBVTT")
    cues = []
    for m in CUE_RE.finditer(text):
        start = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
                 + int(m.group(3)) + int(m.group(4)) / 1000)
        end = (int(m.group(5)) * 3600 + int(m.group(6)) * 60
               + int(m.group(7)) + int(m.group(8)) / 1000)
        # Payload lines are the ones between this timestamp line and the
        # next blank line (whisper.cpp indents them by one space).
        tail = text[m.end():]
        newline = tail.find("\n")
        tail = "" if newline < 0 else tail[newline + 1:]
        payload = []
        for line in tail.splitlines():
            if not line.strip():
                break
            payload.append(line.strip())
        cues.append((start, end, " ".join(payload)))
    return cues, text


def normalize_words(text: str) -> list[str]:
    """Lowercase, drop punctuation, spell out small numbers. Spoken-number
    normalisation is needed because a transcriber may write '5' where the
    transcript says 'five'; both are the same word said aloud."""
    text = text.lower().replace("'", " ")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return [NUM_WORDS.get(w, w) for w in text.split()]


def word_error_rate(ref: str, hyp: str) -> tuple[float, int, int]:
    r, h = normalize_words(ref), normalize_words(hyp)
    if not r:
        raise GateFailure("captions", "the reference transcript is empty")
    prev = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        cur = [i] + [0] * len(h)
        for j in range(1, len(h) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                         prev[j - 1] + (r[i - 1] != h[j - 1]))
        prev = cur
    return prev[len(h)] / len(r), len(r), prev[len(h)]


def check_captions(out: Path, fixtures: Path) -> dict:
    """G7: a real WebVTT that covers the clip; G8: WER against the transcript."""
    path = out / "captions.vtt"
    if not path.is_file():
        raise GateFailure("captions", "captions.vtt is missing")
    cues, text = parse_vtt(path)
    if len(cues) < CAPTION_MIN_CUES:
        raise GateFailure("captions", f"captions.vtt has {len(cues)} cue blocks, "
                                      f"need at least {CAPTION_MIN_CUES}")
    payload = " ".join(c[2] for c in cues).strip()
    if not payload:
        raise GateFailure("captions", "captions.vtt has no cue text")

    speech = float(ffprobe_json(["-i", str(fixtures / "speech.mp3"),
                                 "-show_entries", "format=duration"])["format"]["duration"])
    span = max(c[1] for c in cues) - min(c[0] for c in cues)
    coverage = span / speech
    if coverage < CAPTION_MIN_COVERAGE:
        raise GateFailure("captions", f"captions cover {coverage:.1%} of the "
                                      f"{speech:.2f} s speech clip, need "
                                      f"{CAPTION_MIN_COVERAGE:.0%}")

    # An echo of the transcript file is not a transcription: if the cue text
    # is the transcript verbatim, it must at least be split into real cues.
    transcript = (fixtures / "TRANSCRIPT.txt").read_text().strip()
    echoed = payload.strip() == transcript
    if echoed and len(cues) < 3:
        raise GateFailure("captions", "captions.vtt echoes fixtures/TRANSCRIPT.txt "
                                      "without being segmented into cues")

    wer, n_ref, n_err = word_error_rate(SPEECH_TEXT, payload)
    if wer > WER_LIMIT:
        raise GateFailure("captions", f"caption word error rate {wer:.3f} "
                                      f"({n_err} errors over {n_ref} words) exceeds "
                                      f"the limit {WER_LIMIT}")
    return {"cues": len(cues), "speech_seconds": round(speech, 4),
            "coverage": round(coverage, 4), "wer": round(wer, 4),
            "ref_words": n_ref, "errors": n_err, "echoed_transcript": echoed}


# --------------------------------------------------------------------------
# judge integrity
# --------------------------------------------------------------------------
def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="grade a video-transcode-pipeline artifact")
    ap.add_argument("artifact", help="artifact directory (holding pipeline.sh) or pipeline.sh")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", help="write the verdict JSON here")
    ap.add_argument("--workdir", help="use this directory instead of a temp dir")
    args = ap.parse_args()

    judge_dir = Path(__file__).resolve().parent
    demo_dir = judge_dir.parent
    fixtures = demo_dir / "fixtures"
    artifact = Path(args.artifact).resolve()

    before = tree_hash(judge_dir)
    verdict: dict = {
        "artifact": args.artifact,
        "seed": args.seed,
        "source": {"width": SRC_WIDTH, "height": SRC_HEIGHT, "fps": SRC_FPS,
                   "duration_s": SRC_DURATION},
        "passed": False,
        "gates": {},
    }
    timing: dict = {}
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="vtp-"))
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        if not fixtures.is_dir():
            raise GateFailure("runs", f"fixtures not found at {fixtures}")
        out, elapsed = run_pipeline(artifact, fixtures, workdir, args.seed)
        timing["pipeline_s"] = round(elapsed, 3)
        verdict["gates"]["runs"] = {"passed": True}

        for gate, fn in (("geometry", check_geometry), ("duration", check_duration),
                         ("keyframes", check_keyframes)):
            start = time.monotonic()
            detail = fn(out)
            verdict["gates"][gate] = {"passed": True, **detail}
            timing[f"{gate}_s"] = round(time.monotonic() - start, 3)

        start = time.monotonic()
        verdict["gates"]["counter"] = {"passed": True, **check_counter(out, fixtures, workdir)}
        timing["counter_s"] = round(time.monotonic() - start, 3)

        start = time.monotonic()
        verdict["gates"]["poster"] = {"passed": True, **check_poster(out)}
        timing["poster_s"] = round(time.monotonic() - start, 3)

        start = time.monotonic()
        verdict["gates"]["captions"] = {"passed": True, **check_captions(out, fixtures)}
        timing["captions_s"] = round(time.monotonic() - start, 3)

        verdict["passed"] = True
    except GateFailure as exc:
        verdict["failed_gate"] = exc.gate
        verdict["reason"] = exc.reason
        verdict["gates"].setdefault(exc.gate, {})
        verdict["gates"][exc.gate]["passed"] = False
        verdict["gates"][exc.gate]["reason"] = exc.reason
    except (RuntimeError, subprocess.TimeoutExpired, ValueError, OSError, KeyError) as exc:
        verdict["failed_gate"] = "runs"
        verdict["reason"] = f"{type(exc).__name__}: {exc}"
        verdict["gates"].setdefault("runs", {})
        verdict["gates"]["runs"]["passed"] = False
        verdict["gates"]["runs"]["reason"] = verdict["reason"]
    finally:
        if not args.workdir:
            shutil.rmtree(workdir, ignore_errors=True)

    after = tree_hash(judge_dir)
    verdict["judge_unchanged"] = before == after
    if before != after:
        verdict["passed"] = False
        verdict["failed_gate"] = "integrity"
        verdict["reason"] = "the judge tree changed while grading"

    verdict["timing"] = timing
    ordered = {"artifact": verdict["artifact"], "seed": verdict["seed"],
               "source": verdict["source"], "passed": verdict["passed"]}
    for k in ("failed_gate", "reason"):
        if k in verdict:
            ordered[k] = verdict[k]
    ordered["judge_unchanged"] = verdict["judge_unchanged"]
    ordered["gates"] = verdict["gates"]
    ordered["timing"] = verdict["timing"]
    text = json.dumps(ordered, indent=2, sort_keys=False)
    print(text)
    if args.json:
        Path(args.json).write_text(text + "\n")
    return 0 if ordered["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
