#!/usr/bin/env python3
"""Generate known-bad single-edit mutants of the good analysis artifact.

Each mutant is exactly one textual edit (one line replaced, or one line
deleted) of examples/good/analysis.py, so a mutant that survives points at a
gate that is not pulling its weight.  Used by judge/selftest.sh to prove the
judge fails bad inputs.  Output: <outdir>/<name>/analysis.py, plus one
summary line per mutant naming the edit and the gate it should trip.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# (name, old line, new line, gate it should trip, what it models)
EDITS = [
    ("off-by-one-filter",
     "ML_YEAR_MIN = 1990",
     "ML_YEAR_MIN = 1991",
     "G2/G4",
     "the analysis window starts one year late, so the trend, amplitude "
     "and growth all shift"),
    ("wrong-groupby-key",
     '    monthly = ml.groupby("month")["average"].mean()',
     '    monthly = ml.groupby("year")["average"].mean()',
     "G4",
     "the seasonal cycle groups by year instead of month: 36 bars, not 12"),
    ("mean-vs-median",
     "    mean_growth = float(growth.mean())",
     "    mean_growth = float(growth.median())",
     "G2",
     "mean and median swapped: a plausible number that is the wrong one"),
    ("unit-error",
     "GIGATONNE = 1e9  # tonnes per gigatonne",
     "GIGATONNE = 1e12  # tonnes per gigatonne",
     "G2/G4",
     "tonnes-to-gigatonnes off by 1e3: the total is 1000x too small"),
    ("blank-chart",
     '    ax.bar([m for m, _ in months], [v for _, v in months], '
     'color="#009E73")',
     '    ax.axis("off")',
     "G3",
     "C2 is drawn blank (axis off): a valid PNG of the right size, no data"),
    ("trend-line-disagrees",
     "                  [last_x, float(ybar + trend * (last_x - xbar))]]",
     "                  [last_x, float(ybar)]]",
     "G4",
     "the trend line drawn on C1 is flat, so the chart disagrees with the "
     "answer it plots"),
    ("world-row-in-total",
     '    iso = df["Code"].astype("string").str.fullmatch(r"[A-Z]{3}")'
     ".fillna(False)",
     '    iso = df["Code"].astype("string").str.fullmatch('
     'r"[A-Z]{3}|OWID_WRL").fillna(False)',
     "G2/G4",
     "the OWID 'World' aggregate is counted alongside countries, "
     "double-counting every country"),
]

# (name, exact line to delete, gate, what it models)
DELETIONS = [
    ("missing-answer",
     '        "owid_top_emitter_2024_share": top_share,',
     "G2",
     "one of the five answers is never written"),
]


def mutate(lines, name, outdir, note):
    (outdir / name).mkdir(parents=True, exist_ok=True)
    (outdir / name / "analysis.py").write_text("\n".join(lines) + "\n")
    print(f"mutants: {name}/analysis.py  {note}")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mutants.py <good-analysis.py> <outdir>", file=sys.stderr)
        return 2
    good = Path(sys.argv[1])
    lines = good.read_text().splitlines()
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    made = 0
    for name, old, new, gate, why in EDITS:
        hits = [i for i, ln in enumerate(lines) if ln == old]
        if len(hits) != 1:
            print(f"mutants: anchor {old!r} found {len(hits)}x, need 1",
                  file=sys.stderr)
            return 1
        mutated = list(lines)
        mutated[hits[0]] = new
        mutate(mutated, name, outdir, f"[{gate}] {why}")
        made += 1

    for name, old, gate, why in DELETIONS:
        hits = [i for i, ln in enumerate(lines) if ln == old]
        if len(hits) != 1:
            print(f"mutants: anchor {old!r} found {len(hits)}x, need 1",
                  file=sys.stderr)
            return 1
        mutated = lines[:hits[0]] + lines[hits[0] + 1:]
        mutate(mutated, name, outdir, f"[{gate}] {why}")
        made += 1

    # Each mutant is a standalone artifact directory: it needs the pinned
    # data to run, exactly like examples/good/.
    data = good.parent / "data"
    for mutant_dir in sorted(p for p in outdir.iterdir() if p.is_dir()):
        shutil.copytree(data, mutant_dir / "data", dirs_exist_ok=True)

    print(f"mutants: wrote {made} mutants to {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
