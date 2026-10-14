#!/usr/bin/env python3
"""Judge driver for the gpu-sim-sweep demo. Invoked by grade.sh; see SPEC.md.

Grades a copied artifact (the artifact under test never touches judge/):
  gate 1 structure      — valid JSON, required keys, scene matches canonical
  gate 2 engine-parity  — mujoco version on GPU == CPU
  gate 3 physics-oracle — finite, landed, bounded at every nworld
  gate 4 cpu-parity     — GPU world-0 trajectory matches CPU within tolerance
  gate 5 throughput     — top nworld steps/s >= floor * cpu_steps_per_s

Prints one JSON verdict on stdout; exit 0 only if every gated pass rule holds.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

VENV_DIR = os.path.join(os.path.expanduser("~"), ".venvs", "gpu-sim-sweep")
sys.path.insert(0, VENV_DIR)

MAX_BYTES = 256 * 1024
PARITY_TOL = 1e-3
ARM_ERR_TOL = 0.15
BOX_Z_MIN_MARGIN = 0.02
BOX_Z_MAX_MARGIN = 0.25
BOX_SPEED_MAX = 5.0
DEFAULT_SPEEDUP_FLOOR = 20.0

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scene as scene_mod  # noqa: E402


def die(msg):
    print(json.dumps({"error": msg}))
    sys.exit(2)


def check_shas(judge_dir):
    """sha256 of every judge/ source file, before and after the run."""
    digests = {}
    for root, dirs, files in os.walk(judge_dir):
        dirs.sort()
        if os.path.basename(root) == "__pycache__":
            dirs[:] = []
            continue
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(root, name)
            with open(path, "rb") as fh:
                digests[os.path.relpath(path, judge_dir)] = \
                    hashlib.sha256(fh.read()).hexdigest()
    return digests


def load_artifact(path):
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError(f"artifact exceeds {MAX_BYTES // 1024} KiB")
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    data = json.loads(text)
    return data, text


def gate_structure(data):
    problems = []
    required = ["scene", "timestep", "solver_iterations", "nconmax", "njmax",
                "nworld_ladder", "settle_steps", "timed_steps", "batches",
                "cpu_steps_per_s", "cpu_mujoco_version", "points"]
    for key in required:
        if key not in data:
            problems.append(f"missing required key: {key}")
    if problems:
        return problems
    if not isinstance(data["scene"], str) or len(data["scene"]) < 100:
        problems.append("scene must be a non-trivial XML string")
    if not isinstance(data["timestep"], (int, float)) or data["timestep"] <= 0:
        problems.append("timestep must be a positive number")
    if not isinstance(data["solver_iterations"], int) or data["solver_iterations"] < 1:
        problems.append("solver_iterations must be a positive int")
    if not isinstance(data["nconmax"], int) or data["nconmax"] < 1:
        problems.append("nconmax must be a positive int")
    if not isinstance(data["njmax"], int) or data["njmax"] < 1:
        problems.append("njmax must be a positive int")
    if not isinstance(data["nworld_ladder"], list) or len(data["nworld_ladder"]) < 2:
        problems.append("nworld_ladder must be a list of >= 2 ints")
    elif not all(isinstance(n, int) and n >= 1 for n in data["nworld_ladder"]):
        problems.append("nworld_ladder must contain positive ints")
    if not isinstance(data["settle_steps"], int) or data["settle_steps"] < 1:
        problems.append("settle_steps must be a positive int")
    if not isinstance(data["timed_steps"], int) or data["timed_steps"] < 1:
        problems.append("timed_steps must be a positive int")
    if not isinstance(data["batches"], int) or data["batches"] < 1:
        problems.append("batches must be a positive int")
    if not isinstance(data["cpu_steps_per_s"], (int, float)) or data["cpu_steps_per_s"] <= 0:
        problems.append("cpu_steps_per_s must be a positive number")
    if not isinstance(data["cpu_mujoco_version"], str):
        problems.append("cpu_mujoco_version must be a string")
    if not isinstance(data["points"], list) or len(data["points"]) < 2:
        problems.append("points must be a list of >= 2 entries")
    # scene normalises to canonical
    if not problems:
        art_norm = scene_mod.normalize_xml(data["scene"])
        canon_norm = scene_mod.normalize_xml(scene_mod.canonical_xml())
        if art_norm != canon_norm:
            problems.append("scene XML does not match canonical scene "
                            "(whitespace-normalised comparison)")
    return problems


def gate_engine_parity(data):
    """GPU mujoco version == CPU mujoco version."""
    problems = []
    gpu_versions = set()
    for p in data.get("points", []):
        v = p.get("mujoco_version")
        if v:
            gpu_versions.add(str(v))
    cpu_v = str(data.get("cpu_mujoco_version", ""))
    if not gpu_versions:
        problems.append("no GPU mujoco_version reported in any point")
    elif cpu_v not in gpu_versions:
        problems.append(f"GPU reports mujoco {sorted(gpu_versions)}, "
                        f"CPU baseline uses {cpu_v}")
    return problems


def gate_physics_oracle(data):
    """Every sweep point must pass the physics oracle."""
    problems = []
    for p in data.get("points", []):
        nw = p.get("nworld", "?")
        if not p.get("qpos_finite", False):
            problems.append(f"nworld={nw}: qpos not finite")
        if not p.get("qvel_finite", False):
            problems.append(f"nworld={nw}: qvel not finite")
        arm_err = p.get("arm_max_err")
        if arm_err is None or arm_err >= ARM_ERR_TOL:
            problems.append(f"nworld={nw}: arm tracking error "
                            f"{arm_err} >= {ARM_ERR_TOL}")
        zmin = p.get("box_z_min")
        table_top = scene_mod.TABLE_TOP
        if zmin is None or zmin <= table_top - BOX_Z_MIN_MARGIN:
            problems.append(f"nworld={nw}: box min z {zmin} <= "
                            f"{table_top - BOX_Z_MIN_MARGIN} (tunnelling)")
        zmax = p.get("box_z_max")
        if zmax is None or zmax >= table_top + BOX_Z_MAX_MARGIN:
            problems.append(f"nworld={nw}: box max z {zmax} >= "
                            f"{table_top + BOX_Z_MAX_MARGIN} (never landed)")
        bspeed = p.get("box_speed_max")
        if bspeed is None or bspeed >= BOX_SPEED_MAX:
            problems.append(f"nworld={nw}: box speed max {bspeed} >= "
                            f"{BOX_SPEED_MAX} (energy unbounded)")
        nconf = p.get("nworld_confirmed")
        if nconf is not None and nconf != nw:
            problems.append(f"nworld={nw}: confirmed world count {nconf} != {nw}")
    return problems


def gate_cpu_parity(data):
    """GPU world-0 trajectory matches CPU trajectory within PARITY_TOL."""
    problems = []
    cpu_traj = data.get("cpu_trajectory")
    gpu_traj = data.get("gpu_trajectory")
    if not cpu_traj or not gpu_traj:
        problems.append("missing cpu_trajectory or gpu_trajectory")
        return problems
    n_steps = min(len(cpu_traj), len(gpu_traj))
    if n_steps < 2:
        problems.append("trajectory too short for comparison")
        return problems
    worst = 0.0
    for i in range(n_steps):
        cpu_q = cpu_traj[i]
        gpu_q = gpu_traj[i]
        n_joints = min(len(cpu_q), len(gpu_q))
        for j in range(n_joints):
            err = abs(cpu_q[j] - gpu_q[j])
            if math.isfinite(err):
                worst = max(worst, err)
    if worst > PARITY_TOL:
        problems.append(f"CPU vs GPU world-0 trajectory max error "
                        f"{worst:.6f} > {PARITY_TOL}")
    return problems


def gate_throughput(data, floor):
    """Top ladder point steps/s >= floor * cpu_steps_per_s."""
    problems = []
    cpu_sps = data.get("cpu_steps_per_s", 0)
    points = data.get("points", [])
    if not points:
        problems.append("no sweep points to evaluate throughput")
        return problems
    top = max(points, key=lambda p: p.get("steps_per_s", 0))
    top_sps = top.get("steps_per_s", 0)
    target = floor * cpu_sps
    if top_sps < target:
        problems.append(f"top nworld={top.get('nworld')} steps/s {top_sps} < "
                        f"floor {floor}x CPU ({target:.0f})")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--cpu-check", action="store_true")
    ap.add_argument("--speedup-floor", type=float, default=DEFAULT_SPEEDUP_FLOOR)
    ap.add_argument("--judge-dir")
    args = ap.parse_args()

    judge_dir = os.path.abspath(args.judge_dir or HERE)
    sha_before = check_shas(judge_dir)

    tmp = tempfile.mkdtemp(prefix="gpu-sim-sweep-artifact-")
    art_path = os.path.join(tmp, "sweep.json")
    shutil.copy(args.artifact, art_path)

    verdict = {"artifact": os.path.basename(args.artifact), "mode": "cpu-check",
               "seed": args.seed, "gates": {}, "timing": {}, "points": []}
    rc = 0
    try:
        try:
            data, text = load_artifact(art_path)
        except Exception as exc:
            verdict["gates"]["structure"] = {"pass": False,
                                             "problems": [str(exc)[:300]]}
            rc = 1
        else:
            verdict["gates"]["structure"] = {
                "pass": True, "problems": gate_structure(data)}
            if verdict["gates"]["structure"]["problems"]:
                verdict["gates"]["structure"]["pass"] = False
                rc = 1

        if args.cpu_check:
            # CPU-only: structure gate only
            verdict["mode"] = "cpu-check"
        else:
            verdict["mode"] = "full"
            if rc == 0:
                verdict["gates"]["engine-parity"] = {
                    "pass": True, "problems": gate_engine_parity(data)}
                if verdict["gates"]["engine-parity"]["problems"]:
                    verdict["gates"]["engine-parity"]["pass"] = False
                    rc = 1
            if rc == 0:
                verdict["gates"]["physics-oracle"] = {
                    "pass": True, "problems": gate_physics_oracle(data)}
                if verdict["gates"]["physics-oracle"]["problems"]:
                    verdict["gates"]["physics-oracle"]["pass"] = False
                    rc = 1
            if rc == 0:
                verdict["gates"]["cpu-parity"] = {
                    "pass": True, "problems": gate_cpu_parity(data)}
                if verdict["gates"]["cpu-parity"]["problems"]:
                    verdict["gates"]["cpu-parity"]["pass"] = False
                    rc = 1
            if rc == 0:
                verdict["gates"]["throughput"] = {
                    "pass": True, "problems": gate_throughput(data, args.speedup_floor)}
                if verdict["gates"]["throughput"]["problems"]:
                    verdict["gates"]["throughput"]["pass"] = False
                    rc = 1
            # populate timing and points for the verdict
            cpu_sps = data.get("cpu_steps_per_s", 0)
            points = data.get("points", [])
            top = max(points, key=lambda p: p.get("steps_per_s", 0)) if points else {}
            verdict["timing"] = {
                "cpu_steps_per_s": cpu_sps,
                "top_steps_per_s": top.get("steps_per_s", 0),
                "speedup": (top.get("steps_per_s", 0) / cpu_sps
                            if cpu_sps > 0 else 0),
                "speedup_floor": args.speedup_floor,
            }
            verdict["points"] = [{"nworld": p.get("nworld"),
                                   "steps_per_s": p.get("steps_per_s"),
                                   "arm_max_err": p.get("arm_max_err"),
                                   "box_z_min": p.get("box_z_min"),
                                   "box_z_max": p.get("box_z_max"),
                                   "qpos_finite": p.get("qpos_finite")}
                                  for p in points]

        sha_after = check_shas(judge_dir)
        verdict["judge_intact"] = sha_before == sha_after
        if not verdict["judge_intact"]:
            rc = 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
