#!/usr/bin/env python3
"""Generate known-bad artifacts: single-edit mutants of the good example.

Each mutant changes exactly one thing about examples/good/controller.json and
is expected to fail at least one judge gate — mc-marginal by the
Monte-Carlo gate alone, the rest by a deterministic gate. Writes
examples/bad/*.json.
Usage: mutants.py [good-json] [outdir]
"""
import copy
import json
import os
import sys

MUTANTS = {
    # one negative state weight -> lqr has no stabilising solution
    "sign-flip": lambda a: a["Q"].__setitem__(2, -50.0),
    # 1000x state weights -> high-gain design that demands far beyond the
    # actuator limits (saturation gate)
    "too-aggressive": lambda a: a.update(
        {"Q": [v * 1000.0 for v in a["Q"]]}),
    # 1/100x state weights -> sluggish, misses the settling-time gate
    "too-sluggish": lambda a: a.update(
        {"Q": [v / 100.0 for v in a["Q"]]}),
    # near-zero torque penalty -> enormous torque demand (saturation gate)
    "degenerate-r-torque": lambda a: a["R"].__setitem__(1, 1e-6),
    # near-zero force penalty -> enormous force demand (saturation gate)
    "degenerate-r-force": lambda a: a["R"].__setitem__(0, 1e-6),
    # NaN weight -> artifact validation rejects it
    "nan-weight": lambda a: a["Q"].__setitem__(2, float("nan")),
    # wrong type string -> artifact validation rejects it
    "wrong-type": lambda a: a.update({"type": "pid"}),
    # swapped Q and R shapes -> artifact validation rejects it
    "wrong-shape": lambda a: a.update({"Q": [1.0, 0.1, 50.0]}),
    # 0.8x state weights -> passes every deterministic gate but misses
    # displacement settling on perturbed plants (Monte-Carlo gate alone)
    "mc-marginal": lambda a: a.update(
        {"Q": [v * 0.8 for v in a["Q"]]}),
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
    for name, mutate in MUTANTS.items():
        art = copy.deepcopy(base)
        mutate(art)
        path = os.path.join(outdir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(art, fh, indent=2)
            fh.write("\n")
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
