#!/usr/bin/env python3
"""crop_png.py — pure-stdlib PNG crop (no PIL, no interpolation).

Usage: crop_png.py IN.png OUT.png X Y W H

Decodes an 8-bit, non-interlaced RGB/RGBA PNG (the form headless
Chromium screenshots produce), cuts the rectangle (X, Y, W, H), and
re-encodes it as a truecolor RGB PNG with fixed zlib settings so the
output is byte-deterministic for a given input.
"""

import struct
import sys
import zlib


def decode(path):
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit(f"crop_png: {path} is not a PNG")
    pos = 8
    idat = b""
    w = h = bit_depth = color_type = None
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            w, h, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if w is None or bit_depth != 8 or color_type not in (2, 6):
        sys.exit(f"crop_png: unsupported PNG (bit_depth={bit_depth} "
                 f"color_type={color_type})")
    raw = zlib.decompress(idat)
    c = 3 if color_type == 2 else 4
    stride = w * c
    px = bytearray(w * h * c)
    prev = bytearray(stride)
    i = o = 0
    for _y in range(h):
        f = raw[i]
        i += 1
        line = bytearray(raw[i:i + stride])
        i += stride
        _unfilter(f, line, prev, c)
        px[o:o + stride] = line
        prev = line
        o += stride
    return w, h, c, px


def _unfilter(f, line, prev, bpp):
    if f == 0:
        return
    if f == 1:
        for x in range(bpp, len(line)):
            line[x] = (line[x] + line[x - bpp]) & 0xFF
    elif f == 2:
        for x in range(len(line)):
            line[x] = (line[x] + prev[x]) & 0xFF
    elif f == 3:
        for x in range(len(line)):
            a = line[x - bpp] if x >= bpp else 0
            line[x] = (line[x] + ((a + prev[x]) >> 1)) & 0xFF
    elif f == 4:
        for x in range(len(line)):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            cc = prev[x - bpp] if x >= bpp else 0
            p = a + b - cc
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - cc)
            pr = a if pa <= pb and pa <= pc else (b if pb <= pc else cc)
            line[x] = (line[x] + pr) & 0xFF


def encode(path, w, h, px):
    """px is RGB (3 channels), filter 0 on every row, zlib level 9."""
    stride = w * 3
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += px[y * stride:(y + 1) * stride]

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    out = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBB", w, h, 8, 2)
                   + b"\x00\x00\x00")
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(out)


def main():
    if len(sys.argv) != 7:
        sys.exit(__doc__)
    src, dst, x, y, cw, ch = sys.argv[1], sys.argv[2], *map(int, sys.argv[3:])
    w, h, c, px = decode(src)
    if not (0 <= x and 0 <= y and x + cw <= w and y + ch <= h):
        sys.exit(f"crop_png: rectangle ({x},{y},{cw},{ch}) outside {w}x{h}")
    out = bytearray(cw * ch * 3)
    for row in range(ch):
        sbase = ((y + row) * w + x) * c
        dbase = row * cw * 3
        if c == 3:
            out[dbase:dbase + cw * 3] = px[sbase:sbase + cw * 3]
        else:
            for i in range(cw):
                out[dbase + i * 3:dbase + i * 3 + 3] = \
                    px[sbase + i * 4:sbase + i * 4 + 3]
    encode(dst, cw, ch, out)
    print(f"crop_png: {dst} <- ({x},{y}) {cw}x{ch} of {src}")


if __name__ == "__main__":
    main()
