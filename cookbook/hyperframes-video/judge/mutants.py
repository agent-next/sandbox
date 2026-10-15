#!/usr/bin/env python3
"""Generate known-bad mutant artifacts for self-testing the judge.

Each mutant is a single-edit copy of examples/good/ and must fail at least
one gate.  Output goes to examples/bad/ (gitignored, regenerated).
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


def html_path(d):
    return os.path.join(d, 'composition', 'index.html')


def spec_path(d):
    return os.path.join(d, 'spec.json')


def edit_html(d, fn):
    p = html_path(d)
    s = fn(open(p).read())
    open(p, 'w').write(s)


def edit_spec(d, fn):
    p = spec_path(d)
    spec = json.load(open(p))
    spec = fn(spec)
    open(p, 'w').write(json.dumps(spec, indent=2) + '\n')


def sub1(s, pat, rep, what):
    s2 = re.sub(pat, rep, s, count=1)
    if s2 == s:
        raise RuntimeError('%s: pattern not found' % what)
    return s2


def main():
    os.makedirs(BAD, exist_ok=True)
    made = []

    # 1. wrong-duration — stage claims 20 s while spec.json still says 24 s:
    #    caught by input validation (data-duration must equal duration_s).
    d = clone(os.path.join(BAD, 'wrong-duration'))
    edit_html(d, lambda s: sub1(
        s, r'data-duration="24"', 'data-duration="20"', 'data-duration'))
    made.append('wrong-duration')

    # 2. missing-beat — beat 2 removed from DOM and timeline; spec keeps it.
    d = clone(os.path.join(BAD, 'missing-beat'))
    def drop_beat(s):
        s = sub1(s, r'\s*<div id="beat2".*?</div></div>', '', 'beat2 element')
        s = sub1(s, r'\s*\{ id: "#beat2"[^}]*\},?', '', 'beat2 timeline')
        return s
    edit_html(d, drop_beat)
    made.append('missing-beat')

    # 3. black-gap — an opaque overlay covers the stage for 1.5 s (8.0-9.5).
    d = clone(os.path.join(BAD, 'black-gap'))
    def add_gap(s):
        s = sub1(s, r'(<div id="track">)',
                 '<div id="gap" style="position:absolute;inset:0;'
                 'background:#000;opacity:0;z-index:99;"></div>\n  \\1',
                 'gap element')
        s = sub1(s, r'(tl\.fromTo\("#fill")',
                 'tl.fromTo("#gap", { opacity: 0 }, { opacity: 1, duration: 0.01 }, 8.0)\n'
                 '      .to("#gap", { opacity: 0, duration: 0.01 }, 9.5);\n'
                 '  \\1', 'gap timeline')
        return s
    edit_html(d, add_gap)
    made.append('black-gap')

    # 4. wrong-resolution — stage renders 640x360; spec keeps 1280x720.
    d = clone(os.path.join(BAD, 'wrong-resolution'))
    def shrink(s):
        for a, b in (('width=1280, height=720', 'width=640, height=360'),
                     ('width: 1280px; height: 720px', 'width: 640px; height: 360px'),
                     ('data-width="1280" data-height="720"',
                      'data-width="640" data-height="360"')):
            s = sub1(s, re.escape(a), b, a)
        return s
    edit_html(d, shrink)
    made.append('wrong-resolution')

    # 5. off-brand-colors — brand colours rotated to non-brand values;
    #    spec keeps the declared palette.
    d = clone(os.path.join(BAD, 'off-brand-colors'))
    def rotate(s):
        s = s.replace('#4F46E5', '#10B981').replace('#F59E0B', '#EC4899')
        if '#10B981' not in s:
            raise RuntimeError('colour rotation failed')
        return s
    edit_html(d, rotate)
    made.append('off-brand-colors')

    # 6. broken-js — the vendored gsap script is never loaded, so
    #    gsap.timeline throws and no timeline registers: render fails.
    d = clone(os.path.join(BAD, 'broken-js'))
    edit_html(d, lambda s: sub1(
        s, r'\s*<script src="gsap\.min\.js"></script>', '', 'gsap script'))
    made.append('broken-js')

    # 7. frozen-video — continuous-motion tweens removed; static holds
    #    freeze longer than the 2 s gate.
    d = clone(os.path.join(BAD, 'frozen-video'))
    def freeze(s):
        for pat in (r'\s*tl\.fromTo\("#fill"[^;]*;', r'\s*tl\.fromTo\("#blob-a"[^;]*;',
                    r'\s*tl\.fromTo\("#blob-b"[^;]*;'):
            s = sub1(s, pat, '', 'motion tween')
        return s
    edit_html(d, freeze)
    made.append('frozen-video')

    # 8. nondeterministic — a Math.random()-driven tween makes the two
    #    judge renders visibly diverge; SSIM drops below the gate.
    d = clone(os.path.join(BAD, 'nondeterministic'))
    def jitter(s):
        s = sub1(s, r'\{ x: 160, y: 90, duration: 24',
                 '{ x: 200 + Math.random() * 600, y: Math.random() * 300, duration: 24',
                 'random drift')
        return s
    edit_html(d, jitter)
    made.append('nondeterministic')

    print('Created %d mutants in %s: %s' % (len(made), BAD, ', '.join(made)))


if __name__ == '__main__':
    sys.exit(main())
