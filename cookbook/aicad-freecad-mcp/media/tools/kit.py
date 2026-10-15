#!/usr/bin/env python3
"""Shared helpers for the aicad-freecad-mcp figures and video frames.

Everything a figure shows is read from the judge's own verdict JSONs in
media/data/ (grade.sh --json / selftest.sh). Nothing here invents a number:
the gate limits are the judge's own constants, imported from judge/judge.py
so a figure cannot drift from the code that graded the artifact.

Layout is checked, not eyeballed: every text or image box is registered
with Blocker, which raises on any overlap or overflow of the canvas.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.dirname(HERE)                    # <demo>/media
ROOT = os.path.dirname(MEDIA)                    # <demo>
DATA = os.path.join(MEDIA, "data")
sys.path.insert(0, os.path.join(ROOT, "judge"))

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
MONO = os.path.join(FONT_DIR, "DejaVuSansMono.ttf")
MONO_B = os.path.join(FONT_DIR, "DejaVuSansMono-Bold.ttf")
SANS = os.path.join(FONT_DIR, "DejaVuSans.ttf")
SANS_B = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

# --- palette (dark technical, colour-blind safe: green/red pair is
#     distinguishable by lightness as well as hue) ---
BG_TOP = (18, 21, 26)
BG_BOT = (28, 33, 41)
INK = (233, 238, 244)
MUTED = (150, 162, 176)
FAINT = (86, 96, 110)
GREEN = (54, 190, 116)
GREEN_DIM = (30, 96, 62)
RED = (233, 84, 72)
RED_DIM = (110, 38, 34)
ACCENT = (240, 186, 92)
STEEL = (0.62, 0.66, 0.72, 1.0)

# every part's judge gates, in the order a reader wants them; the plate
# additionally carries the DXF audit
GATE_ORDER = ["files", "brep", "bbox", "stl_topology", "xor_reference",
              "features", "min_wall", "dxf"]


def font(path, size):
    return ImageFont.truetype(path, size)


def verdict(name):
    """Load one verdict JSON from media/data (good_<part> / bad_<mutant>)."""
    p = os.path.join(DATA, name + ".json")
    if not os.path.exists(p):
        raise SystemExit("missing %s -- collect the judge verdicts first" % p)
    with open(p) as f:
        return json.load(f)


def limits():
    """The judge's own gate limits, read from judge/judge.py's constants.

    judge.py imports cadquery/OCP, which the media venv does not carry, so
    the five `NAME = value` lines are read out of its source instead of
    importing it. If a name stops matching, that is an error, not a silent
    fallback to a retyped number.
    """
    names = {"VOLUME_TOL": "brep", "BBOX_TOL": "bbox", "XOR_FRAC":
             "xor_reference", "MIN_WALL": "min_wall"}
    src = open(os.path.join(ROOT, "judge", "judge.py")).read()
    out, seen = {}, set()
    for line in src.splitlines():
        for name, gate in names.items():
            if line.startswith(name + " ="):
                out[gate] = float(line.split("=", 1)[1].split("#")[0].strip())
                seen.add(name)
    if len(seen) != len(names):
        raise SystemExit("judge.py constants not found: %s"
                         % (set(names) - seen))
    out["stl_topology"] = out["brep"]
    return out


# --- measured-vs-limit text, one line per gate ------------------------------

def _pct(x):
    """A fraction as a percentage, 4 significant digits."""
    return "0" if x == 0 else "%.4g%%" % (x * 100)


def gate_line(gate, g, lim):
    """(measured string, limit string) for one gate, from its verdict."""
    if "error" in g:
        return ("FAILED", "could not be measured")
    if gate == "files":
        return ("step + stl", "spec file set")
    if gate == "brep":
        return ("v %.5g mm3  (%s)" % (g["volume_mm3"], _pct(g["rel_error"])),
                "|dv| <= %.4g%% of analytic" % (lim["brep"] * 100))
    if gate == "bbox":
        return ("max axis %g mm" % g["max_axis_error_mm"],
                "<= %g mm per axis" % lim["bbox"])
    if gate == "stl_topology":
        return ("%.5g mm3  (%s)" % (g["stl_volume_mm3"], _pct(g["rel_error"])),
                "watertight, |dv| <= %.4g%%" % (lim["stl_topology"] * 100))
    if gate == "xor_reference":
        return ("%.4f%%  (%.1f mm3)" % (g["xor_fraction"] * 100, g["xor_mm3"]),
                "<= %.4g%% of reference" % (lim["xor_reference"] * 100))
    if gate == "min_wall":
        return ("min %.4g mm" % g["measured_min_mm"],
                ">= %.1f mm" % lim["min_wall"])
    if gate == "features":
        # cylindrical faces grouped by radius: R18x1 R10x1 ... (count of
        # faces at each radius, straight from the verdict's radii list)
        bits, counts = [], {}
        for r in g.get("radii", []):
            counts[r] = counts.get(r, 0) + 1
        for r in sorted(counts, reverse=True):
            bits.append("R%g x%d" % (r, counts[r]) if counts[r] > 1
                        else "R%g" % r)
        return (" ".join(bits), "radii match +/-0.05 mm")
    if gate == "dxf":
        return ("%d circles, %d audit errors"
                % (g["circles"], g["audit_errors"]),
                "ezdxf audit clean")
    raise KeyError(gate)


def measured_cell(gate, g, lim):
    """The 'what it measured' half only (loop.png red cells use this)."""
    return gate_line(gate, g, lim)[0]


def limit_cell(gate, g, lim):
    return gate_line(gate, g, lim)[1]


# --- graded card layout ----------------------------------------------------

class Blocker:
    """Register every drawn box; raise if two overlap or one overflows."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.boxes = []

    def add(self, name, box, pad=0):
        x0, y0, x1, y1 = box
        if x0 >= x1 or y0 >= y1:
            raise AssertionError("empty box %s: %r" % (name, box))
        if x0 < -pad or y0 < -pad or x1 > self.w + pad or y1 > self.h + pad:
            raise AssertionError(
                "%s overflows the %dx%d canvas: %r" % (name, self.w, self.h, box))
        for oname, obox in self.boxes:
            if (x0 < obox[2] and obox[0] < x1
                    and y0 < obox[3] and obox[1] < y1):
                raise AssertionError(
                    "%s %r overlaps %s %r" % (name, box, oname, obox))
        self.boxes.append((name, box))
        return box

    def inside(self, name, box, pad=0):
        """Overflow check only (a background layer is allowed to be overlapped)."""
        x0, y0, x1, y1 = box
        if x0 < -pad or y0 < -pad or x1 > self.w + pad or y1 > self.h + pad:
            raise AssertionError(
                "%s overflows the %dx%d canvas: %r" % (name, self.w, self.h, box))
        return box


def text_size(draw, s, f):
    l, t, r, b = draw.textbbox((0, 0), s, font=f)
    return r - l, b - t


def text_box(draw, xy, s, f, spacing=0):
    """Box a single line of text at xy occupies (anchor 'la')."""
    l, t, r, b = draw.textbbox(xy, s, font=f)
    return (l, t, r + spacing, b)


def wrap(draw, s, f, max_w):
    """Greedy word wrap to at most max_w pixels per line."""
    words, lines, cur = s.split(), [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def shrink_font(draw, s, path, base, max_w, floor=14):
    """Largest font (<= base) at which s fits inside max_w."""
    size = base
    while size > floor and draw.textlength(s, font=font(path, size)) > max_w:
        size -= 1
    return font(path, size)


def mm(v):
    """A millimetre volume/measure; no exponent for magnitudes people write."""
    return "%.0f" % v if abs(v) >= 1e5 else "%.5g" % v


def draw_wrapped(canvas, blk, name, xy, s, f, fill, max_w, line_h=None):
    """Draw wrapped text; every line registered so overlap/overflow is caught."""
    d = ImageDraw.Draw(canvas)
    lines = wrap(d, s, f, max_w)
    lh = line_h or int(f.size * 1.35)
    for i, line in enumerate(lines):
        y = xy[1] + i * lh
        blk.add("%s_%d" % (name, i), d.textbbox((xy[0], y), line, font=f))
        d.text((xy[0], y), line, font=f, fill=fill)
    return len(lines), xy[1] + len(lines) * lh


def gradient(size, top=BG_TOP, bot=BG_BOT):
    w, h = size
    g = Image.new("RGB", (1, h))
    px = g.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(round(top[i] + (bot[i] - top[i]) * t))
                         for i in range(3))
    return g.resize((w, h), Image.BILINEAR)


def paste_center(canvas, img, box, pad=0, bg=None):
    """Fit img inside box preserving aspect; centre it."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0 - 2 * pad, y1 - y0 - 2 * pad
    iw, ih = img.size
    s = min(bw / iw, bh / ih)
    nw, nh = max(1, int(iw * s)), max(1, int(ih * s))
    r = img.resize((nw, nh), Image.LANCZOS)
    x = x0 + pad + (bw - nw) // 2
    y = y0 + pad + (bh - nh) // 2
    if r.mode == "RGBA":
        canvas.paste(r, (x, y), r)
    else:
        canvas.paste(r, (x, y))
    return (x, y, x + nw, y + nh)


def mono_at(canvas, xy, s, f, fill=INK, gap=None, right=None):
    """Standard right-padded setting: mono text, optional gap to a value.

    With `gap`, xy is (x0, y) and the string is padded with spaces so a
    following value column lines up; returns (left_box, right_x).
    """
    px, _ = text_size(ImageDraw.Draw(canvas), s, f)
    d = ImageDraw.Draw(canvas)
    d.text(xy, s, font=f, fill=fill)
    l, t, r, b = d.textbbox(xy, s, font=f)
    return (l, t, r, b), px


def draw_right(canvas, xy, s, f, fill=INK):
    """Draw s ending at x=xy[0]; return its box (used for limit columns)."""
    d = ImageDraw.Draw(canvas)
    x = xy[0] - d.textlength(s, font=f)
    d.text((x, xy[1]), s, font=f, fill=fill)
    l, t, r, b = d.textbbox((x, xy[1]), s, font=f)
    return (l, t, r, b)


def fit_margin(mesh, yaw, pitch, w, h, fov_deg=28.0, target=0.88):
    """Smallest camera margin whose projected bounding box fits `target` NDC.

    A bounding box, so a curved surface may bulge slightly past it; 0.88
    leaves ~10 % of the frame as margin on top of that. Guarantees the
    render is not cut off at the frame edge (checked again on the alpha).
    """
    import pyrender
    from render import _cam_pose
    b = mesh.bounds
    corners = np.array([[x, y, z] for x in b[:, 0]
                        for y in b[:, 1] for z in b[:, 2]])
    for margin in np.arange(1.0, 3.0, 0.02):
        dist = margin * (float(mesh.extents.max()) / 2.0) / np.tan(
            np.radians(fov_deg) / 2)
        pose, _ = _cam_pose(yaw, pitch, dist)
        cam = pyrender.PerspectiveCamera(yfov=np.radians(fov_deg),
                                         znear=dist * 0.02, zfar=dist * 20)
        proj = cam.get_projection_matrix(w, h)
        c4 = np.hstack([corners, np.ones((8, 1))]) @ np.linalg.inv(pose).T
        clip = c4 @ proj.T
        ndc = clip[:, :3] / clip[:, 3:4]
        if max(abs(ndc[:, 0]).max(), abs(ndc[:, 1]).max()) <= target:
            return float(margin)
    raise AssertionError("could not frame the mesh")


def alpha_bbox(img, thresh=8):
    a = np.asarray(img.split()[-1])
    ys, xs = np.where(a > thresh)
    if len(xs) == 0:
        raise AssertionError("render is empty")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1

