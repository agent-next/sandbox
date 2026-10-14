#!/usr/bin/env python3
"""
OpenFOAM CFD judge — gate checking for the channel (Poiseuille) and
lid-driven-cavity demo cases.

Usage: check_gates.py <case_dir> <case_type> [--json out.json]
  case_type: poiseuille | cavity

The case_dir is a scratch copy owned by the caller; the judge is free to
generate meshes, run solvers and write sampling output inside it.

Oracles (independent of "the tool ran"):
  * analytic plane-Poiseuille profile and pressure gradient
  * Reynolds-number consistency with the case's own nu / velocity scale
  * mesh-refinement convergence order
  * Ghia, Ghia & Shin (1982) tabulated centreline data, J. Comput. Phys.
    48(3):387-411, Tables I & II, Re=100.
"""

import bisect
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys

# ---------------------------------------------------------------------------
# Reference data: Ghia et al. (1982), Re = 100, 129x129 grid.
# Table I  — u-velocity on the vertical centreline (x = 0.5), keyed by y.
# Table II — v-velocity on the horizontal centreline (y = 0.5), keyed by x.
# ---------------------------------------------------------------------------
GHIA_U = {
    1.0000:  1.00000, 0.9766:  0.84123, 0.9688:  0.78871, 0.9609:  0.73722,
    0.9531:  0.68717, 0.8516:  0.23151, 0.7344:  0.00332, 0.6172: -0.13641,
    0.5000: -0.20581, 0.4531: -0.21090, 0.2813: -0.15662, 0.1719: -0.10150,
    0.1016: -0.06434, 0.0703: -0.04775, 0.0625: -0.04192, 0.0547: -0.03717,
    0.0000:  0.00000,
}

GHIA_V = {
    1.0000:  0.00000, 0.9688: -0.05906, 0.9609: -0.07391, 0.9531: -0.08864,
    0.9453: -0.10313, 0.9063: -0.16914, 0.8594: -0.22445, 0.8047: -0.24533,
    0.5000:  0.05454, 0.2344:  0.17527, 0.2266:  0.17507, 0.1563:  0.16077,
    0.0938:  0.12317, 0.0781:  0.10890, 0.0703:  0.10091, 0.0625:  0.09233,
    0.0000:  0.00000,
}

GHIA_REF = ("Ghia, U., Ghia, K.N., Shin, C.T. (1982). High-Re solutions for "
            "incompressible flow using the Navier-Stokes equations and a "
            "multigrid method. J. Comput. Phys. 48(3), 387-411. "
            "Tables I & II, Re=100.")

# Gate thresholds (see SPEC.md)
RESIDUAL_TOL = 1e-5        # last-step initial residuals, Ux/Uy/p
CONTINUITY_TOL = 1e-8      # last-step global continuity error
POISEUILLE_L2_TOL = 0.02   # normalised L2 error of u(y) vs analytic
POISEUILLE_DPDX_TOL = 0.15 # relative error of measured dp/dx vs -2*nu*Umax/h^2
RE_TOL = 0.10              # relative tolerance on Re = 100
ORDER_TOL = 1.5            # minimum observed convergence order
GHIA_TOL = 0.02            # max abs error vs Ghia tables (lid-speed units)

FOAM_ENV = dict(os.environ,
                FOAM_ETC='/usr/share/openfoam/etc',
                WM_PROJECT_DIR='/usr/share/openfoam')

# Case geometry pinned by SPEC.md: unit square / channel, half-height 0.5.
HALF_HEIGHT = 0.5


def run_cmd(cmd, cwd):
    r = subprocess.run(cmd, shell=True, cwd=cwd, env=FOAM_ENV,
                       capture_output=True, text=True, timeout=1800)
    return r.returncode, r.stdout, r.stderr


def read_dict(path):
    with open(path) as f:
        return f.read()


def parse_scalar_entry(content, key):
    # accepts `nu 0.01;`, `nu [0 2 -1 0 0 0 0] 0.01;` and `nu nu [...] 0.01;`
    k = re.escape(key)
    m = re.search(r'\b' + k + r'\s+(?:' + k + r'\s+)?(?:\[[^\]]*\]\s*)?'
                  r'(-?[\d.eE+-]+)\s*;', content)
    return float(m.group(1)) if m else None


def parse_vector_uniform(block):
    m = re.search(r'value\s+uniform\s*\(\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+'
                  r'(-?[\d.eE+-]+)\s*\)', block)
    return tuple(float(g) for g in m.groups()) if m else None


def get_boundary_block(content, name):
    """Boundary entries may contain nested entries; find the matching brace."""
    m = re.search(r'\b' + re.escape(name) + r'\s*\{', content)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(content) and depth:
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
        i += 1
    return content[m.end():i - 1] if depth == 0 else None


def mesh_cells(blockmesh_text):
    m = re.search(r'hex\s*\([^)]*\)\s*\(\s*(\d+)\s+(\d+)\s+(\d+)\s*\)',
                  blockmesh_text)
    return tuple(int(g) for g in m.groups()) if m else None


def inlet_profile(case_dir):
    """Return (kind, values) for the inlet patch of 0/U.

    kind = 'uniform'  -> values = (ux, uy, uz)
    kind = 'list'     -> values = [(eta_i, ux_i)] at face-centre heights
                         eta in [0,1] across the patch.
    """
    u = read_dict(os.path.join(case_dir, '0', 'U'))
    block = get_boundary_block(u, 'inlet')
    if block is None:
        return None
    if 'nonuniform' in block:
        m = re.search(r'nonuniform\s+List<vector>\s*(\d+)\s*\((.*?)\)\s*;',
                      block, re.DOTALL)
        if m:
            n = int(m.group(1))
            vals = [float(v[0]) for v in re.findall(
                r'\(\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s*\)',
                m.group(2))]
            if len(vals) == n:
                return ('list', [((i + 0.5) / n, v)
                                 for i, v in enumerate(vals)])
        return None
    vec = parse_vector_uniform(block)
    return ('uniform', vec) if vec else None


def resampled_inlet_value(profile, ny):
    """Produce a `value` entry for the inlet BC at a new face count ny."""
    if profile is None:
        return None
    if profile[0] == 'uniform':
        ux, uy, uz = profile[1]
        return 'uniform (%g %g %g)' % (ux, uy, uz)
    pts = profile[1]
    etas = [p[0] for p in pts]
    vals = [p[1] for p in pts]
    out = []
    for j in range(ny):
        e = (j + 0.5) / ny
        if e <= etas[0]:
            v = vals[0]
        elif e >= etas[-1]:
            v = vals[-1]
        else:
            i = bisect.bisect_left(etas, e)
            t = (e - etas[i - 1]) / (etas[i] - etas[i - 1])
            v = vals[i - 1] + t * (vals[i] - vals[i - 1])
        out.append(v)
    body = '\n'.join('            (%.10g 0 0)' % v for v in out)
    return 'nonuniform List<vector>\n        %d\n        (\n%s\n        );' % (
        ny, body)


def clean_case(case_dir):
    """Delete generated content so grading reflects the committed inputs."""
    for name in os.listdir(case_dir):
        p = os.path.join(case_dir, name)
        if name == '0':
            continue
        if os.path.isdir(p) and re.fullmatch(r'\d+(\.\d+)?', name):
            shutil.rmtree(p)
        elif name in ('postProcessing', 'logs'):
            shutil.rmtree(p, ignore_errors=True)
        elif name.startswith('log.') and os.path.isfile(p):
            os.remove(p)
    shutil.rmtree(os.path.join(case_dir, 'constant', 'polyMesh'),
                  ignore_errors=True)


def latest_time_dir(case_dir):
    dirs = [d for d in glob.glob(os.path.join(case_dir, '[0-9]*'))
            if os.path.isdir(d) and os.path.basename(d) != '0']
    if not dirs:
        return None
    dirs.sort(key=lambda d: float(os.path.basename(d)))
    return dirs[-1]


def write_sample_dict(case_dir, sets):
    sets_text = '\n'.join(
        "    %s\n    {\n        type    uniform;\n        axis    %s;\n"
        "        nPoints %d;\n        start   %s;\n        end     %s;\n    }"
        % s for s in sets)
    text = ("type            sets;\n"
            "libs            (sampling);\n"
            "writeControl    writeTime;\n"
            "interpolationScheme cellPoint;\n"
            "setFormat       raw;\n"
            "sets\n(\n%s\n);\n"
            "fields  (U p);\n" % sets_text)
    path = os.path.join(case_dir, 'system', 'sampleDict')
    with open(path, 'w') as f:
        f.write(text)


def run_sampler(case_dir):
    rc, out, err = run_cmd('postProcess -func sampleDict -latestTime', case_dir)
    dirs = sorted(glob.glob(os.path.join(case_dir, 'postProcessing',
                                         'sampleDict', '*')))
    return rc, dirs[-1] if dirs else None, out + err


def load_sampled(path):
    rows = []
    for line in open(path):
        line = line.strip()
        if line and not line.startswith('#'):
            rows.append([float(v) for v in line.split()])
    return rows


def interp_at(x, xs, vs):
    i = bisect.bisect_left(xs, x)
    if i == 0:
        return vs[0]
    if i >= len(xs):
        return vs[-1]
    t = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
    return vs[i - 1] + t * (vs[i] - vs[i - 1])


def gate_result(gate, name, passed, details):
    return {'gate': gate, 'name': name, 'passed': bool(passed),
            'details': details}


# ---------------------------------------------------------------------------
# Gate 1 — mesh generation & quality
# ---------------------------------------------------------------------------
def gate1_mesh(case_dir):
    rc_bm, out_bm, err_bm = run_cmd('blockMesh', case_dir)
    if rc_bm != 0:
        return gate_result(1, 'Mesh quality', False,
                           {'error': 'blockMesh failed',
                            'output': (out_bm + err_bm)[-2000:]})
    rc, out, err = run_cmd('checkMesh', case_dir)
    txt = out + err
    max_ortho = max_skew = None
    m = re.search(r'Mesh non-orthogonality Max:\s*([\d.eE+-]+)', txt)
    if m:
        max_ortho = float(m.group(1))
    m = re.search(r'Max skewness\s*=\s*([\d.eE+-]+)', txt)
    if m:
        max_skew = float(m.group(1))
    failed = rc != 0 or 'Mesh OK' not in txt or \
        (max_ortho is not None and max_ortho > 70) or \
        (max_skew is not None and max_skew > 4) or \
        bool(re.search(r'\d+ cells with zero volume', txt))
    return gate_result(1, 'Mesh quality', not failed,
                       {'checkMesh_exit': rc,
                        'max_non_orthogonality': max_ortho,
                        'max_skewness': max_skew,
                        'cells': mesh_cells(read_dict(
                            os.path.join(case_dir, 'system',
                                         'blockMeshDict')))})


# ---------------------------------------------------------------------------
# Gate 2 — solver convergence
# ---------------------------------------------------------------------------
def gate2_convergence(case_dir):
    rc, out, err = run_cmd('icoFoam', case_dir)
    txt = out + err
    if rc != 0:
        return gate_result(2, 'Solver convergence', False,
                           {'error': 'icoFoam exited %d' % rc,
                            'output_tail': txt[-1500:]})
    init_res = {}
    glob_cont = None
    for line in txt.split('\n'):
        m = re.search(r'Solving for (\w+), Initial residual = ([\d.eE+-]+)',
                      line)
        if m:
            init_res[m.group(1)] = float(m.group(2))
        m = re.search(r'continuity errors.*global = (-?[\d.eE+-]+)', line)
        if m:
            glob_cont = abs(float(m.group(1)))
    res_ok = all(v < RESIDUAL_TOL for v in init_res.values()) and \
        all(k in init_res for k in ('Ux', 'Uy', 'p'))
    cont_ok = glob_cont is not None and glob_cont < CONTINUITY_TOL
    return gate_result(2, 'Solver convergence',
                       res_ok and cont_ok and latest_time_dir(case_dir),
                       {'icoFoam_exit': rc,
                        'final_initial_residuals': init_res,
                        'global_continuity_error': glob_cont,
                        'residuals_ok': res_ok, 'continuity_ok': cont_ok})


# ---------------------------------------------------------------------------
# Shared: transportProperties nu
# ---------------------------------------------------------------------------
def case_nu(case_dir):
    return parse_scalar_entry(
        read_dict(os.path.join(case_dir, 'constant', 'transportProperties')),
        'nu')


# ---------------------------------------------------------------------------
# Gate 3 — Poiseuille accuracy (Re consistency, profile L2, dp/dx)
# ---------------------------------------------------------------------------
def poiseuille_errors(case_dir):
    """Run the centreline sampler; return (u L2 error, dpdx rel err, Umax)."""
    write_sample_dict(case_dir, [
        ('centerline', 'y', 200, '(0.5 0 0.05)', '(0.5 1 0.05)'),
        ('pline', 'x', 200, '(0 0.5 0.05)', '(1 0.5 0.05)'),
    ])
    rc, pdir, log = run_sampler(case_dir)
    if not pdir:
        return None
    urows = load_sampled(os.path.join(pdir, 'centerline_U.xy'))
    prows = load_sampled(os.path.join(pdir, 'pline_p.xy'))
    ys = [r[0] for r in urows]
    ux = [r[1] for r in urows]
    l2 = math.sqrt(sum((u - (1.0 - (2.0 * y - 1.0) ** 2)) ** 2
                       for y, u in zip(ys, ux)) / len(ys))
    sel = [(r[0], r[1]) for r in prows if 0.2 < r[0] < 0.8]
    n = len(sel)
    sx = sum(x for x, _ in sel)
    sp = sum(p for _, p in sel)
    sxx = sum(x * x for x, _ in sel)
    sxp = sum(x * p for x, p in sel)
    slope = (n * sxp - sx * sp) / (n * sxx - sx * sx)
    return l2, slope, max(ux)


def gate3_poiseuille(case_dir):
    nu = case_nu(case_dir)
    res = poiseuille_errors(case_dir)
    if nu is None or res is None:
        return gate_result(3, 'Poiseuille accuracy', False,
                           {'error': 'could not evaluate case'})
    l2, slope, umax = res
    re = umax * HALF_HEIGHT / nu if nu else None
    dpdx_ana = -2.0 * nu * 1.0 / HALF_HEIGHT ** 2  # Umax = 1 by spec
    dpdx_err = abs(slope - dpdx_ana) / abs(dpdx_ana) if dpdx_ana else 1e9
    re_ok = re is not None and abs(re - 100.0) / 100.0 <= RE_TOL
    l2_ok = l2 <= POISEUILLE_L2_TOL
    dpdx_ok = dpdx_err <= POISEUILLE_DPDX_TOL
    return gate_result(3, 'Poiseuille accuracy',
                       re_ok and l2_ok and dpdx_ok,
                       {'Re_measured': re, 'Re_target': 100.0,
                        'nu': nu, 'Umax': umax,
                        'l2_error': l2, 'l2_tol': POISEUILLE_L2_TOL,
                        'dpdx_measured': slope, 'dpdx_analytic': dpdx_ana,
                        'dpdx_rel_err': dpdx_err,
                        'dpdx_tol': POISEUILLE_DPDX_TOL})


# ---------------------------------------------------------------------------
# Gate 4 — Poiseuille mesh convergence (10x10, 20x20, 40x40)
# ---------------------------------------------------------------------------
def gate4_mesh_convergence(work_root, case_dir):
    bm_path = os.path.join(case_dir, 'system', 'blockMeshDict')
    bm = read_dict(bm_path)
    cells = mesh_cells(bm)
    profile = inlet_profile(case_dir)
    if cells is None or profile is None:
        return gate_result(4, 'Poiseuille mesh convergence', False,
                           {'error': 'cannot parse mesh or inlet profile'})
    nz = cells[2]
    errors = {}
    for n in (10, 20, 40):
        sub = os.path.join(work_root, 'refine_%d' % n)
        if os.path.exists(sub):
            shutil.rmtree(sub)
        shutil.copytree(case_dir, sub, ignore=shutil.ignore_patterns(
            'postProcessing', 'polyMesh', 'log.*', '[0-9]*.[0-9]*'))
        for d in os.listdir(sub):
            p = os.path.join(sub, d)
            if d != '0' and os.path.isdir(p) and \
                    re.fullmatch(r'\d+(\.\d+)?', d):
                shutil.rmtree(p)
        shutil.rmtree(os.path.join(sub, 'constant', 'polyMesh'),
                      ignore_errors=True)

        # new cell counts
        sub_bm = read_dict(os.path.join(sub, 'system', 'blockMeshDict'))
        sub_bm = re.sub(r'(hex\s*\([^)]*\)\s*)\(\s*\d+\s+\d+\s+\d+\s*\)',
                        r'\g<1>(%d %d %d)' % (n, n, nz), sub_bm)
        with open(os.path.join(sub, 'system', 'blockMeshDict'), 'w') as f:
            f.write(sub_bm)

        # resample the artifact's own inlet profile onto n faces
        u_path = os.path.join(sub, '0', 'U')
        u = read_dict(u_path)
        new_val = resampled_inlet_value(profile, n)
        if new_val is None:
            return gate_result(4, 'Poiseuille mesh convergence', False,
                               {'error': 'cannot resample inlet profile'})
        iblock = get_boundary_block(u, 'inlet')
        # replace the value entry inside the inlet block
        new_iblock = re.sub(
            r'value\s+(nonuniform\s+List<vector>\s*\d+\s*\(.*?\)|'
            r'uniform\s*\([^)]*\))\s*;',
            'value           ' + new_val + ';', iblock, flags=re.DOTALL)
        # rebuild 0/U with the patched inlet block
        m = re.search(r'\binlet\s*\{', u)
        depth, i = 1, m.end()
        while depth:
            if u[i] == '{':
                depth += 1
            elif u[i] == '}':
                depth -= 1
            i += 1
        u = u[:m.end()] + new_iblock + u[i - 1:]
        with open(u_path, 'w') as f:
            f.write(u)

        rc, o, e = run_cmd('blockMesh', sub)
        if rc != 0:
            return gate_result(4, 'Poiseuille mesh convergence', False,
                               {'error': 'blockMesh failed at %dx%d' % (n, n)})
        rc, o, e = run_cmd('icoFoam', sub)
        if rc != 0:
            return gate_result(4, 'Poiseuille mesh convergence', False,
                               {'error': 'icoFoam failed at %dx%d' % (n, n)})
        res = poiseuille_errors(sub)
        if res is None:
            return gate_result(4, 'Poiseuille mesh convergence', False,
                               {'error': 'sampling failed at %dx%d' % (n, n)})
        errors[n] = res[0]

    e10, e20, e40 = errors[10], errors[20], errors[40]
    orders = []
    ok = True
    if e10 > 0 and e20 > 0 and e40 > 0:
        o1 = math.log(e10 / e20) / math.log(2) if e20 < e10 else -1e9
        o2 = math.log(e20 / e40) / math.log(2) if e40 < e20 else -1e9
        orders = [o1, o2]
        avg = (o1 + o2) / 2.0
        ok = o1 >= ORDER_TOL and o2 >= ORDER_TOL
    else:
        avg = None
        ok = False
    return gate_result(4, 'Poiseuille mesh convergence', ok,
                       {'l2_errors': errors, 'orders': orders,
                        'avg_order': avg, 'order_tol': ORDER_TOL})


# ---------------------------------------------------------------------------
# Gate 5 — Cavity vs Ghia et al. 1982 (Re consistency + centreline data)
# ---------------------------------------------------------------------------
def gate5_cavity(case_dir):
    nu = case_nu(case_dir)
    u = read_dict(os.path.join(case_dir, '0', 'U'))
    mwall = get_boundary_block(u, 'movingWall')
    lid = parse_vector_uniform(mwall) if mwall else None
    lid_u = abs(lid[0]) if lid else None
    re = lid_u * 1.0 / nu if (lid_u and nu) else None

    write_sample_dict(case_dir, [
        ('centerline_u', 'y', 400, '(0.5 0 0.05)', '(0.5 1 0.05)'),
        ('centerline_v', 'x', 400, '(0 0.5 0.05)', '(1 0.5 0.05)'),
    ])
    rc, pdir, log = run_sampler(case_dir)
    if not pdir:
        return gate_result(5, 'Cavity vs Ghia', False,
                           {'error': 'sampling failed', 'log': log[-1000:]})
    urows = load_sampled(os.path.join(pdir, 'centerline_u_U.xy'))
    vrows = load_sampled(os.path.join(pdir, 'centerline_v_U.xy'))
    ys = [r[0] for r in urows]
    ux = [r[1] for r in urows]
    xs = [r[0] for r in vrows]
    vy = [r[2] for r in vrows]

    u_errs = {gy: abs(interp_at(gy, ys, ux) - gu)
              for gy, gu in GHIA_U.items()}
    v_errs = {gx: abs(interp_at(gx, xs, vy) - gv)
              for gx, gv in GHIA_V.items()}
    max_u = max(u_errs.values())
    max_v = max(v_errs.values())
    re_ok = re is not None and abs(re - 100.0) / 100.0 <= RE_TOL
    ghia_ok = max_u <= GHIA_TOL and max_v <= GHIA_TOL
    return gate_result(5, 'Cavity vs Ghia et al. 1982',
                       re_ok and ghia_ok,
                       {'Re_measured': re, 'Re_target': 100.0,
                        'nu': nu, 'lid_velocity': lid_u,
                        'max_u_error': max_u, 'max_v_error': max_v,
                        'tol': GHIA_TOL,
                        'u_errors': u_errs, 'v_errors': v_errs,
                        'reference': GHIA_REF})


# ---------------------------------------------------------------------------
# Trace logging (--trace DIR) — output-dense rerun of the same committed
# inputs for figures/video.  The judge itself stays stdlib-only.
# ---------------------------------------------------------------------------
def cell_centres(case_dir):
    """Cell-centre coordinates from the ascii polyMesh (x, y per cell)."""
    pm = os.path.join(case_dir, 'constant', 'polyMesh')

    def blk(name):
        t = open(os.path.join(pm, name)).read()
        m = re.search(r'\n(\d+)\s*\(', t)
        start = m.end()
        depth, j = 1, start
        while depth:
            if t[j] == '(':
                depth += 1
            elif t[j] == ')':
                depth -= 1
            j += 1
        return t[start:j - 1]

    points = [tuple(float(x) for x in l.strip('() ').split())
              for l in blk('points').splitlines() if l.strip()]
    # faces are "N(p0 p1 .. pN-1)" — take the indices inside the parens only
    faces = []
    for l in blk('faces').splitlines():
        l = l.strip()
        if '(' not in l or ')' not in l:
            continue
        faces.append([int(x) for x in
                      l[l.index('(') + 1:l.index(')')].split()])
    owner = [int(x) for x in blk('owner').split()]
    neighb = [int(x) for x in blk('neighbour').split()]
    fc = [tuple(sum(points[i][d] for i in f) / len(f) for d in range(3))
          for f in faces]
    ncell = max(owner) + 1
    cent = [[0.0, 0.0] for _ in range(ncell)]
    cnt = [0] * ncell
    for fi, c in enumerate(owner):
        cent[c][0] += fc[fi][0]; cent[c][1] += fc[fi][1]; cnt[c] += 1
    for fi, c in enumerate(neighb):
        cent[c][0] += fc[fi][0]; cent[c][1] += fc[fi][1]; cnt[c] += 1
    return [(c[0] / n, c[1] / n) for c, n in zip(cent, cnt)]


TRACE_WRITE_INTERVAL = 50   # deltaT 0.01 -> a snapshot every 0.5 s pseudo-time


def trace_run(case_dir, trace_dir, case_type):
    """Re-run the artifact with dense output, for figures and the video.

    Same committed inputs, same solver, same deltaT and endTime as the
    graded run; only writeInterval is reduced so saved time directories
    exist at every TRACE_WRITE_INTERVAL-th step.  Writes:
      residuals.csv    time,Ux,Uy,p — last (initial) residual per step
      cellcentres.csv  x,y of every cell centre (for field plots)
      <t>/U, <t>/p     saved time directories over pseudo-time
      samples/*.xy     the judge's own sample sets at latest time
    """
    sub = os.path.join(os.path.dirname(case_dir), 'trace_case')
    if os.path.exists(sub):
        shutil.rmtree(sub)
    shutil.copytree(case_dir, sub)
    clean_case(sub)
    ctrl_path = os.path.join(sub, 'system', 'controlDict')
    s = read_dict(ctrl_path)
    s2 = re.sub(r'(\bwriteInterval\s+)[\d.eE+-]+(\s*;)',
                r'\g<1>%d\g<2>' % TRACE_WRITE_INTERVAL, s)
    if s2 == s:
        raise RuntimeError('writeInterval not patched for trace run')
    with open(ctrl_path, 'w') as f:
        f.write(s2)

    os.makedirs(trace_dir, exist_ok=True)
    rc, _, _ = run_cmd('blockMesh', sub)
    if rc != 0:
        raise RuntimeError('blockMesh failed in trace run')
    rc, out, err = run_cmd('icoFoam', sub)
    if rc != 0:
        raise RuntimeError('icoFoam failed in trace run')

    bytime = {}
    t = None
    for line in (out + err).split('\n'):
        m = re.search(r'Time\s*=\s*([\d.eE+-]+)', line)
        if m:
            t = float(m.group(1))
            bytime.setdefault(t, {})
            continue
        m = re.search(r'Solving for (\w+), Initial residual = ([\d.eE+-]+)',
                      line)
        if m and t is not None:
            bytime[t][m.group(1)] = float(m.group(2))
    with open(os.path.join(trace_dir, 'residuals.csv'), 'w') as f:
        f.write('time,Ux,Uy,p\n')
        for t in sorted(bytime):
            d = bytime[t]
            f.write('%g,%s,%s,%s\n' % (
                t, d.get('Ux', ''), d.get('Uy', ''), d.get('p', '')))

    cents = cell_centres(sub)
    with open(os.path.join(trace_dir, 'cellcentres.csv'), 'w') as f:
        f.write('x,y\n')
        for x, y in cents:
            f.write('%.6f,%.6f\n' % (x, y))

    # saved time directories (pseudo-time snapshots)
    n_copied = 0
    for d in sorted(glob.glob(os.path.join(sub, '[0-9]*'))):
        base = os.path.basename(d)
        if not os.path.isdir(d) or base == '0' or \
                not re.fullmatch(r'\d+(\.\d+)?', base):
            continue
        dst = os.path.join(trace_dir, base)
        os.makedirs(dst, exist_ok=True)
        for fname in ('U', 'p'):
            shutil.copy2(os.path.join(d, fname), os.path.join(dst, fname))
        n_copied += 1

    # the judge's own sample sets, at latest time
    if case_type == 'poiseuille':
        sets = [('centerline', 'y', 200, '(0.5 0 0.05)', '(0.5 1 0.05)'),
                ('pline', 'x', 200, '(0 0.5 0.05)', '(1 0.5 0.05)')]
    else:
        sets = [('centerline_u', 'y', 400, '(0.5 0 0.05)', '(0.5 1 0.05)'),
                ('centerline_v', 'x', 400, '(0 0.5 0.05)', '(1 0.5 0.05)')]
    write_sample_dict(sub, sets)
    rc, pdir, _ = run_sampler(sub)
    if rc != 0 or not pdir:
        raise RuntimeError('sampling failed in trace run')
    os.makedirs(os.path.join(trace_dir, 'samples'), exist_ok=True)
    for xy in glob.glob(os.path.join(pdir, '*.xy')):
        shutil.copy2(xy, os.path.join(trace_dir, 'samples',
                                      os.path.basename(xy)))

    missing = [f for f in ('residuals.csv', 'cellcentres.csv')
               if not os.path.isfile(os.path.join(trace_dir, f))]
    if missing or n_copied == 0:
        raise RuntimeError('trace incomplete: missing %s' %
                           (missing or 'time directories'))
    return n_copied


def main():
    if len(sys.argv) < 3:
        print('Usage: check_gates.py <case_dir> <poiseuille|cavity> '
              '[--json out.json]')
        sys.exit(2)
    case_dir = os.path.abspath(sys.argv[1])
    case_type = sys.argv[2]
    json_out = None
    if '--json' in sys.argv:
        i = sys.argv.index('--json')
        if i + 1 < len(sys.argv):
            json_out = sys.argv[i + 1]

    if not os.path.isdir(os.path.join(case_dir, 'system')):
        print('ERROR: %s is not an OpenFOAM case directory' % case_dir)
        sys.exit(2)

    trace_dir = None
    if '--trace' in sys.argv:
        i = sys.argv.index('--trace')
        if i + 1 < len(sys.argv):
            trace_dir = os.path.abspath(sys.argv[i + 1])

    clean_case(case_dir)
    results = [gate1_mesh(case_dir), gate2_convergence(case_dir)]
    if case_type == 'poiseuille':
        results.append(gate3_poiseuille(case_dir))
        results.append(gate4_mesh_convergence(
            os.path.dirname(case_dir), case_dir))
    elif case_type == 'cavity':
        results.append(gate5_cavity(case_dir))
    else:
        print('ERROR: unknown case type %s' % case_type)
        sys.exit(2)

    # The verdict JSON must be byte-identical between two runs with the same
    # seed (criterion: DEMO-STANDARD.md "Deterministic").  Wall times are the
    # only fields allowed to differ, so they live under a 'timing' key that
    # selftest.sh excludes before diffing.  Everything else in here is
    # deterministic: icoFoam is linked without OpenMP on this build, the
    # judge sets no thread counts, and the mktemp path is deliberately not
    # recorded.
    verdict = {'case_type': case_type,
               'all_gates_passed': all(r['passed'] for r in results),
               'gates': results}
    if json_out:
        with open(json_out, 'w') as f:
            json.dump(verdict, f, indent=2)
            f.write('\n')
    print(json.dumps(verdict, indent=2))
    if trace_dir:
        n = trace_run(case_dir, trace_dir, case_type)
        print('[trace] %d time directories -> %s' % (n, trace_dir))
    sys.exit(0 if verdict['all_gates_passed'] else 1)


if __name__ == '__main__':
    main()
