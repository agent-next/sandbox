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

# ============================================================================
# Video clip data: every byte below also comes from a real ngspice/judge run
# in this sandbox (same process as the sweeps above).
# ============================================================================
import random  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402


def transient_run(freq_hz: float, ncycles: int = 30) -> dict:
    """Real ngspice .tran of the good circuit, V1 swapped to SIN(0 1 f).

    Same element cards the judge graded; only the source and the analysis
    change (the artifact's own .control AC block is replaced by a transient
    one). Output parsed from ngspice's own wrdata table.
    """
    deck_lines, in_control = [], False
    for ln in lines:
        low = ln.strip().lower()
        if low.startswith(".control"):
            in_control = True
            continue
        if low.startswith(".endc"):
            in_control = False
            continue
        if in_control:
            continue
        if ln.startswith("V1 "):
            ln = f"V1 in 0 SIN(0 1 {freq_hz:g})"
        if ln.strip() == ".end":
            continue
        deck_lines.append(ln)
    period = 1.0 / freq_hz
    tstop = ncycles * period
    tstep = period / 500.0
    deck = ("\n".join(deck_lines) + "\n.control\n"
            f"tran {tstep:g} {tstop:g}\n"
            "wrdata tran.dat v(in) v(out)\nquit\n.endc\n.end\n")
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        (wd / "deck.cir").write_text(deck)
        proc = subprocess.run(["ngspice", "-b", "deck.cir"], cwd=wd,
                              capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not (wd / "tran.dat").exists():
            raise SystemExit("make_data: ngspice tran failed at "
                             f"{freq_hz:g} Hz: {(proc.stdout or '')[-300:]}")
        rows = [ln.split() for ln in
                (wd / "tran.dat").read_text().splitlines() if ln.split()]
    t = [float(r[0]) for r in rows]
    vin = [float(r[1]) for r in rows]
    vout = [float(r[3]) for r in rows]
    stride = max(1, len(t) // 1200)  # cap file size
    return {"freq_hz": freq_hz, "period_s": period,
            "t": t[::stride], "vin": vin[::stride], "vout": vout[::stride]}


# passband edge / corner / deep stopband: what the filter does to a sine
(outdir / "transient.json").write_text(json.dumps({
    "source": "examples/good/lpf4sk.cir, V1 -> SIN(0 1 f), ngspice tran",
    "segments": [transient_run(f) for f in (300.0, 1400.0, 16000.0)],
}))


# --- Monte-Carlo curves: re-run the judge's own seeded sequence ------------
# rng = random.Random(seed) + perturbed_source is exactly what the
# montecarlo gate does; we keep each run's decimated sweep for the clip.
mc_seed = 20261014
rng = random.Random(mc_seed)
mc_runs = []
stride = max(1, len(fs) // 40)
f_dec = fs[::stride]
with tempfile.TemporaryDirectory() as td:
    wd = Path(td)
    for i in range(J.MC_RUNS):
        plines = J.perturbed_source(lines, elements, rng)
        sw, _ = J.run_ngspice(J.build_deck(plines, f"mc{i}.raw"),
                              wd, f"mc{i}.raw")
        _, rip, stp = J.mask_metrics(sw)
        mc_runs.append({
            "run": i,
            "ok": bool(rip <= J.MC_RIPPLE_MAX and stp <= J.MC_STOP_MAX),
            "ripple_db": round(rip, 3),
            "stopband_db": round(stp, 3),
            "gain_db": [round(J.db(sw[f]), 3) for f in f_dec],
        })
(outdir / "mc_curves.json").write_text(json.dumps({
    "seed": mc_seed, "runs": J.MC_RUNS,
    "tolerances": f"R +-{J.MC_R_TOL:.0%} / C +-{J.MC_C_TOL:.0%} uniform",
    "relaxed_mask": {"ripple_max_db": J.MC_RIPPLE_MAX,
                     "stop_max_db": J.MC_STOP_MAX},
    "freq": f_dec,
    "results": mc_runs,
    "pass_fraction": round(sum(r["ok"] for r in mc_runs) / len(mc_runs), 3),
}, indent=0))


# --- captured terminal output of this run (for the replay clip) ------------
if (work / "runlog.txt").exists():
    (outdir / "runlog.txt").write_text((work / "runlog.txt").read_text())


# --- video_props.json: every HUD number, traced to a judge file ------------
good_v = json.loads((work / "good.json").read_text())
g = good_v["gates"]
(outdir / "video_props.json").write_text(json.dumps({
    "verdict_pass": good_v["passed"],
    "seed": good_v["seed"],
    "points": g["parse"]["points"],
    "f_grid": g["parse"]["f_grid"],
    "ripple_db": g["mask"]["ripple_db"],
    "ripple_rule": g["mask"]["rule"],
    "stopband_max_db": g["mask"]["stopband_max_db"],
    "stopband_rule": g["mask"]["rule2"],
    "analytic_max_dev_db": g["analytic"]["max_deviation_db"],
    "gbw_dev_db": g["analytic"]["gbw_deviation_db"],
    "gbw_rule": g["analytic"]["rule2"],
    "mc_runs": g["montecarlo"]["runs"],
    "mc_pass_fraction": g["montecarlo"]["pass_fraction"],
    "mc_worst_ripple_db": g["montecarlo"]["worst_ripple_db"],
    "mc_worst_stopband_db": g["montecarlo"]["worst_stopband_db"],
    "kill_rate": kill_rate,
    "mutants": len(kills),
    "replay": [{"label": v["label"],
                "passed": v["passed"],
                "failed_gate": v.get("failed_gate", "-")}
               for v in replay],
    "ngspice": "ngspice-39 (39.3+ds-1)",
}, indent=1))
print("make_data: + transient.json, mc_curves.json "
      f"({len(mc_runs)} seeded runs), runlog.txt, video_props.json")
