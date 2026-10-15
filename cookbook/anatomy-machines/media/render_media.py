#!/usr/bin/env python3
"""Render media/ for the anatomy-machines demo.

Drives the real figure in headless Chromium (the judge's own toolchain:
Playwright + Chrome Headless Shell + SwiftShader WebGL). Every PNG and every
demo.mp4 frame is an actual screenshot of the rendered scene — nothing is
synthesized or interpolated.

Usage: render_media.py <media_dir>   (run by media/make_media.sh)
"""

import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

MEDIA = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else
                        os.path.join(os.path.dirname(__file__)))
DEMO = os.path.dirname(MEDIA)
FIG = os.path.join(DEMO, "examples", "good", "four-stroke-engine")
MASTER = os.path.join(MEDIA, "master")
FRAMES = os.path.join(MASTER, "frames")
PORT = 8893
FPS = 30
CHROMIUM_ARGS = ["--enable-unsafe-swiftshader", "--disable-gpu"]


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def timeline(t):
    """(yaw deg, explode 0..1, label opacity 0..1) at time t seconds.

    assembled turntable -> explode -> labelled hold -> reassemble -> settle.
    """
    if t < 3.5:
        return 15 + 45 * (t / 3.5), 0.0, 0.0
    if t < 10.0:
        u = (t - 3.5) / 6.5
        return 60 + 80 * u, smooth(u), 0.0
    if t < 14.0:
        return 140 + 30 * ((t - 10.0) / 4.0), 1.0, smooth((t - 10.0) / 1.0)
    if t < 19.5:
        u = (t - 14.0) / 5.5
        return 170 + 60 * u, 1.0 - smooth(u), 1.0 - smooth((t - 14.0) / 0.8)
    return 230 + 15 * ((t - 19.5) / 1.5), 0.0, 0.0


DURATION = 21.0          # seconds -> 630 frames at 30 fps


def main():
    # --start N: crash recovery only — resume the frame loop at frame N,
    # skipping the stills (make_media.sh always runs a full 0..N pass).
    start = 0
    if len(sys.argv) > 2 and sys.argv[2].startswith("--start"):
        arg = sys.argv[2]
        start = int(arg.split("=", 1)[1]) if "=" in arg else int(sys.argv[3])
    os.makedirs(FRAMES, exist_ok=True)
    srv = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT),
         "--bind", "127.0.0.1", "--directory", FIG],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    url = f"http://127.0.0.1:{PORT}/four-stroke-engine.html"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=CHROMIUM_ARGS)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})

            # ---- stills -----------------------------------------------------
            if start == 0:
                page.goto(url + "?shot=1&labels=1&explode=0.72&yaw=35",
                          wait_until="load")
                page.wait_for_timeout(1200)
                page.locator("#stageView").screenshot(
                    path=os.path.join(MASTER, "exploded.png"))

                page.goto(url + "?shot=1&labels=0&explode=0&yaw=35",
                          wait_until="load")
                page.wait_for_timeout(1200)
                page.locator("#stageView").screenshot(
                    path=os.path.join(MEDIA, "assembled.png"))

            # ---- demo frames ------------------------------------------------
            page.goto(url + "?shot=1&labels=1", wait_until="load")
            page.wait_for_timeout(800)
            stage = page.locator("#stageView")
            n = int(DURATION * FPS)
            t0 = time.monotonic()
            for i in range(start, n):
                yaw, ex, lab = timeline(i / FPS)
                page.evaluate(
                    "__fig.set({yaw: %r, explode: %r, labels: %r})"
                    % (yaw, ex, lab))
                stage.screenshot(path=os.path.join(FRAMES, "f%04d.png" % i))
                if i % 90 == 0:
                    print("[media] frame %d/%d (%.1fs)" %
                          (i, n, time.monotonic() - t0), flush=True)
            browser.close()
    finally:
        srv.kill()

    # ---- encode: lossless master, then web h264 -----------------------------
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(FPS),
         "-i", os.path.join(FRAMES, "f%04d.png"),
         "-c:v", "libx264", "-crf", "0", "-preset", "slow",
         "-pix_fmt", "yuv420p", os.path.join(MASTER, "master.mp4")],
        check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", os.path.join(MASTER, "master.mp4"),
         "-c:v", "libx264", "-crf", "18", "-preset", "slow",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         os.path.join(MEDIA, "demo.mp4")],
        check=True)

    print("[media] wrote master/exploded.png, assembled.png, "
          "master/master.mp4, demo.mp4")


if __name__ == "__main__":
    main()
