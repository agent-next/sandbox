#!/usr/bin/env python3
"""media/make_frames.py -- capture the real ovui frames the video is cut from.

Run by make_media.sh with the *judge* venv (it needs omni.ui and Pillow),
under the same environment judge/grade.sh uses:

    OMNIUI_HEADLESS=1 OMNIUI_LAVAPIPE=1 OMNIUI_BACKEND=vulkan \
        LD_LIBRARY_PATH=<cuda-stub> \
        <judge venv>/bin/python -I make_frames.py <demo_dir> <out_dir>

It imports the known-good artifact the judge grades (examples/good/panel.py),
builds the panel once, and drives the panel across the offscreen surface --
a real camera move: the window is repositioned and resized, the panel
content is not touched. Every frame is a real 1280x720 lavapipe render of
the real panel, captured with the same pre-bound screenshot path
judge/render.py uses. Nothing is interpolated, morphed or synthesised.

The path is a ping-pong (triangle) with smoothstep easing over CAM_HALF
frames per sweep, and CAM_N is a whole number of cycles, so any 2*CAM_HALF
slice loops. make_video.py composites HUD/captions onto these frames and
cuts between the takes.
"""
import asyncio
import importlib.util
import json
import os
import sys

os.environ.setdefault("OMNIUI_HEADLESS", "1")
os.environ.setdefault("OMNIUI_LAVAPIPE", "1")
os.environ.setdefault("OMNIUI_BACKEND", "vulkan")

from omni.ui import _ui  # noqa: E402  (env vars must be set first)
from omni.ui.standalone import _tick_one_frame, run as UI_RUN  # noqa: E402

SETTLE_FRAMES = 9

# Ping-pong path: CAM_HALF frames per sweep, CAM_CYCLES sweeps out and back.
CAM_HALF = 60
CAM_CYCLES = 5
CAM_N = CAM_HALF * 2 * CAM_CYCLES

# Geometry of the move inside the 1280x720 offscreen surface. The panel is
# pushed across and into the camera: x/y fall while w/h grow, and (x + w,
# y + h) never leaves the surface, so the whole window stays on-screen.
X0, X1 = 700, 20
Y0, Y1 = 300, 40
W0, W1 = 420, 860
H0, H1 = 360, 620


def _tick(n=1):
    for _ in range(n):
        _tick_one_frame()


def _screenshot(path):
    """The capture path judge/render.py uses (pre-bound C functions)."""
    if _ui._schedule_screenshot(path):
        _tick_one_frame()
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon(loop.stop)
            loop.run_forever()
        except RuntimeError:
            pass
        if not _ui._poll_screenshot_done():
            return False
        result = _ui._get_screenshot_result()
        return bool(result.get("success", False)) if result else True
    return _ui._capture_screenshot(path)


async def _settle(n):
    for _ in range(n):
        _tick_one_frame()
        await asyncio.sleep(0)


def _smooth(t):
    """Smoothstep, so the move eases at the ends of each sweep."""
    return t * t * (3.0 - 2.0 * t)


def _triangle(i):
    """Position along the ping-pong path in [0, 1].

    Half linear, half smoothstep: the eased ends stop the move snapping at
    the turnarounds, and the linear middle keeps the per-frame step above
    the video gate's motion threshold for most of the sweep.
    """
    phase = (i / CAM_HALF) % 2.0
    tri = phase if phase < 1.0 else 2.0 - phase
    return 0.5 * tri + 0.5 * _smooth(tri)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: make_frames.py <demo_dir> <out_dir>")
    demo_dir = os.path.abspath(sys.argv[1])
    out_dir = os.path.abspath(sys.argv[2])
    os.makedirs(out_dir, exist_ok=True)

    panel_path = os.path.join(demo_dir, "examples", "good", "panel.py")
    spec = importlib.util.spec_from_file_location("panel_artifact", panel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    state = {"cam": 0, "boxes": []}

    async def _run():
        window, _refs = mod.build_panel()
        await _settle(SETTLE_FRAMES)
        for i in range(CAM_N):
            e = _triangle(i)
            x = int(round(X0 + (X1 - X0) * e))
            y = int(round(Y0 + (Y1 - Y0) * e))
            w = int(round(W0 + (W1 - W0) * e))
            h = int(round(H0 + (H1 - H0) * e))
            window.setPosition(x, y)
            window.width = w
            window.height = h
            _tick(1)
            if not _screenshot(os.path.join(out_dir, f"cam_{i:04d}.png")):
                raise SystemExit(f"camera frame {i} did not capture")
            state["boxes"].append([x, y, w, h])
            state["cam"] += 1

    UI_RUN(_run())

    meta = {
        "source": "examples/good/panel.py",
        "cam_frames": state["cam"],
        "cam_half_frames": CAM_HALF,
        "boxes": state["boxes"],
        "capture": "judge/render.py capture path (pre-bound C functions)",
        "surface": [1280, 720],
    }
    with open(os.path.join(out_dir, "frames.json"), "w") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
    print(f"make_frames: {state['cam']} camera frames -> {out_dir}")


if __name__ == "__main__":
    main()
