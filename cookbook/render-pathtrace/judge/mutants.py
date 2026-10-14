"""Single-edit, hand-auditable bad inputs."""

import copy
import json
from pathlib import Path


def generate(good, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    result = []
    for name in ("energy_gain", "hidden_emission", "clipping", "one_sample",
                 "inside_sphere", "nan_material", "resolution"):
        scene = copy.deepcopy(good)
        if name == "energy_gain":
            scene["materials"]["clay"]["baseColor"] = [1.6, 1.6, 1.6]
        elif name == "hidden_emission":
            scene["materials"]["floor"]["emissionLuminance"] = 2
        elif name == "clipping":
            scene["lights"][0]["intensity"] *= 100
        elif name == "one_sample":
            scene["spp"] = 1
        elif name == "inside_sphere":
            scene["camera"]["position"] = scene["spheres"][0]["position"].copy()
        elif name == "nan_material":
            scene["materials"]["clay"]["specularRoughness"] = float("nan")
        else:
            scene["resolution"] = [512, 512]
        path = directory / f"{name}.json"
        path.write_text(json.dumps(scene) + "\n")
        result.append((name, path))
    return result
