"""Each mutant changes exactly one literal setting."""
import ast
from pathlib import Path

MUTANTS = {
    "unlinked_rim": ("rim_link", False),
    "wrong_period": ("period", 13),
    "off_center": ("hero_x", 1.6),
    "overexposed": ("exposure", 8.0),
    "clipped_hero": ("camera_y", -2.0),
    "visible_seam": ("seam_height", 2.6),
    "high_seam": ("seam_height", 3.4),
    "orbiting_hero": ("hero_x", 0.6),
    "unlinked_halo": ("halo_link", False),
}


def generate(good, destination):
    paths = {}
    for name, (key, value) in MUTANTS.items():
        tree = ast.parse(Path(good).read_text())
        assign = next(node for node in tree.body if isinstance(node, ast.Assign))
        index = next(i for i, node in enumerate(assign.value.keys) if node.value == key)
        assign.value.values[index] = ast.Constant(value=value)
        path = destination / f"{name}.py"
        path.write_text(ast.unparse(tree) + "\n")
        paths[name] = path
    return paths
