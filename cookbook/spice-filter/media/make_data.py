#!/usr/bin/env python3
"""Media data extraction for the spice-filter demo.

Writes media/data/*.json by driving the judge engine directly (imported,
not duplicated): the good artifact's ideal and 1 MHz-GBW macro-model AC
sweeps, the closed-form reference curve, and the replay grade verdicts
copied from the workdir. Every plotted number comes from a judge output
file -- nothing is invented here.

Usage: make_data.py <demodir> <workdir>
  <demodir>  path to cookbook/spice-filter (media/ lives inside)
  <workdir>  scratch dir with the replay sequence grade JSONs
             (good.json, r-decade-up.json, off-series.json,
              unrecognised-topology.json) and mutants/
"""
import json
import math
import shutil
import sys
from pathlib import Path

demodir = Path(sys.argv[1])
work = Path(sys.argv[2])
outdir = demodir / "media" / "data"
outdir.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(demodir / "judge"))
import spice_filter_judge as J  # noqa: E402

good_path = demodir / "examples" / "good" / "lpf4sk.cir"
source = good_path.read_text()
lines = source.splitlines()
elements, _, _ = J.parse_netlist(source)
stages = J.extract_stages(elements)
assert stages is not None, "good example must extract as Sallen-Key"

# --- nominal (ideal op-amp) sweep, the same one grade.sh grades -------
with __import__("tempfile").TemporaryDirectory() as td:
    sweep = J.run_ngspice(
        J.build_deck(lines, "nominal.raw"), Path(td), "nominal.raw")[0]
fs = sorted(sweep)
nominal = {
    "freq": fs,
    "gain_db": [round(J.db(sweep[f]), 4) for f in fs],
    "analytic_db": [round(J.analytic_db(stages, f), 4) for f in fs],
    "f_grid": f"{J.FMIN:g}..{J.FMAX:g} {J.PTS_PER_DECADE}/dec",
    "points": len(fs),
}

# --- 1 MHz-GBW macro-model sweep (the judge's second oracle case) -------
with __import__("tempfile").TemporaryDirectory() as td:
    gbw = J.run_gbw_macromodel(lines, stages, elements)
# re-key gbw sweep onto the same grid (same deck grid, identical points)
gfs = sorted(gbw)
assert gfs == fs, "macro-model grid differs from nominal grid"
macromodel = {
    "freq": fs,
    "gain_db": [round(J.db(gbw[f]), 4) for f in fs],
    "gbw_hz": J.GBW_HZ,
    "max_dev_vs_analytic_db": round(
        max(abs(J.db(gbw[f]) - J.analytic_db(stages, f)) for f in fs), 5),
}

(outdir / "sweep_good.json").write_text(json.dumps(
    {"nominal": nominal, "gbw_macromodel": macromodel,
     "mask": {"ripple_max_db": J.RIPPLE_MAX, "stop_max_db": J.STOP_MAX,
              "passband_edge_hz": 1000.0, "stopband_edge_hz": 10_000.0},
     "stages": [{"Ra": s["Ra"], "Rb": s["Rb"], "Cf": s["Cf"],
                 "Cg": s["Cg"]} for s in stages]},
    indent=1))

# --- replay verdicts: copy the grade JSONs the judge produced ----------
replay_order = ["r-decade-up", "off-series", "unrecognised-topology", "good"]
replay = []
for name in replay_order:
    v = json.loads((work / f"{name}.json").read_text())
    v["label"] = name
    replay.append(v)
(outdir / "replay.json").write_text(json.dumps(replay, indent=1))

# --- selftest replay: per-mutant kill result (freshly graded) ----------
kills = []
for m in sorted((work / "mutants").glob("*.cir")):
    verdict = J.grade(m, seed=20261014)
    kills.append({
        "mutant": m.stem,
        "passed": verdict["passed"],
        "failed_gate": verdict.get("failed_gate", "-"),
    })
kill_rate = sum(1 for k in kills if not k["passed"]) / len(kills)
(outdir / "selftest.json").write_text(json.dumps(
    {"kills": kills, "kill_rate": kill_rate, "mutants": len(kills)},
    indent=1))
print(f"make_data: wrote sweep_good.json, replay.json, selftest.json "
      f"(kill rate {kill_rate:.0%}) to {outdir}")
