#!/usr/bin/env python3
"""Playwright grader for the anatomy-machines demo (SPEC.md gates 1-5).

Headless Chromium + SwiftShader WebGL on CPU. Everything the judge believes
comes from what it drives itself: real pointer drags, real clicks, pixels it
screenshots and measures, and a requestAnimationFrame counter it injects.
The artifact's own claims are never read.

Usage: check_gates.py <url> [--seed N] [--json out.json] [--shots dir]
                      [--reference judgedir/reference]

Exit 0 only if every gate passes.  All run-varying measurements (wall time,
measured fps) live under "timing" so two runs at the same seed give
byte-identical verdict JSON outside that key.
"""

import argparse
import io
import json
import sys
import time

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

VARIANCE_MIN = 50.0     # gate 2: grayscale population variance, 0-255 scale
MAD_MIN = 3.0           # gate 2: mean abs pixel diff between consecutive angles
CHANGED_MIN = 0.02      # gate 2: fraction of pixels differing by > 30 levels
RECALL_MIN = 0.8        # gate 3: fraction of reference parts present
INFO_DESC_MIN = 20      # gate 4: chars of description beyond the part name
FPS_FLOOR = 10.0        # gate 5: frames per second under SwiftShader on 2 vCPU
SETTLE_S = 1.2
CHROMIUM_ARGS = ["--enable-unsafe-swiftshader", "--disable-gpu"]


def gray_stats(png_bytes):
    """(population variance, grayscale image) of a PNG screenshot."""
    img = Image.open(io.BytesIO(png_bytes)).convert("L")
    hist = img.histogram()
    n = sum(hist)
    mean = sum(i * h for i, h in enumerate(hist)) / n
    var = sum(h * (i - mean) ** 2 for i, h in enumerate(hist)) / n
    return var, img


def mean_abs_diff(a, b):
    diff = ImageChops.difference(a, b)
    hist = diff.histogram()
    n = sum(hist)
    return sum(i * h for i, h in enumerate(hist)) / n


def changed_fraction(a, b, threshold=30):
    """Fraction of pixels whose grayscale differs by more than threshold."""
    hist = ImageChops.difference(a, b).histogram()
    n = sum(hist)
    return sum(hist[threshold + 1:]) / n


def slugify(text):
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", default="")
    ap.add_argument("--shots", default="")
    ap.add_argument("--reference", default="")
    args = ap.parse_args()

    t0 = time.monotonic()
    errors = {"console": 0, "page": 0}

    def on_console(msg):
        if msg.type == "error":
            errors["console"] += 1

    def on_pageerror(_exc):
        errors["page"] += 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=CHROMIUM_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 980})
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        resp = page.goto(args.url, wait_until="load", timeout=20000)
        http_ok = resp is not None and resp.ok

        # let the page settle; then snapshot the error counters
        page.wait_for_timeout(int(SETTLE_S * 1000))

        g1 = {"gate": 1, "name": "loads_clean"}
        g1["http_ok"] = bool(http_ok)
        try:
            canvas = page.locator("canvas").first
            canvas.wait_for(state="visible", timeout=8000)
            box = canvas.bounding_box()
            g1["canvas_w"] = int(box["width"]) if box else 0
            g1["canvas_h"] = int(box["height"]) if box else 0
        except Exception:
            g1["canvas_w"] = g1["canvas_h"] = 0
        g1["webgl"] = bool(page.evaluate(
            "() => { const c = document.querySelector('canvas');"
            " return !!c && !!(c.getContext('webgl') || c.getContext('webgl2')); }"))
        g1["console_errors"] = errors["console"] + errors["page"]
        g1["passed"] = (g1["http_ok"] and g1["canvas_w"] >= 480 and g1["canvas_h"] >= 360
                        and g1["webgl"] and g1["console_errors"] == 0)

        machine = page.evaluate(
            "() => { const el = document.querySelector('[data-machine]');"
            " return el ? (el.dataset.machine || el.textContent.trim()) : ''; }")
        machine = slugify(machine or "unknown")

        # ---- gate 2: three identical drags; blank + rotation checks --------
        g2 = {"gate": 2, "name": "rotates_nonblank",
              "variance_min": VARIANCE_MIN, "mad_min": MAD_MIN,
              "changed_min": CHANGED_MIN}
        variances, mads, fracs = [], [], []
        prev_img = None
        for angle_i in range(3):
            canvas = page.locator("canvas").first
            box = canvas.bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            page.mouse.move(cx, cy)
            page.mouse.down()
            for step in range(1, 13):        # 12 steps of 20 px = 240 px drag
                page.mouse.move(cx + step * 20, cy)
                page.wait_for_timeout(30)
            page.mouse.up()
            page.wait_for_timeout(250)       # let a frame render
            png = canvas.screenshot()
            var, img = gray_stats(png)
            variances.append(round(var, 1))
            if prev_img is not None:
                mads.append(round(mean_abs_diff(prev_img, img), 1))
                fracs.append(round(changed_fraction(prev_img, img), 4))
            prev_img = img
            if args.shots:
                with open(f"{args.shots}/angle_{angle_i}.png", "wb") as f:
                    f.write(png)
        # a rotation frame series for media: re-shoot mid-drag frames
        if args.shots:
            box = page.locator("canvas").first.bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            page.mouse.move(cx, cy)
            page.mouse.down()
            for step in range(8):
                page.mouse.move(cx + (step + 1) * 30, cy)
                page.wait_for_timeout(120)
                page.locator("canvas").first.screenshot(path=f"{args.shots}/spin_{step:02d}.png")
            page.mouse.up()
        g2["variances"] = variances
        g2["mean_abs_diffs"] = mads
        g2["changed_fractions"] = fracs
        g2["passed"] = (len(variances) == 3 and min(variances) >= VARIANCE_MIN
                        and len(mads) == 2 and min(mads) >= MAD_MIN
                        and min(fracs) >= CHANGED_MIN)

        # ---- gate 3: parts vs textbook reference ---------------------------
        g3 = {"gate": 3, "name": "parts_coverage", "recall_min": RECALL_MIN}
        scene = page.evaluate(
            "() => Array.from(document.querySelectorAll('[data-part]'))"
            ".map(el => ({id: el.dataset.part, name: el.textContent.trim()}))")
        names = [p["name"].strip().lower() for p in scene]
        g3["n_scene_parts"] = len(names)
        ref_path = f"{args.reference}/{machine}.json"
        try:
            with open(ref_path) as f:
                reference = json.load(f)
        except OSError:
            g3["error"] = f"missing {ref_path}"
            reference = {"parts": []}
        ref_parts = [p.lower() for p in reference.get("parts", [])]
        g3["n_reference"] = len(ref_parts)
        matched = sum(1 for r in ref_parts if r in names)
        g3["recall"] = round(matched / len(ref_parts), 3) if ref_parts else 0.0
        g3["duplicates"] = len(names) - len(set(names))
        g3["passed"] = (g3["recall"] >= RECALL_MIN and g3["duplicates"] == 0
                        and g3["n_reference"] > 0)

        # ---- gate 4: click every reference part, read the info panel -------
        g4 = {"gate": 4, "name": "interaction", "desc_min": INFO_DESC_MIN}
        info_ok = 0
        info_total = 0
        for ref in ref_parts:
            el = None
            for p in scene:
                if p["name"].strip().lower() == ref:
                    el = page.locator(f'[data-part="{p["id"]}"]').first
                    break
            if el is None:
                continue
            info_total += 1
            el.click()
            page.wait_for_timeout(120)
            text = page.evaluate(
                "() => { const el = document.querySelector('[data-part-info]');"
                " return el ? el.innerText : ''; }") or ""
            flat = " ".join(text.split())
            has_name = p["name"].strip().lower() in flat.lower()
            desc_len = len(flat) - len(p["name"]) if has_name else 0
            if has_name and desc_len >= INFO_DESC_MIN:
                info_ok += 1
        g4["info_ok"] = info_ok
        g4["info_total"] = info_total
        g4["passed"] = info_total > 0 and info_ok == info_total

        # ---- gate 5: frames per second, counted by the judge ---------------
        g5 = {"gate": 5, "name": "frame_rate", "fps_floor": FPS_FLOOR}
        fps = page.evaluate(
            """() => new Promise(resolve => {
                 let frames = 0;
                 const t0 = performance.now();
                 function tick() {
                   frames++;
                   if (performance.now() - t0 < 3000) requestAnimationFrame(tick);
                   else resolve(frames / ((performance.now() - t0) / 1000));
                 }
                 requestAnimationFrame(tick);
               })""")
        g5["fps_pass"] = bool(fps >= FPS_FLOOR)
        g5["passed"] = g5["fps_pass"]

        browser.close()

    verdict = {
        "artifact": args.url.rsplit("/", 1)[-1] or args.url,
        "machine": machine,
        "seed": args.seed,
        "gates": [g1, g2, g3, g4, g5],
        "all_gates_passed": all(g["passed"] for g in (g1, g2, g3, g4, g5)),
        "timing": {
            "wall_seconds": round(time.monotonic() - t0, 3),
            "measured_fps": round(fps, 1),
        },
    }
    out = json.dumps(verdict, indent=2) + "\n"
    if args.json:
        with open(args.json, "w") as f:
            f.write(out)
    print(out, end="")
    sys.exit(0 if verdict["all_gates_passed"] else 1)


if __name__ == "__main__":
    main()
