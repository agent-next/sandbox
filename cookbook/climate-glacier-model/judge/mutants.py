#!/usr/bin/env python3
"""Generate known-bad single-edit mutants of the good glacier artifact.

Each mutant is exactly one textual edit (one line replaced, inserted or
deleted) of examples/good/model.py, so a kill can only be attributed to
that edit.  judge/selftest.sh grades every one of them and requires at
least 90 % to fail.

Output: <outdir>/<name>/model.py (a drop-in artifact directory), plus one
line per mutant naming the edit and the gate it is aimed at.
"""

import sys
from pathlib import Path

# (name, gate it should trip, old full line, new full line)
REPLACEMENTS = [
    ("tau-doubled", "shape/final_volume",
     "TAU = 10.0        # yr, length response time",
     "TAU = 20.0        # yr, length response time"),

    ("taper-dropped", "shape",
     "H = H0 - DH * X                     # ice thickness per cell",
     "H = H0 * (X * 0.0 + 1.0)            # ice thickness per cell"),

    ("anomaly-doubled", "final_volume",
     "        anomaly = amp * (year / YEARS)",
     "        anomaly = amp * 2.0 * (year / YEARS)"),

    # The JSON says one year, the CSV says another: the judge must not
    # accept the reported number without checking it against the data.
    ("crossing-year-fabricated-in-json", "crossing",
     "        year = crossing_year(range(YEARS + 1), volumes)",
     "        year = 50.0 if not args.zero_melt else crossing_year(\n"
     "            range(YEARS + 1), volumes)"),

    ("zero-melt-ignored", "zero_melt",
     "    amp = 0.0 if zero_melt else a2",
     "    amp = a2"),

    ("volume-in-cubic-metres-over-km", "final_volume",
     "    return float(W * H[X < length].sum() * DX / 1e9)",
     "    return float(W * H[X < length].sum() * DX / 1e6)"),

    ("mask-frozen-at-year-zero", "crossing",
     "    return float(W * H[X < length].sum() * DX / 1e9)",
     "    return float(W * H[X < L0].sum() * DX / 1e9)"),

    ("row-count-off-by-one", "artifact",
     "    for year in range(YEARS):",
     "    for year in range(YEARS + 1):"),

    ("figure-below-minimum-width", "figure",
     "    fig, ax = plt.subplots(figsize=(9.0, 5.5), dpi=200)",
     "    fig, ax = plt.subplots(figsize=(3.0, 2.0), dpi=200)"),

    # A perturbation far too small for any numeric tolerance to see, but
    # enough to change the bytes: only byte-identity catches this one.
    ("nondeterministic-tiny-perturbation", "determinism",
     "        volumes = [volume_km3(length) for length in lengths]",
     "        volumes = [volume_km3(length) *\n"
     "                   (1.0 + 1e-12 * __import__('random').randint(0, 10**9))\n"
     "                   for length in lengths]"),
]

# (name, gate it should trip, the full line to delete)
DELETIONS = [
    ("figure-not-written", "artifact",
     "        write_figure(os.path.join(args.out, \"retreat.png\"), series)"),
]

# (name, gate it should trip, anchor line, line inserted before the anchor)
INSERTIONS = [
    ("import-outside-allow-list", "artifact",
     "import os",
     "import subprocess  # not on the allow-list"),
    # A plausible "cache the intermediate result" write that lands in the
    # artifact's cwd instead of --out.
    ("writes-outside-out-dir", "artifact",
     "    write_csv(os.path.join(args.out, \"volumes.csv\"), series)",
     "    open(\"volumes.csv.bak\", \"w\").write(\"scratch\\n\")"),
]


def apply(good: str, name: str, old: str, new: str) -> str:
    lines = good.splitlines()
    hits = [i for i, ln in enumerate(lines) if ln == old]
    if len(hits) != 1:
        raise SystemExit(f"mutants: anchor {old!r} found {len(hits)} times "
                         f"(need exactly 1) for mutant {name}")
    lines[hits[0]] = new
    return "\n".join(lines) + "\n"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mutants.py <good-dir> <outdir>", file=sys.stderr)
        return 2
    good_dir = Path(sys.argv[1])
    good = (good_dir / "model.py").read_text()
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    made = 0
    for name, gate, old, new in REPLACEMENTS:
        text = apply(good, name, old, new)
        (outdir / name).mkdir(parents=True, exist_ok=True)
        (outdir / name / "model.py").write_text(text)
        print(f"mutants: {name}/model.py  [expect {gate}]  edit: "
              f"{old.strip()!r} -> {new.strip()!r}")
        made += 1

    for name, gate, old in DELETIONS:
        lines = good.splitlines()
        hits = [i for i, ln in enumerate(lines) if ln == old]
        if len(hits) != 1:
            raise SystemExit(f"mutants: delete anchor {old!r} found "
                             f"{len(hits)} times for {name}")
        del lines[hits[0]]
        (outdir / name).mkdir(parents=True, exist_ok=True)
        (outdir / name / "model.py").write_text("\n".join(lines) + "\n")
        print(f"mutants: {name}/model.py  [expect {gate}]  edit: "
              f"-{old.strip()!r}")
        made += 1

    for name, gate, anchor, inserted in INSERTIONS:
        lines = good.splitlines()
        hits = [i for i, ln in enumerate(lines) if ln == anchor]
        if len(hits) != 1:
            raise SystemExit(f"mutants: insert anchor {anchor!r} found "
                             f"{len(hits)} times for {name}")
        lines.insert(hits[0], inserted)
        (outdir / name).mkdir(parents=True, exist_ok=True)
        (outdir / name / "model.py").write_text("\n".join(lines) + "\n")
        print(f"mutants: {name}/model.py  [expect {gate}]  edit: "
              f"+{inserted.strip()!r}")
        made += 1

    print(f"mutants: wrote {made} mutants to {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
