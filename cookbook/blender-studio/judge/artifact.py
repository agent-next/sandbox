"""Parse, never execute, the restricted scene script."""
import ast
import math
from pathlib import Path

SKELETON = '''from studio import build_scene
SETTINGS = {}
build_scene(SETTINGS)
'''
BOUNDS = {"hero_x": (-5, 5), "camera_y": (-20, -1),
          "key_energy": (0, 1000000), "period": (2, 120),
          "seam_height": (0, 8), "exposure": (-10, 10)}


def read_settings(path):
    text = Path(path).read_text()
    if len(text) > 16384:
        raise ValueError("scene script exceeds 16 KiB")
    tree = ast.parse(text)
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(
            tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
        tree.body.pop(0)
    if len(tree.body) != 3 or not isinstance(tree.body[1], ast.Assign):
        raise ValueError("expected the documented scene script skeleton")
    value = tree.body[1].value
    if not isinstance(value, ast.Dict) or len(value.keys) != 8:
        raise ValueError("expected eight unique settings")
    settings = ast.literal_eval(value)
    tree.body[1].value = ast.Dict(keys=[], values=[])
    if ast.dump(tree, include_attributes=False) != ast.dump(
            ast.parse(SKELETON), include_attributes=False):
        raise ValueError("executable edits are forbidden; change SETTINGS only")
    if set(settings) != set(BOUNDS) | {"rim_link", "halo_link"}:
        raise ValueError("unknown, missing, or duplicate settings")
    for name, (lo, hi) in BOUNDS.items():
        v = settings[name]
        if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"{name} outside [{lo}, {hi}]")
    if type(settings["period"]) is not int:
        raise ValueError("period must be an integer")
    for name in ("rim_link", "halo_link"):
        if type(settings[name]) is not bool:
            raise ValueError(f"{name} must be bool")
    return settings
