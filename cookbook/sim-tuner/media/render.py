"""Real MuJoCo 3D replay, lossless clips, and Pillow-only figures."""

import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "judge"))
import engine

INK = "#102c3b"
PAPER = "#edf2ef"
MUTED = "#547078"
GREEN = "#087b64"
COLORS = {"default": "#ff994c", "tuned": "#17c8b5", "truth": "#f0f2f0"}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
ROLES = ("default", "tuned", "truth")
TITLES = ("DEFAULT", "TUNED", "HIDDEN TRUTH")
PARAM_LABELS = (
    ("mu", "Sliding friction", "coefficient"),
    ("solref_tc", "Contact response time", "s"),
    ("solref_dr", "Contact damping ratio", "ratio"),
    ("damping", "Joint damping", "N·m·s/rad"),
    ("armature", "Joint armature", "kg·m²"),
)
PARAM_BOUNDARIES = (0, 5, 10, 16, 18.5, 21)
# Integer state strides, never interpolated. Four slow-motion box cases,
# then an arm response and a final box proof. Only the end card is frozen.
SHOTS = (
    ("box", 4, False, 0, 75, 1),
    ("box", 4, True, 1, 60, 1),
    ("box", 4, False, 2, 30, 1),
    ("box", 4, True, 3, 0, 1),
    ("arm", 5, False, 0, 251, 1),
    ("box", 3, True, 0, 110, 1),
)
END_FRAMES = 66


def label(image, xy, text, size=40, fill=INK, bold=False):
    font = ImageFont.truetype(BOLD if bold else FONT, size)
    draw = ImageDraw.Draw(image)
    box = draw.textbbox(xy, text, font=font)
    assert min(box[:2]) >= 0 and box[2] <= image.width and box[3] <= image.height, \
        f"Clipped caption: {text}"
    draw.text(xy, text, font=font, fill=fill)


def assert_state(actual, expected, context):
    a, b = np.asarray(actual), np.asarray(expected)
    assert a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all() \
        and np.max(np.abs(a - b), initial=0) <= 1e-9, \
        f"{context}: rendered state differs from graded state"


def visual_model(params, role, light):
    root = ET.fromstring(engine.SCENE_XML)
    visual = ET.SubElement(root, "visual")
    ET.SubElement(visual, "global", offwidth="1920", offheight="1080")
    ET.SubElement(visual, "quality", shadowsize="2048", offsamples="4")
    ET.SubElement(visual, "headlight", ambient=".15 .15 .15", diffuse=".35 .35 .35")
    asset = ET.SubElement(root, "asset")
    ET.SubElement(asset, "texture", name="sky", type="skybox", builtin="gradient",
                  rgb1=".11 .19 .28", rgb2=".58 .69 .75", width="256", height="1536")
    rgb = (".65 .78 .72", ".95 .99 .95") if light else (".025 .05 .075", ".22 .30 .38")
    ET.SubElement(asset, "texture", name="tiles", type="2d", builtin="checker",
                  rgb1=rgb[0], rgb2=rgb[1], width="256", height="256")
    ET.SubElement(asset, "material", name="floor", texture="tiles", texrepeat="3 3",
                  texuniform="true", reflectance="0")
    world = root.find("worldbody")
    ET.SubElement(world, "light", pos="-1 -2 4", dir=".2 .4 -1",
                  diffuse=".65 .60 .55", castshadow="true", directional="true")
    ET.SubElement(world, "light", pos="2 2 3", dir="-.5 -.5 -1",
                  diffuse=".2 .3 .4", castshadow="false")
    color = COLORS[role]
    rgba = " ".join(str(v / 255) for v in ImageColor.getrgb(color)) + " 1"
    for geom in root.findall(".//geom"):
        geom.set("material", "floor") if geom.get("type") == "plane" else geom.set("rgba", rgba)
    # A non-colliding mount locates the arm pivot without changing its inertia.
    ET.SubElement(world, "geom", name="mount", type="cylinder", pos=".7 0 .17",
                  size=".065 .17", mass="0", contype="0", conaffinity="0", rgba=".35 .42 .46 1")
    for name in ("l1", "l2", "mount"):
        root.find(f".//geom[@name='{name}']").set("group", "1")
    root.find(".//geom[@name='boxgeom']").set("group", "2")
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
    original = engine.make_model(params)
    indices = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM,
                               mujoco.mj_id2name(original, mujoco.mjtObj.mjOBJ_GEOM, i))
               for i in range(original.ngeom)]
    assert all(i >= 0 for i in indices), "Missing original geometry"
    for field in ("geom_friction", "geom_solref"):
        getattr(model, field)[indices] = getattr(original, field)
    model.dof_damping[:] = original.dof_damping
    model.dof_armature[:] = original.dof_armature
    # No dynamical property may be changed by render-only scene dressing.
    for field in ("body_mass", "body_inertia", "body_pos", "body_quat", "qpos0",
                  "dof_damping", "dof_armature", "actuator_gainprm", "actuator_biasprm"):
        assert_state(getattr(model, field), getattr(original, field), field)
    for field in ("geom_friction", "geom_solref", "geom_solimp", "geom_size", "geom_pos",
                  "geom_quat", "geom_contype", "geom_conaffinity"):
        assert_state(getattr(model, field)[indices], getattr(original, field), field)
    assert model.opt.timestep == original.opt.timestep == .002
    assert_state(model.opt.gravity, original.opt.gravity, "gravity")
    return model


def rgba(role, alpha=1.):
    return np.array([v / 255 for v in ImageColor.getrgb(COLORS[role])] + [alpha],
                    dtype=np.float32)


class Replay:
    """One shared camera and coordinate system; no offsets or enlarged motion."""

    def __init__(self, meta, traces, light=False):
        self.meta, self.traces = meta, traces
        self.models = {r: visual_model(meta["roles"][r], r, light) for r in ROLES}
        self.states = {r: mujoco.MjData(m) for r, m in self.models.items()}
        self.renderer = mujoco.Renderer(self.models["tuned"], height=1080, width=1920)
        self.checked = 0
        self.paths = {}

    def load_state(self, role, recording, index):
        data, model = self.states[role], self.models[role]
        qp = self.traces[f"{role}_{recording}_qpos"][index]
        qv = self.traces[f"{role}_{recording}_qvel"][index]
        data.qpos[:], data.qvel[:] = qp, qv
        data.time = index * self.meta["timestep_s"]
        ic = self.meta["initial_conditions"][recording]
        data.ctrl[:] = [ic["c1a"], ic["c2a"]] if index <= engine.HALF else \
            [ic["c1b"], ic["c2b"]]
        mujoco.mj_forward(model, data)
        assert_state(data.qpos, qp, f"{role} qpos")
        assert_state(data.qvel, qv, f"{role} qvel")
        self.checked += 1
        return data

    def path(self, role, recording, shot):
        key = role, recording, shot
        if key not in self.paths:
            if shot == "box":
                points = self.traces[f"{role}_{recording}_qpos"][:, :3].copy()
            else:
                points = []
                model = self.models[role]
                gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "l2")
                for index in range(engine.NSTEP + 1):
                    data = self.load_state(role, recording, index)
                    # Exact distal endpoint of the capsule, in world coordinates.
                    points.append(data.geom_xpos[gid] + data.geom_xmat[gid].reshape(3, 3) @
                                  np.array([0., 0., model.geom_size[gid, 1]]))
                points = np.asarray(points)
            self.paths[key] = points
        return self.paths[key]

    def connector(self, start, end, color, radius):
        if np.linalg.norm(end - start) < 1e-8:
            return
        scene = self.renderer.scene
        assert scene.ngeom < scene.maxgeom
        geom = scene.geoms[scene.ngeom]
        mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_CAPSULE, np.zeros(3),
                           np.zeros(3), np.eye(3).ravel(), color)
        mujoco.mjv_connector(geom, mujoco.mjtGeom.mjGEOM_CAPSULE, radius, start, end)
        scene.ngeom += 1

    def frame(self, recording, index, shot, phase):
        paths = {r: self.path(r, recording, shot) for r in ROLES}
        for role in ROLES:
            self.load_state(role, recording, index)
        cam = mujoco.MjvCamera()
        cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        if shot == "box":
            center = (self.states["default"].qpos[:3] + self.states["truth"].qpos[:3]) / 2
            cam.lookat[:] = center + np.array([-.035, 0., -.045])
            cam.distance, cam.azimuth, cam.elevation = .51, 30 + phase * 120, -28
        else:
            cam.lookat[:] = [1.07, 0., .35]
            cam.distance, cam.azimuth, cam.elevation = 1.27, 85 + phase * 40, -22
        option = mujoco.MjvOption()
        option.geomgroup[1 if shot == "box" else 2] = 0
        self.renderer.update_scene(self.states["tuned"], camera=cam, scene_option=option)
        scene = self.renderer.scene
        names = ("boxgeom",) if shot == "box" else ("l1", "l2")
        for role in ("default", "truth"):
            model, data = self.models[role], self.states[role]
            for name in names:
                gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
                color = rgba(role, .95 if role == "default" else .75)
                radius = .0017 if role == "default" else .0007
                if name == "boxgeom":
                    # Exact surface outlines avoid z-fighting between coplanar
                    # boxes. Do not offset or expand either comparison object.
                    corners = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1)
                                        for z in (-1, 1)])
                    xyz = (corners * model.geom_size[gid]) @ data.geom_xmat[gid].reshape(3, 3).T + data.geom_xpos[gid]
                    for a in range(8):
                        for b in range(a + 1, 8):
                            if np.count_nonzero(corners[a] != corners[b]) == 1:
                                self.connector(xyz[a], xyz[b], color, radius)
                else:
                    rotation = data.geom_xmat[gid].reshape(3, 3)
                    half = rotation[:, 2] * model.geom_size[gid, 1]
                    for theta in np.linspace(0, 2 * np.pi, 5)[:-1]:
                        radial = model.geom_size[gid, 0] * (
                            rotation[:, 0] * np.cos(theta) + rotation[:, 1] * np.sin(theta))
                        self.connector(data.geom_xpos[gid] - half + radial,
                                       data.geom_xpos[gid] + half + radial, color, radius)
        for role in ROLES:
            points = paths[role]
            for a in range(0, index, 3):
                if role == "truth" and a % 12 >= 6:
                    continue  # White dashed trace, teal solid trace at the same true coordinates.
                self.connector(points[a], points[min(a + 3, index)], rgba(role, .85),
                               .0023 if role == "tuned" else .0011)
        scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = True
        return Image.fromarray(self.renderer.render())

    def close(self):
        self.renderer.close()


def read_inputs():
    meta = json.loads((HERE / "data/replay.json").read_text())
    report = json.loads((HERE / "data/run-1.json").read_text())
    assert report["verdict"]["pass"] and all(g["pass"] for g in meta["gates"].values())
    return meta, report, np.load(HERE / "data/trajectories.npz", allow_pickle=False)


def shade(image, box, alpha=215):
    layer = Image.new("RGBA", image.size)
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=18, fill=(9, 23, 32, alpha))
    image.paste(Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB"))


def composition(replay, meta, index, shot, phase, rank, elapsed, proof=False):
    recording = meta["presentation_order"][rank]["source_recording"]
    image = replay.frame(recording, index, shot, phase)
    shade(image, (24, 18, 1896, 200), 220)
    title = "Default drifts. Tuned matches." if shot == "box" else "Same fit. A new servo command."
    label(image, (55, 28), title, 66, PAPER, True)
    label(image, (1500, 42), f"TEST {rank + 1}/4", 60, PAPER, True)
    for x, role, title in zip((55, 490, 900), ROLES, TITLES):
        label(image, (x, 126), title, 60, COLORS[role], True)
    label(image, (1480, 126), "0.06x speed", 60, PAPER)
    if shot == "box":
        shade(image, (24, 236, 500, 535), 190)
        for y, role, title in ((248, "default", "Default miss"), (385, "tuned", "Tuned miss")):
            gap = abs(replay.states[role].qpos[0] - replay.states["truth"].qpos[0]) * 100
            label(image, (50, y), title, 60, COLORS[role], True)
            label(image, (50, y + 56), f"{gap:.3f} cm", 64, PAPER, True)
    shade(image, (24, 702, 1896, 795), 220)
    g3 = meta["gates"]["G3_heldout"]
    if proof:
        text = "G1–G4 PASS  /  18/18 caught  /  CPU + GPU agree"
        label(image, (55, 714), text, 60, PAPER, True)
    else:
        text = f"4-test RMS: {g3['default_err']:.5f} → {g3['heldout_err']:.5f}  /  PASS < {g3['abs_threshold']}"
        label(image, (55, 714), text, 60, PAPER, True)
    shade(image, (24, 814, 1896, 1060), 220)
    if proof:
        label(image, (55, 829), "Held-out error (normalized RMS, not cm)", 60, PAPER, True)
        label(image, (55, 917), f"{g3['heldout_err']:.5f} < {g3['abs_threshold']} limit", 72, COLORS["tuned"], True)
        label(image, (1150, 940), "All 4 unseen tests", 60, PAPER)
    else:
        param = sum(elapsed >= boundary for boundary in PARAM_BOUNDARIES[1:-1])
        name, title, unit = PARAM_LABELS[param]
        label(image, (55, 830), f"{title}  [{unit}]", 60, PAPER, True)
        for x, role in zip((55, 685, 1315), ROLES):
            label(image, (x, 903), role.upper() if role != "truth" else "TRUTH", 60, COLORS[role], True)
            label(image, (x, 963), f"{meta['roles'][role][name]:.6f}", 61, PAPER, True)
        label(image, (490, 955), "→", 64, PAPER)
        label(image, (1120, 955), "→", 64, PAPER)
        # Progress is time, not invented intermediate fit values.
        boundaries = PARAM_BOUNDARIES
        progress = (elapsed - boundaries[param]) / (boundaries[param + 1] - boundaries[param])
        ImageDraw.Draw(image).rectangle((55, 1051, 55 + int(1790 * progress), 1055), fill=COLORS["tuned"])
    return image


def hero(meta, traces):
    replay = Replay(meta, traces)
    image = composition(replay, meta, 200, "box", .25, 0, 0)
    image.save(HERE / "result.png", dpi=(200, 200))
    replay.close()


def kills_from_report(report):
    text = report["stages"]["selftest"]["stdout_tail"]
    lines = [line for line in text.splitlines() if ": killed (gate:" in line]
    assert len(lines) == 18 and "kill rate: 18/18 = 100%" in text
    return [line.split("mutant ", 1)[1].split(": killed", 1)[0] for line in lines]


def loop(report):
    history = json.loads((HERE.parent / "examples/good/loop.json").read_text())
    image = Image.new("RGB", (2400, 1580), PAPER)
    draw = ImageDraw.Draw(image)
    label(image, (55, 30), "A measured search, and a judge that rejects bad fits", 51, bold=True)
    label(image, (55, 112), "Recorded CPU search on six training recordings; GPU provides a numerical cross-check.", 33, MUTED)
    label(image, (55, 225), "Best train error per search iteration", 41, bold=True)
    running = 1.
    for i, row in enumerate(history["iterations"]):
        values = row.get("errors", [])
        current = row.get("best_err", min([x for x in values if x is not None], default=running))
        running = min(running, current)
        height = min(600, running / .3 * 600)
        x = 60 + i * 15
        draw.rectangle((x, 1030 - height, x + 10, 1030), fill=GREEN)
    label(image, (55, 1090), f"Final rounded artifact: train error {history['final_cpu_train_err']:.6f}", 36, GREEN, True)
    label(image, (55, 1160), f"Recorded search wall time: {history['wall_s']} s (not run.py time)", 31)
    label(image, (55, 1230), "Train and held-out errors are different metrics.", 31, MUTED)
    label(image, (55, 1300), "G3 pass line: held-out < 0.025 AND < 30% of default.", 30)
    names = kills_from_report(report)
    label(image, (1250, 225), "SELFTEST  18/18 = 100%", 41, GREEN, True)
    for i, name in enumerate(names):
        y = 310 + i * 60
        draw.rectangle((1250, y + 8, 1300, y + 36), fill=GREEN)
        label(image, (1320, y), name.removeprefix("mut_"), 29)
        label(image, (2170, y), "KILLED", 27, GREEN, True)
    label(image, (55, 1490), "Source: examples/good/loop.json + data/run-1.json. No fabricated iterations or speedup claims.", 32, MUTED)
    image.save(HERE / "loop.png", dpi=(200, 200))


def encode_clip(path, frames):
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", "1920x1080", "-r", "30", "-i", "-", "-an", "-c:v", "libx264",
           "-threads", "2", "-crf", "0", "-preset", "ultrafast", str(path)]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as proc:
        try:
            for image in frames:
                proc.stdin.write(image.tobytes())
        finally:
            proc.stdin.close()
        assert proc.wait() == 0, "Lossless clip encoding failed"


def video(meta, report, traces):
    kills_from_report(report)
    paths, checked, elapsed = [], 0, 0
    last = None
    shot_receipts = []
    for n, (shot, seconds, light, rank, start, stride) in enumerate(SHOTS):
        replay = Replay(meta, traces, light)

        def frames():
            nonlocal last
            for i in range(seconds * 30):
                index = start + i * stride
                assert index <= engine.NSTEP
                last = composition(replay, meta, index, shot, i / (seconds * 30 - 1),
                                   rank, elapsed + i / 30, n == 5)
                yield last

        path = HERE / "master" / f"clip-{n}.mp4"
        encode_clip(path, frames())
        paths.append(path)
        checked += replay.checked
        replay.close()
        shot_receipts.append({"start_s": elapsed, "duration_s": seconds, "view": shot,
                              "presentation_rank": rank + 1,
                              "source_recording": meta["presentation_order"][rank]["source_recording"],
                              "first_state": start, "last_state": start + (seconds * 30 - 1) * stride,
                              "state_stride": stride, "playback_speed": 30 * stride * meta["timestep_s"]})
        elapsed += seconds
        print(f"Shot {n}: {shot}, overlaid exact states and trails", flush=True)
    shade(last, (24, 702, 1896, 1060), 250)
    g3 = meta["gates"]["G3_heldout"]
    label(last, (55, 720), f"PASS  /  {g3['heldout_err']:.5f} < {g3['abs_threshold']}  /  {len(kills_from_report(report))}/18 caught",
          62, COLORS["tuned"], True)
    label(last, (55, 834), "Make your simulator match.", 62, PAPER, True)
    label(last, (55, 948), "python3 cookbook/sim-tuner/run.py", 64, PAPER, True)
    path = HERE / "master" / "end.mp4"
    encode_clip(path, (last for _ in range(END_FRAMES)))
    paths.append(path)
    listing = HERE / "master" / "concat.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in paths))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c", "copy", str(HERE / "master/demo.mp4")], check=True)
    (HERE / "data/render-checks.json").write_text(json.dumps({
        "rendered_states_checked": checked, "qpos_tolerance": 1e-9,
        "qvel_tolerance": 1e-9, "interpolation": False,
        "source": "trajectories.npz captured during CPU grading",
        "trajectory_sha256": __import__("hashlib").sha256((HERE / "data/trajectories.npz").read_bytes()).hexdigest(),
        "timestep_s": .002, "duration_s": elapsed + END_FRAMES / 30,
        "end_card_s": END_FRAMES / 30, "shots": shot_receipts}, indent=2) + "\n")


def main():
    meta, report, traces = read_inputs()
    hero(meta, traces)
    loop(report)
    video(meta, report, traces)


if __name__ == "__main__":
    main()
