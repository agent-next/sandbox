#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test from the known-good params.

Every mutant is the known-good examples/good/params.json with a scripted
change, one per file; the self-test expects each to fail at least one gate.
The failure classes are the ones the brief calls out: single parameters
pushed to a physical-range edge, the uncalibrated defaults, a uniformly
biased fit (every parameter shifted +12 % of its physical range off the hidden
truth), swapped units, plus structure violations (extra key, non-finite,
string value, value outside range).

No mutant is produced by a training search. The bias mutant is a
deterministic function of the hidden truth and holds no fitted, searched or
otherwise data-derived number: it is a systematically miscalibrated fit, and
it is named for exactly that.
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


BIASED_FIT_FRAC = 0.12


def biased_fit(scen):
    """A systematically miscalibrated fit: hidden-truth parameters shifted
    by BIASED_FIT_FRAC of each physical range on every axis. Deterministic
    (pure function of scen['truth']); no search, no fitted numbers."""
    truth = scen["truth"]
    return {n: round(min(RANGES[n][1], max(RANGES[n][0],
                truth[n] + BIASED_FIT_FRAC * (RANGES[n][1] - RANGES[n][0]))), 6)
            for n in PARAM_NAMES}


def generate(out_dir, seed=None):
    """Generate all mutants into out_dir; return their names."""
    seed = seed if seed is not None else int(os.environ.get("SIM_TUNER_SEED", "7"))
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

    truth = scen["truth"]
    p = {n: round(min(RANGES[n][1], max(RANGES[n][0],
              truth[n] + 0.06 * (RANGES[n][1] - RANGES[n][0]))), 6)
         for n in PARAM_NAMES}
    _write(out_dir, "mut_truth_shift6", p, names)

    _write(out_dir, "mut_defaults", dict(DEFAULT_PARAMS), names)

    p = biased_fit(scen)
    _write(out_dir, "mut_biased_fit", p, names)

    p = dict(good)
    p["damping"] = round(good["damping"] * 10.0, 6)
    p["armature"] = round(good["armature"] / 10.0, 6)
    _write(out_dir, "mut_swapped_units", p, names)

    p = dict(good)
    p["gravity"] = -9.81
    _write(out_dir, "mut_extra_key", p, names)

    p = dict(good)
    p["mu"] = float("nan")
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

    return names


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(HERE, "mutants-out")
    seed = int(os.environ.get("SIM_TUNER_SEED", "7"))
    names = generate(out_dir, seed=seed)
    scen = gen_scenario(seed)
    p = biased_fit(scen)
    hold = error_of(p, scen["refs_hold"], scen["ics_hold"], scen["scale"])
    print(f"# mut_biased_fit held-out err {hold:.6f} "
          f"(G3 absolute threshold {0.025})", file=sys.stderr)
    print("\n".join(names))


if __name__ == "__main__":
    main()
