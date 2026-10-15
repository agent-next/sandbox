#!/usr/bin/env python3
"""Render the demo video from the artifact the judge graded.

    make_video.py <artifact_dir> <out_master.mp4> [--seed N] [--fps 30]

1920x1080, 30 fps, ~36 s.  Three panels animate together, all from measured
data:
  * left   -- the bouncing ball GIF, frame by frame, at its real frame rate,
              with the judge's measured floor row and bounce marks;
  * top    -- the Shepard chroma glide measured from the WAV, drawing itself
              against the analytic fit and the spec floor;
  * bottom -- the WAV waveform with a playhead, so the rising tone is visible.

Writes a lossless master (the caller encodes the web H.264 from it).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "judge"))
import viral_judge as J  # noqa: E402

OKABE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#F0E442", "#56B4E9"]


def render(art: str, out: str, seed: int, fps: int,
           duration_s: float = 30.0, unique_fps: int = 10) -> None:
    verdict = J.grade(art, seed)
    bb = verdict["gates"]["ball_bounces"]
    sp = verdict["gates"]["shepard_property"]

    frames, _loop = J.read_gif_frames(os.path.join(art, "ball.gif"))
    gif_imgs = [Image.fromarray(f["rgb"], "RGB") for f in frames]

    x = J.read_pcm_mono(os.path.join(art, "shepard.wav"))
    ts, phis = J.track_chroma(x, J.SR, J.CHROMA_F_REF)
    glide = J.unfold_rising(phis)
    slope, intercept = np.polyfit(ts, glide, 1)
    t_end = len(x) / J.SR

    # audio envelope, decimated for drawing
    n = len(x)
    hop = max(1, n // 4000)
    env_t = np.arange(0, n - hop, hop) / J.SR
    env = np.array([np.abs(x[i:i + hop]).max() for i in range(0, n - hop, hop)])

    bottoms = [b for b in bb["bottom_rows"] if b is not None]

    # Unique frames are drawn at `unique_fps` and ffmpeg duplicates them up to
    # `fps`, so the render cost is set by the duration, not the output rate.
    # The animation loops enough times to fill the duration.
    total_video_frames = max(len(gif_imgs), int(round(duration_s * unique_fps)))
    dur = total_video_frames / unique_fps

    tmp = tempfile.mkdtemp(prefix="viral-video-")
    try:
        for k in range(total_video_frames):
            gi = k % len(gif_imgs)
            frac = k / (total_video_frames - 1)
            fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
            gs = fig.add_gridspec(2, 2, width_ratios=[1.0, 1.0],
                                  height_ratios=[1.0, 0.55], hspace=0.24,
                                  wspace=0.14, top=0.90, bottom=0.07,
                                  left=0.05, right=0.97)

            # --- ball panel (16:9 image in a 16:9 axes) ---------------------
            ax = fig.add_subplot(gs[0, 0])
            ax.imshow(gif_imgs[gi], aspect="equal")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(f"ball.gif — frame {gi + 1}/{len(gif_imgs)}   "
                         f"(judge: {bb['n_bounces']} bounces, rise "
                         f"{bb['max_rise_px']} px, travel "
                         f"{bb['x_travel_px']:.0f} px)", fontsize=11)

            # --- glide panel ------------------------------------------------
            ax = fig.add_subplot(gs[0, 1])
            t_now = frac * t_end
            m = ts <= t_now
            ax.plot(ts[m], glide[m], lw=2.0, color=OKABE[0],
                    label="measured chroma glide")
            ax.plot(ts, intercept + slope * ts, lw=1.2, ls="--",
                    color=OKABE[1], label=f"fit: {slope:.4f} oct/s")
            ax.axhline(J.MIN_OCTAVES, color=OKABE[2], lw=1.0, ls=":",
                       label=f"spec floor {J.MIN_OCTAVES:.1f} oct")
            ax.axvline(t_now, color="0.5", lw=0.8)
            ax.set_xlim(0, t_end)
            ax.set_ylim(-0.2, max(glide.max(), J.MIN_OCTAVES) + 0.3)
            ax.set_xlabel("time (s)")
            ax.set_ylabel("glide r(t) (octaves)")
            ax.set_title("Shepard tone: the glide rises forever and returns "
                         f"to its pitch class ({sp['return_octaves']:.4f} oct)",
                         fontsize=11)
            ax.legend(loc="upper left", fontsize=8)
            ax.grid(alpha=0.25)

            # --- waveform panel, full width --------------------------------
            ax = fig.add_subplot(gs[1, :])
            mm = env_t <= t_now
            ax.plot(env_t[mm], env[mm], lw=0.6, color=OKABE[0])
            ax.axvline(t_now, color=OKABE[1], lw=1.2)
            ax.set_xlim(0, t_end)
            ax.set_ylim(0, max(env.max(), 1e-6) * 1.1)
            ax.set_xlabel("time (s)")
            ax.set_ylabel("|sample| envelope")
            ax.set_title("shepard.wav — 22050 Hz mono, 22.0 s, "
                         "gliding from 40 Hz partials upward", fontsize=11)
            ax.grid(alpha=0.25)

            fig.suptitle("viral-microgen — a Shepard tone, a bouncing ball, a "
                         "QR code and a palette card, all judged",
                         fontsize=15, y=0.965)
            p = os.path.join(tmp, f"f{k:05d}.png")
            fig.savefig(p, dpi=100)
            plt.close(fig)

        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-framerate", str(unique_fps), "-i", os.path.join(tmp, "f%05d.png"),
            "-vf", f"fps={fps}",
            "-c:v", "libx264", "-crf", "0", "-preset", "medium",
            "-pix_fmt", "yuv420p", out], check=True)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"make_video: wrote {out} ({total_video_frames} unique frames at "
          f"{unique_fps} fps -> {fps} fps, {dur:.1f} s)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("out_master")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--duration-s", type=float, default=30.0)
    ap.add_argument("--unique-fps", type=int, default=10)
    args = ap.parse_args()
    render(args.artifact, args.out_master, args.seed, args.fps,
           args.duration_s, args.unique_fps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
