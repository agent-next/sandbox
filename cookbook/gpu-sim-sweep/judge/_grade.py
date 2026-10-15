#!/usr/bin/env python3
"""Judge driver for the gpu-sim-sweep demo. Invoked by grade.sh; see SPEC.md.

The artifact is a CONFIG ONLY: scene XML (must equal canonical), timestep,
solver_iterations, nconmax/njmax, the nworld ladder, and the settle/timed/
batch counts. The judge computes every number it gates on by running the
simulation itself:

  gate 1 structure      — valid JSON, config keys only (result keys are
                          rejected), scene matches canonical
  gate 2 cost           — the work the config asks for is bounded (SPEC.md
                          "cost gate"), checked before any simulation runs
  gate 3 engine-parity  — mujoco version measured on GPU == measured on CPU
  gate 4 physics-oracle — live GPU state: finite, landed, bounded at every
                          nworld in the ladder
  gate 5 cpu-parity     — measured GPU world-0 trajectory vs the measured
                          CPU trajectory within tolerance
  gate 6 throughput     — measured top-nworld steps/s >= floor * measured
                          CPU steps/s

cpu-check mode (CPU-only machines) runs gates 1-2 plus a cpu-physics gate:
the same live oracle applied to the CPU reference run of the artifact's
config.

Measured numbers and wall-clock values live under the `timing` key so the
determinism check can compare verdicts on everything else.

Prints one JSON verdict on stdout; exit 0 only if every gated pass rule holds.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time

MAX_BYTES = 256 * 1024
PARITY_TOL = 0.05   # rad; measured CPU-vs-GPU world-0 divergence over the 800-
                    # step settle window is ~8e-3 (mujoco_warp accumulates in
                    # float32); mutants diverge by >= 0.1 or explode
ARM_ERR_TOL = 0.15
BOX_Z_MIN_MARGIN = 0.02
BOX_Z_MAX_MARGIN = 0.25
BOX_SPEED_MAX = 5.0
DEFAULT_SPEEDUP_FLOOR = 4.0  # measured x22-30 on the 4 GiB lease (see RECEIPT)
CPU_TIMED_STEPS = 20000      # CPU steps/s benchmark length
CPU_WARMUP_STEPS = 1000

# Cost bounds (SPEC.md "cost gate"), checked before any simulation runs so
# a single grade stays bounded no matter what the config asks for. All of
# them are derived from the config alone; nothing is measured. The good
# config sits at: settle 0.8 s, timed 0.4 s, 1200 steps/point, 100 solver
# iterations, ladder sum 10817, 13.0M aggregate world-steps.
SETTLE_S_RANGE = (0.4, 4.0)   # settle_steps * timestep; 0.4 s is about the
                            # minimum for every box to land from 0.5-1.1 m
TIMED_S_RANGE = (0.1, 4.0)    # timed_steps * batches * timestep
MAX_POINT_STEPS = 4000        # settle + batches*timed per ladder point:
                            # bounds the slowest point (nworld=1 ~ 240
                            # steps/s) at ~17 s of wall time
MAX_SOLVER_ITERS = 500        # solver cost per step is ~linear in iterations
MAX_BATCHES = 20
MAX_LADDER_LEN = 32
MAX_NWORLD = 65536            # beyond this the 4 GiB slice cannot allocate
MAX_WORLD_STEPS = 100_000_000  # point_steps * sum(ladder); worst legal
                            # config is ~90 s of GPU stepping

REQUIRED_KEYS = ("scene", "timestep", "solver_iterations", "nconmax", "njmax",
                 "nworld_ladder", "settle_steps", "timed_steps", "batches")
OPTIONAL_KEYS = {"notes"}
# Anything that smells like the artifact reporting its own results is
# contraband: the judge measures, the artifact configures.
RESULT_KEYS = {"points", "results", "cpu_steps_per_s", "cpu_mujoco_version",
               "cpu_trajectory", "gpu_trajectory", "trajectory", "steps_per_s",
               "oracle", "measurements", "verdict"}

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scene as scene_mod  # noqa: E402


def _sweep_mod():
    """Lazy: the sim stack (numpy/mujoco) is only needed past gate 1."""
    import _sweep
    return _sweep


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
        return json.loads(fh.read().decode("utf-8"))


def gate_structure(data):
    problems = []
    if not isinstance(data, dict):
        return ["artifact must be a JSON object"]
    for key in REQUIRED_KEYS:
        if key not in data:
            problems.append(f"missing required key: {key}")
    for key in sorted(set(data) - set(REQUIRED_KEYS) - OPTIONAL_KEYS):
        kind = "result key (the artifact may not report its own results)" \
            if key in RESULT_KEYS else "unexpected key"
        problems.append(f"{kind}: {key}")
    if "notes" in data and not isinstance(data["notes"], str):
        problems.append("notes must be a string")
    if problems:
        return problems
    if not isinstance(data["scene"], str) or len(data["scene"]) < 100:
        problems.append("scene must be a non-trivial XML string")
    if not isinstance(data["timestep"], (int, float)) \
            or isinstance(data["timestep"], bool) \
            or not 0 < data["timestep"] <= 0.01:
        problems.append("timestep must be a number in (0, 0.01]")
    if not isinstance(data["solver_iterations"], int) \
            or isinstance(data["solver_iterations"], bool) \
            or data["solver_iterations"] < 1:
        problems.append("solver_iterations must be a positive int")
    if not isinstance(data["nconmax"], int) or data["nconmax"] < 1:
        problems.append("nconmax must be a positive int")
    if not isinstance(data["njmax"], int) or data["njmax"] < 1:
        problems.append("njmax must be a positive int")
    if not isinstance(data["nworld_ladder"], list) \
            or len(data["nworld_ladder"]) < 2 \
            or not all(isinstance(n, int) and not isinstance(n, bool) and n >= 1
                       for n in data["nworld_ladder"]):
        problems.append("nworld_ladder must be a list of >= 2 positive ints")
    if not isinstance(data["settle_steps"], int) or data["settle_steps"] < 1:
        problems.append("settle_steps must be a positive int")
    if not isinstance(data["timed_steps"], int) or data["timed_steps"] < 1:
        problems.append("timed_steps must be a positive int")
    if not isinstance(data["batches"], int) or data["batches"] < 1:
        problems.append("batches must be a positive int")
    if not problems:
        art_norm = scene_mod.normalize_xml(data["scene"])
        canon_norm = scene_mod.normalize_xml(scene_mod.canonical_xml())
        if art_norm != canon_norm:
            problems.append("scene XML does not match canonical scene "
                            "(whitespace-normalised comparison)")
    return problems


def gate_cost(data):
    """Bounded-work check, run after structure and before any simulation
    (SPEC.md "cost gate"). A config that asks for more simulated work than
    these bounds is rejected here — in both modes — instead of being
    discovered by a grade exec that runs for minutes.
    """
    problems = []
    dt = data["timestep"]
    settle_s = data["settle_steps"] * dt
    timed_s = data["timed_steps"] * data["batches"] * dt
    point_steps = data["settle_steps"] + data["batches"] * data["timed_steps"]
    ladder = data["nworld_ladder"]
    world_steps = point_steps * sum(ladder)
    if not SETTLE_S_RANGE[0] <= settle_s <= SETTLE_S_RANGE[1]:
        problems.append(
            f"settle simulated time {settle_s:g} s (settle_steps "
            f"{data['settle_steps']} x timestep {dt:g}) outside "
            f"[{SETTLE_S_RANGE[0]}, {SETTLE_S_RANGE[1]}] s")
    if not TIMED_S_RANGE[0] <= timed_s <= TIMED_S_RANGE[1]:
        problems.append(
            f"timed simulated time {timed_s:g} s (timed_steps "
            f"{data['timed_steps']} x batches {data['batches']} x timestep "
            f"{dt:g}) outside [{TIMED_S_RANGE[0]}, {TIMED_S_RANGE[1]}] s")
    if point_steps > MAX_POINT_STEPS:
        problems.append(
            f"steps per ladder point {point_steps} (settle + batches*timed) "
            f"> {MAX_POINT_STEPS}")
    if data["solver_iterations"] > MAX_SOLVER_ITERS:
        problems.append(
            f"solver_iterations {data['solver_iterations']} > "
            f"{MAX_SOLVER_ITERS}")
    if data["batches"] > MAX_BATCHES:
        problems.append(f"batches {data['batches']} > {MAX_BATCHES}")
    if len(ladder) > MAX_LADDER_LEN:
        problems.append(f"nworld_ladder length {len(ladder)} > "
                        f"{MAX_LADDER_LEN}")
    if max(ladder) > MAX_NWORLD:
        problems.append(f"nworld_ladder max {max(ladder)} > {MAX_NWORLD}")
    if world_steps > MAX_WORLD_STEPS:
        problems.append(
            f"aggregate world-steps {world_steps} (steps/point "
            f"{point_steps} x ladder sum {sum(ladder)}) > {MAX_WORLD_STEPS}")
    return problems


def apply_config(data):
    """The physics the artifact asks for: canonical scene with the option
    element's timestep and solver iterations patched from the config."""
    xml = data["scene"]
    xml = re.sub(r'timestep="[^"]*"',
                 f'timestep="{data["timestep"]:g}"', xml, count=1)
    xml = re.sub(r'iterations="[^"]*"',
                 f'iterations="{data["solver_iterations"]:d}"', xml, count=1)
    return xml


def oracle_problems(tag, s):
    """Threshold oracle on a measured state dict (CPU or GPU point)."""
    bad = []
    if not s.get("qpos_finite", False):
        bad.append(f"{tag}: qpos not finite")
    if not s.get("qvel_finite", False):
        bad.append(f"{tag}: qvel not finite")
    err = s.get("arm_max_err")
    if err is None or not math.isfinite(err) or err >= ARM_ERR_TOL:
        bad.append(f"{tag}: arm tracking error {err} >= {ARM_ERR_TOL}")
    top = scene_mod.TABLE_TOP
    zmin = s.get("box_z_min")
    if zmin is None or not math.isfinite(zmin) or zmin <= top - BOX_Z_MIN_MARGIN:
        bad.append(f"{tag}: box min z {zmin} <= {top - BOX_Z_MIN_MARGIN} "
                   "(tunnelling)")
    zmax = s.get("box_z_max")
    if zmax is None or not math.isfinite(zmax) or zmax >= top + BOX_Z_MAX_MARGIN:
        bad.append(f"{tag}: box max z {zmax} >= {top + BOX_Z_MAX_MARGIN} "
                   "(never landed)")
    spd = s.get("box_speed_max")
    if spd is None or not math.isfinite(spd) or spd >= BOX_SPEED_MAX:
        bad.append(f"{tag}: box speed max {spd} >= {BOX_SPEED_MAX} "
                   "(energy unbounded)")
    return bad


def gpu_available():
    try:
        import warp as wp
        return bool(wp.is_cuda_available())
    except Exception:
        return False


def mujoco_available():
    return importlib.util.find_spec("mujoco") is not None


def public_point(p):
    """Strip big internals (trajectory) from a measured point for the verdict."""
    return {k: v for k, v in p.items() if k != "traj"}


def run_sims(data, mode):
    """The judge's own measurements. Returns (cpu, points, errors).

    cpu: cpu_reference result (includes world-0 trajectory), or None.
    points: per-nworld gpu_point results; a point that raises becomes
    {"nworld": n, "ok": False, "error": ...} — an observed failure, which is
    itself data (e.g. the over-capacity ladder point).
    """
    xml = apply_config(data)
    cpu = _sweep_mod().cpu_reference(xml, scene_mod.ARM_TARGET,
                               settle=data["settle_steps"],
                               warmup=CPU_WARMUP_STEPS,
                               timed=CPU_TIMED_STEPS,
                               record=(mode == "full"))
    if mode != "full":
        return cpu, []
    points = []
    for i, nw in enumerate(data["nworld_ladder"]):
        try:
            p = _sweep_mod().gpu_point(xml, scene_mod.ARM_TARGET, nw,
                                 nconmax=data["nconmax"], njmax=data["njmax"],
                                 settle=data["settle_steps"],
                                 timed=data["timed_steps"],
                                 batches=data["batches"],
                                 record_traj=(i == 0))
            p["ok"] = True
        except Exception as e:
            p = {"nworld": nw, "ok": False,
                 "error": f"{type(e).__name__}: {e}"[:300]}
        points.append(p)
    return cpu, points


def gate_engine_parity(cpu, points):
    problems = []
    gpu_v = {str(p.get("mujoco_version")) for p in points
             if p.get("ok") and p.get("mujoco_version")}
    cpu_v = str((cpu or {}).get("mujoco_version") or "")
    if not cpu_v:
        problems.append("CPU baseline did not report a mujoco version")
    elif not gpu_v:
        problems.append("no GPU sweep point reported a mujoco version")
    elif gpu_v != {cpu_v}:
        problems.append(f"GPU reports mujoco {sorted(gpu_v)}, "
                        f"CPU baseline measured {cpu_v}")
    return problems


def gate_physics_oracle(points):
    problems = []
    for p in points:
        nw = p.get("nworld", "?")
        if not p.get("ok"):
            problems.append(f"nworld={nw}: did not run "
                            f"({str(p.get('error'))[:120]})")
            continue
        problems += oracle_problems(f"nworld={nw}", p)
        nconf = p.get("nworld_confirmed")
        if nconf != nw:
            problems.append(f"nworld={nw}: confirmed world count "
                            f"{nconf} != {nw}")
    if not points:
        problems.append("no sweep points ran")
    return problems


def gate_cpu_parity(cpu, points):
    problems = []
    cpu_traj = (cpu or {}).get("traj") or []
    gpu_traj = (points[0].get("traj") if points and points[0].get("ok")
                else None) or []
    if len(cpu_traj) < 2 or len(gpu_traj) < 2:
        problems.append("missing measured cpu/gpu world-0 trajectory")
        return problems, None
    n = min(len(cpu_traj), len(gpu_traj))
    worst = 0.0
    for i in range(n):
        for a, b in zip(cpu_traj[i], gpu_traj[i]):
            err = abs(a - b)
            if math.isfinite(err):
                worst = max(worst, err)
            else:
                problems.append("non-finite value in trajectory comparison")
                return problems, None
    if worst > PARITY_TOL:
        problems.append(f"CPU vs GPU world-0 trajectory max error "
                        f"{worst:.6f} > {PARITY_TOL}")
    return problems, worst


def gate_throughput(cpu, points, floor):
    problems = []
    cpu_sps = (cpu or {}).get("steps_per_s") or 0
    ok = [p for p in points if p.get("ok") and p.get("steps_per_s")]
    if not cpu_sps:
        problems.append("CPU baseline produced no steps/s measurement")
    if not ok:
        problems.append("no sweep point produced a steps/s measurement")
        return problems, None
    top = max(ok, key=lambda p: p["nworld"])
    if top["nworld"] != max(p["nworld"] for p in points):
        problems.append(f"top ladder point nworld={max(p['nworld'] for p in points)} "
                        f"did not produce a measurement")
    target = floor * cpu_sps
    if top["steps_per_s"] < target:
        problems.append(f"top nworld={top['nworld']} measured "
                        f"{top['steps_per_s']} steps/s < floor {floor}x "
                        f"CPU ({target:.0f})")
    return problems, top["steps_per_s"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--cpu-check", action="store_true",
                    help="structure + CPU physics only (no GPU needed)")
    ap.add_argument("--speedup-floor", type=float,
                    default=DEFAULT_SPEEDUP_FLOOR)
    ap.add_argument("--judge-dir")
    ap.add_argument("--traj-json",
                    help="full mode only: also write the measured world-0 "
                         "settle trajectory (downsampled) to this path")
    args = ap.parse_args()

    judge_dir = os.path.abspath(args.judge_dir or HERE)
    sha_before = check_shas(judge_dir)

    tmp = tempfile.mkdtemp(prefix="gpu-sim-sweep-artifact-")
    art_path = os.path.join(tmp, "sweep.json")
    shutil.copy(args.artifact, art_path)

    verdict = {"artifact": os.path.basename(args.artifact),
               "mode": "cpu-check", "seed": args.seed,
               "gates": {}, "timing": {}}
    rc = 0
    t0 = time.perf_counter()
    try:
        try:
            data = load_artifact(art_path)
            problems = gate_structure(data)
        except Exception as exc:
            problems = [str(exc)[:300]]
        verdict["gates"]["structure"] = {"pass": not problems,
                                         "problems": problems}
        if problems:
            rc = 1
        else:
            problems = gate_cost(data)
            verdict["gates"]["cost"] = {"pass": not problems,
                                        "problems": problems}
            if problems:
                rc = 1
            else:
                full = gpu_available() and not args.cpu_check
                verdict["mode"] = "full" if full else "cpu-check"
                try:
                    cpu, points = run_sims(data, verdict["mode"])
                    sim_err = None
                except Exception as e:
                    cpu, points = None, []
                    sim_err = f"{type(e).__name__}: {e}"[:300]

                if not full:
                    # CPU-only: structure + a live CPU physics oracle. GPU
                    # gates need the lease (see SPEC).
                    problems = ([f"cpu reference crashed: {sim_err}"]
                                if sim_err
                                else oracle_problems("cpu", cpu or {}))
                    verdict["gates"]["cpu-physics"] = {
                        "pass": not problems, "problems": problems}
                    if problems:
                        rc = 1
                    if cpu:
                        verdict["timing"]["cpu"] = public_point(cpu)
                else:
                    if sim_err:
                        for g in ("engine-parity", "physics-oracle",
                                  "cpu-parity", "throughput"):
                            verdict["gates"][g] = {
                                "pass": False,
                                "problems": [f"grade sim crashed: {sim_err}"]}
                        rc = 1
                    else:
                        for name, problems in (
                                ("engine-parity",
                                 gate_engine_parity(cpu, points)),
                                ("physics-oracle",
                                 gate_physics_oracle(points))):
                            verdict["gates"][name] = {
                                "pass": not problems, "problems": problems}
                            if problems:
                                rc = 1
                        problems, parity_err = gate_cpu_parity(cpu, points)
                        verdict["gates"]["cpu-parity"] = {
                            "pass": not problems, "problems": problems}
                        if problems:
                            rc = 1
                        problems, top_sps = gate_throughput(
                            cpu, points, args.speedup_floor)
                        verdict["gates"]["throughput"] = {
                            "pass": not problems, "problems": problems}
                        if problems:
                            rc = 1

                        # everything measured lives under `timing` so the
                        # determinism check can diff the verdict without it
                        verdict["timing"] = {
                            "cpu": public_point(cpu),
                            "points": [public_point(p) for p in points],
                            "cold_compile_s": (points[0].get("first_step_s")
                                               if points
                                               and points[0].get("ok")
                                               else None),
                            "parity_max_err": parity_err,
                            "cpu_steps_per_s":
                                (cpu or {}).get("steps_per_s"),
                            "top_steps_per_s": top_sps,
                            "speedup": (top_sps / cpu["steps_per_s"]
                                        if top_sps
                                        and cpu.get("steps_per_s")
                                        else None),
                            "speedup_floor": args.speedup_floor,
                        }

                        # optional: the measured world-0 settle trajectory,
                        # for media. Not part of the verdict (size), so the
                        # determinism check never sees it.
                        if args.traj_json and points \
                                and points[0].get("ok") \
                                and points[0].get("traj"):
                            traj = points[0]["traj"]
                            stride = max(1, -(-len(traj) // 240))
                            with open(args.traj_json, "w") as fh:
                                json.dump(
                                    {"timestep": data["timestep"],
                                     "settle_steps": data["settle_steps"],
                                     "nq": cpu["nq"],
                                     "stride": stride,
                                     "traj": traj[::stride]}, fh)

        sha_after = check_shas(judge_dir)
        verdict["judge_intact"] = sha_before == sha_after
        if not verdict["judge_intact"]:
            rc = 1
        verdict["timing"]["wall_s"] = round(time.perf_counter() - t0, 2)
    except Exception as exc:
        # a judge bug must not masquerade as a graded artifact: emit the
        # error and exit 2 (distinct from rc=1 "graded and failed")
        die(f"judge error: {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
