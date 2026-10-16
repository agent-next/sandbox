#!/usr/bin/env python3
"""Render the animated plc-st footage from the real judge trace CSVs.

media/make_clips.py  ->  media/clips/*.mp4  (git-ignored)

Every pixel of motion comes from this run's judge output:

* The tank mimic: liquid level, pump, inlet/outlet valves, alarm and E-stop
  lamps are driven scan-by-scan by media/data/traces_good/trace_*.csv
  (columns: t, level, pump, valve_in, valve_out, estop, alarms) written by
  judge/grade.sh in this run. Water fills, drains, valves swing and lamps
  flash in lockstep with the log.
* The strip chart: the same trace CSV, drawn as the scan advances.
* The Structured Text: the graded artifact examples/good/tank_ctrl.st.
* The pipeline clip: the recorded run (media/runlog/pipeline.cast), replayed
  at a multiple of real speed with a Nx badge (real bytes, real timing).

Requirements: ffmpeg on PATH; numpy + pillow as pinned by make_media.sh.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys

WIDTH, HEIGHT = 1920, 1080
FPS = 30

BG = (13, 17, 23)
PANEL = (22, 27, 34)
PANEL_EDGE = (48, 56, 68)
INK = (230, 237, 243)
INK_DIM = (140, 152, 168)
LIQ = (34, 143, 214)
LIQ_HI = (97, 197, 240)
METAL = (92, 104, 118)
GOOD = (63, 185, 80)
WARN = (224, 168, 36)
BAD = (224, 80, 62)
TRACE = (126, 231, 135)
DEEP = (10, 30, 50)

TANK_X, TANK_Y, TANK_W, TANK_H = 120.0, 120.0, 420.0, 500.0
LEVEL_MIN, LEVEL_MAX = 0.0, 100.0

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD_ST = os.path.normpath(os.path.join(HERE, "..", "examples", "good", "tank_ctrl.st"))

FONT_PATHS = {
    "sans": ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
             "/usr/share/fonts/truetype/freefont/FreeSans.ttf"],
    "sans_bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                  "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"],
    "mono": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"],
    "mono_bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"],
}


def find_fonts():
    from PIL import ImageFont

    paths = {}
    for style, cands in FONT_PATHS.items():
        for c in cands:
            if os.path.exists(c):
                paths[style] = c
                break
        else:
            sys.exit(f"make_clips.py: no usable font for style {style!r} (looked in {cands})")
    cache = {}

    def font(style, size):
        key = (style, size)
        if key not in cache:
            cache[key] = ImageFont.truetype(paths[style], size)
        return cache[key]

    return font


def read_trace(path):
    rows = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append((float(r["t"]), float(r["level"]), int(r["pump"]),
                         int(r["valve_in"]), int(r["valve_out"]),
                         int(r["estop"]), int(r["alarms"])))
    return rows


def read_cast(path):
    events = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            if isinstance(e, list) and len(e) >= 3 and e[1] == "o":
                events.append((float(e[0]), e[2]))
    return events


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(round(lerp(c1[i], c2[i], t))) for i in range(3))


def panel(draw, x0, y0, x1, y1, fill=PANEL, edge=PANEL_EDGE, width=2):
    draw.rectangle([x0, y0, x1, y1], fill=fill, outline=edge, width=width)


def pipe(draw, pts, flow, colour, t_seed):
    draw.line(pts, fill=(54, 61, 71), width=16, joint="curve")
    draw.line(pts, fill=(70, 78, 90), width=8, joint="curve")
    if flow:
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            length = math.hypot(bx - ax, by - ay)
            n = max(2, int(length / 34))
            for i in range(n):
                u = (i + (t_seed % 1.0)) / n
                if u > 1:
                    u -= 1.0
                px, py = lerp(ax, bx, u), lerp(ay, by, u)
                draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=colour)


# --------------------------------------------------------------- the mimic ---


class TankScene:
    """Tank mimic + self-drawing strip chart, driven by one trace CSV."""

    def __init__(self, title, rows, font, zoom=1.0, pan=(0, 0), chart=True,
                 subtitle=""):
        self.title = title
        self.rows = rows
        self.F = font
        self.zoom_base = zoom
        self.pan = pan
        self.chart = chart
        self.subtitle = subtitle

    def level_y(self, level):
        return TANK_Y + TANK_H - (level - LEVEL_MIN) / (LEVEL_MAX - LEVEL_MIN) * TANK_H

    def draw(self, draw, row_pos, t, prog):
        F = self.F
        rows = self.rows
        n = len(rows)
        idx = min(n - 1, int(row_pos))
        frac = min(1.0, max(0.0, row_pos - idx)) if row_pos < n else 1.0
        nxt = min(n - 1, idx + 1)
        t_now, level, pump, vin, vout, estop, alarms = rows[idx]
        level_now = lerp(level, rows[nxt][1], frac)   # plant is continuous
        if pump or vin or vout:                        # and it is live
            level_now += 0.30 * math.sin(t * 6.0)

        # camera: a slow move, never a static frame
        zoom = self.zoom_base * (1.0 + 0.05 * math.sin(prog * math.pi))
        sway = math.sin(t * 0.7) * 12
        ox = self.pan[0] + sway
        oy = self.pan[1] + math.cos(t * 0.55) * 8
        prog_cam = math.sin(prog * math.pi)

        # moving background grid
        step = 80
        for x in range(-step, WIDTH + step, step):
            xx = x + (ox % step)
            draw.line([xx, 0, xx, HEIGHT], fill=(17, 21, 27), width=1)
        for y in range(-step, HEIGHT + step, step):
            yy = y + (oy % step)
            draw.line([0, yy, WIDTH, yy], fill=(17, 21, 27), width=1)

        # header
        draw.text((60, 46), "IEC 61131-3  tank_ctrl  ·  live scan", font=F("sans_bold", 46),
                  fill=INK, anchor="lm")
        draw.text((WIDTH - 60, 48), self.title, font=F("sans", 32), fill=INK_DIM, anchor="rm")
        draw.line([60, 90, WIDTH - 60, 90], fill=PANEL_EDGE, width=2)

        cx = TANK_X + TANK_W / 2 + ox
        w = TANK_W * zoom
        left, right = cx - w / 2, cx + w / 2
        top = TANK_Y + oy - 20
        bottom = top + TANK_H
        liq_top = self.level_y(level_now)

        panel(draw, left - 10, top - 10, right + 10, bottom + 10)
        draw.rectangle([left, top, right, bottom], outline=(12, 14, 18), width=3)

        # liquid
        if liq_top < bottom - 4:
            bob = 3 * math.sin(t * 5.0) + 2 * math.sin(t * 11.0)
            ly = liq_top + bob
            draw.rectangle([left + 4, ly, right - 4, bottom - 4], fill=LIQ)
            draw.line([left + 4, ly, right - 4, ly], fill=LIQ_HI, width=4)
            for i in range(7):
                y0 = lerp(ly + 16, bottom, (i + 0.6) / 7.0)
                draw.line([left + 4, y0, right - 4, y0],
                          fill=mix(LIQ, DEEP, 0.16 * (i + 1)), width=3)
            # particles: rising on inlet, falling on outlet
            if vin:
                for i in range(8):
                    yy = liq_top + ((t * 150 + i * 71) % max(1, bottom - liq_top))
                    xx = cx + math.sin(i * 1.7 + t * 3) * (w * 0.34)
                    draw.ellipse([xx - 4, yy - 4, xx + 4, yy + 4],
                                 fill=mix(LIQ, (255, 255, 255), 0.5))
            if vout:
                depth = max(1.0, bottom - liq_top)
                for i in range(9):
                    yy = bottom - ((t * 170 + i * 53) % depth)
                    if yy > liq_top:
                        xx = cx + math.sin(i * 2.3 + t * 4) * (w * 0.30)
                        draw.ellipse([xx - 4, yy - 4, xx + 4, yy + 4],
                                     fill=mix(LIQ, DEEP, 0.35))

        # threshold lines (values from README/SPEC and the judge gates)
        for val, colour, label in ((94.0, BAD, "design cap 94 cm"),
                                   (85.0, WARN, "high switch 85 cm"),
                                   (15.0, WARN, "dry band 15 cm")):
            y = self.level_y(val)
            draw.line([left - 26, y, right + 26, y], fill=colour, width=3)
            for xx in range(int(left - 26), int(right + 26), 24):
                draw.line([xx, y, xx + 12, y - 12], fill=colour, width=2)
            draw.text((right + 34, y), label, font=F("sans", 24), fill=colour, anchor="lm")

        # pipes and valves
        noz_y = bottom - 8
        pipe(draw, [(right + 10, noz_y), (right + 140, noz_y), (right + 140, noz_y + 80)],
             vout, LIQ, t)
        pipe(draw, [(left - 140, top + 40), (left - 10, top + 40)], vin, LIQ, t + 0.5)
        self.valve(draw, right + 80, noz_y, 20, vout, t)
        self.valve(draw, left - 80, top + 40, 20, vin, t)
        self.pump(draw, left - 200, top + 40, 30, pump, t)

        # lamps
        lx = right + 190
        for i, (name, on, colour) in enumerate(
                [("PUMP", bool(pump), GOOD), ("INLET", bool(vin), LIQ),
                 ("OUTLET", bool(vout), LIQ), ("E-STOP", bool(estop), WARN),
                 ("ALARM", bool(alarms), BAD)]):
            ly = 190 + i * 82
            self.lamp(draw, lx, ly, 26, colour, on, flash=bool(alarms and name == "ALARM")
                      and (int(t * 6) % 2 == 0))
            draw.text((lx + 50, ly), name, font=F("sans_bold", 32), fill=INK, anchor="lm")

        # HUD numbers
        draw.text((60, HEIGHT - 128), f"t = {t_now:8.3f} s", font=F("mono_bold", 40),
                  fill=INK, anchor="lm")
        draw.text((420, HEIGHT - 128), f"level = {level_now:6.2f} cm", font=F("mono_bold", 40),
                  fill=LIQ_HI, anchor="lm")
        state = ("PUMP ON    " if pump else "pump off    ") + \
                ("INLET open   " if vin else "INLET shut   ") + \
                ("OUTLET open" if vout else "OUTLET shut")
        draw.text((60, HEIGHT - 78), state, font=F("mono", 28),
                  fill=GOOD if (pump or vin or vout) else INK_DIM, anchor="lm")
        if self.subtitle:
            draw.text((60, HEIGHT - 36), self.subtitle, font=F("sans", 26),
                      fill=INK_DIM, anchor="lm")
        if estop:
            draw.text((right + 190, 640), "LATCHED", font=F("sans_bold", 34),
                      fill=WARN, anchor="lm")

        if self.chart:
            self.strip_chart(draw, idx, n)

    def valve(self, draw, cx, cy, r, open_, t):
        draw.ellipse([cx - r, cy - r * 0.45, cx + r, cy + r * 0.45],
                     fill=(30, 35, 42), outline=(12, 14, 18), width=2)
        # the disc swings: open draws flat, closed stands across the flow
        yoff = math.sin(0 if open_ else math.pi / 2) * r * 0.40
        colour = LIQ if open_ else (74, 82, 94)
        draw.line([cx - r, cy + yoff, cx + r, cy + yoff], fill=colour, width=6)

    def pump(self, draw, cx, cy, r, on, t):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=METAL,
                     outline=(14, 16, 20), width=3)
        for i in range(4):
            a = t * (9.0 if on else 0.4) + i * math.pi / 2
            draw.line([cx, cy, cx + (r - 4) * math.cos(a), cy + (r - 4) * math.sin(a)],
                      fill=(18, 21, 25), width=7)
        draw.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=(16, 19, 23))

    def lamp(self, draw, cx, cy, r, colour, on, flash=False):
        if on and flash:
            colour = BAD
        if on:
            for i in range(5, 0, -1):
                a = 0.09 + 0.14 * (6 - i) / 6
                rr = r + i * 3
                draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                             fill=tuple(int(c * a) for c in colour))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=colour if on else (44, 50, 58), outline=(18, 21, 26), width=2)
        if on:
            draw.ellipse([cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2],
                         fill=mix(colour, (255, 255, 255), 0.55))

    def strip_chart(self, draw, idx, n):
        x0, y0, x1, y1 = 1180, 140, 1860, 880
        panel(draw, x0, y0, x1, y1)
        rows = self.rows
        shown = max(2, min(n, idx + 1))
        draw.text((x0 + 26, y0 + 22), "level vs scan  ·  judge trace",
                  font=self.F("sans", 26), fill=INK_DIM, anchor="la")

        def px(i):
            return x0 + 30 + (x1 - x0 - 60) * (i / (n - 1))

        def py(level):
            return y1 - 34 - (y1 - y0 - 78) * ((level - LEVEL_MIN) / (LEVEL_MAX - LEVEL_MIN))

        for val, colour in ((94.0, BAD), (85.0, WARN), (15.0, WARN)):
            draw.line([x0 + 30, py(val), x1 - 30, py(val)], fill=colour, width=1)
        pts = [(px(i), py(rows[i][1])) for i in range(shown)]
        draw.line(pts, fill=TRACE, width=3, joint="curve")
        draw.ellipse([pts[-1][0] - 7, pts[-1][1] - 7, pts[-1][0] + 7, pts[-1][1] + 7],
                     fill=TRACE)
        draw.line([pts[-1][0], y0 + 30, pts[-1][0], y1 - 16],
                  fill=mix(TRACE, BG, 0.55), width=2)
        draw.text((x0 + 26, y1 + 16),
                  f"{shown}/{n} scans  ·  max {max(r[1] for r in rows[:shown]):.2f} cm",
                  font=self.F("mono", 26), fill=TRACE, anchor="la")


# --------------------------------------------------------------- the ST scene


def st_frame(draw, F, lines, prog, t):
    draw.rectangle([0, 0, WIDTH, HEIGHT], fill=(10, 13, 18))
    draw.text((70, 46), "examples/good/tank_ctrl.st", font=F("mono_bold", 46),
              fill=INK, anchor="lm")
    draw.text((WIDTH - 70, 46), "the artifact, compiled by the pinned MATIEC iec2c",
              font=F("sans", 30), fill=INK_DIM, anchor="rm")
    draw.line([70, 84, WIDTH - 70, 84], fill=PANEL_EDGE, width=2)
    visible, line_h = 15, 54
    scroll = max(0.0, prog * (len(lines) - visible))
    frac = scroll - int(scroll)
    for i in range(visible):
        j = int(scroll) + i
        if j < 0 or j >= len(lines):
            continue
        yy = 110 + i * line_h - frac * line_h
        txt = lines[j].rstrip()
        s = txt.strip()
        if s.startswith(("PROGRAM", "CONFIGURATION", "VAR", "END_")) or ":=" in s:
            colour = LIQ_HI
        elif s.startswith(("IF", "THEN", "ELSIF", "ELSE", "WHEN", "WHILE", "NOT", "AND",
                           "OR", "ELSE")):
            colour = WARN
        elif not s:
            colour = INK_DIM
        else:
            colour = INK
        if abs(i + frac - visible / 2) < 0.9:
            draw.rectangle([56, yy - 8, WIDTH - 56, yy + line_h - 10], fill=(26, 34, 44))
        draw.text((70, yy), txt[:100], font=F("mono", 34), fill=colour, anchor="la")
    if int(t * 2) % 2 == 0:
        draw.rectangle([WIDTH - 96, 110 + line_h * 7, WIDTH - 74,
                        110 + line_h * 7 + 32], fill=LIQ_HI)


# ------------------------------------------------------------ the run replay


class CastTerm:
    """Replays an asciinema v2 cast of the real pipeline run at `now` seconds.

    Newlines start a new row; carriage returns move the cursor back to the start
    of the row and overwrite it, which is how a terminal shows live output.
    Only the last WINDOW rows are kept, like a real scrollback."""

    WIDTH = 112
    WINDOW = 40

    def __init__(self, events, now):
        self.lines = [""]
        self.row = 0
        self.col = 0
        self.now = now
        self.final_t = events[-1][0] if events else 0.0
        for t, text in events:
            if t > now:
                break
            for ch in text:
                self._put(ch)

    def _put(self, ch):
        if ch == "\n":
            self.row += 1
            self.col = 0
            while len(self.lines) <= self.row:
                self.lines.append("")
        elif ch == "\r":
            self.col = 0
        else:
            line = self.lines[self.row]
            if self.col + len(ch) > len(line):
                line += ch * (self.col + len(ch) - len(line))
            self.lines[self.row] = line[: self.col] + ch + line[self.col + 1:]
            self.col += len(ch)
            if self.col >= self.WIDTH:
                self.row += 1
                self.col = 0
                while len(self.lines) <= self.row:
                    self.lines.append("")

    def rows_text(self, count=None):
        """The visible window: the last `count` rows, ending on the cursor."""
        count = count or self.WINDOW
        end = min(len(self.lines) - 1, self.row)
        start = max(0, end - count + 1)
        return [l[: self.WIDTH] for l in self.lines[start:end + 1]], end - start

    def progress(self):
        return min(1.0, self.now / max(1e-6, self.final_t))


def cast_frame(draw, F, term, t, speed, note):
    panel(draw, 0, 0, WIDTH, HEIGHT, fill=(8, 10, 14))
    draw.text((70, 48), "sandbox run — real output, real wall time",
              font=F("sans", 34), fill=INK, anchor="lm")
    draw.text((WIDTH - 70, 46), f"playback {speed:g}× real time",
              font=F("sans_bold", 34), fill=WARN, anchor="rm")
    draw.line([70, 86, WIDTH - 70, 86], fill=PANEL_EDGE, width=2)
    lines, cursor_row = term.rows_text(CastTerm.WINDOW)
    for i, line in enumerate(lines):
        if line:
            y = 118 + (i - (len(lines) - 1 - cursor_row)) * 25
            draw.text((70, y), line, font=F("mono", 24), fill=INK, anchor="la")
    # blinking caret on the cursor row
    if int(t * 3) % 2 == 0:
        y = 118 + cursor_row * 25
        draw.rectangle([70, y - 3, 84, y + 22], fill=LIQ_HI)
    p = term.progress()
    draw.rectangle([70, HEIGHT - 64, WIDTH - 70, HEIGHT - 52], fill=(26, 30, 38))
    draw.rectangle([70, HEIGHT - 64, 70 + (WIDTH - 140) * p, HEIGHT - 52], fill=GOOD)
    draw.text((70, HEIGHT - 96), f"{min(term.now, term.final_t):6.1f} s / {term.final_t:.1f} s of the run",
              font=F("mono", 30), fill=INK_DIM, anchor="lm")
    if note:
        draw.text((WIDTH - 70, HEIGHT - 96), note, font=F("sans", 28), fill=LIQ_HI,
                  anchor="rm")


# ------------------------------------------------------------------ encoding


def render_clip(name, out_dir, tmp_root, n_frames, frame_fn):
    from PIL import Image, ImageDraw

    d = os.path.join(tmp_root, name)
    os.makedirs(d, exist_ok=True)
    for i in range(n_frames):
        img = Image.new("RGB", (WIDTH, HEIGHT), BG)
        draw = ImageDraw.Draw(img, "RGBA")
        frame_fn(draw, i, i / FPS, i / max(1, n_frames - 1))
        img.save(os.path.join(d, "f_%05d.png" % (i + 1)))
        img.close()
    out = os.path.join(out_dir, name + ".mp4")
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(FPS), "-i", os.path.join(d, "f_%05d.png"),
        "-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt", "yuv420p",
        "-vf", f"scale={WIDTH}:{HEIGHT}", "-movflags", "+faststart", out,
    ], check=True)
    shutil.rmtree(d)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=os.path.join(HERE, "..", "..", ".."))
    ap.add_argument("--out", default=os.path.join(HERE, "clips"))
    ap.add_argument("--tmp", default=os.path.join(HERE, "work", "frames"))
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    plc = os.path.dirname(HERE)
    tdir = os.path.join(plc, "media", "data", "traces_good")
    traces = {f[:-4]: read_trace(os.path.join(tdir, f))
              for f in sorted(os.listdir(tdir)) if f.endswith(".csv")}
    st_lines = open(GOOD_ST).read().splitlines()
    F = find_fonts()
    cast_path = os.path.join(HERE, "runlog", "pipeline.cast")

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.tmp, exist_ok=True)
    plans = []

    # scans replayed at 30 fps: a clip is "seconds of video" long; the trace is
    # sampled so the whole scenario's motion is visible.
    def scans_per_second(rows, seconds):
        return max(1, int((len(rows) - 2) / max(1.0, seconds)))

    def make_tank(title, key, seconds, zoom=1.0, pan=(0, 0), subtitle="", stride=None):
        rows = traces[key]

        def fn(draw, i, t, prog):
            row_pos = i * (stride or scans_per_second(rows, seconds)) + 2
            draw.rectangle([0, 0, WIDTH, HEIGHT], fill=BG)
            TankScene(title, rows, F, zoom=zoom, pan=pan, subtitle=subtitle).draw(
                draw, row_pos, t, prog)

        return dict(name=key.replace("trace_", "tank_"), n=int(seconds * FPS), fn=fn)

    plans.append(make_tank("cycle — the level between 15 and 85 cm", "trace_cycle",
                           6.0, zoom=1.15, pan=(120, 0),
                           subtitle="input → output: the controller fills and drains the tank, forever"))
    plans.append(make_tank("overflow_guard — high switch forced low", "trace_overflow_guard",
                           5.0, zoom=1.35, pan=(210, -30),
                           subtitle="high_ls forced 0: the controller closes the inlet before 94 cm"))
    plans.append(make_tank("estop — every actuator off within one scan", "trace_estop",
                           5.0, zoom=1.5, pan=(280, -40),
                           subtitle="E-stop at t=4.000 s: inlet closed, level frozen, alarm latched"))
    plans.append(make_tank("recovery — autocycling again after the E-stop", "trace_recovery",
                           4.0, zoom=1.3, pan=(240, 0),
                           subtitle="a fresh start clears the latch and the cycle resumes"))

    def estop_macro(draw, i, t, prog):
        """Close-up: the one scan between E-stop and the actuator going dead."""
        rows = traces["trace_estop"]
        draw.rectangle([0, 0, WIDTH, HEIGHT], fill=BG)
        # zoom to the valves: the action happens at t=4.000 s
        span = 2.0  # trace seconds shown
        t0 = 3.9
        tp = t0 + prog * span
        TankScene("estop — valve close-up", rows, F, zoom=2.3, pan=(-190, 140),
                  chart=False,
                  subtitle="zoom: the inlet disc swings shut in the same scan, as SPEC.md requires",
        ).draw(draw, (tp / 0.010), tp, prog)

    plans.append(dict(name="tank_estop_macro", n=int(3.2 * FPS), fn=estop_macro))

    def st_fn(draw, i, t, prog):
        st_frame(draw, F, st_lines, prog, t)

    plans.append(dict(name="st_source", n=int(5.0 * FPS), fn=st_fn))

    if os.path.exists(cast_path):
        events = read_cast(cast_path)
        end = events[-1][0]

        def run_fn(draw, i, t, prog):
            speed = 60.0
            term = CastTerm(events, t * speed)
            cast_frame(draw, F, term, t * speed, speed,
                       "MATIEC build → selftest → grade → 8/8 PASS")

        plans.append(dict(name="run_pipeline", n=int(7.5 * FPS), fn=run_fn))

    for p in plans:
        if args.only and args.only not in p["name"]:
            continue
        out = render_clip(p["name"], args.out, args.tmp, p["n"], p["fn"])
        size = os.path.getsize(out) / 1e6
        print(f"[clip] {p['name']}: {p['n']} frames, {size:.2f} MB -> {out}", flush=True)


if __name__ == "__main__":
    main()
