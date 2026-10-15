#!/usr/bin/env python3
"""Media data extraction for the backtest-equity demo.

Writes media/data/*.json by driving the judge engine directly: the blind
reference's equity/position/drawdown series, the known-good artifact's own
series, the self-test's per-mutant verdicts and kill rate, and the
agent-loop replay of a fixing agent (equity error per iteration).

Every plotted number comes from a judge output or the judge's own
reference run -- nothing is invented here.

Usage: make_data.py <demodir> <workdir>
  <demodir>  path to cookbook/backtest-equity (media/ lives inside)
  <workdir>  scratch dir the caller filled with mutant verdict JSONs
             (one file per mutant name, plus good.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

demodir = Path(sys.argv[1]).resolve()
work = Path(sys.argv[2]).resolve()

sys.path.insert(0, str(demodir / "judge"))
import judge as J  # noqa: E402
import reference as R  # noqa: E402

outdir = demodir / "media" / "data"
outdir.mkdir(parents=True, exist_ok=True)

# --- the pinned fixture and the blind reference, at shift 1 -------------
dates, closes = J.read_pinned_closes()
ref = R.reference_backtest(dates, closes, 1)
assert ref["n_days"] == len(dates), "reference must cover every fixture day"

equity = {
    "n_days": ref["n_days"],
    "dates": ref["dates"],
    "final_equity": ref["final_equity"],
    "total_return": ref["total_return"],
    "max_drawdown": ref["max_drawdown"],
    "sharpe": ref["sharpe"],
    "n_trades": ref["n_trades"],
}
# the curves are long; write them once and reference them from the figures
json.dump(equity, open(outdir / "curve.json", "w"))
json.dump({"dates": ref["dates"],
           "equity": ref["equity"],
           "position": ref["position"],
           "net": ref["net"],
           "drawdown": [1.0 - e / m for e, m in zip(
               ref["equity"],
               [max(ref["equity"][:i + 1]) for i in range(ref["n_days"])])]},
          open(outdir / "series.json", "w"))
json.dump({"final_equity": ref["final_equity"],
           "sharpe": ref["sharpe"],
           "max_drawdown": ref["max_drawdown"],
           "n_trades": ref["n_trades"],
           "total_return": ref["total_return"]},
          open(outdir / "metrics.json", "w"))
print(f"make_data: reference series ({ref['n_days']} days, "
      f"final equity {ref['final_equity']:.6f})")

# --- self-test verdicts: the caller already ran judge/selftest.sh -------
verdicts = {}
for p in sorted(work.glob("*.json")):
    verdicts[p.stem] = json.loads(p.read_text())
good = verdicts.get("good")
if good is None:
    raise SystemExit("make_data: good.json missing from the workdir")
selftest = {
    "good_verdict": good["verdict"],
    "good_metrics": good["metrics"],
    "mutants": {name: {"verdict": v["verdict"],
                       "failed": v["failed_gates"]}
                for name, v in verdicts.items() if name != "good"},
}
json.dump(selftest, open(outdir / "selftest.json", "w"), indent=1)
n_killed = sum(1 for m in selftest["mutants"].values() if m["verdict"] != "PASS")
print(f"make_data: selftest {n_killed}/{len(selftest['mutants'])} mutants killed")

# --- agent-loop replay: error per iteration of a scripted fixing agent --
# A real agent fixes its engine iteratively; this replays the graded
# verdicts of known-bad artifacts in the order the agent would meet them,
# each one step closer to the good one, then the good one.  The plotted
# "error" per attempt is the judge's own failing measurement for that
# attempt -- the deviation from what that same measurement should be --
# so a falling curve means each fix moves the reported number back onto
# the judge's oracle.
GATE_ENUM = {
    "G2_final_equity_oracle": ("final_equity", "final_equity"),
    "G3_sharpe_consistency": ("sharpe", "sharpe"),
    "G4_max_drawdown": ("max_drawdown", "max_drawdown"),
}
replay = []
for name in ("lookahead-signal", "lookahead-shift", "sharpe-tamper",
             "mdd-tamper", "returns-drift", "fixture-drift", "cost-tamper",
             "tiny-figure", "short-history", "good"):
    v = verdicts.get(name)
    if v is None:
        continue
    m = v["metrics"]
    ref = m.get("reference", {})
    err = None
    for gate in v["failed_gates"]:
        if gate in GATE_ENUM:
            art_key, ref_key = GATE_ENUM[gate]
            if m.get(art_key) is not None and ref.get(ref_key):
                err = abs(m[art_key] - ref[ref_key]) / abs(ref[ref_key])
                break
    if err is None and v["verdict"] == "PASS" and m.get("final_equity") \
            and ref.get("final_equity"):
        err = abs(m["final_equity"] - ref["final_equity"]) / abs(
            ref["final_equity"])
    replay.append({"step": name, "verdict": v["verdict"],
                   "failed_gates": v["failed_gates"],
                   "error": err})
json.dump(replay, open(outdir / "replay.json", "w"), indent=1)
print(f"make_data: replay has {len(replay)} steps")

# --- the agent's own engine output, for the side-by-side comparison -----
art = json.loads((demodir / "examples" / "good" / "metrics.json").read_text())
json.dump({"artifact": art, "reference": {"final_equity": ref["final_equity"],
                                          "sharpe": ref["sharpe"],
                                          "max_drawdown": ref["max_drawdown"],
                                          "n_trades": ref["n_trades"]}},
          open(outdir / "comparison.json", "w"), indent=1)
print("make_data: done")
