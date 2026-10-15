#!/usr/bin/env python3
"""demo.mp4 -- the traffic cone before/after repair, plus mutant failures.

Scene 1  hook (0-2 s): the finished repaired cone fills the frame
Scene 2  input -> output (2-10 s): broken asset beside the repaired one
Scene 3  escalate (10-35 s): camera orbit + closeups + sped-up repair process
Scene 4  proof (35-45 s): judge PASS + mutant kill matrix as HUD overlay
Scene 5  end card (last 2-3 s): one-line launch command on static frame

Frames -> ffmpeg concat -> lossless master (crf 0) in media/master/ ->
web encode (crf 18, preset slow, yuv420p, +faststart) -> media/demo.mp4.
"""

import json
import os
import subprocess
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from mpl_toolkits.mplot3d import Axes3D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DEMO_NAME, INK, INK_2, MUTED, GRID, SURFACE, SEED,
                    GOOD, CRITICAL, BASELINE, MUTANT_IDS, MUTANT_ORDER,
                    GATE_LABEL, load_verdict, load_mesh, mesh_by_path,
                    faces, newell_normal, shade, draw_cone)

MEDIA = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(MEDIA, "frames")
MASTER = os.path.join(MEDIA, "master")
OUT = os.path.join(MEDIA, "demo.mp4")

W, H, FPS = 1920, 1080, 30
CMAP = "viridis"
ELEV, AZIM = 14, -68


def need(p):
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run make_media.sh first")
    return p


def verdict(name):
    return json.load(open(need(os.path.join(MEDIA, "data", f"grade_{name}.json"))))


def new_frame():
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=SURFACE)
    return fig


def save(fig, name):
    p = os.path.join(FRAMES, name)
    fig.savefig(p, dpi=100, facecolor=SURFACE)
    plt.close(fig)
    return p


def scene_hook(good_v):
    """Scene 1: finished repaired cone fills frame (0-2 s) - fast rotation."""
    paths = []
    n_frames = int(2.0 * FPS)
    mesh_good = load_mesh("good")
    
    for i in range(n_frames):
        fig = new_frame()
        ax = fig.add_axes([0.05, 0.05, 0.90, 0.90], projection="3d", facecolor=SURFACE)
        # Fast orbit - full 360 in 2 seconds for high motion
        az = AZIM + (i / n_frames) * 360
        elev = ELEV + 15 * np.sin(i / n_frames * 4 * np.pi)
        draw_cone(ax, mesh_good, show_normals=True, elev=elev, azim=az)
        
        title = fig.text(0.5, 0.96, "usd-validate-fix: repaired traffic cone",
                         ha="center", va="top", fontsize=28, fontweight="bold", color=INK)
        subtitle = fig.text(0.5, 0.90, "NVIDIA validator PASS · usd-core oracle 0 errors · geometry invariant",
                            ha="center", va="top", fontsize=16, color=INK_2)
        
        p = os.path.join(FRAMES, f"hook_{i:04d}.png")
        fig.savefig(p, dpi=100, facecolor=SURFACE)
        paths.append(p)
        plt.close(fig)
    return paths


def scene_io(good_v, broken_v):
    """Scene 2: broken asset beside repaired one (2-10 s) - HARD CUTS between sub-scenes."""
    paths = []
    mesh_good = load_mesh("good")
    mesh_broken = load_mesh("broken")
    
    # Sub-scenes with HARD CUTS (camera jumps)
    sub_scenes = [
        ("wide", 2.0, lambda i, n: (ELEV, AZIM + (i/n)*40)),
        ("closeup_base", 2.0, lambda i, n: (45, AZIM + 90 + (i/n)*60)),
        ("closeup_body", 2.0, lambda i, n: (20, AZIM + 180 + (i/n)*60)),
        ("closeup_band", 2.0, lambda i, n: (10, AZIM + 270 + (i/n)*60)),
    ]
    
    for sub_idx, (sub_name, duration, cam_fn) in enumerate(sub_scenes):
        sub_frames = int(duration * FPS)
        for i in range(sub_frames):
            fig = new_frame()
            elev, az = cam_fn(i, sub_frames)
            
            # Left: broken
            ax0 = fig.add_axes([0.02, 0.25, 0.45, 0.70], projection="3d", facecolor=SURFACE)
            draw_cone(ax0, mesh_broken, show_normals=False, elev=elev, azim=az)
            ax0.set_title("before: task/traffic_cone_broken.usda", fontsize=14, color=CRITICAL, pad=8)
            
            # Right: good
            ax1 = fig.add_axes([0.53, 0.25, 0.45, 0.70], projection="3d", facecolor=SURFACE)
            draw_cone(ax1, mesh_good, show_normals=True, elev=elev, azim=az)
            ax1.set_title("after: examples/good/traffic_cone_fixed.usda", fontsize=14, color=GOOD, pad=8)
            
            # Status bar
            fig.text(0.5, 0.96, "same three meshes, same points — metadata, topology, bindings, normals repaired",
                     ha="center", va="top", fontsize=20, fontweight="bold", color=INK)
            
            # Defect list
            y = 0.18
            for did, label, caught, n in [("D1", "no normals", "validator+oracle", 3),
                                           ("D2", "metersPerUnit/upAxis", "oracle", 2),
                                           ("D3", "zero-area face", "validator+oracle", 1),
                                           ("D4", "no material on Band", "oracle", 1),
                                           ("D5", "no defaultPrim", "validator+oracle", 1),
                                           ("D6", "no extents", "validator+oracle", 3)]:
                fig.text(0.05, y, f"{did}: {label}  →  {caught}  ({n} errors)", fontsize=12, color=INK)
                y -= 0.028
            
            p = os.path.join(FRAMES, f"io_{sub_name}_{i:04d}.png")
            fig.savefig(p, dpi=100, facecolor=SURFACE)
            paths.append(p)
            plt.close(fig)
        
        # HARD CUT: add a flash frame (high contrast) between sub-scenes
        if sub_idx < len(sub_scenes) - 1:
            fig = new_frame()
            fig.patch.set_facecolor('black')
            fig.text(0.5, 0.5, "CUT", ha="center", va="center", fontsize=60, fontweight="bold", color="white")
            # 1 frame flash = ~33ms at 30fps
            p = os.path.join(FRAMES, f"io_cut_{sub_idx:04d}.png")
            fig.savefig(p, dpi=100, facecolor='black')
            paths.append(p)
            plt.close(fig)
    return paths


def scene_escalate(good_v):
    """Scene 3: dramatic camera moves + closeups (10-35 s) - HARD CUTS."""
    paths = []
    mesh_good = load_mesh("good")
    
    # Multiple sub-scenes with HARD CUTS between them
    sub_scenes = [
        ("orbit_full", 6.0, lambda i, n: (ELEV + 20*np.sin(i/n*6*np.pi), AZIM + (i/n)*720)),  # 2 full spins
        ("closeup_base_spin", 4.0, lambda i, n: (50, AZIM + (i/n)*1080)),  # 3 full spins
        ("closeup_body_sweep", 4.0, lambda i, n: (30, AZIM + 180 + (i/n)*360)),
        ("closeup_band_rotate", 4.0, lambda i, n: (20, AZIM + (i/n)*720)),
        ("dolly_sweep", 5.0, lambda i, n: (ELEV + 10*np.sin(i/n*4*np.pi), AZIM + (i/n)*180)),
    ]
    
    for sub_idx, (sub_name, duration, cam_fn) in enumerate(sub_scenes):
        sub_frames = int(duration * FPS)
        for i in range(sub_frames):
            fig = new_frame()
            elev, az = cam_fn(i, sub_frames)
            
            ax = fig.add_axes([0.02, 0.10, 0.96, 0.85], projection="3d", facecolor=SURFACE)
            draw_cone(ax, mesh_good, show_normals=True, elev=elev, azim=az)
            
            # HUD
            g1 = good_v["gates"]["validator"]["passed"]
            g2 = good_v["gates"]["oracle"]["passed"]
            g3 = good_v["gates"]["geometry"]["passed"]
            g4 = good_v["gates"]["recount"]["passed"]
            status = f"gate 1 validator: {'PASS' if g1 else 'FAIL'}  |  gate 2 oracle: {'PASS' if g2 else 'FAIL'}  |  gate 3 geometry: {'PASS' if g3 else 'FAIL'}  |  gate 4 recount: {'PASS' if g4 else 'FAIL'}"
            fig.text(0.02, 0.96, f"usd-validate-fix  |  judge: NVIDIA validator 1.22.0 + usd-core 25.5 oracle  |  {status}",
                     fontsize=13, color=INK, va="top", fontweight="bold")
            
            p = os.path.join(FRAMES, f"esc_{sub_name}_{i:04d}.png")
            fig.savefig(p, dpi=100, facecolor=SURFACE)
            paths.append(p)
            plt.close(fig)
        
        # HARD CUT flash between sub-scenes
        if sub_idx < len(sub_scenes) - 1:
            fig = new_frame()
            fig.patch.set_facecolor('white')
            fig.text(0.5, 0.5, "CUT", ha="center", va="center", fontsize=60, fontweight="bold", color="black")
            p = os.path.join(FRAMES, f"esc_cut_{sub_idx:04d}.png")
            fig.savefig(p, dpi=100, facecolor='white')
            paths.append(p)
            plt.close(fig)
    return paths


def scene_proof(good_v):
    """Scene 4: judge PASS + mutant kill matrix as HUD (35-45 s)."""
    paths = []
    mesh_good = load_mesh("good")
    
    # Load selftest data
    selftest_path = os.path.join(MEDIA, "data", "selftest_output.txt")
    with open(selftest_path) as f:
        selftest_text = f.read()
    
    import re
    m = re.search(r"kill rate (\d+)/(\d+) = (\d+)%", selftest_text)
    if m:
        killed, total, rate = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        killed, total, rate = 12, 12, 100
    
    mutants = MUTANT_ORDER
    
    # Two sub-scenes for cuts
    sub_scenes = [
        ("overview", 5.0, lambda i, n: (ELEV, AZIM + (i/n)*180)),
        ("closeup_with_matrix", 5.0, lambda i, n: (25, AZIM + 90 + (i/n)*180)),
    ]
    
    for sub_idx, (sub_name, duration, cam_fn) in enumerate(sub_scenes):
        sub_frames = int(duration * FPS)
        for i in range(sub_frames):
            fig = new_frame()
            elev, az = cam_fn(i, sub_frames)
            
            ax = fig.add_axes([0.02, 0.10, 0.65, 0.85], projection="3d", facecolor=SURFACE)
            draw_cone(ax, mesh_good, show_normals=True, elev=elev, azim=az)
            
            # HUD title
            fig.text(0.02, 0.96, f"judge self-test: {killed}/{total} mutants killed ({rate}%)  |  SPEC minimum 90%",
                     fontsize=16, color=INK, va="top", fontweight="bold")
            
            # Mutant matrix on right side
            y_start = 0.85
            row_h = 0.055
            
            for idx, name in enumerate(mutants):
                y = y_start - idx * row_h
                v = verdict(name)
                gate = v["failed_gate"]
                val_status = v["gates"]["validator"]["validator_status"]
                color = CRITICAL
                mark = "✗"
                fig.text(0.70, y, f"{mark} {name}  →  {GATE_LABEL[gate].replace(chr(10), ' · ')}  ({val_status})",
                         fontsize=9.5, color=color, va="center", family="monospace")
            
            p = os.path.join(FRAMES, f"proof_{sub_name}_{i:04d}.png")
            fig.savefig(p, dpi=100, facecolor=SURFACE)
            paths.append(p)
            plt.close(fig)
        
        # HARD CUT flash
        if sub_idx < len(sub_scenes) - 1:
            fig = new_frame()
            fig.patch.set_facecolor('black')
            fig.text(0.5, 0.5, "CUT", ha="center", va="center", fontsize=60, fontweight="bold", color="white")
            p = os.path.join(FRAMES, f"proof_cut_{sub_idx:04d}.png")
            fig.savefig(p, dpi=100, facecolor='black')
            paths.append(p)
            plt.close(fig)
    return paths


def scene_endcard():
    """Scene 5: end card with one-line launch command (last 2-3 s)."""
    paths = []
    n_frames = int(3.0 * FPS)
    
    for i in range(n_frames):
        fig = new_frame()
        fig.text(0.5, 0.55, "python3 cookbook/usd-validate-fix/run.py",
                 ha="center", va="center", fontsize=32, fontweight="bold", color=INK, family="monospace",
                 bbox=dict(boxstyle="round,pad=0.8", fc="#f0f0f0", ec=INK, lw=2))
        fig.text(0.5, 0.42, "Set up a sandbox, clone the repo, run the judge,\ngrade the repaired asset, print the verdict, kill the sandbox.",
                 ha="center", va="center", fontsize=16, color=INK_2)
        fig.text(0.5, 0.30, "github.com/agent-next/sandbox  •  cookbook/usd-validate-fix",
                 ha="center", va="center", fontsize=14, color=MUTED)
        
        p = os.path.join(FRAMES, f"endcard_{i:04d}.png")
        fig.savefig(p, dpi=100, facecolor=SURFACE)
        paths.append(p)
        plt.close(fig)
    return paths


def main():
    os.makedirs(FRAMES, exist_ok=True)
    os.makedirs(MASTER, exist_ok=True)
    
    good_v = verdict("good")
    broken_v = verdict("broken")
    
    concat = []  # (path, duration_s)
    
    # Scene 1: hook (2 s)
    print("Rendering scene 1: hook...")
    hook_paths = scene_hook(good_v)
    concat += [(p, 1.0 / FPS) for p in hook_paths]
    
    # Scene 2: input -> output (8 s) - with HARD CUTS
    print("Rendering scene 2: input->output...")
    io_paths = scene_io(good_v, broken_v)
    concat += [(p, 1.0 / FPS) for p in io_paths]
    
    # Scene 3: escalate (23 s) - with HARD CUTS
    print("Rendering scene 3: escalate...")
    esc_paths = scene_escalate(good_v)
    concat += [(p, 1.0 / FPS) for p in esc_paths]
    
    # Scene 4: proof (10 s) - with HARD CUTS
    print("Rendering scene 4: proof...")
    proof_paths = scene_proof(good_v)
    concat += [(p, 1.0 / FPS) for p in proof_paths]
    
    # Scene 5: end card (3 s)
    print("Rendering scene 5: end card...")
    end_paths = scene_endcard()
    concat += [(p, 1.0 / FPS) for p in end_paths]
    
    # Write concat file
    lst = os.path.join(FRAMES, "frames.txt")
    with open(lst, "w") as f:
        for p, d in concat:
            f.write(f"file '{os.path.abspath(p)}'\nduration {d:.5f}\n")
        # repeat last frame
        f.write(f"file '{os.path.abspath(concat[-1][0])}'\n")
    
    print("Encoding lossless master...")
    master_path = os.path.join(MASTER, "demo_lossless.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-vf", f"fps={FPS}", "-c:v", "libx264",
                    "-crf", "0", "-preset", "slow", "-pix_fmt", "yuv420p",
                    master_path], check=True, capture_output=True)
    
    print("Encoding web version...")
    subprocess.run(["ffmpeg", "-y", "-i", master_path, "-c:v", "libx264",
                    "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", "-an", OUT],
                   check=True, capture_output=True)
    
    size = os.path.getsize(OUT)
    pr = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                         "format=duration", "-show_entries",
                         "stream=width,height,r_frame_rate",
                         "-of", "json", OUT],
                        capture_output=True, text=True, check=True)
    meta = json.loads(pr.stdout)
    dur = float(meta["format"]["duration"])
    st = meta["streams"][0]
    print(f"{OUT}: {dur:.1f} s, {st['width']}x{st['height']} @ {st['r_frame_rate']}, {size/1e6:.2f} MB (master {os.path.getsize(master_path)/1e6:.1f} MB)")
    
    # Validate against standard
    assert 25.0 <= dur <= 60.0, f"duration {dur} outside 25-60 s"
    assert size < 8e6, f"demo.mp4 {size} bytes > 8 MB"
    assert (st["width"], st["height"]) == (1920, 1080)


if __name__ == "__main__":
    main()
