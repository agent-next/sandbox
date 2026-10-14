#!/usr/bin/env python3
"""Judge driver for the sim-engine-arena demo. Invoked by grade.sh; see SPEC.md.

Grades a copied artifact (the artifact under test never touches judge/):
  gate 1 structure   - size, byte-compile, mujoco-based, reads the spec at
                       runtime, no oracle literals hard-coded
  gate 2 run         - the artifact runs and writes all four CSVs
  gate 3 csv-shape   - headers, row counts, monotone t, finite values
  gate 4 oracle      - analytic scoring of each trajectory
  gate 5 agreement   - pointwise deviation vs the judge's reference port

Prints one JSON verdict on stdout; exit 0 only if every gate passes.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE_VENV_PY = os.path.join(os.path.expanduser("~"), ".venvs",
                             "sim-engine-arena", "bin", "python")

MAX_BYTES = 96 * 1024
RUN_TIMEOUT_S = 900

TOL = {"contact_time": 0.03, "accel": 0.05, "period": 0.02}
STICK_TRAVEL_M = 0.02
SLIDE_TRAVEL_M = 0.10
AGREE_SCALE = {"drop": 0.05, "incline_stick": 0.05, "incline_slide": 0.05,
               "pendulum": 0.02}   # 5% of per-scenario spatial scale


# ---------------------------------------------------------------- oracles

def oracle_values(spec):
    """Analytic oracle values, computed from the spec. Agents never see these."""
    g = spec["gravity"]
    drop = next(s for s in spec["scenarios"] if s["name"] == "drop")
    r, z0 = drop["body"]["radius"], drop["body"]["pos"][2]
    pen = next(s for s in spec["scenarios"] if s["name"] == "pendulum")
    L, th0 = pen["link"]["L_m"], pen["theta0_rad"]
    out = {"drop": {"t_contact": math.sqrt(2 * (z0 - r) / g), "r": r},
           "pendulum": {"period": 2 * math.pi * math.sqrt(L / g) * (1 + th0 ** 2 / 16)}}
    for name in ("incline_stick", "incline_slide"):
        sc = next(s for s in spec["scenarios"] if s["name"] == name)
        th = math.radians(sc["plane"]["tilt_deg"])
        mu = sc["plane"]["friction_mu"]
        out[name] = {"theta": th, "mu": mu, "expect_slide": math.tan(th) > mu,
                     "accel": g * (math.sin(th) - mu * math.cos(th))}
    return out


def _interp_cross(t0, v0, t1, v1):
    return t0 + (0.0 - v0) * (t1 - t0) / (v1 - v0) if v1 != v0 else t0


def _fit_accel(t, s):
    """Least squares s = c0 + c1 t + .5 a t^2 -> a. Tiny normal-equations solve."""
    n = len(t)
    if n < 5:
        return None
    S = [sum(u ** k for u in t) for k in range(5)]
    b = [sum(s), sum(ti * si for ti, si in zip(t, s)),
         sum(ti * ti * si for ti, si in zip(t, s)) / 2]
    A = [[S[0], S[1], S[2] / 2], [S[1], S[2], S[3] / 2], [S[2] / 2, S[3] / 2], ]
    A[2].append(S[4] / 4)
    for col in range(3):        # gaussian elimination with partial pivot
        piv = max(range(col, 3), key=lambda r2: abs(A[r2][col]))
        if abs(A[piv][col]) < 1e-12:
            return None
        A[col], A[piv] = A[piv], A[col]
        b[col], b[piv] = b[piv], b[col]
        for r2 in range(col + 1, 3):
            f = A[r2][col] / A[col][col]
            A[r2] = [a - f * a0 for a, a0 in zip(A[r2], A[col])]
            b[r2] -= f * b[col]
    try:
        return b[2] / A[2][2]
    except ZeroDivisionError:
        return None


def _finite(vals):
    return all(isinstance(v, float) and math.isfinite(v) for v in vals)


def analyze(name, rows, exp, spec):
    """rows: {col: [floats]} -> metrics dict. Raises ValueError on garbage."""
    t = rows["t"]
    if len(t) < 10 or not _finite(t):
        raise ValueError("too few rows or non-finite t")
    if name == "drop":
        z = rows["z"]
        r = exp["r"]
        if not _finite(z):
            raise ValueError("non-finite z")
        ic = next((i for i in range(1, len(t)) if z[i] <= r), None)
        if ic is None:
            raise ValueError("never contacts plane")
        tc = _interp_cross(t[ic - 1], z[ic - 1] - r, t[ic], z[ic] - r)
        err = abs(tc - exp["t_contact"]) / exp["t_contact"]
        return {"t_contact": tc, "t_contact_err": err,
                "penetration_m": max(0.0, r - min(z)),
                "rebound_m": max(0.0, max(z[ic:]) - r),
                "pass": err <= TOL["contact_time"]}
    if name.startswith("incline"):
        x, z = rows["x"], rows["z"]
        th = exp["theta"]
        ux, uz = math.cos(th), -math.sin(th)   # downhill unit vector
        s = [xi * ux + zi * uz for xi, zi in zip(x, z)]
        if not _finite(s):
            raise ValueError("non-finite position")
        s0 = s[0]
        s = [v - s0 for v in s]
        disp, end = max(abs(v) for v in s), abs(s[-1])
        if len(t) < 10 or t[1] - t[0] <= 0 or t[-1] - t[0] < 0.5:
            raise ValueError("degenerate t (need >=10 rows, increasing, >=0.5 s span)")
        k = min(len(s) - 1, max(2, int(0.05 / (t[1] - t[0]))))
        vend = abs(s[-1] - s[-k]) / (t[-1] - t[-k])
        moving = disp > SLIDE_TRAVEL_M or vend > 0.2
        stuck = disp < STICK_TRAVEL_M and vend < 0.05
        accel = None
        if moving:
            tail = [(ti, si) for ti, si in zip(t, s) if si > 0.05]
            if len(tail) >= 10:
                t0 = tail[0][0]
                accel = _fit_accel([u[0] - t0 for u in tail],
                                   [u[1] for u in tail])
        res = {"travel_m": disp, "end_m": end, "v_end": vend,
               "state": "slide" if moving else ("stick" if stuck else "ambiguous"),
               "accel": accel}
        if exp["expect_slide"]:
            res["accel_err"] = (abs(accel - exp["accel"]) / exp["accel"]
                                if accel is not None else None)
            res["pass"] = bool(moving and accel is not None
                               and res["accel_err"] <= TOL["accel"])
        else:
            res["pass"] = bool(stuck)
        return res
    if name == "pendulum":
        th = rows["theta"]
        if not _finite(th) or len(th) < 10:
            raise ValueError("too few or non-finite theta samples")
        center = sum(th) / len(th)
        up = [i for i in range(1, len(t)) if th[i - 1] < center <= th[i]]
        if len(up) < 2:
            raise ValueError("fewer than 2 upward zero crossings")
        tcross = [_interp_cross(t[i - 1], th[i - 1] - center, t[i], th[i] - center)
                  for i in up]
        period = sum(b - a for a, b in zip(tcross, tcross[1:])) / (len(tcross) - 1)
        err = abs(period - exp["period"]) / exp["period"]
        res = {"period": period, "period_err": err, "pass": err <= TOL["period"]}
        om = rows.get("omega")
        if om and _finite(om):
            L = spec_pendulum_L(spec)
            g = spec_pendulum_g(spec)
            e = [0.5 * (L * w) ** 2 + g * L * (1 - math.cos(a))
                 for a, w in zip(th, om)]
            res["energy_drift"] = (e[-1] - e[0]) / e[0] if e[0] else None
        return res
    raise ValueError(f"unknown scenario {name}")


def spec_pendulum_L(spec):
    return next(s for s in spec["scenarios"]
                if s["name"] == "pendulum")["link"]["L_m"]


def spec_pendulum_g(spec):
    return spec["gravity"]


# ------------------------------------------------------------ csv + agreement

def parse_traj(path):
    """Read a CSV into {col: [floats]}. Raises ValueError on malformed data."""
    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 5:
        raise ValueError("empty csv")
    hdr = rows[0]
    if any(h.strip() == "" for h in hdr):
        raise ValueError("empty column name")
    cols = {h: [] for h in hdr}
    for row in rows[1:]:
        if len(row) != len(hdr):
            continue
        try:
            vals = [float(v) for v in row]
        except ValueError:
            continue
        for h, v in zip(hdr, vals):
            cols[h].append(v)
    if any(len(v) < 5 for v in cols.values()):
        raise ValueError("too few numeric rows")
    return cols


def slope_coordinate(rows):
    th = math.radians(35.0)     # incline_slide tilt from the spec
    ux, uz = math.cos(th), -math.sin(th)
    return [x * ux + z * uz for x, z in zip(rows["x"], rows["z"])]


def agreement_metric(name, art_rows, ref_rows):
    """Max pointwise deviation on the shared columns, sampled per ms step.

    Both trajectories start at t=0 with the same dt, so index i pairs row
    i of each. Returns a float or None when the columns are missing.
    """
    if name == "drop":
        a, b = art_rows.get("z"), ref_rows.get("z")
    elif name.startswith("incline"):
        a, b = (slope_coordinate(art_rows), slope_coordinate(ref_rows))
    elif name == "pendulum":
        a, b = art_rows.get("theta"), ref_rows.get("theta")
    else:
        return None
    if not a or not b:
        return None
    n = min(len(a), len(b))
    if name == "pendulum":
        # phase-align by the first upward crossing of the mean-centered angle
        def first_cross(v):
            c = sum(v) / len(v)
            for i in range(1, len(v)):
                if v[i - 1] < c <= v[i]:
                    return i
            return 0
        da, db = first_cross(a), first_cross(b)
        n = min(n - da, len(b) - db)
        a, b = a[da:da + n], b[db:db + n]
    return max(abs(a[i] - b[i]) for i in range(n))


# ---------------------------------------------------------------- structure

NUM_RE = re.compile(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?")


def oracle_literals(spec, exp):
    """The four oracle numbers plus the raw scene constants an agent must
    not paste in as a result. Oracle values are formatted to 4 decimals
    and also matched numerically within 2 %."""
    vals = [exp["drop"]["t_contact"], exp["pendulum"]["period"]]
    for name in ("incline_stick", "incline_slide"):
        if exp[name]["expect_slide"]:
            vals.append(abs(exp[name]["accel"]))
    return vals


def hardcode_hits(text, vals):
    """Numeric literals in the artifact within 2 % of an oracle value.

    Only literals with a decimal point or exponent count: a bare `2` is an
    index or a count far more often than a faked period, and a faked
    trajectory is caught by the agreement gate against the reference port.
    """
    hits = []
    for m in NUM_RE.finditer(text):
        lit = m.group()
        if "." not in lit and "e" not in lit and "E" not in lit:
            continue
        try:
            v = float(lit)
        except ValueError:
            continue
        for ov in vals:
            if ov and abs(v - ov) / ov <= 0.02:
                hits.append({"literal": lit, "oracle": round(ov, 4)})
                break
    return hits


def load_artifact(path):
    with open(path, "rb") as fh:
        source = fh.read()
    if len(source) > MAX_BYTES:
        raise ValueError(f"artifact exceeds {MAX_BYTES // 1024} KiB")
    compile(source, path, "exec")       # gate 1 byte-compile, no import
    text = source.decode("utf-8", "replace")
    problems = []
    if "mujoco" not in text:
        problems.append("artifact does not use the mujoco package")
    if not re.search(r"spec\.json|spec\[|json\.load|json\.loads", text):
        problems.append("artifact does not read the spec at runtime")
    return text, problems


# ---------------------------------------------------------------- judge core

def check_shas(judge_dir):
    digests = {}
    for root, dirs, files in os.walk(judge_dir):
        dirs.sort()
        if os.path.basename(root) == "__pycache__":
            dirs[:] = []
            continue
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            p = os.path.join(root, name)
            with open(p, "rb") as fh:
                digests[os.path.relpath(p, judge_dir)] = \
                    hashlib.sha256(fh.read()).hexdigest()
    return digests


def run_artifact(art_path, workdir, spec_path, csv_dir):
    """Run the artifact from a copy in `workdir` with the spec in cwd."""
    shutil.copy(art_path, os.path.join(workdir, "sim.py"))
    shutil.copy(spec_path, os.path.join(workdir, "spec.json"))
    t0 = time.monotonic()
    proc = subprocess.run(
        [JUDGE_VENV_PY, "sim.py"], cwd=workdir, capture_output=True,
        text=True, timeout=RUN_TIMEOUT_S)
    wall = time.monotonic() - t0
    problems = []
    if proc.returncode != 0:
        problems.append(f"exit {proc.returncode}: "
                        + (proc.stderr or proc.stdout)[-300:])
    for sc in SPEC_SCEN:
        if not os.path.exists(os.path.join(csv_dir, sc["output"])):
            problems.append(f"missing {sc['output']}")
    return problems, wall, (proc.stdout or "") + (proc.stderr or "")


def csv_shape(name, rows, sc):
    problems = []
    want_hdr = sc["columns"]
    got_hdr = [c for c in rows.keys()]
    if got_hdr != want_hdr:
        problems.append(f"header {got_hdr} != spec columns {want_hdr}")
        return problems
    n = len(rows["t"])
    want_rows = int(round(sc["duration_s"] / sc["timestep"] )) + 1 \
        if "timestep" in sc else \
        int(round(sc["duration_s"] / SPEC_DT)) + 1
    if not (0.9 * want_rows <= n <= 1.1 * want_rows):
        problems.append(f"{n} rows, expected about {want_rows}")
    t = rows["t"]
    if t and abs(t[0]) > 1e-6:
        problems.append(f"t starts at {t[0]}, not 0")
    if any(t[i] <= t[i - 1] for i in range(1, len(t))):
        problems.append("t not strictly increasing")
    if t and t[-1] < 0.8 * sc["duration_s"]:
        problems.append(f"t ends at {t[-1]}, before 0.8 x duration")
    allv = [v for col in rows.values() for v in col]
    if any(not math.isfinite(v) for v in allv):
        problems.append("non-finite value in csv")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--skip-run", action="store_true",
                    help="score CSVs already next to the artifact (loop "
                         "bookkeeping only; selftest never uses this)")
    ap.add_argument("--judge-dir")
    args = ap.parse_args()

    judge_dir = os.path.abspath(args.judge_dir or HERE)
    spec_path = os.path.join(judge_dir, "spec.json")
    with open(spec_path) as fh:
        spec = json.load(fh)
    global SPEC_SCEN, SPEC_DT
    SPEC_SCEN = spec["scenarios"]
    SPEC_DT = spec["timestep_s"]
    exp = oracle_values(spec)

    sha_before = check_shas(judge_dir)
    verdict = {"demo": "sim-engine-arena", "artifact": os.path.basename(args.artifact),
               "seed": args.seed, "gates": {}, "timing": {}, "scenarios": {}}
    rc = 0
    workdir = tempfile.mkdtemp(prefix="arena-artifact-")
    refdir = tempfile.mkdtemp(prefix="arena-ref-")
    csv_dir = workdir
    try:
        # ---- gate 1: structure
        try:
            text, problems = load_artifact(args.artifact)
        except Exception as exc:
            verdict["gates"]["structure"] = {"pass": False,
                                            "problems": [str(exc)[:300]]}
            rc = 1
        else:
            problems += [{"literal": h["literal"], "near oracle": h["oracle"]}
                         for h in hardcode_hits(text, oracle_literals(spec, exp))]
            verdict["gates"]["structure"] = {"pass": not problems,
                                            "problems": problems}
            if problems:
                rc = 1

        # ---- gate 2: run
        if rc == 0:
            if args.skip_run:
                # score CSVs already next to the artifact
                for sc in SPEC_SCEN:
                    src = os.path.join(os.path.dirname(os.path.abspath(
                        args.artifact)), sc["output"])
                    if os.path.exists(src):
                        shutil.copy(src, os.path.join(workdir, sc["output"]))
                    problems = [f"missing {sc['output']}"
                                for sc in SPEC_SCEN
                                if not os.path.exists(os.path.join(workdir, sc["output"]))]
                verdict["gates"]["run"] = {"pass": not problems,
                                            "problems": problems,
                                            "mode": "skip-run"}
                wall = 0.0
                if problems:
                    rc = 1
            else:
                problems, wall, out = run_artifact(args.artifact, workdir,
                                                   spec_path, csv_dir)
                verdict["gates"]["run"] = {"pass": not problems,
                                           "problems": problems}
                verdict["timing"]["artifact_run_s"] = round(wall, 1)
                if problems:
                    rc = 1

        # ---- gates 3-4: csv shape + oracle
        if rc == 0:
            for sc in SPEC_SCEN:
                name = sc["name"]
                path = os.path.join(csv_dir, sc["output"])
                sres = {}
                try:
                    rows = parse_traj(path)
                except (ValueError, OSError) as e:
                    sres = {"csv_shape": {"pass": False,
                                          "problems": [f"unreadable: {e}"]}}
                else:
                    shape_p = csv_shape(name, rows, sc)
                    sres["csv_shape"] = {"pass": not shape_p,
                                         "problems": shape_p}
                    if not shape_p:
                        try:
                            m = analyze(name, rows, exp[name], spec)
                        except (ValueError, KeyError, IndexError,
                                OverflowError, ZeroDivisionError) as e:
                            m = {"pass": False,
                                 "problems": [f"bad-traj: {e}"]}
                        sres["oracle"] = m
                verdict["scenarios"][name] = sres
                if not all(g.get("pass", False) for g in sres.values()):
                    rc = 1

        # ---- gate 5: agreement with the judge's reference port
        if rc == 0:
            ref = subprocess.run(
                [JUDGE_VENV_PY, os.path.join(judge_dir, "ref_sim.py"),
                 spec_path, refdir, "--seed", str(args.seed)],
                capture_output=True, text=True, timeout=600)
            if ref.returncode != 0:
                verdict["gates"]["agreement"] = {
                    "pass": False,
                    "problems": [f"reference port failed: {ref.stderr[-200:]}"]}
                rc = 1
            else:
                probs = []
                metrics = {}
                for sc in SPEC_SCEN:
                    name = sc["name"]
                    art_rows = parse_traj(os.path.join(csv_dir, sc["output"]))
                    ref_rows = parse_traj(os.path.join(refdir, sc["output"]))
                    dev = agreement_metric(name, art_rows, ref_rows)
                    scale = AGREE_SCALE[name]
                    metrics[name] = {"max_dev": dev, "scale": scale}
                    if dev is None:
                        probs.append(f"{name}: no comparable column")
                    elif dev > scale:
                        probs.append(f"{name}: max deviation {dev:.4f} "
                                     f"> {scale} (agreement tolerance)")
                verdict["gates"]["agreement"] = {"pass": not probs,
                                                 "problems": probs,
                                                 "metrics": metrics}
                if probs:
                    rc = 1

        sha_after = check_shas(judge_dir)
        verdict["judge_intact"] = sha_before == sha_after
        if not verdict["judge_intact"]:
            rc = 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        shutil.rmtree(refdir, ignore_errors=True)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
