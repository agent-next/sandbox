#!/usr/bin/env python3
"""Generate known-bad mutant artifacts for self-testing the judge.

Each mutant is a single-region edit of examples/good/ and must fail at
least one gate.  Output goes to examples/bad/ (gitignored, regenerated).
"""

import json
import os
import re
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = os.path.join(BASE, 'examples', 'good')
BAD = os.path.join(BASE, 'examples', 'bad')

# The good composition's <script> body is replaced wholesale by the two
# "static" mutants — one region swapped for a minimal timeline.
SCRIPT_RE = r'<script>\s*\n  window\.__timelines[\s\S]*?</script>'

STATIC_BODY = '''<script>
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  document.querySelector("#typed1").textContent =
      "Ideas arrive fast. Catch them.";
  document.querySelector("#counter").textContent = "128,400";
  document.querySelector("#qtext").textContent = "plan";
  [["#title", 0.4, 2.6], ["#beat1", 3.4, 4.0], ["#beat2", 7.8, 3.8],
   ["#beat3", 12.0, 4.0], ["#endcard", 16.4, 3.4]].forEach(function (b) {
    tl.set(b[0], { opacity: 1 }, b[1]).set(b[0], { opacity: 0 }, b[1] + b[2]);
  });
  EXTRA
  window.__timelines["main"] = tl;
  tl.seek(0);
</script>'''

# A 50x50 square teleporting between four fixed corners every 0.5 s:
# enough per-frame pixel change that freezedetect never sees a >2 s run,
# but under gate 6's meaningful-diff floor (~0.4% of the frame), so only
# the frame-motion gate kills it.
DECOY = '''var pos = [[620, 300], [1420, 700], [760, 760], [1380, 300]];
  for (var i = 0; i < 40; i++)
    tl.set("#shim", { x: pos[i % 4][0], y: pos[i % 4][1] }, i * 0.5);'''


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

    # 1. wrong-duration — stage claims 16 s while spec.json still says 20 s:
    #    caught by input validation (data-duration must equal duration_s).
    d = clone(os.path.join(BAD, 'wrong-duration'))
    edit_html(d, lambda s: sub1(
        s, r'data-duration="20"', 'data-duration="16"', 'data-duration'))
    made.append('wrong-duration')

    # 2. missing-beat — beat 2 removed from DOM and timeline; spec keeps it.
    d = clone(os.path.join(BAD, 'missing-beat'))
    def drop_beat(s):
        s = sub1(s, r'\n  <div id="beat2" class="beat">[\s\S]*?\n  <div id="beat3"',
                 '\n  <div id="beat3"', 'beat2 element')
        for pat in (r'[ \t]*beatIO\("#beat2"[^;]*;\n?',
                    r'[ \t]*wordsIn\("#beat2[^;]*;\n?',
                    r'[ \t]*tl\.fromTo\("#b2wrap"[\s\S]*?8\.1\);\n?',
                    r'[ \t]*const cnode[\s\S]*?CDUR\);\n  \}\n?',
                    r'[ \t]*tl\.fromTo\("#b2wrap \.bar"[\s\S]*?8\.45\);\n?',
                    r'[ \t]*tl\.fromTo\("#beat2 \.dev"[\s\S]*?9\.2\);\n?',
                    r'[ \t]*tl\.fromTo\("#syncdot"[\s\S]*?8\.9\);\n?'):
            s = sub1(s, pat, '', 'beat2 timeline')
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

    # 4. wrong-resolution — stage renders 640x360; spec keeps 1920x1080.
    d = clone(os.path.join(BAD, 'wrong-resolution'))
    def shrink(s):
        s = s.replace('width=1920, height=1080', 'width=640, height=360')
        s = s.replace('width: 1920px; height: 1080px',
                      'width: 640px; height: 360px')
        s = sub1(s, r'data-width="1920" data-height="1080"',
                 'data-width="640" data-height="360"', 'data-width')
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

    # 7. frozen-video — the whole motion script is swapped for instant
    #    opacity toggles; static holds freeze longer than the 2 s gate 4
    #    limit (and gate 6 counts almost no moving pairs).
    d = clone(os.path.join(BAD, 'frozen-video'))
    edit_html(d, lambda s: sub1(
        s, SCRIPT_RE, STATIC_BODY.replace('EXTRA', ''), 'static script'))
    made.append('frozen-video')

    # 8. nondeterministic — a Math.random()-driven tween makes the two
    #    judge renders visibly diverge; SSIM drops below the gate.
    d = clone(os.path.join(BAD, 'nondeterministic'))
    def jitter(s):
        s = sub1(s, r'\{ x: 420, y: 170, scale: 1\.18',
                 '{ x: 200 + Math.random() * 600, y: Math.random() * 300, scale: 1.18',
                 'random drift')
        return s
    edit_html(d, jitter)
    made.append('nondeterministic')

    # 9. static-composition — like frozen-video but with a decoy square
    #    teleporting every 0.5 s: freezedetect never sees a 2 s run, so
    #    only gate 6 (frame-motion) can kill it.
    d = clone(os.path.join(BAD, 'static-composition'))
    def decoy(s):
        s = sub1(s, r'(<div id="track">)',
                 '<div id="shim" style="position:absolute;left:0;top:0;'
                 'width:50px;height:50px;background:#F59E0B;opacity:0.5;'
                 'border-radius:12px;"></div>\n  \\1', 'shim element')
        s = sub1(s, SCRIPT_RE, STATIC_BODY.replace('EXTRA', DECOY),
                 'static script')
        return s
    edit_html(d, decoy)
    made.append('static-composition')

    # 10. text-overflow — headline font triples so words leave the stage,
    #     and the typed line is clipped by a fixed-width hidden-overflow box.
    d = clone(os.path.join(BAD, 'text-overflow'))
    def overflow(s):
        s = sub1(s, r'font-size: 62px;', 'font-size: 170px;', 'headline size')
        s = sub1(s, r'(\.caret \{)',
                 '#typed1 { display: inline-block; max-width: 120px; '
                 'overflow: hidden; vertical-align: bottom; }\n  \\1',
                 'typed clip')
        return s
    edit_html(d, overflow)
    made.append('text-overflow')

    print('Created %d mutants in %s: %s' % (len(made), BAD, ', '.join(made)))


if __name__ == '__main__':
    sys.exit(main())
