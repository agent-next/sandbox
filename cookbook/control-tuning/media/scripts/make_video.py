#!/usr/bin/env python3
"""make_video.py — render demo.mp4 master (lossless) for the control-tuning demo.

Frames:
  1. Title (3 s)
  2. result.png - good controller traces + gate table + MC panel (10 s)
  3. loop.png - mutant matrix + killer traces + selftest (10 s)
  4. Animation: good controller cart-pole step response (scenario 1 + 2) (12 s)
  5. Side-by-side: too-aggressive vs good torque demand (scenario 2) (8 s)
  6. Side-by-side: too-sluggish vs good cart position (scenario 2) (8 s)
  7. Final matrix hold with caption (5 s)

Total: ~56 s at 30 fps = 1680 frames. Lossless master (crf 0), then re-encoded to crf 18.
"""
import argparse
import os
import sys

import numpy as np

# Use the judge venv's matplotlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation

import common as c

plt = c.rc_params()

# --- load all data once ---------------------------------------------------
Vg = c.verdict("good")
Va = c.verdict("too-aggressive")
Vs = c.verdict("too-sluggish")
Vm = c.verdict("mc-marginal")

# traces
t1g, x1g, _, th1g, _, F1g, tau1g = c.trace("good", 1)
t2g, x2g, _, th2g, _, F2g, tau2g = c.trace("good", 2)
t1a, _, _, _, _, _, tau1a = c.trace("too-aggressive", 1)
t2a, _, _, _, _, _, tau2a = c.trace("too-aggressive", 2)
t1s, x1s, _, _, _, _, _ = c.trace("too-sluggish", 1)
t2s, x2s, _, _, _, _, _ = c.trace("too-sluggish", 2)

# spec constants
F_MAX = c.F_MAX
TAU_MAX = c.TAU_MAX
THETA0 = c.THETA0
S1_THETA_BAND = c.S1_THETA_BAND
S1_X_BAND = c.S1_X_BAND
S2_X_BAND = c.S2_X_BAND
S1_SETTLE_MAX = c.S1_SETTLE_MAX
S2_SETTLE_MAX = c.S2_SETTLE_MAX

# --- helper: cart-pole drawing -------------------------------------------
def draw_cart_pole(ax, x, theta, l=0.5, cart_w=0.3, cart_h=0.15, wheel_r=0.05):
    """Draw cart-pole at state x, theta on given axes. Returns artists."""
    # cart body
    cx = x
    cy = 0.0
    cart = plt.Rectangle((cx - cart_w/2, cy - cart_h/2), cart_w, cart_h,
                         facecolor=c.BLUE, edgecolor=c.INK, lw=1.5, zorder=5)
    ax.add_patch(cart)
    # wheels
    wheel1 = plt.Circle((cx - cart_w/2 + 0.04, cy - cart_h/2 - wheel_r), wheel_r,
                        facecolor=c.INK2, edgecolor=c.INK, lw=1, zorder=6)
    wheel2 = plt.Circle((cx + cart_w/2 - 0.04, cy - cart_h/2 - wheel_r), wheel_r,
                        facecolor=c.INK2, edgecolor=c.INK, lw=1, zorder=6)
    ax.add_patch(wheel1)
    ax.add_patch(wheel2)
    # pole
    px = cx + l * np.sin(theta)
    py = cy + l * np.cos(theta)
    pole = plt.Line2D([cx, px], [cy, py], color=c.ORANGE, lw=3, zorder=4)
    ax.add_line(pole)
    # COM dot
    com = plt.Circle((px, py), 0.025, facecolor=c.CRIT, edgecolor=c.INK, lw=1, zorder=7)
    ax.add_patch(com)
    return [cart, wheel1, wheel2, pole, com]

# --- animation frames -----------------------------------------------------
def make_animation(out_path, crf=0, preset="ultrafast", fps=30, width=1920, height=1080):
    dpi = 100
    fig_w = width / dpi
    fig_h = height / dpi

    # Total frames
    SEC_TITLE = 3
    SEC_RESULT = 10
    SEC_LOOP = 10
    SEC_ANIM = 12
    SEC_SIDE_A = 8
    SEC_SIDE_B = 8
    SEC_HOLD = 5
    TOTAL_SEC = SEC_TITLE + SEC_RESULT + SEC_LOOP + SEC_ANIM + SEC_SIDE_A + SEC_SIDE_B + SEC_HOLD
    N_FRAMES = TOTAL_SEC * fps

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)

    # layout gate: first frame of each segment is checked for clipped or
    # colliding text/legends; the build fails if it trips. The last two
    # entries are mid-segment frames where the delayed annotations are up.
    CHECK_FRAMES = {int(b * fps) for b in
                    (0, SEC_TITLE, SEC_TITLE + SEC_RESULT,
                     SEC_TITLE + SEC_RESULT + SEC_LOOP,
                     SEC_TITLE + SEC_RESULT + SEC_LOOP + 6.0,
                     SEC_TITLE + SEC_RESULT + SEC_LOOP + SEC_ANIM,
                     SEC_TITLE + SEC_RESULT + SEC_LOOP + SEC_ANIM
                     + SEC_SIDE_A,
                     TOTAL_SEC - SEC_HOLD,
                     SEC_TITLE + SEC_RESULT + SEC_LOOP + SEC_ANIM + 7,
                     SEC_TITLE + SEC_RESULT + SEC_LOOP + SEC_ANIM
                     + SEC_SIDE_A + 7)}

    def init():
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor(c.SURFACE)
        ax.set_xlim(-0.5, 0.5)
        ax.set_ylim(-0.5, 0.5)
        ax.axis("off")
        ax.text(0, 0.1, "LQR Cart-Pole Control Tuning", fontsize=48, color=c.INK,
                ha="center", va="center", weight="bold")
        ax.text(0, -0.1, "Agent designs weights; judge decides pass/fail",
                fontsize=24, color=c.INK2, ha="center", va="center")
        ax.text(0, -0.3, "cookbook/control-tuning  •  seed 20260101",
                fontsize=18, color=c.MUTED, ha="center", va="center")
        return []

    def update(frame):
        fig.clear()
        t = frame / fps  # current time in seconds

        if t < SEC_TITLE:
            # Title screen
            ax = fig.add_subplot(111)
            ax.set_facecolor(c.SURFACE)
            ax.axis("off")
            ax.set_xlim(-1, 1)
            ax.set_ylim(-1, 1)
            alpha = 1.0 if t < SEC_TITLE - 0.5 else 2*(SEC_TITLE - t)
            ax.text(0, 0.15, "LQR Cart-Pole Control Tuning", fontsize=48, color=c.INK,
                    ha="center", va="center", weight="bold", alpha=alpha)
            ax.text(0, -0.05, "Agent designs weights; judge decides pass/fail",
                    fontsize=28, color=c.INK2, ha="center", va="center", alpha=alpha)
            ax.text(0, -0.25, "cookbook/control-tuning  •  seed 20260101",
                    fontsize=20, color=c.MUTED, ha="center", va="center", alpha=alpha)
            ax.text(0, -0.5, "Result figure → Loop replay → Animated traces → Side-by-side",
                    fontsize=18, color=c.MUTED, ha="center", va="center", alpha=alpha)
            return []

        elif t < SEC_TITLE + SEC_RESULT:
            # Show result.png (leave a bottom strip so the label/progress
            # bar never overlaps the figure's own caption)
            ax = fig.add_subplot(111)
            ax.set_facecolor(c.SURFACE)
            ax.axis("off")
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            img = plt.imread(os.path.join(c.MEDIA, "result.png"))
            ax.imshow(img, extent=[0, 1, 0.065, 1], aspect="auto")
            # progress bar
            prog = (t - SEC_TITLE) / SEC_RESULT
            ax.plot([0.05, 0.05 + 0.9*prog], [0.04, 0.04], color=c.BLUE, lw=4, solid_capstyle="round")
            ax.text(0.5, 0.01, "Result figure — good controller under the judge's spec envelope",
                    fontsize=16, color=c.INK2, ha="center", va="bottom")
            return []

        elif t < SEC_TITLE + SEC_RESULT + SEC_LOOP:
            # Show loop.png
            ax = fig.add_subplot(111)
            ax.set_facecolor(c.SURFACE)
            ax.axis("off")
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            img = plt.imread(os.path.join(c.MEDIA, "loop.png"))
            ax.imshow(img, extent=[0, 1, 0.065, 1], aspect="auto")
            prog = (t - SEC_TITLE - SEC_RESULT) / SEC_LOOP
            ax.plot([0.05, 0.05 + 0.9*prog], [0.04, 0.04], color=c.ORANGE, lw=4, solid_capstyle="round")
            ax.text(0.5, 0.01, "Loop replay — mutant × gate matrix, killer traces, selftest",
                    fontsize=16, color=c.INK2, ha="center", va="bottom")
            return []

        elif t < SEC_TITLE + SEC_RESULT + SEC_LOOP + SEC_ANIM:
            # Animated cart-pole: scenario 1 (0-6s) then scenario 2 (6-12s)
            t_anim = t - SEC_TITLE - SEC_RESULT - SEC_LOOP
            ax = fig.add_subplot(111)
            ax.set_facecolor(c.SURFACE)
            c.style_axis(ax)
            ax.set_xlim(-1.5, 1.5)
            ax.set_ylim(-0.6, 1.1)
            ax.set_aspect("equal")
            ax.set_xlabel("cart position (m)", fontsize=14, color=c.INK2)
            ax.set_ylabel("height (m)", fontsize=14, color=c.INK2)

            # ground line
            ax.axhline(-0.15, color=c.AXIS, lw=2, zorder=1)

            if t_anim < 6.0:
                # Scenario 1: recover from 0.15 rad lean
                # interpolate trace
                idx = int((t_anim / 6.0) * (len(t1g) - 1))
                idx = min(idx, len(t1g) - 1)
                x = x1g[idx]
                theta = th1g[idx]
                draw_cart_pole(ax, x, theta)
                ax.set_title(f"Scenario 1: recover from {THETA0:.2f} rad lean — t = {t_anim:.1f} / 6.0 s",
                             fontsize=18, color=c.INK, pad=10)
                # settling band indicator
                ax.axhline(S1_THETA_BAND, color=c.GOOD, lw=1.5, ls="--", alpha=0.5, zorder=2)
                ax.axhline(-S1_THETA_BAND, color=c.GOOD, lw=1.5, ls="--", alpha=0.5, zorder=2)
                # time-sync plot inset
                axins = ax.inset_axes([0.62, 0.62, 0.35, 0.35])
                axins.plot(t1g[:idx+1], th1g[:idx+1], color=c.BLUE, lw=1.5)
                axins.axhline(S1_THETA_BAND, color=c.GOOD, lw=1, alpha=0.5)
                axins.axhline(-S1_THETA_BAND, color=c.GOOD, lw=1, alpha=0.5)
                axins.set_xlim(0, 10)
                axins.set_ylim(-0.01, 0.16)
                axins.set_xticks([0, 5, 10])
                axins.set_yticks([0, 0.08, 0.15])
                axins.tick_params(labelsize=8, colors=c.MUTED)
                for s in axins.spines.values():
                    s.set_color(c.AXIS)
                axins.set_title(r"$\theta(t)$", fontsize=10, color=c.INK2)
                c.style_axis(axins)
            else:
                # Scenario 2: return from 1 m displacement
                t2 = t_anim - 6.0
                idx = int((t2 / 6.0) * (len(t2g) - 1))
                idx = min(idx, len(t2g) - 1)
                x = x2g[idx]
                theta = th2g[idx]
                draw_cart_pole(ax, x, theta)
                ax.set_title(f"Scenario 2: return from 1 m displacement — t = {t2:.1f} / 6.0 s",
                             fontsize=18, color=c.INK, pad=10)
                ax.axvline(S2_X_BAND, color=c.GOOD, lw=1.5, ls="--", alpha=0.5, zorder=2)
                ax.axvline(-S2_X_BAND, color=c.GOOD, lw=1.5, ls="--", alpha=0.5, zorder=2)
                # time-sync plot inset
                axins = ax.inset_axes([0.62, 0.62, 0.35, 0.35])
                axins.plot(t2g[:idx+1], x2g[:idx+1], color=c.BLUE, lw=1.5)
                axins.axvline(S2_X_BAND, color=c.GOOD, lw=1, alpha=0.5)
                axins.axvline(-S2_X_BAND, color=c.GOOD, lw=1, alpha=0.5)
                axins.set_xlim(0, 10)
                axins.set_ylim(-0.1, 1.1)
                axins.set_xticks([0, 5, 10])
                axins.set_yticks([0, 0.5, 1.0])
                axins.tick_params(labelsize=8, colors=c.MUTED)
                for s in axins.spines.values():
                    s.set_color(c.AXIS)
                axins.set_title("$x(t)$", fontsize=10, color=c.INK2)
                c.style_axis(axins)
            return []

        elif t < SEC_TITLE + SEC_RESULT + SEC_LOOP + SEC_ANIM + SEC_SIDE_A:
            # Side-by-side: too-aggressive vs good torque demand
            t_side = t - SEC_TITLE - SEC_RESULT - SEC_LOOP - SEC_ANIM
            ax = fig.add_subplot(111)
            ax.set_facecolor(c.SURFACE)
            c.style_axis(ax)
            ax.set_xlim(-0.2, 10.2)
            ax.set_ylim(-2.8, 3.0)
            ax.set_xlabel("time (s)", fontsize=16, color=c.INK2)
            ax.set_ylabel("torque demand (N·m)", fontsize=16, color=c.INK2)
            ax.set_title("Side-by-side: too-aggressive (Q × 1000) vs good — torque demand",
                         fontsize=20, color=c.INK, pad=12)
            ax.axhline(TAU_MAX, color=c.CRIT, lw=2, zorder=2, label="limit ±1 N·m")
            ax.axhline(-TAU_MAX, color=c.CRIT, lw=2, zorder=2)
            ax.axhline(0, color=c.AXIS, lw=1, zorder=1)
            # animate growing curves
            idx = int((t_side / SEC_SIDE_A) * (len(t2a) - 1))
            idx = min(idx, len(t2a) - 1)
            ax.plot(t2a[:idx+1], tau2a[:idx+1], color=c.ORANGE, lw=2.5, zorder=3,
                    label="too-aggressive")
            ax.plot(t2g[:idx+1], tau2g[:idx+1], color=c.BLUE, lw=2.5, zorder=3,
                    label="good")
            # peak annotation for too-aggressive
            if idx > len(t2a) // 2:
                peak_idx = np.argmax(np.abs(tau2a[:idx+1]))
                ax.annotate(f"peak |τ| = {tau2a[peak_idx]:.2f} N·m > 1 N·m ✕",
                            xy=(t2a[peak_idx], tau2a[peak_idx]),
                            xytext=(2, 2.5), fontsize=14, color=c.CRIT,
                            arrowprops=dict(arrowstyle="->", color=c.CRIT, lw=1.5))
            leg = ax.legend(loc="upper right", fontsize=13, frameon=True,
                            facecolor=c.SURFACE, edgecolor=c.GRID)
            for txt in leg.get_texts():
                txt.set_color(c.INK2)
            return []

        elif t < SEC_TITLE + SEC_RESULT + SEC_LOOP + SEC_ANIM + SEC_SIDE_A + SEC_SIDE_B:
            # Side-by-side: too-sluggish vs good cart position
            t_side = t - SEC_TITLE - SEC_RESULT - SEC_LOOP - SEC_ANIM - SEC_SIDE_A
            ax = fig.add_subplot(111)
            ax.set_facecolor(c.SURFACE)
            c.style_axis(ax)
            ax.set_xlim(-0.3, 10.3)
            ax.set_ylim(-0.4, 1.15)
            ax.set_xlabel("time (s)", fontsize=16, color=c.INK2)
            ax.set_ylabel("cart position x (m)", fontsize=16, color=c.INK2)
            ax.set_title("Side-by-side: too-sluggish (Q / 100) vs good — cart position",
                         fontsize=20, color=c.INK, pad=12)
            ax.axhline(S2_X_BAND, color=c.GOOD, lw=1.5, zorder=2)
            ax.axhline(-S2_X_BAND, color=c.GOOD, lw=1.5, zorder=2)
            ax.fill_between([-0.3, 10.3], -S2_X_BAND, S2_X_BAND,
                            color=c.GOOD, alpha=0.08, zorder=1)
            idx = int((t_side / SEC_SIDE_B) * (len(t2s) - 1))
            idx = min(idx, len(t2s) - 1)
            ax.plot(t2s[:idx+1], x2s[:idx+1], color=c.ORANGE, lw=2.5, zorder=3,
                    label="too-sluggish")
            ax.plot(t2g[:idx+1], x2g[:idx+1], color=c.BLUE, lw=2.5, zorder=3,
                    label="good")
            if idx > len(t2s) // 2:
                # too-sluggish hasn't settled by end
                ax.annotate(f"too-sluggish never settles (gate: ≤ {S2_SETTLE_MAX:.0f} s)",
                            xy=(8, x2s[800] if 800 < len(x2s) else x2s[-1]),
                            xytext=(3.2, 1.04), fontsize=14, color=c.CRIT,
                            arrowprops=dict(arrowstyle="->", color=c.CRIT, lw=1.5))
            leg = ax.legend(loc="upper right", fontsize=13, frameon=True,
                            facecolor=c.SURFACE, edgecolor=c.GRID)
            for txt in leg.get_texts():
                txt.set_color(c.INK2)
            return []

        else:
            # Final hold: loop.png matrix with caption
            ax = fig.add_subplot(111)
            ax.set_facecolor(c.SURFACE)
            ax.axis("off")
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            img = plt.imread(os.path.join(c.MEDIA, "loop.png"))
            ax.imshow(img, extent=[0, 1, 0.065, 1], aspect="auto")
            ax.text(0.5, 0.015, "All numbers from real judge runs (grade.sh --trace, seed 20260101) — "
                       "no synthesised data",
                    fontsize=16, color=c.INK2, ha="center", va="bottom")
            return []

    def update_checked(frame):
        artists = update(frame)
        if frame in CHECK_FRAMES:
            c.check_layout(fig)
        return artists

    print(f"Rendering {N_FRAMES} frames ({TOTAL_SEC} s @ {fps} fps)...")
    anim = animation.FuncAnimation(fig, update_checked, frames=N_FRAMES,
                                    init_func=init, blit=False)

    writer = animation.FFMpegWriter(fps=fps, codec="libx264",
                                     extra_args=["-crf", str(crf), "-preset", preset,
                                                 "-pix_fmt", "yuv420p"])
    anim.save(out_path, writer=writer, dpi=dpi)
    plt.close(fig)
    print(f"Written {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output path (e.g. media/master/demo_master.mp4)")
    ap.add_argument("--crf", type=int, default=0, help="crf (0 = lossless)")
    ap.add_argument("--preset", default="ultrafast", help="ffmpeg preset")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    args = ap.parse_args()

    make_animation(args.out, crf=args.crf, preset=args.preset,
                   fps=args.fps, width=args.width, height=args.height)


if __name__ == "__main__":
    main()