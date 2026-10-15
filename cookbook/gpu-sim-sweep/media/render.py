"""Simulator-native 3D frames, Pillow evidence overlays, and a lossless master."""

from functools import lru_cache
import hashlib
import json
import subprocess
import tempfile
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
NAVY, CYAN, LIME, AMBER = "#101c2b", "#65d8ec", "#a6edb0", "#ffc17b"
RED = "#ff8585"
DURATION = 30
SHOT_CUTS = (2, 4, 6, 8, 10, 12, 15, 20, 24, 28)
SWEEP_SIDES = (1, 2, 4, 8, 16)
BROKEN = (
    ("smuggled_results", "Fake results"),
    ("gravity_flipped", "Flipped gravity"),
    ("missing_nconmax", "No contact limit"),
    ("tiny_timestep", "Tiny time step"),
    ("short_settle", "Stops too soon"),
    ("solver_iter_1", "Weak solver"),
    ("low_capacity", "Contact overflow"),
    ("over_ladder", "Out of memory"),
)
WORLD_COLOURS = ((.16, .72, .85, 1), (.35, .60, .95, 1),
                 (.65, .45, .88, 1), (.95, .61, .22, 1),
                 (.21, .78, .57, 1))


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
    ET.SubElement(visual, "quality", shadowsize="4096", offsamples="4")
    ET.SubElement(visual, "headlight", ambient=".22 .25 .30",
                  diffuse=".45 .5 .55", specular=".3 .3 .3")
    asset = ET.SubElement(root, "asset")
    ET.SubElement(asset, "texture", name="sky", type="skybox", builtin="gradient",
                  rgb1=".06 .10 .17", rgb2=".22 .31 .40", width="256", height="1536")
    ET.SubElement(asset, "texture", name="tiles", type="2d", builtin="checker",
                  rgb1=".14 .21 .28", rgb2=".36 .44 .51", width="256", height="256")
    ET.SubElement(asset, "material", name="ground", texture="tiles",
                  texrepeat="1 1", texuniform="true")
    ET.SubElement(asset, "texture", name="studio-tiles", type="2d", builtin="checker",
                  rgb1=".30 .38 .46", rgb2=".47 .55 .62", width="256", height="256")
    ET.SubElement(asset, "material", name="studio-floor", texture="studio-tiles",
                  texrepeat="1 1", texuniform="true")
    ET.SubElement(asset, "material", name="ceramic",
                  specular=".7", shininess=".65", reflectance=".08")
    ET.SubElement(asset, "material", name="anodized",
                  specular=".5", shininess=".45")
    world = root.find("worldbody")
    ET.SubElement(world, "light", pos="-2 -3 5", dir=".3 .4 -1",
                  diffuse="1 .90 .76", specular=".7 .7 .7",
                  directional="true", castshadow="true")
    ET.SubElement(world, "light", pos="3 2 4", dir="-.5 -.3 -1",
                  diffuse=".45 .65 .85", castshadow="false")
    colours = (".94 .44 .12 1", ".10 .50 .82 1", ".10 .65 .55 1",
               ".90 .66 .13 1", ".60 .40 .77 1", ".90 .39 .39 1",
               ".15 .66 .76 1", ".95 .60 .26 1")
    for geom in root.findall(".//geom"):
        name = geom.get("name", "")
        if name == "floor":
            # Plane x/y size is its finite *drawing* extent, not physics:
            # MuJoCo collides with an infinite plane at either size.
            geom.set("size", "24 24 0.1")
            geom.set("material", "ground")
            geom.set("rgba", "1 1 1 1")
        elif name.startswith("boxgeom"):
            geom.set("rgba", colours[int(name[7:])])
            geom.set("material", "ceramic")
        elif name == "tabletop":
            geom.set("rgba", ".32 .40 .48 1")
            geom.set("material", "anodized")
        else:
            geom.set("rgba", ".16 .72 .85 1" if name != "hand" else ".97 .56 .16 1")
            geom.set("material", "ceramic")
    return mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))


@lru_cache(maxsize=2)
def visual_replay(xml, settle, count=256, seed=0):
    """Unmeasured CPU simulations, not retained GPU worlds or performance data."""
    model = mujoco.MjModel.from_xml_string(xml)
    rng = np.random.default_rng(seed)
    states = np.empty((count, settle + 1, model.nq))
    for world in range(count):
        data = mujoco.MjData(model)
        data.ctrl[:] = scene.ARM_TARGET
        data.qpos[:7] += rng.uniform(-.12, .12, 7)
        for box in range(8):
            start = 7 + 7 * box
            data.qpos[start:start + 3] += rng.uniform(
                [-.025, -.025, -.08], [.025, .025, .08])
            axis = rng.normal(size=3)
            axis /= np.linalg.norm(axis)
            angle = rng.uniform(-.35, .35)
            data.qpos[start + 3:start + 7] = np.r_[
                np.cos(angle / 2), axis * np.sin(angle / 2)]
        states[world, 0] = data.qpos
        for step in range(settle):
            mujoco.mj_step(model, data)
            states[world, step + 1] = data.qpos
    assert np.isfinite(states).all(), "Non-finite visual replay"
    states.setflags(write=False)
    return states


def visual_provenance(replay):
    states = visual_replay((HERE / "data/model.xml").read_text().strip(),
                           replay.config["settle_steps"])
    metadata = {
        "measured": False,
        "on_screen_label": "visual replay, perturbed starts",
        "source": "same good config and controls; new CPU simulations only",
        "measured_gpu_starts": "identical; these are NOT the measured worlds",
        "seed": 0, "worlds_rendered_at_most": len(states),
        "arm_start_perturbation_rad": [-.12, .12],
        "box_position_perturbation_m": [[-.025, .025], [-.025, .025], [-.08, .08]],
        "box_rotation_perturbation_rad": [-.35, .35],
        "initial_velocity": 0,
        "display_only": "translated world instances; arm colour varies by world",
        "qpos_sha256": hashlib.sha256(states.tobytes()).hexdigest(),
    }
    (HERE / "data/visual-replay.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def assert_physics(original, rendered):
    for key in ("nq", "nv", "nu", "nbody", "ngeom", "njnt"):
        assert getattr(original, key) == getattr(rendered, key)
    for key in ("body_mass", "body_inertia", "body_ipos", "body_iquat",
                "body_pos", "body_quat", "qpos0", "dof_damping", "dof_armature",
                "jnt_axis", "jnt_pos", "jnt_range", "jnt_limited", "jnt_type",
                "geom_pos", "geom_quat", "geom_type", "geom_friction",
                "geom_solref", "geom_solimp", "geom_contype", "geom_conaffinity",
                "actuator_gainprm", "actuator_biasprm", "actuator_ctrlrange",
                "actuator_forcerange", "actuator_trnid"):
        assert_state(getattr(original, key), getattr(rendered, key), f"physics {key}")
    solids = original.geom_type != mujoco.mjtGeom.mjGEOM_PLANE
    assert_state(original.geom_size[solids], rendered.geom_size[solids], "physics geom_size")
    assert_state(original.geom_size[~solids, 2], rendered.geom_size[~solids, 2],
                 "physics plane thickness")
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
        self.gpu_states = np.asarray(self.report["good"]["world0_traj"]["traj"])
        self.gpu_expected = self.gpu_states.copy()
        self.gpu_stride = self.report["good"]["world0_traj"]["stride"]
        self.original = mujoco.MjModel.from_xml_string(xml)
        self.model = visual_model(xml)
        assert_physics(self.original, self.model)
        self.floor_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
        self.dark_floor = self.model.geom_matid[self.floor_id]
        self.studio_floor = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_MATERIAL, "studio-floor")
        self.data = mujoco.MjData(self.model)
        self.data.ctrl[:] = scene.ARM_TARGET
        self.variant_data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, H, W)
        self.checked = 0

    def frame(self, index, close=False, *, azimuth=115, elevation=-23,
              gpu=False, side=1, distance=None, studio=False, perturbed=False):
        assert not (gpu and perturbed), "Visual variants are not GPU recordings"
        sample = min(len(self.gpu_states) - 1, round(index / self.gpu_stride)) if gpu else index
        states, expected = (self.gpu_states, self.gpu_expected) if gpu else \
            (self.states, self.expected)
        assert_state(states[sample], expected[sample], f"{'GPU' if gpu else 'CPU'} frame {sample}")
        self.data.qpos[:] = states[sample]
        poses = None
        if perturbed:
            variants = visual_replay((HERE / "data/model.xml").read_text().strip(),
                                     self.config["settle_steps"])
            assert side * side <= len(variants)
            positions, matrices = [], []
            for state in variants[:side * side, index]:
                self.variant_data.qpos[:] = state
                mujoco.mj_forward(self.model, self.variant_data)
                assert_state(self.variant_data.qpos, state, "visual replay pose")
                positions.append(self.variant_data.geom_xpos.copy())
                matrices.append(self.variant_data.geom_xmat.copy())
            poses = (positions, matrices)
            self.data.qpos[:] = variants[0, index]
        self.data.time = ((sample * self.gpu_stride + 1) if gpu else index) * self.model.opt.timestep
        self.model.geom_matid[self.floor_id] = self.studio_floor if studio else self.dark_floor
        mujoco.mj_forward(self.model, self.data)
        assert_state(self.data.qpos, variants[0, index] if perturbed else expected[sample],
                     f"rendered frame {sample}")
        camera = mujoco.MjvCamera()
        camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        camera.lookat[:] = [.85, 0, .53] if close else [.52, 0, .56]
        camera.distance = distance or (1.65 if close else 2.35)
        if side > 1:
            camera.lookat[:] = [.52, 0, .30]
            camera.distance = distance or side * 2.65
        camera.azimuth, camera.elevation = azimuth, elevation
        self.renderer.update_scene(self.data, camera=camera)
        if side > 1 or perturbed:
            instance_grid(self.renderer.scene, side, poses=poses)
        # MuJoCo's compiled shadow bounds otherwise only cover the source
        # world. Expand render coverage for display-only grid instances.
        self.renderer._mjr_context.shadowClip = max(self.model.stat.extent, 3 * side)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = True
        self.checked += 1
        return Image.fromarray(self.renderer.render())

    def close(self):
        self.renderer.close()


def instance_grid(view, side, poses=None):
    """Native 3D geoms from verified poses, translated only for display."""
    original = view.ngeom
    fields = ("type", "dataid", "objtype", "objid", "category", "matid",
              "emission", "specular", "shininess", "reflectance",
              "transparent", "modelrbound", "texcoord")
    arrays = ("size", "mat", "rgba")
    # Keep one continuous floor. All other MuJoCo geoms share the verified pose.
    geoms = [i for i in range(original)
             if view.geoms[i].type != mujoco.mjtGeom.mjGEOM_PLANE]
    assert original + (side * side - 1) * len(geoms) <= view.maxgeom
    spacing = 1.85
    origin = np.array([-(side - 1) * spacing / 2, -(side - 1) * spacing / 2, 0])
    for row in range(side):
        for col in range(side):
            if row == col == 0:
                continue
            offset = np.array([col * spacing, row * spacing, 0])
            for i in geoms:
                source, dest = view.geoms[i], view.geoms[view.ngeom]
                mujoco.mjv_initGeom(dest, source.type, source.size.astype(float),
                                   source.pos + origin + offset,
                                   source.mat.astype(float).ravel(), source.rgba)
                for key in fields:
                    setattr(dest, key, getattr(source, key))
                for key in arrays:
                    getattr(dest, key)[:] = getattr(source, key)
                if poses is not None:
                    world = row * side + col
                    dest.pos[:] = poses[0][world][source.objid] + origin + offset
                    dest.mat[:] = poses[1][world][source.objid].reshape(3, 3)
                    if source.type == mujoco.mjtGeom.mjGEOM_CAPSULE:
                        dest.rgba[:] = WORLD_COLOURS[world % len(WORLD_COLOURS)]
                view.ngeom += 1
    for i in geoms:
        view.geoms[i].pos[:] += origin


def hud(image, title, detail, footer, source):
    """Phone-readable captions; provenance is never a tiny footnote."""
    overlay = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(overlay)
    for y in range(280):
        alpha = 245 if y <= 165 else round(245 * (280 - y) / 115)
        draw.line((0, y, W, y), fill=(10, 20, 33, alpha))
    for y in range(340):
        alpha = 240 if y <= 180 else round(240 * (340 - y) / 160)
        draw.line((0, H - 1 - y, W, H - 1 - y),
                  fill=(10, 20, 33, alpha))
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))
    label(image, (56, 30), title, 68, WHITE, True)
    label(image, (58, 124), detail, 60, CYAN)
    label(image, (56, 900), footer, 64, LIME, True)
    label(image, (58, 995), source, 60, WHITE)
    return image


def animate_hud(image, progress):
    """Editorial shot progress, not an invented performance meter."""
    draw = ImageDraw.Draw(image)
    draw.rectangle((58, 0, W - 58, 5), fill="#33475b")
    draw.rectangle((58, 0, 58 + (W - 116) * progress, 5), fill=CYAN)


def status_mark(draw, xy, passed):
    x, y = xy
    if passed:
        draw.line([(x, y + 24), (x + 17, y + 42), (x + 50, y + 2)],
                  fill=LIME, width=10)
    else:
        draw.line((x + 4, y + 4, x + 40, y + 40), fill=RED, width=9)
        draw.line((x + 40, y + 4, x + 4, y + 40), fill=RED, width=9)


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


def comparison(replay, index, phase):
    image = Image.new("RGB", (W, H), NAVY)
    for gpu, x, colour, title, value in (
        (False, 0, AMBER, "CPU · one world", replay.timing["cpu_steps_per_s"]),
        (True, 960, CYAN, "GPU · 8,192 worlds", replay.timing["top_steps_per_s"]),
    ):
        view = replay.frame(index, gpu=gpu, azimuth=110 + phase * 8,
                            elevation=-28, distance=2.5)
        # Two camera renders, cropped rather than stretched.
        image.paste(view.crop((315, 40, 1515, 1080)).resize(
            (950, 830), Image.Resampling.LANCZOS), (x + 5, 180))
        label(image, (x + 48, 198), title, 60, colour, True)
        label(image, (x + 50, 274), "1-world recording" if gpu else "Reference poses",
              60, WHITE)
        draw = ImageDraw.Draw(image)
        draw.rectangle((x + 48, 857, x + 910, 1028), fill=NAVY)
        label(image, (x + 66, 866), f"{value:,} steps/s", 60, colour, True)
        draw.rounded_rectangle((x + 66, 957, x + 880, 980), radius=10, fill="#2b3a4d")
        length = 814 * value / replay.timing["top_steps_per_s"]
        draw.rounded_rectangle((x + 66, 957, x + 66 + length, 980),
                               radius=min(10, length / 2), fill=colour)
        label(image, (x + 50, 1005), "6.25× slow", 60, WHITE)
    label(image, (48, 24), f"Same physics. {replay.timing['speedup']:.1f}× the throughput.",
          68, WHITE, True)
    label(image, (50, 124), "CPU-rendered replays · same clock", 60, CYAN)
    return image


def proof(replay, index, page, phase):
    view = replay.frame(index, azimuth=(105 if page == 0 else 230) + phase * 9,
                        distance=2.55)
    image = Image.new("RGB", (W, H), NAVY)
    image.paste(view.crop((260, 0, 1660, 1080)).resize(
        (1167, 900), Image.Resampling.LANCZOS), (753, 126))
    hud(image, "8 broken configs. All rejected.",
        "CPU reference replay · 5× slow",
        "   6/6 checks pass",
        f"CPU/GPU error: {replay.timing['parity_max_err']:.5f} < 0.05 rad")
    draw = ImageDraw.Draw(image)
    draw.rectangle((36, 230, 825, 847), fill=NAVY)
    status_mark(draw, (59, 927), True)
    for row, (name, plain) in enumerate(BROKEN[page * 4:page * 4 + 4]):
        assert replay.report["mutants"][name]["rc"] == 1
        y = 252 + row * 144
        status_mark(draw, (65, y + 19), False)
        label(image, (132, y), plain, 60, WHITE, True)
        label(image, (134, y + 69), "REJECTED", 60, RED)
    return image


def video(replay):
    cuts = SHOT_CUTS
    cut_times = ",".join(map(str, cuts))
    command = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264",
               "-threads", "1", "-crf", "0", "-preset", "ultrafast", "-pix_fmt", "yuv444p",
               "-map_metadata", "-1", "-force_key_frames", cut_times,
               "-f", "segment", "-segment_times", cut_times, "-reset_timestamps", "1",
               str(HERE / "clips/shot-%02d.mp4")]
    t = replay.timing
    end = replay.config["settle_steps"]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
        try:
            for f in range(DURATION * FPS):
                seconds = f / FPS
                if seconds < 2:
                    image = replay.frame(end, azimuth=100 + 14 * seconds, elevation=-28)
                    hud(image, f"{t['speedup']:.1f}× CPU. Physics checks out.",
                        "8,192 worlds on a GPU slice",
                        f"{t['top_steps_per_s']:,} steps/s · GPU run",
                        "CPU replay of GPU run · finished state")
                elif seconds < 12:
                    phase = seconds - 2
                    point_index = min(4, int(phase / 2))
                    p = t["points"][point_index]
                    index = round((phase % 2) / (2 - 1 / FPS) * end)
                    side = SWEEP_SIDES[point_index]
                    azimuth = (100, 205, 115, 240, 110)[point_index]
                    direction = (1, -1, 1, -1, 1)[point_index]
                    image = replay.frame(
                        index, side=side,
                        azimuth=azimuth + direction * 15 * (phase % 2),
                        elevation=(-28, -35, -40, -48, -38)[point_index],
                        perturbed=True)
                    hud(image, f"{p['nworld']:,} {'world' if p['nworld'] == 1 else 'worlds'} measured",
                        "visual replay, perturbed starts",
                        f"{p['steps_per_s']:,} steps/s · 2.5× slow",
                        "CPU render · not measured worlds")
                elif seconds < 15:
                    phase = seconds - 12
                    index = round(phase / (3 - 1 / FPS) * end)
                    image = replay.frame(index, azimuth=125 + 12 * phase,
                                         elevation=-32, studio=True)
                    hud(image, "Reach. Drop. Settle.",
                        "Config in. Verified physics out.",
                        "All eight boxes land.",
                        "CPU reference replay · 3.75× slow")
                elif seconds < 20:
                    phase = seconds - 15
                    index = round(phase / (5 - 1 / FPS) * end)
                    image = comparison(replay, index, phase)
                elif seconds < 28:
                    phase = (seconds - 20) % 4
                    index = round(phase / (4 - 1 / FPS) * end)
                    image = proof(replay, index, int((seconds - 20) / 4), phase)
                else:
                    image = replay.frame(end, azimuth=118, elevation=-28)
                    hud(image, "Run the real checks in a sandbox.",
                        "GPU run · 4 GiB RTX 5090 slice",
                        "python3 run.py --gpu",
                        "From cookbook/gpu-sim-sweep")
                if seconds < 28:
                    start = max((0,) + tuple(c for c in cuts if c <= seconds))
                    stop = next(c for c in cuts if c > seconds)
                    animate_hud(image, (seconds - start) / (stop - start))
                encoder.stdin.write(image.tobytes())
        finally:
            encoder.stdin.close()
        assert encoder.wait() == 0, "Lossless simulator clip encode failed"
    with tempfile.TemporaryDirectory(dir=HERE / "work") as temp:
        playlist = HERE / temp / "clips.txt"
        playlist.write_text("".join(
            f"file '{HERE / 'clips' / f'shot-{i:02d}.mp4'}'\n"
            for i in range(len(cuts) + 1)))
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                        "-i", str(playlist), "-c", "copy", "-map_metadata", "-1",
                        str(HERE / "master/demo.mp4")], check=True)
    print(f"MuJoCo Renderer: {replay.checked} frames; poses checked within 1e-9 "
          "against CPU reference / retained GPU / labelled visual-replay data")


def main():
    replay = Replay()
    try:
        result(replay)
        loop(replay.report)
        visual_provenance(replay)
        video(replay)
    finally:
        replay.close()


if __name__ == "__main__":
    main()
