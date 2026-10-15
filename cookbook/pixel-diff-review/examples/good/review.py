#!/usr/bin/env python3
"""Component-level pixel diff: block-hash grid diff with connected-component
clustering and integer offset estimation.  This is the known-good artifact
for the pixel-diff-review cookbook demo.

Usage:
  review.py --base BASE.png --head HEAD.png --cols C --rows R \
            [--allow-bbox X,Y,W,H] [--json OUT.json]

Stdlib only.  The hot loops (PNG unfilter, grayscale, block averages, the
offset search) are written against bytes slices and map/sum so they run at
C speed; the definitions they implement are the ones in SPEC.md.
"""
import argparse
import hashlib
import json
import struct
import sys
import zlib
from itertools import accumulate

HASH_THRESHOLD = 4
MEAN_THRESHOLD = 10
SEARCH_PX = 16

# round(0.299*R + 0.587*G + 0.114*B) via three lookup tables
_R = [round(0.299 * v) for v in range(256)]
_G = [round(0.587 * v) for v in range(256)]
_B = [round(0.114 * v) for v in range(256)]


def decode_png_gray(path):
    """Decode a PNG to (width, height, list of `bytes` luminance rows 0-255).

    8-bit grayscale, RGB and RGBA are supported; alpha is dropped (the
    judge's screenshots are opaque).
    """
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("%s: not a PNG" % path)
    pos = 8
    idat = b""
    W = H = bitdepth = colortype = None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            W, H, bitdepth, colortype = struct.unpack(">IIBB", chunk[:10])
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if bitdepth != 8:
        raise ValueError("%s: only 8-bit PNG supported" % path)
    if colortype not in (0, 2, 6):
        raise ValueError("%s: unsupported PNG colour type %d" % (path, colortype))
    ch = {0: 1, 2: 3, 6: 4}[colortype]
    interlace = data[28]  # IHDR byte 12: must be 0 (progressive unsupported)
    if interlace != 0:
        raise ValueError("%s: interlaced PNG not supported" % path)

    raw = zlib.decompress(idat)
    stride = W * ch
    lines = []
    prev = bytes(stride)
    off = 0
    for _y in range(H):
        ft = raw[off]
        off += 1
        line = bytearray(raw[off:off + stride])
        off += stride
        if ft == 0:
            pass
        elif ft == 1:  # Sub: x + a (a = byte ch positions back)
            for lane in range(ch):
                ln = line[lane::ch]
                line[lane::ch] = bytes(v & 0xFF for v in accumulate(ln))
        elif ft == 2:  # Up: x + b (b = byte above), elementwise
            line = bytearray((a + b) & 0xFF for a, b in zip(line, prev))
        elif ft == 3:  # Average: x + floor((a + b) / 2)
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:  # Paeth
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                p = a + b - c
                pa = p - a if p >= a else a - p
                pb = p - b if p >= b else b - p
                pc = p - c if p >= c else c - p
                if pa <= pb and pa <= pc:
                    pr = a
                elif pb <= pc:
                    pr = b
                else:
                    pr = c
                line[i] = (line[i] + pr) & 0xFF
        else:
            raise ValueError("%s: bad PNG filter type %d" % (path, ft))
        lines.append(bytes(line))
        prev = lines[-1]

    if ch == 1:
        return W, H, lines
    Rt, Gt, Bt = _R, _G, _B
    gray = []
    for r in lines:
        gray.append(bytes(Rt[r[i]] + Gt[r[i + 1]] + Bt[r[i + 2]]
                          for i in range(0, stride, ch)))
    return W, H, gray


def block_stats(rows, W, H, bw, bh, cols, rows_n):
    """dHash (64-bit) and mean (0-255) for every block. {(c, r): (hash, mean)}.

    The 9x8 box average follows SPEC.md: cell (k, j) covers
    x in [x0 + j*bw//9, x0 + (j+1)*bw//9), y in [y0 + k*bh//8, ...).
    """
    stats = {}
    for r in range(rows_n):
        y0 = r * bh
        y1 = min(y0 + bh, H)
        for c in range(cols):
            x0 = c * bw
            # per-cell sums for the 9x8 average
            cells = []
            for k in range(8):
                ky0 = y0 + k * bh // 8
                ky1 = max(y0 + (k + 1) * bh // 8, ky0 + 1)
                row_cells = []
                for j in range(9):
                    sx0 = x0 + j * bw // 9
                    sx1 = max(x0 + (j + 1) * bw // 9, sx0 + 1)
                    s = 0
                    n = 0
                    for y in range(ky0, min(ky1, y1)):
                        row = rows[y]
                        s += sum(row[sx0:sx1])
                        n += sx1 - sx0
                    row_cells.append((s, n))
                cells.append(row_cells)
            h = 0
            for k in range(8):
                v = [s / n if n else 0 for s, n in cells[k]]
                for j in range(8):
                    if v[j] < v[j + 1]:
                        h |= 1 << (8 * k + j)
            s = 0
            n = 0
            for y in range(y0, y1):
                row = rows[y]
                s += sum(row[x0:x0 + bw])
                n += bw
            stats[(c, r)] = (h, s / n if n else 0)
    return stats


def popcount(x):
    return bin(x).count("1")


def components(changed):
    """4-connected components of the changed-block set."""
    seen = set()
    regions = []
    for cell in changed:
        if cell in seen:
            continue
        stack = [cell]
        comp = []
        seen.add(cell)
        while stack:
            c, r = stack.pop()
            comp.append((c, r))
            for nb in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
                if nb in changed and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        regions.append(comp)
    return regions


def estimate_offset(brows, hrows, W, H, c0, r0, c1, r1, bw, bh, search=SEARCH_PX):
    """Integer cross-correlation offset over the bbox grown by `search` px.

    Minimises sum |base[y][x] - head[y+dy][x+dx]|; ties break by smallest
    |dx|+|dy|, then smallest dx, then smallest dy (SPEC.md).
    """
    x0 = max(0, c0 * bw - search)
    y0 = max(0, r0 * bh - search)
    x1 = min(W, (c1 + 1) * bw + search)
    y1 = min(H, (r1 + 1) * bh + search)
    sub = int.__sub__
    best_key = None
    best = (0, 0)
    for dy in range(-search, search + 1):
        hy0, hy1 = y0 + dy, y1 + dy
        if hy0 < 0 or hy1 > H:
            continue
        hslice = hrows[hy0:hy1]
        for dx in range(-search, search + 1):
            hx0, hx1 = x0 + dx, x1 + dx
            if hx0 < 0 or hx1 > W:
                continue
            sad = 0
            for brow, hrow in zip(brows[y0:y1], hslice):
                sad += sum(map(abs, map(sub, brow[x0:x1], hrow[hx0:hx1])))
            key = (sad, abs(dx) + abs(dy), dx, dy)
            if best_key is None or key < best_key:
                best_key = key
                best = (dx, dy)
    return best[0], best[1]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_report(base_path, head_path, cols, rows_n, allow_bbox=None):
    W, H, brows = decode_png_gray(base_path)
    W2, H2, hrows = decode_png_gray(head_path)
    if (W, H) != (W2, H2):
        raise ValueError("image size mismatch: %dx%d vs %dx%d" % (W, H, W2, H2))
    bw, bh = W // cols, H // rows_n

    bs = block_stats(brows, W, H, bw, bh, cols, rows_n)
    hs = block_stats(hrows, W, H, bw, bh, cols, rows_n)
    changed = set()
    hash_deltas = {}
    mean_deltas = {}
    for key in bs:
        h1, m1 = bs[key]
        h2, m2 = hs[key]
        hd = popcount(h1 ^ h2)
        md = abs(m1 - m2)
        hash_deltas[key] = hd
        mean_deltas[key] = md
        if hd >= HASH_THRESHOLD or md >= MEAN_THRESHOLD:
            changed.add(key)

    regions_raw = components(changed)

    def sort_key(comp):
        cs = [c for c, r in comp]
        rs = [r for c, r in comp]
        return (min(rs), min(cs), max(rs), max(cs))

    regions_raw.sort(key=sort_key)

    regions = []
    for i, comp in enumerate(regions_raw):
        cs = [c for c, r in comp]
        rs = [r for c, r in comp]
        c0, c1 = min(cs), max(cs)
        r0, r1 = min(rs), max(rs)
        dx, dy = estimate_offset(brows, hrows, W, H, c0, r0, c1, r1, bw, bh)
        regions.append({
            "id": i + 1,
            "bbox_blocks": [c0, r0, c1, r1],
            "bbox_px": [c0 * bw, r0 * bh,
                        (c1 - c0 + 1) * bw, (r1 - r0 + 1) * bh],
            "area_blocks": len(comp),
            "area_px": len(comp) * bw * bh,
            "blocks": sorted([list(b) for b in comp]),
            "offset_px": [dx, dy],
            "hash_delta_max": max(hash_deltas[b] for b in comp),
            "mean_delta_max": max(int(round(mean_deltas[b])) for b in comp),
        })

    report = {
        "schema": "pixel-diff-review/report/1",
        "inputs": {"base": sha256(base_path), "head": sha256(head_path)},
        "grid": {"cols": cols, "rows": rows_n, "block_w": bw, "block_h": bh},
        "regions": regions,
        "changed_blocks": len(changed),
        "verdict": "report",
    }

    if allow_bbox is not None:
        ax, ay, aw, ah = allow_bbox
        outside = 0
        for reg in regions:
            rx, ry, rw, rh = reg["bbox_px"]
            ix0 = max(rx, ax)
            iy0 = max(ry, ay)
            ix1 = min(rx + rw, ax + aw)
            iy1 = min(ry + rh, ay + ah)
            inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
            if inter < rw * rh:
                outside += 1
        report["verdict"] = "pass" if outside == 0 else "fail"
        report["regions_outside_allowed"] = outside

    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--cols", type=int, required=True)
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--allow-bbox", default=None,
                    help="X,Y,W,H in device px; with it, print a verdict")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv)

    allow = None
    if args.allow_bbox:
        try:
            allow = [int(v) for v in args.allow_bbox.split(",")]
        except ValueError:
            print("review: --allow-bbox must be X,Y,W,H integers",
                  file=sys.stderr)
            return 2
        if len(allow) != 4:
            print("review: --allow-bbox must be X,Y,W,H", file=sys.stderr)
            return 2

    try:
        report = build_report(args.base, args.head, args.cols, args.rows,
                              allow_bbox=allow)
    except (ValueError, OSError) as exc:
        print("review: %s" % exc, file=sys.stderr)
        return 2

    out_text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out:
        with open(args.json_out, "w") as f:
            f.write(out_text + "\n")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
