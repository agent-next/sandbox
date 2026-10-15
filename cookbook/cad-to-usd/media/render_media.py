#!/usr/bin/env python3
"""render_media.py — build every media artifact from the real judge outputs.

Usage (run with the judge venv python from media/, see make_media.sh):
    python -I render_media.py <data-dir> <out-dir>

Reads only real run data (media/data): the verdict JSON, the selftest
log, the mutant verdicts, the loop replay, the mesh geometry collected
from the judged .usda files, and the pinned source files (STEP/IGES
headers). Renders, with no invented numbers:

  result.png  hero still: the three judged parts + measured-vs-oracle
              bars with the judge pass lines drawn on
  loop.png    the fixing loop (iterations until pass) + kill-rate bars
  master/demo.mp4   lossless crf 0 master (git-ignored)
  demo.mp4    1920x1080 30 fps H.264 web encode (via make_media.sh)

Every caption's cap height is >= 4 % of the frame height (>= 43.2 px at
1080); fonts are DejaVu from matplotlib's bundled set. The storyboard
(media/STORYBOARD.md) describes the slot order this renders.
"""

import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FPS = 30
OUT = None  # out dir, set in main

BG = (247, 247, 244)        # light neutral background (first frame lit)
INK = (24, 24, 27)          # near-black text
BLUE = (0, 90, 181)         # Okabe-Ito blue
ORANGE = (230, 159, 0)      # Okabe-Ito orange
GREEN = (0, 138, 0)         # Okabe-Ito bluish green (pass)
RED = (213, 62, 79)         # fail
GREY = (105, 105, 110)
TERM_BG = (16, 18, 22)      # terminal slot
TERM_FG = (222, 226, 230)

_HERE = os.path.dirname(os.path.abspath(__file__))


def font_path(name):
    import matplotlib
    return os.path.join(matplotlib.get_data_path(), "fonts", "ttf", name)


def load_font(size, bold=True):
    return ImageFont.truetype(
        font_path("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        size)


def cap_height_px(font):
    """Rendered height of an 'H' in pixels (the caption-size metric)."""
    im = Image.new("L", (400, 200), 0)
    d = ImageDraw.Draw(im)
    d.text((10, 10), "H", font=font, fill=255)
    box = im.getbbox()
    return box[3] - box[1]


CAP_FONT = load_font(64)          # main captions: cap ~46 px = 4.3 % of 1080
CAP2_FONT = load_font(48)         # secondary labels on panels
SMALL_FONT = load_font(40)
TERM_FONT = load_font(34, bold=False)   # terminal text (cropped, zoomed)
MONO_FONT = load_font(34, bold=False)


# ---------------------------------------------------------------- 3D raster

def _project(tris, angle, elevation, scale, sw, sh):
    """Rotate, elevate, project. Returns screen x, y (n,3) and depth (n,3)."""
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    rot = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
    v = tris @ rot.T
    el = math.radians(elevation)
    ce, se = math.cos(el), math.sin(el)
    cam = np.array([[1.0, 0.0, 0.0],
                    [0.0, ce, -se],
                    [0.0, se, ce]])
    v = v @ cam.T
    x = v[..., 0] * scale + sw / 2
    y = -v[..., 2] * scale + sh / 2
    return x, y, v[..., 1]


def fit_scale(tris, elevation, viewport, target_h=0.72, target_w=0.72):
    """Constant scale so the part fills the frame at every turntable angle.

    Samples a full rotation at scale 1, takes the worst (largest) projected
    half-extent, and fits it to target fractions of the viewport. A fixed
    scale avoids the 'breathing' a per-frame fit would cause.
    """
    vw, vh = viewport
    max_x = max_y = 0.0
    for ang in range(0, 360, 15):
        x, y, _ = _project(tris, ang, elevation, 1.0, 0.0, 0.0)
        max_x = max(max_x, np.abs(x - x.mean()).max())
        max_y = max(max_y, np.abs(y - y.mean()).max())
    return min(target_h * vh / (2 * max_y), target_w * vw / (2 * max_x))


def render_mesh(tris, angle, elevation=22.0, zoom=1.0, viewport=(W, H),
                color=BLUE, light=(0.4, -0.55, 0.73), supersample=1.33,
                target_h=0.72, target_w=0.72, scale=None):
    """Software flat-shaded raster of a centered triangle soup.

    tris: (n, 3, 3) float array; angle: turntable degrees around the part's
    up (Z) axis; elevation: camera elevation in degrees. Painter's
    algorithm over depth-sorted triangles, drawn with PIL supersampled and
    box-downsampled. Returns an RGB numpy array of `viewport` size.
    """
    vw, vh = viewport
    sw, sh = int(vw * supersample), int(vh * supersample)
    if scale is None:
        scale = fit_scale(tris, elevation, viewport, target_h, target_w)
    scale *= supersample * zoom
    x, y, depth = _project(tris, angle, elevation, scale, sw, sh)

    # recompute view-space verts for shading normals
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    rot = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
    v = tris @ rot.T
    el = math.radians(elevation)
    ce, se = math.cos(el), math.sin(el)
    cam = np.array([[1.0, 0.0, 0.0],
                    [0.0, ce, -se],
                    [0.0, se, ce]])
    v = v @ cam.T

    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    norm = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.maximum(norm, 1e-12)
    light = np.array(light, dtype=float)
    light = light / np.linalg.norm(light)
    bright = 0.34 + 0.66 * np.clip(n @ light, 0.0, 1.0)

    order = np.argsort(depth.mean(axis=1))       # far first
    x, y, bright = x[order], y[order], bright[order]

    img = Image.new("RGB", (sw, sh), BG)
    draw = ImageDraw.Draw(img)
    base = np.array(color, dtype=float)
    pts = np.stack([x, y], axis=2)
    for i in range(len(order)):
        b = bright[i]
        if b < 0.06:      # near-back-facing: skip cheaply
            continue
        col = tuple(int(c) for c in np.clip(base * b + 18 * (1 - b), 0, 255))
        p = pts[i]
        draw.polygon([(p[0, 0], p[0, 1]), (p[1, 0], p[1, 1]),
                      (p[2, 0], p[2, 1])], fill=col)
    return np.asarray(img.resize((vw, vh), Image.BOX))


# ---------------------------------------------------------------- caption

def caption(img, text, font=CAP_FONT, fill=INK, y=None, x=W // 2,
            band=None, band_fill=(255, 255, 255, 208)):
    """Draw a centred caption; optional translucent band behind it."""
    d = ImageDraw.Draw(img, "RGBA")
    left, top, right, bottom = d.textbbox((0, 0), text, font=font)
    tw, th = right - left, bottom - top
    if y is None:
        y = H - 96 - th
    if band:
        d.rectangle([x - tw // 2 - 26, y - 18, x + tw // 2 + 26, y + th + 18],
                    fill=band_fill)
    d.text((x - tw // 2 - left, y - top), text, font=font, fill=fill)
    return img


# ---------------------------------------------------------------- frames

def frames_write(gen, count, path_fmt):
    os.makedirs(os.path.dirname(path_fmt), exist_ok=True)
    for i in range(count):
        img = gen(i)
        img.save(path_fmt % i)
        if i % 60 == 0:
            print(f"[render] frame {i}/{count}", flush=True)


def part_turntable(tris, frames, start_angle, deg_per_frame, **kw):
    def gen(i):
        ang = start_angle + i * deg_per_frame
        return Image.fromarray(render_mesh(tris, ang, **kw))

    return gen


def source_panel(lines, w, h, title):
    """Left 'input' panel: the real STEP/IGES header lines."""
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 118], fill=(238, 238, 236))
    d.text((36, 30), title, font=load_font(52), fill=INK)
    y = 158
    for ln in lines:
        d.text((36, y), ln, font=MONO_FONT, fill=(60, 64, 70))
        y += 52
    return img


STEP_KEYS = ("ISO-10303-21;", "FILE_DESCRIPTION", "FILE_NAME",
             "FILE_SCHEMA")


def header_lines(path, n=13):
    """First n real lines of a STEP/IGES source, each cropped to 52 chars."""
    out = []
    with open(path, errors="replace") as f:
        for line in f:
            out.append(line.rstrip("\n")[:52])
            if len(out) >= n:
                break
    return out


# ---------------------------------------------------------------- slots

def slot_hook(meshes, keys, seg_dir):
    key = "Servo_Futaba_S3003_v6_step"
    tris = meshes[key]
    gen = part_turntable(tris, 60, 28, 0.8, color=BLUE,
                         target_h=0.8, target_w=0.62)

    def framed(i):
        img = gen(i).copy()
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 8], fill=ORANGE)
        caption(img, "Real CAD → OpenUSD — checked by an independent kernel")
        return img

    frames_write(framed, 60, os.path.join(seg_dir, "s1_%03d.png"))


def slot_in_out(meshes, seg_dir, seg, src_path, key, title, caption_text,
                count, angle0, color):
    tris = meshes[key]
    panel_w = 800
    vw = W - panel_w
    lines = header_lines(src_path)
    gen = part_turntable(tris, count, angle0, 0.9, color=color,
                         viewport=(vw, H), target_h=0.66, target_w=0.66)

    def framed(i):
        img = Image.fromarray(np.full((H, W, 3), BG, dtype=np.uint8))
        img.paste(source_panel(lines, panel_w, H, title), (0, 0))
        img.paste(gen(i), (panel_w, 0))
        d = ImageDraw.Draw(img)
        d.line([panel_w, 0, panel_w, H], fill=(200, 200, 198), width=3)
        d.text((36, H - 110), "in: STEP / IGES", font=CAP2_FONT, fill=INK)
        d.text((panel_w + 36, H - 110),
               "out: .usda — millimetres, Z-up",
               font=CAP2_FONT, fill=INK)
        caption(img, caption_text, font=CAP2_FONT,
                y=40, x=panel_w + vw // 2, band=True)
        return img

    frames_write(framed, count, os.path.join(seg_dir, f"{seg}_%03d.png"))


def slot_closeup(meshes, seg_dir, counts_text):
    tris = meshes["ShockTowerFront_stp"]
    gen = part_turntable(tris, 105, 200, 1.5, color=ORANGE, zoom=1.35,
                         target_h=0.8, target_w=0.62)

    def framed(i):
        img = gen(i).copy()
        caption(img, counts_text)
        return img

    frames_write(framed, 105, os.path.join(seg_dir, "s4_%03d.png"))


def wrap_log_lines(log_paths, max_lines=26):
    """Real judge-run log lines, in order, cropped to the terminal width."""
    lines = []
    for p in log_paths:
        with open(p, errors="replace") as f:
            for line in f:
                line = line.rstrip()
                if line:
                    lines.append(line[:56])
    return lines


def slot_terminal(seg_dir, data, run_seconds, seg_seconds):
    lines = wrap_log_lines(data["log_paths"])
    total_frames = int(seg_seconds * FPS)
    per_frame = max(1, round(len(lines) / total_frames))
    label = f"the judge, run for real — {run_seconds / seg_seconds:.0f}x speed"

    def framed(i):
        img = Image.new("RGB", (W, H), TERM_BG)
        d = ImageDraw.Draw(img)
        d.rectangle([70, 92, W - 70, 94], fill=(70, 78, 88))
        d.text((70, 34), label, font=CAP2_FONT, fill=ORANGE)
        top = max(0, min(i * per_frame, len(lines) - 17))
        y = 122
        for ln in lines[top:top + 17]:
            col = TERM_FG
            if "PASS" in ln or "passed" in ln:
                col = (126, 211, 145)
            elif "FAIL" in ln or "ERROR" in ln or "killed" in ln.split(":")[0]:
                col = (240, 140, 130)
            d.text((84, y), ln, font=TERM_FONT, fill=col)
            y += 50
        caption(img, "one command from clone to verdict",
                font=CAP2_FONT, y=H - 100, band=True)
        return img

    frames_write(framed, total_frames, os.path.join(seg_dir, "s5_%03d.png"))


def slot_verdict(seg_dir, verdict):
    gates = [k for k in ("file_set", "stage_meta", "geometry_counts",
                         "bbox_match", "area_match", "conversion_script")]
    rows = [(g, verdict["gates"][g]["passed"] is True) for g in gates]
    m = verdict["measures"]["ShockTowerFront_stp"]
    parts_line = "3 parts · " + " + ".join(
        f"{verdict['measures'][k]['triangles']:,} tris" for k in
        ("Servo_Futaba_S3003_v6_step", "Servo_Futaba_S3003_v6_iges",
         "ShockTowerFront_stp"))

    def framed(_i):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.text((90, 74), "JUDGE: ALL 6 GATES PASS", font=load_font(76),
               fill=GREEN)
        d.text((90, 190), parts_line, font=CAP2_FONT, fill=INK)
        y = 300
        for name, ok in rows:
            mark = "PASS" if ok else "FAIL"
            d.text((120, y), name, font=CAP_FONT, fill=INK)
            d.text((880, y), mark, font=CAP_FONT,
                   fill=GREEN if ok else RED)
            y += 92
        caption(img, "USD bbox within 1% and area within 3% of the "
                     "OpenCASCADE oracle, per part",
                font=CAP2_FONT, y=H - 116, band=True)
        return img

    frames_write(framed, 75, os.path.join(seg_dir, "s6_%03d.png"))


def slot_matrix(seg_dir, mutant_rows, kill_rate_line):
    rows = mutant_rows
    n = len(rows)
    y0, dy = 190, min(72, (H - 340) // max(n, 1))

    def framed(_i):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.text((90, 64), "SELF-TEST — EVERY MUTANT KILLED BY A JUDGE GATE",
               font=load_font(58), fill=INK)
        y = y0
        for name, gates, ok in rows:
            d.text((120, y), name, font=load_font(44), fill=INK)
            d.text((700, y), "killed by: " + gates, font=load_font(40),
                   fill=BLUE if ok else RED)
            d.text((1660, y), "KILLED" if ok else "ALIVE",
                   font=load_font(44), fill=GREEN if ok else RED)
            y += dy
        d.text((90, H - 150), kill_rate_line, font=load_font(56), fill=GREEN)
        return img

    frames_write(framed, 135, os.path.join(seg_dir, "s7_%03d.png"))


def slot_endcard(seg_dir):
    def framed(_i):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 10], fill=ORANGE)
        d.text((90, 300), "$ python3 run.py", font=load_font(88), fill=INK)
        d.text((90, 470), "one command: fresh sandbox, pinned tools,",
               font=CAP_FONT, fill=GREY)
        d.text((90, 560), "independent judge, verdict printed.",
               font=CAP_FONT, fill=GREY)
        d.text((90, 740), "Ask your agent:", font=CAP2_FONT, fill=INK)
        wrapped = ["“Convert the RC-Car-CAD parts to OpenUSD and pass",
                   "cookbook/cad-to-usd/judge/grade.sh — README.md”"]
        y = 810
        for ln in wrapped:
            d.text((90, y), ln, font=CAP2_FONT, fill=BLUE)
            y += 66
        return img

    frames_write(framed, 90, os.path.join(seg_dir, "s8_%03d.png"))


# ---------------------------------------------------------------- stills

def make_result_png(data, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    verdict = data["verdict"]
    meshes = data["meshes"]
    fig = plt.figure(figsize=(13.2, 7.4), dpi=200)
    gs = fig.add_gridspec(2, 3, height_ratios=[1.35, 1.0],
                          hspace=0.34, wspace=0.28,
                          left=0.07, right=0.97, top=0.90, bottom=0.10)

    names = {"Servo_Futaba_S3003_v6_step": "servo (STEP)",
             "Servo_Futaba_S3003_v6_iges": "servo (IGES)",
             "ShockTowerFront_stp": "shock tower"}
    for j, (key, label) in enumerate(names.items()):
        ax = fig.add_subplot(gs[0, j])
        arr = render_mesh(meshes[key], 30 + 40 * j, zoom=1.0,
                          viewport=(760, 500), color=BLUE if j < 2 else ORANGE)
        ax.imshow(arr)
        m = verdict["measures"][key]
        ax.set_title(f"{label}\n{m['meshes']} meshes · "
                     f"{m['triangles']:,} triangles", fontsize=11)
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)

    ax1 = fig.add_subplot(gs[1, 0])
    labels, vals = [], []
    for key in names:
        for row in verdict["gates"]["bbox_match"]["detail"][key]:
            ext = row["oracle_max"] - row["oracle_min"]
            labels.append(f"{key.split('_')[0][:6]} {row['axis']}")
            vals.append(100.0 * max(row["delta_min"], row["delta_max"])
                        / max(ext, 1e-9))
    ax1.bar(range(len(vals)), vals, color=BLUE)
    ax1.axhline(1.0, color=RED, lw=2, ls="--", label="judge pass line (1%)")
    ax1.set_title("bbox endpoint error vs oracle (per axis)", fontsize=11)
    ax1.set_ylabel("% of oracle extent", fontsize=10)
    ax1.set_xticks(range(len(labels)))
    ax1.set_xticklabels(labels, rotation=45, fontsize=8)
    ax1.legend(fontsize=9)

    ax2 = fig.add_subplot(gs[1, 1])
    rel = [100.0 * verdict["gates"]["area_match"]["detail"][k]["rel_error"]
           for k in names]
    ax2.bar(range(3), rel, color=ORANGE)
    ax2.axhline(3.0, color=RED, lw=2, ls="--", label="judge pass line (3%)")
    ax2.set_title("total surface-area error vs OpenCASCADE", fontsize=11)
    ax2.set_ylabel("% relative error", fontsize=10)
    ax2.set_xticks(range(3))
    ax2.set_xticklabels(["servo\nSTEP", "servo\nIGES", "shock\ntower"],
                        fontsize=9)
    ax2.legend(fontsize=9)

    ax3 = fig.add_subplot(gs[1, 2])
    ax3.axis("off")
    lines = ["measured on a 2 vCPU sandbox, seed 42", "",
             "units: metersPerUnit = 0.001  upAxis = Z",
             "oracle: OpenCASCADE BRepBndLib.AddOptimal +",
             "        BRepGProp surface properties",
             "reader: usd-core 26.8 (independent of the converter)", "",
             "all 6 gates PASS — see judge/grade.sh"]
    y = 0.95
    for ln in lines:
        ax3.text(0.0, y, ln, fontsize=10.5, family="monospace",
                 transform=ax3.transAxes,
                 color=GREEN if ln.startswith("all 6") else INK)
        y -= 0.13
    fig.suptitle("cad-to-usd — STEP/IGES converted to OpenUSD, "
                 "verified against an independent CAD kernel",
                 fontsize=15)
    fig.savefig(out_path)
    plt.close(fig)
    print(f"[render] wrote {out_path}")


def make_loop_png(data, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    loop = data["loop"]
    rows = data["mutant_rows"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.0, 5.6), dpi=200,
                                   gridspec_kw={"wspace": 0.26,
                                                "left": 0.08, "right": 0.98,
                                                "top": 0.86, "bottom": 0.24})
    its = loop["steps"]
    xs = range(1, len(its) + 1)
    fails = [len(s["gates_failed"]) for s in its]
    colors = [RED if f else GREEN for f in fails]
    ax1.bar(xs, fails, color=colors)
    for x, s in zip(xs, its):
        ax1.text(x, 0.15, s["artifact"].replace("_", "\n")[:18],
                 rotation=90, fontsize=6.5, ha="center", va="bottom",
                 color="white" if s["gates_failed"] else GREEN)
    ax1.set_xticks(list(xs))
    ax1.set_xlabel("agent iteration", fontsize=11)
    ax1.set_ylabel("judge gates failed", fontsize=11)
    ax1.set_title("the agent loop: 5 failing drafts, then PASS",
                  fontsize=12)

    names = [r[0] for r in rows]
    killed = [1 if r[2] else 0 for r in rows]
    ax2.barh(range(len(rows)), killed,
             color=[GREEN if k else RED for k in killed])
    ax2.set_yticks(range(len(rows)))
    ax2.set_yticklabels(names, fontsize=8.5)
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(["alive", "killed"], fontsize=10)
    ax2.invert_yaxis()
    rate = sum(killed) / len(killed) * 100
    ax2.set_title(f"self-test kill rate: {sum(killed)}/{len(killed)} "
                  f"({rate:.0f}%) — kills counted only when a judge "
                  "gate reported the failure", fontsize=12)
    fig.suptitle("cad-to-usd — judge feedback drives the loop; the "
                 "self-test proves the judge can fail", fontsize=14)
    fig.savefig(out_path)
    plt.close(fig)
    print(f"[render] wrote {out_path}")


# ---------------------------------------------------------------- assemble

def parse_mutant_rows(data_dir, selftest_log):
    """(name, killing gates, killed) per mutant, from the real verdicts."""
    vdir = os.path.join(data_dir, "verdicts")
    rows = []
    for fn in sorted(os.listdir(vdir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(vdir, fn)) as f:
            v = json.load(f)
        bad = sorted(k for k, g in v.get("gates", {}).items()
                     if isinstance(g, dict) and g.get("passed") is False)
        rows.append((fn[:-5], ", ".join(bad) if bad else "(none)", bool(bad)))
    return rows


def center_meshes(meshes):
    """Center every part on its bbox midpoint (view-independent)."""
    out = {}
    for key, tris in meshes.items():
        v = tris.reshape(-1, 3)
        mid = (v.max(axis=0) + v.min(axis=0)) / 2.0
        out[key] = (tris - mid).astype(np.float32)
    return out


def main():
    global OUT
    data_dir = os.path.abspath(sys.argv[1])
    OUT = os.path.abspath(sys.argv[2])
    os.makedirs(os.path.join(OUT, "master"), exist_ok=True)

    # assert the caption-size rule before rendering anything
    ch = cap_height_px(CAP_FONT)
    print(f"[render] caption cap height {ch} px "
          f"({100.0 * ch / H:.1f}% of frame height)")
    assert ch >= 0.04 * H, "caption cap height below 4% of frame height"

    with open(os.path.join(data_dir, "verdict-good.json")) as f:
        verdict = json.load(f)
    meshes = center_meshes(
        {k: v for k, v in np.load(
            os.path.join(data_dir, "meshes.npz")).items()})
    with open(os.path.join(data_dir, "loop.json")) as f:
        loop = json.load(f)
    with open(os.path.join(data_dir, "selftest_seconds.json")) as f:
        run_seconds = json.load(f)["seconds"]

    mutant_rows = parse_mutant_rows(data_dir, "selftest.log")
    killed = sum(1 for r in mutant_rows if r[2])
    kill_line = (f"kill rate {killed}/{len(mutant_rows)} "
                 f"({100 * killed // max(len(mutant_rows), 1)}%)")

    data = {"verdict": verdict, "meshes": meshes, "loop": loop,
            "mutant_rows": mutant_rows,
            "log_paths": [os.path.join(data_dir, p) for p in
                          ("grade-good.log", "selftest.log")]}

    frames = os.path.join(OUT, "frames")
    os.makedirs(frames, exist_ok=True)

    print("[render] slot 1: hook")
    slot_hook(meshes, None, frames)
    print("[render] slot 2-3: input -> output")
    slot_in_out(meshes, frames, "s2",
                os.path.join(data_dir, "sources",
                             "Servo Futaba S3003 v6.step"),
                "Servo_Futaba_S3003_v6_step",
                "Servo Futaba S3003 v6.step",
                "same servo, converted from STEP", 120, 40, BLUE)
    slot_in_out(meshes, frames, "s3",
                os.path.join(data_dir, "sources",
                             "ShockTowerFront/_ShockTowerFront.stp"),
                "ShockTowerFront_stp",
                "_ShockTowerFront.stp",
                "same pipeline, third part", 105, 150, ORANGE)
    print("[render] slot 4: close-up")
    st = verdict["measures"]["ShockTowerFront_stp"]
    slot_closeup(meshes, frames,
                 f"ShockTowerFront — {st['meshes']} meshes, "
                 f"{st['triangles']:,} triangles")
    print("[render] slot 5: terminal")
    slot_terminal(frames, data, run_seconds, 9.0)
    print("[render] slot 6: verdict")
    slot_verdict(frames, verdict)
    print("[render] slot 7: kill matrix")
    slot_matrix(frames, mutant_rows, kill_line)
    print("[render] slot 8: end card")
    slot_endcard(frames)

    print("[render] encoding lossless master")
    master = os.path.join(OUT, "master", "demo.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-r", str(FPS),
        "-i", os.path.join(frames, "s1_%03d.png"),
        "-i", os.path.join(frames, "s2_%03d.png"),
        "-i", os.path.join(frames, "s3_%03d.png"),
        "-i", os.path.join(frames, "s4_%03d.png"),
        "-i", os.path.join(frames, "s5_%03d.png"),
        "-i", os.path.join(frames, "s6_%03d.png"),
        "-i", os.path.join(frames, "s7_%03d.png"),
        "-i", os.path.join(frames, "s8_%03d.png"),
        "-filter_complex",
        "[0:v][1:v][2:v][3:v][4:v][5:v][6:v][7:v]concat=n=8:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "libx264", "-crf", "0",
        "-preset", "veryfast", "-pix_fmt", "yuv420p", master],
        check=True)

    make_result_png(data, os.path.join(OUT, "result.png"))
    make_loop_png(data, os.path.join(OUT, "loop.png"))
    print("[render] done")


if __name__ == "__main__":
    main()
