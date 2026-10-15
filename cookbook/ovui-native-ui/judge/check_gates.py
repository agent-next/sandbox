"""judge/check_gates.py -- pixel + model gates for the ovui-native-ui demo.

Usage:
    python check_gates.py <facts.json> <screenshot.png> \
        <reference.json> <facts2.json> <screenshot2.png> --json out.json

Exit 0 only if every gate passes; prints the verdict JSON (also written to
--json when given). The `timing` key is filled in by the caller via
second render; byte-identical verdicts across runs except timing are the
self-test's determinism gate.
"""
import hashlib
import json
import sys

import numpy as np
from PIL import Image

# SPEC (fixed)
TITLE = "Tool Panel"
SLIDER_RANGES = [(0.0, 10.0), (0.0, 20.0), (0.0, 50.0)]
SWATCH_RGBA = (0.2, 0.5, 0.9, 1.0)
SWATCH_W, SWATCH_H = 140, 24
WINDOW_MIN_W, WINDOW_MIN_H = 420, 360


def _med(sub, c):
    return float(np.median(sub[:, :, c]))


def gate_results(facts, facts2, shot, shot2, ref):
    g = []

    # Gate 0: screenshot exists & big enough
    try:
        im = np.asarray(Image.open(shot).convert("RGB"), dtype=float)
        ok = im.shape[1] >= WINDOW_MIN_W and im.shape[0] >= WINDOW_MIN_H
        g.append({"gate": "rendered_png", "ok": bool(ok),
                  "size": [int(im.shape[1]), int(im.shape[0])]})
    except Exception as e:
        g.append({"gate": "rendered_png", "ok": False, "error": str(e)})
        return g

    # Gate 1: widget objects / models from the artifact's own builder
    ok = facts.get("window", {}).get("type") == "Window" and \
        facts["window"].get("title") == TITLE
    ok1 = ok
    sliders_ok = True
    for i, (lo, hi) in enumerate(SLIDER_RANGES, start=1):
        s = facts.get(f"slider{i}", {})
        good = (s.get("type") == "FloatSlider"
                and abs(s.get("min", -999) - lo) < 1e-6
                and abs(s.get("max", -999) - hi) < 1e-6)
        sliders_ok = sliders_ok and good
    ch = facts.get("checkbox", {})
    btn = facts.get("button", {})
    sw = facts.get("swatch", {})
    color_ok = False
    if "color" in sw and len(sw["color"]) >= 3:
        color_ok = all(abs(sw["color"][i] - SWATCH_RGBA[i]) < 1e-6 for i in range(3))
    sw_size_ok = (abs(sw.get("computed_width", -1) - SWATCH_W) <= 2
                  and abs(sw.get("computed_height", -1) - SWATCH_H) <= 2)
    g.append({"gate": "widget_tree", "ok": bool(ok1 and sliders_ok
             and ch.get("type") == "CheckBox"
             and btn.get("type") == "Button"
             and "Apply" in str(btn.get("text", ""))
             and sw.get("type") == "ColorWidget"
             and color_ok and sw_size_ok),
              "detail": {"window_ok": ok1, "sliders_ok": sliders_ok,
                          "color_ok": color_ok, "sw_size_ok": sw_size_ok}})

    # Gate 2: pixel spec mask. Window content rect = bounding box of the
    # widget rects, expanded by the VStack padding (8 px on each side).
    lum = im[:, :, :].mean(axis=2)  # luminance proxy

    def rect_facts(name):
        w = facts.get(name, {})
        return (int(round(w.get("screen_position_x", -100))),
                int(round(w.get("screen_position_y", -100))),
                int(round(w.get("computed_width", 0))),
                int(round(w.get("computed_height", 0))))

    names = ("slider1", "slider2", "slider3", "checkbox", "button", "swatch")
    rects = {n: rect_facts(n) for n in names}
    PAD = 8
    xs0 = [r[0] for r in rects.values() if r[2] > 0]
    ys0 = [r[1] for r in rects.values() if r[3] > 0]
    xs1 = [r[0] + r[2] for r in rects.values() if r[2] > 0]
    ys1 = [r[1] + r[3] for r in rects.values() if r[3] > 0]
    ok = len(xs0) == len(rects)
    if ok:
        wx0, wy0 = min(xs0) - PAD, min(ys0) - PAD
        wx1, wy1 = max(xs1) + PAD, max(ys1) + PAD
        inside_ok = all(
            wx0 + 0 <= x and x + w <= wx1 and wy0 + 0 <= y and y + h <= wy1
            for (x, y, w, h) in rects.values())
    else:
        wx0 = wy0 = wx1 = wy1 = 0
        inside_ok = False

    # swatch: interior (ring of 2 px by its edge) must be uniform spec color
    sx, sy, swd, sht = rects.get("swatch", (-1, -1, 0, 0))
    swatch_ok = False
    swatch_med = None
    edge_var = None
    if sht > 8 and swd > 8:
        interior = im[sy + 3:sy + sht - 3, sx + 3:sx + swd - 3]
        swatch_med = [_med(interior, 0), _med(interior, 1), _med(interior, 2)]
        tgt = ref["swatch_rgb"]
        band = ref["swatch_tol"]
        uniform = float(lum[sy + 3:sy + sht - 3, sx + 3:sx + swd - 3].var()) \
            <= bg_var + 4.0
        swatch_ok = uniform and all(
            abs(a - b) <= c for a, b, c in zip(swatch_med, tgt, band))
        # edge ring (widget border) must differ from the interior
        edge_var = float(lum[sy:sy + 2, sx:sx + swd].var()) \
            + float(lum[sy + sht - 2:sy + sht, sx:sx + swd].var()) \
            + float(lum[sy:sy + sht, sx:sx + 2].var()) \
            + float(lum[sy:sy + sht, sx + swd - 2:sx + swd].var())
        edge_var_ok = edge_var > 4.0
    else:
        edge_var_ok = False

    # per-widget non-empty: interior needs >= 20 pixels differing from the
    # uniform window background by >= 20 on the luminance scale
    drawn_ok = inside_ok and edge_var_ok
    if bg_var < 1.0 and wy1 > wy0:
        # background reference: 4-px-wide strip right of the slider column
        bg_ref_x = wx0 + int(round((wx1 - wx0) * 0.75))
        bg_ref = np.median(lum[wy0 + 6:wy1 - 6, bg_ref_x:bg_ref_x + 2]) \
            if bg_ref_x + 2 < im.shape[1] else 0.0
    else:
        bg_ref = 0.0
    for n in ("slider1", "slider2", "slider3", "checkbox", "button", "swatch"):
        x, y, w, h = rects[n]
        if w < 6 or h < 6:
            drawn_ok = False
            break
        sub = lum[y + 2:y + h - 2, x + 2:x + w - 2]
        if sub.size == 0 or int((abs(sub - bg_ref) > 20).sum()) < 20:
            drawn_ok = False
            break

    # button text: at least 25 pixels darker/lighter than the button face
    bx, by, bw, bh = rects["button"]
    bg_btn = 41.0  # darkest widget face in the palette
    bout = lum[by + 4:by + bh - 4, bx + 8:bx + bw - 8]
    btn_text_ok = bout.size > 0 and int((abs(bout - bg_btn) > 28).sum()) >= 25

    g.append({"gate": "pixels", "ok": bool(inside_ok and swatch_ok
                                          and drawn_ok and btn_text_ok),
              "detail": {"inside_ok": inside_ok, "swatch_ok": bool(swatch_ok),
                          "swatch_med": swatch_med, "drawn_ok": drawn_ok,
                          "btn_text_ok": bool(btn_text_ok)}})

    # Gate 3: determinism -- the two runs must be byte-identical
    try:
        h1 = hashlib.sha256(open(shot, "rb").read()).hexdigest()
        h2 = hashlib.sha256(open(shot2, "rb").read()).hexdigest()
        same = h1 == h2
    except Exception as e:
        same = False
    g.append({"gate": "determinism", "ok": bool(same)})

    return g


def main():
    args = sys.argv[1:]
    facts_p, shot_p, ref_p, facts2_p, shot2_p = args[:5]
    json_out = None
    if "--json" in args:
        json_out = args[args.index("--json") + 1]
    facts = json.load(open(facts_p))
    facts2 = json.load(open(facts2_p))
    ref = json.load(open(ref_p))
    verdict = {"pass": False, "gates": []}
    verdict["gates"] = gate_results(facts, facts2, shot_p, shot2_p, ref)
    verdict["pass"] = all(g["ok"] for g in verdict["gates"])
    if json_out:
        json.dump(verdict, open(json_out, "w"), indent=2)
    print(json.dumps(verdict, indent=2))
    sys.exit(0 if verdict["pass"] else 1)


if __name__ == "__main__":
    main()
