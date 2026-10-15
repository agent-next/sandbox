#!/usr/bin/env python3
"""make_media step 1: regenerate every data file the figures and video plot.

Everything written here is produced by the same judge engine (engine.py) that
grade.sh scores with — no number is typed in by hand:

  media/data/traces.npz   held-out recording 0 (seed 7): the recorded (hidden
                          truth + measurement noise) trace, the uncalibrated
                          default-parameter rollout, and the calibrated
                          examples/good rollout — CPU MuJoCo 3.8.1
  media/data/kills.json   self-test kill table: the known-good artifact and
                          every mutant graded --cpu-only; per-verdict failing
                          and passing CPU gates
  media/data/verdict_good.json
                          the good artifact's CPU verdict (the G3 held-out
                          error printed against its pass line in result.png)

The GPU search scores live in examples/good/loop.json (written by
tools/search.py); kill grading is CPU-only by design (judge/selftest.sh
comments), since every mutant is rejected by a CPU gate — no leases are
created here.

    SIM_TUNER_PYTHON=~/.venvs/sim-tuner/bin/python \
        ~/.venvs/sim-tuner/bin/python media/make_data.py
"""
import json
import os
import subprocess
import sys

DEMO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JUDGE = os.path.join(DEMO, "judge")
DATA = os.path.join(DEMO, "media", "data")
PY = os.environ.get("SIM_TUNER_PYTHON",
                    os.path.expanduser("~/.venvs/sim-tuner/bin/python"))
SEED = 7

sys.path.insert(0, JUDGE)
from engine import (DEFAULT_PARAMS, PARAM_NAMES, RANGES, error_of,  # noqa: E402
                    gen_scenario, simulate)


def grade(artifact, json_out):
    """CPU-only grade; returns the verdict dict (any exit code allowed)."""
    subprocess.run(["bash", os.path.join(JUDGE, "grade.sh"), artifact,
                    "--seed", str(SEED), "--cpu-only", "--json", json_out],
                   check=False, env={**os.environ, "SIM_TUNER_PYTHON": PY},
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(json_out) as fh:
        return json.load(fh)


def main():
    os.makedirs(DATA, exist_ok=True)
    mut_dir = os.path.join(DATA, "mutants")
    os.makedirs(mut_dir, exist_ok=True)

    scen = gen_scenario(SEED)
    with open(os.path.join(DEMO, "examples", "good", "params.json")) as fh:
        good = json.load(fh)

    # --- guards: the figures draw the judge's own pass lines, so the numbers
    # they need must already be true when media is regenerated
    g3 = {}
    v = grade(os.path.join(DEMO, "examples", "good", "params.json"),
              os.path.join(DATA, "verdict_good.json"))
    if not v.get("pass"):
        sys.exit("make_data: the good artifact does NOT pass --cpu-only "
                 f"grading (verdict {v.get('verdict')}); media would lie — "
                 "fix the example first")
    g3 = v["gates"]["G3_heldout"]
    h1_err = error_of(good, scen["refs_hold"][1:], scen["ics_hold"][1:],
                      scen["scale"])
    if (0.5 * g3["abs_threshold"] <= h1_err < g3["abs_threshold"]) or \
            (g3["abs_threshold"] <= h1_err and os.environ.get(
                "SIM_TUNER_MEDIA_ALLOW_H1", "") != "1"):
        sys.exit(
            "make_data: held-out recordings 1..3 err "
            f"{h1_err:.5f} is at/over the G3 line {g3['abs_threshold']} for the "
            "calibrated fit (SIM_TUNER_MEDIA_ALLOW_H1=1 to override)")

    # --- traces.npz: held-out recording 0, reported vs default vs calibrated
    import numpy as np
    ic = scen["ics_hold"][0]
    np.savez(os.path.join(DATA, "traces.npz"),
             t=np.arange(1, scen["refs_hold"][0].shape[0] + 1) * 0.008,
             recording=scen["refs_hold"][0],
             default=simulate(dict(DEFAULT_PARAMS), ic),
             calibrated=simulate(good, ic),
             scale=scen["scale"],
             g3_abs_threshold=g3["abs_threshold"],
             g3_default_err=g3["default_err"],
             g3_heldout_err=g3["heldout_err"])

    # --- kills.json: good + every mutant, CPU gates only (self-test rules)
    names = subprocess.run([PY, os.path.join(JUDGE, "mutants.py"), mut_dir],
                           check=True, capture_output=True, text=True,
                           env={**os.environ, "SIM_TUNER_SEED": str(SEED)}
                           ).stdout.split()
    kills = {"good": {
        "pass": v["pass"],
        "gates": {k: g.get("pass") for k, g in v["gates"].items()
                  if isinstance(g, dict)},
        "heldout_err": g3["heldout_err"]}}
    for name in sorted(names):
        vm = grade(os.path.join(mut_dir, name + ".json"),
                   os.path.join(DATA, f"verdict_{name}.json"))
        gates = {k: g.get("pass") for k, g in vm.get("gates", {}).items()
                 if isinstance(g, dict)}
        kills[name] = {"pass": vm.get("pass"), "gates": gates,
                       "heldout_err": (vm.get("gates", {})
                                       .get("G3_heldout", {})
                                       .get("heldout_err"))}
        if vm.get("pass"):
            sys.exit(f"make_data: mutant {name} SURVIVED CPU grading; "
                     "kill-rate figure would lie — the judge is broken")
    with open(os.path.join(DATA, "kills.json"), "w") as fh:
        json.dump(kills, fh, indent=2, sort_keys=True)
    print(f"make_data: {len(names)} mutants graded, all killed; "
          f"traces + verdicts in media/data/")


if __name__ == "__main__":
    main()
