#!/usr/bin/env python3
"""Judge for the rf-openems demo.

Grades a parameterised openEMS patch-antenna script. Exits 0 only when every
gate passes; prints one JSON verdict (and writes it with --json).

Exit codes: 0 = all gates passed; 1 = a gate failed;
2 = partial grade (--skip-convergence left G8 unrun and nothing else
failed — the verdict is explicitly incomplete, never a PASS).

Gates (see SPEC.md):
  G1 parses + parameter block + simulate() present
  G2 physical-sanity ranges
  G3 artifact runs under 9-min wall limit, emits RESULT line + results JSON
     on a *valid sweep grid* (strictly increasing, covering 2.2-2.7 GHz,
     >= 21 points) + raw openEMS port time series *written inside a
     recorded solver-run window and still matching the size+sha256 hashed
     at that Run's end*, and the reported scalars agree with the judge's
     own S11 derivation from those raw files
  G4 |S11| <= -10 dB at 2.45 GHz — computed on the judge-derived curve,
     sampled on the judge-owned frequency grid
  G5 resonance within +/-2 % of 2.45 GHz — judge grid
  G6 judge-derived S11 vs artifact-reported sweep (anti-fake), compared
     on the judge-owned grid
  G7 oracle: openEMS microstrip eeff vs Hammerstad-Jensen (<= 4 %)
  G8 convergence: spec must still hold at mesh_res*0.75 — re-derived from
     the fine-mesh raw port files on the judge grid, G4 and G5 rechecked
  G9 judge/ tree + the judge's executable module copy unchanged
"""
import os, sys, json, time, hashlib, subprocess, shutil, tempfile, \
    resource, ast

HERE = os.path.dirname(os.path.abspath(__file__))

REQUIRED_PARAMS = ["f_target_ghz", "er", "tanD", "sub_h", "patch_L",
                   "patch_W", "feed_inset", "mesh_res"]
SWEEP_LO_GHZ, SWEEP_HI_GHZ = 2.2, 2.7
PORT_R_OHM = 50.0
# The judge-owned frequency grid every acceptance value is derived on:
# fixed count and endpoints, independent of whatever grid the artifact's
# own sweep reports (that one is only a report, cross-checked in G6).
# 2.45 GHz is a node of this grid (i = 25 of 51), so G4 reads a sample,
# not an interpolation. N_JUDGE_GRID is also the minimum point count of
# an artifact sweep: any grid that covers 2.2-2.7 GHz with >= 51 points
# and is strictly increasing can be resampled onto this grid honestly.
N_JUDGE_GRID = 51
JUDGE_FREQS_GHZ = [SWEEP_LO_GHZ + (SWEEP_HI_GHZ - SWEEP_LO_GHZ) * i
                   / (N_JUDGE_GRID - 1) for i in range(N_JUDGE_GRID)]
JUDGE_FREQS_HZ = [f * 1e9 for f in JUDGE_FREQS_GHZ]
# coverage/monotonicity tolerance: a sweep endpoint within 1 kHz of the
# band edge counts as covering it (float round-trips of 2.2/2.7 GHz)
GRID_COVER_TOL_GHZ = 1e-6


def q(x, step):
    """Quantize a sim-derived number to the precision the toolchain
    reproduces run-to-run. openEMS is not bit-deterministic (its FP
    trajectory varies at ~1e-4 relative), so the verdict reports measured
    numbers on a grid coarser than the observed noise; gate *decisions*
    still use the raw values. This keeps two same-seed verdicts
    byte-identical (selftest determinism check)."""
    return round(round(float(x) / step) * step, 10)


def qtree(o):
    if isinstance(o, dict):
        return {k: qtree(v) for k, v in o.items()}
    if isinstance(o, list):
        return [qtree(v) for v in o]
    if isinstance(o, float):
        return q(o, QSTEP_DEFAULT)
    return o


QSTEP_DEFAULT = 0.01          # GHz / eeff / generic float reporting grid
Q_DB = 1.0                    # S11 dB reporting grid (observed noise ~0.1 dB)
Q_PCT = 0.1                   # percent reporting grid


def sha256_tree(path):
    """sha256 over every file in the judge tree — including __pycache__
    and *.pyc. Bytecode is executable input: an artifact that plants a
    forged .pyc mid-run must trip this gate even though the judge never
    imports it (modules are loaded from a private copy, see _isolate()).
    VERSIONS.txt is excluded because setup.sh regenerates it (possibly
    concurrently when several environments share one checkout)."""
    SKIP = {"VERSIONS.txt"}
    h = hashlib.sha256()
    for root, dirs, files in sorted(os.walk(path)):
        dirs[:] = sorted(dirs)
        for f in sorted(files):
            if f in SKIP:
                continue
            fp = os.path.join(root, f)
            h.update(fp.encode())
            with open(fp, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


# --------------------------------------------------------------------------
# judge module isolation
#
# The artifact shares this filesystem while it runs: it can write into
# judge/ (plant a forged __pycache__/*.pyc or a shadowing module) and
# CPython would happily execute a well-forged cache entry. So before any
# judge helper is imported, the judge copies its *.py into a private
# directory, swaps sys.path's judge/ entry for that copy, and disables
# bytecode everywhere (sys.dont_write_bytecode + `-B` +
# PYTHONDONTWRITEBYTECODE on every subprocess). The private copy is
# re-hashed before each lazy import — tampering with it fails the gate.
# --------------------------------------------------------------------------
_JMOD = None
_JMOD_SHA = {}


def _isolate():
    global _JMOD, _JMOD_SHA
    _JMOD = tempfile.mkdtemp(prefix="rfjudge-mods-")
    for f in sorted(os.listdir(HERE)):
        if f.endswith(".py"):
            dst = os.path.join(_JMOD, f)
            shutil.copy2(os.path.join(HERE, f), dst)
            _JMOD_SHA[f] = _sha256(dst)
    sys.path[:] = [_JMOD if os.path.abspath(p or os.getcwd()) == HERE
                   else p for p in sys.path]
    if _JMOD not in sys.path:
        sys.path.insert(0, _JMOD)
    sys.dont_write_bytecode = True


def jmod_intact():
    """The judge's executable module copy is unchanged."""
    try:
        return sorted(os.listdir(_JMOD)) == sorted(_JMOD_SHA) and all(
            _sha256(os.path.join(_JMOD, f)) == s
            for f, s in _JMOD_SHA.items())
    except OSError:
        return False


# --------------------------------------------------------------------------
# solver-run provenance
#
# The artifact's processes run under a judge-written runner that wraps
# openEMS' FDTD.Run and journals every solver invocation (one JSON line:
# sim_path, start/end, ok, and the size+sha256 of port_ut_1/port_it_1
# hashed at the very end of Run). The journal fd is created and unlinked
# by the judge *before* the child starts: the artifact cannot discover
# the journal path from argv/env/cwd, cannot forge entries by writing
# fdtd_runs.jsonl in its workdir, and cannot edit the unlinked inode
# through any path. A raw port file only counts if (a) it was written
# inside a recorded run window of the matching sim_path and (b) its
# bytes still match the sha256 recorded at that Run's end — so replacing
# the files any time after Run returns fails provenance regardless of
# timestamps. The child's CPU time is checked too: a real FDTD solve
# burns orders of magnitude more CPU than a file copy. Residual threats
# are stated in SPEC.md ("Threat model"): in-process hook patching /
# ptrace of the child by the artifact.
# --------------------------------------------------------------------------
PORT_BASENAMES = ("port_ut_1", "port_it_1")

RUNNER = '''\
import sys, os, json, time, runpy, importlib.util, hashlib
jfd, mode, art = int(sys.argv[1]), sys.argv[2], sys.argv[3]
import numpy as _np
for _a, _v in (("float", float), ("int", int), ("bool", bool)):
    if not hasattr(_np, _a):
        setattr(_np, _a, _v)
import openEMS as _pkg
_submod = sys.modules.get("openEMS.openEMS")   # may be shadowed by the class
# openEMS.openEMS is a SWIG type: immutable, so patch by subclassing it and
# rebinding the names the artifact can reach (openEMS.openEMS and
# openEMS.openEMS.openEMS). Anything that bypasses both names simply leaves
# no journal entry -> provenance fails.
class _JFDTD(_pkg.openEMS):
    def Run(self, sim_path, **kw):
        t0 = time.time(); ok = True
        try:
            return super().Run(sim_path, **kw)
        except Exception:
            ok = False
            raise
        finally:
            ent = {"sim_path": os.path.abspath(sim_path),
                   "t0": t0, "t1": time.time(), "ok": ok,
                   "ports": {}}
            for _b in ("port_ut_1", "port_it_1"):
                _p = os.path.join(sim_path, _b)
                try:
                    with open(_p, "rb") as _f:
                        _d = _f.read()
                    ent["ports"][_b] = [len(_d),
                                       hashlib.sha256(_d).hexdigest()]
                except OSError:
                    pass
            _line = (json.dumps(ent) + "\\n").encode()
            while _line:
                _line = _line[os.write(jfd, _line):]

_pkg.openEMS = _JFDTD
if _submod is not None and getattr(_submod, "openEMS", None) is not _JFDTD:
    try:
        _submod.openEMS = _JFDTD
    except (TypeError, AttributeError):
        pass

if mode == "main":
    sys.argv = [art]
    runpy.run_path(art, run_name="__main__")
else:                                   # "sim": call simulate(p, dir)
    spec = importlib.util.spec_from_file_location("artifact_mod", art)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    r = mod.simulate(json.loads(sys.argv[4]), sys.argv[5])
    json.dump({"S11_dB": [float(x) for x in r["S11_dB"]],
               "freqs_GHz": [float(x) for x in r["freqs_GHz"]]},
              open(sys.argv[6], "w"))
'''


def _child_cpu():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


def _read_runs(journal):
    return journal.entries()


def provenance(simdir, journal, slack):
    """(ok, detail): the raw port files exist, were written inside a
    recorded openEMS Run of simdir, and their bytes still match the
    size+sha256 hashed at the end of that Run. slack only covers
    CalcPort's post-Run DFT writes falling inside the run window; it can
    no longer be used to smuggle in post-Run replacements, because the
    content hash is what decides, not the timestamp."""
    pu = os.path.join(simdir, "port_ut_1")
    pi = os.path.join(simdir, "port_it_1")
    if not (os.path.isfile(pu) and os.path.isfile(pi)):
        return False, "port_ut_1/port_it_1 missing"
    runs = [r for r in _read_runs(journal)
            if r.get("ok") and
            os.path.abspath(str(r.get("sim_path", ""))) ==
            os.path.abspath(simdir) and r.get("ports")]
    if not runs:
        return False, "no recorded solver run wrote to simdir"
    for p in (pu, pi):
        nm = os.path.basename(p)
        hashed = [r for r in runs if r["ports"].get(nm)]
        if not hashed:
            return False, f"{nm} not hashed by any recorded solver run"
        mt = os.path.getmtime(p)
        if not any(r["t0"] - slack <= mt <= r["t1"] + slack for r in hashed):
            return False, f"{nm} written outside the solver-run window"
        try:
            size, sha = os.path.getsize(p), _sha256(p)
        except OSError:
            return False, f"{nm} unreadable"
        if not any(r["ports"][nm] == [size, sha] for r in hashed):
            return False, (f"{nm} no longer matches the sha256 recorded "
                           "at the end of the solver run (replaced after "
                           "Run?)")
    return True, ""


def parse_artifact(path):
    src = open(path).read()
    compile(src, path, "exec")          # syntax check without a .pyc
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


def _valid_sweep(freqs, s11):
    """(ok, detail): the reported sweep grid can stand in for the judge
    grid — strictly increasing, covering 2.2-2.7 GHz, >= N_JUDGE_GRID
    points, S11 array of the same length. Count/extrema alone are not
    enough: a reordered or gappy sweep makes interpolated acceptance
    values (G4/G6/G8, and the G3 scalar check) meaningless."""
    import numpy as np
    freqs = np.asarray(freqs, float)
    if len(freqs) != len(s11):
        return False, f"sweep length mismatch ({len(freqs)} freqs, " \
                      f"{len(s11)} S11 values)"
    if len(freqs) < N_JUDGE_GRID:
        return False, f"sweep has {len(freqs)} points, need >= {N_JUDGE_GRID}"
    if np.any(np.diff(freqs) <= 0):
        return False, "sweep frequencies not strictly increasing (reordered?)"
    if freqs[0] > SWEEP_LO_GHZ + GRID_COVER_TOL_GHZ or \
            freqs[-1] < SWEEP_HI_GHZ - GRID_COVER_TOL_GHZ:
        return False, (f"sweep {freqs[0]:.4f}-{freqs[-1]:.4f} GHz does not "
                       f"cover {SWEEP_LO_GHZ}-{SWEEP_HI_GHZ} GHz")
    return True, ""


class RunJournal:
    """The solver-run journal, held open by an unlinked fd.

    The judge creates the journal file and unlinks it before the child
    starts; the child receives only the open descriptor (pass_fds).
    The artifact cannot discover the journal path (argv/env/cwd carry
    nothing about it), cannot forge entries by writing fdtd_runs.jsonl
    in its workdir, and cannot edit the unlinked inode through any path.
    The judge reads the entries back through its own duplicated fd."""

    def __init__(self):
        path = os.path.join(tempfile.mkdtemp(prefix="rfjournal-"),
                            "fdtd_runs.jsonl")
        self._fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_APPEND,
                           0o600)
        os.unlink(path)
        os.rmdir(os.path.dirname(path))

    def fd_for_child(self):
        return self._fd

    def entries(self):
        os.lseek(self._fd, 0, os.SEEK_SET)
        data = os.read(self._fd, 1 << 24)
        out = []
        for line in data.decode().splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
        return out

    def close(self):
        os.close(self._fd)


def run_artifact(mode, workdir, art, args, extra_argv, journal):
    """Run the artifact under the provenance runner. Returns
    (proc, child_cpu_seconds) — raises on timeout."""
    runner = os.path.join(workdir, "_jrunner.py")
    with open(runner, "w") as fh:
        fh.write(RUNNER)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cpu0 = _child_cpu()
    proc = subprocess.run(
        [sys.executable, "-B", runner, str(journal.fd_for_child()), mode,
         art] + extra_argv,
        capture_output=True, text=True, timeout=args.timeout,
        cwd=workdir, env=env, pass_fds=(journal.fd_for_child(),))
    return proc, _child_cpu() - cpu0


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--json", default=None)
    ap.add_argument("--seed", type=int, default=42,
                    help="recorded only; the FDTD run is deterministic")
    ap.add_argument("--skip-convergence", action="store_true")
    ap.add_argument("--timeout", type=int, default=540,
                    help="wall limit for the artifact's own run (G3)")
    ap.add_argument("--conv-timeout", type=int, default=1200,
                    help="wall limit for the judge's own fine-mesh re-run "
                         "(G8); the finer mesh needs roughly 2x the cells")
    ap.add_argument("--trace", default=None,
                    help="DIR to write trace CSV files: s11_artifact.csv "
                         "(artifact's reported S11 sweep), s11_judge.csv "
                         "(judge's own re-derivation from raw port files), "
                         "s11_fine.csv (G8 fine-mesh sweep)")
    args = ap.parse_args()

    _isolate()
    from oracle import ANTENNA_GATES as G, patch_resonance_ghz
    import numpy as np

    verdict = {"artifact": os.path.abspath(args.artifact), "seed": args.seed,
               "gates": [], "timing": {}}
    t0 = time.time()

    def add(name, ok, detail=""):
        verdict["gates"].append({"gate": name, "pass": bool(ok),
                                 "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    def bail(skip_from):
        for g in skip_from:
            add(g, False, "not run (earlier gates failed)")
        return _finish(verdict, args, t0, pre_hash)

    DOWNSTREAM = ("G4_S11_at_target", "G5_resonance", "G6_raw_crosscheck",
                  "G7_oracle_msline", "G8_convergence")

    # The judge never writes bytecode (PYTHONDONTWRITEBYTECODE) and never
    # imports from judge/ (private copy), so any .pyc here is left over
    # from an earlier artifact's plant. Drop it, or a re-plant of the same
    # bytes would leave the tree hash unchanged and pass G9.
    for root, dirs, files in os.walk(HERE):
        for d in [d for d in dirs if d == "__pycache__"]:
            shutil.rmtree(os.path.join(root, d))
            dirs.remove(d)
        for f in files:
            if f.endswith(".pyc"):
                os.remove(os.path.join(root, f))
    pre_hash = sha256_tree(HERE)

    # ---- G1 ------------------------------------------------------------
    try:
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
        return bail(("G3_sim_runs",) + DOWNSTREAM)

    # ---- G3: run the artifact (provenance-checked) ----------------------
    workdir = tempfile.mkdtemp(prefix="rfjudge-run-")
    simdir = os.path.join(workdir, "oems_sim")
    journal = RunJournal()
    s11_j = f_res_j = s11_at_j = None
    try:
        art = os.path.abspath(args.artifact)
        tr = time.time()
        proc, sim_cpu = run_artifact("main", workdir, art, args, [],
                                     journal)
        verdict["timing"]["artifact_sim_s"] = round(time.time() - tr, 1)
        rj = os.path.join(workdir, "antenna_results.json")
        results = json.load(open(rj)) if os.path.exists(rj) else {}
        freqs = results.get("freqs_GHz", [])
        result_line = any(l.startswith("RESULT ") for l in
                          proc.stdout.splitlines())
        try:
            freqs_a = np.asarray(results["freqs_GHz"], float)
            s11_a = np.asarray(results["S11_dB"], float)
            s11_at = float(results["S11_dB_at_target"])
            f_res = float(results["f_res_GHz"])
            fields_ok = True
        except (KeyError, TypeError, ValueError):
            fields_ok = False
        # sweep-grid check: the artifact's grid must be a valid basis for
        # every interpolated acceptance value (G4/G6/G8, G3 scalars)
        if fields_ok:
            grid_ok, grid_msg = _valid_sweep(freqs_a, s11_a)
        else:
            grid_ok, grid_msg = False, "sweep fields missing/malformed"
        prov_ok, prov_msg = provenance(simdir, journal,
                                       G["provenance_slack_s"])
        if prov_ok and sim_cpu < G["min_sim_cpu_s"]:
            prov_ok, prov_msg = False, \
                f"child burned {sim_cpu:.1f} CPU-s, no real solve"
        scal_msg = ""
        if prov_ok and grid_ok:
            try:
                # S11 is re-derived on the judge-owned grid: the artifact
                # controls neither the frequencies acceptance values are
                # computed at nor their ordering/coverage
                s11_j = s11_from_raw(simdir, JUDGE_FREQS_HZ)
                f_res_j = float(JUDGE_FREQS_GHZ[int(np.nanargmin(s11_j))])
                s11_at_j = float(s11_from_raw(
                    simdir, [G["f_target_ghz"] * 1e9])[0])
                scal_msg = (f"reported S11={q(s11_at, Q_DB)} dB/"
                            f"f_res={q(f_res, QSTEP_DEFAULT)} GHz vs "
                            f"judge {q(s11_at_j, Q_DB)} dB/"
                            f"{q(f_res_j, QSTEP_DEFAULT)} GHz")
            except Exception as e:
                prov_ok, prov_msg = False, f"raw port files unreadable: {e!r}"
        scal_ok = s11_j is not None and (
            abs(s11_at - s11_at_j) <= G["scalar_s11_tol_db"] and
            abs(f_res - f_res_j) <= G["scalar_fres_tol_ghz"])
        ok = (proc.returncode == 0 and prov_ok and result_line
              and fields_ok and grid_ok and scal_ok)
        add("G3_sim_runs", ok,
            f"rc={proc.returncode} raw={'yes' if prov_ok else 'no:' + prov_msg} "
            f"result_line={result_line}"
            + ("" if fields_ok else " fields=missing/malformed")
            + ("" if grid_ok else " sweep_grid:" + grid_msg)
            + ("" if scal_ok or s11_j is None else
               " scalars-disagree:" + scal_msg))
        if not ok:
            return bail(DOWNSTREAM)
    except subprocess.TimeoutExpired:
        add("G3_sim_runs", False, f"timeout > {args.timeout} s")
        return bail(DOWNSTREAM)
    except Exception as e:
        add("G3_sim_runs", False, repr(e))
        return bail(DOWNSTREAM)
    finally:
        journal.close()

    # trace: S11 curve of the artifact's own reported sweep (G3 output).
    # Caller gives each run its own DIR (fixed filenames inside), so
    # make_data.sh can keep one trace set per graded artifact.
    if args.trace:
        os.makedirs(args.trace, exist_ok=True)
        with open(os.path.join(args.trace, "s11_artifact.csv"), "w") as f:
            f.write("freq_ghz,s11_db\n")
            for fq, s in zip(results["freqs_GHz"], results["S11_dB"]):
                f.write(f"{fq:.4f},{s:.2f}\n")

    # ---- G4/G5: computed on the judge-derived curve, judge grid ----------
    # The artifact's reported scalars are never trusted: G4/G5 act on the
    # S11 the judge re-derived from the provenance-checked raw port files
    # on the judge-owned frequency grid (the scalar-agreement part of G3
    # already pinned the report to it).
    add("G4_S11_at_target", s11_at_j <= G["s11_target_db"],
        f"S11={q(s11_at_j, Q_DB)} dB at {G['f_target_ghz']} GHz "
        f"(judge-derived on the judge grid, "
        f"need <= {G['s11_target_db']})")
    add("G5_resonance",
        abs(f_res_j - G["f_target_ghz"]) / G["f_target_ghz"] <= G["f_res_tol"],
        f"f_res={q(f_res_j, QSTEP_DEFAULT)} GHz (judge grid, "
        f"+/-{G['f_res_tol']*100:.0f} %)")

    # quasi-static cross-check (informational detail, part of the gate):
    fr_qs = patch_resonance_ghz(params["patch_L"] * 1e-3, params["sub_h"] * 1e-3,
                                params["patch_W"] * 1e-3, params["er"])
    verdict["patch_quasistatic_GHz"] = round(fr_qs, 3)

    # ---- G6: judge-derived vs artifact-reported sweep, judge grid ------
    # Both curves are compared on the judge-owned grid: the artifact's
    # sweep (already validated strictly increasing + covering) is
    # interpolated onto it, so a reordered or gappy sweep cannot move
    # its samples out from under the comparison.
    try:
        s11_a_on_j = np.interp(JUDGE_FREQS_GHZ, freqs_a, s11_a)
        dmax = float(np.max(np.abs(s11_j - s11_a_on_j)))
        verdict["raw_crosscheck_maxdiff_db"] = q(dmax, Q_DB)
        if args.trace:
            with open(os.path.join(args.trace, "s11_judge.csv"), "w") as f:
                f.write("freq_ghz,s11_db\n")
                for fq, s in zip(JUDGE_FREQS_GHZ, s11_j):
                    f.write(f"{fq:.4f},{s:.1f}\n")
        add("G6_raw_crosscheck", dmax <= G["crosscheck_tol_db"],
            f"max|S11_judge - S11_artifact| = {q(dmax, Q_DB)} dB "
            f"on the judge grid (<= {G['crosscheck_tol_db']})")
    except Exception as e:
        add("G6_raw_crosscheck", False, repr(e))

    # ---- G7: oracle line ------------------------------------------------
    try:
        if not jmod_intact():
            raise RuntimeError("judge helper modules changed mid-run "
                               "(tamper attempt)")
        from verify_line import run_verification
        to = time.time()
        ov = run_verification()
        verdict["oracle"] = {
            "eeff_sim": q(ov["eeff_sim"], QSTEP_DEFAULT),
            "eeff_HJ": q(ov["eeff_HJ"], QSTEP_DEFAULT),
            "delta_pct": q(ov["delta_pct"], Q_PCT),
            "freq_GHz": q(ov["freq_GHz"], QSTEP_DEFAULT),
            "phases_deg": [q(p, 1.0) for p in ov["phases_deg"]],
            "probes_mm": ov["probes_mm"], "mesh_res_mm": ov["mesh_res_mm"],
        }
        verdict["timing"]["oracle_s"] = round(time.time() - to, 1)
        add("G7_oracle_msline", ov["delta_pct"] <= G["eeff_tol"] * 100,
            f"eeff sim={verdict['oracle']['eeff_sim']} "
            f"HJ={verdict['oracle']['eeff_HJ']} "
            f"delta={verdict['oracle']['delta_pct']} % "
            f"(<= {G['eeff_tol']*100:.0f} %)")
    except Exception as e:
        add("G7_oracle_msline", False, repr(e))

    # ---- G8: convergence — re-run artifact's simulate() at finer mesh ---
    if args.skip_convergence:
        add("G8_convergence", False,
            "not run (--skip-convergence): verdict is a partial grade")
    elif not all(g["pass"] for g in verdict["gates"]):
        add("G8_convergence", False, "not run (earlier gates failed)")
    else:
        journal2 = RunJournal()
        try:
            tc = time.time()
            p2 = dict(params)
            p2["mesh_res"] = params["mesh_res"] * G["conv_mesh_factor"]
            cdir = tempfile.mkdtemp(prefix="rfconv-")
            simdir2 = os.path.join(cdir, "oems_sim")
            out2 = os.path.join(cdir, "fine.json")
            # the artifact's simulate() runs in its own process under the
            # same provenance runner: no solver run -> no raw files -> fail
            cargs = argparse.Namespace(timeout=args.conv_timeout)
            pr, cpu2 = run_artifact(
                "sim", cdir, art, cargs,
                [json.dumps(p2), simdir2, out2], journal2)
            if pr.returncode != 0 or not os.path.exists(out2):
                raise RuntimeError(f"fine-mesh run rc={pr.returncode}: "
                                   f"{(pr.stderr or '').strip()[-200:]}")
            prov_ok, prov_msg = provenance(simdir2, journal2,
                                           G["provenance_slack_s"])
            if not prov_ok or cpu2 < G["min_sim_cpu_s"]:
                raise RuntimeError(
                    "fine-mesh result not produced by a recorded solver "
                    f"run ({prov_msg}; cpu {cpu2:.1f} s) — a fabricated "
                    "return value cannot stand in for the refined sim")
            r2 = json.load(open(out2))
            verdict["timing"]["convergence_s"] = round(time.time() - tc, 1)
            f2 = np.asarray(r2["freqs_GHz"], float)
            s2 = np.asarray(r2["S11_dB"], float)
            grid_ok2, grid_msg2 = _valid_sweep(f2, s2)
            if not grid_ok2:
                raise RuntimeError(f"fine-mesh sweep grid invalid: "
                                   f"{grid_msg2}")
            # judge re-derives S11 from the fine-mesh raw port files on
            # the judge-owned grid; the returned array is only a report
            # and must agree with it there
            s11_fj = s11_from_raw(simdir2, JUDGE_FREQS_HZ)
            s2_on_j = np.interp(JUDGE_FREQS_GHZ, f2, s2)
            dmax_f = float(np.max(np.abs(s11_fj - s2_on_j)))
            if dmax_f > G["crosscheck_tol_db"]:
                raise RuntimeError(
                    f"fine-mesh report vs judge-derived raw: "
                    f"max diff {dmax_f:.2f} dB > {G['crosscheck_tol_db']}")
            s11_2 = float(s11_from_raw(simdir2,
                                       [G["f_target_ghz"] * 1e9])[0])
            fres_2 = float(JUDGE_FREQS_GHZ[int(np.nanargmin(s11_fj))])
            dfres = abs(fres_2 - f_res_j) / f_res_j
            band_ok = (abs(fres_2 - G["f_target_ghz"]) / G["f_target_ghz"]
                       <= G["f_res_tol"])
            s11_ok = s11_2 <= G["s11_target_db"]
            shift_ok = dfres <= G["conv_fres_tol"]
            verdict["convergence"] = {
                "mesh_res_fine_mm": q(p2["mesh_res"], QSTEP_DEFAULT),
                "S11_at_target_fine_dB": q(s11_2, Q_DB),
                "f_res_fine_GHz": q(fres_2, QSTEP_DEFAULT),
                "f_res_shift_pct": q(dfres * 100, Q_PCT),
                "f_res_fine_in_band": bool(band_ok),
            }
            if args.trace:
                with open(os.path.join(args.trace, "s11_fine.csv"),
                          "w") as f:
                    f.write("freq_ghz,s11_db\n")
                    for fq, s in zip(JUDGE_FREQS_GHZ, s11_fj):
                        f.write(f"{fq:.4f},{s:.1f}\n")
            ok = s11_ok and band_ok and shift_ok
            add("G8_convergence", ok,
                f"fine mesh: S11={verdict['convergence']['S11_at_target_fine_dB']} dB "
                f"f_res={verdict['convergence']['f_res_fine_GHz']} GHz "
                f"on the judge grid "
                f"(G4 {'ok' if s11_ok else 'FAIL'}, G5 band "
                f"{'ok' if band_ok else 'FAIL'}, shift "
                f"{verdict['convergence']['f_res_shift_pct']} % "
                f"<= {G['conv_fres_tol']*100} % "
                f"{'ok' if shift_ok else 'FAIL'})")
        except Exception as e:
            add("G8_convergence", False, repr(e))
        finally:
            journal2.close()

    return _finish(verdict, args, t0, pre_hash)


def _finish(verdict, args, t0, pre_hash=None):
    post_hash = sha256_tree(HERE)
    tree_ok = bool(pre_hash) and post_hash == pre_hash
    mods_ok = jmod_intact()
    ok = tree_ok and mods_ok
    detail = ("judge/ checksums stable" if ok else
              "judge/ tree changed!" if not tree_ok else
              "judge module copy tampered!")
    verdict["gates"].append({"gate": "G9_judge_integrity", "pass": bool(ok),
                             "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] G9_judge_integrity", flush=True)
    verdict["all_pass"] = all(g["pass"] for g in verdict["gates"])
    verdict["timing"]["wall_s"] = round(time.time() - t0, 1)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(verdict, fh, indent=1, sort_keys=True)
    print(json.dumps(verdict, indent=1, sort_keys=True))
    if verdict["all_pass"]:
        return 0
    # partial grade: only G8 is unrun via --skip-convergence
    if args.skip_convergence and all(
            g["pass"] or g["gate"] == "G8_convergence"
            for g in verdict["gates"]):
        return 2
    return 1


if __name__ == "__main__":
    tempfile.tempdir = tempfile.mkdtemp(prefix="rfjudge-")
    try:
        rc = main()
    finally:
        shutil.rmtree(tempfile.tempdir, ignore_errors=True)
    sys.exit(rc)
