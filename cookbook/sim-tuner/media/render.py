"""Real MuJoCo 3D replay, lossless clips, and Pillow-only figures."""

import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "judge"))
import engine

INK = "#102c3b"
PAPER = "#edf2ef"
MUTED = "#547078"
GREEN = "#087b64"
COLORS = {"default": "#d97936", "tuned": "#138a80", "truth": "#586cb6"}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
ROLES = ("default", "tuned", "truth")
TITLES = ("DEFAULT", "TUNED", "HIDDEN TRUTH")


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
    rgb = (".25 .30 .29", ".45 .50 .46") if light else (".04 .08 .11", ".13 .19 .25")
    ET.SubElement(asset, "texture", name="tiles", type="2d", builtin="checker",
                  rgb1=rgb[0], rgb2=rgb[1], width="256", height="256")
    ET.SubElement(asset, "material", name="floor", texture="tiles", texrepeat="6 6",
                  texuniform="true", reflectance=".04")
    world = root.find("worldbody")
    ET.SubElement(world, "light", pos="-1 -2 4", dir=".2 .4 -1",
                  diffuse=".65 .60 .55", castshadow="true", directional="true")
    ET.SubElement(world, "light", pos="2 2 3", dir="-.5 -.5 -1",
                  diffuse=".2 .3 .4", castshadow="false")
    color = COLORS[role]
    from PIL import ImageColor
    rgba = " ".join(str(v / 255) for v in ImageColor.getrgb(color)) + " 1"
    for geom in root.findall(".//geom"):
        geom.set("material", "floor") if geom.get("type") == "plane" else geom.set("rgba", rgba)
    # A non-colliding mount locates the arm pivot without changing its inertia.
    ET.SubElement(world, "geom", name="mount", type="cylinder", pos=".7 0 .17",
                  size=".065 .17", mass="0", contype="0", conaffinity="0", rgba=".35 .42 .46 1")
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


class Replay:
    def __init__(self, role, meta, traces, light=False):
        self.role, self.meta, self.traces = role, meta, traces
        self.model = visual_model(meta["roles"][role], role, light)
        self.data = mujoco.MjData(self.model)
        self.reference_model = engine.make_model(meta["roles"]["truth"])
        self.reference_data = mujoco.MjData(self.reference_model)
        self.renderer = mujoco.Renderer(self.model, height=850, width=640)
        self.checked = 0

    def frame(self, recording, index, shot, phase):
        qp = self.traces[f"{self.role}_{recording}_qpos"][index]
        qv = self.traces[f"{self.role}_{recording}_qvel"][index]
        self.data.qpos[:] = qp
        self.data.qvel[:] = qv
        self.data.time = index * self.meta["timestep_s"]
        ic = self.meta["initial_conditions"][recording]
        self.data.ctrl[:] = [ic["c1a"], ic["c2a"]] if index <= engine.HALF else \
            [ic["c1b"], ic["c2b"]]
        mujoco.mj_forward(self.model, self.data)
        assert_state(self.data.qpos, qp, "qpos")
        assert_state(self.data.qvel, qv, "qvel")
        cam = mujoco.MjvCamera()
        cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        if shot == "box":
            cam.lookat[:] = [-.31, .2, .04]
            cam.distance, cam.azimuth, cam.elevation = .68, 85 + phase * 20, -25
        elif shot == "arm":
            cam.lookat[:] = [1.04, 0, .29]
            cam.distance, cam.azimuth, cam.elevation = 1.8, 65 + phase * 50, -35
        elif shot == "overhead":
            cam.lookat[:] = [.45, .1, .18]
            cam.distance, cam.azimuth, cam.elevation = 2.25, 90 + phase * 60, -65
        else:
            cam.lookat[:] = [.48, .08, .22]
            cam.distance, cam.azimuth, cam.elevation = 3.1, 65 + phase * 60, -35
        self.renderer.update_scene(self.data, camera=cam)
        if self.role != "truth":
            # Render-only target ghosts, from the very same graded timestep.
            ref = self.reference_data
            ref.qpos[:] = self.traces[f"truth_{recording}_qpos"][index]
            ref.qvel[:] = self.traces[f"truth_{recording}_qvel"][index]
            mujoco.mj_forward(self.reference_model, ref)
            assert_state(ref.qpos, self.traces[f"truth_{recording}_qpos"][index], "ghost qpos")
            assert_state(ref.qvel, self.traces[f"truth_{recording}_qvel"][index], "ghost qvel")
            scene = self.renderer.scene
            for name in ("boxgeom", "l1", "l2"):
                gid = mujoco.mj_name2id(self.reference_model, mujoco.mjtObj.mjOBJ_GEOM, name)
                mujoco.mjv_initGeom(
                    scene.geoms[scene.ngeom], self.reference_model.geom_type[gid],
                    self.reference_model.geom_size[gid], ref.geom_xpos[gid],
                    ref.geom_xmat[gid], np.array([.58, .55, 1., .42], dtype=np.float32))
                scene.ngeom += 1
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = True
        self.checked += 1
        return Image.fromarray(self.renderer.render())

    def close(self):
        self.renderer.close()


def read_inputs():
    meta = json.loads((HERE / "data/replay.json").read_text())
    report = json.loads((HERE / "data/run-1.json").read_text())
    assert report["verdict"]["pass"] and all(g["pass"] for g in meta["gates"].values())
    return meta, report, np.load(HERE / "data/trajectories.npz", allow_pickle=False)


def composition(replays, meta, index, shot, phase, recording=0, proof=False):
    image = Image.new("RGB", (1920, 1080), PAPER)
    titles = {"rig": "Fit five numbers. Match unseen motion.",
              "box": "Fit 5 physics values. Match unseen motion.",
              "arm": "Actuation: watch the arm settle.",
              "overhead": "An unseen command. The same tuned rig."}
    label(image, (40, 18), titles[shot], 61, bold=True)
    for col, (role, title) in enumerate(zip(ROLES, TITLES)):
        tile = replays[role].frame(recording, index, shot, phase)
        image.paste(tile, (col * 640, 180))
        label(image, (col * 640 + 28, 116), title, 50, COLORS[role], True)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 900, 1920, 1080), fill=PAPER)
    g3 = meta["gates"]["G3_heldout"]
    if shot == "box":
        for col, role in enumerate(ROLES):
            x = col * 640
            draw.rectangle((x, 805, x + 640, 900), fill=PAPER)
            gap = abs(replays[role].data.qpos[0] - replays["truth"].data.qpos[0]) * 100
            text = f"Target gap: {gap:.3f} cm" if role != "truth" else "Purple ghost = target"
            label(image, (x + 22, 820), text, 43, COLORS[role], True)
    if proof:
        label(image, (32, 908), f"PASS  {g3['heldout_err']:.5f} < {g3['abs_threshold']} held-out error", 56, GREEN, True)
        label(image, (32, 984), "Judge rejected all 18 broken fits. CPU / GPU agree.", 49)
    else:
        label(image, (32, 908), f"PASS: tuned error {g3['heldout_err']:.5f} < {g3['abs_threshold']} limit", 56, GREEN, True)
        label(image, (32, 990), f"Unseen test {recording + 1}/4  |  t = {index * .002:.3f} s  |  1x replay loop  |  purple = target", 40, MUTED)
    return image


def hero(meta, traces):
    replays = {r: Replay(r, meta, traces, light=True) for r in ROLES}
    image = Image.new("RGB", (2400, 1750), PAPER)
    label(image, (45, 25), "Why tune a simulator? Match the hidden rig.", 59, bold=True)
    g3 = meta["gates"]["G3_heldout"]
    label(image, (45, 110), f"Judge: default {g3['default_err']:.5f}  →  tuned {g3['heldout_err']:.5f}  |  PASS < {g3['abs_threshold']}", 44, GREEN, True)
    for row, (index, shot, recording) in enumerate(((320, "box", 2), (261, "arm", 0))):
        for col, role in enumerate(ROLES):
            tile = replays[role].frame(recording, index, shot, .3).resize((800, 590), Image.Resampling.LANCZOS)
            image.paste(tile, (col * 800, 270 + row * 720))
            label(image, (col * 800 + 25, 210 + row * 720), TITLES[col], 46, COLORS[role], True)
            value = g3["default_err"] if role == "default" else g3["heldout_err"] if role == "tuned" else None
            text = f"Held-out error {value:.5f}" if value is not None else "Oracle: noiseless hidden truth"
            label(image, (col * 800 + 25, 865 + row * 720), text, 31)
            line = "PASS < 0.025 and < 30% of default" if role == "tuned" else \
                "FAIL: above 0.025" if role == "default" else "Identical command / timestep / state source"
            label(image, (col * 800 + 25, 910 + row * 720), line, 28, GREEN if role == "tuned" else MUTED)
    label(image, (45, 1680), "Box: held-out 3, t = 0.640 s • arm: held-out 1, t = 0.522 s • seed 7 • 2 ms steps", 33, MUTED)
    image.save(HERE / "result.png", dpi=(200, 200))
    for replay in replays.values():
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
    shots = [("box", 4, False, 2), ("box", 5, True, 2), ("arm", 5, False, 0),
             ("overhead", 4, True, 1), ("rig", 4, False, 2)]
    paths, checked = [], 0
    last = None
    for n, (shot, seconds, light, recording) in enumerate(shots):
        replays = {r: Replay(r, meta, traces, light) for r in ROLES}

        def frames():
            nonlocal last
            for i in range(seconds * 30):
                phase = i / (seconds * 30 - 1)
                # Real-time repeated replay, each reset is explicitly labelled.
                index = round(((i + 25) % 30) / 30 * engine.NSTEP)
                last = composition(replays, meta, index, shot, phase, recording, n == 4)
                yield last

        path = HERE / "master" / f"clip-{n}.mp4"
        encode_clip(path, frames())
        paths.append(path)
        for replay in replays.values():
            checked += replay.checked
            replay.close()
        print(f"Shot {n}: {shot}, every displayed qpos and qvel checked", flush=True)
    draw = ImageDraw.Draw(last)
    draw.rectangle((0, 900, 1920, 1080), fill=PAPER)
    label(last, (32, 913), "Run the real judge. Keep the result.", 56, GREEN, True)
    label(last, (32, 995), "python3 cookbook/sim-tuner/run.py", 49, bold=True)
    path = HERE / "master" / "end.mp4"
    encode_clip(path, (last for _ in range(90)))
    paths.append(path)
    listing = HERE / "master" / "concat.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in paths))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c", "copy", str(HERE / "master/demo.mp4")], check=True)
    (HERE / "data/render-checks.json").write_text(json.dumps({
        "rendered_frames_checked": checked, "qpos_tolerance": 1e-9,
        "qvel_tolerance": 1e-9, "interpolation": False,
        "source": "trajectories.npz captured during CPU grading",
        "timestep_s": .002, "duration_s": sum(s[1] for s in shots) + 3}, indent=2) + "\n")


def main():
    meta, report, traces = read_inputs()
    hero(meta, traces)
    loop(report)
    video(meta, report, traces)


if __name__ == "__main__":
    main()
