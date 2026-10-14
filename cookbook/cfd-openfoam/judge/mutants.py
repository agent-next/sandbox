#!/usr/bin/env python3
"""
Generate known-bad mutant cases for self-testing the judge.
Each mutant is a single-edit copy of a known-good case and must fail at
least one gate.  Output goes to examples/bad/ (gitignored, regenerated).
"""

import os
import re
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = os.path.join(BASE, 'examples', 'good')
BAD = os.path.join(BASE, 'examples', 'bad')


def clone(src, dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def read(p):
    with open(p) as f:
        return f.read()


def write(p, s):
    with open(p, 'w') as f:
        f.write(s)


def patch_block(content, patch, new_body):
    """Replace the {...} body of `patch { ... }` (balanced braces)."""
    m = re.search(r'\b' + re.escape(patch) + r'\s*\{', content)
    if not m:
        raise RuntimeError('patch %s not found' % patch)
    depth, i = 1, m.end()
    while i < len(content) and depth:
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
        i += 1
    if depth:
        raise RuntimeError('unbalanced braces at %s' % patch)
    return content[:m.end()] + new_body + content[i - 1:]


def set_nu(case, nu):
    p = os.path.join(case, 'constant', 'transportProperties')
    s = read(p)
    s2 = re.sub(r'(\bnu\s+)[\d.eE+-]+(\s*;)', r'\g<1>%g\g<2>' % nu, s)
    if s2 == s:
        raise RuntimeError('nu not patched')
    write(p, s2)


def set_cells(case, nx, ny):
    p = os.path.join(case, 'system', 'blockMeshDict')
    s = read(p)
    s2 = re.sub(r'(hex\s*\([^)]*\)\s*)\(\s*\d+\s+\d+\s+\d+\s*\)',
                r'\g<1>(%d %d 1)' % (nx, ny), s)
    if s2 == s:
        raise RuntimeError('cells not patched')
    write(p, s2)


def set_end_time(case, t):
    p = os.path.join(case, 'system', 'controlDict')
    s = read(p)
    s2 = re.sub(r'(\bendTime\s+)[\d.eE+-]+(\s*;)', r'\g<1>%g\g<2>' % t, s)
    if s2 == s:
        raise RuntimeError('endTime not patched')
    write(p, s2)


def main():
    poi = os.path.join(GOOD, 'poiseuille')
    cav = os.path.join(GOOD, 'cavity')
    os.makedirs(BAD, exist_ok=True)

    # -- poiseuille mutants ---------------------------------------------------
    # 1. uniform inlet instead of fully-developed parabolic profile
    d = clone(poi, os.path.join(BAD, 'poiseuille_wrong_bc'))
    p = os.path.join(d, '0', 'U')
    write(p, patch_block(read(p), 'inlet',
                         '\n        type            fixedValue;\n'
                         '        value           uniform (1 0 0);\n    '))

    # 2. viscosity 10x too large -> Re = 10, not 100
    d = clone(poi, os.path.join(BAD, 'poiseuille_wrong_viscosity'))
    set_nu(d, 0.05)

    # 3. much too coarse mesh (5x5): L2 error vs analytic exceeds 2 %
    d = clone(poi, os.path.join(BAD, 'poiseuille_coarse_mesh'))
    set_cells(d, 5, 5)

    # 4. run stops before reaching steady state
    d = clone(poi, os.path.join(BAD, 'poiseuille_unconverged'))
    set_end_time(d, 0.05)

    # 5. outlet pinned to U=0: mass cannot leave the channel
    d = clone(poi, os.path.join(BAD, 'poiseuille_wrong_outlet'))
    p = os.path.join(d, '0', 'U')
    write(p, patch_block(read(p), 'outlet',
                         '\n        type            fixedValue;\n'
                         '        value           uniform (0 0 0);\n    '))

    # -- cavity mutants -------------------------------------------------------
    # 6. lid moves at half speed -> Re = 50, not 100
    d = clone(cav, os.path.join(BAD, 'cavity_wrong_lid'))
    p = os.path.join(d, '0', 'U')
    write(p, patch_block(read(p), 'movingWall',
                         '\n        type            fixedValue;\n'
                         '        value           uniform (0.5 0 0);\n    '))

    # 7. viscosity 10x too large -> Re = 10
    d = clone(cav, os.path.join(BAD, 'cavity_wrong_viscosity'))
    set_nu(d, 0.1)

    # 8. too coarse mesh (10x10): max error vs Ghia exceeds tolerance
    d = clone(cav, os.path.join(BAD, 'cavity_coarse_mesh'))
    set_cells(d, 10, 10)

    # 9. run stops before reaching steady state
    d = clone(cav, os.path.join(BAD, 'cavity_unconverged'))
    set_end_time(d, 0.2)

    # 10. slip walls instead of no-slip on the fixed walls
    d = clone(cav, os.path.join(BAD, 'cavity_slip_wall'))
    p = os.path.join(d, '0', 'U')
    write(p, patch_block(read(p), 'fixedWalls',
                         '\n        type            slip;\n    '))

    print('Created 10 mutants in %s' % BAD)


if __name__ == '__main__':
    sys.exit(main())
