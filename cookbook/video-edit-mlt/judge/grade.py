#!/usr/bin/env python3
"""Independent pixel/PCM oracle. Only render() calls MLT."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import edl
from security import validate

JDIR = Path(__file__).resolve().parent
DEMO = JDIR.parent
TOOLS = Path.home() / ".local/video-edit-mlt/Shotcut.app"
FFMPEG, FFPROBE, MELT = (str(TOOLS / t) for t in ("ffmpeg", "ffprobe", "melt"))
os.environ.update(QT_QPA_PLATFORM="offscreen", OMP_NUM_THREADS="1",
                  OPENBLAS_NUM_THREADS="1", LC_ALL="C")


def command(argv, **kw):
    return subprocess.run(argv, check=True, capture_output=True, timeout=180, **kw)


def checksums():
    return {str(p.relative_to(JDIR)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(JDIR.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def probe(path):
    return json.loads(command([FFPROBE, "-v", "error", "-count_frames",
                               "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)


def frames(path, width=1280, height=720):
    """Bounded-memory decode, with errors and partial frames rejected."""
    p = subprocess.Popen([FFMPEG, "-v", "error", "-threads", "1", "-i", str(path),
                          "-an", "-threads", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        while True:
            raw = p.stdout.read(width * height * 3)
            if not raw:
                break
            if len(raw) != width * height * 3:
                raise ValueError("partial decoded frame")
            yield np.frombuffer(raw, np.uint8).reshape(height, width, 3)
        err = p.stderr.read()
        if p.wait(timeout=30):
            raise ValueError("ffmpeg decode failed: " + err.decode()[-300:])
    finally:
        if p.poll() is None:
            p.kill()
        p.wait()
        p.stdout.close()
        p.stderr.close()


def band_means(frame):
    return np.array([frame[18:38, 30 + 80*i:50 + 80*i, :].mean()
                     for i in range(16)])


def logo_score(rgb, template):
    """Zero-mean normalized correlation; uniform backgrounds score zero."""
    a = rgb.astype(float).ravel()
    b = template.astype(float).ravel()
    a -= a.mean()
    b -= b.mean()
    den = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / den) if den > 1e-9 else 0.0


def render(root, work):
    shutil.copytree(DEMO / "assets", work / "assets")
    # The XML lives beside assets. Never preserve the artifact's root/cwd.
    root.set("root", str(work))
    ET.ElementTree(root).write(work / "edit.mlt", encoding="utf-8", xml_declaration=True)
    command([MELT, "-quiet", "edit.mlt", "-consumer", "avformat:out.mp4",
             "vcodec=libx264", "acodec=aac", "crf=18", "preset=fast",
             "pix_fmt=yuv420p", "ar=48000", "ac=2", "threads=1",
             "real_time=-1", "movflags=+faststart"], cwd=work)
    return work / "out.mp4"


def grade(artifact, spec, seed, export=None):
    start = time.monotonic()
    before = checksums()
    gates = {}
    verdict = {"schema": "video-edit-mlt/verdict@1", "seed": seed,
               "passed": False, "verdict": "FAIL", "gates": gates}

    def gate(name, ok, measured, threshold, **details):
        gates[name] = {"pass": bool(ok), "measured": measured,
                       "threshold": threshold, **details}

    try:
        try:
            root = validate(artifact.read_bytes())
            gate("security", True, 0, "0 unsafe XML constructs")
        except (ValueError, ET.ParseError) as exc:
            gate("security", False, 1, "0 unsafe XML constructs", reason=str(exc))
            return verdict
        refs, bands, power_bad, count = {}, {}, 0, 0
        for name, source in spec["sources"].items():
            cid = source["clip_id"]
            bands[cid] = []
            n = 0
            for n, f in enumerate(frames(DEMO / source["file"]), 1):
                decoded = edl.decode_band(f[8:48].tobytes())
                power_bad += decoded != (cid, n-1)
                bands[cid].append(band_means(f))
                if n == 1:
                    refs[cid] = f[100:200, 500:700].mean(axis=(0, 1)).tolist()
                count += 1
            power_bad += abs(n - source["frames"])
        gate("power", power_bad == 0, power_bad, "0 barcode errors across 450 raw frames",
             frames=count)
        if power_bad:
            return verdict
        with tempfile.TemporaryDirectory(prefix="video-edit-") as tmp:
            work = Path(tmp)
            out = render(root, work)
            info = probe(out)
            video = next(s for s in info["streams"] if s["codec_type"] == "video")
            audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), {})
            fmt = spec["format"]
            measured = {k: video.get(k) for k in
                        ("codec_name", "width", "height", "r_frame_rate", "nb_read_frames",
                         "sample_aspect_ratio", "field_order", "pix_fmt")}
            measured["audio"] = {k: audio.get(k) for k in
                                 ("codec_name", "sample_rate", "channels")}
            format_ok = (video["codec_name"] == fmt["vcodec"] and
                         video["width"] == fmt["width"] and video["height"] == fmt["height"] and
                         video["r_frame_rate"] == f'{fmt["fps_num"]}/{fmt["fps_den"]}' and
                         int(video.get("nb_read_frames", 0)) == fmt["frames"] and
                         video.get("sample_aspect_ratio") == "1:1" and
                         video.get("field_order") == "progressive" and
                         audio.get("codec_name") == fmt["acodec"] and
                         int(audio.get("sample_rate", 0)) == fmt["sample_rate"] and
                         audio.get("channels") == fmt["channels"] and
                         "mp4" in info["format"]["format_name"])
            gate("format", format_ok, measured, fmt)
            if not format_ok:
                return verdict
            template = next(frames(DEMO / spec["logo"]["file"], 160, 80))
            decoded, colours, output_bands, scores = [], [], [], []
            x, y, w, h = spec["logo"]["rect"]
            for f in frames(out):
                decoded.append(edl.decode_band(f[8:48].tobytes()))
                colours.append(f[100:200, 500:700].mean(axis=(0, 1)).tolist())
                output_bands.append(band_means(f))
                scores.append(logo_score(f[y:y+h, x:x+w], template))
            expect = edl.expected_frames(spec)
            mismatches = edl.compare_edl(decoded, colours, expect, refs)
            weights, blend_errors = [], []
            for i, exp in enumerate(expect):
                if exp[0] != "blend":
                    continue
                weight = edl.blend_weight(colours[i], refs[0], refs[1])
                weights.append(weight)
                seg = next(s for s in spec["edl"] if "blend" in s)
                t = exp[1]
                reference = ((1-weight)*bands[0][seg["blend"]["a_in"]+t] +
                             weight*bands[1][seg["blend"]["b_in"]+t])
                error = float(np.max(np.abs(output_bands[i] - reference))) / 255
                blend_errors.append(error)
                if error > 0.12:
                    mismatches.append(f"frame {i}: blended barcode residual {error:.4f}")
            gate("edl", not mismatches, len(mismatches), "0 mismatched output frames",
                 checked_frames=len(decoded), errors=mismatches[:8],
                 blend_barcode_max_error=round(max(blend_errors), 6),
                 blend_barcode_limit=0.12)
            dissolve_bad = edl.check_dissolve(weights)
            ramp_error = max(abs(w - t/24) for t, w in enumerate(weights))
            gate("dissolve", not dissolve_bad, round(ramp_error, 6),
                 "max ramp error <=0.20; endpoints <=0.15 and >=0.85; decrease <=0.05",
                 weights=[round(w, 6) for w in weights], errors=dissolve_bad)
            lo, hi = spec["logo"]["frames"]
            on = min(scores[lo:hi+1])
            off = max(scores[:lo]+scores[hi+1:])
            gate("logo", on >= 0.85 and off < 0.30,
                 {"min_on": round(on, 6), "max_off": round(off, 6)},
                 "on >=0.85, off <0.30 on every frame")
            ebu = command([FFMPEG, "-v", "info", "-i", str(out), "-vn",
                           "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr.decode()
            summary = ebu[ebu.rfind("Summary:"):]
            lufs = float(re.search(r"I:\s*([-\d.]+) LUFS", summary)[1])
            peak = float(re.search(r"Peak:\s*([-\d.]+) dBFS", summary)[1])
            a = spec["audio"]
            gate("loudness", abs(lufs-a["lufs"]) <= a["lufs_tol"] and peak <= a["true_peak_dbtp"],
                 {"integrated_lufs": lufs, "true_peak_dbtp": peak},
                 {"lufs": [a["lufs"]-a["lufs_tol"], a["lufs"]+a["lufs_tol"]],
                  "true_peak_max_dbtp": a["true_peak_dbtp"]})
            # Narrow-band projection avoids a speech harmonic or broad-band
            # RMS being mistaken for music. 100 ms windows are exactly 22 cycles.
            pcm = np.frombuffer(command([FFMPEG, "-v", "error", "-i", str(out),
                                         "-vn", "-ac", "1", "-ar", "48000",
                                         "-f", "f32le", "-"]).stdout, dtype="<f4")
            t = np.arange(4800) / 48000
            carrier = np.exp(-2j*np.pi*a["music_hz"]*t)
            inside, outside = [], []
            per_window = [[] for _ in a["voice_windows"]]
            for i in range(0, len(pcm)-4799, 4800):
                mid = (i+2400)/48000
                amp = float(abs(pcm[i:i+4800] @ carrier)*2/4800/math.sqrt(2))
                if any(l+0.1 <= mid <= h-0.1 for l, h in a["voice_windows"]):
                    inside.append(amp)
                    for j, (l, h) in enumerate(a["voice_windows"]):
                        if l+0.1 <= mid <= h-0.1:
                            per_window[j].append(amp)
                elif all(not l-0.1 <= mid <= h+0.1 for l, h in a["voice_windows"]):
                    outside.append(amp)
            rms_in = float(np.sqrt(np.mean(np.square(inside))))
            rms_out = float(np.sqrt(np.mean(np.square(outside))))
            depths = [20*math.log10(max(rms_out, 1e-12) /
                      max(float(np.sqrt(np.mean(np.square(values)))), 1e-12))
                      for values in per_window]
            depth = min(depths)
            gate("ducking", depth >= a["duck_db"] and rms_out > 1e-5,
                 round(depth, 6), f'>={a["duck_db"]} dB; outside music RMS >1e-5',
                 rms_inside=round(rms_in, 8), rms_outside=round(rms_out, 8),
                 window_depths_db=[round(d, 6) for d in depths])
            if export:
                export.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(out, export / "render.mp4")
                (export / "frames.json").write_text(json.dumps({
                    "decoded": decoded, "colours": colours, "logo_scores": scores,
                    "weights": weights, "music_inside": inside, "music_outside": outside},
                    indent=1) + "\n")
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as exc:
        gate("execution", False, 1, "0 render/decode errors", reason=str(exc)[-500:])
    finally:
        intact = before == checksums()
        gate("integrity", intact, int(not intact), "0 changed judge files")
        verdict["passed"] = all(g["pass"] for g in gates.values()) and len(gates) == 9
        verdict["verdict"] = "PASS" if verdict["passed"] else "FAIL"
        verdict["failed_gate"] = next((n for n, g in gates.items() if not g["pass"]), None)
        verdict["timing"] = {"total_s": round(time.monotonic()-start, 3)}
    return verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", type=Path)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--export", type=Path, help="save render + per-frame measurements for media")
    args = ap.parse_args()
    v = grade(args.artifact, json.loads((DEMO / "spec.json").read_text()), args.seed, args.export)
    text = json.dumps(v, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.json:
        args.json.write_text(text)
    print(text, end="")
    return 0 if v["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
