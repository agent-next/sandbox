#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test from the known-good params.

Every mutant is the known-good examples/good/params.json with a scripted
change, one per file; the self-test expects each to fail at least one gate.
The failure classes are the ones the brief calls out: single parameters
pushed to a physical-range edge, the uncalibrated defaults, a parameter
vector fitted to the train recordings only (overfitting the 1.5 % measurement
noise), swapped units, plus structure violations (extra key, non-finite,
string value).

Mutants that perturb parameter VALUES are derived from examples/good by
editing the numbers directly. The overfit mutant is produced by pulling the
train-overfitted fit out of engine.py's local search helper (L-BFGS-B against
the six train recordings only, starting from a coarse random search); if
scipy is unavailable it falls back to the best of a 4096-sample random rest.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import (DEFAULT_PARAMS, N_HOLDOUT, NOISE_FRAC, PARAM_NAMES,  # noqa: E402
                    PARAM_SPEC, RANGES, error_of, gen_scenario)

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = os.path.join(HERE, "..", "examples", "good", "params.json")


def _write(out_dir, name, obj, names):
    with open(os.path.join(out_dir, name + ".json"), "w") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")
    names.append(name)


def overfit_train(scen, good):
    """Fit to the six noisy train recordings only (ignores physics plausibility).

    L-BFGS-B restarts from the good params and from the train-RMS argmin of a
    512-sample random search. This is exactly the overfit-to-noise artifact
    the brief wants the judge to kill: train error near the noise floor,
    held-out error way off."""
    lo = [RANGES[n][0] for n in PARAM_NAMES]
    hi = [RANGES[n][1] for n in PARAM_NAMES]

    def errs(v):
        p = {k: float(x) for k, x in zip(PARAM_NAMES, v)}
        return error_of(p, scen["refs_train"], scen["ics_train"], scen["scale"])

    import numpy as np
    rng = np.random.default_rng(11)
    samples = rng.uniform(lo, hi, size=(512, len(PARAM_NAMES)))
    start = min(samples, key=errs)
    best_v, best_e = start, errs(start)
    try:
        from scipy.optimize import minimize
        for x0 in (np.array([good[n] for n in PARAM_NAMES]), start):
            r = minimize(errs, x0, method="L-BFGS-B", bounds=list(zip(lo, hi)),
                         options={"maxiter": 200})
            if r.fun < best_e:
                best_v, best_e = r.x, float(r.fun)
    except ImportError:
        pass
    return {k: round(float(v), 6) for k, v in zip(PARAM_NAMES, best_v)}, best_e


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(HERE, "mutants-out")
    seed = int(os.environ.get("SIM_TUNER_SEED", "7"))
    os.makedirs(out_dir, exist_ok=True)
    with open(GOOD) as fh:
        good = json.load(fh)
    scen = gen_scenario(seed)
    names = []

    for name, lo, hi, _, _ in PARAM_SPEC:
        for edge, val in (("lo", lo), ("hi", hi)):
            p = dict(good)
            p[name] = val
            _write(out_dir, f"mut_{name}_{edge}", p, names)

    # relative-band mutant: every parameter shifted to +6 % of its range off
    # the hidden truth (a plausible 'converged but biased' fit). Derived from
    # the truth, not from the good artifact, so the error cannot vanish if the
    # good artifact happens to sit exactly on truth for one parameter.
    truth = scen["truth"]
    p = {n: round(min(RANGES[n][1], max(RANGES[n][0],
              truth[n] + 0.06 * (RANGES[n][1] - RANGES[n][0]))), 6)
         for n in PARAM_NAMES}
    _write(out_dir, "mut_truth_shift6", p, names)

    _write(out_dir, "mut_defaults", dict(DEFAULT_PARAMS), names)

    p, train_e = overfit_train(scen, good)
    _write(out_dir, "mut_overfit_train", p, names)
    print(f"# overfit_train train err {train_e:.6f}", file=sys.stderr)

    # swapped units: damping and armature written 10x (a 'centi-' mistake)
    p = dict(good)
    p["damping"] = round(good["damping"] * 10.0, 6)
    p["armature"] = round(good["armature"] / 10.0, 6)
    _write(out_dir, "mut_swapped_units", p, names)

    # structure violations
    p = dict(good)
    p["gravity"] = -9.81
    _write(out_dir, "mut_extra_key", p, names)

    p = dict(good)
    p["mu"] = float("nan")
    # json.dump would emit NaN, which the loader itself rejects as invalid JSON
    with open(os.path.join(out_dir, "mut_nan.json"), "w") as fh:
        fh.write(json.dumps({**good, "mu": float("nan")}))
        fh.write("\n")
    names.append("mut_nan")

    p = dict(good)
    p["mu"] = "0.62"
    _write(out_dir, "mut_string_value", p, names)

    p = dict(good)
    p["damping"] = RANGES["damping"][1] + 0.01
    _write(out_dir, "mut_out_of_range", p, names)

    print("\n".join(names))


if __name__ == "__main__":
    main()
