"""judge/check_gates.py -- pixel + widget gates for the ovui-native-ui demo.

Usage:
    python check_gates.py <facts1.json> <shot1.png> <reference.json> \
        <facts2.json> <shot2.png> [--json out.json]

Exit 0 only if every gate passes. The verdict JSON is printed and, with
--json, written to a file. Every predicate is numeric and comes from the
SPEC; the swatch colour target in reference.json is the analytic sRGB value
of the spec colour, and the tolerance band is the known-good's measured
render jitter.
"""
import hashlib
import json
import sys

import numpy as np
from PIL import Image

# ---- fixed spec (SPEC.md) -------------------------------------------------
TITLE = "Tool Panel"
SLIDER_RANGES = [(0.0, 10.0), (0.0, 20.0), (0.0, 50.0)]
SWATCH_RGBA = (0.2, 0.5, 0.9, 1.0)
SWATCH_W, SWATCH_H = 140, 24
WINDOW_W, WINDOW_H = 420, 360
REF_NAMES = ["button", "checkbox", "slider1", "slider2", "slider3", "swatch", "window"]

# title bar + border inset of the window content region (measured)
TITLEBAR_H = 26
BORDER = 4
# widget bbox tolerances (px)
POS_TOL, SIZE_TOL = 8, 4
# luminance predicates (0..255)
DRAWN_DELTA, DRAWN_MIN_PX = 20, 20
TITLE_DELTA, TITLE_MIN_PX = 20, 25
BTN_DELTA, BTN_MIN_PX = 28, 25


def _rect(facts, name):
    f = facts.get(name, {})
    try:
        return (int(round(f["screen_position_x"])), int(round(f["screen_position_y"])),
                int(round(f["computed_width"])), int(round(f["computed_height"])))
    except (KeyError, TypeError, ValueError):
        return None


def _close(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


def gate0_render(facts, shot):
    try:
        im = np.asarray(Image.open(shot).convert("RGB"), dtype=float)
    except Exception as e:
        return {"gate": "rendered_png", "ok": False, "error": str(e)}
    h, w = im.shape[0], im.shape[1]
    ok = w >= WINDOW_W and h >= WINDOW_H
    return {"gate": "rendered_png", "ok": bool(ok), "size": [w, h]}


def gate1_widgets(facts):
    detail = {}
    win = facts.get("window", {})
    win_ok = (win.get("type") == "Window" and win.get("title") == TITLE
              and (win.get("width") or 0) >= WINDOW_W - 1e-6
              and (win.get("height") or 0) >= WINDOW_H - 1e-6)
    detail["window_ok"] = win_ok

    # every required name must be present; extra refs are allowed (an agent
    # may return a helper ref, which does not make the panel invalid)
    names = facts.get("_ref_names") or []
    missing = [n for n in REF_NAMES if n not in names]
    refs_ok = not missing
    detail["ref_names_missing"] = missing

    sliders_ok = True
    seen = set()
    for i, (lo, hi) in enumerate(SLIDER_RANGES, start=1):
        s = facts.get(f"slider{i}", {})
        good = (s.get("type") == "FloatSlider"
                and _close(s.get("min"), lo, 1e-6)
                and _close(s.get("max"), hi, 1e-6)
                and s.get("screen_position_x") is not None)
        sliders_ok = sliders_ok and good
        if good:
            seen.add((round(s["min"], 6), round(s["max"], 6)))
    detail["sliders_ok"] = sliders_ok
    detail["sliders_distinct"] = len(seen) == 3

    ch = facts.get("checkbox", {})
    btn = facts.get("button", {})
    sw = facts.get("swatch", {})
    detail["checkbox_ok"] = ch.get("type") == "CheckBox"
    detail["button_ok"] = (btn.get("type") == "Button"
                           and "Apply" in str(btn.get("text", "")))
    color_ok = False
    if isinstance(sw.get("color"), list) and len(sw["color"]) >= 3:
        color_ok = all(abs(sw["color"][i] - SWATCH_RGBA[i]) < 1e-6 for i in range(3))
    detail["swatch_color_ok"] = color_ok
    size_ok = (_close(sw.get("computed_width"), SWATCH_W, 2)
               and _close(sw.get("computed_height"), SWATCH_H, 2))
    detail["swatch_size_ok"] = size_ok
    detail["swatch_type_ok"] = sw.get("type") == "ColorWidget"

    ok = all([win_ok, refs_ok, sliders_ok, detail["sliders_distinct"],
              detail["checkbox_ok"], detail["button_ok"], color_ok, size_ok,
              detail["swatch_type_ok"]])
    return {"gate": "widget_tree", "ok": bool(ok), "detail": detail}


def gate2_pixels(facts, shot, ref):
    im = np.asarray(Image.open(shot).convert("RGB"), dtype=float)
    lum = im.mean(axis=2)
    detail = {}

    win = facts.get("window", {})
    try:
        wx, wy = float(win["position_x"]), float(win["position_y"])
        ww, wh = float(win["width"]), float(win["height"])
    except (KeyError, TypeError, ValueError):
        return {"gate": "pixels", "ok": False,
                "detail": {"error": "window rect missing from facts"}}
    # content region: window inset by title bar and border
    cx0, cy0 = wx + BORDER, wy + TITLEBAR_H
    cx1, cy1 = wx + ww - BORDER, wy + wh - BORDER

    names = ("slider1", "slider2", "slider3", "swatch", "checkbox", "button")
    rects = {n: _rect(facts, n) for n in names}
    detail["rects_missing"] = [n for n, r in rects.items() if r is None]
    if detail["rects_missing"]:
        return {"gate": "pixels", "ok": False, "detail": detail}

    # no overflow: every widget rect fully inside the window content region
    overflow = [n for n, (x, y, w, h) in rects.items()
                if not (cx0 <= x and x + w <= cx1 and cy0 <= y and y + h <= cy1)]
    detail["overflow"] = overflow

    # expected bboxes
    bbox_bad = []
    for n, exp in ref["bbox"].items():
        got = rects.get(n)
        if got is None or not all(
                _close(got[i], exp[i], POS_TOL if i < 2 else SIZE_TOL)
                for i in range(4)):
            bbox_bad.append(n)
    detail["bbox_mismatch"] = bbox_bad

    # window background: an empty band inside the content region, below the
    # lowest widget (the known-good layout leaves the lower half empty)
    ybot = max(y + h for (_x, y, _w, h) in rects.values())
    bg_band = lum[int(ybot) + 8:int(cy1) - 8, int(cx0) + 8:int(cx1) - 8]
    if bg_band.size == 0:
        detail["error"] = "no background band inside the window"
        return {"gate": "pixels", "ok": False, "detail": detail}
    bg = float(np.median(bg_band))
    detail["bg_lum"] = bg

    # swatch colour: median RGB of the rect inset 3 px vs the analytic target
    sx, sy, sw_w, sw_h = rects["swatch"]
    inner = im[sy + 3:sy + sw_h - 3, sx + 3:sx + sw_w - 3]
    if inner.size == 0:
        detail["swatch"] = "empty interior"
        return {"gate": "pixels", "ok": False, "detail": detail}
    med = [float(np.median(inner[:, :, c])) for c in range(3)]
    std = [float(inner[:, :, c].std()) for c in range(3)]
    detail["swatch_median"] = [round(v, 2) for v in med]
    detail["swatch_std"] = [round(v, 3) for v in std]
    detail["swatch_target"] = ref["swatch_rgb"]
    swatch_ok = (all(abs(m - t) <= tol
                     for m, t, tol in zip(med, ref["swatch_rgb"], ref["swatch_tol"]))
                 and all(s <= ref["swatch_uniform_std_max"] for s in std))
    detail["swatch_ok"] = bool(swatch_ok)

    # widgets drawn: interior differs from the window background
    undrawn = []
    for n in names:
        x, y, w, h = rects[n]
        sub = lum[y + 2:y + h - 2, x + 2:x + w - 2]
        if sub.size == 0 or int((np.abs(sub - bg) > DRAWN_DELTA).sum()) < DRAWN_MIN_PX:
            undrawn.append(n)
    detail["undrawn"] = undrawn

    # title text: the title-bar band contains text pixels
    band = lum[int(wy) + 2:int(wy) + TITLEBAR_H - 2, int(wx) + 2:int(wx + ww) - 2]
    bm = float(np.median(band))
    title_px = int((np.abs(band - bm) > TITLE_DELTA).sum()) if band.size else 0
    detail["title_px"] = title_px
    title_ok = title_px >= TITLE_MIN_PX

    # button text: pixels differing from the button face
    bx, by, bw, bh = rects["button"]
    bout = lum[by + 2:by + bh - 2, bx + 2:bx + bw - 2]
    bface = float(np.median(bout)) if bout.size else 0.0
    btn_px = int((np.abs(bout - bface) > BTN_DELTA).sum()) if bout.size else 0
    detail["button_face_lum"] = bface
    detail["button_text_px"] = btn_px
    btn_ok = btn_px >= BTN_MIN_PX

    ok = (not overflow) and (not bbox_bad) and swatch_ok and (not undrawn) \
        and title_ok and btn_ok
    return {"gate": "pixels", "ok": bool(ok), "detail": detail}


def gate3_determinism(shot1, shot2):
    try:
        h1 = hashlib.sha256(open(shot1, "rb").read()).hexdigest()
        h2 = hashlib.sha256(open(shot2, "rb").read()).hexdigest()
    except OSError as e:
        return {"gate": "determinism", "ok": False, "error": str(e)}
    return {"gate": "determinism", "ok": bool(h1 == h2),
            "sha256": h1[:16]}


def main():
    args = sys.argv[1:]
    if len(args) < 5:
        raise SystemExit(
            "usage: check_gates.py <facts1> <shot1> <reference.json> "
            "<facts2> <shot2> [--json out.json]")
    facts1_p, shot1_p, ref_p, facts2_p, shot2_p = args[:5]
    json_out = args[args.index("--json") + 1] if "--json" in args else None

    facts1 = json.load(open(facts1_p))
    json.load(open(facts2_p))  # must be readable; determinism is the render
    ref = json.load(open(ref_p))

    gates = [gate0_render(facts1, shot1_p)]
    if gates[0]["ok"]:
        gates.append(gate1_widgets(facts1))
        gates.append(gate2_pixels(facts1, shot1_p, ref))
        gates.append(gate3_determinism(shot1_p, shot2_p))
    verdict = {"pass": all(g["ok"] for g in gates), "gates": gates}
    if json_out:
        with open(json_out, "w") as f:
            json.dump(verdict, f, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(0 if verdict["pass"] else 1)


if __name__ == "__main__":
    main()
