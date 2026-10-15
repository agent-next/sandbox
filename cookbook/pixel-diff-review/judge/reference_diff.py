#!/usr/bin/env python3
"""The judge's own block-hash grid diff, written against the definition in
SPEC.md but sharing no code with the artifact under test.  It is the
"reference agreement" and "convergence" oracle: region count, bounding
boxes and the changed-block set at any grid the judge asks for.

No offset estimation lives here -- gate 12 compares the artifact's offset
against the browser-measured translateY, never against this module.

stdlib only, loaded by pdr_judge.py via importlib (the engine runs with
python3 -I, so sibling imports do not work by name).
"""

from collections import deque

HASH_THRESHOLD = 4
MEAN_THRESHOLD = 10


# --------------------------------------------------------------------------
# PNG decoding (own implementation: chunk walk, per-byte unfilter)
# --------------------------------------------------------------------------
def decode_gray(path):
    """(width, height, rows) with rows a list of `bytes` of luminance 0-255.

    Accepts 8-bit non-interlaced grayscale, RGB and RGBA; alpha dropped.
    """
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("%s: not a PNG" % path)
    width = height = None
    channels = None
    compressed = bytearray()
    pos = 8
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width = int.from_bytes(body[0:4], "big")
            height = int.from_bytes(body[4:8], "big")
            if body[8] != 8:
                raise ValueError("%s: only 8-bit depth" % path)
            if body[13] != 0:
                raise ValueError("%s: interlaced PNG" % path)
            channels = {0: 1, 2: 3, 6: 4}[body[9]]
        elif kind == b"IDAT":
            compressed += body
        elif kind == b"IEND":
            break
        pos += 12 + length
    if width is None:
        raise ValueError("%s: no IHDR" % path)

    import zlib
    raw = zlib.decompress(bytes(compressed))
    stride = width * channels
    out = []
    above = bytearray(stride)
    i = 0
    for _ in range(height):
        ftype = raw[i]
        i += 1
        cur = bytearray(raw[i:i + stride])
        i += stride
        if ftype == 1:      # Sub
            for k in range(channels, stride):
                cur[k] = (cur[k] + cur[k - channels]) & 0xFF
        elif ftype == 2:    # Up
            for k in range(stride):
                cur[k] = (cur[k] + above[k]) & 0xFF
        elif ftype == 3:    # Average
            for k in range(stride):
                left = cur[k - channels] if k >= channels else 0
                cur[k] = (cur[k] + ((left + above[k]) >> 1)) & 0xFF
        elif ftype == 4:    # Paeth
            for k in range(stride):
                left = cur[k - channels] if k >= channels else 0
                upleft = above[k - channels] if k >= channels else 0
                p = left + above[k] - upleft
                pa, pb, pc = abs(p - left), abs(p - above[k]), abs(p - upleft)
                if pa <= pb and pa <= pc:
                    pred = left
                elif pb <= pc:
                    pred = above[k]
                else:
                    pred = upleft
                cur[k] = (cur[k] + pred) & 0xFF
        elif ftype != 0:
            raise ValueError("%s: filter type %d" % (path, ftype))
        out.append(bytes(cur))
        above = cur

    if channels == 1:
        return width, height, out
    gray = []
    for line in out:
        row = bytearray(width)
        for x in range(width):
            o = x * channels
            row[x] = int(0.299 * line[o] + 0.587 * line[o + 1]
                         + 0.114 * line[o + 2] + 0.5)  # round half up
        gray.append(bytes(row))
    return width, height, gray


def image_is_blank(path):
    """True when the image is a single flat colour (a failed capture)."""
    w, h, rows = decode_gray(path)
    first = rows[0][0]
    for y in range(0, h, 5):
        row = rows[y]
        if any(row[x] != first for x in range(0, w, 5)):
            return False
    return True


# --------------------------------------------------------------------------
# The grid diff
# --------------------------------------------------------------------------
def _block_signature(rows, width, height, bw, bh, c, r):
    """(dHash 64-bit int, mean 0-255) for block (c, r) per SPEC.md."""
    x0, y0 = c * bw, r * bh
    # 9x8 box averages
    avgs = [[0.0] * 9 for _ in range(8)]
    for k in range(8):
        cy0 = y0 + k * bh // 8
        cy1 = max(y0 + (k + 1) * bh // 8, cy0 + 1)
        for j in range(9):
            cx0 = x0 + j * bw // 9
            cx1 = max(x0 + (j + 1) * bw // 9, cx0 + 1)
            total = count = 0
            for y in range(cy0, min(cy1, height)):
                seg = rows[y][cx0:cx1]
                total += sum(seg)
                count += len(seg)
            avgs[k][j] = total / count if count else 0.0
    bits = 0
    bit = 1
    for k in range(8):
        line = avgs[k]
        for j in range(8):
            if line[j] < line[j + 1]:
                bits |= bit
            bit <<= 1
    total = count = 0
    for y in range(y0, min(y0 + bh, height)):
        seg = rows[y][x0:x0 + bw]
        total += sum(seg)
        count += len(seg)
    mean = total / count if count else 0.0
    return bits, mean


def diff(base_img, head_img, cols, rows_n):
    """Grid diff of two decoded images.

    Returns {"changed_blocks": [(c, r), ...], "boxes_px": [[x, y, w, h], ...]}
    with one box per 4-connected component, sorted topmost-then-leftmost.
    """
    (w, h, base_rows), (w2, h2, head_rows) = base_img, head_img
    if (w, h) != (w2, h2):
        raise ValueError("image size mismatch %dx%d vs %dx%d" % (w, h, w2, h2))
    bw, bh = w // cols, h // rows_n

    changed = set()
    for r in range(rows_n):
        for c in range(cols):
            h1, m1 = _block_signature(base_rows, w, h, bw, bh, c, r)
            h2_, m2 = _block_signature(head_rows, w, h, bw, bh, c, r)
            if (bin(h1 ^ h2_).count("1") >= HASH_THRESHOLD
                    or abs(m1 - m2) >= MEAN_THRESHOLD):
                changed.add((c, r))

    boxes = []
    remaining = set(changed)
    while remaining:
        start = sorted(remaining)[0]
        remaining.discard(start)
        queue = deque([start])
        comp = [start]
        while queue:
            c, r = queue.popleft()
            for nxt in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
                if nxt in remaining:
                    remaining.discard(nxt)
                    queue.append(nxt)
                    comp.append(nxt)
        cvals = [p[0] for p in comp]
        rvals = [p[1] for p in comp]
        c0, c1 = min(cvals), max(cvals)
        r0, r1 = min(rvals), max(rvals)
        boxes.append({"bbox_blocks": [c0, r0, c1, r1],
                      "bbox_px": [c0 * bw, r0 * bh,
                                  (c1 - c0 + 1) * bw, (r1 - r0 + 1) * bh],
                      "area_blocks": len(comp)})
    boxes.sort(key=lambda b: (b["bbox_blocks"][1], b["bbox_blocks"][0]))
    return {"changed_blocks": sorted(changed), "boxes_px":
            [b["bbox_px"] for b in boxes], "regions": boxes}


def four_connected(blocks):
    """True when `blocks` (iterable of (c, r)) is one 4-connected set."""
    blocks = set(blocks)
    if not blocks:
        return False
    start = next(iter(blocks))
    seen = {start}
    queue = deque([start])
    while queue:
        c, r = queue.popleft()
        for nxt in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
            if nxt in blocks and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen == blocks
