#!/usr/bin/env python3
"""demo.mp4: the cnc-gcode demo in 31 s of real renders.

Frames are renders of the judge's own outputs, never matplotlib animation
(owner rule for this video):

  0-10 s  a pyrender turntable of the solid the judge's heightmap describes
          (partmesh.block_solid): the graded part.nc cut into the block, then
          the same part close up with the measured gate numbers burned in;
  10-16 s three mutants side by side, each the solid of its own trace
          (media/data/trace_mut/*/final.npz) with the gate that killed it;
  16-28 s full-frame cards of media/result.png and media/loop.png;
  28-31 s a static end card with the one-command run.

Every number burned into a caption is read from the verdict JSONs in
media/data/replay/ at render time -- nothing is hand-typed.

Output: media/demo.mp4 (1920x1080, 30 fps, H.264 crf 18 / preset slow /
yuv420p / +faststart, under 8 MB) plus a lossless master under
media/master/ (git-ignored).  Regenerate with bash media/make_demo.sh.
"""
import json
import os
import subprocess
import sys

os.environ.setdefault("PYOPENGL_PLATFORM", "egl")   # headless GL (must be
# set before pyrender imports OpenGL)

import numpy as np
import pyrender
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import partmesh

DEMO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(DEMO, "media")
DATA = os.path.join(MEDIA, "data")
MASTER = os.path.join(MEDIA, "master")
FRAMES = os.path.join(MASTER, "frames")

W, H, FPS = 1920, 1080, 30

# palette (dataviz reference instance, light mode) -- same as the figures
SURFACE = (247, 247, 246)
INK = (11, 11, 11)
INK2 = (82, 81, 78)
CRIT = (208, 59, 59)
GOOD_C = (12, 163, 12)

BG_RGB = (0.969, 0.965, 0.962)

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
T_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
T_TEXT = os.path.join(FONT_DIR, "DejaVuSans.ttf")
T_MONO = os.path.join(FONT_DIR, "DejaVuSansMono-Bold.ttf")

# mutants with a visible geometric defect (their heightmap differs from the
# good run's); the other four fail process gates and never reach a different
# shape, so they are shown by loop.png's matrix instead
DEFECT_MUTANTS = ["no_tool_offset", "swapped_arcs", "wide_stepover"]

SHOTS = [          # (name, seconds, kind)
    ("turntable_wide", 5.0, "good"),
    ("turntable_close", 5.0, "good"),
    ("mutants", 6.0, "mutants"),
    ("card_result", 6.0, "card:result.png"),
    ("card_loop", 6.0, "card:loop.png"),
    ("endcard", 3.0, "end"),
]


def verdict(name):
    path = os.path.join(DATA, "replay", name)
    if not os.path.exists(path):
        sys.exit(f"make_demo: missing verdict JSON {path}")
    return json.load(open(path))


def kill_line():
    """The self-test's own kill-rate line (media/data/selftest.log)."""
    for line in open(os.path.join(DATA, "selftest.log")):
        if "kill rate" in line:
            return line.strip().split("selftest: ", 1)[1]
    sys.exit("make_demo: no kill-rate line in media/data/selftest.log")


def gate_label(name):
    """(gate key, 'measured vs limit' text) of the gate that killed `name`."""
    gates = verdict(f"02_{name}.json")["gates"]
    for key, g in gates.items():
        if isinstance(g, dict) and not g.get("pass", True):
            if key == "gouge":
                return key, f"gouge {g['worst_gouge_mm']:g} mm (tol {g['tolerance_mm']:g})"
            if key == "residual":
                return key, (f"residual {g['worst_residual_mm']:g} mm "
                             f"(tol {g['tolerance_mm']:g})")
            if key == "stepover":
                return key, (f"spacing {g['max_spacing_mm']:.4g} mm "
                             f"(limit {g['limit_mm']:g})")
            if key == "stepdown":
                return key, (f"axial {g['max_axial_mm']:g} mm "
                             f"(limit {g['limit_mm']:g})")
            if key == "process":
                lo, hi = g["limits"]
                f0, f1 = g["chip_load_mm_per_tooth"]
                return key, f"chip load {f0:g}–{f1:g} (band {lo:g}–{hi:g})"
            if key == "rapid_safety":
                return key, (f"rapid {g['max_rapid_hit_mm']:g} mm into stock "
                             f"(tol {g['tolerance_mm']:g})")
            return key, f"gate {key} failed"
    sys.exit(f"make_demo: {name} passed every gate?!")


# ---------------------------------------------------------------- captions

def font(path, size):
    return ImageFont.truetype(path, size)


def burn(img, title, sub, labels=None):
    """Burn the shot's captions: title top-left, sub bottom, part labels.

    Captions are wrapped to the frame width first and every drawn box is
    checked against the frame, so nothing is ever clipped at 1080p.
    """
    d = ImageDraw.Draw(img)
    drawn = []

    def put(xy, text, f, fill, anchor=None):
        d.text(xy, text, font=f, fill=fill, anchor=anchor)
        drawn.append((text, d.textbbox(xy, text, font=f, anchor=anchor)))

    if title:
        put((70, 40), title, font(T_BOLD, 54), INK)
    if sub:
        lines = wrap(sub, font(T_TEXT, 42), W - 140)[:2]
        for i, line in enumerate(lines):
            put((70, H - 70 - (len(lines) - 1 - i) * 56), line,
                font(T_TEXT, 42), INK2)
    for cx, text in (labels or []):
        f = font(T_BOLD, 40)
        for i, line in enumerate(text.split("\n")):
            put((cx, H - 206 + i * 50), line, f, CRIT, anchor="ma")

    for text, (x0, y0, x1, y1) in drawn:
        if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
            sys.exit(f"make_demo: caption would leave the frame: {text!r} "
                     f"({x0},{y0})-({x1},{y1})")


def wrap(text, f, max_w):
    """Greedy word wrap at the given font's real advance widths."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if f.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- 3D shots

class Renderer:
    """One EGL offscreen renderer shared by every 3D frame."""

    def __init__(self):
        self.r = pyrender.OffscreenRenderer(W, H)
        self.good_scene = None

    def scene_for(self, meshes):
        """A scene with the fixed three-point lighting, meshes at origin."""
        scene = pyrender.Scene(bg_color=[*BG_RGB, 1.0],
                               ambient_light=[0.30, 0.31, 0.33])
        scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=2.2),
                  pose=partmesh.orbit_pose(150, 55, 300))
        scene.add(pyrender.DirectionalLight(
            color=np.array([0.85, 0.90, 1.0]), intensity=0.85),
            pose=partmesh.orbit_pose(-20, 30, 300))
        for mesh, pose in meshes:
            scene.add(pyrender.Mesh.from_trimesh(mesh, smooth=False),
                      pose=pose)
        return scene

    def shot(self, scene, camera_pose):
        cam = pyrender.PerspectiveCamera(yfov=np.deg2rad(29.0))
        node = scene.add(cam, pose=camera_pose)
        color, _ = self.r.render(scene)
        scene.remove_node(node)
        return color[:, :, ::-1].copy()


def good_mesh():
    mesh, _ = partmesh.block_solid("trace_good")
    return mesh


def rot_z(deg):
    a = np.deg2rad(deg)
    c, s = np.cos(a), np.sin(a)
    out = np.eye(4)
    out[:2, :2] = [[c, -s], [s, c]]
    return out


def translate(x, y, z):
    out = np.eye(4)
    out[:3, 3] = [x, y, z]
    return out


def good_frames(rd, captions):
    """The two good-part turntables: orbit the camera around a fixed part."""
    mesh = good_mesh()
    centre = np.array([40.0, 30.0, -5.0])
    scene = rd.scene_for([(mesh, np.eye(4))])
    return {
        "turntable_wide": (scene,
                           dict(az0=25, az1=95, el=34, dist=205,
                                target=centre),
                           captions["turntable_wide"]),
        "turntable_close": (scene,
                            dict(az0=205, az1=262, el=48, dist=188,
                                 target=np.array([40.0, 30.0, -4.0])),
                            captions["turntable_close"]),
    }


def mutant_scene(rd, centre):
    """Three defective parts side by side, seen from the front.

    The slot spacing is set from the block's own size so the three parts fill
    the frame in a row; the camera looks straight down the row's normal so
    none of them hides behind another.
    """
    block_x = float(meta_block_x())
    gap = block_x * 1.06
    slots = np.array([[-gap, 0.0, 0.0], [0.0, 0.0, 0.0], [gap, 0.0, 0.0]])
    meshes = [partmesh.block_solid(os.path.join("trace_mut", n))[0]
              for n in DEFECT_MUTANTS]
    pose_of = lambda i, spin=0.0: (translate(*slots[i]) @ rot_z(spin)
                                   @ translate(-centre[0], -centre[1], -centre[2]))
    scene = rd.scene_for([(mesh, pose_of(i)) for i, mesh in enumerate(meshes)])
    cam_pose = partmesh.orbit_pose(90.0, 35, 398,
                                   target=np.array([0.0, 0.0, -8.0]))
    return scene, scene.mesh_nodes, pose_of, cam_pose


def meta_block_x():
    meta = json.load(open(os.path.join(DATA, "trace_good", "meta.json")))
    return meta["stock"]["x_mm"]


def main():
    os.makedirs(FRAMES, exist_ok=True)
    good = verdict("01_good.json")
    g = good["gates"]
    meta = json.load(open(os.path.join(DATA, "trace_good", "meta.json")))
    tool = meta["tool"]
    captions = {
        "turntable_wide": (
            "cnc-gcode · judged by material-removal simulation",
            f"stock {meta['stock']['x_mm']:g}×{meta['stock']['y_mm']:g}×"
            f"{meta['stock']['z_mm']:g} mm · Ø{tool['diameter_mm']:g} mm "
            f"{tool['flutes']}-flute end mill · 0.05 mm heightmap grid "
            f"· seed {good['seed']}"),
        "turntable_close": (
            "the graded part.nc · every gate measured",
            f"residual {g['residual']['residual_cells']} cells · "
            f"gouge {g['gouge']['gouge_cells']} cells · "
            f"stepdown {g['stepdown']['max_axial_mm']:g}/"
            f"{g['stepdown']['limit_mm']:g} mm · "
            f"stepover {g['stepover']['max_spacing_mm']:g}/"
            f"{g['stepover']['limit_mm']:g} mm · chip load "
            f"{g['process']['chip_load_mm_per_tooth'][0]:g}–"
            f"{g['process']['chip_load_mm_per_tooth'][1]:g} mm/tooth"),
        "mutants": (
            "one edit each · the judge kills all 7",
            None),
        "card_result.png": ("result.png · the graded run, panel by panel",
                            None),
        "card_loop.png": (f"loop.png · the self-test matrix · "
                         f"known-good passes every gate · {kill_line()}",
                         None),
    }

    rd = Renderer()
    good_scenes = good_frames(rd, captions)
    centre = np.array([40.0, 30.0, -7.0])
    mut_stage = mutant_scene(rd, centre)

    idx = 0
    for name, seconds, kind in SHOTS:
        n = int(round(seconds * FPS))
        if kind == "good":
            scene, view, cap = good_scenes[name]
            title, sub = cap
            for k in range(n):
                frac = k / (n - 1)
                az = view["az0"] + (view["az1"] - view["az0"]) * frac
                frame = rd.shot(scene, partmesh.orbit_pose(
                    az, view["el"], view["dist"], view["target"]))
                img = Image.fromarray(frame)
                burn(img, title, sub)
                img.save(os.path.join(FRAMES, f"f{idx:05d}.png"))
                idx += 1
        elif kind == "mutants":
            stage, nodes, pose_of, cam_pose = mut_stage
            title, _ = captions["mutants"]
            labels = [f"{n}\n{gate_label(n)[1]}" for n in DEFECT_MUTANTS]
            for k in range(n):
                frac = k / (n - 1)
                spin = 12 + 26 * frac
                for i, node in enumerate(nodes):
                    stage.set_pose(node, pose_of(i, spin))
                frame = rd.shot(stage, cam_pose)
                img = Image.fromarray(frame)
                labs = [(int(W * (0.5 + (i - 1) * 0.335)), l)
                        for i, l in enumerate(labels)]
                burn(img, title, None, labs)
                img.save(os.path.join(FRAMES, f"f{idx:05d}.png"))
                idx += 1
        elif kind.startswith("card:"):
            which = kind.split(":", 1)[1]
            title, sub = captions[f"card_{which}"]
            card = card_frame(os.path.join(MEDIA, which), title, sub)
            for k in range(n):
                card.save(os.path.join(FRAMES, f"f{idx:05d}.png"))
                idx += 1
        elif kind == "end":
            card = end_card()
            for k in range(n):
                card.save(os.path.join(FRAMES, f"f{idx:05d}.png"))
                idx += 1
        print(f"make_demo: shot {name}: {n} frames (total {idx})",
              flush=True)

    encode(idx)
    print(f"make_demo: wrote media/demo.mp4 from {idx} frames")


def card_frame(path, title, sub):
    """A full-frame card: the figure scaled to fit, captions burned in."""
    img = Image.open(path).convert("RGB")
    # the figure carries its own titles and source line, so the card adds
    # only a one-line header and gives the rest of the frame to the figure
    box_w, box_h = 1864, 936
    scale = min(box_w / img.width, box_h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)),
                     Image.LANCZOS)
    frame = Image.new("RGB", (W, H), SURFACE)
    frame.paste(img, ((W - img.width) // 2, (H - img.height) // 2))
    burn(frame, title, None)
    return frame


def end_card():
    frame = Image.new("RGB", (W, H), (15, 15, 15))
    d = ImageDraw.Draw(frame)
    d.text((W // 2, 430), "run it yourself", font=font(T_TEXT, 52),
           fill=(160, 160, 158), anchor="mm")
    d.text((W // 2, 540), "python3 cookbook/cnc-gcode/run.py",
           font=font(T_MONO, 64), fill=(245, 245, 244), anchor="mm")
    d.text((W // 2, 660),
           "sandbox → judge/setup.sh → selftest.sh → grade.sh "
           "→ verdict: PASS",
           font=font(T_TEXT, 46), fill=(160, 160, 158), anchor="mm")
    return frame


def encode(n_frames):
    master = os.path.join(MASTER, "master.mp4")
    final = os.path.join(MEDIA, "demo.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS),
         "-start_number", "0", "-i", os.path.join(FRAMES, "f%05d.png"),
         "-frames:v", str(n_frames),
         "-c:v", "libx264", "-preset", "veryslow", "-crf", "0",
         "-pix_fmt", "yuv444p", master])
    run(["ffmpeg", "-y", "-v", "error", "-i", master,
         "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", final])
    size = os.path.getsize(final)
    print(f"make_demo: {final} = {size/1e6:.2f} MB, {n_frames/FPS:.1f} s")


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"make_demo: {' '.join(cmd[:3])} failed:\n{proc.stderr[-2000:]}")


if __name__ == "__main__":
    main()