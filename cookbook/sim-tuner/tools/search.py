#!/usr/bin/env python3
"""The demo's evaluate loop, run by the demo builder to PRODUCE examples/good/.

Imitates what the user's agent does: batches of candidates are scored in one
batched mujoco_warp run per chunk on a 4 GiB GPU slice (nworld = candidates x
6 train recordings). The loop is a broad uniform pre-sample (plus the
uncalibrated defaults as candidate 0) followed by BFGS descent with batched
finite-difference gradients — the valley around a genuine fit is narrow and
diagonal, and population resampling (CEM/DE) measurably stalls in its outer
basins while a quasi-Newton walk descends it. Every batch's scores are
appended to examples/good/loop.json (the media round turns it into
loop.png). The resulting artifact is written to examples/good/params.json.

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
        pop = min(511, args.budget - 1)
        cands = [dict(DEFAULT_PARAMS)] + [
            {n: float(v) for n, v in zip(PARAM_NAMES, lo + (hi - lo) * rng.random(5))}
            for _ in range(pop)]
        iterations.append({"iter": 0, "kind": "uniform", "n": len(cands), "chunks": []})
        errs, versions = gpu_score(cands)
        iterations[-1]["errors"] = errs
        order = sorted(range(len(errs)), key=lambda k: errs[k])
        pre_x = np.array([[c["mu"], c["solref_tc"], c["solref_dr"],
                           c["damping"], c["armature"]] for c in cands])
        pre_e = np.array(errs)
        best = {"err": errs[order[0]], "params": cands[order[0]]}
        n_done += len(cands)
        print(f"[search] iter 0 uniform {len(cands)} -> best {best['err']:.5f}", flush=True)

        # --- BFGS descent with batched finite-difference gradients, restarted
        # from the next-best uniform samples when a walk stalls. Two GPU calls
        # per iteration: one chunk with the 5 FD points for the gradient, one
        # chunk with 4 line-search step sizes evaluated at once.
        it = 1
        start_idx = 0
        while n_done < args.budget and start_idx < 4:
            x = pre_x[order[start_idx]].copy()
            fx = float(pre_e[order[start_idx]])
            eps = 0.03 * (hi - lo)
            I5 = np.eye(5)
            B = np.eye(5)
            stall = 0
            start_idx += 1
            while n_done + 14 <= args.budget and stall < 6 and it <= 400:
                # gradient chunk: forward differences at the current point
                cands = [{n: float(v) for n, v in zip(PARAM_NAMES, row)}
                         for row in (x + eps * I5)]
                iterations.append({"iter": it, "kind": "bfgs-grad", "at": list(map(float, x)),
                                   "start": start_idx, "n": len(cands), "chunks": []})
                gerrs, _ = gpu_score(cands)
                g = (np.array(gerrs) - fx) / eps
                n_done += len(cands)
                if not np.all(np.isfinite(g)) or float(g @ B @ g) <= 0:
                    eps = np.maximum(eps / 2.0, 1e-4 * (hi - lo))
                    stall += 1
                    it += 1
                    continue
                p = -(B @ g)
                # line-search chunk: four step sizes evaluated together
                alphas = np.array([1.0, 0.5, 0.25, 0.125])
                trials = np.clip(x + alphas[:, None] * p, lo, hi)
                cands = [{n: float(v) for n, v in zip(PARAM_NAMES, row)} for row in trials]
                iterations.append({"iter": it, "kind": "bfgs-line", "n": len(cands), "chunks": []})
                Terrs, _ = gpu_score(cands)
                n_done += len(cands)
                k = int(np.argmin(Terrs))
                if Terrs[k] < fx - 1e-9:
                    xt, ft = trials[k], float(Terrs[k])
                    # gradient at the accepted point (one more chunk)
                    cands = [{n: float(v) for n, v in zip(PARAM_NAMES, row)}
                             for row in (xt + eps * I5)]
                    iterations.append({"iter": it, "kind": "bfgs-grad2", "n": len(cands),
                                       "chunks": []})
                    g2errs, _ = gpu_score(cands)
                    gn = (np.array(g2errs) - ft) / eps
                    n_done += len(cands)
                    s, y = xt - x, gn - g
                    sy = float(s @ y)
                    if sy > 1e-12:
                        rho = 1.0 / sy
                        V = np.eye(5) - rho * np.outer(s, y)
                        B = V.T @ B @ V + rho * np.outer(s, s)
                    else:
                        B = np.eye(5)
                    x, fx = xt, ft
                    stall = 0
                    if fx < best["err"] - 1e-9:
                        best = {"err": fx,
                                "params": {n: float(v) for n, v in zip(PARAM_NAMES, x)}}
                    it += 1
                else:
                    stall += 1
                    eps = np.maximum(eps / 2.0, 1e-4 * (hi - lo))
                    B = np.eye(5)
                    it += 1
            print(f"[search] start {start_idx}: walk ended at {fx:.5f} "
                  f"(best {best['err']:.5f}, {n_done} evals)", flush=True)

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
