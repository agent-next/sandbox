#!/usr/bin/env python3
"""Generates known-bad artifacts by single-edit mutation of the good example.

Every mutant names the gate it is meant to trip (`targets` below): the
self-test only counts a kill when the verdict is parseable, non-passing,
and the *targeted* gate actually failed — so each entry is a negative
power test for its own gate, not just "some gate went red".

Usage:
    python judge/mutants.py generate   # write mutants into examples/bad/
    python judge/mutants.py list       # name + description
    python judge/mutants.py targets    # name<TAB>targeted gate
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = os.path.normpath(os.path.join(HERE, "..", "examples", "good",
                                     "antenna.py"))
BAD_DIR = os.path.normpath(os.path.join(HERE, "..", "examples", "bad"))

# fabricated results JSON written instead of running simulate()
_FAKE_SWEEP = ('    r = {"freqs_GHz": [2.2 + 0.01*i for i in range(51)],\n'
              '         "S11_dB": [-20.0]*51}')

# no antenna solver at all: fabricate the raw port time series so that the
# judge-side DFT lands a plausible S11 dip (G4/G5-bait), report matching
# scalars. Replaying cached files is the same hole — this is stronger:
# nothing real is ever copied OR simulated.
_REPLAY_MAIN = '''def main():
    import json
    p = dict(f_target_ghz=f_target_ghz, er=er, tanD=tanD, sub_h=sub_h,
             patch_L=patch_L, patch_W=patch_W, feed_inset=feed_inset,
             mesh_res=mesh_res)
    fr = np.linspace(2.2e9, 2.7e9, 51)
    s11_db = -4.0 - 14.0*np.exp(-((fr/1e9 - 2.44)/0.02)**2)
    gm = 10**(s11_db/20.0)
    U = np.ones(len(fr), dtype=complex)
    I = U*(1 - gm)/(1 + gm)/50.0
    t = np.arange(0, 100e-9, 20e-12)
    df = fr[1] - fr[0]
    ut = np.zeros(len(t)); it = np.zeros(len(t))
    for k, f in enumerate(fr):
        ut += np.real(U[k]*np.exp(2j*np.pi*f*t))*2*df
        it += np.real(I[k]*np.exp(2j*np.pi*f*t))*2*df
    os.makedirs("oems_sim", exist_ok=True)
    np.savetxt("oems_sim/port_ut_1", np.column_stack([t, ut]))
    np.savetxt("oems_sim/port_it_1", np.column_stack([t, it]))
    i_res = int(np.argmin(s11_db))
    i_tgt = int(np.argmin(np.abs(fr/1e9 - f_target_ghz)))
    out = dict(params=p, S11_dB_at_target=float(s11_db[i_tgt]),
               f_res_GHz=float(fr[i_res]/1e9),
               freqs_GHz=(fr/1e9).tolist(), S11_dB=s11_db.tolist())
    with open(os.path.abspath("antenna_results.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print("RESULT S11_dB_at_{:.2f}GHz={:.2f} f_res_GHz={:.3f}".format(
        f_target_ghz, out["S11_dB_at_target"], out["f_res_GHz"]))
'''


def _no_ground(s):
    return re.sub(r"^[ \t]*metal\.AddBox\(\[-sub_m[^#]*# ground\n",
                  "", s, flags=re.M)


def _lie_scalars(s):
    s = _no_ground(s)
    s = s.replace("S11_dB_at_target=float(s11[i_tgt])",
                  "S11_dB_at_target=-20.0")
    s = s.replace("f_res_GHz=float(fr[i_res])", "f_res_GHz=2.45")
    return s


def _replay_cached(s):
    return re.sub(r"(?s)def main\(\):.*?(?=\n\nif __name__)",
                  _REPLAY_MAIN, s)


def _fake_curve(s):
    return s.replace('S11_dB=r["S11_dB"]',
                     'S11_dB=[float(x) + 8.0 for x in r["S11_dB"]]')


def _oracle_tamper(s):
    return s.replace(
        "def main():\n    import json",
        "def main():\n    import json, glob as _glob\n"
        "    for _f in _glob.glob('/tmp/rfjudge-*/rfjudge-mods-*/oracle.py'"
        "):\n"
        "        open(_f, 'w').write('raise RuntimeError\\n')")


def _fine_geometry(s):
    return s.replace('    res = p["mesh_res"]',
                     '    res = p["mesh_res"]\n'
                     '    L = L * 1.25 if res < 1.0 else L')


def _fine_fabricated(s):
    return s.replace(
        '    f0 = p["f_target_ghz"] * 1e9',
        '    if p["mesh_res"] < 1.0:\n'
        '        return {"freqs_GHz": [2.2 + 0.01*i for i in range(51)],\n'
        '                "S11_dB": [-20.0]*51}\n'
        '    f0 = p["f_target_ghz"] * 1e9')


def _plant_pyc(s):
    return s.replace(
        "def main():\n    import json",
        "def main():\n"
        "    import json, marshal, importlib.util\n"
        "    _src = os.path.join(os.path.dirname(os.path.abspath(__file__)),\n"
        "                        '..', '..', 'judge', 'verify_line.py')\n"
        "    _pc = importlib.util.cache_from_source(_src)\n"
        "    _st = os.stat(_src)\n"
        "    _code = compile(\n"
        "        'def run_verification(**k):\\n'\n"
        "        '    return {\"eeff_sim\": 3.33, \"eeff_HJ\": 3.33, '\n"
        "        '\"delta_pct\": 0.0, \"freq_GHz\": 2.45, '\n"
        "        '\"phases_deg\": [0.0]*5, \"probes_mm\": [0.0]*5, '\n"
        "        '\"mesh_res_mm\": 1.0}\\n', _src, 'exec')\n"
        "    os.makedirs(os.path.dirname(_pc), exist_ok=True)\n"
        "    with open(_pc, 'wb') as _f:\n"
        "        _f.write(importlib.util.MAGIC_NUMBER + b'\\x00'*4\n"
        "                 + (int(_st.st_mtime) % 2**32).to_bytes(4, 'little')\n"
        "                 + (int(_st.st_size) % 2**32).to_bytes(4, 'little')\n"
        "                 + marshal.dumps(_code))\n"
        "    import json")


# (filename, targeted gate, human description, mutator(src)->src)
MUTANTS = [
    ("bad_nan_er.py", "G1_syntax_and_params",
     "permittivity set to NaN (parameter no longer a literal constant)",
     lambda s: re.sub(r"^er\s*=.*$", 'er           = float("nan")', s,
                      count=1, flags=re.M)),
    ("bad_substrate_er.py", "G2_physical_sanity",
     "wrong substrate permittivity (er=2.2, outside FR-4 sanity range)",
     lambda s: re.sub(r"^er\s*=.*$", "er           = 2.2", s,
                      count=1, flags=re.M)),
    ("bad_thick_substrate.py", "G2_physical_sanity",
     "substrate too thick (3.5 mm, outside the sanity range)",
     lambda s: re.sub(r"^sub_h\s*=.*$", "sub_h        = 3.5", s,
                      count=1, flags=re.M)),
    ("bad_coarse_mesh.py", "G2_physical_sanity",
     "mesh too coarse (mesh_res=2.4 mm, outside the sanity range)",
     lambda s: re.sub(r"^mesh_res\s*=.*$", "mesh_res     = 2.4", s,
                      count=1, flags=re.M)),
    ("bad_patch_length.py", "G5_resonance",
     "wrong patch length (22 mm moves the resonance to ~3.1 GHz)",
     lambda s: re.sub(r"^patch_L\s*=.*$", "patch_L      = 22.0", s,
                      count=1, flags=re.M)),
    ("bad_no_ground.py", "G4_S11_at_target",
     "ground-plane box deleted (no return path -> no patch resonance)",
     _no_ground),
    ("bad_feed_center.py", "G4_S11_at_target",
     "feed near the patch centre (a TM010 voltage node -> no match)",
     lambda s: re.sub(r"^feed_inset\s*=.*$", "feed_inset   = 12.0", s,
                      count=1, flags=re.M)),
    ("bad_no_result.py", "G3_sim_runs",
     "never runs the solver: writes a fabricated results JSON only",
     lambda s: s.replace(
         '    r = simulate(p, os.path.abspath("oems_sim"))', _FAKE_SWEEP)),
    ("bad_lie_scalars.py", "G3_sim_runs",
     "no ground plane (real ~-0.2 dB) but reports S11=-20 dB, f_res=2.45",
     _lie_scalars),
    ("bad_replay_cached.py", "G3_sim_runs",
     "replays fabricated port_ut_1/port_it_1 instead of simulating",
     _replay_cached),
    ("bad_fake_curve.py", "G6_raw_crosscheck",
     "real sim, but the reported S11 sweep is shifted +8 dB",
     _fake_curve),
    ("bad_oracle_tamper.py", "G7_oracle_msline",
     "overwrites the judge's private oracle.py copy mid-run",
     _oracle_tamper),
    ("bad_fine_geometry.py", "G8_convergence",
     "simulate() silently uses a 25%-longer patch at the fine mesh",
     _fine_geometry),
    ("bad_fine_fabricated.py", "G8_convergence",
     "fine-mesh call returns a canned curve without running the solver",
     _fine_fabricated),
    ("bad_plant_pyc.py", "G9_judge_integrity",
     "plants a forged .pyc for verify_line under judge/__pycache__",
     _plant_pyc),
]


def main():
    src = open(GOOD).read()
    os.makedirs(BAD_DIR, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for name, tgt, desc, _ in MUTANTS:
            print(f"{name:28s} [{tgt}] {desc}")
        return
    if len(sys.argv) > 1 and sys.argv[1] == "targets":
        for name, tgt, _, _ in MUTANTS:
            print(f"{name}\t{tgt}")
        return
    out = []
    for name, tgt, desc, fn in MUTANTS:
        dst = os.path.join(BAD_DIR, name)
        mutated = fn(src)
        if mutated == src:
            raise SystemExit(f"mutant {name}: mutation did not apply!")
        open(dst, "w").write(mutated)
        out.append(dst)
    print(f"generated {len(out)} mutants into {BAD_DIR}")


if __name__ == "__main__":
    main()
