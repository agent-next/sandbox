#!/usr/bin/env python3
"""Reference agent engine for the backtest-equity demo (examples/good).

Vectorized 12/26 dual-momentum backtest on the pinned OHLCV fixture with
10 bps proportional costs.  This file is an EXAMPLE artifact: the agent in
the sandbox writes (and, with the judge, fixes) its own version of this.
The judge never executes it.

Signal: sma12(t) - sma26(t) on the close series, computed causally.
Position: +1 while sma12 > sma26, else 0 (flat).  The signal is lagged
LOOKAHEAD_SHIFT bars before sizing: position held over [t, t+1) is the
signal observed at the close of t - LOOKAHEAD_SHIFT (no lookahead).
Trade cost: 10 bps of the notional whenever the position changes.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

LOOKAHEAD_SHIFT = 1      # signal bars lagged before sizing (no lookahead)
COST_BPS = 10.0          # proportional cost per side, one-way
TRADING_DAYS = 252
ANNUAL_RISK_FREE = 0.0   # simple Sharpe vs zero risk-free rate


def sma(x: np.ndarray, n: int) -> np.ndarray:
    """Causal simple moving average: sma[i] = mean(x[i-n+1..i]), NaN before."""
    out = np.full_like(x, np.nan, dtype=float)
    c = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def backtest(ohlcv_csv: Path) -> dict:
    with ohlcv_csv.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    dates = [r["date"] for r in rows]
    close = np.array([float(r["close"]) for r in rows], dtype=float)
    n = len(close)

    s12 = sma(close, 12)
    s26 = sma(close, 26)
    raw = np.where(s12 > s26, 1.0, 0.0)          # signal at close of t
    raw[:26] = 0.0                                # no signal yet -> flat

    # position held over [t, t+1) = signal at close of t - LOOKAHEAD_SHIFT
    pos = np.zeros(n)
    pos[LOOKAHEAD_SHIFT:] = raw[:-LOOKAHEAD_SHIFT]

    # close-to-close returns of the underlying
    price_ret = np.zeros(n)
    price_ret[1:] = close[1:] / close[:-1] - 1.0

    # net strategy return: position return minus cost on position changes
    turnover = np.abs(np.diff(pos, prepend=pos[0]))
    net = pos * price_ret - COST_BPS * 1e-4 * turnover

    equity = np.cumprod(1.0 + net)
    equity /= equity[0]                           # normalise to 1.0

    # max drawdown on the normalised equity curve
    running_max = np.maximum.accumulate(equity)
    drawdown = equity / running_max - 1.0
    max_dd = float(-drawdown.min())

    # daily stats over the whole net return series (the strategy earns 0 on
    # flat days; the judge's CSV recomputation covers the same full series)
    mean_r = float(np.mean(net))
    std_r = float(np.std(net, ddof=1))
    sharpe = mean_r / std_r * np.sqrt(TRADING_DAYS) if std_r > 0 else 0.0

    return {
        "dates": dates,
        "close": close.tolist(),
        "position": pos.tolist(),
        "net_returns": net.tolist(),
        "equity": equity.tolist(),
        "metrics": {
            "final_equity": float(equity[-1]),
            "total_return": float(equity[-1] / equity[0] - 1.0),
            "n_days": n,
            "n_traded_days": int(np.count_nonzero(net)),
            "n_trades": int(np.count_nonzero(turnover)),
            "max_drawdown": max_dd,
            "sharpe": float(sharpe),
            "volatility_ann": float(std_r * np.sqrt(TRADING_DAYS)),
            "mean_daily_ret": mean_r,
            "risk_free_rate": ANNUAL_RISK_FREE,
            "cost_bps": COST_BPS,
            "lookahead_shift": LOOKAHEAD_SHIFT,
        },
    }


def main() -> int:
    here = Path(__file__).resolve().parent
    ohlcv = here / "ohlcv.csv"
    out = backtest(ohlcv)

    with (here / "returns.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "ret"])
        for d, r in zip(out["dates"], out["net_returns"]):
            w.writerow([d, f"{r:.10e}"])

    (here / "metrics.json").write_text(
        json.dumps(out["metrics"], indent=2) + "\n", encoding="utf-8")

    eq = np.array(out["equity"])
    pos = np.array(out["position"])
    dates = out["dates"]
    x = np.arange(len(eq))
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 7), sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1]})
    ax1.plot(x, eq, color="#0072B2", lw=1.4,
             label=f"equity (final {eq[-1]:.3f})")
    ax1.axhline(1.0, color="#555555", lw=0.8, ls="--")
    ax1.set_ylabel("equity (normalised)")
    ax1.set_title(
        "12/26 momentum backtest on pinned OHLCV fixture — "
        f"Sharpe {out['metrics']['sharpe']:.2f}, "
        f"max DD {out['metrics']['max_drawdown']:.1%}")
    ax1.legend(loc="upper left")
    ax1.grid(alpha=0.3)
    ax2.fill_between(x, pos, color="#009E73", alpha=0.6, step="mid")
    ax2.set_ylabel("position")
    ax2.set_xlabel(f"trading day (0 = {dates[0]}, {len(x)-1} = {dates[-1]})")
    ax2.set_ylim(-0.05, 1.05)
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(here / "equity.png", dpi=200)
    print(json.dumps(out["metrics"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
