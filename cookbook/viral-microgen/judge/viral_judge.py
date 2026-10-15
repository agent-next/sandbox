#!/usr/bin/env python3
"""viral-microgen judge: grade one artifact directory against SPEC.md.

    viral_judge.py <artifact_dir> [--seed N] [--json out.json]

Prints one JSON verdict and exits 0 only if every gate passes.  The six gates
are `wav_format`, `shepard_property`, `gif_animation`, `ball_bounces`,
`qr_scans` and `palette_match`; each is numeric, deterministic and compared
against an independent oracle (analytic octave model, frame geometry, two
pinned QR reference libraries, exact RGB set equality) -- never "the tool
ran".

The artifact is read-only input: the judge copies it into its own temp
directory and never writes to the source tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave

import numpy as np
from PIL import Image

# --- judge constants (SPEC.md "Fixed problem statement") -------------------
SR = 22050
MIN_DUR_S = 20.0
MIN_OCTAVES = 3.0
OCTAVE_TOL_OCT = 0.020
MIN_FRAMES = 48
N_COLOURS = 5
MIN_BOUNCES = 4
ZBAR_VERSION = "0.23.92"
ZXING_VERSION = "2.3.0"

REQUIRED = ("shepard.wav", "ball.gif", "qr.png", "palette.png")
GATES = ("wav_format", "shepard_property", "gif_animation", "ball_bounces",
         "qr_scans", "palette_match")

# chroma-tracking window / hop, in samples
PITCH_WIN = 4096
PITCH_HOP = 1024
CHROMA_BINS = 180               # 0.2 cent resolution before refinement
CHROMA_F_REF = 40.0             # the fold reference; the octave it folds at
# spectrum bands for the Shepard signature test
N_BANDS = 8
MIN_MID_TAIL_DB = 8.0


def qr_text(seed: int) -> str:
    return f"VIRAL-MICROGEN-{seed}"


# --------------------------------------------------------------------------
# gate 1: wav_format
# --------------------------------------------------------------------------
def gate_wav_format(path: str) -> dict:
    try:
        with wave.open(path, "rb") as wf:
            nch, sw, fr, nfr = (wf.getnchannels(), wf.getsampwidth(),
                                wf.getframerate(), wf.getnframes())
    except Exception as exc:                       # unparseable is not a WAV
        return dict(passed=False, reason=f"not a readable RIFF/WAVE file: "
                                         f"{type(exc).__name__}: {exc}")
    dur = nfr / fr if fr else 0.0
    checks = {
        "mono": nch == 1,
        "sampwidth_2": sw == 2,
        "sample_rate_22050": fr == SR,
        "duration_ge_20s": dur >= MIN_DUR_S,
    }
    bad = [k for k, v in checks.items() if not v]
    return dict(passed=not bad,
                reason="all format checks passed" if not bad
                       else "failed: " + ", ".join(bad),
                channels=nch, sampwidth=sw, sample_rate_hz=fr,
                nframes=nfr, duration_s=round(dur, 4))


# --------------------------------------------------------------------------
# gate 2: shepard_property
# --------------------------------------------------------------------------
def read_pcm_mono(path: str) -> np.ndarray:
    with wave.open(path, "rb") as wf:
        nch, sw, fr = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if sw != 2:
        raise ValueError(f"sampwidth {sw} is not 16-bit")
    a = np.frombuffer(raw, dtype="<i2").astype(np.float64)
    if nch > 1:
        a = a.reshape(-1, nch).mean(axis=1)
    return a / 32768.0


def track_chroma(x: np.ndarray, sr: int,
                 f_ref: float) -> tuple[np.ndarray, np.ndarray]:
    """Track the Shepard glide as a folded (chroma) phase, per short frame.

    For each Hann-windowed frame the power spectrum's log2 frequencies are
    folded modulo one octave onto a circular histogram of `CHROMA_BINS` bins.
    A Shepard tone's partials all sit at the same chroma -- r(t), modulo an
    octave -- so the envelope-weighted peak of that histogram is r(t) mod 1.
    The peak is refined by the power-weighted circular mean of the bins
    around it, which resolves the phase far below one bin.

    Returns (times, phases) with phases in [0, 1).  This is the natural
    observable for the Shepard illusion: a plain steady tone gives a constant
    phase and a plain sweep gives a phase that ramps but never closes.
    """
    if len(x) < PITCH_WIN:
        raise ValueError("signal shorter than one analysis window")
    win = np.hanning(PITCH_WIN)
    freqs = np.fft.rfftfreq(PITCH_WIN, 1.0 / sr)
    band = (freqs >= f_ref * 0.9) & (freqs <= min(11000.0, sr / 2.0))
    if band.sum() < CHROMA_BINS:
        raise ValueError("analysis band too narrow for the chroma histogram")
    fold = np.log2(freqs[band] / f_ref) % 1.0
    bins = (fold * CHROMA_BINS).astype(int) % CHROMA_BINS
    nb = CHROMA_BINS
    angles = 2.0 * np.pi * np.arange(nb) / nb

    ts, phis = [], []
    for start in range(0, len(x) - PITCH_WIN + 1, PITCH_HOP):
        frame = x[start:start + PITCH_WIN] * win
        power = np.abs(np.fft.rfft(frame)) ** 2
        h = np.zeros(nb)
        np.add.at(h, bins, power[band])
        if h.sum() <= 0:
            raise ValueError("silent analysis window")
        k = int(np.argmax(h))
        idx = np.array([(k + d) % nb for d in range(-3, 4)])
        z = (h[idx] * np.exp(1j * angles[idx])).sum()
        if z == 0:
            raise ValueError("degenerate chroma histogram")
        ts.append((start + PITCH_WIN / 2.0) / sr)
        phis.append((np.angle(z) / (2.0 * np.pi)) % 1.0)
    return np.array(ts), np.array(phis)


def unfold_rising(phis: np.ndarray) -> np.ndarray:
    """Unwrap a folded phase into a monotonically rising trajectory."""
    out = [float(phis[0])]
    for p in phis[1:]:
        d = float(p) - out[-1]
        while d < -0.5:
            d += 1.0
        while d > 0.5:
            d -= 1.0
        out.append(out[-1] + d)
    return np.array(out)


def band_energies(x: np.ndarray, sr: int) -> np.ndarray:
    """Energy in N_BANDS octave bands, band 0 the lowest."""
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freqs = np.fft.rfftfreq(len(x), 1.0 / sr)
    f_lo = 40.0
    f_hi = min(8000.0, sr / 2.0)
    edges = f_lo * 2.0 ** np.arange(N_BANDS + 1)
    e = np.zeros(N_BANDS)
    for b in range(N_BANDS):
        lo, hi = edges[b], min(edges[b + 1], f_hi)
        m = (freqs >= lo) & (freqs < hi)
        e[b] = spec[m].sum()
    return e


def gate_shepard_property(path: str) -> dict:
    try:
        x = read_pcm_mono(path)
        ts, phis = track_chroma(x, SR, CHROMA_F_REF)
    except Exception as exc:
        return dict(passed=False, reason=f"chroma tracking failed: "
                                         f"{type(exc).__name__}: {exc}")
    glide = unfold_rising(phis)

    slope, intercept = np.polyfit(ts, glide, 1)
    fit = slope * ts + intercept
    ss_res = float(((glide - fit) ** 2).sum())
    ss_tot = float(((glide - glide.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # The oracle is the analytic fit: the first and last analysis windows are
    # centred inside the file, so the glide at the file boundaries is read off
    # the fitted line rather than from the end windows.
    t_end = len(x) / SR
    r_start = float(intercept)
    r_end = float(intercept + slope * t_end)
    span_oct = r_end - r_start
    ratio_oct = span_oct
    octave_multiple = abs(ratio_oct - round(ratio_oct)) <= OCTAVE_TOL_OCT
    returns = (2.0 ** r_end) >= (2.0 ** r_start) * 0.95

    e = band_energies(x, SR)
    mid = int(np.argmax(e))
    unimodal = bool(np.all(np.diff(e[:mid + 1]) >= 0) and
                    np.all(np.diff(e[mid:]) <= 0))
    middle_band = 2 <= mid <= 6
    tail = float(e[max(mid + 1, N_BANDS - 2):].sum())
    mid_energy = float(e[mid])
    mid_tail_db = (float("inf") if tail <= 0
                   else 10.0 * math.log10(mid_energy / tail))

    checks = {
        "rising_slope": slope > 0,
        "log_linear_r2_ge_0.995": r2 >= 0.995,
        "span_ge_3_octaves": span_oct >= MIN_OCTAVES,
        "pitch_class_return": returns and octave_multiple,
        "spectrum_unimodal": unimodal,
        "spectrum_max_middle_band": middle_band,
        "mid_tail_ge_8db": mid_tail_db >= MIN_MID_TAIL_DB,
    }
    bad = [k for k, v in checks.items() if not v]
    return dict(passed=not bad,
                reason="all Shepard checks passed" if not bad
                       else "failed: " + ", ".join(bad),
                slope_oct_per_s=round(float(slope), 6),
                fit_r2=round(r2, 6), span_octaves=round(span_oct, 4),
                r_start_oct=round(r_start, 4), r_end_oct=round(r_end, 4),
                return_octaves=round(ratio_oct, 4),
                band_energies=[round(float(v), 4) for v in e],
                peak_band=mid, mid_tail_db=round(mid_tail_db, 3),
                n_hops=int(len(phis)))


# --------------------------------------------------------------------------
# gates 3 & 4: the GIF
# --------------------------------------------------------------------------
def read_gif_frames(path: str):
    """Every frame as an RGB array plus its size and duration.

    Frames are read through a full RGB rendering rather than the paletted
    view: a GIF whose later frames carry local colour tables is handed back
    by Pillow in RGB mode, so the palette is not a reliable per-frame handle.
    """
    frames = []
    with Image.open(path) as g:
        n = getattr(g, "n_frames", 1)
        loop = g.info.get("loop", None)
        for i in range(n):
            g.seek(i)
            rgb = g.convert("RGB")
            frames.append(dict(rgb=np.asarray(rgb, dtype=np.uint8),
                               size=rgb.size,
                               duration=g.info.get("duration", 0)))
    return frames, loop


def frame_colours(f) -> dict[tuple, int]:
    """Colour -> pixel count for one frame."""
    vals, cts = np.unique(f["rgb"].reshape(-1, 3), axis=0, return_counts=True)
    return {tuple(int(x) for x in v): int(c) for v, c in zip(vals, cts)}


def gate_gif_animation(path: str) -> dict:
    try:
        frames, loop = read_gif_frames(path)
    except Exception as exc:
        return dict(passed=False, reason=f"GIF did not decode: "
                                         f"{type(exc).__name__}: {exc}")
    n = len(frames)
    sizes = {f["size"] for f in frames}
    durs = [f["duration"] for f in frames]
    per_frame = [set(frame_colours(f)) for f in frames]
    union = set().union(*per_frame) if per_frame else set()

    checks = {
        "n_frames_ge_48": n >= MIN_FRAMES,
        "all_durations_positive": all(d and d > 0 for d in durs),
        "single_size": len(sizes) == 1,
        "loop_infinite": loop == 0,
        "no_sixth_colour": all(len(s) <= N_COLOURS for s in per_frame),
        "every_frame_within_global_set": all(s <= union for s in per_frame),
        "exactly_5_colours": len(union) == N_COLOURS,
    }
    bad = [k for k, v in checks.items() if not v]
    return dict(passed=not bad,
                reason="all GIF checks passed" if not bad
                       else "failed: " + ", ".join(bad),
                n_frames=n, size=list(frames[0]["size"]) if frames else [],
                frame_duration_ms=durs[0] if durs else None, loop=loop,
                distinct_colours=len(union),
                colours_used=[list(c) for c in sorted(union)])


def ball_mask(frames, ball):
    """Boolean stack (T, H, W) of ball pixels, one frame at a time."""
    want = np.array(ball, dtype=np.uint8)
    return [np.all(f["rgb"] == want, axis=2) for f in frames]


def _pick_ball_colour(frames, bg, floor):
    """The frame colour that is neither background nor floor and is roundest
    (area / perimeter closest to that of a disc) in the first frame."""
    best = None
    counts = frame_colours(frames[0])
    rgb = frames[0]["rgb"]
    for c, count in counts.items():
        if c == bg or c == floor or count < 30:
            continue
        a = np.all(rgb == np.array(c, dtype=np.uint8), axis=2)
        # erode by one pixel: the component's interior
        er = np.zeros_like(a)
        er[1:-1, 1:-1] = (a[1:-1, 1:-1] & a[:-2, 1:-1] & a[2:, 1:-1] &
                          a[1:-1, :-2] & a[1:-1, 2:])
        per = int(a.sum() - er.sum())
        roundness = 4.0 * math.pi * count / (per * per) if per else 0.0
        if best is None or roundness > best[1]:
            best = (c, roundness, count)
    return best


def gate_ball_bounces(path: str) -> dict:
    try:
        frames, _loop = read_gif_frames(path)
    except Exception as exc:
        return dict(passed=False, reason=f"GIF did not decode: "
                                         f"{type(exc).__name__}: {exc}")
    if len(frames) < 2:
        return dict(passed=False,
                    reason="a single frame has no motion to measure")
    # background: the most common colour of the whole first frame.
    # floor: the most common colour of the bottom fifth of the frame.
    by_count = frame_colours(frames[0])
    if len(by_count) < 3:
        return dict(passed=False,
                    reason=f"only {len(by_count)} colours in the frames")
    ordered = sorted(by_count.items(), key=lambda kv: -kv[1])
    bg = ordered[0][0]
    rgb = frames[0]["rgb"]
    h = rgb.shape[0]
    vals, cts = np.unique(rgb[int(h * 0.8):, :].reshape(-1, 3), axis=0,
                          return_counts=True)
    floor = tuple(int(v) for v in vals[int(np.argmax(cts))])
    if floor == bg:
        floor = ordered[1][0]

    cand = _pick_ball_colour(frames, bg, floor)
    if cand is None:
        return dict(passed=False, reason="no ball-coloured pixels found")
    ball = cand[0]

    masks = ball_mask(frames, ball)
    bottoms, heights, widths = [], [], []
    for m in masks:
        rows = np.where(m.any(axis=1))[0]
        cols = np.where(m.any(axis=0))[0]
        if len(rows) == 0:
            bottoms.append(None)
            heights.append(0)
            widths.append(0)
            continue
        bottoms.append(int(rows.max()))
        heights.append(int(rows.max() - rows.min() + 1))
        widths.append(int(cols.max() - cols.min() + 1))
    valid = [b for b in bottoms if b is not None]
    if not valid:
        return dict(passed=False, reason="the ball mask is empty in every "
                                         "frame")

    # The floor row is the lowest image row the ball ever reaches: a bouncing
    # ball touches its floor once per bounce, so the mode of the bottom rows
    # (and the maximum) both land on it.
    vals, cts = np.unique(valid, return_counts=True)
    floor_row = int(vals[int(np.argmax(cts))])
    if floor_row < int(np.max(valid)):
        floor_row = int(np.max(valid))
    arr = np.array([b if b is not None else floor_row for b in bottoms])
    # local maxima of the ball's bottom edge, i.e. the frames in which the
    # ball is in contact with the floor: b >= neighbours and on the floor row
    n_bounces = 0
    for i in range(1, len(arr) - 1):
        if arr[i] >= arr[i - 1] and arr[i] > arr[i + 1] and \
                abs(int(arr[i]) - floor_row) <= 2:
            n_bounces += 1
    rises = [floor_row - (b if b is not None else floor_row) for b in bottoms]
    max_rise = max(rises) if rises else 0
    x_centres = []
    for m in masks:
        cols = np.where(m.any(axis=0))[0]
        x_centres.append(float(cols.mean()) if len(cols) else float("nan"))
    xs = [v for v in x_centres if v == v]
    travel = (max(xs) - min(xs)) if xs else 0.0
    # every contact frame must sit on the same floor row, within 2 px
    contacts = [int(b) for b in bottoms
                if b is not None and abs(int(b) - floor_row) <= 2]
    floor_ok = bool(contacts) and all(abs(b - floor_row) <= 2 for b in contacts)

    checks = {
        "n_bounces_ge_4": n_bounces >= MIN_BOUNCES,
        "floor_row_constant_within_2px": floor_ok,
        "rise_ge_25px": max_rise >= 25,
        "travel_ge_120px": travel >= 120,
    }
    bad = [k for k, v in checks.items() if not v]
    return dict(passed=not bad,
                reason="all bounce checks passed" if not bad
                       else "failed: " + ", ".join(bad),
                ball_colour=list(ball), background=list(bg), floor=list(floor),
                floor_row=floor_row, n_bounces=n_bounces,
                max_rise_px=int(max_rise), x_travel_px=round(travel, 3),
                bottom_rows=[None if b is None else int(b) for b in bottoms])


# --------------------------------------------------------------------------
# gate 5: qr_scans
# --------------------------------------------------------------------------
def _zbar_decode(path: str) -> tuple[str | None, str]:
    try:
        proc = subprocess.run(["zbarimg", "--raw", "--quiet", path],
                              capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return None, "zbarimg not installed"
    except subprocess.TimeoutExpired:
        return None, "zbarimg timed out"
    if proc.returncode != 0:
        return None, f"zbarimg exit {proc.returncode}: {proc.stderr.strip()}"
    return proc.stdout.strip(), "ok"


def _zxing_decode(path: str) -> tuple[str | None, str]:
    try:
        import zxingcpp
    except ImportError as exc:
        return None, f"zxingcpp not installed: {exc}"
    try:
        res = zxingcpp.read_barcode(Image.open(path))
    except Exception as exc:
        return None, f"zxingcpp error: {type(exc).__name__}: {exc}"
    if res is None or not getattr(res, "text", ""):
        return None, "zxingcpp found no barcode"
    return res.text, "ok"


def gate_qr_scans(path: str, seed: int) -> dict:
    expected = qr_text(seed)
    zbar, zbar_note = _zbar_decode(path)
    zxing, zxing_note = _zxing_decode(path)
    checks = {
        "zbar_decodes": zbar is not None,
        "zxing_decodes": zxing is not None,
        "zbar_matches_planted": zbar == expected,
        "zxing_matches_planted": zxing == expected,
        "both_agree": zbar is not None and zbar == zxing,
    }
    bad = [k for k, v in checks.items() if not v]
    return dict(passed=not bad,
                reason="both decoders returned the planted string"
                       if not bad else "failed: " + ", ".join(bad),
                expected=expected, zbar=zbar, zxing=zxing,
                zbar_note=zbar_note, zxing_note=zxing_note)


# --------------------------------------------------------------------------
# gate 6: palette_match
# --------------------------------------------------------------------------
def gate_palette_match(palette_path: str, frames) -> dict:
    try:
        with Image.open(palette_path) as p:
            im = p.convert("RGB")
    except Exception as exc:
        return dict(passed=False, reason=f"palette.png did not decode: "
                                         f"{type(exc).__name__}: {exc}")
    a = np.asarray(im, dtype=np.uint8)
    vals, cts = np.unique(a.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-cts)
    if len(order) < 2:
        return dict(passed=False, reason="palette card is a single flat colour")
    bg = tuple(int(v) for v in vals[order[0]])
    # swatches: the remaining colours that are not the background
    swatches = [tuple(int(v) for v in vals[i]) for i in order
                if tuple(int(v) for v in vals[i]) != bg]
    if len(swatches) != N_COLOURS:
        return dict(passed=False,
                    reason=f"palette card has {len(swatches)} swatch colours, "
                           f"expected {N_COLOURS}",
                    swatch_colours=[list(c) for c in swatches])

    # equal-size check: every swatch colour must cover (almost) the same area
    areas = {}
    for c in swatches:
        areas[c] = int(cts[np.where(np.all(vals == np.array(c), axis=1))[0][0]])
    amin, amax = min(areas.values()), max(areas.values())
    equal_size = amin > 0 and (amax - amin) / amax <= 0.02

    # GIF colours, with the count of pixels each occupies across all frames
    gif_counts: dict[tuple[int, int, int], int] = {}
    for f in frames:
        for c, count in frame_colours(f).items():
            gif_counts[c] = gif_counts.get(c, 0) + count
    gif_set = set(gif_counts)

    checks = {
        "exactly_5_swatches": len(swatches) == N_COLOURS,
        "swatches_equal_size": equal_size,
        "swatches_exact_gif_colours": set(swatches) <= gif_set,
        "every_gif_colour_on_card": gif_set <= set(swatches),
        "each_swatch_ge_50px_in_gif": all(gif_counts.get(c, 0) >= 50
                                          for c in swatches),
    }
    bad = [k for k, v in checks.items() if not v]
    return dict(passed=not bad,
                reason="palette card restates the GIF colour set exactly"
                       if not bad else "failed: " + ", ".join(bad),
                background=list(bg), swatch_colours=[list(c) for c in swatches],
                swatch_areas={f"{c[0]},{c[1]},{c[2]}": areas[c]
                              for c in swatches},
                gif_colours={f"{c[0]},{c[1]},{c[2]}": gif_counts[c]
                             for c in sorted(gif_set)})


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def validate(art: str) -> dict | None:
    """Return a failure verdict if the artifact is structurally invalid.

    Validation happens before any gate runs: a missing file, a directory
    instead of a file, or an empty file fails every gate with that reason --
    a malformed artifact must never be reported as a partial pass.
    """
    if not os.path.isdir(art):
        return dict(reason=f"artifact path {art!r} is not a directory")
    for name in REQUIRED:
        p = os.path.join(art, name)
        if not os.path.exists(p):
            return dict(reason=f"missing required file {name}")
        if not os.path.isfile(p):
            return dict(reason=f"{name} is not a regular file")
        if os.path.getsize(p) == 0:
            return dict(reason=f"{name} is empty")
    return None


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def grade(art: str, seed: int) -> dict:
    t0 = time.monotonic()
    verdict: dict = dict(artifact=os.path.abspath(art), seed=seed,
                         qr_expected=qr_text(seed))
    invalid = validate(art)
    if invalid is not None:
        verdict.update(passed=False, failed_gate=None, gates={},
                       reason=invalid["reason"])
        verdict["timing"] = dict(total_s=round(time.monotonic() - t0, 4))
        return verdict

    work = tempfile.mkdtemp(prefix="viral-judge-")
    try:
        # grade a copy: the artifact must never be able to touch the source
        for name in REQUIRED:
            shutil.copy2(os.path.join(art, name), os.path.join(work, name))
        p = {name: os.path.join(work, name) for name in REQUIRED}
        verdict["artifact_sha256"] = {n: sha256_file(p[n]) for n in REQUIRED}

        gates: dict[str, dict] = {}
        gates["wav_format"] = gate_wav_format(p["shepard.wav"])
        gates["shepard_property"] = gate_shepard_property(p["shepard.wav"])
        try:
            frames, _loop = read_gif_frames(p["ball.gif"])
        except Exception as exc:
            err = dict(passed=False, reason=f"GIF did not decode: "
                                            f"{type(exc).__name__}: {exc}")
            gates["gif_animation"] = err
            gates["ball_bounces"] = dict(err)
            frames = None
        else:
            gates["gif_animation"] = gate_gif_animation(p["ball.gif"])
            gates["ball_bounces"] = gate_ball_bounces(p["ball.gif"])
        gates["qr_scans"] = gate_qr_scans(p["qr.png"], seed)
        if frames is None:
            gates["palette_match"] = dict(passed=False,
                                          reason="GIF did not decode")
        else:
            gates["palette_match"] = gate_palette_match(p["palette.png"], frames)

        failed = [g for g in GATES if not gates[g]["passed"]]
        verdict["gates"] = gates
        verdict["passed"] = not failed
        verdict["failed_gate"] = failed[0] if failed else None
        verdict["reason"] = ("all gates passed" if not failed
                             else "; ".join(f"{g}: {gates[g]['reason']}"
                                            for g in failed))
        verdict["timing"] = dict(total_s=round(time.monotonic() - t0, 4))
        return verdict
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    verdict = grade(args.artifact, args.seed)
    out = json.dumps(verdict, indent=2, sort_keys=True)
    print(out)
    if args.json:
        with open(args.json, "w") as f:
            f.write(out + "\n")
    return 0 if verdict.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
