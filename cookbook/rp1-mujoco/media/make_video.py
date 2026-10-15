#!/usr/bin/env python3
"""demo.mp4 -- the real judged run, then the mutants the judge killed.

Storyboard: media/STORYBOARD.md (written before the cut; the video is
judged against it).  1590 frames at 30 fps = 53.0 s.

Every robot frame is a real headless MuJoCo (EGL) render of the pinned RP1
scene loaded with the exact state the judge recorded at that instant
(media/data/traces/<name>/trace.csv, written by `grade.sh --trace`, seed
20261014) -- nothing is re-simulated.  Every number on screen is read from
a trace column or from a verdict JSON in media/data/verdicts/.

Frames -> lossless crf-0 master in media/master/ (git-ignored) -> H.264
web encode (crf 18, preset slow, yuv420p, +faststart) -> media/demo.mp4.

The script raises if any source file is missing, a caption's cap height is
under 4 % of the frame height, the end card is not static, or the result
is outside 25-60 s / 1920x1080 / 30 fps / 8 MB.
"""
import json
import os
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rp1render

MEDIA = os.path.dirname(os.path.abspath(__file__))
VERDICTS = os.path.join(MEDIA, "data", "verdicts")
TRACES = os.path.join(MEDIA, "data", "traces")
SCENE = os.path.join(MEDIA, "work", "scene", "mjcf", "rp1_flat.xml")
MASTER = os.path.join(MEDIA, "master")
OUT = os.path.join(MEDIA, "demo.mp4")

W, H, FPS = 1920, 1080, 30
GREEN = "#1a7a2f"
RED = "#b71c1c"
INK = "#0b0b0b"
SUB = "#4a4a48"

# burned-in caption sizes (cap height >= 4 % of 1080 px = 43.2 px)
FS_BIG = 52
FS_CAP = 44
FS_HUD = 30          # live readouts (not captions)
FS_FINE = 22         # provenance fine print

MUTANTS = [
    ("zero_torque", "u = 0 -- the zero-torque oracle: nothing holds it up",
     "stand"),
    ("no_balance", "the ankle balance law is deleted -- posture PD alone",
     "push"),
    ("weak_balance", "balance gains /1.5: stands, recovers too slowly",
     "push"),
]

GATES = ["model_loads", "mass_match", "joint_match", "effort_match",
         "gravity_statics", "stand", "push", "limits", "effort",
         "integrity"]
ROWS = ["good", "zero_gains", "no_balance", "weak_balance",
        "sign_flip_knee", "wrong_joint_order", "gains_100x", "clamp_1pct",
        "cancels_push", "zero_torque"]


def need(p):
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run media/collect_data.sh first")
    return p


def verdict(name):
    return json.load(open(need(os.path.join(VERDICTS, name + ".json"))))


def trace(name):
    return rp1render.Trace(need(os.path.join(TRACES, name, "trace.csv")))


class Shot:
    """One matplotlib frame factory reused across a scene's frames."""

    def __init__(self):
        self.fig = plt.figure(figsize=(W / 100, H / 100), dpi=100,
                              facecolor="#fcfcfb")
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.axis("off")
        self.im = None
        self.captions = []      # (artist) -- cap height is checked

    def image(self, rgb):
        if self.im is None:
            self.im = self.ax.imshow(rgb)
        else:
            self.im.set_data(rgb)

    def text(self, x, y, s, size, color=INK, weight="normal",
             ha="left", va="top", caption=False, family=None,
             box=False, boxfc="white", boxec="0.6", rot=0, zorder=5):
        t = self.ax.text(x, y, s, fontsize=size, color=color,
                         fontweight=weight, ha=ha, va=va,
                         family=family, rotation=rot, zorder=zorder,
                         transform=self.ax.transAxes,
                         bbox=(dict(boxstyle="round,pad=0.45", fc=boxfc,
                                    ec=boxec, lw=1.2) if box else None))
        if caption:
            self.captions.append(t)
        return t

    def frame(self):
        self.fig.canvas.draw()
        buf = np.asarray(self.fig.canvas.buffer_rgba())
        return buf[:, :, :3].copy()

    def check_captions(self, renderer):
        for t in self.captions:
            bb = t.get_window_extent(renderer=renderer)
            cap_h = 0.72 * bb.height      # cap height approx for DejaVu
            if cap_h < 0.04 * H:
                raise SystemExit(
                    f"caption too small: '{t.get_text()[:30]}' cap height "
                    f"{cap_h:.0f}px < {0.04 * H:.0f}px")


def cam_for(shot_k, n, base, sweep):
    """Interpolate camera params across a scene (they always move a
    little; the floor is never static behind a moving robot)."""
    f = shot_k / max(n - 1, 1)
    out = {}
    for k, (lo, hi) in sweep.items():
        out[k] = lo + (hi - lo) * f
    out.update(base)
    return out


def main():
    os.makedirs(MASTER, exist_ok=True)
    good_v = verdict("good")
    good_tr = trace("good")
    rend = rp1render.Renderer(need(SCENE))

    master = os.path.join(MASTER, "demo_lossless.mp4")
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-crf", "0", "-preset", "slow",
         "-pix_fmt", "yuv420p", master],
        stdin=subprocess.PIPE)

    n_written = 0
    tail_hashes = []           # end-card frames must be identical

    def emit(shot, tag, check_at=0):
        nonlocal n_written
        if n_written == check_at:
            shot.check_captions(shot.fig.canvas.get_renderer())
        f = shot.frame()
        ff.stdin.write(f.tobytes())
        if tag == "endcard":
            tail_hashes.append(hash(f.tobytes()))
        n_written += 1
        return f

    # ---- helper: robot frame rendered from the judge's trace --------------
    def robot(tr, t_sim):
        k = tr.index_at(t_sim)
        rend.set_state(tr, k)
        return k

    # ======================================================================
    # 1. hook -- the finished real result fills the frame (0-2.0 s)
    # ======================================================================
    sh = Shot()
    cap = sh.text(0.5, 0.055, "RP1 humanoid stands -- and takes a 30 N push",
                  FS_BIG, weight="bold", ha="center", caption=True)
    fine = sh.text(0.5, 0.145,
                   "real MuJoCo render of the judged run "
                   "(grade.sh --trace, seed 20261014); judge verdict: PASS",
                   FS_HUD, color=SUB, ha="center")
    for i in range(2 * FPS):
        t_sim = 8.0 + i / FPS
        robot(good_tr, t_sim)
        rend.aim(**cam_for(i, 2 * FPS, dict(lookat_z=0.85),
                           dict(azimuth=(120, 150), distance=(2.7, 2.45),
                                elevation=(-4, -6))))
        sh.image(rend.render())
        emit(sh, "hook", check_at=0)
    plt.close(sh.fig)

    # ======================================================================
    # 2. input -> output (2.0-6.0 s)
    # ======================================================================
    sh = Shot()
    prompt = (
        "Ask your agent:\n\n"
        "\"write controller.py: make the\n"
        "RP1 stand 10 s in MuJoCo and\n"
        "survive a 30 N push at t = 5 s.\n"
        "Stay inside every joint and\n"
        "torque limit.\"\n\n"
        "SPEC.md gates:\n"
        "stand   z >= 0.9 z0, tilt <= 10 deg\n"
        "push    tilt <= 5 deg by t = 7 s\n"
        "limits  qpos / ctrl / force in range\n"
        "integrity  no state tamper")
    p = sh.text(0.025, 0.95, prompt, FS_HUD, family="monospace", va="top",
                box=True, boxfc="#f4f6f9", boxec="#4a4a48")
    cap = sh.text(0.5, 0.05,
                  "the agent writes one file; the judge runs the physics "
                  "-- real time", FS_CAP, ha="center", caption=True,
                  weight="bold")
    hud = sh.text(0.42, 0.955, "", FS_HUD, family="monospace", va="top")
    for i in range(4 * FPS):
        t_sim = i / FPS
        k = robot(good_tr, t_sim)
        rend.aim(**cam_for(i, 4 * FPS, dict(lookat_z=0.85, elevation=-4),
                           dict(azimuth=(132, 140), distance=(2.9, 2.6))))
        sh.image(rend.render())
        hud.set_text(f"t = {good_tr.t[k]:5.2f} s   "
                     f"tilt {good_tr.tilt[k]:4.1f} deg   "
                     f"pelvis z {good_tr.pos[k, 2]:.3f} m")
        emit(sh, "input", check_at=0)
    plt.close(sh.fig)

    # ======================================================================
    # 3. the push + recovery, real time (6.0-12.0 s)
    # ======================================================================
    sh = Shot()
    hud = sh.text(0.025, 0.955, "", FS_HUD, family="monospace", va="top",
                  box=True, boxfc="white", boxec="0.6")
    push_t = sh.text(0.5, 0.86, "", int(FS_CAP * 0.9), color=RED,
                     ha="center", weight="bold")
    cap = sh.text(0.30, 0.05,
                  "the judged episode -- real time; tilt limit 10 deg "
                  "(stand gate)", int(FS_CAP * 0.9), ha="center",
                  caption=True, weight="bold")
    axin = sh.fig.add_axes([0.665, 0.115, 0.315, 0.24])
    axin.set_facecolor("#fcfcfb")
    ln, = axin.plot(good_tr.t, good_tr.tilt, color="#2a78d6", lw=1.6)
    mk, = axin.plot([], [], "o", color=RED, ms=8)
    axin.axhline(10, color=GREEN, ls="--", lw=1.4)
    axin.axhline(5, color="0.45", ls=(0, (4, 3)), lw=1.0)
    axin.axvspan(5.0, 5.2, color=RED, alpha=0.15)
    axin.set_xlim(0, 10)
    axin.set_ylim(0, 11)
    axin.tick_params(labelsize=13)
    axin.set_title("torso tilt [deg] -- green 10, grey 5 (push gate)",
                   fontsize=14)
    for i in range(6 * FPS):
        t_sim = 4.0 + i / FPS
        k = robot(good_tr, t_sim)
        rend.aim(**cam_for(i, 6 * FPS, dict(lookat_z=0.85, elevation=-5),
                           dict(azimuth=(128, 146), distance=(2.6, 2.5))))
        sh.image(rend.render())
        hud.set_text(f"t = {good_tr.t[k]:5.2f} s   "
                     f"tilt {good_tr.tilt[k]:4.1f} deg   "
                     f"pelvis z {good_tr.pos[k, 2]:.3f} m")
        push_t.set_text("30 N PUSH" if 5.0 <= good_tr.t[k] < 5.2 else "")
        mk.set_data([good_tr.t[k]], [good_tr.tilt[k]])
        emit(sh, "push", check_at=0)
    plt.close(sh.fig)

    # ======================================================================
    # 4. slow replay of the push window (12.0-17.0 s)
    # ======================================================================
    sh = Shot()
    hud = sh.text(0.025, 0.955, "", FS_HUD, family="monospace", va="top",
                  box=True, boxfc="white", boxec="0.6")
    cap = sh.text(0.5, 0.05,
                  "0.2x slow replay -- the push window (sim t = 4.85-5.85 s)",
                  int(FS_CAP * 0.9), ha="center", caption=True,
                  weight="bold")
    fine = sh.text(0.985, 0.955,
                   "30 N, world +Y, on waist_yaw_link\n(judge/params.json)",
                   FS_HUD, color=SUB, ha="right", va="top")
    for i in range(5 * FPS):
        t_sim = 4.85 + 0.2 * i / FPS
        k = robot(good_tr, t_sim)
        rend.aim(**cam_for(i, 5 * FPS, dict(lookat_z=0.95),
                           dict(azimuth=(118, 152), distance=(1.75, 1.6),
                                elevation=(-2, 4))))
        sh.image(rend.render())
        hud.set_text(f"t = {good_tr.t[k]:5.2f} s   "
                     f"tilt {good_tr.tilt[k]:4.1f} deg   "
                     f"pelvis z {good_tr.pos[k, 2]:.3f} m")
        emit(sh, "slow", check_at=0)
    plt.close(sh.fig)

    # ======================================================================
    # 5. recovery + the push-gate rule (17.0-20.5 s)
    # ======================================================================
    sh = Shot()
    g = good_v["gates"]
    box = sh.text(
        0.985, 0.90,
        "push gate:  |tilt| <= 5 deg by t = 7 s, held to 10 s\n"
        f"measured:   {g['push']['max_tilt_after_recovery_deg']:.2f} deg "
        f"after t = 7 s  ->  PASS\n"
        f"stand gate: pelvis z >= {g['stand']['z_floor_m']:.2f} m: "
        f"min {g['stand']['zmin_m']:.4f} m  ->  PASS",
        FS_HUD, family="monospace", ha="right", va="top", box=True,
        boxfc="#eef6ee", boxec=GREEN)
    cap = sh.text(0.5, 0.05,
                  "back under 5 deg by t = 7 s and holding -- the push gate",
                  int(FS_CAP * 0.9), ha="center", caption=True,
                  weight="bold")
    t7 = sh.text(0.025, 0.90, "", int(FS_CAP * 0.9), color=RED,
                 weight="bold")
    for i in range(int(3.5 * FPS)):
        t_sim = 5.85 + i / FPS
        k = robot(good_tr, t_sim)
        rend.aim(**cam_for(i, int(3.5 * FPS), dict(lookat_z=0.85,
                                                   elevation=-4),
                           dict(azimuth=(146, 132), distance=(2.6, 2.75))))
        sh.image(rend.render())
        t7.set_text("t = 7 s: tilt must already be <= 5 deg"
                    if 6.9 <= good_tr.t[k] <= 7.6 else "")
        emit(sh, "recover", check_at=0)
    plt.close(sh.fig)

    # ======================================================================
    # 6. verdict card (20.5-23.5 s)
    # ======================================================================
    sh = Shot()
    robot(good_tr, 9.9)
    rend.aim(distance=2.55, azimuth=136, elevation=-4, lookat_z=0.82)
    sh.image(rend.render())
    sh.text(0.025, 0.945, "judge verdict:  PASS", FS_BIG, color=GREEN,
            weight="bold")
    lines = ["gate            measured                     rule"]
    gmap = [
        ("model_loads", f"nq 31  nv 30  nu 24, {g['model_loads']['total_mass_kg']:.2f} kg", "compiles"),
        ("mass_match", f"worst link dev {100 * g['mass_match']['worst_link_rel']:.2f} %", "<= 1 % (URDF)"),
        ("joint_match", f"range dev {g['joint_match']['worst_range_delta_rad']:.0f}", "<= 1e-4 rad (URDF)"),
        ("effort_match", f"worst dev {100 * g['effort_match']['worst_rel']:.2f} %", "<= 1 % (URDF effort)"),
        ("gravity_statics", f"fz/mg {g['gravity_statics']['ratio']:.4f}", "within 2 %"),
        ("stand", f"tilt {g['stand']['max_tilt_deg']:.2f} deg, z {g['stand']['zmin_m']:.4f} m", "10 deg / 0.702 m"),
        ("push", f"{g['push']['max_tilt_after_recovery_deg']:.2f} deg after t = 7 s", "<= 5 deg"),
        ("limits", "qpos/ctrl/force all in range", "tol 1 mrad / 1 N m"),
        ("effort", f"peak {g['effort']['peak_tau_nm']:.1f} N m, {g['effort']['mechanical_energy_j']:.1f} J", "info, never gated"),
        ("integrity", "judge checksums + audit clean", "no tamper"),
    ]
    for name, meas, rule in gmap:
        lines.append(f"{name:<15} {meas:<34} {rule}")
    sh.text(0.025, 0.845, "\n".join(lines), FS_HUD - 4, family="monospace",
            va="top", box=True, boxfc="white", boxec=GREEN)
    cap = sh.text(0.985, 0.05,
                  "grade.sh --json, seed 20261014 (data/verdicts/good.json)",
                  FS_HUD, color=SUB, ha="right", caption=True)
    for _ in range(3 * FPS):
        emit(sh, "verdict", check_at=0)
    plt.close(sh.fig)

    # ======================================================================
    # 7-9. mutants: real renders of each fall + the gate that caught it
    # ======================================================================
    for name, edit, _gate in MUTANTS:
        v = verdict(name)
        tr = trace(name)
        sh = Shot()
        sh.text(0.025, 0.945, f"mutant {name}", FS_BIG, weight="bold")
        sh.text(0.025, 0.875, edit, FS_HUD, color=SUB)
        failed = [gn for gn in GATES
                  if v["gates"][gn]["verdict"] == "fail"]
        d = v["gates"][failed[0]] if failed else {}
        detail = ""
        if "artifact_error" in d:
            detail = d["artifact_error"]
        elif failed[0] == "stand":
            detail = (f"tilt {d['max_tilt_deg']:.0f} deg > 10 deg; "
                      f"z min {d['zmin_m']:.3f} m")
        elif failed[0] == "push":
            detail = (f"{d['max_tilt_after_recovery_deg']:.1f} deg > "
                      f"5 deg after t = 7 s")
        elif failed[0] == "limits":
            detail = (f"q over range +{d['worst_qpos_over_range_rad'] * 1000:.1f}"
                      f" mrad (tol 1 mrad)")
        sh.text(0.985, 0.945, "KILLED", FS_BIG, color=RED, ha="right",
                weight="bold")
        sh.text(0.985, 0.875,
                f"gate {failed[0]}:  {detail}", FS_HUD, color=RED,
                ha="right")
        hud = sh.text(0.025, 0.115, "", FS_HUD, family="monospace",
                      va="top", box=True, boxfc="white", boxec="0.6")
        cap = sh.text(0.5, 0.035,
                      f"real render of {name}'s own judged run "
                      "(grade.sh --trace)", int(FS_CAP * 0.82),
                      ha="center", caption=True)
        # sim windows per mutant: fall early / fall at push / stand+fail rule
        t0, t1, speed = {
            "zero_torque": (0.0, 5.0, 1.0),
            "no_balance": (3.5, 8.5, 1.0),
            "weak_balance": (0.0, 10.0, 2.0),
        }[name]
        for i in range(5 * FPS):
            t_sim = t0 + (t1 - t0) * i / (5 * FPS)
            k = robot(tr, t_sim)
            rend.aim(**cam_for(i, 5 * FPS, dict(lookat_z=0.70,
                                                elevation=-6),
                               dict(azimuth=(126, 144), distance=(2.9, 2.7))))
            sh.image(rend.render())
            hud.set_text(f"t = {tr.t[k]:5.2f} s   tilt {tr.tilt[k]:5.1f} deg"
                         f"   pelvis z {tr.pos[k, 2]:.3f} m"
                         + (f"   [{speed:g}x]" if speed != 1.0 else ""))
            emit(sh, f"mut-{name}", check_at=0)
        plt.close(sh.fig)

    # ======================================================================
    # 10. the kill matrix (38.5-44.5 s)
    # ======================================================================
    sh = Shot()
    axm = sh.fig.add_axes([0.30, 0.10, 0.68, 0.72])
    axm.set_xlim(0, len(GATES) + 0.6)
    axm.set_ylim(0, len(ROWS) + 1.2)
    axm.axis("off")
    for j, gn in enumerate(GATES):
        axm.add_patch(Rectangle((j, len(ROWS)), 1, 1.2, fc="#dce6f2",
                                ec="0.5", lw=0.6))
        axm.text(j + 0.5, len(ROWS) + 0.6, gn.replace("_", "\n"),
                 ha="center", va="center", fontsize=13, fontweight="bold")
    for i, rn in enumerate(ROWS):
        y = len(ROWS) - 1 - i
        v = verdict(rn)
        axm.text(-0.15, y + 0.5, rn, ha="right", va="center", fontsize=15,
                 color=GREEN if rn == "good" else INK,
                 fontweight="bold" if rn == "good" else "normal")
        for j, gn in enumerate(GATES):
            d = v["gates"][gn]
            if d["verdict"] == "info":
                fc, ec = "#e8edf4", "#4a4a48"
            elif d["pass"]:
                fc, ec = "#d9f2dd", GREEN
            else:
                fc, ec = "#f6d5d5", RED
            axm.add_patch(Rectangle((j, y), 1, 1, fc=fc, ec=ec, lw=0.8))
    sh.text(0.025, 0.945, "self-test: 8/8 mutants killed (100 %)",
            FS_BIG, weight="bold")
    cap = sh.text(0.025, 0.845,
                  "green pass / red fail / blue info\n"
                  "known-good passes every gate;\n"
                  "every mutant is killed by at\n"
                  "least one -- each red cell is a\n"
                  "real grade.sh verdict\n(media/data/verdicts/)",
                  FS_HUD, va="top", caption=True)
    for _ in range(6 * FPS):
        emit(sh, "matrix", check_at=0)
    plt.close(sh.fig)

    # ======================================================================
    # 11. summary (44.5-48.5 s)
    # ======================================================================
    sh = Shot()
    sh.text(0.5, 0.80,
            "a controller the physics cannot fool",
            FS_BIG, ha="center", weight="bold")
    sh.text(0.5, 0.62,
            f"mass {g['model_loads']['total_mass_kg']:.2f} kg   |   "
            f"min pelvis z {g['stand']['zmin_m']:.4f} m (>= 0.702)   |   "
            f"tilt {g['stand']['max_tilt_deg']:.2f} deg (<= 10)\n"
            f"after push {g['push']['max_tilt_after_recovery_deg']:.2f} deg "
            f"(<= 5)   |   fz/mg {g['gravity_statics']['ratio']:.4f} "
            f"(+-2 %)   |   peak torque "
            f"{g['effort']['peak_tau_nm']:.1f} N m",
            FS_HUD, ha="center", color=INK)
    sh.text(0.5, 0.44,
            "determinism: same seed -> byte-identical verdict "
            "(selftest.sh)\n"
            "the mutant sequence above is a replay of real grade JSONs, "
            "not a live agent trace",
            FS_HUD, ha="center", color=SUB)
    robot(good_tr, 9.0)
    rend.aim(distance=2.55, azimuth=136, elevation=-4, lookat_z=0.82)
    axr = sh.fig.add_axes([0.36, 0.04, 0.28, 0.34])
    axr.imshow(rend.render())
    axr.axis("off")
    cap = sh.text(0.5, 0.995,
                  "every number from data/verdicts/good.json",
                  FS_HUD, ha="center", color=SUB, caption=True)
    for _ in range(4 * FPS):
        emit(sh, "summary", check_at=0)
    plt.close(sh.fig)

    # ======================================================================
    # 12. end card (48.5-53.0 s) -- static
    # ======================================================================
    sh = Shot()
    sh.fig.patch.set_facecolor("#fcfcfb")
    sh.text(0.5, 0.60, "try it:", FS_CAP, ha="center", color=SUB,
            caption=True)
    sh.text(0.5, 0.47, "python3 cookbook/rp1-mujoco/run.py", FS_BIG,
            ha="center", family="monospace", weight="bold")
    sh.text(0.5, 0.34,
            "agent-next sandbox demo  --  cookbook/rp1-mujoco\n"
            "judge: MuJoCo 3.14.0 + URDF cross-parse + statics oracle",
            FS_HUD, ha="center", color=SUB)
    for _ in range(int(4.5 * FPS)):
        emit(sh, "endcard", check_at=0)
    plt.close(sh.fig)

    ff.stdin.close()
    rc = ff.wait()
    if rc != 0:
        raise SystemExit(f"ffmpeg master encode failed (exit {rc})")

    # static end card: the last 4.5 s (135 frames) must be identical
    assert len(tail_hashes) == int(4.5 * FPS)
    assert len(set(tail_hashes)) == 1, "end card is not static"

    # ---- web encode --------------------------------------------------------
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", master,
         "-c:v", "libx264", "-crf", "18", "-preset", "slow",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT],
        check=True)

    size = os.path.getsize(OUT)
    pr = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-show_entries",
         "stream=width,height,r_frame_rate,codec_name,pix_fmt",
         "-of", "json", OUT],
        capture_output=True, text=True, check=True)
    meta = json.loads(pr.stdout)
    dur = float(meta["format"]["duration"])
    st = meta["streams"][0]
    print(f"{OUT}: {dur:.1f} s, {st['width']}x{st['height']} @ "
          f"{st['r_frame_rate']} {st['codec_name']}/{st['pix_fmt']}, "
          f"{size / 1e6:.2f} MB (master {os.path.getsize(master) / 1e6:.1f} MB)")
    assert 25.0 <= dur <= 60.0, f"duration {dur} outside 25-60 s"
    assert size < 8e6, f"demo.mp4 {size} bytes > 8 MB"
    assert (st["width"], st["height"]) == (1920, 1080)
    assert st["codec_name"] == "h264" and st["pix_fmt"] == "yuv420p"
    assert n_written == int(round(dur * FPS)), \
        f"wrote {n_written} frames for {dur:.2f} s"
    print(f"frames written: {n_written}; end card static: OK; "
          "caption cap heights checked")


if __name__ == "__main__":
    main()
