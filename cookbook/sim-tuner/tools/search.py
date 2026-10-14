#!/usr/bin/env python3
"""The demo's evaluate loop, run by the demo builder to PRODUCE examples/good/.

Imitates what the user's agent does: batches of candidates are scored in one
batched mujoco_warp run per chunk on a 4 GiB GPU slice (nworld = candidates x
6 train recordings), then a cross-entropy style resample shrinks around the
elite. Every batch's scores are appended to examples/good/loop.json (the
media round turns it into loop.png). The resulting artifact is written to
examples/good/params.json.

    SIM_TUNER_PYTHON=~/.venvs/sim-tuner/bin/python \
    python3 cookbook/sim-tuner/tools/search.py [--seed 7] [--budget 2000]

Needs SBX_API_KEY (or E2B_API_KEY) with GPU access. Runs the judge venv
python so CPU errors of the incumbent can be watched locally (the incumbent
is only graded by the judge, not here).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE = os.path.join(HERE, "..", "judge")
sys.path.insert(0, JUDGE)
sys.path.insert(0, os.path.expanduser("~/.venvs/sim-tuner/lib"))

from engine import (DEFAULT_PARAMS, PARAM_NAMES, PARAM_SPEC, RANGES,  # noqa: E402
                    error_of, gen_scenario, gpu_eval_chunks, gpu_eval_code)
from _grade import GpuLease  # noqa: E402

GOOD_DIR = os.path.join(HERE, "..", "examples", "good")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--budget", type=int, default=2000)
    ap.add_argument("--out", default=GOOD_DIR)
    args = ap.parse_args()

    import numpy as np

    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        print("export SBX_API_KEY (GPU access needed)", file=sys.stderr)
        return 2

    scen = gen_scenario(args.seed)
    lo = np.array([p[1] for p in PARAM_SPEC])
    hi = np.array([p[2] for p in PARAM_SPEC])
    dflt = np.array([DEFAULT_PARAMS[n] for n in PARAM_NAMES])
    rng = np.random.default_rng(args.seed - 3)
    t_start = time.time()

    lease = GpuLease(key)
    iterations = []
    n_done, n_eval_calls, gpu_sim_s = 0, 0, 0.0
    best = {"err": float("inf"), "params": None}

    def gpu_score(cands):
        nonlocal n_eval_calls, gpu_sim_s
        errors = []
        for chunk in gpu_eval_chunks(cands, scen["ics_train"]):
            t0 = time.monotonic()
            rep = lease.exec(gpu_eval_code(chunk, scen["ics_train"],
                                           scen["refs_train"], scen["scale"]))
            dt = time.monotonic() - t0
            n_eval_calls += 1
            gpu_sim_s += rep["sim_s"]
            versions = rep.get("versions")
            errors.extend(rep["err"])
            iterations[-1]["chunks"].append({
                "n": len(chunk), "best_err": min(rep["err"]), "sim_s": rep["sim_s"],
                "exec_wall_s": rep["_wall_s"], "nworld": rep["nworld"]})
        return errors, versions

    try:
        lease.create()
        print(f"[search] gpu slice {lease.id} up in {lease.create_s}s", flush=True)
        versions = None

        # --- iteration 0: broad uniform + the uncalibrated defaults as candidate 0
        pop = 170
        cands = [dict(DEFAULT_PARAMS)] + [
            {n: float(v) for n, v in zip(PARAM_NAMES, lo + (hi - lo) * rng.random(5))}
            for _ in range(pop - 1)]
        iterations.append({"iter": 0, "kind": "uniform", "n": len(cands), "chunks": []})
        errs, versions = gpu_score(cands)
        iterations[-1]["errors"] = errs
        i = min(range(len(errs)), key=lambda k: errs[k])
        best = {"err": errs[i], "params": cands[i]}
        n_done += len(cands)
        print(f"[search] iter 0 uniform {len(cands)} -> best {best['err']:.5f}", flush=True)

        # --- cross-entropy resample rounds around the elite
        centre = np.array([best["params"][n] for n in PARAM_NAMES])
        spread = (hi - lo) * 0.15
        it = 1
        while n_done < args.budget:
            if it == 4:
                break
            k = min(128, args.budget - n_done)
            pop_x = np.clip(centre + spread * rng.standard_normal((k, 5)), lo, hi)
            cands = [{n: float(v) for n, v in zip(PARAM_NAMES, row)} for row in pop_x]
            iterations.append({"iter": it, "kind": "cem", "centre": list(map(float, centre)),
                               "spread": list(map(float, spread)), "n": len(cands), "chunks": []})
            errs, _ = gpu_score(cands)
            iterations[-1]["errors"] = errs
            order = sorted(range(len(errs)), key=lambda k: errs[k])
            elite = max(4, k // 8)
            centres = np.array([[cands[j][n] for n in PARAM_NAMES] for j in order[:elite]])
            centre = centres.mean(axis=0)
            spread = np.maximum(centres.std(axis=0) * 1.5, (hi - lo) * 0.002)
            n_done += len(cands)
            if errs[order[0]] < best["err"]:
                best = {"err": errs[order[0]], "params": cands[order[0]]}
            print(f"[search] iter {it} cem {len(cands)} -> best-so-far {best['err']:.5f} "
                  f"(this round {errs[order[0]]:.5f})", flush=True)
            it += 1

        final = {n: round(float(best["params"][n]), 6) for n in PARAM_NAMES}
        cpu_train = error_of(final, scen["refs_train"], scen["ics_train"], scen["scale"])
        wall = time.time() - t_start
        print(f"[search] done: {n_done} candidates, best gpu train {best['err']:.5f}, "
              f"cpu re-score {cpu_train:.5f}, gpu sim {gpu_sim_s:.1f}s, wall {wall:.0f}s")
        print(f"[search] params: {json.dumps(final)}")

        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "params.json"), "w") as fh:
            json.dump(final, fh, indent=2)
            fh.write("\n")
        with open(os.path.join(args.out, "loop.json"), "w") as fh:
            json.dump({
                "seed": args.seed, "budget": args.budget, "evaluated": n_done,
                "best_train_err_gpu": round(best["err"], 6),
                "final_cpu_train_err": round(cpu_train, 6),
                "wall_s": round(wall, 1), "gpu_sim_s": round(gpu_sim_s, 2),
                "gpu_execs": n_eval_calls, "gpu_create_s": lease.create_s,
                "lease_versions": versions,
                "iterations": iterations,
            }, fh, indent=2)
            fh.write("\n")
        print(f"[search] wrote {args.out}/params.json and loop.json")
        return 0
    finally:
        lease.close()
        print(f"[search] lease {lease.id or '(already gone)'} destroyed and confirmed gone", flush=True)


if __name__ == "__main__":
    sys.exit(main())
