#!/usr/bin/env python3
"""Generate judge/manifest.json: the audio corpus for the transcription demo.

Each utterance is a spoken callsign spelled letter-by-letter in the ICAO
spelling alphabet ("alpha bravo ..."), synthesized as a sum of FSK tones:
every letter maps to two concatenated 60 ms tone bursts, one for the row
and one for the column of its ICAO grid position. The artifact decodes the
frequencies back to grid cells and reads the letters off the manifest's
grid at runtime.

The utterance list is fixed by name (flight ids and lengths); the texts
come from a seeded RNG (random.Random(42)) so the corpus is identical on
every machine. The manifest stores text + tone map + seed; the oracle
texts are thus fully determined.

Output: JSON with
  seed, n_fft, frame_step, frame_len, target_hz, dc_hz, snr_db,
  duration_s, letters (grid: token -> [row_hz, col_hz]),
  utterances: [{id, flight, letters:[tokens], text}]
"""

import json
import math
import random
import sys

SEED = 42
# 6x5 = 30 grid cells, 26 of them used (one per letter), 4 left unused.
ROW_HZ = [300, 400, 500, 600, 700, 800]   # 6 rows, 100 Hz apart
COL_HZ = [1000, 1150, 1300, 1450, 1600]  # 5 columns, 150 Hz apart
VOCAB = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
         "golf", "hotel", "india", "juliet", "kilo", "lima", "mike",
         "november", "oscar", "papa", "quebec", "romeo", "sierra",
         "tango", "uniform", "victor", "whiskey", "xray", "yankee",
         "zulu")
assert len(VOCAB) == 26 and len(VOCAB) <= len(ROW_HZ) * len(COL_HZ)

FLIGHTS = [  # (flight id, letter count) — fixed, seeds the texts
    ("VJ731", 4), ("DL294", 6), ("UA109", 5), ("AS618", 7), ("F9250", 5),
    ("WN1742", 6), ("AC865", 4), ("QF32", 8), ("BA249", 5), ("NH021", 6),
    ("EK203", 7), ("SQ226", 5), ("AF456", 4), ("LH403", 6), ("KE907", 5),
    ("JL005", 7), ("CX840", 5), ("EY231", 6), ("TK1988", 4), ("QR803", 5),
]

SR = 16000


def tone_burst(freq_hz, dur_s, sr=SR):
    """A pure tone burst with 4 ms raised-cosine edges (no clicks)."""
    n = max(1, int(round(dur_s * sr)))
    t = [(i / sr) for i in range(n)]
    edge = max(1, int(0.004 * sr))
    out = []
    for i, ti in enumerate(t):
        w = 1.0
        if i < edge:
            w = 0.5 * (1.0 - math.cos(math.pi * i / edge))
        elif i >= n - edge:
            w = 0.5 * (1.0 - math.cos(math.pi * (n - 1 - i) / edge))
        out.append(math.sin(2.0 * math.pi * freq_hz * ti) * w)
    return out


def main():
    rng = random.Random(SEED)
    grid = {}
    letters = []
    for i, tok in enumerate(VOCAB):
        r, c = divmod(i, len(COL_HZ))
        grid[tok] = [ROW_HZ[r], COL_HZ[c]]
        letters.append(tok)

    utterances = []
    for flight, count in FLIGHTS:
        toks = [rng.choice(VOCAB) for _ in range(count)]
        uid = flight.lower()
        utterances.append({
            "id": uid,
            "flight": flight,
            "letters": toks,
            "text": " ".join(toks),
        })

    man = {
        "seed": SEED,
        "sample_rate": SR,
        "n_fft": 512,
        "frame_step": 160,       # 10 ms hop at 16 kHz
        "frame_len": 512,        # 32 ms analysis window
        "token_hz": 25.0,       # each letter spans two 60 ms bursts = 0.12 s
        "dc_hz": 120.0,         # DC carrier marking token boundaries
        "snr_db": 20.0,         # additive white Gaussian noise level
        "burst_s": 0.060,
        "row_hz": ROW_HZ,
        "col_hz": COL_HZ,
        "letters": letters,
        "grid": grid,
        "utterances": utterances,
    }
    out = sys.argv[1] if len(sys.argv) > 1 else "manifest.json"
    with open(out, "w") as fh:
        json.dump(man, fh, indent=1, sort_keys=True)
        fh.write("\n")
    total = sum(len(u["text"].split()) for u in utterances)
    print(f"manifest: {len(utterances)} utterances, {total} tokens "
          f"-> {out}")


if __name__ == "__main__":
    main()
