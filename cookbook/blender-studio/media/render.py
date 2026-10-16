"""Run INSIDE blender template: full-resolution, real Cycles turntable frames."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import bpy

DEMO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEMO / "judge"))
from artifact import read_settings
from studio import build_scene, configure

POSE_COUNT = 48


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=17)
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    args.out.mkdir(parents=True, exist_ok=True)
    settings = read_settings(DEMO / "examples/good/scene.py")
    scene = build_scene(settings)
    configure(scene, args.seed, 1920, 1080, 8)
    rows = []
    for pose in range(POSE_COUNT):
        # Sample the existing animation at subframes, without changing G4.
        frame = 1 + pose * settings["period"] / POSE_COUNT
        scene.frame_set(int(frame), subframe=frame % 1)
        angle = bpy.data.objects["Turntable"].evaluated_get(
            bpy.context.evaluated_depsgraph_get()).rotation_euler.z
        if abs(angle - 2 * math.pi * pose / POSE_COUNT) > 0.00001:
            raise RuntimeError("media pose does not match the judged animation")
        name = f"frame-{pose+1:02}.png"
        scene.render.filepath = str(args.out / name)
        start = time.monotonic()
        bpy.ops.render.render(write_still=True)
        row = {"file": name, "pose": pose + 1, "frame": frame,
               "angle_radians": round(angle, 8),
               "seconds": round(time.monotonic()-start, 3),
               "sha256": hashlib.sha256((args.out / name).read_bytes()).hexdigest()}
        rows.append(row)
        print("MEDIA_FRAME " + json.dumps(row), flush=True)
        (args.out / "render.json").write_text(json.dumps(rows, indent=2) + "\n")
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out / "scene.blend"))
    bpy.data.objects["Rim"].light_linking.receiver_collection = None
    scene.render.filepath = str(args.out / "unlinked.png")
    start = time.monotonic()
    bpy.ops.render.render(write_still=True)
    rows.append({"file": "unlinked.png", "frame": 1,
                 "seconds": round(time.monotonic()-start, 3),
                 "sha256": hashlib.sha256((args.out / "unlinked.png").read_bytes()).hexdigest()})
    (args.out / "render.json").write_text(json.dumps(rows, indent=2) + "\n")
    print("MEDIA_DONE " + json.dumps(rows), flush=True)


if __name__ == "__main__":
    main()
