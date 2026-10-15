#!/usr/bin/env python3
"""Batch FSK callsign transcriber (the demo's known-good artifact).

Reads the runtime manifest (grid: ICAO token -> [row_hz, col_hz]) and the
utterance audio files (utt_<id>.npy, 16 kHz float32) beside it, decodes
every letter from its two 60 ms tone bursts, and writes transcripts.json:
{"transcripts": {<id>: "<token token ...>"}}

Pipeline:
  1. VAD: a 20 ms moving-RMS envelope finds the push-to-talk region
     (each file has a noise-only lead-in before the first burst).
  2. burst clock: a fine alignment search places the 60 ms burst grid
     relative to the envelope crossing.
  3. batched Goertzel: every burst of every utterance is stacked into ONE
     (n_bursts_total, burst_len) matrix and scored against every candidate
     frequency in a single complex matmul — the "batch" in
     batch-transcribe. A GPU (or a BLAS-backed CPU) does one GEMM for the
     whole corpus, not a per-file loop.
  4. lookup: argmax band per burst pair -> grid cell -> manifest token.

Runs on CPU by default and on CUDA when torch finds a device, printing
the device it used. Outputs are byte-identical on both.

Usage: python3 transcriber.py   (run from a directory holding manifest.json
and utt_*.npy; writes transcripts.json there)
"""

import json
import math
import os

import numpy as np
import torch

MANIFEST = "manifest.json"
OUT = "transcripts.json"

ONSET_WIN_S = 0.004        # onset-detection window (short: sharp step)
ONSET_THRESH = 0.12        # between the noise floor (~0.03 RMS) and tone
ONSET_LAG = 8              # causal-window lag of the crossing vs onset
BURST_POWER_THRESH = 0.25  # of the first burst's power (noise is ~1%)
EDGE_FRACTION = 0.10       # burst edges skipped (raised-cosine ramps)


def load_audio(path):
    return np.load(path).astype(np.float64)


def envelope(x, win):
    """Moving RMS of |x| over `win` samples (causal window)."""
    p = np.cumsum(x ** 2)
    p = np.concatenate([[0.0], p])
    n = len(x)
    if n < win:
        return np.full(n, math.sqrt(p[-1] / n))
    out = np.empty(n)
    out[:win - 1] = np.sqrt(p[1:win] / np.arange(1, win))
    idx = np.arange(win - 1, n)
    out[win - 1:] = np.sqrt((p[idx + 1] - p[idx - win + 1]) / win)
    return out


def align_burst_clock(x, sr, burst, skip):
    """Find the burst-grid start from the push-to-talk onset.

    The corpus has a noise-only lead-in, so the first tone burst is a
    sharp step in the 4 ms RMS envelope; the burst clock is then simply
    samples [onset, onset + k*burst). ONSET_LAG corrects the causal
    window's delay. Returns (start, live_burst_count): live counts
    leading bursts whose core energy is at least BURST_POWER_THRESH of
    the first burst's (tone cores hold ~100x the noise energy, so the
    cut is unambiguous).
    """
    win = max(2, int(round(ONSET_WIN_S * sr)))
    env = envelope(x, win)
    if len(env) == 0 or float(env.max()) <= 0.0:
        return 0, 0
    crossing = int(np.nonzero(env > ONSET_THRESH)[0][0])
    start = max(0, crossing - ONSET_LAG)

    first_core = None
    live = 0
    k = 0
    while start + (k + 1) * burst <= len(x):
        s = start + k * burst
        core = x[s + skip:s + burst - skip]
        p = float(np.sum(core ** 2))
        if first_core is None:
            if p <= 0.0:
                return 0, 0
            first_core = p
        if p >= BURST_POWER_THRESH * first_core:
            live += 1
        else:
            break
        k += 1
    return start, live


def decode_batch(paths, manifest, device=None):
    """Decode every audio file in one batched pass.

    All live bursts of all utterances are stacked into a single matrix
    and scored with one complex matmul against all candidate frequencies;
    the argmax per burst pair gives each letter's grid cell.
    Returns {utterance id: token string}.
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    sr = manifest["sample_rate"]
    burst = int(round(manifest["burst_s"] * sr))
    skip = int(round(burst * EDGE_FRACTION))
    rows = manifest["row_hz"]
    cols = manifest["col_hz"]
    grid = manifest["grid"]
    inv = {(r, c): tok for tok, (r, c) in grid.items()}

    # Pass 1 (numpy): VAD + burst clock per file; collect live bursts.
    jobs = []       # (utterance id, n_tokens)
    blocks = []     # core slices of live bursts, in utterance order
    for path in paths:
        name = os.path.basename(path)
        if not (name.startswith("utt_") and name.endswith(".npy")):
            continue
        uid = name[len("utt_"):-len(".npy")]
        x = load_audio(path)
        start, live = align_burst_clock(x, sr, burst, skip)
        n_tok = live // 2
        jobs.append((uid, n_tok))
        for k in range(live):
            s = start + k * burst
            blocks.append(x[s + skip:s + burst - skip])
    if not blocks:
        return {uid: "" for uid, _ in jobs}

    # Pass 2 (torch): ONE matmul scores every burst against every tone.
    B = torch.from_numpy(np.stack(blocks)).to(device)
    freqs = torch.tensor(rows + cols, dtype=torch.float64, device=device)
    power = goertzel_matrix(B, freqs, sr).cpu()

    # Pass 3: burst pairs -> grid cells -> manifest tokens.
    transcripts = {}
    i = 0
    for uid, n_tok in jobs:
        toks = []
        for _ in range(n_tok):
            r_hz = rows[int(torch.argmax(power[i, :len(rows)]))]
            c_hz = cols[int(torch.argmax(power[i + 1, len(rows):]))]
            i += 2
            tok = inv.get((r_hz, c_hz))
            if tok:
                toks.append(tok)
        transcripts[uid] = " ".join(toks)
    return transcripts


def goertzel_matrix(bursts, freqs, sr):
    """Power of each burst (rows) at each frequency (columns).

    One complex matmul on the active device:
    B (n_bursts, len) @ W (len, n_freqs).conj().T, power = |B @ W|^2.
    """
    n = bursts.shape[1]
    t = torch.arange(n, dtype=torch.float64, device=bursts.device) / sr
    W = torch.view_as_complex(torch.stack(
        [torch.cos(2 * math.pi * freqs[:, None] * t[None, :]),
         -torch.sin(2 * math.pi * freqs[:, None] * t[None, :])],
        dim=-1))
    z = bursts.to(W.dtype) @ W.conj().T
    return z.real.square() + z.imag.square()


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    with open(MANIFEST) as fh:
        man = json.load(fh)
    names = sorted(f for f in os.listdir(".")
                   if f.startswith("utt_") and f.endswith(".npy"))
    paths = [os.path.join(".", f) for f in names]
    transcripts = decode_batch(paths, man, device)
    with open(OUT, "w") as fh:
        json.dump({"transcripts": transcripts}, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"transcribed {len(transcripts)} utterances on {device.type} "
          f"-> {OUT}")


if __name__ == "__main__":
    main()
