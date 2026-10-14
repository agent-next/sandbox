#!/usr/bin/env python3
"""Judge for the fea-calculix demo.

Usage: judge.py <artifact> [--seed N] [--json out.json]

<artifact> is a directory containing:
  design.json  {"L": mm, "b": mm, "h": mm, "mesh_size": mm}
  beam.inp     CalculiX deck that *INCLUDEs mesh.inc and uses the node/element
               sets the judge generates: NSET NFIX (clamped face), NTIP (tip
               face), NLOAD (4 tip corner nodes), NEVAL (stress evaluation),
               ELSET EALL (all solids), EMEAS (stress output region).
(or a path to design.json, in which case beam.inp must sit next to it)

Units: mm, N, MPa.  Fixed problem constants: P = 1000 N tip load in -Z split
over the 4 NLOAD corner nodes, steel E = 200000 MPa, nu = 0.3,
rho = 0.00785 g/mm^3, sigma_allow = 250/1.5 MPa, deflection limit = L/100.

Gates:
  verification : reference beam (1000 x 50 x 100 mm) at a converged mesh must
                 match Euler-Bernoulli within 3% (tip deflection and bending
                 stress at the wall)
  convergence  : on the submitted design, the s and s/2 meshes must agree
                 within 2% in both quantities
  spec_limits  : sigma_wall <= sigma_allow, delta_tip <= L/100, and both must
                 stay within a sanity band of the Euler-Bernoulli estimate
                 (catches wrong loads/BCs that still "satisfy" the limits)
  mass         : informational, rho*L*b*h in grams

Stress is measured as the max von Mises over the outer-fiber nodes of the
cross-section mid-width band at 0.3h <= x <= h (clear of the clamp singularity
and the loaded corner nodes), scaled by L/(L-x) to the wall bending moment.
Exits 0 only if every gate passes.
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

# fixed problem constants (mm, N, MPa, g)
E_MOD = 200000.0
NU = 0.3
RHO = 7.85e-3        # g/mm^3
P_LOAD = 1000.0      # N total tip load in -Z
S_ALLOW = 250.0 / 1.5

# judge constants
REF = dict(L=1000.0, b=50.0, h=100.0, s=5.0)
VERIFY_TOL = 0.03
CONV_TOL = 0.02
DELTA_BAND = (0.85, 1.15)   # delta_fea / delta_EB sanity band
SIGMA_BAND = (0.75, 1.25)   # sigma_fea / sigma_EB sanity band
MAX_ELEMS = 150000
CCX_TIMEOUT = 300
GMSH_TIMEOUT = 120

GEO_TMPL = """\
L = {L};  b = {b};  h = {h};
nx = {nx};  ny = {ny};  nz = {nz};
Point(1) = {{0,0,0}};  Point(2) = {{L,0,0}};  Point(3) = {{L,b,0}};  Point(4) = {{0,b,0}};
Point(5) = {{0,0,h}};  Point(6) = {{L,0,h}};  Point(7) = {{L,b,h}};  Point(8) = {{0,b,h}};
Line(1)={{1,2}}; Line(2)={{2,3}}; Line(3)={{3,4}}; Line(4)={{4,1}};
Line(5)={{5,6}}; Line(6)={{6,7}}; Line(7)={{7,8}}; Line(8)={{8,5}};
Line(9)={{1,5}}; Line(10)={{2,6}}; Line(11)={{3,7}}; Line(12)={{4,8}};
Curve Loop(1)={{1,2,3,4}};      Plane Surface(1)={{1}};
Curve Loop(2)={{5,6,7,8}};      Plane Surface(2)={{2}};
Curve Loop(3)={{1,10,-5,-9}};   Plane Surface(3)={{3}};
Curve Loop(4)={{11,7,-12,-3}};  Plane Surface(4)={{4}};
Curve Loop(5)={{4,9,-8,-12}};   Plane Surface(5)={{5}};
Curve Loop(6)={{2,11,-6,-10}};  Plane Surface(6)={{6}};
Surface Loop(1)={{1,2,3,4,5,6}};
Volume(1)={{1}};
Transfinite Curve {{1,3,5,7}} = nx+1;
Transfinite Curve {{2,4,6,8}} = ny+1;
Transfinite Curve {{9,10,11,12}} = nz+1;
Transfinite Surface {{1,2,3,4,5,6}};
Recombine Surface {{1,2,3,4,5,6}};
Transfinite Volume {{1}};
"""


def find_tool(name):
    path = shutil.which(name) or shutil.which(
        name, path=os.path.expanduser("~/tools/bin"))
    if not path:
        raise RuntimeError(f"{name} not found; run judge/setup.sh first")
    return path


class RunError(RuntimeError):
    pass


def gen_mesh(L, b, h, s, workdir):
    """Mesh the beam with gmsh and write mesh.inc with the contracted sets.

    Returns (stats dict, ntip set, neval set)."""
    nx = max(2, round(L / s))
    ny = max(2, min(4, round(b / s)))   # uniform across width: cap at 4
    nz = max(2, round(h / s))
    with open(os.path.join(workdir, "beam.geo"), "w") as f:
        f.write(GEO_TMPL.format(L=L, b=b, h=h, nx=nx, ny=ny, nz=nz))
    raw = os.path.join(workdir, "raw.inp")
    r = subprocess.run([find_tool("gmsh"), "beam.geo", "-3", "-o", raw, "-v", "0"],
                       cwd=workdir, capture_output=True, text=True,
                       timeout=GMSH_TIMEOUT)
    if r.returncode != 0 or not os.path.exists(raw):
        raise RunError(f"gmsh failed: {r.stdout[-500:]} {r.stderr[-500:]}")
    nodes, elems, mode = {}, {}, None
    for line in open(raw):
        line = line.strip()
        if line.startswith("*"):
            u = line.upper()
            if u.startswith("*NODE"):
                mode = "node"
            elif u.startswith("*ELEMENT"):
                mode = "elem" if "C3D8" in u else "skip"
            else:
                mode = None
            continue
        if not line or mode in (None, "skip"):
            continue
        p = [t.strip() for t in line.split(",") if t.strip()]
        if mode == "node" and len(p) >= 4:
            nodes[int(p[0])] = tuple(float(v) for v in p[1:4])
        elif mode == "elem" and len(p) >= 9:
            elems[int(p[0])] = [int(v) for v in p[1:9]]
    if not nodes or not elems:
        raise RunError("gmsh produced an empty mesh")
    tol = 1e-6 * L
    nfix = sorted(n for n, (x, y, z) in nodes.items() if x < tol)
    ntip = sorted(n for n, (x, y, z) in nodes.items() if x > L - tol)
    nload = sorted(n for n in ntip
                   if (nodes[n][1] < tol or nodes[n][1] > b - tol)
                   and (nodes[n][2] < tol or nodes[n][2] > h - tol))
    xa, xb = 0.3 * h, h
    neval = sorted(n for n, (x, y, z) in nodes.items()
                   if xa <= x <= xb and tol < y < b - tol
                   and (z < tol or z > h - tol))
    neval_set = set(neval)
    emeas = sorted(e for e, nn in elems.items()
                   if any(n in neval_set for n in nn))
    if len(nload) != 4:
        raise RunError(f"expected 4 tip corner nodes, found {len(nload)}")
    if not neval:
        raise RunError("no stress-evaluation nodes: mesh too coarse across "
                       "the width (need an interior row of surface nodes)")

    def wset(f, kw, name, ids):
        f.write(f"*{kw},{kw}={name}\n")
        for i in range(0, len(ids), 16):
            f.write(", ".join(str(v) for v in ids[i:i + 16]) + ",\n")

    with open(os.path.join(workdir, "mesh.inc"), "w") as f:
        f.write("*NODE\n")
        for n in sorted(nodes):
            x, y, z = nodes[n]
            f.write(f"{n}, {x:.10g}, {y:.10g}, {z:.10g}\n")
        f.write("*ELEMENT, TYPE=C3D8, ELSET=EALL\n")
        for e in sorted(elems):
            f.write(f"{e}, " + ", ".join(str(v) for v in elems[e]) + "\n")
        wset(f, "NSET", "NFIX", nfix)
        wset(f, "NSET", "NTIP", ntip)
        wset(f, "NSET", "NLOAD", nload)
        wset(f, "NSET", "NEVAL", neval)
        wset(f, "ELSET", "EMEAS", emeas)
    return (dict(nx=nx, ny=ny, nz=nz, nelem=len(elems), nnode=len(nodes)),
            set(ntip), neval_set, nodes)


def parse_frd(path):
    """Parse ASCII .frd: disp {node:(u1,u2,u3)}, stress {node:(xx,yy,zz,xy,xz,yz)}"""
    disp, sig, mode = {}, {}, None
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith(" -4"):
                mode = ("disp" if "DISP" in line
                        else "sig" if "STRESS" in line else None)
                continue
            if mode is None:
                continue
            if line.startswith(" -1"):
                node = int(line[3:13])
                n = 3 if mode == "disp" else 6
                vals = [float(line[13 + i * 12:13 + (i + 1) * 12])
                        for i in range(n)]
                (disp if mode == "disp" else sig)[node] = vals
            elif not line.startswith(" -"):
                mode = None
    return disp, sig


def vm_stress(s):
    xx, yy, zz, xy, xz, yz = s
    return math.sqrt(0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2
                            + 6.0 * (xy ** 2 + xz ** 2 + yz ** 2)))


def run_fea(deck_text, L, b, h, s, workdir):
    """Mesh at size s, run the deck under ccx, return measured delta/sigma."""
    os.makedirs(workdir, exist_ok=True)
    stats, ntip, neval, nodes = gen_mesh(L, b, h, s, workdir)
    with open(os.path.join(workdir, "job.inp"), "w") as f:
        f.write(deck_text)
    try:
        r = subprocess.run([find_tool("ccx"), "job"], cwd=workdir,
                           capture_output=True, text=True, timeout=CCX_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RunError(f"ccx timed out after {CCX_TIMEOUT}s")
    frd = os.path.join(workdir, "job.frd")
    if not os.path.exists(frd):
        raise RunError(f"ccx produced no results (rc={r.returncode}): "
                       f"{r.stdout[-300:]} {r.stderr[-300:]}")
    disp, sig = parse_frd(frd)
    tip = [disp[n] for n in ntip if n in disp]
    if not tip:
        raise RunError("deck produced no displacements on NSET NTIP "
                       "(missing *NODE FILE U output?)")
    ev = [(vm_stress(sig[n]) * L / (L - nodes[n][0]), nodes[n][0])
          for n in neval if n in sig]
    if not ev:
        raise RunError("deck produced no stresses on NSET NEVAL "
                       "(missing *EL FILE S output?)")
    delta = max(-d[2] for d in tip)
    sigma = max(v for v, _ in ev)
    return dict(delta=delta, sigma=sigma, **stats)


def eb(L, b, h):
    """Euler-Bernoulli tip deflection (mm) and wall bending stress (MPa)."""
    i_mom = b * h ** 3 / 12.0
    return P_LOAD * L ** 3 / (3.0 * E_MOD * i_mom), P_LOAD * L / (b * h ** 2 / 6.0)


def main():
    args = sys.argv[1:]
    json_out = None
    artifact = None
    i = 0
    while i < len(args):
        if args[i] == "--json":
            json_out = args[i + 1]; i += 2
        elif args[i] == "--seed":
            i += 2                      # deterministic judge: seed unused
        elif args[i].startswith("--seed="):
            i += 1
        else:
            artifact = args[i]; i += 1
    if artifact is None:
        print("usage: judge.py <artifact> [--seed N] [--json out.json]",
              file=sys.stderr)
        sys.exit(2)
    if os.path.isdir(artifact):
        adir = artifact
    else:
        adir = os.path.dirname(os.path.abspath(artifact))
    design_path = os.path.join(adir, "design.json")
    deck_path = os.path.join(adir, "beam.inp")

    gates = {}
    metrics = {}

    def fail_all(reason):
        for g in ("verification", "convergence", "spec_limits"):
            gates[g] = dict(pass_=False, detail=reason)
        emit()

    def emit():
        ok = all(g["pass_"] for g in gates.values())
        out = dict(verdict="PASS" if ok else "FAIL",
                   timing=dict(wall_s=round(time.time() - T0, 1)),
                   gates={k: {"pass": v["pass_"], "detail": v["detail"]}
                          for k, v in gates.items()},
                   metrics=metrics)
        text = json.dumps(out, indent=2)
        if json_out:
            with open(json_out, "w") as f:
                f.write(text + "\n")
        print(text)
        sys.exit(0 if ok else 1)

    # ---- read artifact ----------------------------------------------------
    try:
        design = json.load(open(design_path))
        L = float(design["L"]); b = float(design["b"]); h = float(design["h"])
        s = float(design["mesh_size"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fail_all(f"design.json unreadable or missing L/b/h/mesh_size: {exc}")
    try:
        deck_text = open(deck_path).read()
    except OSError as exc:
        fail_all(f"beam.inp unreadable: {exc}")

    # ---- validation -------------------------------------------------------
    def est_elems(mesh):
        return (max(2, round(L / mesh)) * max(2, min(4, round(b / mesh)))
                * max(2, round(h / mesh)))
    problems = []
    if not (L > 0 and b > 0 and h > 0 and s > 0):
        problems.append("L, b, h, mesh_size must be positive")
    elif L < 5 * max(b, h):
        problems.append("beam must be slender: L >= 5*max(b,h) required")
    if s > min(b, h) / 2:
        problems.append("mesh_size too large: need >= 2 elements across "
                        "the smallest cross-section dimension")
    for label, mesh in (("mesh_size", s), ("mesh_size/2", s / 2)):
        if est_elems(mesh) > MAX_ELEMS:
            problems.append(f"{label} yields > {MAX_ELEMS} elements; "
                            "choose a coarser mesh_size")
    if problems:
        fail_all("invalid design: " + "; ".join(problems))
    metrics.update(L_mm=L, b_mm=b, h_mm=h, mesh_size_mm=s)
    d_eb, s_eb = eb(L, b, h)
    metrics["mass_g"] = round(RHO * L * b * h, 3)

    # ---- gate 1: verification on the reference beam -----------------------
    try:
        r = run_fea(deck_text, REF["L"], REF["b"], REF["h"], REF["s"],
                    os.path.join(workdir, "ref"))
        d_ref, s_ref = eb(REF["L"], REF["b"], REF["h"])
        derr = (r["delta"] - d_ref) / d_ref
        serr = (r["sigma"] - s_ref) / s_ref
        ok = abs(derr) <= VERIFY_TOL and abs(serr) <= VERIFY_TOL
        gates["verification"] = dict(
            pass_=ok,
            detail=(f"reference beam vs Euler-Bernoulli: "
                    f"deflection {r['delta']:.4f} vs {d_ref:.4f} mm "
                    f"({derr:+.2%}), stress {r['sigma']:.2f} vs {s_ref:.2f} MPa "
                    f"({serr:+.2%}); tolerance {VERIFY_TOL:.0%}"))
        metrics["ref_delta_mm"] = round(r["delta"], 4)
        metrics["ref_sigma_mpa"] = round(r["sigma"], 3)
    except RunError as exc:
        fail_all(f"reference run failed ({exc}); downstream gates cannot run")

    # ---- gates 2+3: two meshes of the submitted design --------------------
    try:
        coarse = run_fea(deck_text, L, b, h, s, os.path.join(workdir, "coarse"))
        fine = run_fea(deck_text, L, b, h, s / 2.0,
                       os.path.join(workdir, "fine"))
    except RunError as exc:
        for g in ("convergence", "spec_limits"):
            gates[g] = dict(pass_=False, detail=f"run failed: {exc}")
        emit()

    dd = abs(fine["delta"] - coarse["delta"]) / max(abs(fine["delta"]), 1e-9)
    ds = abs(fine["sigma"] - coarse["sigma"]) / max(abs(fine["sigma"]), 1e-9)
    gates["convergence"] = dict(
        pass_=dd <= CONV_TOL and ds <= CONV_TOL,
        detail=(f"mesh {s:g} vs {s/2:g} mm "
                f"({coarse['nelem']} -> {fine['nelem']} elements): "
                f"deflection change {dd:.2%}, stress change {ds:.2%}; "
                f"tolerance {CONV_TOL:.0%}"))
    metrics.update(coarse_elems=coarse["nelem"], fine_elems=fine["nelem"],
                   delta_mm=round(fine["delta"], 4),
                   sigma_mpa=round(fine["sigma"], 3))

    lim = L / 100.0
    checks = []
    ok = True
    if not fine["sigma"] <= S_ALLOW:
        ok = False
        checks.append(f"sigma {fine['sigma']:.1f} > allowable {S_ALLOW:.1f} MPa")
    else:
        checks.append(f"sigma {fine['sigma']:.1f} <= allowable {S_ALLOW:.1f} MPa")
    if not fine["delta"] <= lim:
        ok = False
        checks.append(f"deflection {fine['delta']:.2f} > limit {lim:.2f} mm")
    else:
        checks.append(f"deflection {fine['delta']:.2f} <= limit {lim:.2f} mm")
    dr = fine["delta"] / d_eb
    sr = fine["sigma"] / s_eb
    if not DELTA_BAND[0] <= dr <= DELTA_BAND[1]:
        ok = False
        checks.append(f"deflection/EB ratio {dr:.2f} outside "
                      f"[{DELTA_BAND[0]}, {DELTA_BAND[1]}] (load/BC wrong?)")
    if not SIGMA_BAND[0] <= sr <= SIGMA_BAND[1]:
        ok = False
        checks.append(f"stress/EB ratio {sr:.2f} outside "
                      f"[{SIGMA_BAND[0]}, {SIGMA_BAND[1]}] (load/BC wrong?)")
    gates["spec_limits"] = dict(pass_=ok, detail="; ".join(checks))

    emit()


if __name__ == "__main__":
    T0 = time.time()
    with tempfile.TemporaryDirectory(prefix="fea-judge-") as workdir:
        main()
