#!/usr/bin/env python3
"""Write the Kestrel favicon (64x64 PNG) with the standard library only.

Flat brand colours, no gradients: a viridian ring on warm paper with the
pine needle pointing north-east, matching media/make_images.py's compass.
Run: python3 media/make_favicon.py
"""

import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "examples", "good", "site", "assets", "img",
                   "favicon.png")

PAPER = (244, 241, 234)   # #F4F1EA
PINE = (26, 36, 31)       # #1A241F
VIRIDIAN = (14, 110, 84)  # #0E6E54

S = 64


def render():
    px = [[PAPER] * S for _ in range(S)]
    cx = cy = S / 2 - 0.5
    ring_r, ring_w = S * 0.42, S * 0.11
    for y in range(S):
        for x in range(S):
            dx, dy = x - cx, y - cy
            r = (dx * dx + dy * dy) ** 0.5
            if ring_r - ring_w / 2 <= r <= ring_r + ring_w / 2:
                px[y][x] = VIRIDIAN
    # needle: a slim triangle pointing NNE (22.5 deg east of up)
    import math
    ang = math.radians(22.5)
    ux, uy = math.sin(ang), -math.cos(ang)          # needle axis
    vx, vy = -uy, ux                                 # perpendicular
    tip, tail, half_w = S * 0.30, -S * 0.16, S * 0.075
    for y in range(S):
        for x in range(S):
            dx, dy = x - cx, y - cy
            along = dx * ux + dy * uy
            across = abs(dx * vx + dy * vy)
            if tail <= along <= tip:
                w = half_w * (along - tail) / (tip - tail)
                if across <= w:
                    px[y][x] = PINE
    return px


def write_png(path, px):
    n = len(px)
    raw = b"".join(b"\x00" + b"".join(bytes(c) for c in row) for row in px)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    n = write_png(OUT, render())
    print(f"wrote {OUT} ({n} bytes)")
