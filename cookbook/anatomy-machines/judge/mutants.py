#!/usr/bin/env python3
"""
Generate known-bad mutant figures for self-testing the judge (SPEC.md).
Each mutant is a single-edit copy of the good four-stroke-engine figure and
must fail at least one gate.  Output goes to examples/bad/ (committed, and
regenerated identically by judge/selftest.sh before grading).
"""

import os
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = os.path.join(BASE, 'examples', 'good', 'four-stroke-engine',
                    'four-stroke-engine.html')
BAD = os.path.join(BASE, 'examples', 'bad')


def edit(src, old, new):
    """One exact string edit; refuse silently-matching no-ops."""
    if old not in src:
        raise RuntimeError('mutant target not found: %r' % old[:60])
    return src.replace(old, new, 1)


def main():
    with open(GOOD) as f:
        good = f.read()
    os.makedirs(BAD, exist_ok=True)

    mutants = {
        # 1. no parts are ever drawn: background + labels only -> gates 2, 6
        'blank_canvas': (
            'for (const p of PARTS) drawPart(p, cam.mvp, viewRot);',
            '/* mutant: solid pass removed */'),
        # 2. the parts list stops after 8 of 17 parts -> recall 0.47 -> gate 3
        'missing_parts': (
            'for (const p of PARTS) {\n  const li = document.createElement("li");',
            'for (const p of PARTS.slice(0, 8)) {\n  const li = document.createElement("li");'),
        # 3. the page throws on load -> console/page error -> gate 1
        'console_error': (
            '"use strict";',
            '"use strict"; throw new Error("mutant: broken figure");'),
        # 4. dragging no longer turns the camera -> identical frames -> gate 2
        'static_camera': (
            'yawDeg += (e.clientX - lastX) * 0.4;',
            '/* mutant: camera frozen */;'),
        # 5. every part is relabelled -> recall 0 -> gate 3 (and gate 4)
        'wrong_labels': (
            'li.textContent = p.name;',
            'li.textContent = "gizmo " + li.dataset.part;'),
        # 6. clicking a part never shows its info -> gate 4
        'no_interaction': (
            'li.addEventListener("click", () => select(p));',
            'li.addEventListener("click", () => {});'),
        # 7. the showcase capture shrinks to 40% of the viewport -> gate 6
        'tiny_capture': (
            'html.shot .stage-view { position: fixed; inset: 0; }',
            'html.shot .stage-view { position: fixed; inset: 30%; }'),
    }

    for name, (old, new) in mutants.items():
        d = os.path.join(BAD, name)
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)
        with open(os.path.join(d, 'four-stroke-engine.html'), 'w') as f:
            f.write(edit(good, old, new))

    print('Created %d mutants in %s' % (len(mutants), BAD))
    return 0


if __name__ == '__main__':
    sys.exit(main())
