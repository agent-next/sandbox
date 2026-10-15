"""Run INSIDE blender template: full-resolution, real Cycles turntable frames."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import bpy

DEMO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEMO / "judge"))
from artifact import read_settings
from studio import build_scene, configure


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=17)
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    args.out.mkdir(parents=True, exist_ok=True)
    scene = build_scene(read_settings(DEMO / "examples/good/scene.py"))
    configure(scene, args.seed, 1920, 1080, 8)
    rows = []
    for frame in range(1, 13):
        scene.frame_set(frame)
        name = f"frame-{frame:02}.png"
        scene.render.filepath = str(args.out / name)
        start = time.monotonic()
        bpy.ops.render.render(write_still=True)
        row = {"file": name, "frame": frame, "seconds": round(time.monotonic()-start, 3),
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
