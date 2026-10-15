#!/usr/bin/env python3
"""Generate the pinned OHLCV fixture for the backtest-equity demo.

Fully deterministic (seeded, stdlib only): no third-party data is fetched,
so there is no external citation needed.  The output is a synthetic daily
OHLCV series that is realistic enough for a momentum backtest to be
interesting (trending regimes, volatility clustering, realistic wicks),
and exactly reproducible: the same --seed always gives the same file.

Usage:
    python3 tools/make_fixture.py --out tools/data/ohlcv.csv --seed 20261014

Writes:
    tools/data/ohlcv.csv       the OHLCV fixture (ISO date, O/H/L/C/V)
    tools/data/ohlcv.sha256    sha256 of that exact file (checked by G1)
"""

from __future__ import annotations

import argparse
import hashlib
import math
import random
from datetime import date, timedelta
from pathlib import Path

# A fixed, public start date: the fixture is a property of the repo, not
# of when it is generated.  10 years of business days ~= 2517 rows.
START = date(2014, 1, 2)
N_DAYS = 2517
OPEN_PRICE = 100.0
DRIFT = 0.0004          # per-day drift under the trend regime
BASE_VOL = 0.012        # per-day log-return sigma baseline
REGIME_LEN = (60, 180)  # business days per regime, uniform draw


def gen_prices(rng: random.Random, n: int) -> list[tuple[float, float, float, float]]:
    """Gearest-neighbour bootstrap-free synthetic path with regime switching.

    Returns (open, high, low, close) per day.  The path is generated with a
    simple recursion on the *log* price: close-to-close log returns are
    i.i.d. within a regime (trend up / trend down / chop), then mapped to
    O/H/L/C with a realistic intraday range.  No day depends on future
    data: this is a pure recursion from the start date.
    """
    rows: list[tuple[float, float, float, float]] = []
    logp = math.log(OPEN_PRICE)
    regime_left = 0
    drift, vol = DRIFT, BASE_VOL
    prev_close = OPEN_PRICE
    for _ in range(n):
        if regime_left <= 0:
            regime_left = rng.randint(*REGIME_LEN)
            u = rng.random()
            if u < 0.38:
                drift, vol = DRIFT, BASE_VOL            # trend up
            elif u < 0.62:
                drift, vol = -DRIFT, BASE_VOL * 1.05    # trend down
            else:
                drift, vol = 0.0, BASE_VOL * 1.35       # chop / high vol
        regime_left -= 1
        # log close-to-close return for today
        shock = rng.gauss(0.0, 1.0)
        r = drift + vol * shock
        close = prev_close * math.exp(r)
        # intraday: open near prev close with a small gap, range proportional to vol
        gap = prev_close * vol * 0.15 * rng.gauss(0.0, 1.0)
        o = prev_close * math.exp(gap)
        hi = max(o, close) * (1.0 + abs(rng.gauss(0.0, vol * 0.35)))
        lo = min(o, close) * (1.0 - abs(rng.gauss(0.0, vol * 0.35)))
        rows.append((round(o, 4), round(hi, 4), round(lo, 4), round(close, 4)))
        prev_close = close
    return rows


def gen_volume(rng: random.Random, n: int, rows, days) -> list[int]:
    """Volume correlated with absolute daily move + weekly seasonality."""
    vols = []
    for i, (o, h, l, c) in enumerate(rows):
        move = abs(c - o) / o if o else 0.0
        base = 1.2e6
        scale = base * (1.0 + 25.0 * move) * rng.uniform(0.7, 1.3)
        # weekly seasonality: Mondays and Fridays heavier
        seasonal = 1.15 if days[i].weekday() in (0, 4) else 1.0
        vols.append(int(scale * seasonal))
    return vols


def daterange(n: int) -> list[date]:
    """n business days starting on START."""
    days = []
    d = START
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("tools/data/ohlcv.csv"))
    ap.add_argument("--seed", type=int, default=20261014)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    rows = gen_prices(rng, N_DAYS)
    days = daterange(N_DAYS)
    vols = gen_volume(rng, N_DAYS, rows, days)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("date,open,high,low,close,volume\n")
        for d, (o, h, l, c), v in zip(days, rows, vols):
            fh.write(f"{d.isoformat()},{o:.4f},{h:.4f},{l:.4f},{c:.4f},{v}\n")
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.out.with_suffix(".csv.sha256").write_text(
        f"{digest}  {args.out.name}\n", encoding="utf-8")
    print(f"make_fixture: wrote {args.out} ({N_DAYS} rows, seed {args.seed})")
    print(f"make_fixture: sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
