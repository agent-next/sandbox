#!/usr/bin/env python3
"""Machine gate for cookbook demo videos (cookbook/DEMO-STANDARD.md).

Usage:
    python3 video_gate.py <video.mp4> [--json out.json]

Prints a JSON verdict; every check reports its measured value, threshold and
pass flag. Exit status:

    0  every check passed
    1  at least one check failed (see "failed" in the verdict)
    2  the file could not be measured (missing file, ffprobe/ffmpeg error,
       no video stream, unreadable container)

Requirements: Python 3.10+ standard library, ffmpeg and ffprobe on PATH.

How things are measured (calibrated on generated fixtures; see
test_video_gate.py):

* container/codec: ffprobe JSON on the first video stream.
* faststart: top-level MP4 atom walk; moov must start before mdat.
* first frame: frame 0 decoded to gray rawvideo; luma mean/std/spread are
  computed over its pixels. signalstats exposes YAVG but no luma standard
  deviation, so the raw pixels are used for all three (the mean matches
  signalstats YAVG on the same frame).
* scene cuts: ffmpeg select='gt(scene,0.3)' + showinfo; one pts_time line per
  selected frame. A solid colour yields zero lines, so the rate is 0/min.
* end card: mean signalstats YDIF (frame-to-frame luma difference) over the
  final 2 s. Calibration: static tail 0.000-0.0002, committed demo tails
  0.000-0.0002, continuously moving tail ~1.9, a cut inside the window ~1.7;
  the threshold 0.5 sits in the empty band between static and moving.
* audio: optional; reported, never fails.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import struct
import subprocess
import sys

# --- thresholds (single source of truth; tests import this module) ----------
MIN_WIDTH = 1920
MIN_HEIGHT = 1080
ASPECT_TARGET = 16 / 9
ASPECT_TOLERANCE = 0.01  # relative, i.e. 16:9 +/- 1 %
MIN_DURATION_S = 25.0
MAX_DURATION_S = 60.0
FPS_MIN = 29.969  # covers NTSC 30000/1001 = 29.97003
FPS_MAX = 30.001  # covers 30/1
EXPECTED_CODEC = "h264"
EXPECTED_PIX_FMT = "yuv420p"
MAX_SIZE_BYTES = 8 * 1024 * 1024  # the standard's "under 8 MB"
FIRST_FRAME_MIN_LUMA_MEAN = 20.0
FIRST_FRAME_MIN_LUMA_STD = 12.0
FIRST_FRAME_MIN_SPREAD = 8.0  # luma max-min; a solid colour has spread 0
SCENE_CUT_MIN_PER_10S = 0.8
END_WINDOW_S = 2.0
ENDCARD_MAX_MEAN_YDIF = 0.5


class GateError(Exception):
    """The file could not be measured; the gate exits 2."""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run cmd, capturing bytes (pixel output is not valid UTF-8)."""
    try:
        return subprocess.run(cmd, capture_output=True)
    except FileNotFoundError as exc:  # pragma: no cover - depends on PATH
        raise GateError(f"{cmd[0]} not found on PATH") from exc


def _text(blob: bytes | None) -> str:
    return (blob or b"").decode("utf-8", errors="replace")


# --- probe -------------------------------------------------------------------


def probe(path: str) -> dict:
    """Return the merged ffprobe JSON for the first video stream + format."""
    proc = _run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", path,
        ]
    )
    if proc.returncode != 0:
        raise GateError(
            f"ffprobe failed: {_text(proc.stderr).strip()[:400]}"
        )
    try:
        data = json.loads(_text(proc.stdout))
    except json.JSONDecodeError as exc:
        raise GateError(f"ffprobe returned invalid JSON: {exc}") from exc
    streams = [
        s for s in data.get("streams", []) if s.get("codec_type") == "video"
    ]
    if not streams:
        raise GateError("no video stream found")
    return {"video": streams[0], "audio_present": any(
        s.get("codec_type") == "audio" for s in data.get("streams", [])
    ), "format": data.get("format", {})}


def _ratio(text: str | None) -> float | None:
    """'30/1' -> 30.0; '0/0' or absent -> None."""
    if not text or "/" not in text:
        return None
    num, _, den = text.partition("/")
    try:
        num_f, den_f = float(num), float(den)
    except ValueError:
        return None
    if den_f == 0 or num_f == 0:
        return None
    return num_f / den_f


def duration_of(info: dict) -> float:
    for source in (info["video"], info["format"]):
        try:
            value = source.get("duration")
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    raise GateError("no duration reported")


def fps_of(info: dict) -> float:
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = _ratio(info["video"].get(key))
        if value:
            return value
    raise GateError("no frame rate reported")


def display_aspect(info: dict) -> float:
    sar = _ratio(info["video"].get("sample_aspect_ratio")) or 1.0
    return (info["video"]["width"] * sar) / info["video"]["height"]


def atom_offsets(path: str, wanted: set[str]) -> dict[str, int]:
    """Offsets of top-level MP4 atoms by walking size/type headers."""
    offsets: dict[str, int] = {}
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        pos = 0
        while pos < size:
            fh.seek(pos)
            header = fh.read(8)
            if len(header) < 8:
                break
            atom_size, atom_type_raw = struct.unpack(">I4s", header)
            atom_type = atom_type_raw.decode("latin-1")
            header_len = 8
            if atom_size == 1:  # 64-bit extended size
                ext = fh.read(8)
                if len(ext) < 8:
                    break
                atom_size = struct.unpack(">Q", ext)[0]
                header_len = 16
            elif atom_size == 0:  # extends to end of file
                atom_size = size - pos
            if atom_size < header_len or pos + atom_size > size:
                break  # malformed; stop walking
            if atom_type in wanted and atom_type not in offsets:
                offsets[atom_type] = pos  # atom start
            pos += atom_size
    return offsets


# --- pixel measurements -------------------------------------------------------


def first_frame_luma(path: str) -> tuple[float, float, float]:
    """(mean, std, max-min) of frame 0 luma, decoded to gray rawvideo."""
    proc = _run(
        [
            "ffmpeg", "-v", "error", "-i", path,
            "-vf", "select='eq(n,0)'", "-frames:v", "1",
            "-f", "rawvideo", "-pix_fmt", "gray", "-",
        ]
    )
    if proc.returncode != 0 or not proc.stdout:
        raise GateError(
            f"could not decode frame 0: {_text(proc.stderr).strip()[:400]}"
        )
    pixels = list(proc.stdout)
    mean = statistics.mean(pixels)
    std = statistics.pstdev(pixels)
    return mean, std, max(pixels) - min(pixels)


def count_scene_cuts(path: str) -> int:
    """Frames selected by select='gt(scene,0.3)' (one showinfo line each)."""
    proc = _run(
        [
            "ffmpeg", "-v", "info", "-i", path,
            "-vf", "select='gt(scene,0.3)',showinfo", "-f", "null", "-",
        ]
    )
    if proc.returncode != 0:
        raise GateError(
            f"scene detection failed: {_text(proc.stderr).strip()[:400]}"
        )
    text = _text(proc.stdout) + _text(proc.stderr)
    return len(
        re.findall(r"Parsed_showinfo.*pts_time:\d+(?:\.\d+)?", text)
    )


def endcard_mean_ydif(path: str, duration: float) -> float:
    """Mean signalstats YDIF over the final END_WINDOW_S seconds."""
    start = max(0.0, duration - END_WINDOW_S)
    proc = _run(
        [
            "ffmpeg", "-v", "info", "-ss", f"{start:.3f}", "-i", path,
            "-vf", "signalstats,metadata=print:file=-", "-f", "null", "-",
        ]
    )
    if proc.returncode != 0:
        raise GateError(
            f"end-card measurement failed: {_text(proc.stderr).strip()[:400]}"
        )
    values = [
        float(line.rsplit("=", 1)[1])
        for line in (_text(proc.stdout) + _text(proc.stderr)).splitlines()
        if "lavfi.signalstats.YDIF" in line
    ]
    if not values:
        raise GateError("no YDIF frames measured in the end window")
    return statistics.mean(values)


# --- verdict ------------------------------------------------------------------


def _check(name: str, measured, threshold: str, ok: bool) -> dict:
    return {
        "name": name,
        "measured": round(measured, 4) if isinstance(measured, float) else measured,
        "threshold": threshold,
        "pass": bool(ok),
    }


def judge(path: str) -> dict:
    """Run every check on path and return the verdict dict."""
    checks: list[dict] = []
    info = probe(path)
    video = info["video"]

    width = video.get("width") or 0
    height = video.get("height") or 0
    checks.append(_check("width", width, f">= {MIN_WIDTH}", width >= MIN_WIDTH))
    checks.append(
        _check("height", height, f">= {MIN_HEIGHT}", height >= MIN_HEIGHT)
    )
    dar = display_aspect(info)
    checks.append(
        _check(
            "aspect_ratio",
            dar,
            f"16:9 +/- {ASPECT_TOLERANCE:.0%}",
            abs(dar / ASPECT_TARGET - 1) <= ASPECT_TOLERANCE,
        )
    )

    duration = duration_of(info)
    checks.append(
        _check(
            "duration_s",
            duration,
            f"{MIN_DURATION_S:g}-{MAX_DURATION_S:g} s",
            MIN_DURATION_S <= duration <= MAX_DURATION_S,
        )
    )

    fps = fps_of(info)
    checks.append(
        _check(
            "fps",
            fps,
            f"{FPS_MIN:g}-{FPS_MAX:g}",
            FPS_MIN <= fps <= FPS_MAX,
        )
    )

    codec = video.get("codec_name") or ""
    checks.append(
        _check("codec", codec, f"== {EXPECTED_CODEC}", codec == EXPECTED_CODEC)
    )
    pix_fmt = video.get("pix_fmt") or ""
    checks.append(
        _check(
            "pix_fmt",
            pix_fmt,
            f"== {EXPECTED_PIX_FMT}",
            pix_fmt == EXPECTED_PIX_FMT,
        )
    )

    size = os.path.getsize(path)
    checks.append(
        _check(
            "size_mib",
            size / (1024 * 1024),
            f"<= {MAX_SIZE_BYTES / (1024 * 1024):g} MiB",
            size <= MAX_SIZE_BYTES,
        )
    )

    offsets = atom_offsets(path, {"moov", "mdat"})
    faststart_ok = "moov" in offsets and "mdat" in offsets and (
        offsets["moov"] < offsets["mdat"]
    )
    measured_order = (
        f"moov@{offsets.get('moov')} mdat@{offsets.get('mdat')}"
        if offsets
        else "no top-level atoms found"
    )
    checks.append(
        _check(
            "faststart",
            measured_order,
            "moov atom before mdat",
            faststart_ok,
        )
    )

    luma_mean, luma_std, spread = first_frame_luma(path)
    checks.append(
        _check(
            "first_frame_luma_mean",
            luma_mean,
            f">= {FIRST_FRAME_MIN_LUMA_MEAN:g}",
            luma_mean >= FIRST_FRAME_MIN_LUMA_MEAN,
        )
    )
    checks.append(
        _check(
            "first_frame_luma_std",
            luma_std,
            f">= {FIRST_FRAME_MIN_LUMA_STD:g}",
            luma_std >= FIRST_FRAME_MIN_LUMA_STD,
        )
    )
    checks.append(
        _check(
            "first_frame_not_solid",
            spread,
            f">= {FIRST_FRAME_MIN_SPREAD:g} (luma max-min)",
            spread >= FIRST_FRAME_MIN_SPREAD,
        )
    )

    cuts = count_scene_cuts(path)
    cut_rate = cuts / duration * 10 if duration > 0 else 0.0
    checks.append(
        _check(
            "scene_cuts_per_10s",
            cut_rate,
            f">= {SCENE_CUT_MIN_PER_10S:g}",
            cut_rate >= SCENE_CUT_MIN_PER_10S,
        )
    )

    mean_ydif = endcard_mean_ydif(path, duration)
    checks.append(
        _check(
            "endcard_static",
            mean_ydif,
            f"<= {ENDCARD_MAX_MEAN_YDIF:g} (mean YDIF, last {END_WINDOW_S:g} s)",
            mean_ydif <= ENDCARD_MAX_MEAN_YDIF,
        )
    )

    checks.append(
        _check(
            "audio",  # optional: reported, never fails
            "present" if info["audio_present"] else "absent",
            "optional",
            True,
        )
    )

    failed = [c["name"] for c in checks if not c["pass"]]
    return {
        "file": os.path.basename(path),
        "passed": not failed,
        "failed": failed,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate a cookbook demo video against cookbook/DEMO-STANDARD.md."
    )
    parser.add_argument("video", help="path to the .mp4 to judge")
    parser.add_argument(
        "--json", metavar="OUT", help="also write the verdict JSON to OUT"
    )
    args = parser.parse_args(argv)

    if not os.path.isfile(args.video):
        print(
            json.dumps({"file": args.video, "error": "file not found"}),
            file=sys.stdout,
        )
        return 2
    try:
        verdict = judge(args.video)
    except GateError as exc:
        print(
            json.dumps({"file": args.video, "error": str(exc)}), file=sys.stdout
        )
        return 2

    print(json.dumps(verdict, indent=2))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(verdict, fh, indent=2)
            fh.write("\n")
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
