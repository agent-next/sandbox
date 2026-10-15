#!/usr/bin/env python3
"""Capture real browser frames of the known-good site for media/.

Run with the judge venv python after judge/setup.sh:

    ~/.taste-judge/venv/bin/python media/make_frames.py [--out media]

Writes full-page screenshots at 1440/768/375 px plus a scroll-capture
frame series at 1440x900 (the site's reveal animations need real
scrolling to show). Frames over 300 KB are quantised to a 256-colour
palette when Pillow is available (flat brand colours survive it).
"""

import argparse
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "..", "examples", "good", "site")
FRAMES = 10
VIEW_W, VIEW_H = 1440, 900


def quantize_if_big(path, limit=300 * 1024):
    if os.path.getsize(path) <= limit:
        return
    try:
        from PIL import Image
    except ImportError:
        print(f"  note: {path} > {limit} bytes and Pillow is not installed")
        return
    im = Image.open(path).convert("RGB")
    im.quantize(colors=256, method=Image.MEDIANCUT,
                dither=Image.FLOYDSTEINBERG).save(path, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    url = "file://" + os.path.abspath(os.path.join(SITE, "index.html"))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        # full-page shots at the three judge widths
        for w in (1440, 768, 375):
            page = browser.new_page(viewport={"width": w, "height": 900})
            page.goto(url, wait_until="load")
            page.wait_for_timeout(700)
            # force every reveal on, so the full page is in final state
            page.evaluate("document.querySelectorAll('.reveal')"
                          ".forEach(e => e.classList.add('revealed'))")
            page.wait_for_timeout(700)
            p = os.path.join(out, f"site-{w}.png")
            page.screenshot(path=p, full_page=True)
            quantize_if_big(p)
            print("wrote", p, os.path.getsize(p) // 1024, "KB")
            page.close()

        # scroll frame series at desktop width
        page = browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H})
        page.goto(url, wait_until="load")
        page.wait_for_timeout(700)
        total = page.evaluate(
            "document.documentElement.scrollHeight - window.innerHeight")
        for i in range(FRAMES):
            y = round(total * i / (FRAMES - 1))
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(750)  # let reveals play
            p = os.path.join(out, f"scroll-{i:02d}.png")
            page.screenshot(path=p)
            quantize_if_big(p)
            print("wrote", p, os.path.getsize(p) // 1024, "KB")
        page.close()
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
