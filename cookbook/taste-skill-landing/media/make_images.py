#!/usr/bin/env python3
"""Draw the Kestrel brand imagery (compass rose, wind field, route ribbons)
as PNGs with Pillow — flat colour, brand palette only, no gradients."""

import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "examples", "good", "site", "assets", "img")
os.makedirs(OUT, exist_ok=True)

PAPER = (244, 241, 234)   # #F4F1EA
PINE = (26, 36, 31)       # #1A241F
VIRIDIAN = (14, 110, 84)  # #0E6E54
MIST = (222, 216, 203)    # #DED8CB — a tone step, not a shadow
SLATE = (74, 84, 78)      # #4A544E — secondary ink


def hexc(rgb):
    return "#%02X%02X%02X" % rgb


def compass(w=960, h=960):
    """Kestrel's motif: a compass rose with the wind arrow flying NNE."""
    scale = 4
    W, H = w * scale, h * scale
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    cx, cy = W // 2, H // 2

    # needle triangle: the west point — the direction the wind pushes you.
    d.polygon([(W//32, cy), (W//2, cy - H//11), (W//2, cy + H//11)], PINE)
    d.polygon([(W//2 + W//32, cy), (W//2, cy - H//11), (W//2, cy + H//11)], VIRIDIAN)
    # north pointer
    d.polygon([(W//2, cy - H//3), (W//2 - W//28, cy - H//7), (W//2 + W//28, cy - H//7)], PINE)
    # ring: heavy, flat
    d.ellipse([W//4, H//4, 3*W//4, 3*H//4], outline=PINE, width=22*scale//4)
    # tick at NNE — where the wind arrow goes
    import math
    ang = math.radians(22.5)
    tx1 = cx + (W//4) * math.sin(ang)
    ty1 = cy - (W//4) * math.cos(ang)
    tx2 = cx + (W//4 + 90*scale//4) * math.sin(ang)
    ty2 = cy - (W//4 + 90*scale//4) * math.cos(ang)
    d.line([(tx1, ty1), (tx2, ty2)], fill=VIRIDIAN, width=26*scale//4)
    im = im.resize((w, h), Image.LANCZOS)
    return im


def windfield(w=960, h=540):
    """A field of wind arrows — flat, one palette, one weight."""
    scale = 4
    W, H = w * scale, h * scale
    im = Image.new("RGB", (W, H), PINE)  # pine field
    d = ImageDraw.Draw(im)
    # arrows: shaft + head, all NNE, viridian on pine
    dx, dy = 3, 2
    marginx, marginy = W // 10, H // 6
    x = marginx
    while x < W - marginx:
        y = marginy
        while y < H - marginy:
            L = W // 20
            ax, ay = x, y + L
            d.line([(ax, ay), (x, y)], fill=PAPER, width=10*scale//4)
            d.polygon([(x - W//60, y + H//30), (x + W//60, y + H//30), (x, y - H//60)], PAPER)
            y += (H - 2 * marginy) // 3
        x += (W - 2 * marginx) // 4
    im = im.resize((w, h), Image.LANCZOS)
    return im


def routes(w=960, h=540):
    """Three loop ribbons on paper — the showcased routes."""
    scale = 4
    W, H = w * scale, h * scale
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    lw = 26*scale//4
    # loop 1 (large, pine): a round loop
    d.arc([W//8, H//6, 7*W//8, 5*H//6], start=30, end=330, fill=PINE, width=lw)
    # loop 2 (viridian): a rounded rectangle loop
    d.rounded_rectangle([W//6, H//4, W//2, 3*H//4], radius=H//6, outline=VIRIDIAN, width=lw)
    # loop 3 (mist, wide): a big sweep
    d.arc([W//3, H//8, 5*W//3, 7*H//8], start=200, end=340, fill=MIST, width=lw+8*scale//4)
    # start dots
    for (px, py, c) in [(W//8, H//2, PINE), (W//3, H//2, VIRIDIAN), (W//2, H//2, SLATE)]:
        r = 30*scale//4
        d.ellipse([px - r, py - r, px + r, py + r], fill=c)
    im = im.resize((w, h), Image.LANCZOS)
    return im


def profile(w=960, h=540):
    """A route's elevation as flat steps of tone — the honest diagram."""
    scale = 4
    W, H = w * scale, h * scale
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    # stepped elevation bars, widths on the 8px scale, three tones
    bar = W // 16
    heights = [H//3, H//4, H//2, 5*H//12, 2*H//3, H//2, H//3, H//5, 5*H//12, H//4, H//3, H//5, H//4, H//6, H//5, H//8]
    tones = [PINE, VIRIDIAN, MIST]
    for i, hh in enumerate(heights):
        x = i * bar
        c = tones[i % 3]
        d.rectangle([x, H - hh, x + bar - 12*scale//4, H], fill=c)
    im = im.resize((w, h), Image.LANCZOS)
    return im


if __name__ == "__main__":
    compass().save(os.path.join(OUT, "compass.png"), optimize=True)
    windfield().save(os.path.join(OUT, "windfield.png"), optimize=True)
    routes().save(os.path.join(OUT, "routes.png"), optimize=True)
    profile().save(os.path.join(OUT, "elevation.png"), optimize=True)
    print("wrote 4 images to", OUT)
