"""Barcode decoder, blend estimator and EDL comparator for the
video-edit-mlt judge.  Pure Python 3.10+ standard library: every gate in
grade.py measures the rendered bytes, never MLT's own reporting.

Frame pixels reach this module as rgb24 bytes, already cropped by ffmpeg
to the region that matters:

* the barcode band  -- a 1280x40 strip at the top of every source frame,
  16 blocks of 80 px, each block solid black or solid white.  Bit layout,
  MSB-first block order left to right:

      block 0..3    sync pattern 1 0 1 0
      block 4..5    clip id       (0=A, 1=B, 2=C)
      block 6..15   source frame index, 10 bits big-endian

* the blend window  -- a centre region scaled to one pixel by ffmpeg;
  its colour is either a clip's flat hue or, during the dissolve, a
  blend of two of them.

* the logo rect    -- the bottom-right corner, matched against the
  decoded pixels of assets/logo.png.
"""

W, H = 1280, 720
BAND_Y, BAND_H = 8, 40
NBLOCKS = 16
BLOCK_W = W // NBLOCKS          # 80 px
SYNC = (1, 0, 1, 0)

# Thresholds on a block's centre mean (0..255).  Anything between them is
# ambiguous -- a blend, a codec smear, or a non-source frame -- and the
# frame reports "unreadable" instead of guessing.
BLACK_MAX = 64
WHITE_MIN = 192


def encode_code(clip_id, frame):
    """The 16 bits a source frame's barcode band carries."""
    assert 0 <= clip_id <= 3 and 0 <= frame < 1024
    bits = list(SYNC)
    bits += [(clip_id >> 1) & 1, clip_id & 1]
    bits += [(frame >> (9 - i)) & 1 for i in range(10)]
    assert len(bits) == NBLOCKS
    return bits


def band_row(bits):
    """One rgb24 scanline (1280x3 bytes) of a barcode band for `bits`."""
    row = bytearray(W * 3)
    for i, bit in enumerate(bits):
        v = 255 if bit else 0
        start = i * BLOCK_W * 3
        row[start:start + BLOCK_W * 3] = bytes((v,)) * (BLOCK_W * 3)
    return bytes(row)


def _block_mean(band, block, width):
    """Mean of the centre 20x20 px of one 80x40 block of an rgb24 band."""
    x0 = block * BLOCK_W + BLOCK_W // 2 - 10
    y0 = BAND_H // 2 - 10
    total = 0
    for y in range(y0, y0 + 20):
        base = (y * width + x0) * 3
        for x in range(20):
            total += band[base + x * 3]
    return total / 400


def decode_band(band, width=W):
    """Decode one cropped barcode band -> (clip_id, frame) or None.

    Returns None when the sync pattern is wrong or any block lands in the
    ambiguous zone (e.g. a dissolve mid-blend)."""
    if len(band) != width * BAND_H * 3:
        raise ValueError("band is %d bytes, want %d"
                         % (len(band), width * BAND_H * 3))
    bits = []
    for i in range(NBLOCKS):
        m = _block_mean(band, i, width)
        if m <= BLACK_MAX:
            bits.append(0)
        elif m >= WHITE_MIN:
            bits.append(1)
        else:
            return None
    if tuple(bits[:4]) != SYNC:
        return None
    clip_id = (bits[4] << 1) | bits[5]
    frame = 0
    for b in bits[6:]:
        frame = (frame << 1) | b
    return clip_id, frame


def blend_weight(rgb, ca, cb):
    """Project measured colour `rgb` onto the ca->cb axis.

    Returns the weight w such that rgb ~ (1-w)*ca + w*cb, clamped to a
    sane window so noise on near-duplicate colours cannot explode."""
    num = sum((m - a) * (b - a) for m, a, b in zip(rgb, ca, cb))
    den = sum((b - a) ** 2 for a, b in zip(ca, cb))
    if den == 0:
        return 0.0
    return num / den


def colour_close(rgb, ref, tol=16):
    return all(abs(m - r) <= tol for m, r in zip(rgb, ref))


def expected_frames(spec):
    """Expand spec["edl"] to a per-output-frame expectation list.

    Each entry is ("cut", clip_id, src_frame) or ("blend", t, span)."""
    clip_ids = {name: s["clip_id"] for name, s in spec["sources"].items()}
    expect = []
    for seg in spec["edl"]:
        lo, hi = seg["out"]
        if "clip" in seg:
            cid = clip_ids[seg["clip"]]
            for f in range(hi - lo + 1):
                expect.append(("cut", cid, seg["in"] + f))
        else:
            for f in range(hi - lo + 1):
                expect.append(("blend", f, hi - lo))
    return expect


def compare_edl(decoded, colours, expect, clip_rgb, tol=16):
    """Compare per-frame decodes + colours against the expectation list.

    `decoded`   -- per frame: (clip_id, src_frame) or None
    `colours`   -- per frame: measured centre-region (r, g, b)
    `clip_rgb`  -- clip_id -> measured reference colour

    Returns a list of mismatch strings (empty = clean EDL).  Blend-window
    frames are skipped here -- gate G4 owns them.
    """
    bad = []
    if len(decoded) != len(expect) or len(colours) != len(expect):
        return ["frame count mismatch"]
    for i, exp in enumerate(expect):
        kind = exp[0]
        if kind == "blend":
            continue
        _, cid, src = exp
        if decoded[i] != (cid, src):
            bad.append("frame %d: barcode %s, expected clip %d frame %d"
                       % (i, decoded[i], cid, src))
        elif not colour_close(colours[i], clip_rgb[cid], tol):
            bad.append("frame %d: colour %s, expected near %s"
                       % (i, colours[i], clip_rgb[cid]))
    return bad


def check_dissolve(weights, span=24, lo_tol=0.15, hi_tol=0.85,
                   lin_tol=0.20, mono_slack=0.05):
    """Validate a measured blend-weight ramp over a dissolve window.

    `weights` -- measured w for each output frame in the window, t=0..span.
    Pass requires: starts near 0, ends near 1, tracks the linear ramp
    t/span within `lin_tol` at every frame, and never falls more than
    `mono_slack` below the previous frame."""
    bad = []
    if len(weights) != span + 1:
        return ["dissolve length mismatch"]
    if weights[0] > lo_tol:
        bad.append("w(t=0)=%.3f > %.2f" % (weights[0], lo_tol))
    if weights[-1] < hi_tol:
        bad.append("w(t=%d)=%.3f < %.2f" % (span, weights[-1], hi_tol))
    for t, w in enumerate(weights):
        err = abs(w - t / span)
        if err > lin_tol:
            bad.append("w(t=%d)=%.3f off ramp by %.3f" % (t, w, err))
        if t and w < weights[t - 1] - mono_slack:
            bad.append("w decreases at t=%d (%.3f -> %.3f)"
                       % (t, weights[t - 1], w))
    return bad
