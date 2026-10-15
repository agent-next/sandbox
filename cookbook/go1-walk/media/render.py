"""MuJoCo Renderer replay of exact judge states; Pillow for labels/figures."""

import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from OpenGL import GL

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
DATA = HERE / "data"
WHITE, INK, MUTED, GREEN, ORANGE = "#f4f8fb", "#172e40", "#526777", "#087852", "#a94e0d"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
GRAPHICS = {}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(image, xy, value, size=30, color=INK, bold=False):
    font = ImageFont.truetype(BOLD if bold else FONT, size)
    draw = ImageDraw.Draw(image)
    box = draw.textbbox(xy, value, font=font)
    assert min(box[:2]) >= 0 and box[2] <= image.width and box[3] <= image.height, value
    draw.text(xy, value, font=font, fill=color)


def assert_state(actual, expected, context):
    actual, expected = np.asarray(actual), np.asarray(expected)
    assert actual.shape == expected.shape, f"{context}: shape mismatch"
    assert np.isfinite(actual).all() and np.isfinite(expected).all(), context
    assert np.max(np.abs(actual - expected), initial=0) <= 1e-9, \
        f"{context}: rendered state differs from graded trajectory"


def visual_model():
    DATA.mkdir(exist_ok=True)
    source = (DEMO / "model/go1_meshless.xml").read_text()
    root = ET.fromstring(source)
    visual = ET.SubElement(root, "visual")
    ET.SubElement(visual, "global", offwidth="1920", offheight="1080")
    ET.SubElement(visual, "quality", shadowsize="2048", offsamples="4")
    ET.SubElement(visual, "headlight", ambient=".2 .2 .2",
                  diffuse=".45 .45 .45", specular=".3 .3 .3")
    asset = ET.SubElement(root, "asset")
    ET.SubElement(asset, "texture", name="sky", type="skybox", builtin="gradient",
                  rgb1=".2 .3 .4", rgb2=".75 .83 .88", width="256", height="1536")
    ET.SubElement(asset, "texture", name="tiles", type="2d", builtin="checker",
                  rgb1=".48 .57 .61", rgb2=".65 .71 .73", width="256", height="256")
    ET.SubElement(asset, "material", name="ground", texture="tiles",
                  texrepeat="2 2", texuniform="true", reflectance=".08")
    world = root.find("worldbody")
    ET.SubElement(world, "light", pos="-2 -3 5", dir=".3 .4 -1",
                  diffuse=".9 .85 .75", specular=".5 .5 .5",
                  castshadow="true", directional="true")
    ET.SubElement(world, "light", pos="2 3 3", dir="-.5 -.5 -1",
                  diffuse=".3 .4 .5", castshadow="false")
    for geom in world.findall(".//geom"):
        if geom.get("name") == "floor":
            geom.set("material", "ground")
        else:
            geom.set("rgba", ".13 .23 .31 1")
    for geom in world.find("body").findall("geom"):
        geom.set("rgba", ".91 .46 .12 1")
    xml = ET.tostring(root, encoding="unicode")
    (DATA / "render-model.xml").write_text(xml + "\n")
    original = mujoco.MjModel.from_xml_string(source)
    rendered = mujoco.MjModel.from_xml_string(xml)
    # No added collision geometry, body or actuator. All dynamics are identical.
    for key in ("body_mass", "body_inertia", "body_ipos", "body_iquat",
                "body_pos", "body_quat", "qpos0", "dof_damping", "dof_armature",
                "jnt_axis", "jnt_pos", "jnt_range", "geom_size", "geom_pos",
                "geom_quat", "geom_friction", "geom_solref", "geom_solimp",
                "geom_contype", "geom_conaffinity", "geom_condim",
                "actuator_gainprm", "actuator_biasprm", "actuator_ctrlrange",
                "actuator_forcerange"):
        assert_state(getattr(rendered, key), getattr(original, key), f"physics {key}")
    assert rendered.opt.timestep == original.opt.timestep == .002
    assert_state(rendered.opt.gravity, original.opt.gravity, "gravity")
    return rendered


class Replay:
    def __init__(self, model, name, seed):
        self.name, self.seed, self.model = name, seed, model
        self.verdict = json.loads((DATA / f"{name}.json").read_text())
        path = DATA / f"{name}-{seed}.npz"
        assert sha(path) == self.verdict["traces"][str(seed)], "trace hash mismatch"
        with np.load(path, allow_pickle=False) as z:
            assert str(z["model_sha256"]) == sha(DEMO / "model/go1_meshless.xml")
            assert float(z["sim_dt"]) == model.opt.timestep
            assert float(z["control_dt"]) == .02 and float(z["mass_scale"]) == 1
            self.qpos, self.qvel, self.alive = z["qpos"], z["qvel"], z["alive"]
            self.metrics = json.loads(str(z["metrics"]))
            initial_qpos, final_qpos, final_alive = z["initial_qpos"], z["final_qpos"], z["final_alive"]
            assert int(z["episode"]) == 0
        assert self.qpos.shape == (501, 1, 19)
        # Episode 0 is fixed a priori, never selected for a flattering gait.
        self.episode = 0
        self.data = mujoco.MjData(model)
        self.option = mujoco.MjvOption()
        self.option.geomgroup[:] = 1  # The shipped robot uses collision group 3.
        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.camera.distance = 1.45
        self.camera.azimuth, self.camera.elevation = 120, -19
        self.renderer = None
        self.checked = 0
        # Recompute plotted aggregate numbers directly from the saved states.
        speed = float(np.mean((final_qpos[:, 0] - initial_qpos[:, 0]) / 10))
        fall = float(np.mean(~final_alive))
        assert_state(self.qpos[0, 0], initial_qpos[0], "initial recorded state")
        assert_state(self.qpos[-1, 0], final_qpos[0], "final recorded state")
        assert round(speed, 6) == self.metrics["forward_mps"]
        assert round(fall, 6) == self.metrics["fall_rate"]
        self.first_fall = int(np.argmax(~self.alive[:, 0])) \
            if not self.alive[-1, 0] else None

    def frame(self, index, width=960, height=780):
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, height, width)
        assert (self.renderer.width, self.renderer.height) == (width, height)
        state = self.qpos[index, self.episode]
        self.data.qpos[:] = state
        self.data.qvel[:] = self.qvel[index, self.episode]
        self.data.time = index * .02
        mujoco.mj_forward(self.model, self.data)
        assert_state(self.data.qpos, state, f"{self.name} seed {self.seed} frame {index}")
        assert_state(self.data.qvel, self.qvel[index, self.episode], "qvel replay")
        self.camera.lookat[:] = [state[0], state[1], .19]
        self.renderer.update_scene(self.data, camera=self.camera,
                                   scene_option=self.option)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = True
        image = Image.fromarray(self.renderer.render())
        if not GRAPHICS:
            GRAPHICS.update({name: GL.glGetString(value).decode() for name, value in
                             (("vendor", GL.GL_VENDOR), ("renderer", GL.GL_RENDERER),
                              ("version", GL.GL_VERSION))})
        assert_state(self.data.qpos, state, "post-render qpos")
        self.checked += 1
        return image

    def close(self):
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None


def readout(replay):
    m = replay.metrics
    return (f"Speed {m['forward_mps']:.3f} m/s  |  pass >= 0.500",
            f"Falls {m['fall_rate']:.1%}  |  pass <= 5.0%")


def result(replays):
    image = Image.new("RGB", (2400, 1300), WHITE)
    text(image, (35, 22), "Go1 learns to walk / real MuJoCo 3D states", 46, bold=True)
    text(image, (35, 90), "Held-out seeds 101 / 202 / 303  •  command 1.0 m/s  •  64 episodes per seed", 30, MUTED)
    for row, name in enumerate(("trained", "untrained")):
        for col, (seed, moment) in enumerate(((101, 2), (202, 5), (303, 8))):
            replay = replays[name, seed]
            frame = replay.frame(round(moment / .02), 800, 410)
            tile = Image.new("RGB", (800, 550), WHITE)
            tile.paste(frame, (0, 58))
            text(tile, (20, 12), f"{name.upper()} / seed {seed} / t={moment:.1f} s", 27, bold=True)
            text(tile, (20, 475), readout(replay)[0], 25)
            text(tile, (20, 512), readout(replay)[1] + ("  PASS" if name == "trained" else "  FAIL"),
                 25, GREEN if name == "trained" else ORANGE, True)
            image.paste(tile, (col * 800, 160 + row * 565))
            replay.close()
    image.save(HERE / "result.png", dpi=(200, 200))


def loop():
    curve = json.loads((DEMO / "examples/good/curve.json").read_text())["curve"]
    history = json.loads((DEMO / "examples/good/loop.json").read_text())["iterations"]
    test = json.loads((DATA / "selftest.json").read_text())
    image = Image.new("RGB", (2400, 1600), WHITE)
    draw = ImageDraw.Draw(image)
    text(image, (60, 30), "PPO training, independent judge, real mutation test", 46, bold=True)
    text(image, (60, 105), "Training reward is not acceptance. Only fresh held-out simulation decides PASS.", 30, MUTED)
    text(image, (60, 205), "Training curve / mean reward per control step", 32, bold=True)
    x0, x1, y0, y1 = 125, 1050, 315, 720
    rewards = [r["mean_reward"] for r in curve]
    lo, hi = min(rewards), max(rewards)
    pad = max((hi-lo) * .05, .01)
    lo, hi = lo-pad, hi+pad
    for i in range(5):
        value = lo + (hi-lo) * i/4
        y = y1 - (y1-y0)*i/4
        draw.line((x0, y, x1, y), fill="#dbe4e9", width=2)
        text(image, (60, int(y)-12), f"{value:.1f}", 24, MUTED)
    points = [(x0+(x1-x0)*r["it"]/curve[-1]["it"],
               y1-(y1-y0)*(r["mean_reward"]-lo)/(hi-lo)) for r in curve]
    draw.line(points, fill="#0072b2", width=5)
    text(image, (125, 740), "PPO iteration", 25, MUTED)
    text(image, (930, 740), str(curve[-1]["it"]), 25)
    text(image, (60, 845), "Judge result per agent-loop iteration", 32, bold=True)
    for i, entry in enumerate(history):
        y = 920 + i * 180
        v = entry["verdict"]
        m = v["measured"]
        count = sum(g["pass"] for g in v["gates"].values())
        text(image, (60, y), f"Iteration {entry['iteration']}  /  {entry['change']}", 27, bold=True)
        draw.rectangle((60, y+53, 60+count*155, y+78),
                       fill=GREEN if v["ok"] else ORANGE)
        text(image, (860, y+43), f"{count}/5 gates", 26)
        text(image, (60, y+98),
             f"{m['mean_forward_mps']:.3f} m/s • falls {m['fall_rate']:.1%} • "
             f"{'PASS' if v['ok'] else 'FAIL'}", 26)
    rate = test["kill_rate"]
    text(image, (1190, 205), f"Self-test: {test['killed']}/{test['total']} = {rate:.0%} killed",
         36, GREEN, True)
    text(image, (1190, 275), "Pass line: >= 90%; every shipped mutant fails", 27)
    draw.rectangle((1190, 330, 2290, 365), fill="#dbe4e9")
    draw.rectangle((1190, 330, 1190+1100*rate, 365), fill=GREEN)
    draw.line((1190+1100*.9, 312, 1190+1100*.9, 385), fill=INK, width=4)
    for i, (name, row) in enumerate(test["mutants"].items()):
        y = 425 + i*95
        text(image, (1190, y), name, 28, bold=True)
        gates = ", ".join(g.split("_")[0].upper() for g in row["failed_gates"])
        text(image, (1740, y), "KILLED: " + gates, 25, GREEN)
    text(image, (60, 1515), "Same checkpoint + same seeds: byte-identical verdicts outside timing.", 30, MUTED)
    image.save(HERE / "loop.png", dpi=(200, 200))


def video(replays):
    command = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", "1920x1080", "-r", "30", "-i", "-", "-an", "-c:v", "libx264",
               "-threads", "2", "-crf", "0", "-preset", "ultrafast", "-pix_fmt", "yuv444p",
               "-map_metadata", "-1", str(HERE / "master/demo.mp4")]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
        try:
            for seed in (101, 202, 303):
                for frame in range(300):
                    index = round((frame / 30) / .02)
                    image = Image.new("RGB", (1920, 1080), WHITE)
                    text(image, (36, 20), "Go1 / from random weights to walking", 46, bold=True)
                    text(image, (36, 85), f"Seed {seed} • episode 0 • t={index*.02:.2f} s • readouts: 64-episode judge averages",
                         29, MUTED)
                    for x, name in ((0, "trained"), (960, "untrained")):
                        replay = replays[name, seed]
                        image.paste(replay.frame(index), (x, 170))
                        text(image, (x+28, 128), "TRAINED / PASS" if name == "trained" else "RANDOM INIT / FAIL",
                             31, GREEN if name == "trained" else ORANGE, True)
                        text(image, (x+28, 960), readout(replay)[0], 28)
                        text(image, (x+28, 1007), readout(replay)[1], 28,
                             GREEN if name == "trained" else ORANGE)
                        if replay.first_fall is not None and index >= replay.first_fall:
                            text(image, (x+590, 128), "FALL / terminated", 25, ORANGE)
                    assert image.size == (1920, 1080)
                    encoder.stdin.write(image.tobytes())
                    # Full-size PNGs are actual video frames for the human review.
                    global_frame = (0 if seed == 101 else 300 if seed == 202 else 600) + frame
                    if global_frame in (0, 30, 120, 330, 750):
                        image.save(HERE / "work" / f"frame-{global_frame:04}.png")
                for name in ("trained", "untrained"):
                    replays[name, seed].close()
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise RuntimeError("lossless master encode failed")
        except BaseException:
            encoder.kill()
            raise


def main():
    assert mujoco.__version__ == "3.8.1", "wrong render engine"
    for directory in ("work", "master"):
        (HERE / directory).mkdir(exist_ok=True)
    model = visual_model()
    replays = {(name, seed): Replay(model, name, seed)
               for name in ("trained", "untrained") for seed in (101, 202, 303)}
    try:
        result(replays)
        loop()
        video(replays)
    finally:
        for replay in replays.values():
            replay.close()
    report = {"frames": 900, "duration_s": 30, "width": 1920, "height": 1080,
              "fps": 30, "backend": os_backend(),
              "graphics": GRAPHICS,
              "state_checks": {f"{n}-{s}": r.checked for (n, s), r in replays.items()},
              "episode_selection": "episode 0, fixed before grading",
              "model_sha256": sha(DEMO / "model/go1_meshless.xml"),
              "render_model_sha256": sha(DATA / "render-model.xml")}
    (DATA / "render.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


def os_backend():
    import os
    return os.environ.get("MUJOCO_GL", "unknown")


if __name__ == "__main__":
    main()
