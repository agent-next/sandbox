#!/usr/bin/env python3
"""judge/mutants.py — regenerate the known-bad artifacts.

Each mutant is a single-edit copy of examples/good that must fail at
least one gate.  Run by selftest.sh; writes to examples/bad/<name>/.
"""

import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = os.path.join(HERE, "..", "examples", "good")
BAD = os.path.join(HERE, "..", "examples", "bad")


def fresh(name):
    dst = os.path.join(BAD, name)
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(GOOD, dst)
    return dst


def manifest(dst):
    p = os.path.join(dst, "artist.json")
    return p, json.load(open(p))


def html(dst):
    p = os.path.join(dst, "index.html")
    return p, open(p).read()


def write(p, s):
    open(p, "w").write(s)


def main():
    os.makedirs(BAD, exist_ok=True)
    made = []

    # 1. fake effect — a type the pinned registry does not export.
    d = fresh("fake-type")
    p, m = manifest(d)
    m["effects"][0] = {"type": "NotARealEffect", "region": "hero-aurora"}
    json.dump(m, open(p, "w"), indent=2)
    made.append("fake-type")

    # 2. inline-shader — page ships its own GLSL (hand-written shader).
    d = fresh("inline-shader")
    p, h = html(d)
    write(p, h.replace(
        "</body>",
        "<script>const fs = 'precision mediump float; void main(){"
        " gl_FragColor = vec4(1.0,0.0,0.0,1.0); }';</script>\n</body>"))
    made.append("inline-shader")

    # 3. missing-region — manifest points at an element that is not there.
    d = fresh("missing-region")
    p, m = manifest(d)
    m["effects"][2] = {"type": "FlowingGradient", "region": "hero-gone"}
    json.dump(m, open(p, "w"), indent=2)
    made.append("missing-region")

    # 4. overflow — fixed 2000px wide element forces horizontal scroll.
    d = fresh("overflow")
    p, h = html(d)
    write(p, h.replace(
        "</header>",
        "  <div style=\"width:2000px;height:10px\"></div>\n</header>"))
    made.append("overflow")

    # 5. tiny-region — effect region shrunk below the 100/80px floors.
    d = fresh("tiny-region")
    p, h = html(d)
    write(p, h.replace(
        ".fx .stage { height: 180px; }",
        ".fx .stage { height: 40px; }"))
    made.append("tiny-region")

    # 6. no-h1 — the hero headline is required.
    d = fresh("no-h1")
    p, h = html(d)
    write(p, h.replace("<h1>", "<p>").replace("</h1>", "</p>"))
    made.append("no-h1")

    # 7. console-error — page throws on load.
    d = fresh("console-error")
    p, h = html(d)
    write(p, h.replace(
        "</body>",
        "<script>throw new Error('boom');</script>\n</body>"))
    made.append("console-error")

    # 8. static-effect — ConicGradient is a real library export but does
    #    not animate; gate 3 must kill it.
    d = fresh("static-effect")
    p, m = manifest(d)
    m["effects"][0] = {"type": "ConicGradient", "region": "hero-aurora"}
    json.dump(m, open(p, "w"), indent=2)
    made.append("static-effect")

    print("[mutants] wrote:", ", ".join(made))


if __name__ == "__main__":
    main()
