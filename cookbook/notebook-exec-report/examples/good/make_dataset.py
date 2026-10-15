#!/usr/bin/env python3
"""Generate the pinned housing dataset for the notebook-exec-report demo.

Synthetic, but rigorous: a documented generator (documented seed, documented
linear signal in the standardized feature space, Gaussian noise), so the
normative coefficient vector is exact by construction and the judge can check
a fit against it.  Written as examples/good/make_dataset.py next to the CSV it
produces, so the data's provenance is auditable.

Usage:  python3 make_dataset.py [outdir]     # writes dataset.csv
Stdlib + numpy + pandas only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- generator constants (documented, part of the artifact's specification)
GEN_SEED = 987654321
N_ROWS = 1600
W_TRUE = np.array([0.30, 0.10, 0.25, -0.08, 0.05, -0.20, 0.45, -0.35])
NOISE_STD = 0.30
PRICE_SCALE = 2.0          # $1e5 per unit, so the median price is ~2e5

FEATURES = [
    "MED_INC", "HOUSEHOLDS", "AVE_ROOMS", "AVE_BEDRMS",
    "POPULATION", "AVE_OCCUPANCY", "LAT", "LONG",
]
TARGET = "MED_VALUE"


def build(seed: int = GEN_SEED, n: int = N_ROWS) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cols = {
        # median household income, $1e3  (right-skewed, positive)
        "MED_INC": rng.lognormal(1.2, 0.5, n).round(5),
        "HOUSEHOLDS": rng.lognormal(6.5, 0.8, n).round(3),
        "AVE_ROOMS": rng.lognormal(1.5, 0.25, n).round(5),
        "AVE_BEDRMS": rng.lognormal(-0.3, 0.2, n).round(5),
        "POPULATION": rng.lognormal(7.2, 0.9, n).round(3),
        "AVE_OCCUPANCY": rng.lognormal(0.4, 0.3, n).round(5),
        "LAT": (34.0 + rng.normal(0.0, 1.8, n)).round(5),
        "LONG": (-118.0 + rng.normal(0.0, 1.8, n)).round(5),
    }
    x = np.column_stack([cols[c] for c in FEATURES])
    # linear signal in the *standardized* feature space, plus Gaussian noise
    signal = (x - x.mean(axis=0)) / x.std(axis=0) @ W_TRUE
    price = PRICE_SCALE * np.exp(signal + rng.normal(0.0, NOISE_STD, n))
    cols[TARGET] = price.round(5)
    return pd.DataFrame(cols)[FEATURES + [TARGET]]


def main() -> int:
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    df = build()
    dest = outdir / "dataset.csv"
    df.to_csv(dest, index=False)
    print(f"make_dataset: wrote {dest} ({len(df)} rows x {df.shape[1]} cols, "
          f"{dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
