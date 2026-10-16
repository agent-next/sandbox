"""Record the real motion clips that the Remotion composition plays.

Every frame is rendered by mujoco.Renderer from a state the judge actually
graded: render.Replay.frame() re-checks the joint state and the graded
position/angle against the retained judge CSV before any pixel is
produced, so a clip cannot contain an invented pose. A clip never
interpolates between samples either: the source index for path position
t is round(sim_t / timestep) over the recorded samples, and each frame
names the sample it showed while encoding.

ffmpeg only encodes the pixels the renderer produced - it never composes,
captions or transitions anything. The HUD, the counting numbers and the
PASS badge are Remotion overlays drawn on top of these clips in
media/video/.

The camera is MuJoCo's own free camera, driven per frame. "The camera
moves" is renderer work, not a Ken-Burns pan on a still: the sample index
advances under the moving camera every frame.

Clips are gitignored (media/clips/); make_media.sh regenerates them.
Playback speed is stamped per clip: sim_window_s is the span of graded
simulation a clip covers and wall_s is its on-screen length, so
slowdown = wall_s / sim_window_s. Numbers shown faster or slower than
real time are labelled on screen from clips/numbers.json, which this
module writes from the judge outputs of this run.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):                      # python -I: no script dir
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from PIL import Image

import render

HERE = Path(__file__).resolve().parent
CLIPS = HERE / "clips"
DATA = HERE / "data"
FPS = 30
DT = render.SPEC["timestep_s"]

# Each clip: (name, width, height, wall seconds, graded sim window [s0, s1]).
# The pendulum runs at real time; the drop and the inclines are slowed so
# contact and the 0.8 m slide stay legible. The slow factors are stamped.
PLAN = [
    ("01_hook", 1920, 1080, 2.0, ("pendulum", 0.0, 2.0)),
    ("02_drop", 1280, 720, 2.5, ("drop", 0.0, 1.5)),
    ("03_slide", 1280, 720, 2.5, ("incline_slide", 0.0, 1.0)),
    ("04_stick", 1280, 720, 2.5, ("incline_stick", 0.0, 1.0)),
    ("05_pendulum", 1280, 720, 2.5, ("pendulum", 2.0, 4.5)),
    ("08_closeup", 1920, 1080, 2.0, None),          # two half-shots below
    ("09_proof", 1920, 1080, 6.5, ("pendulum", 4.5, 11.0)),
]
QUAD = ("06_quad", 1920, 1080, 9.0)                 # 2x2 of all four scenes

# Free-camera paths per scene: (azimuth, elevation, distance) at t=0 and t=1.
CAMS = {
    "pendulum": ((60, -12, 2.0), (105, -7, 1.7)),
    "drop": ((110, -14, 2.2), (180, -8, 1.6)),
    "incline_slide": ((100, -12, 1.9), (170, -6, 1.3)),
    "incline_stick": ((100, -12, 1.9), (170, -6, 1.3)),
}
LOOKAT = {"pendulum": (0, 0, 1.48), "drop": (0, 0, 0.48),
          "incline_slide": (0.35, 0, -0.13), "incline_stick": (0, 0, 0.03)}


def sample(replay, sim_t):
    """The graded sample index at simulation time sim_t (never a blend)."""
    i = int(round(sim_t / DT))
    return max(0, min(len(replay.states) - 1, i))


def aim(replay, scene, t, lookat=None):
    a0, e0, d0 = CAMS[scene][0]
    a1, e1, d1 = CAMS[scene][1]
    replay.camera.azimuth = a0 + (a1 - a0) * t
    replay.camera.elevation = e0 + (e1 - e0) * t
    replay.camera.distance = d0 + (d1 - d0) * t
    replay.camera.lookat[:] = lookat if lookat is not None else LOOKAT[scene]


def encode(name, width, height, frames, produce):
    """Pipe renderer output straight into a lossless x264 intermediate."""
    out = CLIPS / f"{name}.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt",
           "rgb24", "-s", f"{width}x{height}", "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "libx264", "-threads", "2", "-crf", "0",
           "-preset", "veryfast", "-pix_fmt", "yuv444p", "-map_metadata",
           "-1", str(out)]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as proc:
        for i in range(frames):
            proc.stdin.write(produce(i / max(frames - 1, 1)).convert("RGB").tobytes())
        proc.stdin.close()
        assert proc.wait() == 0, f"ffmpeg failed for {name}"
    print(f"clip {name}: {frames} frames at {width}x{height}", flush=True)
    return out


def scene_clip(name, width, height, wall_s, scene, s0, s1, replays):
    replay = replays[scene]
    frames = round(wall_s * FPS)

    def produce(t):
        sim_t = s0 + (s1 - s0) * t
        aim(replay, scene, t)
        return replay.frame(sample(replay, sim_t), width, height)

    encode(name, width, height, frames, produce)
    return {"wall_s": wall_s, "sim_s": s1 - s0,
            "slowdown": round(wall_s / (s1 - s0), 2)}


def quad_clip(name, width, height, wall_s, replays, tiles):
    """2x2 grid, every tile moving: each scene orbits inside its own tile."""
    frames = round(wall_s * FPS)
    tw, th = width // 2, height // 2
    spans = {sc: (0.0, min(render.SCENES[sc]["duration_s"], wall_s))
             for sc in tiles}

    def produce(t):
        image = Image.new("RGB", (width, height))
        for k, sc in enumerate(tiles):
            replay = replays[sc]
            s0, s1 = spans[sc]
            sim_t = s0 + (s1 - s0) * t
            aim(replay, sc, t)
            tile = replay.frame(sample(replay, sim_t), tw, th)
            image.paste(tile, (tw * (k % 2), th * (k // 2)))
        return image

    encode(name, width, height, frames, produce)


def closeup_clip(name, width, height, wall_s, replays):
    """Two half-length close-ups with a hard cut between them: the sliding
    box tracked by its own graded x, then a push-in on the pendulum bob."""
    frames = round(wall_s * FPS)
    slide, pend = replays["incline_slide"], replays["pendulum"]

    def produce(t):
        if t < 0.5:
            u = t / 0.5
            sim_t = u * 1.0                       # full graded slide, 2x slow
            i = sample(slide, sim_t)
            x = slide.rows["x"][i]
            aim(slide, "incline_slide", u,
                lookat=(x * 0.9 + 0.05, 0, -0.10))
            slide.camera.distance = 0.85
            return slide.frame(i, width, height)
        u = (t - 0.5) / 0.5
        sim_t = 4.5 + u * 2.0                     # graded swing, real time
        i = sample(pend, sim_t)
        aim(pend, "pendulum", u, lookat=(0.35, 0, 1.30))
        pend.camera.distance = 1.1
        return pend.frame(i, width, height)

    encode(name, width, height, frames, produce)
    return {"wall_s": wall_s, "sim_s": 3.0, "slowdown": 0.67}


def receipt_run():
    """The recorded fresh-sandbox run (RECEIPT.md, run 2): its stage list
    and total, parsed from the committed receipt so they cannot drift."""
    text = (HERE.parent / "RECEIPT.md").read_text()
    block = text.split("## Fresh-sandbox run 2", 1)[1].split("\n## ", 1)[0]
    stages = [(k, int(v)) for k, v in re.findall(
        r"\[(\w+)\]\s.*\((\d+) s\)", block)]
    total = int(re.search(r"^total: (\d+) s$", block, re.M).group(1))
    got = sum(s for _, s in stages)
    assert stages and got <= total <= got + 4, (
        f"RECEIPT.md run 2 stages sum to {got} s, total says {total} s")
    return [{"stage": name, "s": s} for name, s in stages], total


def numbers(speeds):
    """Every on-screen number, from this run's judge outputs or RECEIPT.md."""
    verdict = render.VERDICT
    oracle = render.ORACLE
    stages, receipt_run_s = receipt_run()
    terminal_slot_s = 4.0

    def row(key, title, unit, metric_name, err_name=None):
        """One row: the value the judge measured, its spec oracle, and the
        percentage the judge itself printed (err relative to the measured
        value, exactly as _grade.py computes it)."""
        metric = verdict["scenarios"][key]["oracle"]
        value = metric[metric_name]
        err = metric.get(err_name)
        return {
            "key": key, "title": title, "unit": unit,
            "value": round(value, 4),
            "oracle": (None if metric_name not in oracle[key]
                       else round(oracle[key][metric_name], 4)),
            "err_pct": None if err is None else round(err * 100, 2),
            "pass": metric["pass"],
        }

    scenes = [
        row("drop", "01 DROP", "s", "t_contact", "t_contact_err"),
        row("incline_slide", "02 SLIDE 35", "m/s2", "accel", "accel_err"),
        row("incline_stick", "03 STICK 20", "mm", "travel_m"),
        row("pendulum", "04 PENDULUM", "s", "period", "period_err"),
    ]
    stick = verdict["scenarios"]["incline_stick"]["oracle"]
    scenes[2]["value"] = round(stick["travel_m"] * 1000, 1)  # mm
    scenes[2]["oracle"] = 0.0
    # The stick gate is a travel threshold, not an error bound: read the
    # judge's own constant so the number on screen cannot drift from it.
    grade_src = (HERE.parent / "judge" / "_grade.py").read_text()
    scenes[2]["limit_mm"] = round(float(re.search(
        r"^STICK_TRAVEL_M = ([\d.]+)", grade_src, re.M).group(1)) * 1000, 1)
    loop = json.loads((HERE.parent / "examples/good/loop.json").read_text())
    import collect
    mutants = collect.read_selftest(DATA / "selftest.txt")
    return {
        "scenes": scenes,
        "kill_rate": f"{len(mutants)}/{len(mutants)}",
        "killed": len(mutants),
        "mutants": [{"name": n, "gates": g.split(",")}
                    for n, g in mutants],
        "loop": [{"i": it["iteration"], "passed": it["passed"],
                  "failed": it.get("failed_gates", []),
                  "change": it["change"].split(":")[0]}
                 for it in loop["iterations"]],
        "speeds": speeds,
        "agent_run": {"receipt_total_s": receipt_run_s,
                      "slot_s": terminal_slot_s,
                      "factor": round(receipt_run_s / terminal_slot_s, 1),
                      "stages": stages},
        "timestep_s": DT,
        "seed": verdict["seed"],
        "mujoco": __import__("mujoco").__version__,
    }


def speed_table():
    """The playback speed of every clip, without rendering anything."""
    speeds = {}
    for name, w, h, wall_s, window in PLAN:
        if window is None:
            speeds[name] = {"wall_s": wall_s, "sim_s": 3.0, "slowdown": 0.67}
            continue
        scene, s0, s1 = window
        speeds[name] = {"wall_s": wall_s, "sim_s": s1 - s0,
                        "slowdown": round(wall_s / (s1 - s0), 2)}
    span = min(render.SCENES["drop"]["duration_s"], QUAD[3])
    speeds[QUAD[0]] = {"wall_s": QUAD[3], "sim_s": span,
                       "slowdown": round(QUAD[3] / span, 2)}
    return speeds


def main():
    CLIPS.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "--quad":
        # The 2x2 grid needs a process of its own: once a Renderer has
        # switched size, OSMesa leaves every other renderer reading the
        # last-created context's pixels, so interleaving four tiles in the
        # same process that recorded the 720p/1080p clips freezes three of
        # them. In a fresh process the tiles are created directly at their
        # own size and every frame renders.
        replays = {name: render.Replay(name, offsamples="0", shadowsize="1024",
                                       xml_prefix="clip")
                   for name in render.SCENES}
        quad_clip(*QUAD, replays,
                  ("drop", "incline_slide", "incline_stick", "pendulum"))
        for replay in replays.values():
            replay.close()
        return

    replays = {name: render.Replay(name, offsamples="0", shadowsize="1024",
                                   xml_prefix="clip")
               for name in render.SCENES}
    graded = sum(len(r.states) for r in replays.values())
    print(f"clips: {graded} graded samples available", flush=True)

    for name, w, h, wall_s, window in PLAN:
        if window is None:
            closeup_clip(name, w, h, wall_s, replays)
            continue
        scene_clip(name, w, h, wall_s, *window, replays)

    for replay in replays.values():
        replay.close()
    subprocess.run([sys.executable, "-I", str(Path(__file__).resolve()),
                    "--quad"], check=True)
    write_numbers()


def write_numbers():
    (CLIPS / "numbers.json").write_text(
        json.dumps(numbers(speed_table()), indent=2))
    print("clips/numbers.json written from this run's judge output", flush=True)


if __name__ == "__main__":
    main()
