#!/usr/bin/env python3
"""Synthesize the demo's audio corpus from judge/manifest.json.

Every utterance is a spoken callsign in the ICAO spelling alphabet,
rendered as FSK tones: each letter is two 60 ms bursts, one at its grid
row frequency and one at its grid column frequency (see gen_manifest.py).
20 dB of seeded Gaussian noise is added so the decoder sees a noisy
channel, like a real one.

Deterministic: the noise for utterance U is drawn from
random.Random(f"{seed}:{U}") turned into Gaussians by Box-Muller over
random.random() draws, so the same manifest gives bit-identical audio on
every machine and Python version.

Usage: synth_corpus.py <manifest.json> <outdir>
Writes outdir/utt_<id>.npy (float32, 16 kHz) + outdir/corpus.json
(checksums, per-utterance sample counts).
"""

import hashlib
import json
import math
import os
import random
import sys

import numpy as np


def tone_burst(freq_hz, n, sr):
    """n samples of a pure tone with 4 ms raised-cosine edges."""
    t = np.arange(n, dtype=np.float64) / sr
    sig = np.sin(2.0 * math.pi * freq_hz * t)
    edge = max(1, int(0.004 * sr))
    ramp = 0.5 * (1.0 - np.cos(math.pi * np.arange(edge) / edge))
    win = np.ones(n)
    win[:edge] = ramp
    win[n - edge:] = ramp[::-1]
    return sig * win


def seeded_gauss(rng, n):
    """n standard-normal floats from rng via Box-Muller (version-stable)."""
    out = []
    while len(out) < n:
        u1, u2 = rng.random(), rng.random()
        r = math.sqrt(-2.0 * math.log1p(-u1))   # u1 in [0,1): log(1-u1) safe
        out.append(r * math.cos(2.0 * math.pi * u2))
    return np.array(out[:n])


def synth_utterance(utt, man):
    """One utterance: random lead-in, back-to-back tone bursts, tail.

    The lead-in and tail are noise-only (like an open mic before the
    push-to-talk click), so the decoder has to find the first burst
    before it can read the burst clock. Everything is drawn from the
    utterance's own seeded RNG, so the audio is bit-reproducible.
    """
    sr = man["sample_rate"]
    burst = max(1, int(round(man["burst_s"] * sr)))
    rng = random.Random(f"{man['seed']}:{utt['id']}")
    lead = int(round(rng.uniform(0.15, 0.35) * sr))
    tail = int(round(rng.uniform(0.10, 0.20) * sr))
    parts = []
    for tok in utt["letters"]:
        row_hz, col_hz = man["grid"][tok]
        parts.append(tone_burst(row_hz, burst, sr))
        parts.append(tone_burst(col_hz, burst, sr))
    sig = np.concatenate(parts)
    sig = sig / np.max(np.abs(sig)) * 0.5        # fixed peak of 0.5
    sig_rms = float(np.sqrt(np.mean(sig ** 2)))
    noise_rms = sig_rms / (10.0 ** (man["snr_db"] / 20.0))
    full = np.zeros(lead + len(sig) + tail)
    full[lead:lead + len(sig)] = sig
    noise = seeded_gauss(rng, len(full))
    noise = noise / np.sqrt(np.mean(noise ** 2)) * noise_rms
    return (full + noise).astype(np.float32)


def main():
    manifest_path, outdir = sys.argv[1], sys.argv[2]
    with open(manifest_path) as fh:
        man = json.load(fh)
    os.makedirs(outdir, exist_ok=True)
    meta = {"manifest_seed": man["seed"], "sample_rate": man["sample_rate"],
            "utterances": {}}
    for utt in man["utterances"]:
        audio = synth_utterance(utt, man)
        name = f"utt_{utt['id']}.npy"
        np.save(os.path.join(outdir, name), audio, allow_pickle=False)
        meta["utterances"][utt["id"]] = {
            "file": name,
            "samples": int(len(audio)),
            "seconds": round(len(audio) / man["sample_rate"], 3),
            "sha256": hashlib.sha256(audio.tobytes()).hexdigest(),
        }
    with open(os.path.join(outdir, "corpus.json"), "w") as fh:
        json.dump(meta, fh, indent=1, sort_keys=True)
        fh.write("\n")
    total = sum(u["samples"] for u in meta["utterances"].values())
    print(f"corpus: {len(meta['utterances'])} utterances, "
          f"{total} samples ({total / man['sample_rate']:.1f} s) -> {outdir}")


if __name__ == "__main__":
    main()
