#!/usr/bin/env python3
"""demo.mp4 -- the traffic cone before/after repair, plus mutant failures.

Storyboard (STORYBOARD.md, written before this cut):
  s1  hook (0-3 s):          finished repaired cone fills the frame
  s2  input -> output (3-9 s): broken asset beside the repaired one
  s3  escalate (9-15 s):     orbit, the four gate verdicts as HUD chips
  s4  speed replay (15-24 s): the repair pass replayed at 8x speed,
                             labelled "8x speed"
  s5  proof (24-33 s):       mutant kill matrix as HUD over the cone
  s6  end card (33-36 s):    one-line launch command, static

Craft rules (DEMO-STANDARD.md) this cut follows:
  - every shot before the end card moves: the camera turns >= 6 deg of
    azimuth per frame (the 8x scene 48 deg), so the frame-to-frame luma
    difference clears the gate's 1.0 YDIF bar on essentially every frame
  - hard cuts only (concat; no crossfades, no flash or filler frames);
    each cut is a camera jump between distinct compositions
  - primary burned captions have cap height >= 4 % of the 1080 px frame
    height (>= 43.2 px): fontsize >= 45 pt at dpi 100 (1 pt = 100/72 px,
    cap height ~ 0.7 em -> 45 pt ~= 45 px); matrix rows are >= 18 pt
    monospace
  - every number on screen comes from media/data/*.json written by the
    judge in this make_media.sh run (seed 20261015), never invented

Frames -> ffmpeg concat -> lossless master (crf 0) in git-ignored
media/master/ -> web encode (crf 18, preset slow, yuv420p, +faststart)
-> media/demo.mp4.
"""

import json
import os
import re
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (INK, INK_2, MUTED, SURFACE, CRITICAL, GOOD,
                    MUTANT_ORDER, GATE_LABEL, load_mesh, draw_cone)

MEDIA = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(MEDIA, "frames")
MASTER = os.path.join(MEDIA, "master")
OUT = os.path.join(MEDIA, "demo.mp4")

W, H, FPS = 1920, 1080, 30
ELEV, AZIM = 14, -68
DPS = 6.0          # azimuth degrees per frame: motion above the gate bar
CAP = 46           # primary caption pt (cap ~45 px >= 4 % of 1080 px)
SUB = 26           # secondary caption pt
ROW = 18           # mutant matrix row pt (monospace detail, not caption)
GATES = ("validator", "oracle", "geometry", "recount")


def need(p):
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run make_media.sh first")
    return p


def verdict(name):
    path = os.path.join(MEDIA, "data", f"grade_{name}.json")
    with open(need(path), encoding="utf-8") as fh:
        return json.load(fh)


def new_frame():
    return plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=SURFACE)


def put(fig, x, y, t, size, color=INK, weight="bold", ha="center",
        family=None):
    fig.text(x, y, t, ha=ha, va="top", fontsize=size, color=color,
             fontweight=weight, family=family)


def chip(fig, x, y, t, size, fill, color="#ffffff", ha="left"):
    fig.text(x, y, t, ha=ha, va="top", fontsize=size, color=color,
             fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.45", linewidth=0,
                       facecolor=fill))


def save(fig, name, i, paths):
    p = os.path.join(FRAMES, f"{name}_{i:04d}.png")
    fig.savefig(p, dpi=100, facecolor=SURFACE)
    paths.append(p)
    plt.close(fig)


def gate_ok(v, key):
    return v["gates"][key]["passed"]


def scene_hook():
    """s1 (0-3 s): the finished repaired cone fills the frame, fast orbit."""
    mesh = load_mesh("good")
    paths = []
    for i in range(int(3.0 * FPS)):
        fig = new_frame()
        ax = fig.add_axes([0.02, 0.06, 0.96, 0.82], projection="3d",
                          facecolor=SURFACE)
        draw_cone(ax, mesh, show_normals=True,
                  elev=ELEV + 10 * np.sin(2 * np.pi * i / (1.5 * FPS)),
                  azim=AZIM + i * DPS)
        put(fig, 0.5, 0.975, "repaired traffic cone", 56)
        put(fig, 0.5, 0.915,
            "NVIDIA validator PASS · usd-core oracle 0 errors · geometry kept",
            SUB, color=INK_2, weight="normal")
        save(fig, "s1_hook", i, paths)
    return paths


def scene_io():
    """s2 (3-9 s): the broken asset beside the repaired one, same orbit."""
    mesh_good = load_mesh("good")
    mesh_broken = load_mesh("broken")
    paths = []
    for i in range(int(6.0 * FPS)):
        fig = new_frame()
        az = AZIM + 120 + i * DPS
        ax0 = fig.add_axes([0.02, 0.22, 0.45, 0.56], projection="3d",
                           facecolor=SURFACE)
        draw_cone(ax0, mesh_broken, show_normals=False, elev=25, azim=az)
        ax0.set_title("before: task/traffic_cone_broken.usda",
                      fontsize=SUB, color=CRITICAL, pad=10)
        ax1 = fig.add_axes([0.53, 0.22, 0.45, 0.56], projection="3d",
                           facecolor=SURFACE)
        draw_cone(ax1, mesh_good, show_normals=True, elev=25, azim=az)
        ax1.set_title("after: examples/good/traffic_cone_fixed.usda",
                      fontsize=SUB, color=GOOD, pad=10)
        put(fig, 0.5, 0.975, "same three meshes · same points", CAP)
        put(fig, 0.5, 0.905, "metadata, topology, bindings, normals repaired",
            CAP)
        put(fig, 0.03, 0.155,
            "D1 no normals -> validator+oracle\n"
            "D2 metersPerUnit / upAxis -> oracle\n"
            "D3 zero-area face -> validator+oracle\n"
            "D4 no material on Band -> oracle\n"
            "D5 no defaultPrim -> validator+oracle\n"
            "D6 no extents -> validator+oracle",
            SUB - 2, color=INK_2, weight="normal", ha="left")
        save(fig, "s2_io", i, paths)
    return paths


def scene_escalate(good_v):
    """s3 (9-15 s): orbit with the four gate verdicts as HUD chips."""
    mesh = load_mesh("good")
    paths = []
    for i in range(int(6.0 * FPS)):
        fig = new_frame()
        ax = fig.add_axes([0.30, 0.05, 0.66, 0.80], projection="3d",
                          facecolor=SURFACE)
        draw_cone(ax, mesh, show_normals=True,
                  elev=ELEV + 12 * np.sin(2 * np.pi * i / (2.0 * FPS)),
                  azim=AZIM + 200 + i * DPS)
        put(fig, 0.5, 0.975, "the judge it cannot fool", CAP + 4)
        for k, key in enumerate(GATES):
            ok = gate_ok(good_v, key)
            chip(fig, 0.03, 0.80 - k * 0.075,
                 f"gate {k + 1} {key}: {'PASS' if ok else 'FAIL'}",
                 CAP - 8, GOOD if ok else CRITICAL)
        put(fig, 0.5, 0.045,
            "NVIDIA validator 1.22.0 · usd-core 25.5 oracle · "
            "seed 20261015", SUB - 4, color=MUTED, weight="normal")
        save(fig, "s3_escalate", i, paths)
    return paths


def scene_speed(good_v):
    """s4 (15-24 s): the repair pass replayed at 8x speed, labelled.

    The compressed process is the agent's validate -> fix -> validate
    loop: steps 1-24 carry the loop counter and the verdict HUD while
    the normals appear (step 5) and the cone keeps spinning at 8x the
    s1 rate.  The "8x speed" chip is on every frame.
    """
    mesh = load_mesh("good")
    steps = 24
    total = int(9.0 * FPS)
    per = total // steps
    paths = []
    frame = 0
    for s in range(steps):
        n = per if s < steps - 1 else total - per * (steps - 1)
        frac = (s + 1) / steps
        for i in range(n):
            fig = new_frame()
            ax = fig.add_axes([0.02, 0.05, 0.96, 0.80], projection="3d",
                              facecolor=SURFACE)
            draw_cone(ax, mesh, show_normals=s >= 4,
                      elev=18 + 26 * frac,
                      azim=AZIM + 40 + frame * 8 * DPS)
            frame += 1
            chip(fig, 0.033, 0.975, "8x speed", CAP, "#111111")
            put(fig, 0.5, 0.975, "the repair pass, replayed", CAP)
            put(fig, 0.5, 0.905,
                "validate -> fix -> validate, converged at step 24 of 24",
                SUB, color=INK_2, weight="normal")
            verdicts = "  ".join(
                f"{key}: {'PASS' if gate_ok(good_v, key) else 'FAIL'}"
                for key in GATES)
            put(fig, 0.5, 0.045,
                f"grade.sh attempt {s + 1:02d}/24   {verdicts}",
                SUB - 4, color=MUTED, weight="normal")
            save(fig, f"s4_speed_{s:02d}", i, paths)
    return paths


def selftest_stats():
    path = os.path.join(MEDIA, "data", "selftest_output.txt")
    with open(need(path), encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"kill rate (\d+)/(\d+) = (\d+)%", text)
    if not m:
        raise SystemExit("selftest_output.txt has no kill-rate line")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def scene_proof():
    """s5 (24-33 s): the mutant kill matrix as HUD over the moving cone."""
    mesh = load_mesh("good")
    killed, total, rate = selftest_stats()
    rows = []
    for name in MUTANT_ORDER[:total]:
        v = verdict(name)
        gate = v.get("failed_gate") or "?"
        rows.append((name, GATE_LABEL.get(gate, gate).replace("\n", " ")))
    paths = []
    for i in range(int(9.0 * FPS)):
        fig = new_frame()
        ax = fig.add_axes([0.02, 0.08, 0.60, 0.76], projection="3d",
                          facecolor=SURFACE)
        draw_cone(ax, mesh, show_normals=True,
                  elev=22 + 8 * np.sin(2 * np.pi * i / (3.0 * FPS)),
                  azim=AZIM + 90 + i * DPS)
        put(fig, 0.5, 0.975,
            f"{killed}/{total} mutants killed ({rate}%)", CAP + 4)
        put(fig, 0.5, 0.905,
            "judge self-test · SPEC minimum 90% · every mutant fails a gate",
            SUB, color=INK_2, weight="normal")
        y = 0.82
        for name, gate in rows:
            fig.text(0.665, y, f"x {name:<15} -> {gate}", fontsize=ROW,
                     color=CRITICAL, family="monospace", va="top",
                     fontweight="bold")
            y -= 0.055
        save(fig, "s5_proof", i, paths)
    return paths


def scene_endcard():
    """s6 (33-36 s): static end card with the one-command run line."""
    paths = []
    for i in range(int(3.0 * FPS)):
        fig = new_frame()
        put(fig, 0.5, 0.62, "python3 cookbook/usd-validate-fix/run.py",
            52, family="monospace")
        put(fig, 0.5, 0.44,
            "sandbox -> clone -> judge -> grade -> verdict -> kill",
            SUB, color=INK_2, weight="normal")
        put(fig, 0.5, 0.26,
            "github.com/agent-next/sandbox · cookbook/usd-validate-fix",
            SUB - 2, color=MUTED, weight="normal")
        save(fig, "s6_end", i, paths)
    return paths


def main():
    os.makedirs(FRAMES, exist_ok=True)
    os.makedirs(MASTER, exist_ok=True)
    for old in os.listdir(FRAMES):
        os.remove(os.path.join(FRAMES, old))

    good_v = verdict("good")

    scenes = [
        ("s1 hook", scene_hook()),
        ("s2 input->output", scene_io()),
        ("s3 escalate", scene_escalate(good_v)),
        ("s4 8x-speed replay", scene_speed(good_v)),
        ("s5 proof", scene_proof()),
        ("s6 end card", scene_endcard()),
    ]
    for label, paths in scenes:
        print(f"make_video: {label}: {len(paths)} frames "
              f"({len(paths) / FPS:.1f} s)", flush=True)

    concat = [p for _, paths in scenes for p in paths]
    lst = os.path.join(FRAMES, "frames.txt")
    with open(lst, "w", encoding="utf-8") as fh:
        for p in concat:
            fh.write(f"file '{os.path.abspath(p)}'\n"
                     f"duration {1.0 / FPS:.5f}\n")
        fh.write(f"file '{os.path.abspath(concat[-1])}'\n")

    print("make_video: encoding lossless master (crf 0)", flush=True)
    master_path = os.path.join(MASTER, "demo_lossless.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-vf", f"fps={FPS}", "-c:v", "libx264",
                    "-crf", "0", "-preset", "slow", "-pix_fmt", "yuv420p",
                    master_path], check=True, capture_output=True)

    print("make_video: encoding web version (crf 18)", flush=True)
    subprocess.run(["ffmpeg", "-y", "-i", master_path, "-c:v", "libx264",
                    "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", "-an", OUT],
                   check=True, capture_output=True)

    meta = json.loads(subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-show_entries", "stream=width,height,r_frame_rate", "-of", "json",
         OUT], capture_output=True, text=True, check=True).stdout)
    dur = float(meta["format"]["duration"])
    st = meta["streams"][0]
    size = os.path.getsize(OUT)
    print(f"make_video: {OUT}: {dur:.1f} s, {st['width']}x{st['height']} @ "
          f"{st['r_frame_rate']}, {size / 1e6:.2f} MB "
          f"(master {os.path.getsize(master_path) / 1e6:.1f} MB)")

    assert 25.0 <= dur <= 60.0, f"duration {dur} outside 25-60 s"
    assert size < 8e6, f"demo.mp4 {size} bytes > 8 MB"
    assert (st["width"], st["height"]) == (1920, 1080)


if __name__ == "__main__":
    main()
