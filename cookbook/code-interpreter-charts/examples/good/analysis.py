#!/usr/bin/env python3
"""LLM code-interpreter artifact: five fixed answers and three charts.

Answers five questions about two pinned public CSVs (Mauna Loa monthly CO2,
NOAA GML; annual CO2 emissions by country, Our World in Data) and renders
three PNG charts.  Definitions are in ../SPEC.md.

Run:  python3 analysis.py --data-dir data --out-dir out
Writes out/answers.json, out/charts.json and three PNGs.  Headless: set
MPLBACKEND=Agg (the script also forces it) so no display is needed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless: the judge runs with no display
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

# --- fixed analysis window (SPEC.md) -----------------------------------
ML_YEAR_MIN = 1990
ML_YEAR_MAX = 2025
GROWTH_MIN = 1991
EMISSIONS_YEAR = 2024
TOP_N = 10
GIGATONNE = 1e9  # tonnes per gigatonne

# Chart sizes are declared in charts.json and checked by the judge.
CHART_SIZES = {
    "c1_mauna_loa_trend.png": (1280, 800),
    "c2_seasonal_cycle.png": (1280, 800),
    "c3_top_emitters_2024.png": (1280, 900),
}
DPI = 100


def load_mauna_loa(data_dir: Path) -> pd.DataFrame:
    """Mauna Loa monthly means; the file has a 40-line '#' comment header."""
    df = pd.read_csv(data_dir / "co2_mm_mlo.csv", comment="#")
    df.columns = [c.strip() for c in df.columns]
    window = df[(df["year"] >= ML_YEAR_MIN) & (df["year"] <= ML_YEAR_MAX)]
    return window.sort_values(["year", "month"]).reset_index(drop=True)


def load_emissions(data_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(data_dir / "annual-co2-emissions-per-country.csv")
    # ISO-3166 alpha-3 codes only: excludes OWID_* aggregates and blanks.
    iso = df["Code"].astype("string").str.fullmatch(r"[A-Z]{3}").fillna(False)
    return df[iso & (df["Year"] == EMISSIONS_YEAR)].reset_index(drop=True)


def ols_slope(x, y) -> float:
    """Closed-form ordinary least squares slope of y on x."""
    xbar, ybar = x.mean(), y.mean()
    return float(((x - xbar) * (y - ybar)).sum() / ((x - xbar) ** 2).sum())


def analyse(ml: pd.DataFrame, em: pd.DataFrame) -> tuple[dict, dict]:
    """Return (answers, charts) per SPEC.md."""
    trend = ols_slope(ml["decimal date"], ml["average"])

    monthly = ml.groupby("month")["average"].mean()
    amplitude = float(monthly.max() - monthly.min())

    yearly = ml.groupby("year")["average"].mean()
    # diff() gives year_mean(y) - year_mean(y-1); the first row (1990) has
    # no predecessor, so the surviving index starts at GROWTH_MIN.
    growth = yearly.diff().dropna()
    growth = growth[growth.index >= GROWTH_MIN]
    mean_growth = float(growth.mean())

    total_t = float(em["Annual CO₂ emissions"].sum())
    total_gt = total_t / GIGATONNE
    ranked = em.sort_values(
        ["Annual CO₂ emissions", "Code"], ascending=[False, True])
    top = ranked.head(TOP_N)
    top_share = float(ranked.iloc[0]["Annual CO₂ emissions"] / total_t)

    answers = {
        "mauna_loa_trend_ppm_per_year": trend,
        "mauna_loa_seasonal_amplitude_ppm": amplitude,
        "mauna_loa_mean_annual_growth_ppm": mean_growth,
        "owid_world_emissions_2024_gt": total_gt,
        "owid_top_emitter_2024_share": top_share,
    }

    # Trend line endpoints, from the same fit, evaluated at the window ends.
    xbar, ybar = ml["decimal date"].mean(), ml["average"].mean()
    first_x, last_x = float(ml["decimal date"].iloc[0]), float(
        ml["decimal date"].iloc[-1])
    trend_line = [[first_x, float(ybar + trend * (first_x - xbar))],
                  [last_x, float(ybar + trend * (last_x - xbar))]]

    charts = {
        "C1": {
            "mauna_loa_trend_ppm_per_year": trend,
            "months": [[float(d), float(a)] for d, a in
                       zip(ml["decimal date"], ml["average"])],
            "trend_line": trend_line,
        },
        "C2": {
            "mauna_loa_seasonal_amplitude_ppm": amplitude,
            "months": [[int(m), float(v)] for m, v in monthly.items()],
            "amplitude_ppm": amplitude,
        },
        "C3": {
            "owid_world_emissions_2024_gt": total_gt,
            "owid_top_emitter_2024_share": top_share,
            "entities": [str(e) for e in top["Entity"]],
            "emissions_gt": [[str(e), float(v) / GIGATONNE] for e, v in
                             zip(top["Entity"], top["Annual CO₂ emissions"])],
            "total_gt": total_gt,
        },
    }
    return answers, charts


def draw_charts(ml: pd.DataFrame, charts: dict, out_dir: Path) -> dict:
    """Render the three PNGs; return the file/size metadata for charts.json."""
    sizes = {}
    for name, (w, h) in CHART_SIZES.items():
        sizes[name] = {"width_px": w, "height_px": h}

    # C1: the monthly series with the OLS trend line.
    fig, ax = plt.subplots(figsize=(12.8, 8.0), dpi=DPI)
    ax.plot(ml["decimal date"], ml["average"], color="#0072B2", lw=1.0,
            label="Mauna Loa monthly mean")
    line = charts["C1"]["trend_line"]
    ax.plot([line[0][0], line[1][0]], [line[0][1], line[1][1]],
            color="#D55E00", lw=2.0, ls="--",
            label=f"OLS trend {charts['C1']['mauna_loa_trend_ppm_per_year']:.3f}"
                  " ppm/yr")
    ax.set_xlabel("Year (decimal date)")
    ax.set_ylabel("CO$_2$ (ppm)")
    ax.set_title("Mauna Loa atmospheric CO$_2$, 1990-2025")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "c1_mauna_loa_trend.png")
    plt.close(fig)

    # C2: mean seasonal cycle.
    months = charts["C2"]["months"]
    fig, ax = plt.subplots(figsize=(12.8, 8.0), dpi=DPI)
    ax.bar([m for m, _ in months], [v for _, v in months], color="#009E73")
    ax.set_xlabel("Month")
    ax.set_ylabel("Mean CO$_2$ (ppm), 1990-2025")
    ax.set_title(f"Mean seasonal cycle (amplitude "
                 f"{charts['C2']['amplitude_ppm']:.2f} ppm)")
    ax.set_xticks(range(1, 13))
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_dir / "c2_seasonal_cycle.png")
    plt.close(fig)

    # C3: 2024 top-10 ISO emitters, horizontal bars.
    emis = charts["C3"]["emissions_gt"]
    names = [n for n, _ in emis][::-1]
    values = [v for _, v in emis][::-1]
    fig, ax = plt.subplots(figsize=(12.8, 9.0), dpi=DPI)
    ax.barh(names, values, color="#CC79A7")
    ax.set_xlabel("Annual CO$_2$ emissions 2024 (GtCO$_2$)")
    ax.set_title(f"Top 10 emitters, 2024 (ISO-3166 countries; "
                 f"total {charts['C3']['total_gt']:.2f} Gt)")
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(out_dir / "c3_top_emitters_2024.png")
    plt.close(fig)

    return sizes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    args = ap.parse_args()
    data_dir, out_dir = Path(args.data_dir), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ml = load_mauna_loa(data_dir)
    em = load_emissions(data_dir)
    answers, charts = analyse(ml, em)
    sizes = draw_charts(ml, charts, out_dir)
    for chart, meta in sizes.items():
        charts_meta = charts.setdefault(chart.split("_")[0].upper(), {})
        charts_meta.update(meta)
        charts_meta["file"] = chart

    (out_dir / "answers.json").write_text(
        json.dumps(answers, indent=2, sort_keys=True) + "\n")
    (out_dir / "charts.json").write_text(
        json.dumps(charts, indent=2, sort_keys=True) + "\n")
    print(f"analysis: wrote {len(answers)} answers and "
          f"{len(sizes)} charts to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
