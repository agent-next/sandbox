#!/usr/bin/env python3
"""Judge for the rf-openems demo.

Grades a parameterised openEMS patch-antenna script. Exits 0 only when every
gate passes; prints one JSON verdict (and writes it with --json).

Gates (see SPEC.md):
  G1 parses + parameter block + simulate() present
  G2 physical-sanity ranges
  G3 artifact runs under 9-min wall limit, emits RESULT line + results JSON
     + raw openEMS port time series
  G4 |S11| <= -10 dB at 2.45 GHz
  G5 resonance within +/-2 % of 2.45 GHz
  G6 judge re-derives S11 from the raw port time series (anti-fake)
  G7 oracle: openEMS microstrip eeff vs Hammerstad-Jensen (<= 4 %)
  G8 convergence: spec must still hold at mesh_res*0.75
  G9 judge/ directory checksums unchanged
"""
import os, sys, json, time, hashlib, subprocess, shutil, tempfile, \
    py_compile, ast, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

REQUIRED_PARAMS = ["f_target_ghz", "er", "tanD", "sub_h", "patch_L",
                   "patch_W", "feed_inset", "mesh_res"]
SWEEP_LO_GHZ, SWEEP_HI_GHZ = 2.2, 2.7
PORT_R_OHM = 50.0


def sha256_tree(path):
    h = hashlib.sha256()
    for root, dirs, files in sorted(os.walk(path)):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for f in sorted(files):
            fp = os.path.join(root, f)
            h.update(fp.encode())
            with open(fp, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def parse_artifact(path):
    src = open(path).read()
    tree = ast.parse(src, filename=path)
    params, has_sim = {}, False
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                isinstance(node.targets[0], ast.Name) and \
                node.targets[0].id in REQUIRED_PARAMS and \
                isinstance(node.value, ast.Constant) and \
                isinstance(node.value.value, (int, float)) and \
                not isinstance(node.value.value, bool):
            params[node.targets[0].id] = float(node.value.value)
        if isinstance(node, ast.FunctionDef) and node.name == "simulate":
            has_sim = True
    return params, has_sim


def dft(t, val, freq):
    import numpy as np
    t = np.asarray(t); val = np.asarray(val)
    dt = t[1] - t[0]
    return np.array([2 * np.sum(val * np.exp(-2j * np.pi * f * t)) * dt
                     for f in freq])


def s11_from_raw(sim_dir, freqs_hz):
    """Judge's own S11 derivation from the raw openEMS port time series."""
    import numpy as np
    tu, ut = np.loadtxt(os.path.join(sim_dir, "port_ut_1"),
                        comments="%", unpack=True)
    ti, it = np.loadtxt(os.path.join(sim_dir, "port_it_1"),
                        comments="%", unpack=True)
    Uf = dft(tu, ut, freqs_hz)
    If = dft(ti, it, freqs_hz)
    uf_inc = 0.5 * (Uf + If * PORT_R_OHM)
    uf_ref = Uf - uf_inc
    return 20 * np.log10(np.abs(uf_ref / uf_inc) + 1e-15)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--json", default=None)
    ap.add_argument("--seed", type=int, default=42,
                    help="recorded only; the FDTD run is deterministic")
    ap.add_argument("--skip-convergence", action="store_true")
    ap.add_argument("--timeout", type=int, default=540)
    args = ap.parse_args()

    from oracle import ANTENNA_GATES as G, patch_resonance_ghz
    import numpy as np

    verdict = {"artifact": os.path.abspath(args.artifact), "seed": args.seed,
               "gates": [], "timing": {}}
    t0 = time.time()

    def add(name, ok, detail=""):
        verdict["gates"].append({"gate": name, "pass": bool(ok),
                                 "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    pre_hash = sha256_tree(HERE)

    # ---- G1 ------------------------------------------------------------
    try:
        py_compile.compile(args.artifact, doraise=True)
        params, has_sim = parse_artifact(args.artifact)
        missing = [p for p in REQUIRED_PARAMS if p not in params]
        ok = not missing and has_sim
        add("G1_syntax_and_params", ok,
            f"missing={missing} simulate={'found' if has_sim else 'absent'}")
        if not ok:
            return _finish(verdict, args, t0, pre_hash)
    except Exception as e:
        add("G1_syntax_and_params", False, repr(e))
        return _finish(verdict, args, t0, pre_hash)

    # ---- G2 ------------------------------------------------------------
    ok = (G["er_min"] <= params["er"] <= G["er_max"]
          and G["sub_h_min_mm"] <= params["sub_h"] <= G["sub_h_max_mm"]
          and G["patch_L_min_mm"] <= params["patch_L"] <= G["patch_L_max_mm"]
          and G["patch_W_min_mm"] <= params["patch_W"] <= G["patch_W_max_mm"]
          and 0.0 < params["feed_inset"] <= 0.45 * params["patch_L"]
          and G["mesh_res_min_mm"] <= params["mesh_res"] <= G["mesh_res_max_mm"])
    add("G2_physical_sanity", ok, json.dumps(params))
    if not ok:
        for g in ("G3_sim_runs", "G4_S11_at_target", "G5_resonance",
                  "G6_raw_crosscheck", "G7_oracle_msline", "G8_convergence"):
            add(g, False, "not run (G2 physical sanity failed)")
        return _finish(verdict, args, t0, pre_hash)

    # ---- G3: run the artifact ------------------------------------------
    workdir = tempfile.mkdtemp(prefix="rfjudge-")
    try:
        art = os.path.abspath(args.artifact)
        tr = time.time()
        proc = subprocess.run([sys.executable, art], capture_output=True,
                              text=True, timeout=args.timeout, cwd=workdir)
        verdict["timing"]["artifact_sim_s"] = round(time.time() - tr, 1)
        rj = os.path.join(workdir, "antenna_results.json")
        simdir = os.path.join(workdir, "oems_sim")
        results = json.load(open(rj)) if os.path.exists(rj) else {}
        freqs = results.get("freqs_GHz", [])
        raw_ok = os.path.exists(os.path.join(simdir, "port_ut_1")) and \
            os.path.exists(os.path.join(simdir, "port_it_1"))
        result_line = any(l.startswith("RESULT ") for l in
                          proc.stdout.splitlines())
        ok = (proc.returncode == 0 and raw_ok and result_line
              and len(freqs) >= 21
              and min(freqs) <= SWEEP_LO_GHZ + 1e-9
              and max(freqs) >= SWEEP_HI_GHZ - 1e-9)
        add("G3_sim_runs", ok,
            f"rc={proc.returncode} raw={'yes' if raw_ok else 'no'} "
            f"result_line={result_line} wall={verdict['timing']['artifact_sim_s']}s")
        if not ok:
            for g in ("G4_S11_at_target", "G5_resonance",
                      "G6_raw_crosscheck", "G7_oracle_msline",
                      "G8_convergence"):
                add(g, False, "not run (G3 failed)")
            return _finish(verdict, args, t0, pre_hash)
    except subprocess.TimeoutExpired:
        add("G3_sim_runs", False, f"timeout > {args.timeout} s")
        return _finish(verdict, args, t0, pre_hash)
    except Exception as e:
        add("G3_sim_runs", False, repr(e))
        return _finish(verdict, args, t0, pre_hash)

    freqs = np.asarray(results["freqs_GHz"], float)
    s11 = np.asarray(results["S11_dB"], float)
    s11_at = float(results["S11_dB_at_target"])
    f_res = float(results["f_res_GHz"])

    # ---- G4/G5 ---------------------------------------------------------
    add("G4_S11_at_target", s11_at <= G["s11_target_db"],
        f"S11={s11_at:.2f} dB (need <= {G['s11_target_db']})")
    add("G5_resonance",
        abs(f_res - G["f_target_ghz"]) / G["f_target_ghz"] <= G["f_res_tol"],
        f"f_res={f_res:.3f} GHz (+/-{G['f_res_tol']*100:.0f} %)")

    # quasi-static cross-check (informational detail, part of the gate):
    fr_qs = patch_resonance_ghz(params["patch_L"] * 1e-3, params["sub_h"] * 1e-3,
                                params["patch_W"] * 1e-3, params["er"])
    verdict["patch_quasistatic_GHz"] = round(fr_qs, 3)

    # ---- G6: re-derive S11 from raw port files --------------------------
    try:
        s11_j = s11_from_raw(simdir, freqs * 1e9)
        dmax = float(np.max(np.abs(s11_j - s11)))
        verdict["raw_crosscheck_maxdiff_db"] = round(dmax, 3)
        add("G6_raw_crosscheck", dmax <= G["crosscheck_tol_db"],
            f"max|S11_judge - S11_artifact| = {dmax:.2f} dB "
            f"(<= {G['crosscheck_tol_db']})")
    except Exception as e:
        add("G6_raw_crosscheck", False, repr(e))

    # ---- G7: oracle line ------------------------------------------------
    from verify_line import run_verification
    try:
        to = time.time()
        ov = run_verification()
        verdict["oracle"] = ov
        verdict["timing"]["oracle_s"] = round(time.time() - to, 1)
        add("G7_oracle_msline", ov["delta_pct"] <= G["eeff_tol"] * 100,
            f"eeff sim={ov['eeff_sim']:.3f} HJ={ov['eeff_HJ']:.3f} "
            f"delta={ov['delta_pct']:.2f} % (<= {G['eeff_tol']*100:.0f} %)")
    except Exception as e:
        add("G7_oracle_msline", False, repr(e))

    # ---- G8: convergence — re-run artifact's simulate() at finer mesh ---
    early_fail = not all(g["pass"] for g in verdict["gates"][:5])
    if args.skip_convergence:
        add("G8_convergence", True, "skipped (--skip-convergence)")
    elif early_fail:
        add("G8_convergence", False, "not run (earlier gates failed)")
    else:
        try:
            tc = time.time()
            spec = importlib.util.spec_from_file_location("artifact_mod", art)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            p2 = dict(params)
            p2["mesh_res"] = params["mesh_res"] * G["conv_mesh_factor"]
            cdir = tempfile.mkdtemp(prefix="rfconv-")
            r2 = mod.simulate(p2, os.path.join(cdir, "oems_sim"))
            verdict["timing"]["convergence_s"] = round(time.time() - tc, 1)
            s2 = np.asarray(r2["S11_dB"], float)
            f2 = np.asarray(r2["freqs_GHz"], float)
            s11_2 = float(s2[int(np.argmin(np.abs(f2 - G["f_target_ghz"])))])
            fres_2 = float(f2[int(np.nanargmin(s2))])
            dfres = abs(fres_2 - f_res) / f_res
            verdict["convergence"] = {
                "mesh_res_fine_mm": p2["mesh_res"],
                "S11_at_target_fine_dB": round(s11_2, 2),
                "f_res_fine_GHz": round(fres_2, 3),
                "f_res_shift_pct": round(dfres * 100, 2),
            }
            ok = (s11_2 <= G["s11_target_db"]
                  and dfres <= G["conv_fres_tol"])
            add("G8_convergence", ok,
                f"fine mesh: S11={s11_2:.2f} dB f_res={fres_2:.3f} GHz "
                f"(shift {dfres*100:.2f} % <= {G['conv_fres_tol']*100} %)")
        except Exception as e:
            add("G8_convergence", False, repr(e))

    return _finish(verdict, args, t0, pre_hash)


def _finish(verdict, args, t0, pre_hash=None):
    post_hash = sha256_tree(HERE)
    ok = post_hash == pre_hash if pre_hash else False
    verdict["gates"].append({"gate": "G9_judge_integrity", "pass": bool(ok),
                             "detail": "judge/ checksums stable"
                                       if ok else "judge/ tree changed!"})
    print(f"[{'PASS' if ok else 'FAIL'}] G9_judge_integrity", flush=True)
    verdict["all_pass"] = all(g["pass"] for g in verdict["gates"])
    verdict["timing"]["wall_s"] = round(time.time() - t0, 1)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(verdict, fh, indent=1, sort_keys=True)
    print(json.dumps(verdict, indent=1, sort_keys=True))
    return 0 if verdict["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
