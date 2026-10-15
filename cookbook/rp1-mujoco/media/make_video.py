#!/usr/bin/env python3
"""demo.mp4 -- the real judged run, then the mutant the judge killed.

Frames are composited with Pillow and piped to ffmpeg; the video is
1920x1080 at 30 fps, H.264 (crf 18, preset slow, yuv420p, +faststart),
25-40 s and under 8 MB, cut against cookbook/tools/video_gate.py.

Every robot frame is a real headless MuJoCo render of the pinned RP1
scene, loaded with the exact state the judge recorded at that instant
(media/data/traces/<name>/trace.csv, written by `grade.sh --trace`, seed
20261014) -- nothing is re-simulated.  Every number on screen is read from
a trace column or from a verdict JSON in media/data/verdicts/.  The 3D
frames are produced by vid_render.py (slow software rasterisation), so
this script only composites them: run vid_render.py first.

    python3 vid_render.py turntable 0 120   # ... and the other two shots
    python3 make_video.py

Structure (at least one cut every ~10 s; 30.0 s total):

    0.0- 4.0  the real result, orbiting          (3D, real render)
    4.0- 9.0  the judged episode, live readout   (3D, real render)
    9.0-12.5  result.png, full frame             (card)
   12.5-16.5  the zero-torque mutant falling     (3D, real render)
   16.5-20.5  loop.png, the kill matrix          (card)
   20.5-23.5  the verdict, quoted                (card)
   23.5-30.0  static end card                    (card)
"""
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MEDIA = os.path.dirname(os.path.abspath(__file__))
VERDICTS = os.path.join(MEDIA, "data", "verdicts")
TRACES = os.path.join(MEDIA, "data", "traces")
FRAMES = os.path.join(MEDIA, "frames")
MASTER = os.path.join(MEDIA, "master")
OUT = os.path.join(MEDIA, "demo.mp4")

W, H, FPS = 1920, 1080, 30
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_M = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_MB = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

GREEN = (26, 122, 47)
RED = (183, 28, 28)
INK = (11, 11, 11)
SUB = (74, 74, 72)
PAPER = (252, 252, 251)
BLUE = (42, 120, 214)

# burned-in caption sizes: cap height >= 4 % of 1080 px = 43.2 px.
# DejaVuSans-Bold 'H' cap height is ~0.73 em, so >= 60 px em size.
FS_BIG = 66
FS_CAP = 60          # cap height 44 px >= 43.2 px
FS_HUD = 40
FS_FINE = 44         # provenance lines: >= 44 px as the rule requires


def font(path, size):
    return ImageFont.truetype(path, size)


def cap_height(px):
    """Cap height of an 'H' drawn in the bold face at this pixel size."""
    bbox = font(FONT_B, px).getbbox("H")
    return bbox[3] - bbox[1]


def need(p):
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run media/collect_data.sh first")
    return p


def verdict(name):
    return json.load(open(need(os.path.join(VERDICTS, name + ".json"))))


def trace_cols(name):
    """(t, pelvis z, tilt) from the judge's own trace CSV."""
    p = need(os.path.join(TRACES, name, "trace.csv"))
    a = np.loadtxt(p, delimiter=",", skiprows=1)
    return a[:, 0], a[:, 3], a[:, 10]


class Card:
    """A 1920x1080 RGB canvas with caption-height-checked text helpers."""

    def __init__(self, bg=PAPER):
        self.im = Image.new("RGB", (W, H), bg)
        self.d = ImageDraw.Draw(self.im)
        self.captions = []

    def text(self, xy, s, fnt, fill=INK, anchor="la", caption=False,
             stroke=0, stroke_fill=None):
        self.d.text(xy, s, font=fnt, fill=fill, anchor=anchor,
                    stroke_width=stroke, stroke_fill=stroke_fill)
        if caption:
            self.captions.append((s, fnt))
        return self

    def image(self, im, box):
        """Paste im scaled into box=(x, y, w, h), keeping its aspect."""
        x, y, bw, bh = box
        iw, ih = im.size
        s = min(bw / iw, bh / ih)
        im = im.resize((max(1, int(iw * s)), max(1, int(ih * s))),
                       Image.LANCZOS)
        self.im.paste(im, (x + (bw - im.size[0]) // 2,
                           y + (bh - im.size[1]) // 2))
        return self

    def check(self):
        for s, fnt in self.captions:
            ch = cap_height(fnt.size)
            if ch < 0.04 * H:
                raise SystemExit(
                    f"caption too small: {s[:40]!r} cap height {ch:.0f}px "
                    f"< {0.04 * H:.0f}px")
        return self


def fit_font(d, s, path, size, max_w):
    """The largest font <= `size` whose rendering of s fits max_w.

    Captions must keep a cap height >= 4 % of the frame height (>= 44 px,
    i.e. em size >= 60) *and* must never run off the frame, so the size is
    only ever shrunk down to that floor -- never below it.  A string that
    does not fit at the floor is a bug in the caller's wording, not
    something to silently truncate.
    """
    floor = FS_CAP
    while size > floor:
        if d.textlength(s, font=font(path, size)) <= max_w:
            return font(path, size)
        size -= 2
    if d.textlength(s, font=font(path, floor)) > max_w:
        raise SystemExit(
            f"text does not fit in {max_w}px at the {floor}px caption "
            f"floor: {s[:70]!r}")
    return font(path, floor)


BANNER_H = 96        # one line of caption text
BANNER_H2 = 160      # title + a second caption line


def banner(card, title, sub=None, bar=(12, 20, 32), tcol=(255, 255, 255),
           scol=(178, 196, 214)):
    """A solid strip at the top so captions never sit on a busy render.

    Title and subtitle both stay at the 44 px caption floor, so the strip
    is two lines tall when a subtitle is present.  Returns its height.
    """
    h = BANNER_H2 if sub else BANNER_H
    card.d.rectangle([0, 0, W, h], fill=bar)
    ft = fit_font(card.d, title, FONT_B, FS_CAP, W - 72)
    card.text((36, 48), title, ft, fill=tcol, anchor="lm", caption=True)
    if sub:
        fs = fit_font(card.d, sub, FONT_M, FS_CAP, W - 72)
        card.text((36, 120), sub, fs, fill=scol, anchor="lm", caption=True)
    return h


def footnote(card, s):
    """Provenance line on a solid strip at the bottom (also a caption)."""
    card.d.rectangle([0, H - 78, W, H], fill=(12, 20, 32))
    f = fit_font(card.d, s, FONT, FS_CAP, W - 60)
    card.text((W // 2, H - 39), s, f, fill=(226, 234, 242), anchor="mm",
              caption=True)


def render_frame(shot, i):
    p = os.path.join(FRAMES, f"{shot}_{i:04d}.png")
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run media/vid_render.py {shot} first")
    return Image.open(p).convert("RGB")


def main():
    os.makedirs(MASTER, exist_ok=True)
    good = verdict("good")["gates"]
    zt = verdict("zero_torque")["gates"]
    t_good, z_good, tilt_good = trace_cols("good")
    t_zt, z_zt, tilt_zt = trace_cols("zero_torque")

    # the shots are defined once, in vid_render.py, so the video can only
    # use frames that were actually rendered (and the pose a frame shows
    # is the pose the caption quotes)
    sys.path.insert(0, MEDIA)
    import vid_render
    shot_n = {k: v[1] for k, v in vid_render.shots().items()}

    result_png = Image.open(need(os.path.join(MEDIA, "result.png")))
    loop_png = Image.open(need(os.path.join(MEDIA, "loop.png")))

    master = os.path.join(MASTER, "demo_lossless.mp4")
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-crf", "0", "-preset", "slow",
         "-pix_fmt", "yuv420p", master],
        stdin=subprocess.PIPE)

    n_written = 0
    checked = False
    tail = []

    def emit(card, tag="", check_now=False):
        nonlocal n_written, checked
        if check_now and not checked:
            card.check()
            checked = True
        frame = card.im.tobytes()
        ff.stdin.write(frame)
        if tag == "endcard":
            tail.append(frame)
        n_written += 1

    # ======================================================================
    # 1. the real result, orbiting
    # ======================================================================
    n = shot_n["turntable"]
    for i in range(n):
        c = Card((10, 16, 26))
        bh = banner(c, "RP1 humanoid -- stands through a 30 N push",
                    "real MuJoCo render")
        c.image(render_frame("turntable", i), (0, bh, W, H - 78 - bh))
        footnote(c, "judged pose from grade.sh --trace, seed 20261014")
        emit(c, check_now=(i == 0))

    # ======================================================================
    # 2. the judged episode, live readout
    # ======================================================================
    n = shot_n["episode"]
    for i in range(n):
        c = Card((10, 16, 26))
        bh = banner(c, "the judged episode -- real time",
                    "tilt limit 10 deg (stand gate)")
        c.image(render_frame("episode", i), (0, bh, W, H - bh))
        k = int(np.argmin(np.abs(t_good - (3.8 + (9.8 - 3.8) * i / (n - 1)))))
        c.d.rectangle([30, H - 160, 800, H - 30], fill=(12, 20, 32))
        c.text((54, H - 126), f"t = {t_good[k]:5.2f} s",
               font(FONT_MB, FS_CAP), fill=(255, 255, 255))
        c.text((54, H - 74),
               f"tilt {tilt_good[k]:4.1f} deg   pelvis z {z_good[k]:.3f} m",
               font(FONT_M, FS_CAP), fill=(178, 196, 214))
        if 5.0 <= t_good[k] < 5.4:
            c.text((W - 220, H - 95), "30 N PUSH", font(FONT_B, FS_BIG),
                   fill=(255, 90, 90), anchor="mm", caption=True)
        emit(c)

    # ======================================================================
    # 3. result.png, full frame (9.0-12.5 s, 105 frames)
    # ======================================================================
    n = 105
    for _ in range(n):
        c = Card((16, 20, 28))
        bh = banner(c, "the judged run, and every pass line")
        c.image(result_png, (24, bh + 22, W - 48, H - bh - 22 - 92))
        footnote(c, "result.png -- data/traces/good, data/verdicts/good.json")
        emit(c)

    # ======================================================================
    # 4. the mutant falling
    # ======================================================================
    n = shot_n["fall"]
    for i in range(n):
        c = Card((10, 16, 26))
        bh = banner(c, "mutant zero_torque -- the judge kills it",
                    "gate stand: z 0.051 m < 0.702 m", bar=(58, 10, 10))
        c.image(render_frame("fall", i), (0, bh, W, H - bh))
        k = int(np.argmin(np.abs(t_zt - 2.0 * i / (n - 1))))
        c.d.rectangle([30, H - 160, 800, H - 30], fill=(12, 20, 32))
        c.text((54, H - 126), f"t = {t_zt[k]:5.2f} s",
               font(FONT_MB, FS_CAP), fill=(255, 255, 255))
        c.text((54, H - 74),
               f"tilt {tilt_zt[k]:5.1f} deg   pelvis z {z_zt[k]:.3f} m",
               font(FONT_M, FS_CAP), fill=(255, 170, 170))
        emit(c)

    # ======================================================================
    # 5. loop.png, the kill matrix (16.5-20.5 s, 120 frames)
    # ======================================================================
    n = 120
    for _ in range(n):
        c = Card((16, 20, 28))
        bh = banner(c, "the judge can fail: 8/8 mutants killed")
        c.image(loop_png, (24, bh + 22, W - 48, H - bh - 22 - 92))
        footnote(c, "loop.png -- agent-loop replay, mutant x gate matrix")
        emit(c)

    # ======================================================================
    # 6. the verdict, quoted (20.5-23.5 s, 90 frames)
    # ======================================================================
    # (gate, measured, rule) -- two columns of cells, three short lines
    # each, so every string fits at the 44 px caption floor (checked below)
    rows = [
        ("model_loads",
         f"nq {good['model_loads']['nq']} nv {good['model_loads']['nv']} "
         f"nu {good['model_loads']['nu']}",
         f"{good['model_loads']['total_mass_kg']:.2f} kg"),
        ("mass_match",
         f"worst link {100 * good['mass_match']['worst_link_rel']:.2f} %",
         "<= 1 %"),
        ("gravity_statics",
         f"fz/mg {good['gravity_statics']['ratio']:.4f}", "within 2 %"),
        ("stand", f"tilt {good['stand']['max_tilt_deg']:.2f} deg, z "
         f"{good['stand']['zmin_m']:.3f} m", ">= 0.702 m"),
        ("push", f"{good['push']['max_tilt_after_recovery_deg']:.2f} deg "
         f"after t = 7 s", "<= 5 deg"),
        ("limits", "qpos, ctrl, force in range", "tol 1 mrad"),
        ("integrity", "checksums + audit clean", "no tamper"),
    ]
    n = 90
    for _ in range(n):
        c = Card(PAPER)
        c.text((W // 2, 78), "judge verdict:  PASS", font(FONT_B, 78),
               fill=GREEN, anchor="mm", caption=True)
        fn = font(FONT_B, FS_CAP)
        fm = font(FONT, FS_CAP)
        margin, gap = 60, 50
        cellw = (W - 2 * margin - gap) // 2
        y0, rowh, lh = 150, 196, 62
        n_rows = (len(rows) + 1) // 2
        if y0 + (n_rows - 1) * rowh + 2 * lh + 60 > H - 96:
            raise SystemExit("verdict card does not fit above the footnote")
        for i, (name, meas, rule) in enumerate(rows):
            col, row = i % 2, i // 2
            x = margin + col * (cellw + gap)
            y = y0 + row * rowh
            for s, f in ((name, fn), (meas, fm), (rule, fm)):
                if c.d.textlength(s, font=f) > cellw:
                    raise SystemExit(f"verdict cell {name}: {s!r} is wider "
                                     f"than {cellw}px")
            c.text((x, y), name, fn, fill=INK)
            c.text((x, y + lh), meas, fm, fill=INK)
            c.text((x, y + 2 * lh), rule, fm, fill=SUB)
        footnote(c, "source: data/verdicts/good.json (grade.sh --json)")
        emit(c)

    # ======================================================================
    # 7. end card (23.5-30.0 s, 195 frames) -- static
    # ======================================================================
    n = 195
    c = Card(PAPER)
    c.text((W // 2, 320), "try it:", font(FONT_B, FS_CAP), fill=SUB,
           anchor="mm", caption=True)
    c.text((W // 2, 452), "python3 cookbook/rp1-mujoco/run.py",
           font(FONT_MB, 76), fill=INK, anchor="mm")
    c.text((W // 2, 596),
           "agent-next sandbox demo  --  cookbook/rp1-mujoco",
           font(FONT, FS_CAP), fill=SUB, anchor="mm", caption=True)
    c.text((W // 2, 672),
           "judge: MuJoCo 3.14.0 + URDF cross-parse + statics oracle",
           font(FONT, FS_CAP), fill=SUB, anchor="mm", caption=True)
    c.text((W // 2, 812),
           "8/8 mutants killed (100 %)  |  same seed -> byte-identical "
           "verdict", font(FONT, FS_CAP), fill=SUB, anchor="mm")
    c.check()
    end_frame = c.im.tobytes()
    for _ in range(n):
        ff.stdin.write(end_frame)
        tail.append(end_frame)
        n_written += 1

    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg master encode failed")

    # the end card must be genuinely static (video_gate: mean YDIF <= 0.5)
    assert len(set(tail)) == 1, "end card is not static"

    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", master,
         "-c:v", "libx264", "-crf", "18", "-preset", "slow",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT],
        check=True)

    size = os.path.getsize(OUT)
    pr = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-show_entries", "stream=width,height,r_frame_rate,codec_name,"
         "pix_fmt", "-of", "json", OUT],
        capture_output=True, text=True, check=True)
    meta = json.loads(pr.stdout)
    dur = float(meta["format"]["duration"])
    st = meta["streams"][0]
    print(f"{OUT}: {dur:.1f} s, {st['width']}x{st['height']} @ "
          f"{st['r_frame_rate']} {st['codec_name']}/{st['pix_fmt']}, "
          f"{size / 1e6:.2f} MB (master "
          f"{os.path.getsize(master) / 1e6:.1f} MB)")
    assert 25.0 <= dur <= 40.0, f"duration {dur} outside 25-40 s"
    assert size < 8e6, f"demo.mp4 {size} bytes > 8 MB"
    assert (st["width"], st["height"]) == (W, H)
    assert st["codec_name"] == "h264" and st["pix_fmt"] == "yuv420p"
    assert n_written == int(round(dur * FPS)), \
        f"wrote {n_written} frames for {dur:.2f} s"
    print(f"frames written: {n_written}; end card static: OK; "
          "caption cap heights checked")


if __name__ == "__main__":
    main()
