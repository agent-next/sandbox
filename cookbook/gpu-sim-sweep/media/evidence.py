"""Measured GPU acceptance report and the judge's exact CPU reference replay."""

import json
from pathlib import Path
import sys

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
sys.path.insert(0, str(DEMO / "judge"))
import _grade as grade
import _sweep as sweep
import scene

GATES = ("structure", "cost", "engine-parity", "physics-oracle",
         "cpu-parity", "throughput")


def assert_state(actual, expected, context):
    a, b = np.asarray(actual), np.asarray(expected)
    assert a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), \
        f"{context}: rendered-state mismatch (shape or non-finite)"
    assert np.max(np.abs(a - b), initial=0) <= 1e-9, \
        f"{context}: rendered-state mismatch"


def load_report():
    report = json.loads((HERE / "data/report.json").read_text())
    good = report["good"]
    verdict = good["verdict"]
    assert good["rc"] == 0 and verdict["mode"] == "full" and verdict["judge_intact"]
    assert set(verdict["gates"]) == set(GATES)
    assert all(g["pass"] for g in verdict["gates"].values())
    assert len(report["mutants"]) == 8
    for name, mutant in report["mutants"].items():
        assert mutant["rc"] == 1 and mutant["failed"] and not mutant["judge_error"], \
            f"Self-test incomplete: {name}"
        assert set(mutant["failed"]) == {g for g, ok in mutant["gates"].items()
                                         if ok is False}
    timing = verdict["timing"]
    assert not grade.gate_physics_oracle(timing["points"])
    assert timing["top_steps_per_s"] == timing["points"][-1]["steps_per_s"]
    assert timing["cpu_steps_per_s"] == timing["cpu"]["steps_per_s"]
    assert timing["speedup"] == timing["top_steps_per_s"] / timing["cpu_steps_per_s"]
    return report


def reference(report):
    config = json.loads((DEMO / "examples/good/sweep.json").read_text())
    assert not grade.gate_structure(config) and not grade.gate_cost(config)
    xml = grade.apply_config(config)
    assert mujoco.__version__ == report["good"]["verdict"]["timing"]["cpu"]["mujoco_version"]
    # Run the actual reference function, not a reimplementation of its physics.
    cpu = sweep.cpu_reference(xml, scene.ARM_TARGET, settle=config["settle_steps"],
                              warmup=0, timed=1, record=True)
    recorded = report["good"]["verdict"]["timing"]["cpu"]
    for key in ("arm_max_err", "box_z_min", "box_z_max", "box_speed_max"):
        assert_state(cpu[key], recorded[key], f"graded CPU oracle {key}")
    assert not grade.oracle_problems("CPU replay", cpu)
    states = np.asarray(cpu["traj"], dtype=np.float64)
    model = mujoco.MjModel.from_xml_string(xml)
    assert states.shape == (config["settle_steps"] + 1, model.nq)
    assert_state(states[0], model.qpos0, "initial state")
    assert config["nworld_ladder"] == [p["nworld"] for p in
                                    report["good"]["verdict"]["timing"]["points"]]
    for point in report["good"]["verdict"]["timing"]["points"]:
        for key in ("nconmax", "njmax", "timed_steps"):
            assert point[key] == config[key], f"Graded config mismatch: {key}"
        assert len(point["steps_per_s_batches"]) == config["batches"]
    gpu = report["good"]["world0_traj"]
    assert gpu["timestep"] == model.opt.timestep == config["timestep"]
    assert gpu["settle_steps"] == config["settle_steps"] and gpu["nq"] == model.nq
    indices = np.arange(0, len(states), gpu["stride"])
    measured = np.asarray(gpu["traj"])
    assert measured.shape == states[indices].shape and np.isfinite(measured).all()
    # _sweep.gpu_point records AFTER its compile step. Preserve the judge's
    # original index convention (CPU step i vs GPU step i+1), not fake equality
    # between double-precision MuJoCo and float32 Warp.
    error = float(np.max(np.abs(states[indices] - measured)))
    assert error <= grade.PARITY_TOL, f"Recorded GPU trajectory parity mismatch: {error}"
    return config, xml, states, error


def collect():
    report = load_report()
    config, xml, states, error = reference(report)
    np.save(HERE / "data/cpu-qpos.npy", states, allow_pickle=False)
    (HERE / "data/model.xml").write_text(xml + "\n")
    metadata = {
        "command": "media/.venv/bin/python media/evidence.py",
        "source": "judge/_sweep.py:cpu_reference; examples/good/sweep.json",
        "seed": report["good"]["verdict"]["seed"],
        "timestep_s": config["timestep"],
        "samples": len(states),
        "initial_state": "MjData(model).qpos = model.qpos0; qvel = 0; ctrl = ARM_TARGET",
        "replay": "MuJoCo CPU reference replay of world 0",
        "recorded_gpu_samples": len(report["good"]["world0_traj"]["traj"]),
        "recorded_gpu_sample_max_error": error,
        "recorded_gpu_tolerance": grade.PARITY_TOL,
        "gpu_sample_convention": "CPU i versus GPU i+1, as in the judge parity gate",
        "worlds": "identical initial states; no randomization",
    }
    (HERE / "data/replay.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(f"CPU reference: {len(states)} states; graded oracle matches within 1e-9")
    print(f"Recorded GPU trajectory: {metadata['recorded_gpu_samples']} samples; "
          f"max error {error:.8f} <= {grade.PARITY_TOL}")


if __name__ == "__main__":
    collect()
