#!/usr/bin/env python3
"""Independent oracle for the code-interpreter-charts judge.

Recomputes every answer and every plotted series from the raw pinned CSVs
using only the standard library (`csv`, `statistics`, `math`) -- no pandas,
no numpy -- so the judge compares the artifact against a second,
independently written implementation rather than against the artifact
itself.  Definitions are in ../SPEC.md.
"""

from __future__ import annotations

import csv
import re
import statistics

# Mauna Loa window: 1990..2025 inclusive, by the `year` column.
ML_YEAR_MIN = 1990
ML_YEAR_MAX = 2025
# Growth years: 1991..2025.
GROWTH_MIN = 1991

ISO3 = re.compile(r"^[A-Z]{3}$")

ML_FILE = "co2_mm_mlo.csv"
OWID_FILE = "annual-co2-emissions-per-country.csv"


class OracleError(RuntimeError):
    """The oracle could not compute an answer: fail closed."""


def _read_ml(data_dir):
    """Return the Mauna Loa window rows as dicts with float fields."""
    rows = []
    with open(data_dir / ML_FILE, newline="") as fh:
        lines = [ln for ln in fh if not ln.startswith("#") and ln.strip()]
    reader = csv.DictReader(lines)
    for rec in reader:
        try:
            year = int(rec["year"])
            rows.append({
                "year": year,
                "month": int(rec["month"]),
                "date": float(rec["decimal date"]),
                "average": float(rec["average"]),
            })
        except (KeyError, ValueError) as exc:
            raise OracleError(f"{ML_FILE}: bad row {rec!r}: {exc}") from exc
    if not rows:
        raise OracleError(f"{ML_FILE}: no data rows")
    window = [r for r in rows if ML_YEAR_MIN <= r["year"] <= ML_YEAR_MAX]
    if not window:
        raise OracleError(f"{ML_FILE}: no rows in {ML_YEAR_MIN}..{ML_YEAR_MAX}")
    return window


def _read_owid(data_dir):
    rows = []
    with open(data_dir / OWID_FILE, newline="") as fh:
        reader = csv.DictReader(fh)
        for rec in reader:
            try:
                rows.append({
                    "entity": rec["Entity"],
                    "code": rec["Code"] or "",
                    "year": int(rec["Year"]),
                    "emissions": float(rec["Annual CO₂ emissions"]),
                })
            except (KeyError, ValueError) as exc:
                raise OracleError(f"{OWID_FILE}: bad row {rec!r}: {exc}") from exc
    if not rows:
        raise OracleError(f"{OWID_FILE}: no data rows")
    return rows


def _ols_slope(pairs):
    """Closed-form OLS slope of y on x: sum((x-xbar)(y-ybar)) / sum((x-xbar)^2)."""
    if len(pairs) < 2:
        raise OracleError("OLS needs at least 2 points")
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    xbar = statistics.fmean(xs)
    ybar = statistics.fmean(ys)
    sxx = sum((x - xbar) ** 2 for x in xs)
    if sxx == 0:
        raise OracleError("OLS: zero x variance")
    return sum((x - xbar) * (y - ybar) for x, y in pairs) / sxx


def _ols_line(pairs, x):
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    xbar = statistics.fmean(xs)
    ybar = statistics.fmean(ys)
    slope = _ols_slope(pairs)
    return ybar + slope * (x - xbar)


def mauna_loa(window):
    """Every Mauna Loa answer and plotted series."""
    pairs = [(r["date"], r["average"]) for r in window]
    trend = _ols_slope(pairs)

    by_month = {}
    for r in window:
        by_month.setdefault(r["month"], []).append(r["average"])
    if sorted(by_month) != list(range(1, 13)):
        raise OracleError(f"{ML_FILE}: window is missing calendar months "
                          f"{sorted(set(range(1, 13)) - set(by_month))}")
    monthly_means = {m: statistics.fmean(by_month[m]) for m in range(1, 13)}
    amplitude = (max(monthly_means.values()) - min(monthly_means.values()))

    by_year = {}
    for r in window:
        by_year.setdefault(r["year"], []).append(r["average"])
    year_mean = {y: statistics.fmean(v) for y, v in by_year.items()}
    growth = [year_mean[y] - year_mean[y - 1]
              for y in range(GROWTH_MIN, ML_YEAR_MAX + 1)]
    if not growth:
        raise OracleError(f"{ML_FILE}: no growth years in the window")

    dates = [r["date"] for r in window]
    return {
        "mauna_loa_trend_ppm_per_year": trend,
        "mauna_loa_seasonal_amplitude_ppm": amplitude,
        "mauna_loa_mean_annual_growth_ppm": statistics.fmean(growth),
        "months": [[r["date"], r["average"]] for r in window],
        "monthly_means": [[m, monthly_means[m]] for m in range(1, 13)],
        "trend_line": [[dates[0], _ols_line(pairs, dates[0])],
                       [dates[-1], _ols_line(pairs, dates[-1])]],
        "amplitude_ppm": amplitude,
    }


def owid_2024(rows, top_n=10):
    """Every 2024 emissions answer and plotted series (ISO-3166 rows only)."""
    iso_rows = [r for r in rows if r["year"] == 2024 and ISO3.match(r["code"])]
    if not iso_rows:
        raise OracleError(f"{OWID_FILE}: no 2024 rows with an ISO-3166 code")
    total_t = sum(r["emissions"] for r in iso_rows)
    if total_t <= 0:
        raise OracleError(f"{OWID_FILE}: non-positive 2024 ISO total {total_t}")
    total_gt = total_t / 1e9
    ranked = sorted(iso_rows, key=lambda r: (-r["emissions"], r["code"]))
    if len(ranked) < top_n:
        raise OracleError(f"{OWID_FILE}: only {len(ranked)} ISO rows in 2024")
    top = ranked[:top_n]
    return {
        "owid_world_emissions_2024_gt": total_gt,
        "owid_top_emitter_2024_share": ranked[0]["emissions"] / total_t,
        "entities": [r["entity"] for r in top],
        "emissions_gt": [[r["entity"], r["emissions"] / 1e9] for r in top],
        "total_gt": total_gt,
    }


def compute(data_dir):
    """Every oracle number for the pinned dataset, keyed as in the SPEC."""
    ml = mauna_loa(_read_ml(data_dir))
    ow = owid_2024(_read_owid(data_dir))
    return {
        "answers": {
            "mauna_loa_trend_ppm_per_year": ml["mauna_loa_trend_ppm_per_year"],
            "mauna_loa_seasonal_amplitude_ppm":
                ml["mauna_loa_seasonal_amplitude_ppm"],
            "mauna_loa_mean_annual_growth_ppm":
                ml["mauna_loa_mean_annual_growth_ppm"],
            "owid_world_emissions_2024_gt": ow["owid_world_emissions_2024_gt"],
            "owid_top_emitter_2024_share": ow["owid_top_emitter_2024_share"],
        },
        "mauna_loa": ml,
        "owid": ow,
    }


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    if len(sys.argv) != 2:
        print("usage: oracle.py <data-dir>", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(compute(Path(sys.argv[1])), indent=2, sort_keys=True))
