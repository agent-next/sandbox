#!/usr/bin/env python3
"""check_gates.py -- run the MLS-MPM snow artifact and grade its gates.

Stdlib only.  Invokes `sim.py` with the judged venv's python, reads the
artifact's own `metrics.jsonl`, and evaluates every numeric gate from
SPEC.md.  Prints a single JSON verdict to stdout (or --json).

Usage:
    check_gates.py <artifact_dir> --json out.json [--steps N]

`--steps` overrides params.steps for a short smoke run (mutants use
the full run).
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
    'px', 'py', 'com_x', 'com_y', 'vel_com_x', 'vel_com_y',
    'x_min', 'y_min', 'x_max', 'y_max',
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
    'wall_s': float(os.environ.get('SPEC_WALL_S', '1800')),
}


def fail_gate(gate, passed, detail, verdict, short=True):
    verdict['gates'].append({
        'gate': gate,
        'passed': bool(passed),
        'detail': detail,
    })


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

    # Gate 1 -- completion and sanity
    g1_ok = proc.returncode == 0 and wall <= T['wall_s']
    rows = []
    metrics_p = os.path.join(work, 'metrics.jsonl')
    if g1_ok and os.path.isfile(metrics_p):
        with open(metrics_p) as f:
            for ln in f:
                rows.append(json.loads(ln))
        want_steps = (args.steps if args.steps is not None
                      else params['steps'])
        g1_ok = g1_ok and len(rows) == want_steps + 1
        for r in rows:
            for k in FIELDS:
                v = r.get(k)
                if v is None or \
                   (isinstance(v, float) and not math.isfinite(v)):
                    g1_ok = False
    fail_gate('completion', g1_ok,
              f'exit={proc.returncode} rows={len(rows)} '
              f'wall_ok={wall <= T["wall_s"]}',
              verdict)
    if not g1_ok:
        verdict['all_gates_passed'] = False
        json.dump(verdict, open(args.json, 'w'), indent=2)
        sys.exit(1)

    dx = 1.0 / params['n_grid']
    g = params['gravity']
    dt = params['dt']

    # Gate 2 -- mass conservation
    m0 = rows[0]['mass_particles']
    mass_ok = all(abs(r['mass_particles'] - m0) / m0 <= T['mass_rel']
                  for r in rows)
    grid_ok = all(abs(r['mass_grid_after_p2g'] - r['mass_particles'])
                  / m0 <= T['grid_mass_rel'] for r in rows)
    max_mass = max(abs(r['mass_particles'] - m0) / m0 for r in rows)
    max_grid = max(abs(r['mass_grid_after_p2g'] - r['mass_particles'])
                   / m0 for r in rows)
    fail_gate('mass', mass_ok and grid_ok,
              f'|dm|/m0<={max_mass:.3g} (want <=1e-12); '
              f'|mgrid-m|/m0<={max_grid:.3g} (want <=1e-6)',
              verdict)

    # Gate 3 -- free-fall before contact
    ymin_contact = params['bound'] * dx + 2 * dx
    t_contact = None
    for i, r in enumerate(rows):
        if r['y_min'] <= ymin_contact:
            t_contact = i
            break
    ff_ok = t_contact is not None
    worst = 0.0
    if t_contact is not None:
        skip = max(1, int(math.ceil(20 * dt / dt)))
        for r in rows[skip:t_contact]:
            if r['time'] <= 0:
                continue
            exp = g * r['time']
            rel = abs(r['vel_com_y'] - exp) / abs(exp)
            worst = max(worst, rel)
            if rel > T['freefall_rel'] or \
               abs(r['vel_com_x']) > T['freefall_vx_abs']:
                ff_ok = False
    fail_gate('freefall', ff_ok,
              f't_contact_step={t_contact} worst_rel_err={worst:.4g}',
              verdict)

    # Gate 4 -- boundary
    b_ok = all(
        r['x_min'] >= dx and r['y_min'] >= dx and
        r['x_max'] <= params['domain'][0] - dx and
        r['y_max'] <= params['domain'][1] - dx for r in rows)
    detail = (f"x_min>={min(r['x_min'] for r in rows):.4g} "
              f"y_min>={min(r['y_min'] for r in rows):.4g} "
              f"x_max<={max(r['x_max'] for r in rows):.4g} "
              f"y_max<={max(r['y_max'] for r in rows):.4g}")
    fail_gate('boundary', b_ok, detail, verdict)

    # Gate 5 -- plastic deformation
    h0 = rows[0]['snow_height']
    hn = rows[-1]['snow_height']
    jp_frac = rows[-1]['jp_frac_lt_09'] + rows[-1]['jp_frac_gt_11']
    fail_gate(
        'plasticity',
        hn / h0 <= T['squash_ratio'] and jp_frac >= T['jp_frac_min'],
        f'height_ratio={hn/h0:.4g} (want <=0.93) '
        f'jp_frac={jp_frac:.4g} (want >=0.05)',
        verdict)

    # Gate 6 -- horizontal momentum
    px_ok = all(abs(r['px']) / m0 <= T['px_rel'] for r in rows)
    px_max = max(abs(r['px']) / m0 for r in rows)
    fail_gate('momentum', px_ok,
              f'max |px|/m0={px_max:.3g} (want <=0.02)', verdict)

    verdict['all_gates_passed'] = all(g['passed'] for g in verdict['gates'])
    json.dump(verdict, open(args.json, 'w'), indent=2)
    sys.exit(0 if verdict['all_gates_passed'] else 1)


if __name__ == '__main__':
    main()
