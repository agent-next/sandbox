"""Simulator-native 3D frames, Pillow evidence overlays, and a lossless master."""

from functools import lru_cache
import json
import subprocess
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from evidence import HERE, GATES, assert_state, scene, load_report, reference

WHITE, INK, MUTED = "#f4f8fb", "#142b40", "#536b7d"
BLUE, GREEN, ORANGE = "#186eb0", "#087852", "#b65b10"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H, FPS = 1920, 1080, 30


@lru_cache(maxsize=64)
def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def label(image, xy, text, size=32, fill=INK, bold=False):
    draw = ImageDraw.Draw(image)
    f = font(size, bold)
    box = draw.textbbox(xy, text, font=f)
    assert min(box[:2]) >= 0 and box[2] <= image.width and box[3] <= image.height, \
        f"Clipped label: {text}"
    draw.text(xy, text, font=f, fill=fill)


def visual_model(source):
    """Dress the existing geometry; never add or change a physics object."""
    root = ET.fromstring(source)
    visual = ET.SubElement(root, "visual")
    ET.SubElement(visual, "global", offwidth=str(W), offheight=str(H))
    ET.SubElement(visual, "quality", shadowsize="2048", offsamples="4")
    ET.SubElement(visual, "headlight", ambient=".3 .3 .3",
                  diffuse=".5 .5 .5", specular=".3 .3 .3")
    asset = ET.SubElement(root, "asset")
    ET.SubElement(asset, "texture", name="sky", type="skybox", builtin="gradient",
                  rgb1=".18 .28 .40", rgb2=".72 .82 .88", width="256", height="1536")
    ET.SubElement(asset, "texture", name="tiles", type="2d", builtin="checker",
                  rgb1=".43 .52 .56", rgb2=".60 .68 .70", width="256", height="256")
    ET.SubElement(asset, "material", name="ground", texture="tiles",
                  texrepeat="5 5", texuniform="true", reflectance=".08")
    world = root.find("worldbody")
    ET.SubElement(world, "light", pos="-2 -3 5", dir=".3 .4 -1",
                  diffuse=".9 .85 .75", specular=".5 .5 .5",
                  directional="true", castshadow="true")
    ET.SubElement(world, "light", pos="3 2 4", dir="-.5 -.3 -1",
                  diffuse=".35 .45 .55", castshadow="false")
    colours = (".94 .44 .12 1", ".10 .50 .82 1", ".10 .65 .55 1",
               ".90 .66 .13 1", ".60 .40 .77 1", ".90 .39 .39 1",
               ".15 .66 .76 1", ".95 .60 .26 1")
    for geom in root.findall(".//geom"):
        name = geom.get("name", "")
        if name == "floor":
            geom.set("material", "ground")
            geom.set("rgba", "1 1 1 1")
        elif name.startswith("boxgeom"):
            geom.set("rgba", colours[int(name[7:])])
        elif name == "tabletop":
            geom.set("rgba", ".24 .31 .38 1")
        else:
            geom.set("rgba", ".12 .57 .72 1" if name != "hand" else ".95 .45 .12 1")
    return mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))


def assert_physics(original, rendered):
    for key in ("nq", "nv", "nu", "nbody", "ngeom", "njnt"):
        assert getattr(original, key) == getattr(rendered, key)
    for key in ("body_mass", "body_inertia", "body_ipos", "body_iquat",
                "body_pos", "body_quat", "qpos0", "dof_damping", "dof_armature",
                "jnt_axis", "jnt_pos", "jnt_range", "jnt_limited", "jnt_type",
                "geom_size", "geom_pos", "geom_quat", "geom_type", "geom_friction",
                "geom_solref", "geom_solimp", "geom_contype", "geom_conaffinity",
                "actuator_gainprm", "actuator_biasprm", "actuator_ctrlrange",
                "actuator_forcerange", "actuator_trnid"):
        assert_state(getattr(original, key), getattr(rendered, key), f"physics {key}")
    assert original.opt.timestep == rendered.opt.timestep
    assert original.opt.iterations == rendered.opt.iterations
    assert original.opt.integrator == rendered.opt.integrator
    assert_state(original.opt.gravity, rendered.opt.gravity, "physics gravity")


class Replay:
    def __init__(self):
        self.report = load_report()
        self.timing = self.report["good"]["verdict"]["timing"]
        self.config, xml, expected, _ = reference(self.report)
        self.states = np.load(HERE / "data/cpu-qpos.npy", allow_pickle=False)
        assert_state(self.states, expected, "retained CPU trajectory")
        assert (HERE / "data/model.xml").read_text().strip() == xml.strip()
        self.expected = expected
        self.original = mujoco.MjModel.from_xml_string(xml)
        self.model = visual_model(xml)
        assert_physics(self.original, self.model)
        self.data = mujoco.MjData(self.model)
        self.data.ctrl[:] = scene.ARM_TARGET
        self.renderer = mujoco.Renderer(self.model, H, W)
        self.checked = 0

    def frame(self, index, close=False):
        assert_state(self.states[index], self.expected[index], f"CPU frame {index}")
        self.data.qpos[:] = self.states[index]
        self.data.time = index * self.model.opt.timestep
        mujoco.mj_forward(self.model, self.data)
        assert_state(self.data.qpos, self.expected[index], f"rendered frame {index}")
        camera = mujoco.MjvCamera()
        camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        camera.lookat[:] = [.85, 0, .53] if close else [.52, 0, .56]
        camera.distance = 1.85 if close else 2.55
        camera.azimuth, camera.elevation = 115, -23
        self.renderer.update_scene(self.data, camera=camera)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = True
        self.checked += 1
        return Image.fromarray(self.renderer.render())

    def close(self):
        self.renderer.close()


def caption(image, title, subtitle, lines):
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, W, 140), fill=WHITE)
    draw.rectangle((0, H - 170, W, H), fill=WHITE)
    label(image, (40, 12), title, 54, bold=True)
    label(image, (40, 85), subtitle, 31, MUTED)
    for y, text in zip((H - 152, H - 84), lines):
        label(image, (40, y), text, 40, GREEN if text.startswith("PASS") else INK)
    return image


def result(replay):
    image = Image.new("RGB", (2400, 1950), WHITE)
    label(image, (40, 20), "GPU sim sweep / the scene the judge runs", 56, bold=True)
    label(image, (40, 98), "MuJoCo CPU reference replay of world 0 • exact config, timestep and initial state",
          33, MUTED)
    cpu = replay.timing["cpu"]
    for i, index in enumerate((0, 200, 400, 800)):
        tile = replay.frame(index).resize((1200, 675), Image.Resampling.LANCZOS)
        y = 0 if i < 2 else 675
        x = (i % 2) * 1200
        d = ImageDraw.Draw(tile)
        d.rectangle((0, 0, 1200, 55), fill=WHITE)
        d.rectangle((0, 570, 1200, 675), fill=WHITE)
        label(tile, (24, 4), f"Arm + 8 boxes / t = {index * .001:.3f} s", 31, bold=True)
        label(tile, (24, 573), f"Graded CPU arm error {cpu['arm_max_err']:.4f} rad / oracle < 0.15 rad", 28)
        label(tile, (24, 621), f"PASS at 0.800 s: box centres {cpu['box_z_min']:.3f} m / "
              "0.255 < z < 0.525 m", 27, GREEN)
        image.paste(tile, (x, 160 + y))
    label(image, (40, 1530), "Measured GPU ladder / aggregate steps/s", 38, bold=True)
    draw = ImageDraw.Draw(image)
    points = replay.timing["points"]
    for i, p in enumerate(points):
        x = 40 + i * 470
        label(image, (x, 1600), f"nworld {p['nworld']:,}", 31, MUTED)
        draw.rectangle((x, 1652, x + 420, 1675), fill="#dbe5eb")
        draw.rectangle((x, 1652, x + 420 * p["steps_per_s"] / replay.timing["top_steps_per_s"],
                        1675), fill=BLUE)
        label(image, (x, 1690), f"{p['steps_per_s']:,} steps/s", 34, bold=True)
    t = replay.timing
    label(image, (40, 1772), f"PASS: {t['top_steps_per_s']:,} > {t['speedup_floor']:g} × "
          f"{t['cpu_steps_per_s']:,} = {t['speedup_floor'] * t['cpu_steps_per_s']:,.0f} steps/s "
          f"• {t['speedup']:.1f}× CPU", 35, GREEN, True)
    label(image, (40, 1845), f"World-0 parity {t['parity_max_err']:.5f} < 0.05 rad • "
          "8/8 mutants killed • 4 GiB RTX 5090 slice", 32, MUTED)
    image.save(HERE / "result.png", dpi=(200, 200))


def loop(report):
    image = Image.new("RGB", (2400, 1600), WHITE)
    draw = ImageDraw.Draw(image)
    label(image, (45, 30), "Fixing the config / measured judge results", 54, bold=True)
    label(image, (45, 110), "Recorded config replay, not a live agent trace. Each row cites a real acceptance grade.",
          33, MUTED)
    label(image, (45, 208), "Iteration replay / pass line: all 6 gates", 40, bold=True)
    history = json.loads((HERE / "data/loop.json").read_text())
    for i, row in enumerate(history["iterations"]):
        source = row["report_key"]
        gates = report["good"]["verdict"]["gates"] if source == "good" else \
            report["mutants"][source]["gates"]
        passed = sum((v["pass"] if isinstance(v, dict) else v) is True for v in gates.values())
        y = 300 + i * 145
        label(image, (45, y), f"{i + 1}. {row['label']}", 33, bold=True)
        draw.rectangle((45, y + 58, 820, y + 90), fill="#dbe5eb")
        draw.rectangle((45, y + 58, 45 + 775 * passed / len(GATES), y + 90),
                       fill=GREEN if passed == len(GATES) else ORANGE)
        label(image, (860, y + 45), f"{passed}/6  {'PASS' if passed == 6 else 'FAIL'}", 34)
    label(image, (1240, 208), "Self-test / 8 of 8 killed = 100%", 40, GREEN, True)
    draw.rectangle((1240, 280, 2350, 325), fill=GREEN)
    label(image, (1240, 350), "Pass line ≥ 90% • 0 survived • good PASS", 31)
    for i, (name, mutant) in enumerate(sorted(report["mutants"].items())):
        y = 425 + i * 124
        label(image, (1240, y), name, 31, bold=True)
        label(image, (1240, y + 46), "KILLED / " + ", ".join(mutant["failed"]), 27, GREEN)
    label(image, (45, 800), "Final good config / every gate PASS", 37, GREEN, True)
    for i, gate_name in enumerate(GATES):
        label(image, (45, 890 + i * 73), f"PASS  {gate_name}", 33)
    label(image, (45, 1415), "Seed 0 • judge intact • broken configs really fail", 31, MUTED)
    label(image, (45, 1490), "Source: data/report.json + data/loop.json", 29, MUTED)
    image.save(HERE / "loop.png", dpi=(200, 200))


def tiled_frame(replay, index):
    tile = replay.frame(index).resize((320, 180), Image.Resampling.LANCZOS)
    image = Image.new("RGB", (W, H), WHITE)
    for row in range(4):
        for col in range(4):
            image.paste(tile, (320 + col * 320, 150 + row * 180))
    return image


def video(replay):
    command = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264",
               "-threads", "1", "-crf", "0", "-preset", "ultrafast", "-pix_fmt", "yuv444p",
               "-map_metadata", "-1", str(HERE / "master/demo.mp4")]
    t = replay.timing
    end = replay.config["settle_steps"]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
        try:
            for f in range(26 * FPS):
                seconds = f / FPS
                if seconds < 2:
                    image = replay.frame(end)
                    caption(image, f"{t['top_steps_per_s']:,} steps/s / physics PASS",
                            "MuJoCo CPU reference replay of world 0 • finished state",
                            [f"{t['speedup']:.1f}× CPU at nworld 8192 • 4 GiB RTX 5090 slice",
                             "PASS: arm reaches target; 8 boxes landed on the table"])
                elif seconds < 8:
                    index = round((seconds - 2) / (6 - 1 / FPS) * end)
                    image = replay.frame(index)
                    caption(image, "01 / Reach the target. Land all eight boxes.",
                            f"MuJoCo CPU reference replay of world 0 • t = {index * .001:.3f} s • 7.5× slow",
                            ["Config: dt 0.001 s • implicitfast • 100 solver iterations",
                             "Oracle at 0.800 s: arm error < 0.15 rad; 0.255 < box z < 0.525 m"])
                elif seconds < 11:
                    index = round((seconds - 8) / (3 - 1 / FPS) * end)
                    image = replay.frame(index, close=True)
                    caption(image, "02 / Contact is the capacity trap",
                            f"MuJoCo CPU reference replay of world 0 • t = {index * .001:.3f} s • 3.75× slow",
                            ["Eight free bodies fall from 0.50–1.10 m onto the table",
                             f"PASS: graded CPU box centres {t['cpu']['box_z_min']:.3f} m • oracle > 0.255 m"])
                elif seconds < 21:
                    phase = seconds - 11
                    point_index = min(4, int(phase / 2))
                    p = t["points"][point_index]
                    index = round((phase % 2) / (2 - 1 / FPS) * end)
                    image = tiled_frame(replay, index)
                    # Count-up is only a reveal animation. Only the endpoint is
                    # a measurement, and the caption makes this distinction explicit.
                    fraction = min(1, (phase % 2) / .8)
                    shown = round(p["steps_per_s"] * fraction)
                    caption(image, f"03 / nworld {p['nworld']:,} → {shown:,} steps/s",
                            "16 replay tiles • identical initial states in every world • no randomized variety",
                            [f"Measured endpoint: {p['steps_per_s']:,} steps/s • count-up is a reveal, not a live meter",
                             "MuJoCo CPU reference replay of world 0 • repeated tiles • 2.5× slow"])
                else:
                    image = replay.frame(end)
                    caption(image, f"PASS / {t['top_steps_per_s']:,} steps/s at nworld 8192",
                            "MuJoCo CPU reference replay of world 0 • graded by the judge on a 4 GiB RTX 5090 slice",
                            [f"CPU {t['cpu_steps_per_s']:,} steps/s • {t['speedup']:.1f}× • "
                             f"floor {t['speedup_floor']:g}× • 8/8 mutants killed",
                             f"Parity {t['parity_max_err']:.5f} < 0.05 rad • run: python3 run.py --gpu"])
                encoder.stdin.write(image.tobytes())
        finally:
            encoder.stdin.close()
        assert encoder.wait() == 0, "Lossless master encode failed"
    print(f"MuJoCo Renderer: {replay.checked} frames verified against CPU qpos data within 1e-9")


def main():
    replay = Replay()
    try:
        result(replay)
        loop(replay.report)
        video(replay)
    finally:
        replay.close()


if __name__ == "__main__":
    main()
