"""Trusted Blender process: real pixels, projected evaluated mesh, actual driver."""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio import build_scene, configure


def render(scene, path):
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(str(path), check_existing=False)
    pixels = np.array(image.pixels[:], dtype=np.float64).reshape(
        image.size[1], image.size[0], 4)[:, :, :3]
    # Loaded PNG buffer is display-referred RGB, matching its encoded preview.
    bpy.data.images.remove(image)
    return pixels


def geometry(scene):
    graph = bpy.context.evaluated_depsgraph_get()
    obj = bpy.data.objects["Hero"].evaluated_get(graph)
    points = [world_to_camera_view(scene, scene.camera, obj.matrix_world @ v.co)
              for v in obj.data.vertices]
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    area = (high[0] - low[0]) * (high[1] - low[1])
    center = [(low[i] + high[i]) / 2 for i in range(2)]
    inside = (low[0] >= 0.04 and high[0] <= 0.96 and low[1] >= 0.04
              and high[1] <= 0.96 and low[2] > scene.camera.data.clip_start)
    return {"pass": bool(0.07 <= area <= 0.22 and
                        abs(center[0] - 0.5) <= 0.055 and
                        abs(center[1] - 0.5) <= 0.12 and inside),
            "bbox_fraction": round(area, 6), "center": [round(v, 6) for v in center],
            "inside_margin": inside}


def backdrop_mask(scene, width, height, region=None):
    """Independent primary-ray visibility, not artifact labels or object indices."""
    graph = bpy.context.evaluated_depsgraph_get()
    camera = scene.camera
    corners = camera.data.view_frame(scene=scene)
    xs = [p.x / -p.z for p in corners]
    ys = [p.y / -p.z for p in corners]
    rotation = camera.matrix_world.to_3x3()
    mask = np.zeros((height, width), dtype=bool)
    for y in range(height):
        for x in range(width):
            if region is not None and not region[y, x]:
                continue
            direction = rotation @ Vector((
                min(xs) + (max(xs) - min(xs)) * (x + 0.5) / width,
                min(ys) + (max(ys) - min(ys)) * (y + 0.5) / height, -1))
            hit, _, _, _, obj, _ = scene.ray_cast(
                graph, camera.matrix_world.translation, direction.normalized())
            mask[y, x] = hit and obj.name == "Cyclorama"
    return mask


def grade(settings, seed, out):
    scene = build_scene(settings)
    configure(scene, seed)
    scene.frame_set(1)
    gates = {"G1_framing": geometry(scene)}
    hero = render(scene, out / "hero.png")
    lum = hero @ np.array([0.2126, 0.7152, 0.0722])
    mean = float(lum.mean())
    clipped = float(np.mean(np.any(hero >= 253 / 255, axis=2)))
    gates["G2_exposure"] = {"pass": bool(0.15 <= mean <= 0.65 and clipped <= 0.005),
                            "mean_display_luminance": round(mean, 6),
                            "clipped_fraction": round(clipped, 6)}
    # Side strips avoid cast shadows/products; vertical differences detect a sweep seam.
    strips = np.zeros((144, 256), dtype=bool)
    strips[78:134, 8:48] = True
    strips[78:134, 208:248] = True
    mask = backdrop_mask(scene, 256, 144, strips)
    valid = (mask[2:] & mask[1:-1] & mask[:-2] &
             strips[2:] & strips[1:-1] & strips[:-2])
    second = np.abs(lum[2:] - 2 * lum[1:-1] + lum[:-2])
    seam = float(second[valid].max()) if valid.any() else 1.0
    visible = float(mask[strips].mean())
    gates["G3_backdrop"] = {"pass": bool(visible >= 0.995 and
                                        valid.sum() >= 4000 and seam <= 0.055),
                            "max_second_difference": round(seam, 6),
                            "backdrop_visibility_fraction": round(visible, 6),
                            "verified_pixels": int(valid.sum())}
    angles = []
    for frame in range(1, 14):
        scene.frame_set(frame)
        angles.append(float(bpy.data.objects["Turntable"].rotation_euler.z))
    errors = [abs((b - a) - 2 * math.pi / 12) for a, b in zip(angles, angles[1:])]
    # Compare rendered endpoint against frame 1 at the same resolution and sample seed.
    endpoint = render(scene, out / "endpoint.png")
    diff = float(np.abs(hero - endpoint).mean())
    gates["G4_loop"] = {"pass": bool(max(errors) <= 1e-5 and diff <= 0.003),
                        "max_step_error_radians": round(max(errors), 8),
                        "endpoint_mean_abs_diff": round(diff, 6),
                        "frames": 12}
    scene.frame_set(1)
    rim, halo = bpy.data.objects["Rim"], bpy.data.objects["Halo"]
    rim_names = sorted(o.name for o in rim.light_linking.receiver_collection.objects
                       ) if rim.light_linking.receiver_collection else []
    halo_names = sorted(o.name for o in halo.light_linking.receiver_collection.objects
                        ) if halo.light_linking.receiver_collection else []
    # Isolate DIRECT rim contribution. Indirect product bounce is not forbidden by linking.
    for obj in bpy.data.objects:
        if obj.type == "LIGHT" and obj != rim:
            obj.data.energy = 0
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0
    configure(scene, seed, 128, 72, 4)
    scene.cycles.max_bounces = 0
    scene.cycles.use_denoising = False
    scene.view_settings.exposure = 0
    linked = render(scene, out / "rim-on.png")
    rim.data.energy = 0
    dark = render(scene, out / "rim-off.png")
    mask = backdrop_mask(scene, 128, 72)
    difference = np.abs(linked - dark).mean(axis=2)
    delta = float(difference[mask].mean()) if mask.any() else 1
    signal = float(difference[~mask].mean()) if (~mask).any() else 0
    gates["G5_linking"] = {
        "pass": bool(delta <= 0.001 and signal >= 0.001 and
                     rim_names == ["GlassOrb", "GoldRing", "Hero", "Plinth"] and
                     halo_names == ["Cyclorama"]),
        "backdrop_direct_delta": round(delta, 6),
        "product_direct_delta": round(signal, 6),
        "rim_receivers": rim_names, "halo_receivers": halo_names}
    return {"gates": gates, "pass": all(g["pass"] for g in gates.values()),
            "seed": seed, "blender": bpy.app.version_string,
            "render": {"engine": "CYCLES", "device": "CPU", "threads": 4,
                       "resolution": [256, 144], "samples": 8}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("settings", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--seed", type=int, required=True)
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    args.out.mkdir(parents=True, exist_ok=True)
    verdict = grade(json.loads(args.settings.read_text()), args.seed, args.out)
    (args.out / "measure.json").write_text(json.dumps(verdict, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
