#!/usr/bin/env python3
"""Render the 3D frames of demo.mp4 -- one worker, one shot, one range.

Every frame is a real headless MuJoCo render of the pinned RP1 scene,
loaded with the exact state the judge recorded at that instant
(media/data/traces/<name>/trace.csv, written by `grade.sh --trace`, seed
20261014).  Nothing is re-simulated and no number is invented.

The frames are expensive (software rasterisation), so make_video.py runs
several copies of this script in parallel and each one writes its own
range into media/frames/; a frame that already exists is skipped, so a
cut-off run resumes where it stopped.

    python3 vid_render.py <shot> <first> <count>
"""
import os
import sys
import time

MEDIA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, MEDIA)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import rp1render  # noqa: E402

FRAMES = os.path.join(MEDIA, "frames")
W, H = 1920, 1080


def _lerp(a, b, f):
    return a + (b - a) * f


def shots():
    """The 3D shots: name -> (trace, frame count, per-frame pose+camera)."""
    good = "good"
    zero_torque = "zero_torque"

    def turntable(i, n):
        """Standing, held at the final judged pose, camera orbiting."""
        f = i / max(n - 1, 1)
        return dict(t=9.9, azimuth=_lerp(100, 160, f),
                    distance=_lerp(2.95, 2.40, f),
                    elevation=_lerp(-8, 2, f), lookat_z=0.84)

    def episode(i, n):
        """The judged episode around the push, sim t = 3.8 .. 9.8 s."""
        f = i / max(n - 1, 1)
        return dict(t=_lerp(3.8, 9.8, f), azimuth=_lerp(124, 146, f),
                    distance=_lerp(2.80, 2.50, f),
                    elevation=_lerp(-7, -2, f), lookat_z=0.86)

    def fall(i, n):
        """The zero-torque mutant collapsing, sim t = 0 .. 2 s (slowed)."""
        f = i / max(n - 1, 1)
        return dict(t=_lerp(0.0, 2.0, f), azimuth=_lerp(118, 152, f),
                    distance=_lerp(3.10, 2.60, f),
                    elevation=_lerp(-11, -1, f), lookat_z=0.72)

    return {
        "turntable": (good, 120, turntable),
        "episode": (good, 180, episode),
        "fall": (zero_torque, 90, fall),
    }


def main():
    shot, first, count = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    trace_name, n_total, spec = shots()[shot]
    trace = rp1render.Trace(os.path.join(
        MEDIA, "data", "traces", trace_name, "trace.csv"))
    rend = rp1render.Renderer(os.path.join(
        MEDIA, "work", "scene", "mjcf", "rp1_flat.xml"), width=W, height=H)

    os.makedirs(FRAMES, exist_ok=True)
    t0 = time.time()
    done = 0
    for i in range(first, min(first + count, n_total)):
        out = os.path.join(FRAMES, f"{shot}_{i:04d}.png")
        if os.path.exists(out):
            continue
        p = spec(i, n_total)
        rend.set_state(trace, trace.index_at(p["t"]))
        rend.aim(azimuth=p["azimuth"], distance=p["distance"],
                 elevation=p["elevation"], lookat_z=p["lookat_z"])
        img = rend.render()
        if img.shape[:2] != (H, W):
            raise SystemExit(f"render returned {img.shape}, expected {(H, W, 3)}")
        if float(np.asarray(img).std()) < 5.0:
            raise SystemExit(f"frame {out} looks blank (std "
                             f"{float(np.asarray(img).std()):.2f})")
        # atomic-ish: write a temp name then rename, so a killed worker
        # never leaves a half-written PNG that the next run would skip
        tmp = out + ".part"
        Image.fromarray(img).save(tmp, format="PNG")
        os.replace(tmp, out)
        done += 1
    dt = time.time() - t0
    rate = f"{dt / done:.2f} s/frame" if done else "nothing to do"
    print(f"{shot}[{first}:{first + count}]: wrote {done} frames, {rate}",
          flush=True)


if __name__ == "__main__":
    main()
