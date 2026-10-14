#!/usr/bin/env python3
"""Judge: grade an antenna.py artifact.

Exits 0 only when every gate passes. Prints a JSON verdict to stdout (and
optionally to --json).
"""
import os, sys, json, time, hashlib, subprocess, shutil, tempfile, py_compile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.environ.setdefault("OMP_NUM_THREADS", "2")

REQUIRED_PARAMS = ["f_target_ghz", "er", "tanD", "patch_L", "patch_W", "sub_h",
                   "feed_inset", "line_L", "line_w", "resolution"]


def sha256_tree(path):
    h = hashlib.sha256()
    for root, _, files in sorted(os.walk(path)):
        for f in sorted(files):
            if f.endswith((".pyc", ".h5", ".json", ".out", ".log")) and \
               (root.endswith("__pycache__") or f in ("judge-run.json",)):
                continue
            if f == "judge-run.json":
                continue
            fp = os.path.join(root, f)
            h.update(fp.encode())
            h.update(open(fp, "rb").read())
    return h.hexdigest()


def gate(name, ok, detail=""):
    return {"gate": name, "pass": bool(ok), "detail": detail}


def parse_params(path):
    """Extract the numeric parameter block from the artifact."""
    import ast
    src = open(path).read()
    tree = ast.parse(src, filename=path)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
           isinstance(node.targets[0], ast.Name):
            n = node.targets[0].id
            if n in REQUIRED_PARAMS and isinstance(node.value, ast.Constant):
                out[n] = float(node.value.value) if isinstance(node.value.value, (int, float)) else None
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", help="path to antenna.py")
    ap.add_argument("--json", default=None)
    ap.add_argument("--seed", type=int, default=42, help="accepted for compat; physics is deterministic")
    ap.add_argument("--skip-convergence", action="store_true")
    args = ap.parse_args()

    from oracle import (ANTENNA_GATES as G, microstrip_hammerstad_jensen,
                        patch_resonance_ghz, Z0_50_WIDTH_MM, Z0_50_H_MM, Z0_50_ER)
    t0 = time.time()
    verdict = {"artifact": os.path.abspath(args.artifact), "gates": [], "t_start": time.time()}

    def add(name, ok, detail=""):
        verdict["gates"].append(gate(name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    # ---- G0: judge integrity baseline ------------------------------------ #
    pre_hash = sha256_tree(HERE)

    # ---- G1: parses + params exist --------------------------------------- #
    try:
        py_compile.compile(args.artifact, doraise=True)
        params = parse_params(args.artifact)
        missing = [p for p in REQUIRED_PARAMS if p not in params or params[p] is None]
        add("G1_syntax_and_params", not missing, f"missing={missing}")
    except Exception as e:
        add("G1_syntax_and_params", False, repr(e))
        _finish(verdict, args)
        return 1

    # ---- G2: physical sanity --------------------------------------------- #
    ok = (G["sub_h_min_mm"] <= params["sub_h"] <= G["sub_h_max_mm"]) and \
         (G["patch_L_min_mm"] <= params["patch_L"] <= G["patch_L_max_mm"]) and \
         (G["er_min"] <= params["er"] <= G["er_max"]) and \
         (G["resolution_min"] <= params["resolution"] <= G["resolution_max"])
    add("G2_physical_sanity", ok, json.dumps(params))

    # ---- G3: run the sim -------------------------------------------------- #
    workdir = tempfile.mkdtemp(prefix="rfjudge-")
    try:
        art = os.path.abspath(args.artifact)
        t_run0 = time.time()
        proc = subprocess.run(
            [sys.executable, art],
            capture_output=True, text=True, timeout=540, cwd=workdir)
        verdict["sim_wall_s"] = round(time.time() - t_run0, 1)
        rj = os.path.join(os.path.dirname(art), "antenna_results.json")
        if not os.path.exists(rj):
            rj = os.path.join(workdir, "antenna_results.json")
        results = json.load(open(rj))
        ok = proc.returncode == 0 and len(results.get("freqs_GHz", [])) >= 21 \
            and min(results["freqs_GHz"]) <= 2.2 and max(results["freqs_GHz"]) >= 2.7
        add("G3_sim_runs", ok, f"rc={proc.returncode} wall={verdict['sim_wall_s']}s")
    except subprocess.TimeoutExpired:
        add("G3_sim_runs", False, "timeout > 9 min")
        _finish(verdict, args); return 1
    except Exception as e:
        add("G3_sim_runs", False, repr(e))
        _finish(verdict, args); return 1

    # ---- G4 & G5: S11 target and resonance location ---------------------- #
    s11_at = float(results["S11_dB_at_target"])
    f_res = float(results["f_res_GHz"])
    add("G4_S11_at_target", s11_at <= G["s11_target_db"],
        f"S11={s11_at:.2f} dB (need ≤ {G['s11_target_db']})")
    add("G5_resonance", abs(f_res - G["f_target_ghz"]) / G["f_target_ghz"] <= G["f_res_tol"],
        f"f_res={f_res:.3f} GHz (2 % tol)")

    # ---- G6: independent analytic oracle --------------------------------- #
    from verify_line import run_verification
    t_o = time.time()
    ov = run_verification(resolution=int(params["resolution"]))
    verdict["oracle"] = ov
    verdict["oracle_wall_s"] = round(time.time() - t_o, 1)
    add("G6_oracle_msline", ov["delta_pct"] <= G["z0_tol"] * 100,
        f"eeff meep={ov['eeff_meep']:.4f} HJ={ov['eeff_HJ']:.4f} Δ={ov['delta_pct']:.2f}% (≤3 %)")
    # patch resonance quasi-static sanity (informational, loose)
    fr_qs = patch_resonance_ghz(params["patch_L"]*1e-3, params["sub_h"]*1e-3, params["er"])
    add("G6b_patch_quasistatic",
        abs(f_res - fr_qs) / fr_qs <= 0.10,
        f"MEEP f_res={f_res:.3f} GHz vs quasi-static {fr_qs:.3f} GHz (10 % tol)")

    # ---- G7: convergence (re-run at resolution+2) ------------------------- #
    if args.skip_convergence:
        add("G7_convergence", True, "skipped")
    else:
        import sim_engine
        t_c = time.time()
        p2 = dict(f_target_ghz=params["f_target_ghz"], er=params["er"], tanD=params["tanD"],
                  patch_L=params["patch_L"], patch_W=params["patch_W"], sub_h=params["sub_h"],
                  feed_inset=params["feed_inset"], line_L=params["line_L"], line_w=params["line_w"])
        r2 = sim_engine.simulate_antenna(p2, resolution=int(params["resolution"]) + 2)
        i2 = min(range(len(r2["freqs_ghz"])), key=lambda k: abs(r2["freqs_ghz"][k] - G["f_target_ghz"]))
        dS11 = abs(r2["s11_db"][i2] - s11_at)
        verdict["conv_wall_s"] = round(time.time() - t_c, 1)
        add("G7_convergence", dS11 <= G["s11_conv_delta_db"],
            f"ΔS11(res→res+2)={dS11:.2f} dB (≤ {G['s11_conv_delta_db']})")

    # ---- G8: judge not tampered ------------------------------------------ #
    post_hash = sha256_tree(HERE)
    add("G8_judge_integrity", pre_hash == post_hash, "judge/ checksums stable")

    _finish(verdict, args)
    return 0 if all(g["pass"] for g in verdict["gates"]) else 1


def _finish(verdict, args):
    verdict["all_pass"] = all(g["pass"] for g in verdict["gates"])
    verdict["wall_s"] = round(time.time() - verdict["t_start"], 1)
    verdict.pop("t_start", None)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(verdict, fh, indent=1)
    print(json.dumps(verdict, indent=1))
    shutil.rmtree(args._workdir if hasattr(args, "_workdir") else "/nonexistent", ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
