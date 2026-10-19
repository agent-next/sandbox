#!/usr/bin/env python3
"""Blind, independent reference implementation for the backtest-equity judge.

This is deliberately written as a scalar loop over the CSV, with the signal,
the position lag, the cost accounting and every metric computed in the
plainest possible way: it must not share a code path (or a helper) with the
agent's vectorized engine, so that an agreement between the two means the
artifact is right rather than that both made the same off-by-one mistake.

The reference never imports numpy and never executes the artifact. It reads
the pinned fixture and the artifact's own files only.

Conventions the SPEC fixes (the same ones the good example uses):

* signal(t)     = +1 if sma12(t) > sma26(t) else 0, both SMAs causal and
                  computed on the CLOSE series; 0 while either SMA is
                  undefined (t < 25).
* position held over [t, t+1) = signal(t - lookahead_shift).
* gross return on day t = position(t) * (close(t)/close(t-1) - 1).
* one-way proportional cost COST_BPS * 1e-4 charged on |position change|
  between the position held over [t-1, t) and the one held over [t, t+1).
* equity is the cumulative product of (1 + net return), normalised to 1.0
  on the first day.
* Sharpe = mean(net)/std(net, ddof=1) * sqrt(252), risk-free rate 0.
* max drawdown = 1 - min(equity/running_max), on the normalised curve.
"""

from __future__ import annotations

import math

# The single parameter set the demo fixes.  Not configurable: an artifact
# that declares anything else is failed by gate G6, not silently accepted.
FAST = 12
SLOW = 26
COST_BPS = 10.0
TRADING_DAYS = 252
ANNUAL_RISK_FREE = 0.0


def sma_at(closes, i, n):
    """Causal simple moving average at index i, or None while undefined."""
    if i - n + 1 < 0:
        return None
    total = 0.0
    for k in range(i - n + 1, i + 1):
        total += closes[k]
    return total / n


def reference_backtest(dates, closes, lookahead_shift):
    """Return the full reference series/methods for `lookahead_shift` bars
    of signal lag.  Loop-based, no numpy, independent of the artifact."""
    n = len(closes)
    position = [0.0] * n
    for t in range(n):
        src = t - lookahead_shift
        if src < 0:
            position[t] = 0.0
            continue
        fast = sma_at(closes, src, FAST)
        slow = sma_at(closes, src, SLOW)
        if fast is None or slow is None:
            position[t] = 0.0
        elif fast > slow:
            position[t] = 1.0
        else:
            position[t] = 0.0

    net = [0.0] * n
    turnover = [0.0] * n
    for t in range(1, n):
        gross = position[t] * (closes[t] / closes[t - 1] - 1.0)
        change = abs(position[t] - position[t - 1])
        turnover[t] = change
        net[t] = gross - COST_BPS * 1e-4 * change

    equity = [1.0]
    for t in range(1, n):
        equity.append(equity[-1] * (1.0 + net[t]))

    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = 1.0 - e / peak
        if dd > max_dd:
            max_dd = dd

    mean_r = sum(net) / n
    var_r = sum((r - mean_r) ** 2 for r in net) / (n - 1)
    std_r = math.sqrt(var_r)
    sharpe = mean_r / std_r * math.sqrt(TRADING_DAYS) if std_r > 0 else 0.0

    return {
        "dates": list(dates),
        "closes": list(closes),
        "position": position,
        "net": net,
        "turnover": turnover,
        "equity": equity,
        "final_equity": equity[-1],
        "total_return": equity[-1] - 1.0,
        "n_days": n,
        "n_trades": int(sum(1 for x in turnover if x > 0.0)),
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "volatility_ann": std_r * math.sqrt(TRADING_DAYS),
        "mean_daily_ret": mean_r,
        "risk_free_rate": ANNUAL_RISK_FREE,
        "cost_bps": COST_BPS,
    }


def reference_metrics_from_prices(closes, lookahead_shift):
    """Reference metrics for a close price vector (dates not needed)."""
    n = len(closes)
    days = [str(i) for i in range(n)]
    r = reference_backtest(days, closes, lookahead_shift)
    return r


def reference_final_equity(closes, lookahead_shift):
    return reference_metrics_from_prices(closes, lookahead_shift)["final_equity"]
