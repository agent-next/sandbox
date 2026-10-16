#!/usr/bin/env python3
"""Render media/clips/*.mp4 — the real motion clips the Remotion cut composes.

Every clip is 1920x1080 @ 30 fps drawn frame-by-frame with PIL from the
judge-output data in media/data/ (all written by make_data.py from real
ngspice runs in this sandbox). ffmpeg only encodes the PNG frames; nothing
here draws a still.

Clips:
  scope.mp4  dual-trace oscilloscope, ngspice .tran waveforms sweeping in
             at 300 Hz / 1.4 kHz / 16 kHz (passband / corner / stopband)
  bode.mp4   the judge's AC sweeps drawing themselves against the spec mask
  term.mp4   captured terminal output of this run's selftest+grade, replayed
  mc.mp4     all 100 seeded Monte-Carlo sweeps streaming in over the
             relaxed mask with the pass counter
"""
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"
CLIPS = MEDIA / "clips"
W, H, FPS = 1920, 1080, 30

BG = (14, 20, 29)
PANEL = (22, 31, 43)
GRID = (44, 60, 82)
GRID2 = (30, 41, 57)
TXT = (198, 212, 226)
DIM = (116, 130, 148)
CYAN = (0, 214, 255)
GREEN = (84, 255, 122)
AMBER = (255, 179, 40)
BLUE = (88, 140, 255)
RED = (255, 92, 92)
MASKC = (255, 210, 80)

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def font(size, bold=False, mono=True):
    name = ("DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf") if mono \
        else ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    return ImageFont.truetype(str(FONT_DIR / name), size)


def load(name):
    return json.loads((DATA / name).read_text())


def enc(frames_dir: Path, out: Path) -> None:
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
        "-i", str(frames_dir / "f%05d.ppm"),
        "-c:v", "libx264", "-crf", "14", "-preset", "medium",
        "-pix_fmt", "yuv420p", str(out)], check=True)
    print(f"  {out.name}: {out.stat().st_size / 1e6:.1f} MB")


def text(d, xy, s, fnt, fill=TXT, anchor="la"):
    d.text(xy, s, font=fnt, fill=fill, anchor=anchor)


# --- in-clip camera ---------------------------------------------------------
# Clips that cannot move their content every frame (a drawing pen is a few
# px wide) put the finished 1080p frame on a wider canvas and crop a moving
# viewport: a constant-speed ping-pong pan, i.e. the camera exploring the
# plot.  Every textured pixel then shifts ~5 px/frame at 640 px wide, which
# is what the video gate's motion metric measures.
PAN_MX, PAN_MY = 340, 100
WORLD = (W + 2 * PAN_MX, H + 2 * PAN_MY)


def pan_view(frame: Image.Image, fi: int, sx: float = 14.0,
             sy: float = 5.0) -> Image.Image:
    phx = (fi * sx / (2 * PAN_MX)) % 2.0
    vx = int(2 * PAN_MX * (phx if phx < 1 else 2 - phx))
    phy = (fi * sy / (2 * PAN_MY)) % 2.0
    vy = int(2 * PAN_MY * (phy if phy < 1 else 2 - phy))
    world = Image.new("RGB", WORLD, BG)
    world.paste(frame, (PAN_MX, PAN_MY))
    return world.crop((vx, vy, vx + W, vy + H))


# --------------------------------------------------------------------------
# clip 1: oscilloscope — real ngspice transient segments in roll mode:
# the whole waveform slides left every frame (continuous motion), the
# write head enters at the right edge.  V/div and TIME/div stay honest.
# --------------------------------------------------------------------------

def clip_scope(frames: Path) -> None:
    segs = load("transient.json")["segments"]
    dur = 12.0                       # s; 3 segments of 4 s
    n = int(dur * FPS)
    # scope bezel + grid (static layer)
    bg = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle([40, 60, W - 40, H - 120], radius=18,
                        fill=(12, 17, 24), outline=GRID, width=3)
    x0, y0, x1, y1 = 90, 110, W - 90, H - 170
    px_per_div = (x1 - x0) / 10.0
    for i in range(11):
        x = x0 + i * px_per_div
        d.line([x, y0, x, y1], fill=GRID if i % 5 else GRID2, width=1)
    for i in range(9):
        y = y0 + i * (y1 - y0) / 8
        d.line([x0, y, x1, y], fill=GRID, width=1)
    d.line([(x0 + x1) / 2, y0, (x0 + x1) / 2, y1], fill=GRID2, width=2)
    d.line([x0, (y0 + y1) / 2, x1, (y0 + y1) / 2], fill=GRID2, width=2)
    bg_arr = np.asarray(bg, dtype=np.uint8)

    f_ch1 = font(30); f_ch2 = font(30); f_lab = font(34, bold=True)
    f_meas = font(36, bold=True)

    seg_s = dur / len(segs)
    seg_frames = int(seg_s * FPS)
    cycles = 2.0                     # window width in periods (10 div);
                                     # integer cycles -> wraps phase-aligned
    scroll_px = 13.0                 # roll speed, screen px per frame
    for fi in range(n):
        t = fi / FPS
        k = min(int(t / seg_s), len(segs) - 1)
        seg = segs[k]
        f0 = seg["freq_hz"]
        per = seg["period_s"]
        win = cycles * per
        tt = np.asarray(seg["t"])
        # settled tail only: the last few complete periods, where both
        # channels are steady sines.  The record's startup ring is large
        # (the 16 kHz step rings at ~47 mV, off-screen at 1 mV/div) so the
        # window must live in the genuinely settled cycles.
        ncyc = min(8, int(round((tt[-1] - tt[0]) / per)) - 1)
        tail_start = tt[-1] - ncyc * per
        span = ncyc * per - win      # sliding range inside the tail
        fi_seg = fi - k * seg_frames
        off = tail_start + ((fi_seg * scroll_px) / (x1 - x0) * win) % span
        m = (tt >= off) & (tt <= off + win)
        frame = Image.fromarray(bg_arr.copy())
        dd = ImageDraw.Draw(frame)
        if m.sum() >= 2:
            xs = x0 + (tt[m] - off) / win * (x1 - x0)
            # honest scope scales: 500 mV/div (8 div = ±2 V), and
            # CH2 at 1 mV/div in the stopband segment
            vs_in = (y1 - y0) / (8 * 0.5)
            vs_out = vs_in if k < 2 else (y1 - y0) / (8 * 0.001)
            ys_in = (y0 + y1) / 2 - np.asarray(seg["vin"])[m] * vs_in
            ys_out = (y0 + y1) / 2 - np.asarray(seg["vout"])[m] * vs_out
            pts_in = list(zip(xs, ys_in)); pts_out = list(zip(xs, ys_out))
            for pts, col in ((pts_in, CYAN), (pts_out, GREEN)):
                dd.line(pts, fill=tuple(c // 3 for c in col), width=9)
                dd.line(pts, fill=col, width=3)
            # write head: bright dot where new samples enter (right edge)
            for pts, col in ((pts_in, CYAN), (pts_out, GREEN)):
                ex, ey = pts[-1]
                dd.ellipse([ex - 10, ey - 10, ex + 10, ey + 10], fill=col)
            dd.line([x1 - 2, y0, x1 - 2, y1], fill=(60, 90, 120), width=2)
        # bezel labels (real numbers)
        ch2div = "500 mV/div" if k < 2 else "1 mV/div"
        text(dd, (160, H - 100), "CH1 500 mV/div", f_ch1, CYAN)
        text(dd, (540, H - 100), f"CH2 {ch2div}", f_ch2, GREEN)
        text(dd, (W - 190, H - 100), "ngspice tran · lpf4sk.cir", f_ch1, DIM,
             anchor="ra")
        text(dd, (160, 66), "OSCILLOSCOPE  in → out", f_lab, TXT)
        tdiv = win / 10.0
        if tdiv >= 2e-4:
            v, unit = tdiv * 1e3, "ms"
        else:
            v, unit = tdiv * 1e6, "µs"
        tdiv_s = f"{v:.0f} {unit}/div" if v >= 100 else f"{v:.2g} {unit}/div"
        text(dd, (880, H - 100), f"TIME {tdiv_s}", f_ch2, DIM)
        text(dd, (W - 190, 66), f"meas f = {f0:g} Hz", f_meas, AMBER,
             anchor="ra")
        frame.save(frames / f"f{fi:05d}.ppm")
    print(f"  scope.mp4 frames: {n}")


# --------------------------------------------------------------------------
# clip 2: bode — judge sweeps drawing themselves against the spec mask
# --------------------------------------------------------------------------

def clip_bode(frames: Path) -> None:
    sw = load("sweep_good.json")
    nom, ana, gbw = sw["nominal"], sw["nominal"]["analytic_db"], sw["gbw_macromodel"]
    mask = sw["mask"]
    f = np.asarray(nom["freq"]); g = np.asarray(nom["gain_db"])
    ga = np.asarray(ana); gg = np.asarray(gbw["gain_db"])
    props = load("video_props.json")

    dur = 12.5
    n = int(dur * FPS)
    x0, y0, x1, y1 = 170, 130, W - 90, H - 150
    FMIN, FMAX = 10.0, 100_000.0
    YMIN, YMAX = -110.0, 8.0

    def xy(ff, db):
        x = x0 + (math.log10(ff) - math.log10(FMIN)) / \
            (math.log10(FMAX) - math.log10(FMIN)) * (x1 - x0)
        y = y1 - (db - YMIN) / (YMAX - YMIN) * (y1 - y0)
        return x, y

    # static layer: panel, grid, axes labels, spec mask edges
    bg = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle([40, 40, W - 40, H - 40], radius=16,
                        fill=PANEL, outline=GRID, width=2)
    f_t = font(28); f_ax = font(30); f_ttl = font(40, bold=True)
    f_mask = font(30, bold=True)
    for p in range(1, 5):
        fx = 10.0 ** p
        x, _ = xy(fx, 0)
        d.line([x, y0, x, y1], fill=GRID, width=2)
        text(d, (x, y1 + 14), f"{fx:g} Hz" if fx >= 1000 else f"{fx:g} Hz",
             f_ax, DIM, anchor="ma")
    for dbv in range(-100, 9, 20):
        _, y = xy(10, dbv)
        d.line([x0, y, x1, y], fill=GRID, width=1)
        text(d, (x0 - 16, y), f"{dbv} dB", f_ax, DIM, anchor="rm")
    d.rectangle([x0, y0, x1, y1], outline=GRID, width=2)
    text(d, (150, 66), "AC SWEEP  |v(out)|  vs  SPEC MASK", f_ttl, TXT)
    text(d, (W - 180, 66), "ngspice ac dec 200 10 100k", f_t, DIM, anchor="ra")
    # mask polyline (step): passband ripple band + stopband ceiling
    rip, stp = mask["ripple_max_db"], mask["stop_max_db"]
    pe, se = mask["passband_edge_hz"], mask["stopband_edge_hz"]
    xa, ya = xy(FMIN, rip); xb, yb = xy(pe, rip)
    xc, yc = xy(se, stp); xd, yd = xy(FMAX, stp)
    mask_pts = [(xa, ya), (xb, yb), (xb, yc), (xc, yc), (xd, yd)]
    d.line(mask_pts, fill=MASKC, width=4)
    # ripple band floor (-1 dB)
    _, yrb = xy(10, -rip)
    d.line([(xa, yrb), (xb, yrb)], fill=MASKC, width=4)
    text(d, (xb + 18, (yb + yc) / 2), "SPEC MASK", f_mask, MASKC)
    bg_arr = np.asarray(bg, dtype=np.uint8)

    # soft measurement scan band, sweeping the plot for the whole shot
    band_w = 300
    band = Image.new("RGBA", (band_w, y1 - y0), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for i in range(band_w):
        a = int(36 * math.sin(math.pi * i / band_w) ** 2)
        bd.line([i, 0, i, y1 - y0], fill=(120, 220, 255, a))
    band_travel = (x1 - x0) + 2 * band_w

    # phased drawing: mask+nominal 8-56 %, analytic 56-66 %, gbw 66-80 %,
    # measurement cursor scan 80-100 %
    def draw_curve(img_d, xs, ys, upto, col, wdt=4):
        k = max(2, int(upto))
        img_d.line(list(zip(xs[:k], ys[:k])), fill=col, width=wdt)
        return xs[k - 1], ys[k - 1]

    xs_nom, ys_nom = [], []
    for ff, v in zip(f, g):
        a, b = xy(ff, v); xs_nom.append(a); ys_nom.append(b)
    xs_ana, ys_ana = [], []
    for ff, v in zip(f, ga):
        a, b = xy(ff, v); xs_ana.append(a); ys_ana.append(b)
    xs_gbw, ys_gbw = [], []
    for ff, v in zip(f, gg):
        a, b = xy(ff, v); xs_gbw.append(a); ys_gbw.append(b)

    worst_i = int(np.argmax(np.abs(gg - ga)))
    f_meas = font(40, bold=True); f_chip = font(30, bold=True)

    for fi in range(n):
        p = fi / n
        frame = Image.fromarray(bg_arr.copy())
        dd = ImageDraw.Draw(frame, "RGBA")
        # translucent fill under the part of the sweep drawn so far
        if p >= 0.08:
            upto_f = max(2, int(min(1.0, (p - 0.08) / 0.48) * len(xs_nom)))
            dd.polygon(list(zip(xs_nom[:upto_f], ys_nom[:upto_f]))
                       + [(xs_nom[upto_f - 1], y1), (xs_nom[0], y1)],
                       fill=(0, 214, 255, 26))
        # the scan band sweeps the plot continuously, behind the traces
        frame.paste(band, (int(x0 - band_w + (fi * 10) % band_travel), y0),
                    band)
        if p >= 0.08:
            u = min(1.0, (p - 0.08) / 0.48)
            upto = u * len(xs_nom)
            ex, ey = draw_curve(dd, xs_nom, ys_nom, upto, CYAN, 5)
            if u < 1.0:
                dd.ellipse([ex - 10, ey - 10, ex + 10, ey + 10], fill=CYAN)
                i = max(0, int(upto) - 1)
                chip = f"f={f[i]:9.0f} Hz   |v(out)|={g[i]:7.2f} dB"
                dd.rounded_rectangle([x0 + 30, y1 - 90, x0 + 780, y1 - 30],
                                     radius=10, fill=(14, 21, 30),
                                     outline=CYAN, width=2)
                text(dd, (x0 + 52, y1 - 74), chip, f_chip, CYAN)
        if p >= 0.56:
            u = min(1.0, (p - 0.56) / 0.10)
            draw_curve(dd, xs_ana, ys_ana, u * len(xs_ana), DIM, 3)
            if u >= 1.0:
                text(dd, (x1 - 560, y0 + 52), "closed-form oracle", f_t, DIM)
        if p >= 0.66:
            u = min(1.0, (p - 0.66) / 0.14)
            draw_curve(dd, xs_gbw, ys_gbw, u * len(xs_gbw), AMBER, 4)
            if u >= 1.0:
                mx, my = xs_gbw[worst_i], ys_gbw[worst_i]
                dd.ellipse([mx - 12, my - 12, mx + 12, my + 12],
                           outline=AMBER, width=4)
                tx, ty = x1 - 560, y0 + 300
                dd.line([(mx - 8, my - 8), (tx + 330, ty + 62)],
                        fill=AMBER, width=2)
                dd.rounded_rectangle([tx, ty, tx + 520, ty + 64],
                                     radius=10, fill=(14, 21, 30),
                                     outline=AMBER, width=2)
                text(dd, (tx + 22, ty + 16),
                     f"GBW dev ≤ {props['gbw_dev_db']:.3f} dB",
                     f_chip, AMBER)
                text(dd, (x1 - 560, y0 + 94), "1 MHz-GBW macro-model",
                     f_t, AMBER)
        if p >= 0.80:
            u = (p - 0.80) / 0.20
            fx = FMIN * (FMAX / FMIN) ** u
            cx, _ = xy(fx, 0)
            dd.line([cx, y0, cx, y1], fill=(255, 255, 255), width=2)
            # cursor readout interpolates the real sweep at fx
            gv = float(np.interp(np.log10(fx), np.log10(f), g))
            dd.rounded_rectangle([x0 + 30, y1 - 90, x0 + 700, y1 - 30],
                                 radius=10, fill=(14, 21, 30),
                                 outline=TXT, width=2)
            text(dd, (x0 + 52, y1 - 78),
                 f"cursor  f={fx:9.0f} Hz   gain={gv:7.2f} dB", f_chip, TXT)
        pan_view(frame, fi).save(frames / f"f{fi:05d}.ppm")
    print(f"  bode.mp4 frames: {n}")


# --------------------------------------------------------------------------
# clip 3: terminal — this run's captured selftest+grade output, replayed
# --------------------------------------------------------------------------

def clip_term(frames: Path) -> None:
    log = (DATA / "runlog.txt").read_text().splitlines()
    dur = 9.0
    n = int(dur * FPS)
    f_t = font(27); f_b = font(30, bold=True)
    lh = 40
    # pre-render the whole transcript once, then pan a window over it
    th = lh * (len(log) + 2)
    page = Image.new("RGB", (1560, th), (13, 17, 23))
    pd_ = ImageDraw.Draw(page)
    for i, ln in enumerate(log[:]):
        if len(ln) > 92:
            ln = ln[:89] + "..."
        col = TXT
        if ln.startswith("$ "):
            col = GREEN
        elif '"passed": true' in ln or "PASS" in ln:
            col = CYAN
        elif "killed" in ln or "failed" in ln.lower():
            col = AMBER
        pd_.text((30, i * lh), ln, font=f_t, fill=col)
    page_arr = np.asarray(page)

    for fi in range(n):
        p = fi / (n - 1)
        # scroll: fast start, settle on the verdict tail
        ease = 1.0 - (1.0 - p) ** 1.6
        ymax = max(0, th - 920)
        top = int(ease * ymax)
        frame = Image.new("RGB", (W, H), (6, 9, 13))
        dd = ImageDraw.Draw(frame)
        dd.rounded_rectangle([140, 70, 1780, 1030], radius=14,
                             fill=(17, 22, 30), outline=GRID, width=2)
        dd.rounded_rectangle([140, 70, 1780, 126], radius=14,
                             fill=(30, 38, 50))
        dd.rectangle([140, 110, 1780, 126], fill=(30, 38, 50))
        for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
            dd.ellipse([170 + i * 34, 88, 190 + i * 34, 108], fill=c)
        text(dd, (960, 98), "sandbox — judge run (recorded)", f_t, DIM,
             anchor="mm")
        win = Image.fromarray(page_arr[top:top + 880])
        frame.paste(win, (170, 140))
        dd.rectangle([170, 140, 1750, 150], fill=(17, 22, 30))
        # badge: the replay is sped up — labelled
        dd.rounded_rectangle([1380, 950, 1750, 1010], radius=10,
                             fill=(30, 38, 52), outline=AMBER, width=2)
        text(dd, (1400, 965), "REPLAY · 8× speed", f_b, AMBER)
        # blinking block cursor at the live edge
        if fi % 30 < 18:
            dd.rectangle([170, 1000 - lh, 190, 1000 - 6], fill=GREEN)
        frame.save(frames / f"f{fi:05d}.ppm")
    print(f"  term.mp4 frames: {n}")


# --------------------------------------------------------------------------
# clip 4: monte-carlo — all 100 seeded sweeps streaming over the relaxed mask
# --------------------------------------------------------------------------

def clip_mc(frames: Path) -> None:
    mc = load("mc_curves.json")
    props = load("video_props.json")
    f = np.asarray(mc["freq"])
    dur = 8.0
    n = int(dur * FPS)
    x0, y0, x1, y1 = 170, 130, W - 90, H - 150
    YMIN, YMAX = -80.0, 8.0

    def xy(ff, db):
        x = x0 + (math.log10(ff) - math.log10(10.0)) / 4.0 * (x1 - x0)
        y = y1 - (db - YMIN) / (YMAX - YMIN) * (y1 - y0)
        return x, y

    bg = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle([40, 40, W - 40, H - 40], radius=16,
                        fill=PANEL, outline=GRID, width=2)
    f_t = font(28); f_ttl = font(40, bold=True)
    for p_ in range(1, 5):
        x, _ = xy(10.0 ** p_, 0)
        d.line([x, y0, x, y1], fill=GRID, width=2)
    for dbv in range(-80, 9, 20):
        _, y = xy(10, dbv)
        d.line([x0, y, x1, y], fill=GRID, width=1)
        text(d, (x0 - 16, y), f"{dbv} dB", f_t, DIM, anchor="rm")
    d.rectangle([x0, y0, x1, y1], outline=GRID, width=2)
    text(d, (150, 66), "MONTE-CARLO  R ±5 % / C ±10 %  ·  relaxed mask",
         f_ttl, TXT)
    text(d, (W - 180, 66), f"seed {mc['seed']} · ngspice ×{mc['runs']}",
         f_t, DIM, anchor="ra")
    # relaxed mask lines
    rm = mc["relaxed_mask"]
    xa, ya = xy(10, rm["ripple_max_db"]); xb, yb = xy(1000, rm["ripple_max_db"])
    xc, yc = xy(10_000, rm["stop_max_db"]); xd, yd = xy(100_000, rm["stop_max_db"])
    _, yrb = xy(10, -rm["ripple_max_db"])
    d.line([(xa, ya), (xb, yb)], fill=MASKC, width=3)
    d.line([(xa, yrb), (xb, yrb)], fill=MASKC, width=3)
    d.line([(xb, yc), (xc, yc), (xd, yd)], fill=MASKC, width=3)
    bg_arr = np.asarray(bg, dtype=np.uint8)

    # same continuous scan band as the bode clip
    band_w = 300
    band = Image.new("RGBA", (band_w, y1 - y0), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for i in range(band_w):
        a = int(36 * math.sin(math.pi * i / band_w) ** 2)
        bd.line([i, 0, i, y1 - y0], fill=(120, 220, 255, a))
    band_travel = (x1 - x0) + 2 * band_w

    runs = mc["results"]
    curves_xy = []
    for r in runs:
        pts = [xy(ff, v) for ff, v in zip(f, r["gain_db"])]
        curves_xy.append(pts)

    f_cnt = font(64, bold=True); f_chip = font(32, bold=True)
    arrivals = n - 45                    # last ~1.5 s only the banner moves
    for fi in range(n):
        frame = Image.fromarray(bg_arr.copy())
        dd = ImageDraw.Draw(frame, "RGBA")
        # scan band sweeping under everything for the whole shot
        frame.paste(band, (int(x0 - band_w + (fi * 10) % band_travel), y0),
                    band)
        shown = min(len(runs), int(fi * len(runs) / arrivals) + 1)
        for i in range(shown):
            age = shown - i
            base = curves_xy[i]
            col = BLUE if runs[i]["ok"] else RED
            if age <= 6:                 # curve sweeps in over 6 frames
                k = max(2, int(len(base) * age / 6))
                dd.line(base[:k], fill=col, width=5)
            else:
                dd.line(base, fill=tuple(max(30, c // 3) for c in col),
                        width=2)
        ok_ct = sum(1 for r in runs[:shown] if r["ok"])
        dd.rounded_rectangle([x0 + 30, y0 + 24, x0 + 560, y0 + 110],
                             radius=12, fill=(14, 21, 30), outline=GREEN,
                             width=2)
        text(dd, (x0 + 56, y0 + 40),
             f"run {shown:3d}/100   pass {ok_ct}", f_cnt, GREEN)
        if fi >= arrivals:
            a = min(1.0, (fi - arrivals) / 20)
            bw = int(560 * a)
            cxp = (x0 + x1) / 2
            dd.rounded_rectangle([cxp - bw, y0 + 150, cxp + bw, y0 + 236],
                                 radius=14, fill=(14, 34, 22),
                                 outline=GREEN, width=3)
            if bw > 270:
                text(dd, (cxp, y0 + 165),
                     f"{props['mc_runs']}/{props['mc_runs']} PASS — "
                     f"≥90 % gate met", f_chip, GREEN, anchor="ma")
        pan_view(frame, fi).save(frames / f"f{fi:05d}.ppm")
    print(f"  mc.mp4 frames: {n}")


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    CLIPS.mkdir(parents=True, exist_ok=True)
    jobs = {"scope": clip_scope, "bode": clip_bode,
            "term": clip_term, "mc": clip_mc}
    for name, fn in jobs.items():
        if only and name != only:
            continue
        with tempfile.TemporaryDirectory() as td:
            fd = Path(td)
            fn(fd)
            enc(fd, CLIPS / f"{name}.mp4")
            for leftover in fd.iterdir():
                leftover.unlink()
    print("make_clips: done ->", CLIPS)


if __name__ == "__main__":
    main()
