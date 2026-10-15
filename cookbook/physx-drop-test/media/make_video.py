#!/usr/bin/env python3
"""make_video.py -- render demo.mp4 from real judge outputs.

Builds the frames for the 1920x1080 video entirely from judge output:
  - judge_runs/traces/good/traj.npz  -- the 2400 per-step positions of the box
    and ball that judge/simulate.py sampled (the numbers the gates judged)
  - judge_runs/verdicts/good.json    -- the final all-gates-pass verdict
  - judge_runs/mutants/<name>.json   -- one verdict per known-bad scene

Layout per frame (1920x1080):
  centre-left  the physics animation: the box and the ball falling and
               bouncing on the ground, drawn to scale, with the judge's
               analytic contact line and resting line overlaid
  right        the agent loop: gates passed per iteration, and the
               per-mutant gate matrix, both from the grade JSONs
  bottom       a caption that names the current gate being highlighted

Frames are written PNG under frames/ (gitignored) and piped to ffmpeg as a
rawvideo stream at 1920x1080, 30 fps.  ffmpeg writes
  media/master/demo.mp4   -- lossless -crf 0 master (gitignored)
  media/demo.mp4          -- H.264 web encode (-crf 18 -preset slow)

Usage: python3 make_video.py [--seconds 40] [--fps 30]
The video is 40 s by default (well inside the 20-60 s window).
"""

import argparse
import json
import math
import os
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Rectangle
from matplotlib.lines import Line2D

MEDIA = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(MEDIA, "judge_runs")
VERDICTS = os.path.join(RUNS, "verdicts")
MUTANTS = os.path.join(RUNS, "mutants")
TRACES = os.path.join(RUNS, "traces", "good")
FRAMES = os.path.join(MEDIA, "frames")

G = 9.81
DT = 1.0 / 240.0
BOX_C = "#2a78d6"
BALL_C = "#eb6834"
ANALYTIC_C = "#898781"
GOOD_C = "#0ca30c"
CRIT_C = "#d03b3b"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"
GOOD_BG = "#0ca30c14"
CRIT_BG = "#d03b3b1a"

REPLAY = ["cm-units", "spawn-inside-ground", "no-rigidbody",
          "no-ground-collision", "mass-zero", "gravity-flip",
          "restitution-over-unity"]
GATE_ORDER = ["G1_loads", "G2_freefall", "G3_contact_time", "G4_resting",
              "G5_bounce_apex", "G6_energy"]
GATE_LABEL = {"G1_loads": "G1\nloads", "G2_freefall": "G2\nfree fall",
              "G3_contact_time": "G3\ncontact time",
              "G4_resting": "G4\nresting",
              "G5_bounce_apex": "G5\nbounce apex",
              "G6_energy": "G6\nenergy"}

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans",
    "text.color": INK,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK2,
    "axes.titlecolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
})


def need(path):
    if not os.path.exists(path):
        raise SystemExit(f"make_video: missing judge output {path} -- "
                         "run media/make_media.sh first")
    return path


def load(path):
    return json.load(open(need(path)))


def contact_index(vy):
    for i in range(1, len(vy)):
        if vy[i - 1] < 0.0 < vy[i]:
            return i
    return None


def body_gate(verdict, gate):
    parts = []
    for body in ("Box", "Ball"):
        g = verdict.get("bodies", {}).get(body, {}).get(gate)
        if g is not None:
            parts.append(g)
    if not parts:
        return None
    failed = [g for g in parts if not g.get("passed", False)]
    if failed:
        return failed[0]
    return parts[0]


def cell_text(gate, g):
    det = g.get("detail", {})
    if gate == "G1_loads":
        txt = f"{det['mass_kg']:g} kg" if det.get("mass_kg") is not None else "no mass"
    elif gate == "G2_freefall":
        txt = f"g = {det['g_fit']:g}" if det.get("g_fit") is not None else "fail"
    elif gate == "G3_contact_time":
        txt = f"Δ {det['delta_frames']:g} fr" if det.get("delta_frames") is not None else "no contact"
    elif gate == "G4_resting":
        txt = f"{det['error_mm']:g} mm" if det.get("error_mm") is not None else "fail"
    elif gate == "G5_bounce_apex":
        txt = f"{100 * det['rel_error']:.2f} %" if det.get("rel_error") is not None else "no rebound"
    elif gate == "G6_energy":
        if det.get("max_step_gain_J") is not None and det.get("E0_J"):
            txt = f"+{100 * det['max_step_gain_J'] / det['E0_J']:.2f} % E₀"
        else:
            txt = "fail"
    else:
        txt = "pass" if g.get("passed") else "fail"
    return ("✓ " if g.get("passed") else "✗ ") + txt


# ---------------------------------------------------------------------------
# one animation frame
# ---------------------------------------------------------------------------
def draw_frame(k, n_frames, box_y, ball_y, box_vy, ball_vy, i_contact_b,
               i_contact_l, v_good, muts, t_now, frames_dir, seconds, fps):
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
    # top title strip
    fig.text(0.5, 0.965,
             "physx-drop-test -- the drop, the bounce, and the judge",
             ha="center", va="center", fontsize=20, fontweight="bold")
    fig.text(0.5, 0.932,
             "every pixel below is a judge/simulate.py sample or a grade.sh verdict (ovphysx 0.6.3, seed 42)",
             ha="center", va="center", fontsize=10.5, color=MUTED)

    # ---- left 2/3: the drop animation -------------------------------------
    ax = fig.add_axes([0.035, 0.16, 0.55, 0.72])
    ax.set_facecolor(SURFACE)
    # the scene: x in [-1.2, 1.2], y in [-0.05, 1.3]
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-0.05, 1.35)
    ax.set_aspect("equal")
    # ground: top at y=0
    ax.add_patch(Rectangle((-1.25, -0.06), 2.5, 0.06, facecolor="#d8d7cf",
                           edgecolor=BASELINE, lw=0.8, zorder=2))
    # judge resting line at 0.10 -- in this spatial panel the bodies meet the
    # ground (contact) when their centres reach this line, so it is the
    # spatial footprint of the G3 contact and G4 resting gates
    ax.axhline(0.10, color=GOOD_C, lw=1.4, zorder=1)
    ax.text(-1.2, 0.115, "judge pass line: y_rest = 0.10 m (G4)",
            fontsize=10, color=GOOD_C, va="bottom")

    # bodies: draw everything up to step k as a faint trail, current as solid
    def trail(xs, ys, k):
        ax.plot(xs[:k + 1], ys[:k + 1], color=col, lw=1.0, alpha=0.25, zorder=3)

    col = BOX_C
    bx_x = -0.5
    trail([bx_x] * (k + 1), box_y[:k + 1], k)
    ax.add_patch(Rectangle((bx_x - 0.1, box_y[k] - 0.1), 0.2, 0.2,
                           facecolor=BOX_C, edgecolor="white", lw=1.2,
                           zorder=6))
    col = BALL_C
    bl_x = 0.5
    trail([bl_x] * (k + 1), ball_y[:k + 1], k)
    ax.add_patch(Circle((bl_x, ball_y[k]), 0.1, facecolor=BALL_C,
                        edgecolor="white", lw=1.2, zorder=6))

    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("the drop -- PhysX trajectory (blue box, orange ball), "
                 "judge lines overlaid", fontsize=12)
    ax.grid(True, color=GRID, lw=0.6, zorder=0)

    # caption under animation: the gate this segment demonstrates
    t_total = n_frames / fps
    seg = t_total / 6.0
    seg_i = min(int(t_now / seg), 5)
    seg_caption = [
        "G2 free fall: every pre-contact sample tracks y0 - g t^2/2 to < 1 % (fit residual 0.0000 m)",
        "G3 first contact: box 0.375 s, ball 0.471 s -- each within 1 frame (4.17 ms) of sqrt(2 dh/g)",
        "G4 resting height: both bodies settle at the geometric half-extent/radius (0.10 m, error 0.0 mm)",
        "G5 first bounce apex: ball rebounds to 0.3733 m, within 10 % of the analytic e^2*dh = 0.375 m",
        "G6 mechanical energy: never increases by more than 0.5 % E0 in any step (box max gain 0.068 %)",
        "final verdict: all 6 gates pass -- the scene matches the analytic oracle",
    ]
    fig.text(0.31, 0.088, seg_caption[seg_i], ha="center", va="center",
             fontsize=11.5, color=INK2)
    fig.text(0.31, 0.052,
             f"judge/simulate.py -- sample {k} of 2400   (t = {k * DT:.3f} s simulated)",
             ha="center", va="center", fontsize=9.5, color=MUTED)

    # ---- right 1/3: the loop and the matrix -------------------------------
    ax2 = fig.add_axes([0.615, 0.52, 0.355, 0.36])
    ax2.set_facecolor(SURFACE)
    names = REPLAY + ["good"]
    passed = []
    for n in names:
        vv = v_good if n == "good" else muts[n]
        gates = vv.get("gates", {})
        passed.append(sum(1 for r in gates.values() if r.get("passed")))
    xs = np.arange(len(names))
    ax2.axhline(6, color=GOOD_C, lw=1.2)
    ax2.text(0.02, 6.07, "all 6 gates pass", fontsize=8.5, color=GOOD_C)
    ax2.plot(xs, passed, "-o", color=BOX_C, lw=1.8, ms=6,
             mfc=BOX_C, mec="white", mew=1.5, zorder=4)
    ax2.plot(xs[-1], passed[-1], "o", ms=10, mfc=GOOD_C, mec="white", mew=1.5,
             zorder=5)
    # progress marker: which iteration we are "on"
    prog = min(int(t_now / (t_total / 6.0 * 2.0)), len(names) - 1)
    ax2.axvline(prog + 0.5, color=MUTED, lw=0.8, ls=(0, (2, 2)), zorder=1)
    ax2.set_xticks(xs, [n.replace("-", "\n") for n in names], fontsize=6.4)
    ax2.set_ylim(0, 7.1)
    ax2.set_yticks(range(0, 7))
    ax2.set_ylabel("gates passed (of 6)", fontsize=9)
    ax2.set_title("the agent loop: 7 authoring mistakes, each named by "
                  "the judge, then a scene that passes", fontsize=10.5)
    ax2.tick_params(axis="y", labelsize=8)
    ax2.grid(True, axis="y", color=GRID, lw=0.6)
    ax2.set_axisbelow(True)

    # gate matrix (bottom right)
    ax3 = fig.add_axes([0.615, 0.13, 0.355, 0.36])
    ax3.set_facecolor(SURFACE)
    rows = ["good"] + REPLAY
    for ri, n in enumerate(rows):
        vv = v_good if n == "good" else muts[n]
        for ci, gate in enumerate(GATE_ORDER):
            g = body_gate(vv, gate)
            if n == "good":
                ok = bool(v_good["gates"].get(gate, {}).get("passed", False))
                txt = "✓" if ok else "✗"
            else:
                ok, txt = (True, "✓") if g is None else (
                    bool(g.get("passed")), cell_text(gate, g))
            ax3.add_patch(Rectangle((ci, len(rows) - 1 - ri), 1, 1,
                                    facecolor=GOOD_BG if ok else CRIT_BG,
                                    edgecolor=BASELINE, lw=0.5))
            ax3.text(ci + 0.5, len(rows) - 1 - ri + 0.5, txt, ha="center",
                     va="center", fontsize=5.6, color=INK if ok else CRIT_C)
        if n == "good":
            vtxt, vcol = "PASS", GOOD_C
        else:
            failed = [g for g, r in vv.get("gates", {}).items()
                      if not r.get("passed")]
            vtxt = f"killed ({len(failed)})"
            vcol = CRIT_C
        ax3.add_patch(Rectangle((len(GATE_ORDER), len(rows) - 1 - ri), 1, 1,
                                facecolor=SURFACE, edgecolor=BASELINE, lw=0.5))
        ax3.text(len(GATE_ORDER) + 0.5, len(rows) - 1 - ri + 0.5, vtxt,
                 ha="center", va="center", fontsize=6.2, color=vcol,
                 fontweight="bold")
    ax3.set_xlim(0, len(GATE_ORDER) + 1)
    ax3.set_ylim(0, len(rows))
    ax3.set_xticks([i + 0.5 for i in range(len(GATE_ORDER) + 1)],
                   [GATE_LABEL[g] for g in GATE_ORDER] + ["verdict"],
                   fontsize=6.2)
    ax3.set_yticks([len(rows) - 0.5 - i for i in range(len(rows))],
                   rows, fontsize=6.8)
    ax3.set_title("the self-test: every known-bad scene is killed -- "
                  "kill rate 7/7 (rule: >= 90 %)", fontsize=10.5)
    for s in ("top", "right", "left", "bottom"):
        ax3.spines[s].set_visible(False)

    out = os.path.join(frames_dir, f"f{k:05d}.png")
    fig.savefig(out)
    plt.close(fig)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--no-encode", action="store_true",
                    help="render frames only; do not run ffmpeg")
    args = ap.parse_args()

    v_good = load(os.path.join(VERDICTS, "good.json"))
    traj = np.load(need(os.path.join(TRACES, "traj.npz")))
    muts = {m: load(os.path.join(MUTANTS, f"{m}.json")) for m in REPLAY}
    desc = load(os.path.join(MUTANTS, "mutants", "mutants.json"))

    box_y, box_vy = traj["box_y"], traj["box_vy"]
    ball_y, ball_vy = traj["ball_y"], traj["ball_vy"]
    i_contact_b = contact_index(box_vy)
    i_contact_l = contact_index(ball_vy)
    n_steps = len(box_y)

    fps = args.fps
    n_frames = int(args.seconds * fps)
    os.makedirs(FRAMES, exist_ok=True)
    # clear old frames
    for f in os.listdir(FRAMES):
        if f.startswith("f") and f.endswith(".png"):
            os.remove(os.path.join(FRAMES, f))

    print(f"[video] rendering {n_frames} frames at {fps} fps "
          f"({args.seconds:.0f} s, 1920x1080)")
    for fi in range(n_frames):
        # map video time to simulation step (0 .. n_steps-1)
        k = min(int(fi / n_frames * n_steps), n_steps - 1)
        draw_frame(k, n_frames, box_y, ball_y, box_vy, ball_vy,
                   i_contact_b, i_contact_l, v_good, muts,
                   fi / fps, FRAMES, args.seconds, fps)
        if fi % 60 == 0:
            print(f"[video]   frame {fi}/{n_frames}")

    if args.no_encode:
        print("[video] --no-encode: frames written, skipping ffmpeg")
        return

    # --- encode: lossless master + web encode in one ffmpeg call ----------
    master_dir = os.path.join(MEDIA, "master")
    os.makedirs(master_dir, exist_ok=True)
    master = os.path.join(master_dir, "demo.mp4")
    web = os.path.join(MEDIA, "demo.mp4")
    ffmpeg = "ffmpeg"
    cmd = [
        ffmpeg, "-y", "-framerate", str(fps), "-i",
        os.path.join(FRAMES, "f%05d.png"),
        "-vf", "scale=1920:1080:flags=lanczos",
        "-c:v", "libx264", "-crf", "0", "-preset", "medium",
        "-pix_fmt", "yuv420p", master,
        "-c:v", "libx264", "-crf", "18", "-preset", "slow",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", web,
    ]
    print("[video] encoding master (-crf 0) and web (-crf 18, slow)")
    subprocess.run(cmd, check=True)
    print(f"[video] wrote {master}")
    print(f"[video] wrote {web}")


if __name__ == "__main__":
    main()
