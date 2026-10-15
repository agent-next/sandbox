#!/usr/bin/env python3
"""make_video.py -- render media/demo.mp4 (1920x1080, 30 fps, H.264) from
real judge outputs, following cookbook/DEMO-STANDARD.md (Media) and
media/STORYBOARD.md.

Every frame is real output of this repo's pinned run:

  judge_runs/traces/good/traj.npz     the 2400 per-step positions/velocities
                                      of the box and ball that
                                      judge/simulate.py sampled -- the exact
                                      numbers the gates graded
  judge_runs/verdicts/good.json       the final all-gates-pass verdict
  judge_runs/mutants/<name>.json      one verdict per single-edit mutant
  judge_runs/mutants/mutants/mutants.json   the mutant descriptions
  judge_runs/selftest.log             the real `bash judge/selftest.sh` stdout
  judge_runs/selftest.time            its measured wall seconds (for "Nx speed")
  examples/good/scene.usda            the authored input (shown verbatim)

The physical motion is drawn by render3d.py -- a deterministic software 3D
renderer of the simulator's own per-step samples (the pinned ovphysx wheel
ships no renderer; see STORYBOARD.md).  Charts, the terminal capture,
captions and HUD chips are composited on top of the moving render, never
replacing it: no slides, no stills, no Ken-Burns pans.  Hard cuts only --
no crossfades -- and the last 3 s are a static end card.

Frames go to frames/ (gitignored) and are encoded by ffmpeg into the
lossless master (media/master/demo.mp4, gitignored) and the web encode
(media/demo.mp4, -crf 18 -preset slow -pix_fmt yuv420p +faststart).

Deterministic: fixed camera maths, fixed light, no randomness.

Usage: python3 make_video.py [--fps 30] [--only SHOT] [--preview A,B,C]
         --preview renders single frames (at those seconds) instead of the
         whole video, for layout checks.
"""

import argparse
import json
import os
import subprocess
import textwrap

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

import render3d
from PIL import Image

MEDIA = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(MEDIA, "judge_runs")
VERDICTS = os.path.join(RUNS, "verdicts")
MUTANTS = os.path.join(RUNS, "mutants")
TRACES = os.path.join(RUNS, "traces", "good")
FRAMES = os.path.join(MEDIA, "frames")

W, H = 1920, 1080
FPS = 30
DT = 1.0 / 240.0
NSTEPS = 2400
G = 9.81

BOX_C = "#2a78d6"
BALL_C = "#eb6834"
GOOD_C = "#16c05a"
CRIT_C = "#ff6b5f"
INK = "#f4f6f9"
INK2 = "#b8bdc7"
MUTED = "#8b919d"
BG = "#0b0d11"
TERM_BG = "#05070a"
CHART_BG = "#11141a"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": INK,
    "axes.facecolor": CHART_BG,
    "figure.facecolor": CHART_BG,
    "axes.edgecolor": "#2c313c",
    "axes.labelcolor": INK2,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "grid.color": "#232833",
})

# ---------------------------------------------------------------------------
# storyboard: the cut list.  Hard cuts at every boundary; 9 cuts over 43 s
# = 2.1 cuts / 10 s (rule >= 0.8).  Slots per DEMO-STANDARD.md: hook,
# input->output, escalate (+ Nx-speed sandbox run), proof, end card.
# ---------------------------------------------------------------------------
SHOTS = [
    ("hook",       0.0,  2.5),
    ("input",      2.5,  9.0),
    ("freefall",   9.0,  13.5),
    ("contact",   13.5,  17.5),
    ("bounce",    17.5,  22.5),
    ("sandbox",   22.5,  29.5),
    ("energy",    29.5,  33.5),
    ("proof_pass", 33.5, 36.5),
    ("proof_kill", 36.5, 40.0),
    ("endcard",   40.0, 43.0),
]
TOTAL = SHOTS[-1][2]
BOUNDS = {n: (a, b) for n, a, b in SHOTS}

# left 3D evidence panel and right chart panel (x, y_top, w, h); the band
# under the panels carries the chips and the top band the caption bar.
# Layout numbers, top-origin pixels for panels and figure fractions for text.
# Caption sizing is derived from a measured cap height, not guessed: at dpi
# 100 one point is 100/72 px and DejaVu Sans Bold's cap height is 0.70 em,
# so cap_px = fontsize * 1.389 * 0.70 = 0.972 * fontsize.  The standard wants
# >= 4 % of the frame height (43.2 px); CAPTION_FRAC targets 5 % (54 px).
CAPTION_FRAC = 0.045
CAPTION_PT = round(CAPTION_FRAC * H / 0.972)     # 50 pt -> 48.6 px cap
CAPTION_PITCH = 0.070                            # line pitch, figure frac
CAPTION_TOP = 0.022                              # bar top edge, from the top
CAPTION_WRAP = 54                                # characters (fallback)
CHIP_PT = 34                                     # 33 px cap = 3.1 % (chip)
CHIP_ROWS = (0.112, 0.032)                       # bottom band; [0] is the top
PANEL_TOP = 200                                  # px from the top edge
PANEL_H = 690
L3D = (40, PANEL_TOP, 985, PANEL_H)              # left  evidence panel
RCH = (1035, PANEL_TOP, 845, PANEL_H)            # right chart panel
R3D = (640, round(640 * PANEL_H / 985))          # render size for a panel
RFULL = (640, 360)                               # render size, full frame


def need(path):
    if not os.path.exists(path):
        raise SystemExit(f"make_video: missing {path} -- run media/make_media.sh")
    return path


def load(path):
    return json.load(open(need(path)))


# ---------------------------------------------------------------------------
# canvas / compositing
# ---------------------------------------------------------------------------
def hex_rgb(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], np.uint8)


def new_canvas(rgb=BG):
    c = np.empty((H, W, 3), np.uint8)
    c[:, :] = hex_rgb(rgb) if isinstance(rgb, str) else np.array(rgb, np.uint8)
    return c


def scale_nn(img, w, h):
    ih, iw = img.shape[:2]
    yi = np.clip((np.arange(h) * ih / h).astype(int), 0, ih - 1)
    xi = np.clip((np.arange(w) * iw / w).astype(int), 0, iw - 1)
    return img[yi][:, xi]


def blit(canvas, img, x, y):
    ih, iw = img.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + iw, W), min(y + ih, H)
    if x1 <= x0 or y1 <= y0:
        return
    canvas[y0:y1, x0:x1] = img[y0 - y:y1 - y, x0 - x:x1 - x]


def overlay(canvas, draw):
    """Alpha-composite a transparent matplotlib figure over the canvas."""
    fig = plt.figure(figsize=(W / 100.0, H / 100.0), dpi=100)
    fig.patch.set_alpha(0.0)
    draw(fig)
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba()).astype(np.float32)
    plt.close(fig)
    a = buf[..., 3:4] / 255.0
    canvas[:] = np.clip(canvas.astype(np.float32) * (1.0 - a)
                        + buf[..., :3] * a, 0, 255).astype(np.uint8)
    return canvas


TEXT_W = {}


def text_px(fig, text, size, weight, family):
    """Measured advance width of one line, in pixels (real font metrics)."""
    key = (text, size, weight, family)
    if key not in TEXT_W:
        t = fig.text(0, 0, text, fontsize=size, fontweight=weight,
                     family=family)
        bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
        t.remove()
        TEXT_W[key] = bb.width
    return TEXT_W[key]


def wrap_px(fig, text, size, max_px, weight="bold", family="DejaVu Sans"):
    """Greedy word wrap on measured widths, so text can never run off the
    frame the way a character-count wrap does (digits and wide glyphs)."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if cur and text_px(fig, cand, size, weight, family) > max_px:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines or [""]


def caption(fig, text, accent=GOOD_C):
    """Top caption: a dark bar carrying large, wrapped, high-contrast text.

    The font size is chosen so the cap height is CAPTION_FRAC of the frame
    height (56 pt -> 54 px, >= the standard's 43.2 px); the wrap is measured,
    not counted, so no line can leave the frame."""
    fig.canvas.draw()
    lines = wrap_px(fig, text, CAPTION_PT, W * (1 - 2 * 0.026) - 8)
    if len(lines) > 2:      # the panels start at PANEL_TOP; a taller bar
        # would cover them.  Shorten the caption, don't shrink the font.
        raise SystemExit(f"make_video: caption wraps to {len(lines)} lines "
                         f"(max 2): {text!r}")
    height = CAPTION_TOP + (len(lines) - 1) * CAPTION_PITCH + 0.062
    y0 = 1.0 - height
    fig.patches.append(Rectangle((0.0, y0), 1.0, height,
                                 transform=fig.transFigure,
                                 facecolor="#000000", alpha=0.74,
                                 edgecolor="none"))
    fig.patches.append(Rectangle((0.0, y0), 0.0055, height,
                                 transform=fig.transFigure,
                                 facecolor=accent, edgecolor="none"))
    for i, ln in enumerate(lines):
        fig.text(0.026, 1.0 - CAPTION_TOP - i * CAPTION_PITCH, ln,
                 fontsize=CAPTION_PT, color=INK, fontweight="bold",
                 ha="left", va="top", family="DejaVu Sans")


def bar_height(text, x=0.026, accent=0.0):
    """Figure height the caption bar will occupy for `text` (fractions)."""
    n = len(textwrap.wrap(text, CAPTION_WRAP)) or 1
    return CAPTION_TOP + (n - 1) * CAPTION_PITCH + 0.062


def chip(fig, x, y, text, size=CHIP_PT, color=INK, alpha=0.72, maxw=None):
    """A HUD chip: a rounded dark box sized to the measured text, anchored
    by its bottom-left corner at (x, y) in figure fractions.  Long text
    wraps (at most two lines) instead of running off the frame."""
    fig.canvas.draw()
    avail = (maxw or (W - 40)) - 2 * 15
    lines = wrap_px(fig, text, size, avail)
    if len(lines) > 2:                      # keep chips compact: split even
        half = (len(lines) + 1) // 2
        lines = [" ".join(lines[:half]), " ".join(lines[half:])]
    wpx = max(text_px(fig, ln, size, "bold", "DejaVu Sans") for ln in lines)
    lh = size * 1.42
    hpx = lh * len(lines) + 16
    fig.patches.append(FancyBboxPatch(
        (x, y), (wpx + 30) / W, hpx / H,
        boxstyle="round,pad=0.0,rounding_size=0.008",
        transform=fig.transFigure, facecolor="#000000", alpha=alpha,
        edgecolor="none", mutation_aspect=W / H))
    for i, ln in enumerate(lines):
        fig.text(x + 15.0 / W, (y + hpx / H) - ((i + 0.5) * lh) / H, ln,
                 fontsize=size, color=color, fontweight="bold", ha="left",
                 va="center", family="DejaVu Sans")


def hud_chips(fig, rows, x=0.036, maxw=None):
    """A stack of chips in the band below the panels; rows[0] is the top."""
    for i, (text, color) in enumerate(rows):
        chip(fig, x, CHIP_ROWS[i], text, color=color, maxw=maxw)


def panel_box(fig, x, y, w, h, alpha=0.80, edge="#2c313c"):
    fig.patches.append(FancyBboxPatch(
        (x, y), w, h, transform=fig.transFigure,
        boxstyle="round,pad=0.0,rounding_size=0.010",
        facecolor="#0b0d11", alpha=alpha, edgecolor=edge, linewidth=1.4,
        mutation_aspect=W / H))


# ---------------------------------------------------------------------------
# offscreen images (code panel, terminal, charts)
# ---------------------------------------------------------------------------
def fig_to_array(fig):
    fig.canvas.draw()
    rgba = np.asarray(fig.canvas.buffer_rgba())
    plt.close(fig)
    return rgba[..., :3].copy()


def render_text_image(lines, w, fontsize, bg, color, ratio=1.62, mono=True,
                      wrap=None, pad=18):
    """A full-height image of `lines` at width w (no clipping)."""
    if wrap:
        wrapped = []
        for ln in lines:
            wrapped += textwrap.wrap(ln, wrap) or [""]
        lines = wrapped
    lh = int(fontsize * ratio)
    h = lh * len(lines) + 2 * pad
    fig = plt.figure(figsize=(w / 100.0, h / 100.0), dpi=100)
    fig.patch.set_facecolor(bg)
    fig.add_axes((0, 0, 1, 1)).axis("off")
    fig.text(pad / w, 1.0 - pad / h, "\n".join(lines), fontsize=fontsize,
             family="DejaVu Sans Mono" if mono else "DejaVu Sans",
             color=color, va="top", ha="left", linespacing=ratio)
    return fig_to_array(fig)


def scroll_window(full, win_h, u, center=True):
    """Crop a win_h-tall window out of a tall image, scrolled by fraction u."""
    total = full.shape[0]
    if total <= win_h:
        pad_top = (win_h - total) // 2 if center else 0
        out = np.empty((win_h, full.shape[1], 3), np.uint8)
        out[:, :] = full[0, 0]  # pad with the image's own background colour
        out[pad_top:pad_top + total] = full
        return out
    off = int(round(u * (total - win_h)))
    return full[off:off + win_h]


def render_chart(w, h, draw, dpi=110):
    fig = plt.figure(figsize=(w / dpi, h / dpi), dpi=dpi)
    fig.patch.set_facecolor(CHART_BG)
    draw(fig)
    return fig_to_array(fig)


def chart_axes(fig, rect=(0.155, 0.12, 0.815, 0.74)):
    ax = fig.add_axes(rect)
    ax.set_facecolor(CHART_BG)
    ax.grid(True, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    return ax


# ---------------------------------------------------------------------------
# data accessors
# ---------------------------------------------------------------------------
GATE_ORDER = ["G1_loads", "G2_freefall", "G3_contact_time", "G4_resting",
              "G5_bounce_apex", "G6_energy", "G7_contract"]
GATE_LABEL = {"G1_loads": "G1\nloads", "G2_freefall": "G2\nfree fall",
              "G3_contact_time": "G3\ncontact", "G4_resting": "G4\nresting",
              "G5_bounce_apex": "G5\nbounce", "G6_energy": "G6\nenergy",
              "G7_contract": "G7\ncontract"}


def body_gate(verdict, gate):
    parts = [verdict.get("bodies", {}).get(b, {}).get(gate)
             for b in ("Box", "Ball")]
    parts = [p for p in parts if p is not None]
    for p in parts:
        if not p.get("passed", False):
            return p
    return parts[0] if parts else None


def contact_index(vy):
    for i in range(1, len(vy)):
        if vy[i - 1] < 0.0 < vy[i]:
            return i
    return None


class Scene:
    def __init__(self):
        self.good = load(os.path.join(VERDICTS, "good.json"))
        self.traj = np.load(need(os.path.join(TRACES, "traj.npz")))
        self.box_y, self.ball_y = self.traj["box_y"], self.traj["ball_y"]
        self.box_vy, self.ball_vy = self.traj["box_vy"], self.traj["ball_vy"]
        self.muts_desc = load(os.path.join(MUTANTS, "mutants", "mutants.json"))
        self.muts = {n: load(os.path.join(MUTANTS, f"{n}.json"))
                     for n in self.muts_desc}
        self.log = open(need(os.path.join(RUNS, "selftest.log")),
                        encoding="utf-8", errors="replace").read().splitlines()
        self.wall_s = float(open(need(os.path.join(RUNS, "selftest.time"))
                                 ).read().strip())
        self.usd = open(os.path.join(MEDIA, os.pardir, "examples", "good",
                                     "scene.usda")).read().splitlines()
        self.t = np.arange(NSTEPS) * DT
        self._cache = {}

    def det(self, body, gate, key=None):
        detail = self.good["bodies"][body][gate]["detail"]
        return detail if key is None else detail[key]

    def cached(self, key, make):
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]


# ---------------------------------------------------------------------------
# 3D helpers
# ---------------------------------------------------------------------------
def cam3d(az, el, dist, target=(0.0, 0.42, 0.0), fov=42.0, full=False):
    w, h = RFULL if full else R3D
    return render3d.orbit_camera(az, el, dist, target=target, fov_y_deg=fov,
                                 w=w, h=h)


def render3d_shot(scn, sim_t, cam, ghost=False, apex=False, rest=True,
                  trail_body=None):
    k = int(np.clip(round(sim_t / DT), 0, NSTEPS - 1))
    ghost_y = max(0.8 - 0.5 * G * (k * DT) ** 2, 0.10) if ghost else None
    trail = None
    if trail_body is not None:
        ys = scn.box_y if trail_body == "box" else scn.ball_y
        step = max(1, k // 24)
        idx = np.arange(0, k + 1, step) if k else np.arange(1)
        x = render3d.BOX_X if trail_body == "box" else render3d.BALL_X
        trail = [(x, float(ys[int(i)]), 0.0) for i in idx]
    return render3d.render_frame(
        cam, float(scn.box_y[k]), float(scn.ball_y[k]), ghost_box_y=ghost_y,
        apex_line=(0.375 if apex else None), rest_line=rest, trail=trail)


def two_panel(scn, sim_t, cam, chart, ghost=False, apex=False,
              trail_body=None):
    c = new_canvas()
    img = render3d_shot(scn, sim_t, cam, ghost=ghost, apex=apex,
                        trail_body=trail_body)
    blit(c, scale_nn(img, L3D[2], L3D[3]), L3D[0], L3D[1])
    blit(c, chart, RCH[0], RCH[1])
    return c


# ===========================================================================
# SHOTS
# ===========================================================================
def shot_hook(scn, t, t0, t1):
    """0-2.5 s -- hook: the finished result fills the frame (both bodies
    settled at the geometric resting height), camera slowly orbiting.
    No title card, logo, terminal or blank chart."""
    u = (t - t0) / (t1 - t0)
    cam = cam3d(38.0 + 8.0 * u, 16.0, 2.5, target=(0.0, 0.34, 0.0), full=True)
    img = render3d_shot(scn, 10.0, cam)
    c = new_canvas()
    blit(c, scale_nn(img, W, H), 0, 0)

    def hud(fig):
        caption(fig, "all 7 gates pass - 2 400 PhysX steps vs closed-form "
                     "Newtonian mechanics")
        hud_chips(fig, [
            (f"box rests at {scn.det('Box','G4_resting','y_final_m'):.2f} m "
             f"(error {scn.det('Box','G4_resting','error_mm'):.1f} mm, "
             f"rule <= 1 mm)", GOOD_C),
            (f"ball apex {scn.det('Ball','G5_bounce_apex','apex_sim_m'):.4f} m "
             f"vs e²Δh = {scn.det('Ball','G5_bounce_apex','apex_analytic_m'):.3f} m "
             f"({scn.det('Ball','G5_bounce_apex','rel_error')*100:.2f} %, "
             f"rule <= 10 %)", GOOD_C),
        ])

    return overlay(c, hud)


def shot_input(scn, t, t0, t1):
    """2.5-9 s -- input -> output: the authored USD text on the left, the
    same scene simulated on the right (0.15x slow motion) with the analytic
    free-fall ghost."""
    u = (t - t0) / (t1 - t0)
    sim_t = 1.2 * u
    c = new_canvas()

    # left: the authored scene itself, verbatim, scrolling past
    code = scn.cached("code", lambda: render_text_image(
        scn.usd, L3D[2], 21, "#0d1017", "#cfd6e0", ratio=1.5))
    blit(c, scroll_window(code, L3D[3], u), L3D[0], L3D[1])

    # right: that scene stepped by PhysX, with the analytic ghost overlaid
    cam = cam3d(34.0 + 5.0 * u, 15.0, 2.45)
    img = render3d_shot(scn, sim_t, cam, ghost=True)
    blit(c, scale_nn(img, RCH[2], RCH[3]), RCH[0], RCH[1])

    def hud(fig):
        caption(fig, "input: one authored USD scene -> the exact trajectory "
                     "the judge grades", accent=BOX_C)
        hud_chips(fig, [
            ("right panel: 0.15× slow motion, ghost = y₀ - g t²/2", INK2),
            ("green line = y_rest = 0.10 m", GOOD_C),
        ], x=0.545, maxw=880)

    return overlay(c, hud)


def chart_freefall(scn, upto):
    def draw(fig):
        ax = chart_axes(fig)
        n = int(np.clip(upto / DT, 12, int(0.42 / DT)))
        tt = scn.t[:n]
        ax.plot(tt, scn.box_y[:n], color=BOX_C, lw=3.4, label="PhysX box y(t)")
        ax.plot(tt, 0.8 - 0.5 * G * tt ** 2, color="#c8ccd6", lw=2.0, ls="--",
                label="analytic y₀ - g t²/2")
        ax.axhline(0.10, color=GOOD_C, lw=1.6)
        ax.text(0.006, 0.115, "y_rest = 0.10 m", color=GOOD_C, fontsize=16)
        ax.set_xlabel("t (s)", fontsize=18)
        ax.set_ylabel("box centre height (m)", fontsize=18)
        ax.set_title("G2  free fall: sim vs closed form", fontsize=23,
                     color=INK, pad=12)
        ax.legend(fontsize=16, loc="upper right", framealpha=0.3)
        ax.tick_params(labelsize=15)
        ax.set_xlim(0, 0.42)
        ax.set_ylim(0, 0.92)
    return render_chart(RCH[2], RCH[3], draw)


def shot_freefall(scn, t, t0, t1):
    """9-13.5 s -- escalate: close 3/4 camera on the falling box with the
    analytic ghost and trail; the G2 residual panel alongside."""
    u = (t - t0) / (t1 - t0)
    sim_t = 0.055 + 0.325 * u
    cam = cam3d(-16.0 + 14.0 * u, 11.0, 1.55, target=(-0.5, 0.50, 0.0),
                fov=38.0)
    c = two_panel(scn, sim_t, cam, chart_freefall(scn, sim_t), ghost=True,
                  trail_body="box")

    def hud(fig):
        d = scn.det("Box", "G2_freefall")
        caption(fig, f"G2 free fall: fitted g = {d['g_fit']:.2f} m/s², "
                     f"max residual {d['max_abs_residual_m']:.4f} m")
        hud_chips(fig, [
            (f"rule: |g - 9.81| <= 1 %, residual <= 1 % + 0.5 mm", GOOD_C),
            (f"least-squares fit over {d['fit_start_s']:.2f}-"
             f"{d['fit_end_s']:.2f} s, 2 400 steps at 240 Hz", INK2),
        ])

    return overlay(c, hud)


def chart_contact(scn, upto):
    def draw(fig):
        ax = chart_axes(fig, (0.17, 0.14, 0.80, 0.70))
        tc = scn.det("Box", "G3_contact_time", "t_contact_sim_s")
        ta = scn.det("Box", "G3_contact_time", "t_contact_analytic_s")
        ax.axvspan(ta - 1 / 240.0, ta + 1 / 240.0, color=GOOD_C, alpha=0.18)
        n = int(np.clip(upto / DT, 12, int(0.44 / DT)))
        tt = scn.t[:n]
        ax.plot(tt, scn.box_vy[:n], color=BOX_C, lw=3.2,
                label="box vᵧ(t) (PhysX)")
        ax.axvline(ta, color=GOOD_C, lw=2.0, ls="--",
                   label="analytic √(2Δh/g)")
        ax.set_xlabel("t (s)", fontsize=18)
        ax.set_ylabel("box vertical velocity (m/s)", fontsize=18)
        ax.set_title("G3  first contact: velocity reversal", fontsize=23,
                     color=INK, pad=12)
        ax.legend(fontsize=16, loc="lower left", framealpha=0.3)
        ax.tick_params(labelsize=15)
        ax.set_xlim(0.30, 0.44)
        ax.set_ylim(-4.4, 1.9)
        ax.text(0.985, 0.06, "green band = ±1 frame", color=GOOD_C,
                fontsize=15, ha="right", transform=ax.transAxes)
    return render_chart(RCH[2], RCH[3], draw)


def shot_contact(scn, t, t0, t1):
    """13.5-17.5 s -- escalate: ground-level close-up of the box meeting the
    ground, the G3 contact band alongside."""
    u = (t - t0) / (t1 - t0)
    sim_t = 0.300 + 0.135 * u
    cam = cam3d(-50.0 + 9.0 * u, 6.0, 1.0, target=(-0.5, 0.17, 0.0), fov=40.0)
    c = two_panel(scn, sim_t, cam, chart_contact(scn, sim_t))

    def hud(fig):
        d = scn.det("Box", "G3_contact_time")
        caption(fig, f"G3 contact: {d['t_contact_sim_s']:.4f} s vs "
                     f"√(2Δh/g) = {d['t_contact_analytic_s']:.4f} s - "
                     f"Δ {d['delta_frames']:.2f} frame")
        hud_chips(fig, [
            ("rule: first contact within 1 frame of analytic", GOOD_C),
        ])

    return overlay(c, hud)


def chart_bounce(scn, upto):
    def draw(fig):
        ax = chart_axes(fig)
        n = int(np.clip(upto / DT, 12, int(1.15 / DT)))
        tt = scn.t[:n]
        ax.plot(tt, scn.ball_y[:n], color=BALL_C, lw=3.4, label="ball y(t)")
        ax.axhline(0.375, color=GOOD_C, lw=2.0, ls="--",
                   label="analytic apex = y_rest + e²Δh")
        ax.axhline(0.10, color="#c8ccd6", lw=1.2, ls=":")
        ax.text(0.012, 0.128, "y_rest = 0.10 m", color=MUTED, fontsize=15)
        ax.set_xlabel("t (s)", fontsize=18)
        ax.set_ylabel("ball centre height (m)", fontsize=18)
        ax.set_title("G5  first bounce apex (e = 0.50)", fontsize=23,
                     color=INK, pad=12)
        ax.legend(fontsize=16, loc="upper right", framealpha=0.3)
        ax.tick_params(labelsize=15)
        ax.set_xlim(0, 1.15)
        ax.set_ylim(0, 1.32)
    return render_chart(RCH[2], RCH[3], draw)


def shot_bounce(scn, t, t0, t1):
    """17.5-22.5 s -- escalate: the camera tracks the ball's first rebound
    against the analytic apex line."""
    u = (t - t0) / (t1 - t0)
    sim_t = 0.40 + 0.42 * u
    k = int(np.clip(round(sim_t / DT), 0, NSTEPS - 1))
    y_mid = float(scn.ball_y[k]) * 0.55 + 0.10
    cam = cam3d(56.0 + 14.0 * u, 12.0, 1.35, target=(0.5, y_mid, 0.0),
                fov=38.0)
    c = two_panel(scn, sim_t, cam, chart_bounce(scn, sim_t), apex=True,
                  trail_body="ball")

    def hud(fig):
        caption(fig, f"G5 bounce: apex "
                     f"{scn.det('Ball','G5_bounce_apex','apex_sim_m'):.4f} m "
                     f"vs e²Δh = "
                     f"{scn.det('Ball','G5_bounce_apex','apex_analytic_m'):.3f} m "
                     f"- {scn.det('Ball','G5_bounce_apex','rel_error')*100:.2f} % "
                     "(rule: <= 10 %)")

    return overlay(c, hud)


def shot_sandbox(scn, t, t0, t1):
    """22.5-29.5 s -- escalate: the real `bash judge/selftest.sh` sandbox run,
    sped up and labelled "Nx speed" (measured wall time / clip length).  The
    terminal capture is cropped to the active region."""
    u = (t - t0) / (t1 - t0)
    dur = t1 - t0
    c = new_canvas(TERM_BG)
    text = scn.cached("term", lambda: render_text_image(
        scn.log, L3D[2] + RCH[2], 28, TERM_BG, "#cfe3d2", ratio=1.5, wrap=126))
    win = scroll_window(text, PANEL_H, u)
    blit(c, win, 40, PANEL_TOP)

    speed = max(1, round(scn.wall_s / dur))
    bar_w = int(u * (L3D[2] + RCH[2]))

    def hud(fig):
        # bottom command bar + progress
        fig.patches.append(Rectangle((40 / W, 0.062), (L3D[2] + RCH[2]) / W,
                                     0.020, transform=fig.transFigure,
                                     facecolor="#1b2027", edgecolor="none"))
        fig.patches.append(Rectangle((40 / W, 0.062), bar_w / W, 0.020,
                                     transform=fig.transFigure,
                                     facecolor=GOOD_C, edgecolor="none"))
        fig.text(40 / W, 0.032, "$ bash judge/selftest.sh", fontsize=30,
                 color=GOOD_C, family="DejaVu Sans Mono", fontweight="bold",
                 ha="left", va="center")
        fig.text((W - 40) / W, 0.032,
                 f"measured {scn.wall_s:.0f} s wall clock -> {dur:.0f} s clip",
                 fontsize=26, color=INK2, ha="right", va="center")
        chip(fig, 0.62, 0.112, f"{speed}× speed", 52, color="#ffd23f")
        caption(fig, "real sandbox run: bash judge/selftest.sh - the judge "
                     "names the gate that kills every mutant")

    return overlay(c, hud)


def chart_energy(scn, upto):
    def draw(fig):
        ax = chart_axes(fig)
        n = int(np.clip(upto / DT, 12, NSTEPS))
        tt = scn.t[:n]
        e0 = scn.det("Box", "G6_energy", "E0_J")
        E = 4.0 * G * scn.box_y[:n] + 0.5 * 4.0 * scn.box_vy[:n] ** 2
        ax.plot(tt, E / e0, color=BOX_C, lw=3.0, label="box E/E₀")
        e0b = scn.det("Ball", "G6_energy", "E0_J")
        Eb = 1.0 * G * scn.ball_y[:n] + 0.5 * 1.0 * scn.ball_vy[:n] ** 2
        ax.plot(tt, Eb / e0b, color=BALL_C, lw=3.0, label="ball E/E₀")
        ax.axhline(1.0, color="#c8ccd6", lw=1.4, ls=":")
        ax.axhspan(1.0, 1.005, color=CRIT_C, alpha=0.20)
        ax.text(max(upto, 0.2) - 0.05, 1.02, "+0.5 % E₀ limit", color=CRIT_C,
                fontsize=15, ha="right")
        ax.set_xlabel("t (s)", fontsize=18)
        ax.set_ylabel("mechanical energy / E₀", fontsize=18)
        ax.set_title("G6  energy: never increases", fontsize=23, color=INK,
                     pad=12)
        ax.legend(fontsize=16, loc="lower left", framealpha=0.3)
        ax.tick_params(labelsize=15)
        ax.set_xlim(0, 10.0)
        ax.set_ylim(0, 1.12)
    return render_chart(RCH[2], RCH[3], draw)


def shot_energy(scn, t, t0, t1):
    """29.5-33.5 s -- escalate: both bodies bouncing to rest beside the
    measured energy curve with its +0.5 % pass band."""
    u = (t - t0) / (t1 - t0)
    sim_t = 10.0 * u
    cam = cam3d(30.0 + 12.0 * u, 14.0, 2.1)
    c = two_panel(scn, sim_t, cam, chart_energy(scn, sim_t))

    def hud(fig):
        d = scn.det("Box", "G6_energy")
        caption(fig, f"G6 energy: E = mgy + ½mv² never gains more than "
                     f"{100 * d['max_step_gain_J'] / d['E0_J']:.3f} % of E₀"
                     "  (limit 0.5 %)")

    return overlay(c, hud)


def shot_proof_pass(scn, t, t0, t1):
    """33.5-36.5 s -- proof: the judge PASS verdict as a HUD over the still
    moving result (never a text slide)."""
    u = (t - t0) / (t1 - t0)
    cam = cam3d(-30.0 + 16.0 * u, 13.0, 1.9, target=(0.0, 0.30, 0.0),
                full=True)
    img = render3d_shot(scn, 10.0, cam)
    c = new_canvas()
    blit(c, scale_nn(img, W, H), 0, 0)
    g1, g2 = scn.det("Box", "G1_loads"), scn.det("Box", "G2_freefall")
    g3 = max(scn.det("Box", "G3_contact_time")["delta_frames"],
             scn.det("Ball", "G3_contact_time")["delta_frames"])
    g4 = scn.det("Box", "G4_resting")
    g5 = scn.det("Ball", "G5_bounce_apex")
    g6 = scn.det("Box", "G6_energy")
    g7 = scn.good["gates"]["G7_contract"]["detail"]["violations"]
    rows = [
        ("G1 loads", f"{g1['steps_sampled']} steps, mass "
                     f"{g1['mass_kg']:.1f} / {scn.det('Ball','G1_loads')['mass_kg']:.1f} kg"),
        ("G2 free fall", f"g fit {g2['g_fit']:.2f}, residual "
                         f"{g2['max_abs_residual_m']:.4f} m"),
        ("G3 contact", f"Δ {g3:.2f} frame (box and ball)"),
        ("G4 resting", f"{g4['y_final_m']:.2f} m, error {g4['error_mm']:.1f} mm"),
        ("G5 bounce apex", f"{g5['apex_sim_m']:.4f} m ({100*g5['rel_error']:.2f} %)"),
        ("G6 energy", f"max gain {100*g6['max_step_gain_J']/g6['E0_J']:.3f} % E₀"),
        ("G7 contract", f"{len(g7)} violations"),
    ]

    def hud(fig):
        panel_box(fig, 0.20, 0.115, 0.60, 0.80, alpha=0.88)
        fig.text(0.5, 0.845, "verdict: PASS", fontsize=62, color=GOOD_C,
                 fontweight="bold", ha="center", va="center")
        fig.text(0.5, 0.775, "every gate a number, every number inside its "
                 "rule", fontsize=25, color=INK2, ha="center", va="center")
        # the verdict reveals gate by gate, so the panel is never static
        n_show = min(len(rows), 1 + int(u * len(rows)))
        for i, (name, val) in enumerate(rows[:n_show]):
            y = 0.695 - i * 0.082
            fig.patches.append(Rectangle((0.212, y - 0.038), 0.0055, 0.076,
                                         transform=fig.transFigure,
                                         facecolor=GOOD_C, edgecolor="none"))
            fig.text(0.235, y, name, fontsize=29, color=INK,
                     fontweight="bold", ha="left", va="center")
            fig.text(0.765, y, val, fontsize=27, color=INK2, ha="right",
                     va="center")
            fig.patches.append(Rectangle((0.235, y - 0.036), 0.53, 0.0012,
                                         transform=fig.transFigure,
                                         facecolor="#2c313c", edgecolor="none"))
        caption(fig, "the judge re-derives every number from the simulator's "
                     "own output files - nothing asks PhysX if PhysX is right")

    return overlay(c, hud)


def shot_proof_kill(scn, t, t0, t1):
    """36.5-40 s -- proof: the mutant x gate kill matrix as a HUD over the
    moving result."""
    u = (t - t0) / (t1 - t0)
    cam = cam3d(24.0 + 20.0 * u, 15.0, 2.2, target=(0.0, 0.34, 0.0), full=True)
    img = render3d_shot(scn, 10.0, cam)
    c = new_canvas()
    blit(c, scale_nn(img, W, H), 0, 0)
    names = sorted(scn.muts)
    shown = min(len(names), 11)
    killed = sum(1 for v in scn.muts.values()
                 if any(not r.get("passed", False)
                        for r in v.get("gates", {}).values()))
    x0, y0 = 0.300, 0.135
    cw, rh = (0.46 / len(GATE_ORDER)), 0.052

    def hud(fig):
        panel_box(fig, 0.035, 0.10, 0.93, 0.73, alpha=0.88)
        fig.text(0.5, 0.775,
                 f"self-test: {len(names)} single-edit mutants, "
                 f"{killed} killed by a gate = "
                 f"{round(100 * killed / len(names))} %", fontsize=40,
                 color=INK, fontweight="bold", ha="center", va="center")
        for ci, g in enumerate(GATE_ORDER):
            fig.text(x0 + cw * (ci + 0.5), y0 + rh * shown + 0.012,
                     GATE_LABEL[g], fontsize=19, color=INK2, ha="center",
                     va="bottom")
        for ri, n in enumerate(names[:shown]):
            y = y0 + rh * (shown - 1 - ri)
            fig.text(x0 - 0.014, y + rh / 2, n, fontsize=21, color=INK,
                     ha="right", va="center")
            v = scn.muts[n]
            failed = sorted(g for g, r in v.get("gates", {}).items()
                            if not r.get("passed", False))
            for ci, g in enumerate(GATE_ORDER):
                gx = v.get("gates", {}).get(g)
                ok = True if gx is None else bool(gx.get("passed", False))
                fig.patches.append(Rectangle(
                    (x0 + cw * ci + 0.0015, y + 0.004), cw - 0.003,
                    rh - 0.008, transform=fig.transFigure,
                    facecolor="#123322" if ok else "#3a1717",
                    edgecolor="#2c313c", linewidth=0.8))
                fig.text(x0 + cw * (ci + 0.5), y + rh / 2,
                         "pass" if ok else "FAIL", fontsize=15,
                         color=GOOD_C if ok else CRIT_C, ha="center",
                         va="center", fontweight="bold")
            fig.text(x0 + cw * len(GATE_ORDER) + 0.016, y + rh / 2,
                     f"killed by {len(failed)} gate"
                     f"{'s' if len(failed) != 1 else ''}", fontsize=19,
                     color=CRIT_C, ha="left", va="center")
        caption(fig, "the self-test: every cheat attempt is named by the gate "
                     "that kills it - a crash does not count")

    return overlay(c, hud)


def shot_endcard(scn, t, t0, t1):
    """40-43 s -- static end card: the one-line launch."""
    c = new_canvas("#06070a")

    def hud(fig):
        fig.patches.append(Rectangle((0.499, 0.30), 0.0006, 0.40,
                                     transform=fig.transFigure,
                                     facecolor=GOOD_C, edgecolor="none"))
        fig.text(0.5, 0.560, "python3 cookbook/physx-drop-test/run.py",
                 fontsize=56, color=INK, family="DejaVu Sans Mono",
                 fontweight="bold", ha="center", va="center")
        fig.text(0.5, 0.455, "one command: sandbox, pinned PhysX, judge, "
                 "verdict", fontsize=30, color=INK2, ha="center", va="center")
        fig.text(0.5, 0.320, "agent-next sandbox cookbook", fontsize=26,
                 color=MUTED, ha="center", va="center")

    return overlay(c, hud)


SHOT_FN = {
    "hook": shot_hook, "input": shot_input, "freefall": shot_freefall,
    "contact": shot_contact, "bounce": shot_bounce, "sandbox": shot_sandbox,
    "energy": shot_energy, "proof_pass": shot_proof_pass,
    "proof_kill": shot_proof_kill, "endcard": shot_endcard,
}


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--only", help="render just this shot")
    ap.add_argument("--preview", help="comma-separated seconds, one frame each")
    args = ap.parse_args()

    scn = Scene()
    os.makedirs(FRAMES, exist_ok=True)
    for f in os.listdir(FRAMES):
        if f.startswith("f") and f.endswith(".png"):
            os.remove(os.path.join(FRAMES, f))

    if args.preview:
        plan = [(None, float(x)) for x in args.preview.split(",")]
    else:
        shots = [s for s in SHOTS if not args.only or s[0] == args.only]
        plan = []
        for name, t0, t1 in shots:
            n = int(round((t1 - t0) * args.fps))
            plan += [(name, t0 + j / args.fps) for j in range(n)]
        print(f"[video] {len(plan)} frames at {args.fps} fps "
              f"({plan[-1][1] + 1 / args.fps:.1f} s, {W}x{H})")

    for idx, (name, t) in enumerate(plan):
        if name is None:
            name = next(n for n, a, b in SHOTS if a <= t < b)
        t0, t1 = BOUNDS[name]
        canvas = SHOT_FN[name](scn, t, t0, t1)
        Image.fromarray(canvas).save(os.path.join(FRAMES, f"f{idx:05d}.png"),
                                     compress_level=1)
        if idx % 90 == 0:
            print(f"[video]   frame {idx}/{len(plan)} ({name}, t={t:.2f}s)")

    if args.preview or args.only:
        print(f"[video] preview frames written to {FRAMES}")
        return

    master_dir = os.path.join(MEDIA, "master")
    os.makedirs(master_dir, exist_ok=True)
    master = os.path.join(master_dir, "demo.mp4")
    web = os.path.join(MEDIA, "demo.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate",
                    str(args.fps), "-i", os.path.join(FRAMES, "f%05d.png"),
                    "-c:v", "libx264", "-crf", "0", "-preset", "medium",
                    "-pix_fmt", "yuv420p", master], check=True)
    print("[video] lossless master written")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", master,
                    "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
                    web], check=True)
    print(f"[video] wrote {master}")
    print(f"[video] wrote {web}")


if __name__ == "__main__":
    main()
