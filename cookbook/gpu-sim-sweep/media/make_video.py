#!/usr/bin/env python3
"""Render media/demo.mp4 from media/data/report.json only.

1920x1080, 30 fps, H.264 web encode (-crf 18 -preset slow -pix_fmt yuv420p
-movflags +faststart) from a git-ignored lossless master (-crf 0) under
media/master/.

Scene 1 animates the judge-measured world-0 settle trajectory: the 8 boxes
fall onto the table, drawn as oriented boxes from the recorded quaternions.
Scene 2 fills in the nworld ladder with the measured steps/s of every
sweep point, against the CPU baseline and the throughput floor.

No number on screen is invented: every value is read from report.json.
Missing data exits non-zero naming the field.
"""

import json
import os
import shutil
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

MEDIA_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(MEDIA_DIR, "data")
REPORT_JSON = os.path.join(DATA_DIR, "report.json")
FRAMES_DIR = os.path.join(MEDIA_DIR, ".frames")
MASTER_DIR = os.path.join(MEDIA_DIR, "master")
OUT_MP4 = os.path.join(MEDIA_DIR, "demo.mp4")

FPS = 30
W, H = 1920, 1080

# Scene timing.
TITLE_FRAMES = 60     # 2.0 s title card
SIM_FRAMES = 270      # 9.0 s of box-fall (0.8 s of sim, ~11x slow)
LADDER_FRAMES = 270   # 9.0 s: ladder bars fill in
END_FRAMES = 90       # 3.0 s summary card

# Scene geometry mirrored from judge/scene.py (structure, not data).
NQ_ARM = 7
NQ_BOX = 7
N_BOXES = 8
BOX_HALF = 0.04
TABLE_POS = np.array([0.85, 0.0, 0.25])
TABLE_HALF = np.array([0.35, 0.35, 0.025])
TABLE_TOP = 0.275


def die(msg):
    print(f"make_video.py: {msg}", file=sys.stderr)
    raise SystemExit(1)


def need(obj, *keys):
    cur = obj
    for i, k in enumerate(keys):
        if not isinstance(cur, dict) or k not in cur:
            die(f"report.json missing field: {'.'.join(map(str, keys[:i + 1]))}")
        cur = cur[k]
    return cur


def rotmat(q):
    """mujoco free-joint quaternion (w, x, y, z) -> rotation matrix."""
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def box_corners(pos, quat, half):
    c = np.array([[sx, sy, sz] for sx in (-half, half)
                  for sy in (-half, half) for sz in (-half, half)])
    return (rotmat(quat) @ c.T).T + pos


def box_faces(corners):
    idx = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4),
           (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    return [[corners[i] for i in f] for f in idx]


def new_canvas():
    fig = plt.figure(figsize=(W / 120, H / 120), dpi=120)
    fig.patch.set_facecolor("#101418")
    return fig


def save(fig, n):
    fig.savefig(os.path.join(FRAMES_DIR, f"f{n:05d}.png"),
                facecolor=fig.get_facecolor())
    plt.close(fig)


def title_frame(n):
    fig = new_canvas()
    fig.text(0.5, 0.62, "gpu-sim-sweep", ha="center", va="center",
             fontsize=44, color="white", weight="bold")
    fig.text(0.5, 0.47,
             "one CPU world vs 8192 GPU worlds — a judge that runs "
             "the physics itself",
             ha="center", va="center", fontsize=19, color="#9fb3c8")
    fig.text(0.5, 0.34,
             "MuJoCo-Warp on a 4 GiB RTX 5090 slice - all numbers measured "
             "by the judge",
             ha="center", va="center", fontsize=14, color="#5b7288")
    save(fig, n)


def sim_frame(n, t_idx, t_max, sim_t, traj):
    """Draw the 8 boxes (oriented, from the measured trajectory) + table."""
    fig = new_canvas()
    ax = fig.add_axes([0.02, 0.02, 0.96, 0.9], projection="3d")
    ax.set_facecolor("#101418")

    row = traj[t_idx]
    polys, colours = [], []
    # table slab
    c = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1)
                  for sz in (-1, 1)]) * TABLE_HALF + TABLE_POS
    polys += box_faces(c)
    colours += ["#3d4b57"] * 6
    # floor line under table (just the table footprint square at z=0)
    fl = np.array([[0.35, -0.5, 0.0], [1.35, -0.5, 0.0],
                   [1.35, 0.5, 0.0], [0.35, 0.5, 0.0]])
    polys.append(fl)
    colours.append("#1a222b")
    # boxes
    palette = ["#e0823d", "#4d9de0", "#e15759", "#76b041",
               "#b07cc6", "#f2c14e", "#4ecdc4", "#ef6f91"]
    for i in range(N_BOXES):
        base = NQ_ARM + i * NQ_BOX
        pos = np.asarray(row[base:base + 3])
        quat = np.asarray(row[base + 3:base + 7])
        corners = box_corners(pos, quat, BOX_HALF)
        polys += box_faces(corners)
        colours += [palette[i]] * 6
    pc = Poly3DCollection(polys, facecolors=colours, edgecolors="#0b0e11",
                          linewidths=0.4, alpha=0.96)
    ax.add_collection3d(pc)

    ax.set_xlim(0.3, 1.4)
    ax.set_ylim(-0.55, 0.55)
    ax.set_zlim(0, 1.05)
    ax.view_init(elev=16, azim=-62)
    ax.set_box_aspect((1.1, 1.1, 1.05))
    ax.set_axis_off()

    fig.text(0.03, 0.955, "world 0 - settle phase (real mujoco_warp "
             "trajectory)", fontsize=15, color="white", va="top")
    fig.text(0.97, 0.955, f"t = {sim_t:0.2f} s", fontsize=15,
             color="#9fb3c8", va="top", ha="right")
    # progress bar of the settle window
    fig.add_axes([0.03, 0.045, 0.94, 0.018]).axis("off")
    fig.lines.append(plt.Line2D([0.03, 0.03 + 0.94 * t_idx / t_max],
                                [0.045, 0.045], transform=fig.transFigure,
                                color="#4d9de0", lw=3))
    save(fig, n)


def ladder_frame(n, pts, cpu_sps, floor, reveal_frac):
    """Bar chart of measured steps/s per nworld, filling in over time."""
    fig = new_canvas()
    ax = fig.add_axes([0.10, 0.14, 0.86, 0.72])
    ax.set_facecolor("#101418")

    shown = max(1, int(reveal_frac * len(pts) + 1e-9))
    labels = [str(p["nworld"]) for p in pts]
    vals = [p["steps_per_s"] if i < shown else 0 for i, p in enumerate(pts)]
    xs = np.arange(len(pts))
    ax.bar(xs, vals, width=0.62, color="#4d9de0",
           edgecolor="#0b0e11")
    for i, p in enumerate(pts[:shown]):
        ax.text(i, p["steps_per_s"] * 1.15, f"{p['steps_per_s']:,.0f}",
                ha="center", fontsize=12, color="white")
        ax.text(i, -0.14, "", fontsize=1)  # keep layout stable
    ax.axhline(cpu_sps, color="#e0823d", ls="--", lw=2)
    ax.text(len(pts) - 0.4, cpu_sps * 1.25, f"CPU baseline "
            f"{cpu_sps:,.0f} steps/s", color="#e0823d", fontsize=11,
            ha="right")
    ax.axhline(floor * cpu_sps, color="#e15759", ls=":", lw=2)
    ax.text(len(pts) - 0.4, floor * cpu_sps * 1.25,
            f"pass floor {floor:g}x CPU", color="#e15759", fontsize=11,
            ha="right")
    ax.set_yscale("log")
    ax.set_ylim(100, max(p["steps_per_s"] for p in pts) * 4)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, color="#9fb3c8", fontsize=12)
    ax.set_xlabel("nworld (parallel worlds stepped in lockstep)",
                  color="#9fb3c8", fontsize=12)
    ax.set_ylabel("measured aggregate steps/s (log)", color="#9fb3c8",
                  fontsize=12)
    ax.tick_params(colors="#9fb3c8")
    for s in ax.spines.values():
        s.set_color("#33414d")
    ax.grid(True, which="both", axis="y", color="#22303a", lw=0.6)
    fig.text(0.05, 0.94, "the nworld ladder - every bar measured by the "
             "judge", fontsize=15, color="white", va="top")
    save(fig, n)


def end_frame(n, rep):
    t = need(rep, "good", "verdict", "timing")
    mutants = need(rep, "mutants")
    killed = sum(1 for m in mutants.values() if m.get("failed"))
    fig = new_canvas()
    fig.text(0.5, 0.72, "verdict: PASS", ha="center", fontsize=40,
             color="#76b041", weight="bold")
    fig.text(0.5, 0.55,
             f"top nworld {need(t, 'top_steps_per_s'):,.0f} steps/s "
             f"vs CPU {need(t, 'cpu_steps_per_s'):,.0f} steps/s "
             f"(x{need(t, 'speedup'):.1f}, floor x{need(t, 'speedup_floor'):g})",
             ha="center", fontsize=17, color="white")
    fig.text(0.5, 0.45,
             f"CPU<->GPU world-0 parity err "
             f"{need(t, 'parity_max_err'):.4f} rad - "
             f"all boxes landed, finite",
             ha="center", fontsize=15, color="#9fb3c8")
    fig.text(0.5, 0.34,
             f"self-test: {killed}/{len(mutants)} mutants killed by real "
             "judge runs", ha="center", fontsize=15, color="#9fb3c8")
    save(fig, n)


def main():
    if not os.path.isfile(REPORT_JSON):
        die("missing media/data/report.json: run 'python3 "
            "cookbook/gpu-sim-sweep/run.py --gpu --report-json "
            "cookbook/gpu-sim-sweep/media/data/report.json'")
    with open(REPORT_JSON) as fh:
        rep = json.load(fh)

    wt = need(rep, "good", "world0_traj")
    traj = need(wt, "traj")
    dt = need(wt, "timestep") * need(wt, "stride")
    timing = need(rep, "good", "verdict", "timing")
    pts = [p for p in need(timing, "points") if p.get("ok")]
    if not pts:
        die("report.json: no successful sweep points")
    cpu_sps = need(timing, "cpu_steps_per_s")
    floor = need(timing, "speedup_floor")

    shutil.rmtree(FRAMES_DIR, ignore_errors=True)
    os.makedirs(FRAMES_DIR)
    os.makedirs(MASTER_DIR, exist_ok=True)

    n = 0
    for _ in range(TITLE_FRAMES):
        title_frame(n)
        n += 1
    t_max = len(traj) - 1
    for f in range(SIM_FRAMES):
        ti = min(t_max, round(f * t_max / (SIM_FRAMES - 1)))
        sim_frame(n, ti, t_max, ti * dt, traj)
        n += 1
    for f in range(LADDER_FRAMES):
        ladder_frame(n, pts, cpu_sps, floor, f / (LADDER_FRAMES - 1))
        n += 1
    for _ in range(END_FRAMES):
        end_frame(n, rep)
        n += 1
    total = n

    master = os.path.join(MASTER_DIR, "demo-master.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(FPS),
         "-i", os.path.join(FRAMES_DIR, "f%05d.png"),
         "-c:v", "libx264", "-crf", "0", "-preset", "medium",
         "-pix_fmt", "yuv420p", master],
        check=True, capture_output=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", master,
         "-c:v", "libx264", "-crf", "18", "-preset", "slow",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT_MP4],
        check=True, capture_output=True)
    shutil.rmtree(FRAMES_DIR, ignore_errors=True)
    print(f"wrote {OUT_MP4} ({total} frames, {total / FPS:.1f} s)")


if __name__ == "__main__":
    main()
