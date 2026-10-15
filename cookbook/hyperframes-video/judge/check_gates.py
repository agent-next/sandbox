#!/usr/bin/env python3
"""check_gates.py — run every judge gate on an artifact copy.

Usage: check_gates.py <artifact_dir> --json out.json

The artifact is a scratch copy made by grade.sh (committed files are never
touched).  This script renders the composition twice with the pinned
HyperFrames toolchain, measures everything itself (ffprobe/ffmpeg frames,
tesseract OCR), and writes one JSON verdict.

Every measured number written to the verdict is quantised on a documented
grid: HyperFrames is not byte-deterministic (documented in SPEC.md gate 6),
so raw measurements would differ between two grades of equivalent renders.
The quantisation step for each metric is far larger than encoder noise and
far smaller than the pass threshold, so a verdict is byte-identical across
grades of equivalent renders while still reporting what was measured.
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GSAP_VENDOR = os.path.join(SCRIPT_DIR, "vendor", "gsap.min.js")
RENDER_TIMEOUT = 900          # gate 1: render must finish within 15 min
OCR_THRESHOLD = 0.9           # gate 3: char-3gram containment
BLACK_MAX_S = 0.5             # gate 4
FREEZE_MAX_S = 2.0            # gate 4
DE_MAX = 25.0                 # gate 5: CIE76 delta-E
BRAND_MIN_PCT = 1.0           # gate 5: % of frame pixels within DE_MAX
SSIM_MIN = 0.995              # gate 6
PSNR_MIN = 40.0               # gate 6


def log(msg):
    print("[gates] %s" % msg, flush=True)


def run(cmd, timeout=None, env=None):
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, env=env)


# ---------------------------------------------------------------------------
# spec.json validation (SPEC.md "Rules the artifact must satisfy")
# ---------------------------------------------------------------------------

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def fail_spec(problems):
    return problems


def validate_spec(spec):
    p = []
    if not isinstance(spec, dict):
        return ["spec.json is not a JSON object"]
    dur = spec.get("duration_s")
    if not isinstance(dur, (int, float)) or not (20 <= dur <= 30):
        p.append("duration_s must be a number in [20, 30]")
    w, h = spec.get("width"), spec.get("height")
    if not isinstance(w, int) or not (320 <= w <= 7680):
        p.append("width must be an int in [320, 7680]")
    if not isinstance(h, int) or not (320 <= h <= 4320):
        p.append("height must be an int in [320, 4320]")
    if spec.get("fps") not in (24, 30, 60):
        p.append("fps must be one of 24, 30, 60")
    bc = spec.get("brand_colors")
    if not isinstance(bc, list) or not (1 <= len(bc) <= 4) \
            or not all(isinstance(c, str) and HEX_RE.match(c) for c in bc):
        p.append("brand_colors must be 1-4 '#RRGGBB' strings")
    beats = spec.get("beats")
    if not isinstance(beats, list) or len(beats) < 1:
        p.append("beats must be a non-empty list")
    else:
        prev_end = -1.0
        for i, b in enumerate(beats):
            if not isinstance(b, dict):
                p.append("beats[%d] is not an object" % i)
                continue
            for k in ("label", "text", "start_s", "hold_s"):
                if k not in b:
                    p.append("beats[%d] missing '%s'" % (i, k))
            s, hd = b.get("start_s"), b.get("hold_s")
            if not isinstance(s, (int, float)) or not isinstance(hd, (int, float)) or hd <= 0:
                p.append("beats[%d] start_s/hold_s must be numbers, hold_s > 0" % i)
                continue
            if s < prev_end - 1e-9:
                p.append("beats[%d] overlaps the previous beat" % i)
            if isinstance(dur, (int, float)) and s + hd > dur + 1e-9:
                p.append("beats[%d] extends past duration_s" % i)
            if not isinstance(b.get("text"), str) or not b["text"].strip():
                p.append("beats[%d] text must be a non-empty string" % i)
            prev_end = s + hd
    return p


REMOTE_RE = re.compile(
    r"(?:src|href)\s*=\s*[\"']https?://"
    r"|url\(\s*[\"']?https?://"
    r"|fetch\(\s*[\"']https?://"
    r"|import\s*\(\s*[\"']https?://"
    r"|@import\s+[\"']https?://"
    r"|XMLHttpRequest"
    r"|new\s+WebSocket", re.I)


def validate_composition(comp_dir, dur):
    """Return a list of validation problems (empty = valid)."""
    p = []
    index = os.path.join(comp_dir, "index.html")
    if not os.path.isfile(index):
        return ["composition/index.html is missing"]
    html = open(index, encoding="utf-8", errors="replace").read()
    if "data-composition-id" not in html:
        p.append("no element declares data-composition-id")
    if not re.search(r'data-start\s*=\s*["\']?0(?:\.0+)?["\']?', html):
        p.append("stage does not declare data-start=0")
    m = re.search(r'data-duration\s*=\s*["\']?([0-9]+(?:\.[0-9]+)?)', html)
    if not m:
        p.append("stage does not declare data-duration")
    elif abs(float(m.group(1)) - float(dur)) > 1e-6:
        p.append("stage data-duration %s != spec duration_s %s"
                 % (m.group(1), dur))
    for root, _dirs, files in os.walk(comp_dir):
        for f in files:
            fp = os.path.join(root, f)
            try:
                body = open(fp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if REMOTE_RE.search(body):
                p.append("remote reference in %s — compositions must be "
                         "self-contained (vendor assets instead)" % f)
    return p


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def hyperframes_cmd():
    node = os.environ.get("HF_NODE", "node")
    hf = os.environ.get("HYPERFRAMES_BIN")
    if hf and os.path.isfile(hf):
        return [node, hf]
    return ["hyperframes"]


def render(comp_dir, out_mp4, fps, rlog):
    cmd = hyperframes_cmd() + ["render", comp_dir, "-o", out_mp4,
                               "-f", str(fps), "-w", "2"]
    try:
        p = run(cmd, timeout=RENDER_TIMEOUT)
    except subprocess.TimeoutExpired:
        rlog.write("%s\nTIMED OUT after %ds\n" % (" ".join(cmd), RENDER_TIMEOUT))
        return False, "render timed out after %ds" % RENDER_TIMEOUT
    rlog.write("$ %s\n%s\n%s\n(exit %d)\n"
               % (" ".join(cmd), p.stdout[-4000:], p.stderr[-4000:],
                  p.returncode))
    if p.returncode != 0:
        tail = (p.stdout + p.stderr).strip().splitlines()
        return False, "render exited %d: %s" % (
            p.returncode, tail[-1][:200] if tail else "no output")
    if not os.path.isfile(out_mp4) or os.path.getsize(out_mp4) == 0:
        return False, "render exited 0 but produced no output.mp4"
    return True, ""


# ---------------------------------------------------------------------------
# measurement helpers
# ---------------------------------------------------------------------------

def ffprobe_json(mp4):
    p = run(["ffprobe", "-v", "error", "-print_format", "json",
             "-show_streams", "-show_format", mp4])
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return None


def grab_frame_rgb(mp4, t, w, h):
    """Raw rgb24 bytes of the frame nearest to t (fast seek before -i)."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", mp4,
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    if p.returncode != 0 or len(p.stdout) != w * h * 3:
        return None
    return p.stdout


def write_pgm(path, w, h, gray):
    with open(path, "wb") as f:
        f.write(b"P5\n%d %d\n255\n" % (w, h))
        f.write(gray)


def ocr_file(path):
    p = run(["tesseract", path, "stdout", "-l", "eng"])
    return p.stdout if p.returncode == 0 else ""


def norm_text(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


def trigrams(s):
    s = norm_text(s)
    if len(s) <= 3:
        return {s} if s else set()
    return {s[i:i + 3] for i in range(len(s) - 2)}


def containment(beat_text, ocr_text):
    """|grams(beat) ∩ grams(ocr)| / |grams(beat)| — extra on-screen text
    (e.g. an end card repeating the product name) must not dilute the
    match, so the denominator is the beat's grams only."""
    want = trigrams(beat_text)
    if not want:
        return 0.0
    have = trigrams(ocr_text)
    return len(want & have) / len(want)


def q_step(x, step):
    """Quantise x to the nearest multiple of step (verdict determinism)."""
    return round(round(x / step) * step, 6)


# CIE76 delta-E ---------------------------------------------------------------

def _srgb_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _f_lab(t):
    return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0


def rgb2lab(r, g, b):
    rl, gl, bl = _srgb_lin(r), _srgb_lin(g), _srgb_lin(b)
    x = (0.4124 * rl + 0.3576 * gl + 0.1805 * bl) / 0.95047
    y = 0.2126 * rl + 0.7152 * gl + 0.0722 * bl
    z = (0.0193 * rl + 0.1192 * gl + 0.9505 * bl) / 1.08883
    fx, fy, fz = _f_lab(x), _f_lab(y), _f_lab(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def brand_share(rgb, w, h, lab):
    """Share of pixels within DE_MAX of brand colour `lab` (CIE76)."""
    l1, a1, b1 = lab
    n = w * h
    hits = 0
    lim = DE_MAX * DE_MAX
    for i in range(0, n * 3, 3):
        l2, a2, b2 = rgb2lab(rgb[i], rgb[i + 1], rgb[i + 2])
        d2 = (l2 - l1) ** 2 + (a2 - a1) ** 2 + (b2 - b1) ** 2
        if d2 <= lim:
            hits += 1
    return 100.0 * hits / n


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if not args:
        print("usage: check_gates.py <artifact_dir> [--json out.json]",
              file=sys.stderr)
        return 2
    artifact = os.path.abspath(args[0])
    json_out = None
    if "--json" in args:
        json_out = os.path.abspath(args[args.index("--json") + 1])

    gates = []
    # The artifact path here is a per-grade mktemp dir (grade.sh), not user
    # content — record only its basename so two same-seed grades give
    # byte-identical verdict JSON (DEMO-STANDARD.md "Deterministic").
    verdict = {"artifact": os.path.basename(artifact),
               "gates": gates, "all_gates_passed": False}

    def gate(num, name, passed, detail):
        gates.append({"gate": num, "name": name, "passed": bool(passed),
                      "detail": detail})
        log("gate %d %-34s %s  %s" % (num, name,
                                      "PASS" if passed else "FAIL",
                                      json.dumps(detail)[:240]))

    def finish():
        verdict["all_gates_passed"] = all(g["passed"] for g in gates) \
            and len(gates) >= 6
        if json_out:
            with open(json_out, "w") as f:
                json.dump(verdict, f, indent=2)
                f.write("\n")
        return 0 if verdict["all_gates_passed"] else 1

    work = tempfile.mkdtemp(prefix="hf-gates-")
    rlog = open(os.path.join(work, "render.log"), "w")

    # -- input validation ----------------------------------------------------
    spec_path = os.path.join(artifact, "spec.json")
    comp_dir = os.path.join(artifact, "composition")
    problems = []
    if not os.path.isfile(spec_path):
        problems.append("spec.json is missing")
        spec = None
    else:
        try:
            spec = json.load(open(spec_path))
        except json.JSONDecodeError as e:
            problems.append("spec.json is not valid JSON: %s" % e)
            spec = None
    if spec is not None:
        problems += validate_spec(spec)
    if spec is not None and isinstance(spec, dict):
        problems += validate_composition(comp_dir, spec.get("duration_s", 0))
    elif not os.path.isdir(comp_dir):
        problems.append("composition/ is missing")

    if problems:
        gate(0, "input-validation", False, {"problems": problems})
        for n, nm in ((1, "render"), (2, "container-format"),
                      (3, "beat-text-ocr"), (4, "no-black-no-freeze"),
                      (5, "brand-colors"), (6, "determinism")):
            gate(n, nm, False, {"skipped": "input invalid"})
        rlog.close()
        shutil.rmtree(work, ignore_errors=True)
        return finish()
    gate(0, "input-validation", True, {"checked": len(problems)})

    dur = float(spec["duration_s"])
    w, h, fps = spec["width"], spec["height"], spec["fps"]

    # vendored gsap next to index.html in the scratch copy
    shutil.copy2(GSAP_VENDOR, os.path.join(comp_dir, "gsap.min.js"))

    # -- gate 1: render --------------------------------------------------------
    out1 = os.path.join(work, "render1.mp4")
    ok, why = render(comp_dir, out1, fps, rlog)
    gate(1, "render", ok,
         {"output": os.path.basename(out1) if ok else None,
          "error": why or None})
    if not ok:
        for n, nm in ((2, "container-format"), (3, "beat-text-ocr"),
                      (4, "no-black-no-freeze"), (5, "brand-colors"),
                      (6, "determinism")):
            gate(n, nm, False, {"skipped": "render failed"})
        rlog.close()
        shutil.rmtree(work, ignore_errors=True)
        return finish()

    # -- gate 2: container format ----------------------------------------------
    probe = ffprobe_json(out1)
    vs = next((s for s in (probe or {}).get("streams", [])
               if s.get("codec_type") == "video"), {})
    meas_dur = float((probe or {}).get("format", {}).get("duration", -1))
    fps_parts = vs.get("r_frame_rate", "0/1").split("/")
    meas_fps = (float(fps_parts[0]) / float(fps_parts[1])
                if len(fps_parts) == 2 and float(fps_parts[1]) else -1)
    checks = {
        "duration_s": {"expected": dur, "measured": round(meas_dur, 3),
                       "ok": abs(meas_dur - dur) <= 0.11},
        "width": {"expected": w, "measured": vs.get("width"),
                  "ok": vs.get("width") == w},
        "height": {"expected": h, "measured": vs.get("height"),
                   "ok": vs.get("height") == h},
        "fps": {"expected": fps, "measured": meas_fps,
                "ok": abs(meas_fps - fps) < 0.01},
        "codec": {"expected": "h264", "measured": vs.get("codec_name"),
                  "ok": vs.get("codec_name") == "h264"},
        "pix_fmt": {"expected": "yuv420p", "measured": vs.get("pix_fmt"),
                    "ok": vs.get("pix_fmt") == "yuv420p"},
    }
    gate(2, "container-format", all(c["ok"] for c in checks.values()),
         checks)

    # -- gates 3-5 need sampled frames from render 1 ----------------------------
    beats = spec["beats"]
    beat_times = [float(b["start_s"]) + float(b["hold_s"]) / 2.0
                  for b in beats]
    frames = [grab_frame_rgb(out1, t, w, h) for t in beat_times]
    # small downscale for the colour gate
    small = []
    for t in beat_times:
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", out1,
             "-frames:v", "1", "-vf", "scale=160:90", "-f", "rawvideo",
             "-pix_fmt", "rgb24", "-"], capture_output=True)
        small.append(p.stdout if p.returncode == 0
                      and len(p.stdout) == 160 * 90 * 3 else None)

    # -- gate 3: OCR every beat text -------------------------------------------
    ocr_detail = []
    all_ok = True
    for b, t, rgb in zip(beats, beat_times, frames):
        best = 0.0
        best_variant = None
        if rgb is not None:
            base = os.path.join(work, "beat_%s" % b["label"])
            # raw variant: 2x lanczos-upscaled frame straight from ffmpeg
            up = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", out1,
                 "-frames:v", "1", "-vf",
                 "scale=%d:%d:flags=lanczos" % (w * 2, h * 2),
                 "-f", "image2", "-vcodec", "pgm", "-"],
                capture_output=True)
            if up.returncode == 0 and up.stdout:
                fp = "%s_raw.pgm" % base
                with open(fp, "wb") as f:
                    f.write(up.stdout)
                c = containment(b["text"], ocr_file(fp))
                if c > best:
                    best, best_variant = c, "raw"
            # threshold variants at native res: near-white text -> black,
            # near-black text -> black (SPEC: light >=200 / dark <=80)
            light = bytearray(w * h)
            dark = bytearray(w * h)
            for i in range(0, w * h * 3, 3):
                r, g, bl = rgb[i], rgb[i + 1], rgb[i + 2]
                lo = r if r < g else g
                if bl < lo:
                    lo = bl
                hi = r if r > g else g
                if bl > hi:
                    hi = bl
                j = i // 3
                light[j] = 0 if lo > 180 else 255
                dark[j] = 0 if hi < 80 else 255
            for name, data in (("light", light), ("dark", dark)):
                fp = "%s_%s.pgm" % (base, name)
                write_pgm(fp, w, h, bytes(data))
                c = containment(b["text"], ocr_file(fp))
                if c > best:
                    best, best_variant = c, name
        ok = best >= OCR_THRESHOLD
        all_ok = all_ok and ok
        ocr_detail.append({"label": b["label"], "t_s": round(t, 2),
                           "containment": round(best, 2),
                           "variant": best_variant, "ok": ok})
    gate(3, "beat-text-ocr", all_ok, {"beats": ocr_detail})

    # -- gate 4: blackdetect + freezedetect on render 1 -------------------------
    p = run(["ffmpeg", "-i", out1, "-vf",
             "blackdetect=d=%s:pic_th=0.98" % BLACK_MAX_S,
             "-an", "-f", "null", "-"])
    blacks = [float(m.group(1)) for m in re.finditer(
        r"black_duration:([0-9.]+)", p.stderr)]
    max_black = max(blacks) if blacks else 0.0
    p2 = run(["ffmpeg", "-i", out1, "-vf",
              "freezedetect=n=0.001:d=%s" % FREEZE_MAX_S,
              "-an", "-f", "null", "-"])
    freezes = [float(m.group(1)) for m in re.finditer(
        r"freeze_duration: ([0-9.]+)", p2.stderr)]
    max_freeze = max(freezes) if freezes else 0.0
    gate(4, "no-black-no-freeze",
         max_black <= BLACK_MAX_S and max_freeze <= FREEZE_MAX_S,
         {"max_black_s": q_step(max_black, 0.5),
          "max_freeze_s": q_step(max_freeze, 0.5),
          "limits": {"black_s": BLACK_MAX_S, "freeze_s": FREEZE_MAX_S}})

    # -- gate 5: brand colours in the sampled frames -----------------------------
    brand = [rgb2lab(int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
             for c in spec["brand_colors"]]
    col_detail = []
    col_ok = True
    for b, s in zip(beats, small):
        row = {"label": b["label"], "shares_pct": {}}
        if s is None:
            row["error"] = "frame decode failed"
            col_ok = False
        else:
            for c, lab in zip(spec["brand_colors"], brand):
                share = brand_share(s, 160, 90, lab)
                row["shares_pct"][c] = q_step(share, 0.5)
                if share < BRAND_MIN_PCT:
                    col_ok = False
        col_detail.append(row)
    gate(5, "brand-colors", col_ok,
         {"min_pct_required": BRAND_MIN_PCT, "delta_e_max": DE_MAX,
          "beats": col_detail})

    # -- gate 6: determinism — second render, SSIM/PSNR vs first -----------------
    # A second render is only meaningful when the first one is a clean pass;
    # skip it when an earlier gate already killed the artifact (saves ~2 min).
    if all(g["passed"] for g in gates if g["gate"] in (1, 2, 3, 4, 5)):
        out2 = os.path.join(work, "render2.mp4")
        ok2, why2 = render(comp_dir, out2, fps, rlog)
        if not ok2:
            gate(6, "determinism", False,
                 {"error": "second render failed: %s" % why2})
        else:
            p = run(["ffmpeg", "-i", out1, "-i", out2, "-lavfi",
                     "[0:v][1:v]ssim", "-f", "null", "-"])
            m = re.search(r"All:([0-9.]+)", p.stderr)
            ssim = float(m.group(1)) if m else 0.0
            p = run(["ffmpeg", "-i", out1, "-i", out2, "-lavfi",
                     "[0:v][1:v]psnr", "-f", "null", "-"])
            m = re.search(r"average:([0-9.]+|inf)", p.stderr)
            psnr = float(m.group(1)) if m else 0.0
            if math.isinf(psnr):
                psnr = 99.0          # identical streams; cap for reporting
            gate(6, "determinism",
                 ssim >= SSIM_MIN and psnr >= PSNR_MIN,
                 {"ssim_all": round(ssim, 4),
                  "psnr_db": q_step(psnr, 5.0),
                  "min": {"ssim": SSIM_MIN, "psnr_db": PSNR_MIN}})
    else:
        gate(6, "determinism", False,
             {"skipped": "an earlier gate already failed"})

    rlog.close()
    shutil.rmtree(work, ignore_errors=True)
    return finish()


if __name__ == "__main__":
    sys.exit(main())
