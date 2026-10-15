#!/usr/bin/env python3
"""Generate known-bad artifacts: single-edit mutants of the good example.

Each mutant changes exactly one thing about examples/good/controller.json
and is expected to be rejected for a specific reason, declared here so
selftest.sh can verify the judge fails it through the right gate — a
crash or a rejection for the wrong reason does not count as a kill.

Expectations written to <outdir>/_manifest.json:
  target     gate name that must fail, or "validation" for mutants the
             artifact check rejects before any simulation runs
  isolated   when true, the target gate must be the ONLY failed gate —
             that is what proves the gate has independent killing power
             (used for the margin gates and the Monte-Carlo gate)
  desc       one-line description of the intended kill, shown in media

Writes examples/bad/*.json. Usage: mutants.py [good-json] [outdir]
"""
import copy
import json
import os
import sys

MUTANTS = {
    # negative state weight -> artifact validation rejects it before the
    # linear design is ever attempted (cannot exercise the design gate)
    "sign-flip": {
        "mutate": lambda a: a["Q"].__setitem__(2, -50.0),
        "target": "validation", "isolated": False,
        "desc": "gate 1: Q weight < 0",
    },
    # 1000x state weights -> high-gain design that demands far beyond the
    # actuator limits (saturation gate)
    "too-aggressive": {
        "mutate": lambda a: a.update(
            {"Q": [v * 1000.0 for v in a["Q"]]}),
        "target": "s1_tau_demand_max_Nm", "isolated": False,
        "desc": "gate 3: |τ| demand > 1 N·m",
    },
    # 1/100x state weights -> sluggish, misses the settling-time gates
    "too-sluggish": {
        "mutate": lambda a: a.update(
            {"Q": [v / 100.0 for v in a["Q"]]}),
        "target": "s2_x_settle_s", "isolated": False,
        "desc": "gate 3/4: misses settling",
    },
    # near-zero torque penalty -> enormous torque demand (saturation gate)
    "degenerate-r-torque": {
        "mutate": lambda a: a["R"].__setitem__(1, 1e-6),
        "target": "s1_tau_demand_max_Nm", "isolated": False,
        "desc": "gate 3: |τ| demand > 1 N·m",
    },
    # near-zero force penalty -> enormous force demand (saturation gate)
    "degenerate-r-force": {
        "mutate": lambda a: a["R"].__setitem__(0, 1e-6),
        "target": "s1_F_demand_max_N", "isolated": False,
        "desc": "gate 3: |F| demand > 10 N",
    },
    # NaN weight -> artifact validation rejects it
    "nan-weight": {
        "mutate": lambda a: a["Q"].__setitem__(2, float("nan")),
        "target": "validation", "isolated": False,
        "desc": "gate 1: NaN weight",
    },
    # wrong type string -> artifact validation rejects it
    "wrong-type": {
        "mutate": lambda a: a.update({"type": "pid"}),
        "target": "validation", "isolated": False,
        "desc": "gate 1: type ≠ \"lqr\"",
    },
    # swapped Q and R shapes -> artifact validation rejects it
    "wrong-shape": {
        "mutate": lambda a: a.update({"Q": [1.0, 0.1, 50.0]}),
        "target": "validation", "isolated": False,
        "desc": "gate 1: Q length 3",
    },
    # 30x torque penalty -> phase margin of the force loop sags below
    # 45 deg while every other gate still passes (phase-margin-gate kill)
    "pm-fail": {
        "mutate": lambda a: a["R"].__setitem__(1, a["R"][1] * 30.0),
        "target": "pm_force_deg", "isolated": True,
        "desc": "gate 5: PM < 45° only",
    },
    # 120x torque penalty -> the force loop crosses an odd multiple of
    # 180 deg with |L| > 1: negative gain margin, and nothing else fails
    # (gain-margin-gate kill)
    "gm-fail": {
        "mutate": lambda a: a["R"].__setitem__(1, a["R"][1] * 120.0),
        "target": "gm_force_db", "isolated": True,
        "desc": "gate 5: GM < 6 dB only",
    },
    # 1e5x input penalties -> feedback too weak: the design gate's pole
    # check fails (max Re(lam) >= -0.05) even though the artifact is
    # valid and lqr() succeeds — proves the design gate itself can fire
    "weak-feedback": {
        "mutate": lambda a: a.update({"R": [r * 1e5 for r in a["R"]]}),
        "target": "design_stable", "isolated": False,
        "desc": "gate 2: poles too slow",
    },
    # 0.8x state weights -> passes every deterministic gate but misses
    # displacement settling on perturbed plants (Monte-Carlo gate alone)
    "mc-marginal": {
        "mutate": lambda a: a.update(
            {"Q": [v * 0.8 for v in a["Q"]]}),
        "target": "mc_pass_fraction", "isolated": True,
        "desc": "gate 6: Monte-Carlo < 95 %",
    },
}


def main():
    good = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "examples", "good",
        "controller.json")
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(__file__), "..", "examples", "bad")
    with open(good, "r", encoding="utf-8") as fh:
        base = json.load(fh)
    os.makedirs(outdir, exist_ok=True)
    manifest = {}
    for name, spec in MUTANTS.items():
        art = copy.deepcopy(base)
        spec["mutate"](art)
        path = os.path.join(outdir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(art, fh, indent=2)
            fh.write("\n")
        manifest[name] = {"target": spec["target"],
                          "isolated": spec["isolated"],
                          "desc": spec["desc"]}
        print(path)
    with open(os.path.join(outdir, "_manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
