#!/usr/bin/env python3
"""Record the real motion clips (media/clips/*.mp4, 30 fps, git-ignored).

Every beam clip is the real CalculiX field of this run -- boundary quads of
the exact mesh.inc the solver consumed, displaced by the job.frd
displacement field times a printed amplification, painted with the same von
Mises colour map as result.png -- re-rendered in 3D by an ORBITING
orthographic camera (elevation and azimuth sweep per frame, painter-sorted
quads; matplotlib builds every pixel, ffmpeg only encodes the frames).

The terminal clip replays this run's real console output (judge/setup.sh,
judge/selftest.sh, judge/grade.sh) scrolled at a speed whose Nx label is
computed from the measured wall times, never invented.

Linear static note: the load ramp scales the solved field linearly (ccx
solves the full load once); the on-screen load factor states this.

clips/:
  hero.mp4      full load, close camera, fast low orbit        (the hook)
  ramp.mp4      load ramp 0 -> 1000 N, slow orbit              (input->output)
  closeup.mp4   camera dives onto the clamped wall             (escalate)
  overload.mp4  the overload-10x mutant's own field, 10x load  (escalate)
  terminal.mp4  this run's real console replay, "Nx speed"     (escalate)
  proof.mp4     full load, high slow orbit                     (PASS HUD base)
"""
import json
import os
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm, colors
from matplotlib.collections import LineCollection, PolyCollection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import beamviz

MEDIA = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(MEDIA, "work")
CLIPS = os.path.join(MEDIA, "clips")
TMP = os.path.join(WORK, "clip_frames")

W, H, FPS = 1920, 1080, 30
CMAP = "viridis"
ALLOW = 250.0 / 1.5
BG = "#0d1117"          # matches the composition background


def encode(frames_glob, out, lossless=True):
    """ffmpeg ONLY encodes: PNG frames -> mp4 (30 fps, yuv420p)."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS),
           "-i", frames_glob]
    if lossless:
        cmd += ["-c:v", "libx264", "-qp", "0", "-preset", "fast"]
    else:
        cmd += ["-c:v", "libx264", "-crf", "10", "-preset", "slow"]
    cmd += ["-pix_fmt", "yuv420p", out]
    subprocess.run(cmd, check=True)


class BeamCam:
    """One figure reused across frames: set camera + field, savefig."""

    def __init__(self, fields, vmax, pad_frac=0.06):
        self.coords, self.conn = fields["coords"], fields["conn"]
        self.disp, self.vm = fields["disp"], fields["vm"]
        self.faces = beamviz.boundary_faces(self.conn)
        self.center = (self.coords.min(axis=0) + self.coords.max(axis=0)) / 2
        self.span = float(np.linalg.norm(
            self.coords.max(axis=0) - self.coords.min(axis=0)))
        self.vmax = vmax
        self.pad_frac = pad_frac
        self.fig = plt.figure(figsize=(W / 100, H / 100), dpi=100,
                              facecolor=BG)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_facecolor(BG)
        self.ax.axis("off")
        self.coll = PolyCollection(
            [], array=[], cmap=CMAP,
            norm=colors.BoundaryNorm(np.linspace(0.0, vmax, 25), 256),
            edgecolors=(0.03, 0.05, 0.09, 0.7),
            linewidths=0.6, antialiased=False)
        self.ax.add_collection(self.coll)
        # turntable grid floor under the beam (rotates with the camera):
        # lines on the plane below the undeformed beam, real 3-D viz grid
        c0, c1 = self.coords.min(axis=0), self.coords.max(axis=0)
        Lx, Ly = c1[0] - c0[0], c1[1] - c0[1]
        zf = c0[2] - 0.12 * (c1[2] - c0[2])
        segs = []
        for gx in np.linspace(c0[0], c1[0], 41):
            segs.append([[gx, c0[1] - 0.6 * Ly, zf],
                         [gx, c1[1] + 0.6 * Ly, zf]])
        for gy in np.linspace(c0[1] - 0.6 * Ly, c1[1] + 0.6 * Ly, 11):
            segs.append([[c0[0], gy, zf], [c1[0], gy, zf]])
        self.grid3d = np.array(segs)                     # (M,2,3)
        self.grid = LineCollection(
            [], colors=(0.35, 0.48, 0.65, 0.45), linewidths=1.0,
            zorder=0)
        self.ax.add_collection(self.grid)
        self.ghost = LineCollection([], colors="#3d5a80", linewidths=1.4,
                                    linestyles=(0, (4, 4)), alpha=0.75)
        self.ax.add_collection(self.ghost)

        # colour-bar: the map is the same viridis normalisation the judge
        # numbers use; the allowable stress is ticked explicitly.
        cax = self.fig.add_axes([0.615, 0.055, 0.30, 0.016])
        cb = self.fig.colorbar(self.coll, cax=cax, orientation="horizontal",
                               extend="max")
        cb.set_ticks([0, ALLOW])
        cb.set_ticklabels(["0", f"{ALLOW:.0f} = allowable"])
        cb.ax.tick_params(colors="#c9d1d9", labelsize=15, length=0)
        cb.outline.set_visible(False)
        cax.set_title(f"von Mises stress (MPa), max {vmax:.0f}",
                      color="#c9d1d9", fontsize=15, loc="left", pad=4)

    def frame(self, lam, scale, elev, azim, zoom=1.0, center_on=None,
              path=None):
        """Render one frame: load factor, camera (elev/azim deg), zoom."""
        xyz = (self.coords + scale * lam * self.disp)[self.faces]
        if center_on is None:
            # track the DISPLACED surface centroid -- the amplified beam
            # stays centred at any zoom and under any load factor
            ctr = xyz.mean(axis=(0, 1))
        else:
            nn = int(np.argmin(
                np.linalg.norm(self.coords - center_on, axis=1)))
            ctr = center_on + scale * lam * self.disp[nn]
        rel = xyz - ctr                                   # (K,4,3)
        v, r, u = beamviz.view_axes(elev, azim)
        px, py = rel @ r, rel @ u
        depth = rel @ v
        order = np.argsort(depth.mean(axis=1), kind="stable")
        verts = np.stack([px, py], axis=-1)[order]
        fvm = np.nan_to_num(lam * self.vm[self.faces].mean(axis=1),
                            nan=0.0)[order]
        self.coll.set_verts(verts)
        self.coll.set_array(fvm)

        # turntable grid floor under the same camera
        grel = self.grid3d - ctr
        gseg = np.stack([grel @ r, grel @ u], axis=-1)
        self.grid.set_segments(gseg)

        # undeformed silhouette as a dashed ghost under the same camera
        c0 = self.coords.min(axis=0) - ctr
        c1 = self.coords.max(axis=0) - ctr
        corners = np.array([
            [c0[0], c0[1], c0[2]], [c1[0], c0[1], c0[2]],
            [c1[0], c1[1], c0[2]], [c0[0], c1[1], c0[2]],
            [c0[0], c0[1], c1[2]], [c1[0], c0[1], c1[2]],
            [c1[0], c1[1], c1[2]], [c0[0], c1[1], c1[2]]])
        gc = np.stack([corners @ r, corners @ u], axis=-1)
        hull = beamviz.hull2d(gc)
        ring = np.r_[hull, hull[:1]]
        self.ghost.set_segments([ring])

        # frame the beam: half-height = fit(projected extent) * pad / zoom,
        # centred on the projected ctr (ctr = beam centre, or the dive
        # target for close-ups).  pad_frac is a real margin (~1.1).
        apx, apy = verts[..., 0], verts[..., 1]
        fit = max(0.5 * (apy.max() - apy.min()),
                  0.5 * (apx.max() - apx.min()) * H / W)
        half = fit * self.pad_frac / zoom
        cx, cy = float(ctr @ r), float(ctr @ u)
        self.ax.set_xlim(cx - W / H * half, cx + W / H * half)
        self.ax.set_ylim(cy - half, cy + half)
        self.ax.set_aspect("equal")
        self.fig.savefig(path, facecolor=BG)
        return path

    def close(self):
        plt.close(self.fig)


def clip(name, frames_fn, n):
    """Render n frames into work/clip_frames/<name>/ then encode."""
    d = os.path.join(TMP, name)
    os.makedirs(d, exist_ok=True)
    for i in range(n):
        frames_fn(i, n, os.path.join(d, f"f{i:04d}.png"))
    out = os.path.join(CLIPS, name + ".mp4")
    encode(os.path.join(d, "f%04d.png"), out)
    print(f"clip {name}: {n} frames -> {out} "
          f"({os.path.getsize(out) / 1e6:.1f} MB)")
    return out


def lerp(a, b, t):
    return a + (b - a) * t


def ease(t):                       # smoothstep: gentle at both ends
    return t * t * (3 - 2 * t)


def main():
    os.makedirs(CLIPS, exist_ok=True)
    good = beamviz.load_fields("good-fine")
    ov = beamviz.load_fields("overload-10x")
    m = json.load(open(os.path.join(MEDIA, "data", "verdicts",
                                    "good.json")))["metrics"]
    L = m["L_mm"]

    # --- hero: full load, low fast orbit, fills the frame ------------------
    cam = BeamCam(good, vmax=1.15 * ALLOW, pad_frac=1.03)
    n = int(4.5 * FPS)

    def hero(i, n, p):
        t = i / (n - 1)
        cam.frame(1.0, 20.0,
                  elev=lerp(10, 24, ease(t)), azim=lerp(-85, 75, ease(t)),
                  zoom=lerp(2.2, 3.0, ease(t)), path=p)
    clip("hero", hero, n)
    cam.close()

    # --- ramp: load 0 -> 1000 N, orbiting; mid-clip jump cut to the
    #     other side (a real cut inside the clip, not a slide) -------------
    cam = BeamCam(good, vmax=1.15 * ALLOW, pad_frac=1.05)
    n = int(11.0 * FPS)
    cut = int(0.5 * n)

    def ramp(i, n, p):
        if i < cut:
            t = i / (cut - 1)
            cam.frame(ease(0.5 * t), 20.0, elev=lerp(22, 12, ease(t)),
                      azim=lerp(-95, -25, ease(t)),
                      zoom=lerp(1.6, 2.0, ease(t)), path=p)
        else:
            t = (i - cut) / (n - 1 - cut)
            cam.frame(ease(0.5 + 0.5 * t), 20.0,
                      elev=lerp(16, 8, ease(t)),
                      azim=lerp(20, 90, ease(t)),
                      zoom=lerp(2.0, 2.4, ease(t)), path=p)
    clip("ramp", ramp, n)
    cam.close()

    # --- closeup: dive onto the clamped wall at full load ------------------
    wall = np.array([0.06 * L, good["coords"][:, 1].mean(),
                     good["coords"][:, 2].mean()])
    cam = BeamCam(good, vmax=1.15 * ALLOW, pad_frac=1.03)
    n = int(7.0 * FPS)

    def closeup(i, n, p):
        t = i / (n - 1)
        cam.frame(1.0, 20.0,
                  elev=lerp(18, 5, ease(t)), azim=lerp(-10, 50, ease(t)),
                  zoom=lerp(1.8, 4.5, ease(t)),
                  center_on=lerp(0.35, 1.0, ease(t)) * wall, path=p)
    clip("closeup", closeup, n)
    cam.close()

    # --- overload: the overload-10x mutant's own field ----------------------
    ov_m = json.load(open(os.path.join(MEDIA, "data", "verdicts",
                                       "overload-10x.json")))["metrics"]
    maxu = float(np.abs(ov["disp"]).max())
    ov_scale = 0.18 * L / maxu        # tip swings ~18% of span: visibly huge
    cam = BeamCam(ov, vmax=10 * ALLOW, pad_frac=1.08)
    n = int(6.0 * FPS)
    cut = int(0.5 * n)

    def overload(i, n, p):
        if i < cut:
            t = i / (cut - 1)
            cam.frame(ease(0.5 * t), ov_scale,
                      elev=lerp(14, 20, ease(t)),
                      azim=lerp(-90, -30, ease(t)),
                      zoom=lerp(1.6, 2.0, ease(t)), path=p)
        else:
            t = (i - cut) / (n - 1 - cut)
            cam.frame(ease(0.5 + 0.5 * t), ov_scale,
                      elev=lerp(22, 28, ease(t)),
                      azim=lerp(35, 95, ease(t)),
                      zoom=lerp(2.0, 2.3, ease(t)), path=p)
    clip("overload", overload, n)
    cam.close()

    # --- proof: high, majestic orbit at full load ---------------------------
    cam = BeamCam(good, vmax=1.15 * ALLOW, pad_frac=1.05)
    n = int(5.5 * FPS)

    def proof(i, n, p):
        t = i / (n - 1)
        cam.frame(1.0, 20.0, elev=lerp(30, 10, ease(t)),
                  azim=lerp(-60, -200, ease(t)),
                  zoom=lerp(1.8, 2.4, ease(t)), path=p)
    clip("proof", proof, n)
    cam.close()

    import terminal_clip
    terminal_clip.main(FPS, W, H, CLIPS, encode)


if __name__ == "__main__":
    main()
