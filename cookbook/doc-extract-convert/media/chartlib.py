#!/usr/bin/env python3
"""Tiny Pillow chart kit for the demo's media.

The judge already pins Pillow (sha256-checked, judge/setup.sh), so the
figures are drawn with it rather than pulling in a second plotting stack:
every pixel of media/ is produced by tools whose versions the repo pins.

Only what these two figures need: a horizontal bar panel, a dot-and-line
panel and a bar panel, each with a drawn pass line (the judge's numeric
rule), direct value labels, recessive grid and DejaVu text.

Style: thin marks, one measure per panel (never two y-scales), text in
ink colours rather than series colours, colour-blind-safe palette
(Okabe-Ito; validated for CVD separation against the light surface).
"""

import os

from PIL import Image, ImageDraw, ImageFont

# Okabe-Ito steps, validated with the dataviz six-checks validator against
# the light surface (#FCFCFB): CVD Delta E 21.9 (protan) / 30.9 (tritan),
# normal-vision Delta E 31.2, contrast >= 3:1.
PASS_BLUE = (0, 114, 178)      # measured value that meets the gate
FAIL_RED = (213, 94, 0)        # measured value that misses a gate
INK = (34, 34, 34)             # primary text
INK_2 = (96, 96, 96)           # secondary text (axis labels, captions)
GRID = (222, 222, 220)
SURFACE = (252, 252, 251)
WHITE = (255, 255, 255)

FONT_DIRS = (
    "/usr/share/fonts/truetype/dejavu",          # fonts-dejavu-core (pinned)
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),
)


def font(size, bold=False):
    """DejaVuSans at `size` (the corpus font, installed by judge/setup.sh)."""
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in FONT_DIRS:
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    raise SystemExit("chartlib: %s not found -- run judge/setup.sh first" % name)


class Panel:
    """One measure, one scale, drawn inside a padded box."""

    def __init__(self, draw, box, title=None, caption=None):
        self.d = draw
        self.x0, self.y0, self.x1, self.y1 = box
        self.title = title
        self.caption = caption

    # -- text ---------------------------------------------------------------
    def text(self, xy, s, size=28, bold=False, fill=INK, anchor="la"):
        self.d.text(xy, s, font=font(size, bold), fill=fill, anchor=anchor)

    def header(self):
        y = self.y0
        if self.title:
            self.text((self.x0, y), self.title, size=34, bold=True)
            y += 52
        if self.caption:
            self.text((self.x0, y), self.caption, size=26, fill=INK_2)
            y += 40
        return y

    # -- scales -------------------------------------------------------------
    def hscale(self, lo, hi, ticks):
        """x-pixels for values in [lo, hi]; draws the x axis and its ticks."""
        top = self.header()
        axis_y = self.y1 - 46
        self.d.line([(self.x0, axis_y), (self.x1, axis_y)], fill=INK, width=2)
        for v in ticks:
            x = self.x0 + (v - lo) / float(hi - lo) * (self.x1 - self.x0)
            self.d.line([(x, axis_y), (x, axis_y + 8)], fill=INK, width=2)
            self.text((x, axis_y + 14), "%g" % v, size=24, fill=INK_2,
                      anchor="ma")
            if v > lo:
                self.d.line([(x, top), (x, axis_y - 4)], fill=GRID, width=1)
        return top, axis_y

    def vscale(self, lo, hi, ticks):
        """y-pixels for values in [lo, hi]; draws the y axis and its ticks."""
        top = self.header()
        self.d.line([(self.x0, top), (self.x0, self.y1 - 46)], fill=INK,
                    width=2)
        for v in ticks:
            y = self.y1 - 46 - (v - lo) / float(hi - lo) * (self.y1 - 46 - top)
            self.d.line([(self.x0 - 8, y), (self.x0, y)], fill=INK, width=2)
            self.text((self.x0 - 16, y), "%g" % v, size=24, fill=INK_2,
                      anchor="rm")
            if v > lo:
                self.d.line([(self.x0 + 2, y), (self.x1, y)], fill=GRID,
                            width=1)
        return top

    # -- marks --------------------------------------------------------------
    def hbar(self, y, h, lo, hi, value, color, label, note_x,
             note_fill=None, note=None):
        """One horizontal bar ending at `value`, direct-labelled at its end.

        `note` is drawn left-aligned at `note_x`, in its own column clear of
        the bar end, so a long bar can never overwrite it.
        """
        x = self.x0 + (value - lo) / float(hi - lo) * (self.x1 - self.x0)
        self.d.rounded_rectangle(
            [self.x0, y - h // 2, max(x, self.x0 + 6), y + h // 2],
            radius=4, fill=color)
        self.text((x + 16, y), label, size=26, anchor="lm", bold=True)
        if note:
            self.text((note_x, y), note, size=25, anchor="lm",
                      fill=note_fill or INK_2)
        return x

    def passline_v(self, lo, hi, at, text, top, bottom):
        """The judge's numeric rule, as a dashed vertical line + label."""
        x = self.x0 + (at - lo) / float(hi - lo) * (self.x1 - self.x0)
        for yy in range(top, bottom, 18):
            self.d.line([(x, yy), (x, min(yy + 10, bottom))], fill=INK,
                        width=3)
        self.text((x - 10, top - 34), text, size=26, bold=True, anchor="ra")

    def dotline(self, pts, top, bottom, lo, hi, color, r=11):
        """A 3 px line through 2px-gap-separated >=8 px dots."""
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            self.d.line([(x1, y1), (x2, y2)], fill=color, width=3)
        for x, y in pts:
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=WHITE,
                           outline=color, width=3)

    def vbar(self, x, w, top, bottom, lo, hi, value, color, label, above):
        """One vertical bar with its value labelled just above the end."""
        y = bottom - (value - lo) / float(hi - lo) * (bottom - top)
        self.d.rounded_rectangle([x - w // 2, y, x + w // 2, bottom - 4],
                                 radius=4, fill=color)
        self.text((x, above), label, size=26, bold=True, anchor="ma")

    def passline_h(self, lo, hi, at, left, right, text):
        """The judge's numeric rule, as a dashed horizontal line + label."""
        top = self.y0
        bottom = self.y1 - 46
        y = bottom - (at - lo) / float(hi - lo) * (bottom - top)
        for xx in range(left, right, 18):
            self.d.line([(xx, y), (min(xx + 10, right), y)], fill=INK, width=3)
        self.text((right, y - 12), text, size=26, bold=True, anchor="rd")


def new_figure(width, height, title, subtitle):
    """A white card with a title block; returns (image, draw, content_top)."""
    im = Image.new("RGB", (width, height), SURFACE)
    d = ImageDraw.Draw(im)
    d.text((70, 54), title, font=font(44, True), fill=INK)
    if subtitle:
        d.text((70, 122), subtitle, font=font(28), fill=INK_2)
    return im, d, 190
