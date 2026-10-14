#!/usr/bin/env python3
"""Collect real CalculiX result fields for the fea-calculix media.

For each case this reruns the exact mesh+solve the judge ran:
judge.gen_mesh() writes the same mesh.inc the judge consumes, then the
artifact's own deck is run under ccx with one change -- the output
requests are widened from the NTIP/EMEAS subsets to the whole model so
the full displacement/stress field can be drawn. Nothing else in the
deck is touched; the measured quantities (max -U3 over NSET NTIP, max
scaled von Mises over NSET NEVAL) are recomputed with the judge's own
parse_frd()/vm_stress() and cross-checked against the verdict JSON in
data/verdicts/ -- they must agree to < 0.1% or this script fails.

Outputs per case in work/<case>/: mesh.inc, job.inp, job.frd (real ccx
output), fields.npz, summary.json.  Also writes data/convergence.json
(tip deflection / wall stress per mesh for the good design, from the
real .frd files, cross-checked against the verdict's convergence gate).

Usage: solve_fields.py [--force]
"""
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "judge"))
import judge  # noqa: E402  (gen_mesh, parse_frd, vm_stress, find_tool)

MEDIA = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(MEDIA)
WORK = os.path.join(MEDIA, "work")
VERDICTS = os.path.join(MEDIA, "data", "verdicts")
XCHECK_TOL = 1e-3   # relative; ccx is deterministic, this should be ~0

# cases: (work dir name, artifact dir relative to the demo dir,
#         mesh expression over mesh_size s, verdict json name or None)
CASES = [
    ("good-coarse", "examples/good",               "s",     "good"),
    ("good-fine",   "examples/good",               "s/2",   "good"),
    ("overload-10x", "media/work/mutants/overload-10x", "s/2", "overload-10x"),
    ("undersized",   "media/work/mutants/undersized",   "s/2", "undersized"),
    ("propped-tip",  "media/work/mutants/propped-tip",  "s/2", "propped-tip"),
    ("load-on-ntip", "media/work/mutants/load-on-ntip", "s/2", "load-on-ntip"),
]


def full_output_deck(text):
    """Widen *NODE FILE / *EL FILE to the whole model; everything else
    in the graded deck is left byte-identical."""
    text = re.sub(r"(?m)^\s*\*NODE FILE[^\n]*$", "*NODE FILE", text)
    text = re.sub(r"(?m)^\s*\*EL FILE[^\n]*$", "*EL FILE", text)
    return text


def parse_mesh_inc(path):
    """Parse the mesh.inc the solver actually included: nodes + C3D8 elems."""
    nodes, elems, mode = {}, {}, None
    for line in open(path):
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
    return nodes, elems


def solve_case(name, adir, mesh_expr, verdict_name, force):
    adir = os.path.join(DEMO, adir)
    cdir = os.path.join(WORK, name)
    os.makedirs(cdir, exist_ok=True)
    design = json.load(open(os.path.join(adir, "design.json")))
    deck = open(os.path.join(adir, "beam.inp")).read()
    L, b, h, s = (float(design[k]) for k in ("L", "b", "h", "mesh_size"))
    mesh = eval(mesh_expr, {}, {"s": s})
    job_inp = os.path.join(cdir, "job.inp")
    frd = os.path.join(cdir, "job.frd")
    stamp_path = os.path.join(cdir, "stamp.sha256")

    full_deck = full_output_deck(deck)
    stamp = hashlib.sha256(
        f"{L}|{b}|{h}|{mesh}|{full_deck}".encode()).hexdigest()
    if not force and os.path.exists(frd) and os.path.exists(stamp_path) \
            and open(stamp_path).read().strip() == stamp:
        print(f"{name}: cached (mesh.inc+job.inp unchanged)")
    else:
        stats, ntip, neval, _ = judge.gen_mesh(L, b, h, mesh, cdir)
        with open(job_inp, "w") as f:
            f.write(full_deck)
        r = subprocess.run([judge.find_tool("ccx"), "job"], cwd=cdir,
                           capture_output=True, text=True,
                           timeout=judge.CCX_TIMEOUT)
        if not os.path.exists(frd):
            raise SystemExit(f"{name}: ccx produced no job.frd "
                             f"(rc={r.returncode}): {r.stdout[-300:]}")
        open(stamp_path, "w").write(stamp + "\n")
        print(f"{name}: solved ({stats['nelem']} elements, "
              f"{stats['nnode']} nodes)")

    nodes, elems = parse_mesh_inc(os.path.join(cdir, "mesh.inc"))
    disp, sig = judge.parse_frd(frd)
    if not disp:
        raise SystemExit(f"{name}: job.frd has no displacement block")

    # judge-identical measurements
    tol = 1e-6 * L
    ntip = sorted(n for n, (x, y, z) in nodes.items() if x > L - tol)
    neval = sorted(n for n, (x, y, z) in nodes.items()
                   if 0.3 * h <= x <= h and tol < y < b - tol
                   and (z < tol or z > h - tol))
    delta = max(-disp[n][2] for n in ntip if n in disp)
    sigma = max(judge.vm_stress(sig[n]) * L / (L - nodes[n][0])
                for n in neval if n in sig) if sig else None

    import numpy as np
    ids = np.array(sorted(nodes))
    idx = {n: i for i, n in enumerate(ids)}
    coords = np.array([nodes[n] for n in ids])
    u = np.array([disp.get(n, (0., 0., 0.)) for n in ids])
    vm = np.array([judge.vm_stress(sig[n]) if n in sig else float("nan")
                   for n in ids])
    conn = np.array([[idx[n] for n in elems[e]] for e in sorted(elems)])
    np.savez_compressed(os.path.join(cdir, "fields.npz"),
                        ids=ids, coords=coords, disp=u, vm=vm, conn=conn)

    summary = dict(case=name, artifact=os.path.relpath(adir, DEMO),
                   mesh_mm=mesh, L_mm=L, b_mm=b, h_mm=h,
                   nelem=len(elems), nnode=len(ids),
                   delta_mm=delta,
                   sigma_mpa=None if sigma is None else sigma,
                   vm_field_max=float(np.nanmax(vm)))

    # cross-check against the judge's own verdict where it measured the
    # same quantity (verdict metrics are on the mesh_size/2 mesh)
    if verdict_name and mesh_expr == "s/2":
        v = json.load(open(os.path.join(VERDICTS, verdict_name + ".json")))
        m = v.get("metrics", {})
        checks = {}
        if "delta_mm" in m:
            checks["delta_mm"] = dict(media=delta, judge=m["delta_mm"])
        if "sigma_mpa" in m:
            checks["sigma_mpa"] = dict(media=sigma, judge=m["sigma_mpa"])
        for k, c in checks.items():
            j = c["judge"]; me = c["media"]
            rel = abs(me - j) / max(abs(j), 1e-12)
            c["rel_err"] = rel
            if rel > XCHECK_TOL:
                raise SystemExit(
                    f"{name}: media {k}={me} disagrees with verdict "
                    f"{j} ({rel:.2%})")
        summary["xcheck_vs_verdict"] = checks
    with open(os.path.join(cdir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    return summary


def main():
    force = "--force" in sys.argv[1:]
    summaries = [solve_case(*c, force) for c in CASES]

    # convergence panel data: the good design at s and s/2, all from .frd
    gc = next(s for s in summaries if s["case"] == "good-coarse")
    gf = next(s for s in summaries if s["case"] == "good-fine")
    dd = abs(gf["delta_mm"] - gc["delta_mm"]) / abs(gf["delta_mm"])
    ds = abs(gf["sigma_mpa"] - gc["sigma_mpa"]) / abs(gf["sigma_mpa"])
    conv = dict(
        source="media/work/good-{coarse,fine}/job.frd parsed with "
               "judge.parse_frd + judge.vm_stress",
        gate="convergence: |change| <= 2% between mesh_size and mesh_size/2",
        meshes=[dict(mesh_mm=gc["mesh_mm"], elems=gc["nelem"],
                     delta_mm=gc["delta_mm"], sigma_mpa=gc["sigma_mpa"]),
                dict(mesh_mm=gf["mesh_mm"], elems=gf["nelem"],
                     delta_mm=gf["delta_mm"], sigma_mpa=gf["sigma_mpa"])],
        delta_change_pct=100 * dd, sigma_change_pct=100 * ds)
    v = json.load(open(os.path.join(VERDICTS, "good.json")))
    conv["verdict_detail"] = v["gates"]["convergence"]["detail"]
    m = re.search(r"deflection change ([\d.]+)%, stress change ([\d.]+)%",
                  conv["verdict_detail"])
    if not m or abs(float(m.group(1)) - conv["delta_change_pct"]) > 0.005 \
            or abs(float(m.group(2)) - conv["sigma_change_pct"]) > 0.005:
        raise SystemExit("convergence numbers disagree with verdict JSON")
    with open(os.path.join(MEDIA, "data", "convergence.json"), "w") as f:
        json.dump(conv, f, indent=2)
    print("convergence.json written:",
          f"delta {conv['delta_change_pct']:.2f}% "
          f"sigma {conv['sigma_change_pct']:.2f}% (verdict agrees)")


if __name__ == "__main__":
    main()
