#!/usr/bin/env python3
"""Component-level pixel diff: block-hash grid diff with connected-component
clustering and integer offset estimation.  This is the known-good artifact
for the pixel-diff-review cookbook demo.

Usage:
  review.py --base BASE.png --head HEAD.png --cols C --rows R \
            [--allow-bbox X,Y,W,H] [--json OUT.json]
"""
import argparse
import hashlib
import json
import struct
import sys
import zlib


def decode_png_gray(path):
    """Decode a PNG to (width, height, list of luminance rows 0-255)."""
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
    if colortype not in (0, 2):
        raise ValueError("%s: only grayscale or RGB PNG supported" % path)
    raw = zlib.decompress(idat)
    ch = {0: 1, 2: 3}[colortype]
    stride = W * ch
    rows = []
    prev = bytearray(stride)
    off = 0
    for _y in range(H):
        ft = raw[off]
        off += 1
        line = bytearray(raw[off:off + stride])
        off += stride
        if ft == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        rows.append(line)
        prev = line
    if ch == 1:
        return W, H, [list(r) for r in rows]
    gray = []
    for r in rows:
        g = []
        for x in range(W):
            i = x * 3
            g.append(round(0.299 * r[i] + 0.587 * r[i + 1] + 0.114 * r[i + 2]))
        gray.append(g)
    return W, H, gray


def block_stats(rows, W, H, bw, bh, cols, rows_n):
    """Compute dHash and mean for every block.  Returns {(c,r): (hash, mean)}."""
    stats = {}
    for r in range(rows_n):
        for c in range(cols):
            x0, y0 = c * bw, r * bh
            # box-average to 9x8
            avg = []
            for k in range(8):
                row_avg = []
                for j in range(9):
                    sx0 = x0 + j * bw // 9
                    sx1 = x0 + (j + 1) * bw // 9
                    sy0 = y0 + k * bh // 8
                    sy1 = y0 + (k + 1) * bh // 8
                    s = 0
                    cnt = 0
                    for y in range(sy0, min(sy1, H)):
                        for x in range(sx0, min(sx1, W)):
                            s += rows[y][x]
                            cnt += 1
                    row_avg.append(s / cnt if cnt else 0)
                avg.append(row_avg)
            h = 0
            for k in range(8):
                for j in range(8):
                    if avg[k][j] < avg[k][j + 1]:
                        h |= 1 << (8 * k + j)
            # mean
            s = 0
            cnt = 0
            for y in range(y0, min(y0 + bh, H)):
                for x in range(x0, min(x0 + bw, W)):
                    s += rows[y][x]
                    cnt += 1
            stats[(c, r)] = (h, s / cnt if cnt else 0)
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
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (c + dc, r + dr)
                if nb in changed and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        regions.append(comp)
    return regions


def estimate_offset(brows, hrows, W, H, c0, r0, c1, r1, bw, bh, search=16):
    """Integer cross-correlation offset.  Returns (dx, dy, sad)."""
    x0 = max(0, c0 * bw - search)
    y0 = max(0, r0 * bh - search)
    x1 = min(W, (c1 + 1) * bw + search)
    y1 = min(H, (r1 + 1) * bh + search)
    best = None
    best_sad = None
    for dy in range(-search, search + 1):
        for dx in range(-search, search + 1):
            sad = 0
            for y in range(y0, y1):
                hy = y + dy
                if hy < 0 or hy >= H:
                    continue
                brow = brows[y]
                hrow = hrows[hy]
                for x in range(x0, x1):
                    hx = x + dx
                    if hx < 0 or hx >= W:
                        continue
                    sad += abs(brow[x] - hrow[x])
            key = (sad, abs(dx) + abs(dy), abs(dx), abs(dy))
            if best is None or key < best_sad:
                best = (dx, dy)
                best_sad = key
    return best[0], best[1], best_sad[0]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--cols", type=int, required=True)
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--allow-bbox", default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv)

    W, H, brows = decode_png_gray(args.base)
    W2, H2, hrows = decode_png_gray(args.head)
    if (W, H) != (W2, H2):
        print("image size mismatch: %dx%d vs %dx%d" % (W, H, W2, H2),
              file=sys.stderr)
        return 2
    bw, bh = W // args.cols, H // args.rows

    bs = block_stats(brows, W, H, bw, bh, args.cols, args.rows)
    hs = block_stats(hrows, W, H, bw, bh, args.cols, args.rows)
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
        if hd >= 4 or md >= 10:
            changed.add(key)

    regions_raw = components(changed)
    # sort by bbox_blocks: topmost row, then leftmost col
    def bbox_of(comp):
        cs = [c for c, r in comp]
        rs = [r for c, r in comp]
        return min(rs), min(cs), max(rs), max(cs)
    regions_raw.sort(key=bbox_of)

    regions = []
    for i, comp in enumerate(regions_raw):
        cs = [c for c, r in comp]
        rs = [r for c, r in comp]
        c0, c1 = min(cs), max(cs)
        r0, r1 = min(rs), max(rs)
        dx, dy, sad = estimate_offset(brows, hrows, W, H,
                                      c0, r0, c1, r1, bw, bh)
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
        "inputs": {"base": sha256(args.base), "head": sha256(args.head)},
        "grid": {"cols": args.cols, "rows": args.rows,
                 "block_w": bw, "block_h": bh},
        "regions": regions,
        "changed_blocks": len(changed),
        "verdict": "report",
    }

    if args.allow_bbox:
        parts = [int(v) for v in args.allow_bbox.split(",")]
        ax, ay, aw, ah = parts
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

    out_text = json.dumps(report, indent=2)
    if args.json_out:
        with open(args.json_out, "w") as f:
            f.write(out_text + "\n")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
