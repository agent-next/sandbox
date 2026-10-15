"""Capture the states *inside* CPU grading, then match the fresh lease receipt."""

import json
import hashlib
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
sys.path.insert(0, str(DEMO / "judge"))
import engine
import _grade


def key(params, ic):
    return tuple(params[n] for n in engine.PARAM_NAMES), tuple(sorted(ic.items()))


def collect():
    report = json.loads((HERE / "data/run-1.json").read_text())
    accepted = report["verdict"]
    assert accepted["pass"] and accepted["judge_intact"]
    captured = {}
    original_simulate = engine.simulate
    original_step = engine.mujoco.mj_step

    def simulate(params, ic):
        positions, velocities = [], []

        def step(model, data):
            if not positions:
                positions.append(data.qpos.copy())
                velocities.append(data.qvel.copy())
            original_step(model, data)
            positions.append(data.qpos.copy())
            velocities.append(data.qvel.copy())

        with patch.object(engine.mujoco, "mj_step", step):
            signals = original_simulate(params, ic)
        qp, qv = np.asarray(positions), np.asarray(velocities)
        # The exact post-step samples that error_of() consumes.
        observed = np.column_stack((qp[4::4, 0], qp[4::4, 2], qv[4::4, 2],
                                    qp[4::4, 7:9], qv[4::4, 6:8]))
        np.testing.assert_array_equal(observed, signals)
        captured[key(params, ic)] = (qp, qv)
        return signals

    with patch.object(engine, "simulate", simulate):
        verdict, _, scenario, _ = _grade.grade(
            str(DEMO / "examples/good/params.json"), accepted["seed"], gpu=False)
    for name in ("G1_ranges", "G2_train", "G3_heldout"):
        assert verdict["gates"][name] == accepted["gates"][name], \
            f"Local replay differs from accepted lease: {name}"
    good = _grade.load_artifact(DEMO / "examples/good/params.json")
    roles = {"default": engine.DEFAULT_PARAMS, "tuned": good, "truth": scenario["truth"]}
    arrays = {}
    for role, params in roles.items():
        for i, ic in enumerate(scenario["ics_hold"]):
            qp, qv = captured[key(params, ic)]
            arrays[f"{role}_{i}_qpos"] = qp
            arrays[f"{role}_{i}_qvel"] = qv
    np.savez_compressed(HERE / "data/trajectories.npz", **arrays)
    metadata = {"seed": accepted["seed"], "timestep_s": 0.002,
                "steps": engine.NSTEP, "roles": roles,
                "initial_conditions": scenario["ics_hold"],
                "source": "Captured inside _grade.grade CPU scoring; G1-G3 equal data/run-1.json",
                "gates": accepted["gates"]}
    # Rank presentation by the largest actual horizontal miss, not an invented
    # dramatic trajectory. Preserve the original held-out recording identifiers.
    cases = []
    for i in range(len(scenario["ics_hold"])):
        errors = {}
        for role in ("default", "tuned"):
            qp, qv = arrays[f"{role}_{i}_qpos"], arrays[f"{role}_{i}_qvel"]
            signals = np.column_stack((qp[4::4, 0], qp[4::4, 2], qv[4::4, 2],
                                       qp[4::4, 7:9], qv[4::4, 6:8]))
            errors[role] = float(np.sqrt(np.mean(
                ((signals - scenario["refs_hold"][i]) / scenario["scale"]) ** 2)))
        gap = np.abs(arrays[f"default_{i}_qpos"][:, 0] -
                     arrays[f"truth_{i}_qpos"][:, 0])
        cases.append({"source_recording": i, "max_default_box_gap_cm": float(gap.max() * 100),
                      "default_error": errors["default"], "tuned_error": errors["tuned"]})
    metadata["presentation_order"] = sorted(
        cases, key=lambda c: c["max_default_box_gap_cm"], reverse=True)
    for role, name in (("default", "default_err"), ("tuned", "heldout_err")):
        aggregate = np.sqrt(np.mean([c[f"{role}_error"] ** 2 for c in cases]))
        assert round(float(aggregate), 6) == accepted["gates"]["G3_heldout"][name]
    (HERE / "data/replay.json").write_text(json.dumps(metadata, indent=2) + "\n")
    paths = [DEMO / "run.py", *sorted((DEMO / "judge").glob("*")),
             *sorted((DEMO / "examples/good").glob("*.json"))]
    hashes = {str(p.relative_to(DEMO)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in paths if p.is_file()}
    provenance = {
        "source_commit": subprocess.check_output(
            ["git", "-C", str(DEMO), "rev-parse", "HEAD"], text=True).strip(),
        "source_sha256": hashes,
        "note": "Exact grading inputs; media and documentation may be committed later."
    }
    (HERE / "data/provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("Captured 12 graded held-out trajectories; G1-G3 match the fresh lease exactly.")


if __name__ == "__main__":
    collect()
