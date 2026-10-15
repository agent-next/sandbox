#!/usr/bin/env python3
"""The demo's evaluate loop, run by the demo builder to PRODUCE examples/good/.

Imitates what the user's agent does: batches of candidates are scored in one
batched mujoco_warp run per chunk on a 4 GiB GPU slice (nworld = candidates x
6 train recordings). The judge metric is a narrow valley — a pointwise error
over an 8 ms-sampled contact transient, so the basin around a true fit is
~1e-4 wide in solref_tc — and population resampling or coarse-finite-
difference BFGS both stall in its outer basins (measured; see RECEIPT r2).

The search therefore exploits the rig's separability: the box and the arm
never touch, so {mu, solref_tc, solref_dr} move only the box channels and
{damping, armature} move only the arm channels (the GPU evaluator returns
per-signal errors for exactly this). Stages:

  1. uniform pre-sample on the total error;
  2. mu from a line scan on box_x (smooth, convex);
  3. (solref_tc, solref_dr) on the box_zdot channel: a dense solref_tc scan at
     the lowest damping ratio, then ridge tracking — for each next dr a narrow
     tc window around the previous best tc, since the valley's best tc drifts
     smoothly with dr;
  4. repeat mu and the ridge once at the improved point;
  5. (damping, armature) on the arm channels, coarse grid + zoom;
  6. joint polish on the total error: coordinate line scans until stall.

Every batch's scores are appended to examples/good/loop.json (the media
round turns it into loop.png). The resulting artifact is written to
examples/good/params.json.

    SIM_TUNER_PYTHON=~/.venvs/sim-tuner/bin/python \
    python3 cookbook/sim-tuner/tools/search.py [--seed 7] [--budget 4000]

Needs SBX_API_KEY (or E2B_API_KEY) with GPU access. Runs the judge venv
python so CPU errors of the incumbent can be watched locally (the incumbent
is only graded by the judge, not here). `--cpu` scores candidates on the CPU
oracle instead of a GPU slice — slower per batch but identical math, useful
when no slice is free; the loop.json records which engine produced it.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE = os.path.join(HERE, "..", "judge")
sys.path.insert(0, JUDGE)
sys.path.insert(0, os.path.expanduser("~/.venvs/sim-tuner/lib"))

from engine import (DEFAULT_PARAMS, PARAM_NAMES, PARAM_SPEC, RANGES,  # noqa: E402
                    error_of, gen_scenario, gpu_eval_chunks, gpu_eval_code,
                    simulate)
from _grade import GpuLease  # noqa: E402

GOOD_DIR = os.path.join(HERE, "..", "examples", "good")

BOX_X, BOX_ZDOT, ARM = (0,), (1, 2), (3, 4, 5, 6)


def group_err(sig_row, chs):
    """RMS error over one channel group from a per-signal error row."""
    vals = [sig_row[c] for c in chs]
    if not all(math.isfinite(v) for v in vals):
        return float("inf")
    return math.sqrt(sum(v * v for v in vals) / len(vals))


def cpu_scores(cands, scen):
    """Per-candidate (total err, per-signal err row) on the CPU oracle."""
    import numpy as np
    totals, sigs = [], []
    scale = scen["scale"]
    for c in cands:
        acc = np.zeros(7)
        for ref, ic in zip(scen["refs_train"], scen["ics_train"]):
            d = (simulate(c, ic) - ref) / scale
            acc += (d * d).sum(axis=0)
        n, nobs = len(scen["ics_train"]), len(ref)
        sig = np.sqrt(acc / (n * nobs))
        totals.append(float(np.sqrt(acc.sum() / (n * 7 * nobs))))
        sigs.append(sig)
    return totals, sigs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--budget", type=int, default=4000)
    ap.add_argument("--out", default=GOOD_DIR)
    ap.add_argument("--cpu", action="store_true",
                    help="score candidates on the CPU oracle, no GPU lease")
    args = ap.parse_args()

    import numpy as np

    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key and not args.cpu:
        print("export SBX_API_KEY (GPU access needed)", file=sys.stderr)
        return 2

    scen = gen_scenario(args.seed)
    lo = np.array([p[1] for p in PARAM_SPEC])
    hi = np.array([p[2] for p in PARAM_SPEC])
    rng = np.random.default_rng(args.seed - 3)
    t_start = time.time()

    lease = None if args.cpu else GpuLease(key)
    iterations = []
    n_done, n_eval_calls, gpu_sim_s = 0, 0, 0.0
    cur = dict(DEFAULT_PARAMS)
    best = {"err": float("inf"), "params": None}

    def gpu_score(cands, group):
        """Score candidates; returns (total errs, per-group objective errs)."""
        nonlocal n_eval_calls, gpu_sim_s
        if args.cpu:
            t0 = time.monotonic()
            totals, sigs = cpu_scores(cands, scen)
            iterations[-1]["chunks"].append({
                "engine": "cpu", "n": len(cands),
                "best_err": min((e for e in totals if math.isfinite(e)), default=None),
                "wall_s": round(time.monotonic() - t0, 2)})
            objs = totals if group == "all" else \
                [group_err(row, group) for row in sigs]
            return totals, objs, None
        totals, objs = [], []
        versions = None
        for chunk in gpu_eval_chunks(cands, scen["ics_train"]):
            rep = lease.exec(gpu_eval_code(chunk, scen["ics_train"],
                                           scen["refs_train"], scen["scale"]))
            n_eval_calls += 1
            gpu_sim_s += rep["sim_s"]
            tot = [float(e) for e in rep["err"]]
            totals.extend(tot)
            if group == "all":
                objs.extend(tot)
            else:
                objs.extend(group_err(row, group) for row in rep["sig_err"])
            iterations[-1]["chunks"].append({
                "n": len(chunk), "best_err": min((e for e in tot if math.isfinite(e)), default=None),
                "sim_s": rep["sim_s"], "exec_wall_s": rep["_wall_s"],
                "nworld": rep["nworld"], "finite": rep["finite"]})
            versions = rep.get("versions")
        return totals, objs, versions

    def run_scan(cands, kind, group):
        nonlocal n_done
        iterations.append({"iter": len(iterations), "kind": kind,
                           "group": list(group) if group != "all" else "all",
                           "n": len(cands), "chunks": []})
        totals, objs, versions = gpu_score(cands, group)
        n_done += len(cands)
        iterations[-1]["errors"] = [e if math.isfinite(e) else None for e in totals]
        iterations[-1]["obj"] = [e if math.isfinite(e) else None for e in objs]
        return totals, objs, versions

    def line_scan(name, grid, chs, kind):
        """1-D scan of one parameter around `cur` on channel group chs."""
        nonlocal best
        cands = []
        for v in grid:
            c = dict(cur)
            c[name] = float(v)
            cands.append(c)
        _, objs, _ = run_scan(cands, kind, chs)
        i = min(range(len(objs)), key=lambda k: objs[k])
        cur[name] = float(grid[i])
        return objs[i]

    def grid_scan(pts, chs, kind):
        """Cartesian grid of [(name, grid), ...]; returns best (obj, params)."""
        nonlocal best
        import itertools
        names = [n for n, _ in pts]
        grids = [g for _, g in pts]
        cands = []
        for combo in itertools.product(*grids):
            c = dict(cur)
            for nm, v in zip(names, combo):
                c[nm] = float(v)
            cands.append(c)
        _, objs, _ = run_scan(cands, kind, chs)
        i = min(range(len(objs)), key=lambda k: objs[k])
        for nm in names:
            cur[nm] = cands[i][nm]
        return objs[i]

    def update_best(totals, cands):
        for e, c in zip(totals, cands):
            if math.isfinite(e) and e < best["err"]:
                best["err"] = e
                best["params"] = {n: float(c[n]) for n in PARAM_NAMES}

    try:
        versions = None
        if lease is not None:
            lease.create()
            print(f"[search] gpu slice {lease.id} up in {lease.create_s}s", flush=True)

        # --- iter 0: broad uniform pre-sample on the total error
        pop = min(511, args.budget - 1)
        cands = [dict(DEFAULT_PARAMS)] + [
            {n: float(v) for n, v in zip(PARAM_NAMES, lo + (hi - lo) * rng.random(5))}
            for _ in range(pop)]
        totals, _, versions = run_scan(cands, "uniform", "all")
        update_best(totals, cands)
        i = min(range(len(totals)), key=lambda k: totals[k] if math.isfinite(totals[k]) else float("inf"))
        cur = {n: cands[i][n] for n in PARAM_NAMES}
        print(f"[search] uniform {len(cands)} -> best total {totals[i]:.4f}", flush=True)

        # --- box group: mu on box_x, then ridge-tracked (solref_tc, solref_dr)
        # on box_z/box_zdot. Two rounds; the second re-fits at the better point.
        for rnd in range(2):
            half_w = [None, 0.06][rnd]  # None: full range
            if half_w is None:
                grid = np.linspace(RANGES["mu"][0], RANGES["mu"][1], 41)
            else:
                grid = np.linspace(max(RANGES["mu"][0], cur["mu"] - half_w),
                                   min(RANGES["mu"][1], cur["mu"] + half_w), 21)
            e = line_scan("mu", grid, BOX_X, f"mu-scan-r{rnd}")
            print(f"[search] r{rnd} mu -> {cur['mu']:.4f} (box_x {e:.4f})", flush=True)

            drs = np.linspace(RANGES["solref_dr"][0], RANGES["solref_dr"][1], 11)
            # round 0: fresh full-range tc scan at the first dr (the incumbent
            # may be far off); round 1: warm-start tracking from the round-0 best
            prev_tc = cur["solref_tc"] if rnd else None
            ridge_best = (float("inf"), None)
            for dv in drs:
                if prev_tc is None:
                    tcs = np.linspace(*RANGES["solref_tc"], 301)
                else:
                    half = 5e-4 if rnd == 0 else 3e-4
                    tcs = np.linspace(max(RANGES["solref_tc"][0], prev_tc - half),
                                      min(RANGES["solref_tc"][1], prev_tc + half), 51)
                cands = [dict(cur, solref_tc=float(t), solref_dr=float(dv)) for t in tcs]
                totals, objs, _ = run_scan(cands, f"ridge-dr{dv:.2f}-r{rnd}", BOX_ZDOT)
                update_best(totals, cands)
                i = min(range(len(objs)), key=lambda k: objs[k])
                prev_tc = float(tcs[i])
                if objs[i] < ridge_best[0]:
                    ridge_best = (objs[i], (prev_tc, float(dv)))
            cur["solref_tc"], cur["solref_dr"] = ridge_best[1]
            print(f"[search] r{rnd} ridge -> tc {cur['solref_tc']:.5f} dr {cur['solref_dr']:.3f} "
                  f"(box_zdot {ridge_best[0]:.4f})", flush=True)

        # --- arm group: (damping, armature) grid + zoom on the arm channels
        e = grid_scan([("damping", np.linspace(*RANGES["damping"], 12)),
                       ("armature", np.linspace(*RANGES["armature"], 12))],
                      ARM, "arm-grid")
        print(f"[search] arm grid -> {cur['damping']:.4f}/{cur['armature']:.4f} ({e:.4f})", flush=True)
        e = grid_scan([("damping", np.linspace(max(0.02, cur["damping"] - 0.03),
                                               min(0.35, cur["damping"] + 0.03), 9)),
                       ("armature", np.linspace(max(0.005, cur["armature"] - 0.005),
                                                min(0.06, cur["armature"] + 0.005), 9))],
                      ARM, "arm-zoom")
        print(f"[search] arm zoom -> {cur['damping']:.4f}/{cur['armature']:.4f} ({e:.4f})", flush=True)

        # --- joint polish on the total error: coordinate line scans to stall
        widths = {"mu": 0.04, "solref_tc": 8e-5, "solref_dr": 0.10,
                  "damping": 0.08, "armature": 0.01}
        for rnd in range(4):
            before = error_of(cur, scen["refs_train"], scen["ics_train"], scen["scale"])
            for nm, w in widths.items():
                lo_, hi_ = RANGES[nm]
                grid = np.linspace(max(lo_, cur[nm] - w), min(hi_, cur[nm] + w), 11)
                cands = [dict(cur, **{nm: float(v)}) for v in grid]
                totals, objs, _ = run_scan(cands, f"polish-{nm}-r{rnd}", "all")
                update_best(totals, cands)
                i = min(range(len(objs)), key=lambda k: objs[k])
                cur[nm] = float(grid[i])
            after = error_of(cur, scen["refs_train"], scen["ics_train"], scen["scale"])
            print(f"[search] polish r{rnd}: cpu train {before:.4f} -> {after:.4f}", flush=True)
            if before - after < 2e-4:
                break

        # the judge scores on CPU MuJoCo; a final short CPU polish of the two
        # needle parameters removes any GPU/CPU engine offset in the incumbent
        for nm, w in (("solref_tc", 1e-4), ("solref_dr", 0.08)):
            lo_, hi_ = RANGES[nm]
            grid = np.linspace(max(lo_, cur[nm] - w), min(hi_, cur[nm] + w), 21)
            errs = [error_of(dict(cur, **{nm: float(v)}), scen["refs_train"],
                             scen["ics_train"], scen["scale"]) for v in grid]
            cur[nm] = float(grid[int(np.argmin(errs))])

        final = {n: round(float(cur[n]), 6) for n in PARAM_NAMES}
        cpu_train = error_of(final, scen["refs_train"], scen["ics_train"], scen["scale"])
        wall = time.time() - t_start
        print(f"[search] done: {n_done} candidates, best gpu train {best['err']:.5f}, "
              f"cpu incumbent {cpu_train:.5f}, gpu sim {gpu_sim_s:.1f}s, wall {wall:.0f}s")
        print(f"[search] params: {json.dumps(final)}")

        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "params.json"), "w") as fh:
            json.dump(final, fh, indent=2)
            fh.write("\n")
        with open(os.path.join(args.out, "loop.json"), "w") as fh:
            json.dump({
                "seed": args.seed, "budget": args.budget, "evaluated": n_done,
                "engine": "cpu" if args.cpu else "gpu",
                "best_train_err_gpu": round(best["err"], 6),
                "final_cpu_train_err": round(cpu_train, 6),
                "wall_s": round(wall, 1), "gpu_sim_s": round(gpu_sim_s, 2),
                "gpu_execs": n_eval_calls,
                "gpu_create_s": lease.create_s if lease else None,
                "lease_versions": versions,
                "iterations": iterations,
            }, fh, indent=2)
            fh.write("\n")
        print(f"[search] wrote {args.out}/params.json and loop.json")
        return 0
    finally:
        if lease is not None:
            lease.close()
            print(f"[search] lease {lease.id or '(already gone)'} destroyed and confirmed gone",
                  flush=True)


if __name__ == "__main__":
    sys.exit(main())
