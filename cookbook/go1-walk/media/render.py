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
                  rgb1=".52 .59 .62", rgb2=".59 .65 .67", width="256", height="256")
    ET.SubElement(asset, "material", name="ground", texture="tiles",
                  texrepeat="1 1", texuniform="true", reflectance="0")
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
        checkpoint = DEMO / "examples/good/policy.npz" if name == "trained" \
            else DATA / "untrained-policy.npz"
        assert sha(checkpoint) == self.verdict["policy_sha256"], \
            "checkpoint differs from the graded media source"
        assert self.verdict["judge_intact"] and self.verdict["backend"] == "mujoco-cpu-float64"
        assert self.verdict["ok"] == (name == "trained"), "incorrect PASS/FAIL caption"
        evaluation = self.verdict["eval"]
        assert evaluation["episodes_per_seed"] == 64 and evaluation["steps"] == 500
        assert evaluation["cmd"] == [1.0, 0.0, 0.0] and evaluation["mass_scale"] == 1.0
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
        graded = next(r for r in self.verdict["runs"]
                      if r["seed"] == seed and r["policy"] == "under_test")
        assert self.metrics == {k: v for k, v in graded.items() if k not in ("seed", "policy")}
        assert self.qpos.shape == (501, 1, 19)
        # Episode 0 is fixed a priori, never selected for a flattering gait.
        self.episode = 0
        self.data = mujoco.MjData(model)
        self.light_positions = model.light_pos.copy()
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
        # Directional shadow maps are centred on the light, not the camera.
        # Follow the robot so its shadow remains visible after metres of travel.
        self.model.light_pos[:] = self.light_positions
        self.model.light_pos[:, :2] += state[:2]
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
    image = Image.new("RGB", (2400, max(1600, 1030 + 140 * len(history))), WHITE)
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
        y = 920 + i * 140
        v = entry["verdict"]
        m = v["measured"]
        count = sum(g["pass"] for g in v["gates"].values())
        text(image, (60, y), f"Iteration {entry['iteration']}  /  {entry['change']}", 27, bold=True)
        draw.rectangle((60, y+43, 60+count*155, y+63),
                       fill=GREEN if v["ok"] else ORANGE)
        text(image, (860, y+35), f"{count}/5 gates", 26)
        text(image, (60, y+78),
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
    text(image, (60, image.height - 85),
         "Same checkpoint + same seeds: byte-identical verdicts outside timing.", 30, MUTED)
    image.save(HERE / "loop.png", dpi=(200, 200))


def video(replays):
    """Cut lossless simulator clips, then concatenate without re-encoding."""
    clips = HERE / "clips"
    clips.mkdir(exist_ok=True)
    curve = json.loads((DEMO / "examples/good/curve.json").read_text())
    test = json.loads((DATA / "selftest.json").read_text())
    measured = replays["trained", 101].verdict["measured"]
    scenes = (("hook", 60), ("spec", 180), ("compare-202", 180),
              ("compare-303", 180), ("proof", 210), ("end", 90))
    end_background = None
    global_frame = 0

    def view(name, seed, index, width, height, azimuth=120, distance=1.45):
        replay = replays[name, seed]
        if replay.renderer is not None and (
                replay.renderer.width != width or replay.renderer.height != height):
            replay.close()
        replay.camera.azimuth, replay.camera.distance = azimuth, distance
        return replay.frame(index, width, height)

    def panel(image, box):
        layer = Image.new("RGBA", image.size)
        ImageDraw.Draw(layer).rounded_rectangle(box, radius=20, fill=(244, 248, 251, 235))
        image.paste(layer, (0, 0), layer)

    for scene, count in scenes:
        command = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                   "-s", "1920x1080", "-r", "30", "-i", "-", "-an", "-c:v", "libx264",
                   "-threads", "2", "-crf", "0", "-preset", "ultrafast", "-pix_fmt", "yuv444p",
                   "-map_metadata", "-1", str(clips / f"{scene}.mp4")]
        with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
            try:
                for frame in range(count):
                    index = round(frame / 30 / .02)
                    if scene in ("hook", "proof"):
                        image = view("trained", 101, index, 1920, 1080,
                                     132 if scene == "proof" else 120 + 6*frame/count,
                                     1.7 if scene == "proof" else 1.45)
                        if scene == "hook":
                            panel(image, (24, 18, 1350, 190))
                            text(image, (50, 32), "4 GiB → Go1 learns to walk", 64, bold=True)
                            text(image, (50, 112),
                                 f"{measured['mean_forward_mps']:.3f} m/s • {measured['fall_rate']:.1%} falls • held-out judge", 58, GREEN)
                        else:
                            end_background = image.copy()
                            panel(image, (20, 15, 1900, 120))
                            text(image, (45, 28), f"Judge PASS • all {test['total']} mutants rejected", 64, GREEN, True)
                            panel(image, (20, 145, 635, 1055))
                            panel(image, (1320, 145, 1900, 1055))
                            text(image, (45, 166), "Five policy gates", 60, bold=True)
                            rows = (("Speed ≥ 0.500", f"{measured['mean_forward_mps']:.3f} m/s"),
                                    ("Falls ≤ 5%", f"{measured['fall_rate']:.1%}"),
                                    ("Torque sat ≤ 15%", f"{measured['max_sat_frac']:.2%}"),
                                    ("Margin ≥ 0.30", f"{measured['mean_forward_mps'] - measured['best_baseline_forward_mps']:.3f} m/s"),
                                    ("Same seed", "Identical"))
                            for i, (rule, value) in enumerate(rows):
                                y = 265 + 150*i
                                text(image, (45, y), rule, 60)
                                text(image, (45, y+64), value, 64, GREEN, True)
                            text(image, (1345, 162), f"{test['killed']}/{test['total']} killed", 64, GREEN, True)
                            labels = {"short-training": "short training", "reward-flipped": "reward −vx",
                                      "random-init": "random init", "zero-output": "zero",
                                      "negated-output": "negated", "shuffled-output": "shuffled",
                                      "noisy-weights": "noisy", "weak-output": "weak", "mass2x": "mass ×2"}
                            for i, (name, row) in enumerate(test["mutants"].items()):
                                assert row["failed_gates"], "a crash is not a mutation kill"
                                text(image, (1345, 250+i*70), "× " + labels.get(name, name),
                                     60, ORANGE, True)
                    elif scene == "spec":
                        image = Image.new("RGB", (1920, 1080), WHITE)
                        image.paste(view("trained", 101, index+100, 1240, 1080,
                                         140), (680, 0))
                        for y, value in ((35, "PPO → WALK"), (140, "4 GiB GPU slice"),
                                         (235, "vx = 1.0 m/s"), (330, "Held-out seeds"),
                                         (410, "101 / 202 / 303")):
                            text(image, (35, y), value, 60, bold=y == 35)
                        panel(image, (705, 20, 1400, 115))
                        text(image, (730, 30), "Final policy / seed 101", 52, GREEN, True)
                        speed = curve["train_wall_s"] / (count/30)
                        text(image, (35, 560), "PPO telemetry", 60, bold=True)
                        text(image, (35, 640), f"{speed:.0f}× overview", 60, MUTED)
                        values = curve["curve"]
                        visible = [r for r in values if
                                   r["wall_s"] <= curve["train_wall_s"]*(frame+1)/count]
                        lo = min(r["mean_reward"] for r in values)
                        hi = max(r["mean_reward"] for r in values)
                        points = [(45+580*r["it"]/values[-1]["it"],
                                   900-150*(r["mean_reward"]-lo)/(hi-lo)) for r in visible]
                        ImageDraw.Draw(image).line(points, fill="#0072b2", width=6)
                        text(image, (35, 950), f"{values[-1]['it']} recorded iterations", 48, MUTED)
                    elif scene.startswith("compare-"):
                        seed = int(scene.split("-")[1])
                        index = round(frame / 30 * (10/6) / .02)
                        image = Image.new("RGB", (1920, 1080), WHITE)
                        text(image, (30, 18), f"Seed {seed} • 1.67× speed • exact scored states", 60, bold=True)
                        for x, name in ((0, "trained"), (960, "untrained")):
                            replay = replays[name, seed]
                            image.paste(view(name, seed, index, 960, 740,
                                             120 if seed == 202 else 55), (x, 170))
                            color = GREEN if name == "trained" else ORANGE
                            text(image, (x+25, 100), "TRAINED / PASS" if name == "trained" else "RANDOM INIT / FAIL",
                                 58, color, True)
                            text(image, (x+25, 920), f"{replay.metrics['forward_mps']:.3f} m/s  |  ≥ 0.500", 60)
                            text(image, (x+25, 1000), f"Falls {replay.metrics['fall_rate']:.0%}  |  ≤ 5%", 60, color)
                            if replay.first_fall is not None and index >= replay.first_fall:
                                panel(image, (x+12, 185, x+730, 280))
                                text(image, (x+30, 195), "FALL / state frozen", 56, ORANGE, True)
                    else:
                        assert end_background is not None
                        image = end_background.copy()
                        panel(image, (20, 740, 1900, 1060))
                        text(image, (50, 765), "Train it. Grade it. Destroy the lease.", 64, bold=True)
                        text(image, (50, 870), "python3 cookbook/go1-walk/run.py", 72, GREEN, True)
                        text(image, (50, 980), "MuJoCo-Warp PPO / independent CPU MuJoCo judge", 48, MUTED)
                    assert image.size == (1920, 1080)
                    encoder.stdin.write(image.tobytes())
                    if global_frame in (0, 30, 120, 330, 750, 840):
                        image.save(HERE / "work" / f"frame-{global_frame:04}.png")
                    global_frame += 1
                encoder.stdin.close()
                if encoder.wait() != 0:
                    raise RuntimeError(f"lossless clip encode failed: {scene}")
            except BaseException:
                encoder.kill()
                raise
        for replay in replays.values():
            replay.close()
    listing = clips / "concat.txt"
    listing.write_text("".join(f"file '{name}.mp4'\n" for name, _ in scenes))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c", "copy", str(HERE / "master/demo.mp4")], check=True)


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
              "lighting": "render-only world lights follow robot xy for shadow-map coverage",
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
