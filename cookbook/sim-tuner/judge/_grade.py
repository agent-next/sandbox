#!/usr/bin/env python3
"""Judge driver for the sim-tuner demo. Invoked by grade.sh; see SPEC.md.

Grades a params.json artifact (the agent's calibrated physics parameters):

  G1 ranges           — strict JSON object, exactly the 5 finite parameters,
                        each within its physical range from PARAM_SPEC
  G2 training error   — CPU MuJoCo RMSE against the train recordings
  G3 held-out error   — CPU MuJoCo RMSE against the judge-hidden held-out
                        recordings: < ORACLE_ABS_ERR and < 30 % of the
                        default-parameter error
  G4 GPU/CPU agreement — the same params scored on a fresh 4 GiB mujoco_warp
                        batch run must match the CPU train error (abs 0.003,
                        rel 10 %); also validates the lease stack versions
                        against the SPEC table

The scenario (hidden ground truth, all recordings) is regenerated from
--seed inside this module; nothing on disk carries it. The artifact is
graded from a copy in a fresh temp dir; sha256 of judge/ before and after
must match.

Prints one JSON verdict on stdout; exit 0 only if every gate passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from engine import (DEFAULT_PARAMS, GPU_CPU_ABS, GPU_CPU_TOL, N_TRAIN, N_HOLDOUT,  # noqa: E402
                    ORACLE_ABS_ERR, ORACLE_REL_FRAC, PARAM_NAMES, PARAM_SPEC, RANGES,
                    bundle_scenario, check_version_table, error_of, gen_scenario,
                    gpu_eval_chunks, gpu_eval_code)

API = "https://api.sbx.agent-next.com"
MAX_BYTES = 16 * 1024
GPU_VRAM_GB = 4
GPU_TIMEOUT_S = 600


def die(msg):
    print(json.dumps({"error": msg}))
    sys.exit(2)


def check_shas(judge_dir):
    """sha256 of every judge/ source file (excluding __pycache__ / media dev files)."""
    digests = {}
    for root, dirs, files in os.walk(judge_dir):
        dirs.sort()
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(root, name)
            with open(path, "rb") as fh:
                digests[os.path.relpath(path, judge_dir)] = hashlib.sha256(fh.read()).hexdigest()
    return digests


def get_versions(label, accel=""):
    import mujoco
    import numpy as np
    mj_cv = tuple(int(x) for x in mujoco.__version__.split(".") if x.isdigit())
    v = {"name": label, "accel": accel, "os": platform.platform(),
         "python": platform.python_version(), "mujoco": mujoco.__version__,
         "numpy": np.__version__, "mujoco_cv": list(mj_cv)}
    return v


def load_artifact(path, ranges=None):
    """G1: strict structure and physical ranges. Never clamps: out-of-range fails.

    `ranges` overrides PARAM_SPEC ranges (used by the '--relaxed' self-test
    control, which grades a physically impossible artifact that should only
    fail on engine agreement, not on G1)."""
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError(f"artifact exceeds {MAX_BYTES} bytes")
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("artifact is not UTF-8") from None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"artifact is not valid JSON: {e}") from None
    if not isinstance(obj, dict):
        raise ValueError("artifact must be a JSON object, not " + type(obj).__name__)
    extra = sorted(set(obj) - set(PARAM_NAMES))
    missing = sorted(set(PARAM_NAMES) - set(obj))
    problems = []
    if missing:
        problems.append(f"missing parameters: {missing}")
    if extra:
        problems.append(f"unknown parameters: {extra}")
    params = {}
    spec = PARAM_SPEC if ranges is None else [
        (n, ranges.get(n, (RANGES[n]))[0], ranges.get(n, RANGES[n])[1], d, desc)
        for n, lo, hi, d, desc in PARAM_SPEC]
    for name, lo, hi, _, _ in spec:
        if name not in obj:
            continue
        v = obj[name]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            problems.append(f"{name} is not a number: {v!r}")
            continue
        v = float(v)
        if not math.isfinite(v):
            problems.append(f"{name} is not finite: {v!r}")
            continue
        if not (lo <= v <= hi):
            problems.append(f"{name} = {v} outside physical range [{lo}, {hi}]")
            continue
        params[name] = v
    if problems:
        raise ValueError("; ".join(problems))
    return params


def request(key, method, path, body=None, timeout=900):
    data = None if body is None else json.dumps(body).encode()
    req = Request(API + path, data=data, method=method,
                  headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        return exc.code, None


class GpuLease:
    """One 4 GiB RTX 5090 slice via the agent-next REST API. create/exec/confirm-kill."""

    def __init__(self, key):
        self.key = key
        self.id = None
        self.create_s = 0.0
        self.exec_wall_s = []

    def create(self):
        t0 = time.perf_counter()
        status, body = request(self.key, "POST", "/sandboxes",
                               {"accel": {"vram_gb": GPU_VRAM_GB, "reserve": "exec"}})
        if status != 201 or not isinstance(body, dict) or "sandboxID" not in body:
            raise RuntimeError(f"gpu create failed: HTTP {status} {str(body)[:200]}")
        sid = body["sandboxID"]
        if not isinstance(sid, str) or not sid.startswith("gl-") or not all(
                c.isascii() and (c.isalnum() or c == "-") for c in sid):
            raise RuntimeError(f"gpu create returned an invalid lease id {sid!r}; "
                               "delete it manually with sandbox_kill")
        self.id = sid
        self.create_s = round(time.perf_counter() - t0, 2)

    def exec(self, code, timeout=GPU_TIMEOUT_S):
        t0 = time.monotonic()
        status, body = request(self.key, "POST", f"/sandboxes/{self.id}/exec",
                               {"code": code, "timeout_s": timeout})
        dt = time.monotonic() - t0
        self.exec_wall_s.append(round(dt, 2))
        if status != 200 or not isinstance(body, dict):
            raise RuntimeError(f"gpu exec failed: HTTP {status}")
        result = body.get("result") or {}
        report = result.get("report")
        if result.get("ok") is not True or not isinstance(report, dict):
            raise RuntimeError(f"gpu exec job failed: {(result.get('stderr') or '')[-300:]}")
        report["_wall_s"] = round(dt, 3)
        return report

    def close(self):
        """DELETE + confirm; raise naming the id when destruction cannot be confirmed."""
        if not self.id:
            return
        sid = self.id
        try:
            request(self.key, "DELETE", f"/sandboxes/{sid}")
        except Exception:
            pass  # a lost destroy reply may still mean the lease was released
        try:
            status, remaining = request(self.key, "GET", f"/sandboxes/{sid}")
        except Exception as e:
            raise RuntimeError(f"cleanup unconfirmed for {sid}; run sandbox_kill for this id") from e
        if status != 404 and not (status == 200 and isinstance(remaining, dict)
                                  and remaining.get("phase") == "dead"):
            raise RuntimeError(f"cleanup unconfirmed for {sid}: HTTP {status}; "
                               "run sandbox_kill for this id")


def gate_gpu_agreement(lease, params, scen):
    """G4: score the artifact on the GPU batch evaluator; must match the CPU error."""
    errors, gpu_sim_s, versions, nworld = None, 0.0, None, 0
    for chunk in gpu_eval_chunks([params], scen["ics_train"]):
        rep = lease.exec(gpu_eval_code(chunk, scen["ics_train"], scen["refs_train"], scen["scale"]))
        if not rep.get("finite"):
            raise RuntimeError("gpu evaluate returned non-finite errors")
        errors = rep["err"]
        gpu_sim_s += rep["sim_s"]
        nworld = max(nworld, rep["nworld"])
        versions = rep.get("versions")
    cpu_err = error_of(params, scen["refs_train"], scen["ics_train"], scen["scale"])
    gpu_err = float(errors[0])
    abs_diff = abs(gpu_err - cpu_err)
    rel_diff = abs_diff / cpu_err if cpu_err else float("inf")
    ok = abs_diff <= GPU_CPU_ABS and rel_diff <= GPU_CPU_TOL and math.isfinite(gpu_err)
    return {"pass": ok, "gpu_train_err": round(gpu_err, 6), "cpu_train_err": round(cpu_err, 6),
            "abs_diff": round(abs_diff, 6), "rel_diff": round(rel_diff, 6),
            "abs_tol": GPU_CPU_ABS, "rel_tol": GPU_CPU_TOL,
            "gpu_sim_s": round(gpu_sim_s, 3), "nworld": nworld,
            "lease_versions": versions}


def grade(artifact_path, seed, gpu=True, lease=None, expected_versions=None, want_params=False):
    """Run every gate; -> (verdict dict, rc, scenario, lease)."""
    scen = gen_scenario(seed, expected_versions=expected_versions)
    t0 = time.perf_counter()
    verdict = {"artifact": os.path.basename(artifact_path), "demo": "sim-tuner",
               "seed": seed, "noise_frac": scen["noise_frac"],
               "gates": {}, "n_model_params": len(PARAM_NAMES),
               "recordings": {"train": N_TRAIN, "holdout": N_HOLDOUT}}

    problems = []
    try:
        params = load_artifact(artifact_path)
    except Exception as exc:
        params, problems = None, [str(exc)]
    verdict["gates"]["G1_ranges"] = {"pass": not problems, "problems": problems}

    cpu_train_err = None
    if params is not None:
        cpu_train_err = error_of(params, scen["refs_train"], scen["ics_train"], scen["scale"])
        cpu_hold_err = error_of(params, scen["refs_hold"], scen["ics_hold"], scen["scale"])
        cpu_hold_default = error_of(DEFAULT_PARAMS, scen["refs_hold"], scen["ics_hold"], scen["scale"])
        frac = cpu_hold_err / cpu_hold_default if cpu_hold_default else float("inf")
        g3_ok = cpu_hold_err < ORACLE_ABS_ERR and frac < ORACLE_REL_FRAC
        verdict["gates"]["G2_train"] = {"pass": True, "train_err": round(cpu_train_err, 6)}
        verdict["gates"]["G3_heldout"] = {
            "pass": g3_ok, "heldout_err": round(cpu_hold_err, 6),
            "abs_threshold": ORACLE_ABS_ERR,
            "frac_of_default": round(frac, 4), "rel_threshold": ORACLE_REL_FRAC,
            "default_err": round(cpu_hold_default, 6)}

    if params is not None and gpu:
        if lease is None:
            key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
            if not key:
                raise RuntimeError("no API key: export SBX_API_KEY (G4 needs a GPU lease)")
            lease = GpuLease(key)
        if lease.id is None:
            lease.create()
        g4 = gate_gpu_agreement(lease, params, scen)
        if expected_versions:
            vprobs = check_version_table(g4.get("lease_versions") or {}, expected_versions)
            g4["version_check"] = "pass" if not vprobs else "fail"
            if vprobs:
                g4.setdefault("problems", []).extend(vprobs)
                g4["pass"] = False
        else:
            g4["version_check"] = "unpinned"
        if g4["version_check"] not in ("unpinned", "pass"):
            g4["problems"] = g4["version_check"]["problems"]
            g4["pass"] = False
        verdict["gates"]["G4_gpu_cpu_agree"] = g4
    elif params is not None:
        verdict["gates"]["G4_gpu_cpu_agree"] = {"pass": None, "skipped": "no GPU lease"}

    verdict["timing"] = {"wall_seconds": round(time.perf_counter() - t0, 2),
                         "gpu_create_s": lease.create_s if lease else None,
                         "gpu_exec_wall_s": lease.exec_wall_s if lease else None}
    if want_params:
        verdict["params"] = params
    verdict["versions_cpu"] = get_versions("judge-host")
    rc = 0 if all(g.get("pass") for g in verdict["gates"].values()
                  if isinstance(g, dict) and g.get("pass") is not None) and not problems else 1
    verdict["pass"] = rc == 0
    verdict["verdict"] = "PASS" if rc == 0 else "FAIL"
    return verdict, rc, scen, lease


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", help="path to params.json")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--cpu-only", action="store_true", help="skip G4 (no GPU lease)")
    ap.add_argument("--judge-dir")
    ap.add_argument("--bundle", help="write the scenario bundle JSON here")
    ap.add_argument("--keep-params", action="store_true",
                    help="echo the parsed params back in the verdict (off by default)")
    args = ap.parse_args()

    judge_dir = os.path.abspath(args.judge_dir or HERE)
    sha_before = check_shas(judge_dir)

    table_path = os.path.join(judge_dir, "version-table.json")
    expected_versions = None
    if os.path.exists(table_path):
        with open(table_path) as fh:
            table = json.load(fh)
        if not isinstance(table, dict) or not table.get("gpu"):
            die(f"{table_path} is malformed: expected a 'gpu' table entry")
        expected_versions = table["gpu"]

    tmp = tempfile.mkdtemp(prefix="sim-tuner-artifact-")
    art = os.path.join(tmp, "params.json")
    shutil.copy(args.artifact, art)

    lease = None
    try:
        try:
            verdict, rc, scen, lease = grade(art, args.seed, gpu=not args.cpu_only,
                                             expected_versions=expected_versions,
                                             want_params=args.keep_params)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    finally:
        if lease and lease.id:
            lease.close()
            print("[gpu] lease destroyed and confirmed gone", file=sys.stderr, flush=True)

    sha_after = check_shas(judge_dir)
    verdict["judge_intact"] = sha_before == sha_after
    if not verdict["judge_intact"]:
        verdict["verdict"] = "FAIL"
        verdict["pass"] = False
        rc = 1
    if args.bundle:
        with open(args.bundle, "w") as fh:
            json.dump(bundle_scenario(scen), fh)
    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
