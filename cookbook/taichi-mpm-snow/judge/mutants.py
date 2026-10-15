#!/usr/bin/env python3
"""Generate known-bad mutant artifacts for the self-test.

Each mutant is a single-edit copy of examples/good/ that must be killed
by at least one gate.  Output goes to examples/bad/ (gitignored,
regenerated on every self-test run).
"""

import json
import os
import re
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = os.path.join(BASE, 'examples', 'good')
BAD = os.path.join(BASE, 'examples', 'bad')


def clone(dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(GOOD, dst)
    return dst


def edit_py(dst, old, new):
    p = os.path.join(dst, 'sim.py')
    s = open(p).read()
    if old not in s:
        raise RuntimeError(f'pattern not found in {p}: {old!r}')
    open(p, 'w').write(s.replace(old, new, 1))


def edit_params(dst, mut):
    p = os.path.join(dst, 'params.json')
    j = json.load(open(p))
    mut(j)
    open(p, 'w').write(json.dumps(j, indent=2))


def main():
    os.makedirs(BAD, exist_ok=True)

    # 1. gravity sign flipped -> free-fall gate dies (snow rises)
    d = clone(os.path.join(BAD, 'gravity_flipped'))
    edit_params(d, lambda j: j.update(gravity=abs(j['gravity'])))

    # 2. dt 20x too large -> blow-up, non-finite metrics (Gate 1)
    d = clone(os.path.join(BAD, 'dt_too_large'))
    edit_params(d, lambda j: j.update(dt=j['dt'] * 20.0))

    # 3. boundary condition removed -> boundary gate dies on the
    #    finite prefix before any blow-up
    d = clone(os.path.join(BAD, 'no_boundary'))
    edit_py(d,
            "if i < bound and grid_v[i, j].x < 0:",
            "if i < 0 and grid_v[i, j].x < 0:")
    edit_py(d,
            "if i > n_grid - 1 - bound and grid_v[i, j].x > 0:",
            "if i > n_grid - 1 + 999 and grid_v[i, j].x > 0:")
    edit_py(d,
            "if j < bound and grid_v[i, j].y < 0:",
            "if j < 0 and grid_v[i, j].y < 0:")
    edit_py(d,
            "if j > n_grid - 1 - bound and grid_v[i, j].y > 0:",
            "if j > n_grid - 1 + 999 and grid_v[i, j].y > 0:")

    # 4. P2G weight bug: drop one stencil corner -> mass not conserved
    d = clone(os.path.join(BAD, 'p2g_weight_bug'))
    edit_py(d,
            "for gj in ti.static(range(3)):\n"
            "                    offset = ti.Vector([gi, gj])",
            "for gj in ti.static(range(2)):\n"
            "                    offset = ti.Vector([gi, gj])")

    # 5. hardening 0 + plasticity clamp off -> no plastic deformation
    d = clone(os.path.join(BAD, 'no_plasticity'))
    def _no_plastic(j):
        for m in j['materials']:
            if m['name'] == 'snow':
                m['hardening'] = 0.0
                m['jp_min'] = 1e-9
                m['jp_max'] = 1e9
    edit_params(d, _no_plastic)

    # 6. v0 injected that the params do not declare -> momentum gate
    #    dies (measured px[0] disagrees with mass_by_material x v0)
    d = clone(os.path.join(BAD, 'v0_mismatch'))
    edit_py(d,
            "        v_np[a:b, 0] = mats[mi]['v0'][0]",
            "        v_np[a:b, 0] = mats[mi]['v0'][0] + 0.6")

    print('Created 6 mutants in %s' % BAD)
    return 0


if __name__ == '__main__':
    sys.exit(main())
