#!/usr/bin/env python3
"""check_gates.py -- run the MLS-MPM snow artifact and grade its gates.

Stdlib only.  Invokes `sim.py` with the judged venv's python, reads the
artifact's own `metrics.jsonl`, and evaluates every numeric gate from
SPEC.md.  Prints a single JSON verdict to stdout (or --json).

Usage:
    check_gates.py <artifact_dir> --json out.json [--steps N]

`--steps` overrides params.steps for a short smoke run (mutants use
the full run).

Every physics gate is evaluated on the finite prefix of metrics rows
the artifact managed to write, even when Gate 1 (completion) fails —
a solver that crashes at step k still owes the invariants of every
step it did produce.  A mutant that blows up is therefore killed by
its physics gate AND by completion, not by the crash alone.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time


FIELDS = [
    'step', 'time', 'mass_particles', 'mass_grid_after_p2g',
    'px', 'py', 'ke', 'v_max', 'com_x', 'com_y',
    'vel_com_x', 'vel_com_y',
    'x_min', 'y_min', 'x_max', 'y_max',
    'snow_x_min', 'snow_y_min', 'snow_x_max', 'snow_y_max',
    'jp_min', 'jp_max', 'jp_frac_lt_09', 'jp_frac_gt_11', 'snow_height',
]

T = {
    'mass_rel': 1e-12,
    'grid_mass_rel': 1e-6,
    'freefall_rel': 0.01,
    'freefall_vx_abs': 0.02,
    'boundary_dx': 1.0,           # multiples of dx
    'squash_ratio': 0.93,
    'jp_frac_min': 0.05,
    'px_rel': 0.02,
    'energy_rel': 0.15,           # mechanical energy may never exceed E0*(1+tol)
    'wall_s': float(os.environ.get('SPEC_WALL_S', '1800')),
}


def gate(verdict, name, passed, detail):
    verdict['gates'].append({
        'gate': name,
        'passed': bool(passed),
        'detail': detail,
    })


def finite_row(r):
    if not isinstance(r, dict):
        return False
    for k in FIELDS:
        v = r.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or \
                not math.isfinite(v):
            return False
    mbm = r.get('mass_by_material')
    if not isinstance(mbm, list) or not mbm or \
            not all(isinstance(v, (int, float)) and math.isfinite(v)
                    for v in mbm):
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('artifact')
    ap.add_argument('--json', required=True)
    ap.add_argument('--steps', type=int, default=None)
    ap.add_argument('--seed', type=int, default=None)
    args = ap.parse_args()

    art = os.path.abspath(args.artifact)
    sim_py = os.path.join(art, 'sim.py')
    params_p = os.path.join(art, 'params.json')
    verdict = {'artifact': os.path.basename(art),
               'all_gates_passed': False, 'gates': []}

    venv_py = os.path.expanduser('~/.taichi-mpm-venv/bin/python3')
    python = venv_py if os.path.exists(venv_py) else sys.executable

    if not os.path.isfile(sim_py) or not os.path.isfile(params_p):
        verdict['error'] = 'artifact missing sim.py or params.json'
        json.dump(verdict, open(args.json, 'w'), indent=2)
        sys.exit(2)

    with open(params_p) as f:
        params = json.load(f)

    work = os.path.join(os.path.dirname(args.json), 'run_out')
    os.makedirs(work, exist_ok=True)
    cmd = [python, sim_py, '--params', params_p, '--out', work]
    if args.seed is not None:
        cmd += ['--seed', str(args.seed)]
    if args.steps is not None:
        cmd += ['--steps', str(args.steps)]

    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=T['wall_s'])
    wall = time.monotonic() - t0

    # ---- parse metrics.jsonl into its finite prefix --------------------
    rows = []
    total_lines = 0
    bad_tail = 0                    # lines after the valid prefix
    metrics_p = os.path.join(work, 'metrics.jsonl')
    if os.path.isfile(metrics_p):
        with open(metrics_p) as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                total_lines += 1
                try:
                    r = json.loads(ln)
                except ValueError:
                    bad_tail += 1
                    break
                if not finite_row(r):
                    bad_tail += 1
                    break
                rows.append(r)

    # Gate 1 -- completion and sanity
    want_steps = (args.steps if args.steps is not None
                  else params['steps'])
    g1_ok = (proc.returncode == 0 and wall <= T['wall_s'] and
             len(rows) == want_steps + 1 and bad_tail == 0 and
             total_lines == len(rows))
    gate(verdict, 'completion', g1_ok,
         f'exit={proc.returncode} rows={len(rows)}/{want_steps + 1} '
         f'bad_tail={bad_tail} wall_ok={wall <= T["wall_s"]}')

    if not rows:
        for name in ('mass', 'freefall', 'boundary', 'plasticity',
                     'momentum', 'stability'):
            gate(verdict, name, False, 'no finite metrics rows')
        verdict['all_gates_passed'] = False
        json.dump(verdict, open(args.json, 'w'), indent=2)
        sys.exit(1)

    dx = 1.0 / params['n_grid']
    g = params['gravity']
    dt = params['dt']
    m0 = rows[0]['mass_particles']

    # first step whose SNOW bounding box reaches the boundary layer
    # (the second material may rest on the floor from step 0)
    pad = (params['bound'] + 2) * dx
    t_contact = None
    for i, r in enumerate(rows):
        if r['snow_y_min'] <= pad or \
                r['snow_y_max'] >= params['domain'][1] - pad or \
                r['snow_x_min'] <= pad or \
                r['snow_x_max'] >= params['domain'][0] - pad:
            t_contact = i
            break

    # Gate 2 -- mass conservation and grid-vs-particle agreement
    mass_ok = all(abs(r['mass_particles'] - m0) / m0 <= T['mass_rel']
                  for r in rows)
    grid_ok = all(abs(r['mass_grid_after_p2g'] - r['mass_particles'])
                  / m0 <= T['grid_mass_rel'] for r in rows)
    max_mass = max(abs(r['mass_particles'] - m0) / m0 for r in rows)
    max_grid = max(abs(r['mass_grid_after_p2g'] - r['mass_particles'])
                   / m0 for r in rows)
    gate(verdict, 'mass', mass_ok and grid_ok,
         f'|dm|/m0<={max_mass:.3g} (want <=1e-12); '
         f'|mgrid-m|/m0<={max_grid:.3g} (want <=1e-6)')

    # Gate 3 -- ballistic free flight before first contact
    v0x = rows[0]['px'] / m0
    v0y = rows[0]['py'] / m0
    skip = max(1, int(math.ceil(20 * dt / dt)))
    ff_ok = g < 0                    # gravity must point down
    worst = 0.0
    if t_contact is None or t_contact <= skip:
        ff_ok = False
    else:
        for r in rows[skip:t_contact]:
            exp = v0y + g * r['time']
            rel = abs(r['vel_com_y'] - exp) / max(abs(exp), 1e-9)
            worst = max(worst, rel)
            if rel > T['freefall_rel'] or \
               abs(r['vel_com_x'] - v0x) > T['freefall_vx_abs']:
                ff_ok = False
    gate(verdict, 'freefall', ff_ok,
         f'g={g}<0 t_contact_step={t_contact} '
         f'worst_rel_err={worst:.4g}')

    # Gate 4 -- boundary condition (checked on every finite row, so a
    # penetrator is caught steps before any blow-up)
    b_ok = all(
        r['x_min'] >= dx and r['y_min'] >= dx and
        r['x_max'] <= params['domain'][0] - dx and
        r['y_max'] <= params['domain'][1] - dx for r in rows)
    detail = (f"x_min>={min(r['x_min'] for r in rows):.4g} "
              f"y_min>={min(r['y_min'] for r in rows):.4g} "
              f"x_max<={max(r['x_max'] for r in rows):.4g} "
              f"y_max<={max(r['y_max'] for r in rows):.4g}")
    gate(verdict, 'boundary', b_ok, detail)

    # Gate 5 -- plastic deformation on impact: the snowball must
    # squash in at least one dimension and engage plastic flow
    h0 = rows[0]['snow_height']
    w0 = rows[0]['snow_x_max'] - rows[0]['snow_x_min']
    rf = rows[-1]
    hr = rf['snow_height'] / h0
    wr = (rf['snow_x_max'] - rf['snow_x_min']) / w0
    jp_frac = rf['jp_frac_lt_09'] + rf['jp_frac_gt_11']
    gate(verdict, 'plasticity',
         min(hr, wr) <= T['squash_ratio'] and jp_frac >= T['jp_frac_min'],
         f'height_ratio={hr:.4g} width_ratio={wr:.4g} '
         f'(want min<=0.93) jp_frac={jp_frac:.4g} (want >=0.05)')

    # Gate 6 -- horizontal momentum: px[0] must match the momentum the
    # params claim (mass_by_material x v0), and px must be conserved
    # while the snowball is still in free flight
    px_exp = 0.0
    for i, m in enumerate(params['materials']):
        v0 = m.get('v0', [0.0, 0.0])
        if i < len(rows[0]['mass_by_material']):
            px_exp += rows[0]['mass_by_material'][i] * v0[0]
    px0_err = abs(rows[0]['px'] - px_exp) / m0
    pre = rows[:t_contact] if t_contact is not None else rows
    px_drift = max(abs(r['px'] - rows[0]['px']) / m0 for r in pre)
    gate(verdict, 'momentum',
         px0_err <= T['px_rel'] and px_drift <= T['px_rel'],
         f'|px0-expected|/m0={px0_err:.4g} '
         f'max|px-px0|/m0={px_drift:.4g} (want <=0.02)')

    # Gate 7 -- mechanical-energy bound (stability): an explicit
    # scheme with too-large dt injects energy each step, so the run
    # blows up long before NaN if the gate watches it
    pe = [m0 * (-g) * r['com_y'] for r in rows]
    e = [r['ke'] + p for r, p in zip(rows, pe)]
    e0 = e[0]
    e_ratio = max(x / e0 for x in e) if e0 > 0 else float('inf')
    gate(verdict, 'stability',
         e_ratio <= 1.0 + T['energy_rel'],
         f'max E/E0={e_ratio:.4g} (want <=1+{T["energy_rel"]})')

    verdict['all_gates_passed'] = all(gt['passed']
                                    for gt in verdict['gates'])
    json.dump(verdict, open(args.json, 'w'), indent=2)
    sys.exit(0 if verdict['all_gates_passed'] else 1)


if __name__ == '__main__':
    main()
