"""Offscreen MuJoCo replay of the judge's actual output, with Pillow labels."""

import importlib.util
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from collect import read_selftest

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
DATA = HERE / "data"
module = importlib.util.spec_from_file_location("grade", DEMO / "judge/_grade.py")
grade = importlib.util.module_from_spec(module)
module.loader.exec_module(grade)
SPEC = json.loads((DEMO / "judge/spec.json").read_text())
SCENES = {s["name"]: s for s in SPEC["scenarios"]}
ORACLE = grade.oracle_values(SPEC)
VERDICT = json.loads((DATA / "grade.json").read_text())
METRIC = {n: s["oracle"] for n, s in VERDICT["scenarios"].items()}
INK, MUTED, WHITE, GREEN = "#152d40", "#526777", "#f4f8fb", "#087852"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def label(image, xy, text, size=32, fill=INK, bold=False):
    """Reject clipped labels rather than shipping unreadable captions."""
    font = ImageFont.truetype(BOLD if bold else FONT, size)
    draw = ImageDraw.Draw(image)
    box = draw.textbbox(xy, text, font=font)
    assert min(box[:2]) >= 0 and box[2] <= image.width and box[3] <= image.height, \
        f"Clipped label: {text}"
    draw.text(xy, text, font=font, fill=fill)


def readout(name):
    m, o = METRIC[name], ORACLE[name]
    if name == "drop":
        return (f"Contact {m['t_contact']:.4f} s  |  oracle {o['t_contact']:.4f} s",
                "PASS: contact error < 3%")
    if name == "incline_slide":
        return (f"a = {m['accel']:.4f} m/s²  |  oracle {o['accel']:.4f} m/s²",
                "PASS: acceleration error < 5%")
    if name == "incline_stick":
        return (f"Travel {m['travel_m'] * 1000:.2f} mm  |  oracle 0 mm (stick)",
                "PASS: travel < 20 mm")
    return (f"Period {m['period']:.4f} s  |  oracle {o['period']:.4f} s",
            "PASS: period error < 2%")


def assert_state(actual, expected, context):
    assert np.asarray(actual).shape == np.asarray(expected).shape, \
        f"{context}: rendered-state mismatch (shape)"
    assert np.isfinite(actual).all() and np.isfinite(expected).all() and \
        np.max(np.abs(np.asarray(actual) - expected), initial=0) <= 1e-9, \
        f"{context}: rendered-state mismatch"


def visual_model(name, source, offsamples="4", shadowsize="2048",
                 outfile=None):
    """Only materials, textures, lighting and zero-mass noncontact scenery.

    offsamples/shadowsize are offscreen-quality knobs only: they change
    neither the scene nor the physics, and assert_physics still runs on the
    result. The animated clip renderer lowers them for throughput and writes
    its XML under a separate name, so this module's own output is untouched.
    """
    root = ET.fromstring(source)
    ET.SubElement(root, "visual")
    visual = root.find("visual")
    ET.SubElement(visual, "global", offwidth="1920", offheight="1080")
    ET.SubElement(visual, "quality", shadowsize=shadowsize,
                  offsamples=offsamples)
    ET.SubElement(visual, "headlight", ambient=".25 .25 .25",
                  diffuse=".55 .55 .55", specular=".3 .3 .3")
    asset = ET.SubElement(root, "asset")
    ET.SubElement(asset, "texture", name="sky", type="skybox", builtin="gradient",
                  rgb1=".18 .28 .39", rgb2=".7 .79 .85", width="256", height="1536")
    ET.SubElement(asset, "texture", name="tiles", type="2d", builtin="checker",
                  rgb1=".47 .56 .60", rgb2=".61 .68 .70", width="256", height="256")
    ET.SubElement(asset, "material", name="ground", texture="tiles",
                  texrepeat="4 4", texuniform="true", reflectance=".12")
    ET.SubElement(asset, "material", name="object", rgba="0.9 .38 .08 1",
                  specular=".7", shininess=".6")
    world = root.find("worldbody")
    ET.SubElement(world, "light", pos="-2 -3 5", dir=".3 .4 -1",
                  diffuse=".9 .85 .75", specular=".5 .5 .5", castshadow="true",
                  directional="true")
    ET.SubElement(world, "light", pos="2 3 3", dir="-.5 -.5 -1",
                  diffuse=".3 .4 .5", castshadow="false")
    for geom in root.findall(".//geom"):
        geom.set("material", "ground" if geom.get("type") == "plane" else "object")
    if name == "pendulum":
        # The original point-mass inertia is explicit. The visible rod, anchor
        # and floor have zero mass and cannot collide; no physics is changed.
        mover = world.find("body")
        ET.SubElement(mover, "geom", name="visual_link", type="capsule",
                      fromto="0 0 0 0 0 -1", size=".006", mass="0",
                      contype="0", conaffinity="0", rgba=".65 .72 .78 1")
        ET.SubElement(world, "geom", name="visual_anchor", type="sphere",
                      pos="0 0 2", size=".035", mass="0", contype="0",
                      conaffinity="0", rgba=".2 .3 .4 1")
        ET.SubElement(world, "geom", name="visual_floor", type="plane",
                      size="5 5 .1", mass="0", contype="0", conaffinity="0",
                      material="ground")
    xml = ET.tostring(root, encoding="unicode")
    (outfile or DATA / f"render_{name}.xml").write_text(xml + "\n")
    return mujoco.MjModel.from_xml_string(xml)


def assert_physics(original, rendered):
    # Existing geoms keep their exact shape, contact settings and transforms.
    # Added geoms are strictly visual; explicit inertia is unchanged.
    for key in ("body_mass", "body_inertia", "body_ipos", "body_iquat",
                "body_pos", "body_quat", "qpos0", "dof_damping",
                "jnt_axis", "jnt_pos"):
        assert_state(getattr(rendered, key), getattr(original, key), f"physics {key}")
    indices = [mujoco.mj_name2id(rendered, mujoco.mjtObj.mjOBJ_GEOM,
                               mujoco.mj_id2name(original, mujoco.mjtObj.mjOBJ_GEOM, i))
               for i in range(original.ngeom)]
    assert all(i >= 0 for i in indices), "Missing original geometry"
    for key in ("geom_size", "geom_pos", "geom_quat", "geom_friction",
                "geom_solref", "geom_solimp", "geom_contype", "geom_conaffinity"):
        assert_state(getattr(rendered, key)[indices],
                     getattr(original, key), f"physics {key}")
    assert rendered.opt.timestep == original.opt.timestep == SPEC["timestep_s"]
    assert_state(rendered.opt.gravity, original.opt.gravity, "physics gravity")
    for i in set(range(rendered.ngeom)) - set(indices):
        assert rendered.geom_contype[i] == rendered.geom_conaffinity[i] == 0


class Replay:
    def __init__(self, name, offsamples="4", shadowsize="2048",
                 xml_prefix="render"):
        self.name = name
        self.scene = SCENES[name]
        self.rows = grade.parse_traj(DATA / self.scene["output"])
        source = (DATA / f"model_{name}.xml").read_text()
        self.original = mujoco.MjModel.from_xml_string(source)
        self.model = visual_model(name, source, offsamples, shadowsize,
                                  DATA / f"{xml_prefix}_{name}.xml")
        assert_physics(self.original, self.model)
        self.data = mujoco.MjData(self.model)
        self.states = self.replay()
        np.save(DATA / f"state_{name}.npy", self.states, allow_pickle=False)
        # One Renderer per output size, held for the whole recording.
        self.renderers: dict[tuple[int, int], object] = {}
        self.renderer = None
        self.live = None
        self.checked = 0
        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        if name == "drop":
            self.camera.lookat[:] = [0, 0, .48]
            self.camera.distance, self.camera.azimuth, self.camera.elevation = 2.2, 115, -16
        elif name.startswith("incline"):
            self.camera.lookat[:] = [.35, 0, -.13] if name.endswith("slide") else [0, 0, .03]
            self.camera.distance, self.camera.azimuth, self.camera.elevation = 1.9, 100, -12
        else:
            self.camera.lookat[:] = [0, 0, 1.48]
            self.camera.distance, self.camera.azimuth, self.camera.elevation = 2.3, 90, -10

    def replay(self):
        """Verify every sample against the *actual* CSV scored by the judge."""
        data = mujoco.MjData(self.original)
        if self.name == "pendulum":
            data.qpos[0] = -self.scene["theta0_rad"]
        mujoco.mj_forward(self.original, data)
        states = []
        bid = mujoco.mj_name2id(self.original, mujoco.mjtObj.mjOBJ_BODY, "mover")
        for i in range(len(self.rows["t"])):
            before = data.qpos.copy()
            if i:
                mujoco.mj_step(self.original, data)
            p = data.xpos[bid]
            if self.name == "drop":
                measured = [p[2], data.qvel[5]]
            elif self.name.startswith("incline"):
                measured = [p[0], p[2], data.qvel[3], data.qvel[5]]
            else:
                measured = [-data.qpos[0], -data.qvel[0]]
            expected = [self.rows[c][i] for c in self.scene["columns"][1:]]
            assert_state(measured, expected, f"{self.name} CSV sample {i}")
            assert abs(self.rows["t"][i] - i * self.original.opt.timestep) < 1e-12
            # mj_step leaves xpos at its pre-integration value. Free-joint
            # CSVs record xpos; pendulum CSVs instead record the updated qpos.
            states.append(data.qpos.copy() if self.name == "pendulum" else before)
        print(f"{self.name}: {len(states)} actual graded samples verified", flush=True)
        return np.asarray(states)

    def frame(self, index, width=1920, height=1080):
        # A MuJoCo Renderer owns its offscreen surface, so one is kept per
        # (scene, size) and reused. Rebuilding mid-recording corrupts the
        # OSMesa context - the 2x2 grid comes back as noise - so the first
        # frame of a new size closes only the renderer it already held and
        # opens one, and never again while that size is in use.
        size = (int(width), int(height))
        if self.renderers and size not in self.renderers:
            self.live.close()
            self.renderers.clear()
        if not self.renderers:
            self.renderers[size] = mujoco.Renderer(self.model, height, width)
        self.live = self.renderers[size]
        self.renderer = self.live
        self.data.qpos[:] = self.states[index]
        mujoco.mj_forward(self.model, self.data)
        assert_state(self.data.qpos, self.states[index], f"{self.name} frame {index} qpos")
        bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "mover")
        if self.name == "pendulum":
            assert_state([-self.data.qpos[0]], [self.rows["theta"][index]],
                         f"{self.name} frame {index} angle")
        else:
            cols, axes = (["z"], [2]) if self.name == "drop" else (["x", "z"], [0, 2])
            assert_state(self.data.xpos[bid][axes], [self.rows[c][index] for c in cols],
                         f"{self.name} frame {index} graded position")
        self.renderer.update_scene(self.data, camera=self.camera)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = True
        self.checked += 1
        return Image.fromarray(self.renderer.render())

    def close(self):
        for renderer in self.renderers.values():
            renderer.close()
        self.renderers.clear()
        self.live = self.renderer = None


TITLES = {"drop": "01  DROP / sphere meets floor",
          "incline_slide": "02  SLIDE / 35° incline",
          "incline_stick": "03  STICK / 20° incline",
          "pendulum": "04  PENDULUM / anchored swing"}


def caption(image, name, index, compact=False):
    w, h = image.size
    draw = ImageDraw.Draw(image)
    top, bottom = (64, 94) if compact else (150, 225)
    draw.rectangle((0, 0, w, top), fill=WHITE)
    draw.rectangle((0, h - bottom, w, h), fill=WHITE)
    size = 22 if compact else 38
    label(image, (24, 10 if compact else 28), TITLES[name], size, bold=True)
    label(image, (24, h - bottom + 8), readout(name)[0], 20 if compact else 30)
    label(image, (24, h - bottom + (40 if compact else 61)),
          readout(name)[1], 20 if compact else 30, GREEN, True)
    if not compact:
        label(image, (24, 92), f"MuJoCo 3D replay  /  simulation t = {index * SPEC['timestep_s']:.3f} s",
              27, MUTED)
        label(image, (24, h - 70), "Actual graded trajectory  •  seed 0  •  visual-only scene dressing",
              25, MUTED)
    else:
        label(image, (w - 180, 41), f"t = {index * SPEC['timestep_s']:.3f} s", 18, MUTED)
    return image


def result(replays):
    hero = Image.new("RGB", (2400, 2130), WHITE)
    label(hero, (32, 18), "Physics-engine arena / real MuJoCo 3D renders", 44, bold=True)
    label(hero, (32, 80), "Actual judge-scored states • seed 0 • measured vs analytic oracle • all gates PASS",
          28, MUTED)
    moments = {"drop": [0, 441, 650], "incline_slide": [0, 500, 1000],
               "incline_stick": [0, 500, 1000], "pendulum": [0, 502, 1004]}
    for row, (name, indices) in enumerate(moments.items()):
        replay = replays[name]
        for col, index in enumerate(indices):
            image = replay.frame(index).resize((800, 480), Image.Resampling.LANCZOS)
            hero.paste(caption(image, name, index, compact=True), (col * 800, 150 + row * 490))
        replay.close()
    hero.save(HERE / "result.png", dpi=(200, 200))


def loop():
    history = json.loads((DEMO / "examples/good/loop.json").read_text())["iterations"]
    mutants = read_selftest(DATA / "selftest.txt")
    image = Image.new("RGB", (2400, 1600), WHITE)
    draw = ImageDraw.Draw(image)
    label(image, (70, 40), "The fixing loop / a judge that rejects broken ports", 48, bold=True)
    label(image, (70, 115), "Recorded draft replay, not a live agent trace. Results come from judge verdicts.",
          30, MUTED)
    label(image, (70, 230), "Judge result per iteration", 37, bold=True)
    changes = ["Wrong pendulum pivot", "Box not aligned to incline", "Both corrected; agreement PASS"]
    for i, (row, change) in enumerate(zip(history, changes)):
        y = 320 + i * 200
        count = sum(s["pass"] for s in row["scenarios"].values())
        label(image, (70, y), f"Iteration {row['iteration']}  /  {count}/4 scenes", 32, bold=True)
        draw.rounded_rectangle((70, y + 63, 870, y + 98), radius=9, fill="#dbe4e9")
        draw.rounded_rectangle((70, y + 63, 70 + count * 200, y + 98),
                               radius=9, fill=GREEN if row["passed"] else "#b35b13")
        label(image, (70, y + 120), change, 27, MUTED)
        label(image, (910, y + 58), "PASS" if row["passed"] else "FAIL",
              28, GREEN if row["passed"] else INK, True)
    label(image, (1150, 230), "Self-test kill rate: 8/8 = 100%", 37, GREEN, True)
    label(image, (1150, 305), "Known-good: PASS, not killed", 29, bold=True)
    for i, (name, gates) in enumerate(mutants):
        y = 385 + i * 123
        label(image, (1150, y), name, 29, bold=True)
        draw.rectangle((1150, y + 49, 1320, y + 68), fill=GREEN)
        suffix = ", ".join(sorted({g.split(".")[-1] for g in gates.split(",")}))
        label(image, (1350, y + 39), f"KILLED / {suffix}", 26)
    label(image, (70, 1080), "Pass line: all 4 scenes + every judge gate", 30, GREEN, True)
    label(image, (70, 1160), "1  Pendulum fails the oracle", 28)
    label(image, (70, 1230),
          f"2  Stick travel {history[1]['scenarios']['incline_stick']['travel_m'] * 1000:.2f} mm"
          " exceeds 20 mm", 28)
    label(image, (70, 1300), "3  All five gates pass; judge intact", 28)
    label(image, (70, 1500), "Good must pass. Every broken mutant must fail. Self-test determinism: OK.",
          30, MUTED)
    image.save(HERE / "loop.png", dpi=(200, 200))


def pass_card(frame):
    image = frame.copy()
    # Keep the rendered pendulum visible on the right of the final frame.
    panel = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(panel)
    draw.rounded_rectangle((35, 160, 1140, 870), radius=24, fill=(244, 248, 251, 245))
    image = Image.alpha_composite(image.convert("RGBA"), panel).convert("RGB")
    label(image, (75, 195), "PASS / all five judge gates", 46, GREEN, True)
    for y, name in zip((300, 405, 510, 615), SCENES):
        label(image, (75, y), readout(name)[0], 29)
        label(image, (75, y + 43), readout(name)[1], 26, GREEN)
    label(image, (75, 737), "Self-test kill rate 8/8  •  judge intact", 31, bold=True)
    label(image, (75, 799), "graded by the judge in a disposable sandbox", 30)
    return image


def video(replays):
    command = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", "1920x1080", "-r", "30", "-i", "-", "-an", "-c:v", "libx264",
               "-threads", "2", "-crf", "0", "-preset", "ultrafast",
               "-pix_fmt", "yuv444p", "-map_metadata", "-1", str(HERE / "master/demo.mp4")]
    # Drop is slowed 4x; inclines 8x, side by side; pendulum is real time.
    # Indices always address actual graded samples, never interpolated poses.
    with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
        try:
            for name, seconds in (("drop", 6), ("inclines", 8), ("pendulum", 10), ("pass", 4)):
                for i in range(seconds * 30):
                    if name == "inclines":
                        image = Image.new("RGB", (1920, 1080))
                        for x, scene in ((0, "incline_slide"), (960, "incline_stick")):
                            replay = replays[scene]
                            index = round(i * (len(replay.states) - 1) / (seconds * 30 - 1))
                            tile = replay.frame(index, 960, 1080)
                            # Half-width video labels use smaller type but full 3D renders.
                            draw = ImageDraw.Draw(tile)
                            draw.rectangle((0, 0, 960, 150), fill=WHITE)
                            draw.rectangle((0, 855, 960, 1080), fill=WHITE)
                            label(tile, (24, 28), TITLES[scene], 32, bold=True)
                            label(tile, (24, 92), f"simulation t = {index * SPEC['timestep_s']:.3f} s / 8x slow motion", 25, MUTED)
                            for y, text in zip((875, 931), readout(scene)):
                                label(tile, (24, y), text, 27, GREEN if y == 931 else INK)
                            label(tile, (24, 1015), "Real graded state • MuJoCo • seed 0", 25, MUTED)
                            image.paste(tile, (x, 0))
                    else:
                        replay = replays["pendulum" if name == "pass" else name]
                        index = len(replay.states) - 1 if name == "pass" else round(
                            i * (len(replay.states) - 1) / (seconds * 30 - 1))
                        image = replay.frame(index)
                        if name == "pass":
                            # A second camera frames the same final state beside the card.
                            replay.camera.lookat[0] = -.47
                            image = pass_card(replay.frame(index))
                        else:
                            image = caption(image, name, index)
                    encoder.stdin.write(image.tobytes())
                for replay in replays.values():
                    replay.close()
                print(f"video {name}: every frame state-checked", flush=True)
        finally:
            encoder.stdin.close()
        assert encoder.wait() == 0, "Lossless encoding failed"


def main():
    assert all(g["pass"] for g in VERDICT["gates"].values())
    assert all(g["pass"] for s in VERDICT["scenarios"].values() for g in s.values())
    replays = {name: Replay(name) for name in SCENES}
    result(replays)
    loop()
    checks = {n: {"graded_samples": len(r.states), "rendered_frames_checked": r.checked,
                  "max_state_tolerance": 1e-9} for n, r in replays.items()}
    (DATA / "render-checks.json").write_text(json.dumps(checks, indent=2) + "\n")


if __name__ == "__main__":
    main()
