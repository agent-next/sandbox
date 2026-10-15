#!/usr/bin/env python3
"""Write known-bad single-edit mutants of a good design.json.

Usage: mutants.py <good design.json> <out dir>

Each mutant is one plausible modelling mistake an agent could make; the
self-test requires the judge to reject every one of them.
"""

from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path


def circles(cmds: list, diameter: float) -> list[dict]:
    return [c for c in cmds if c["command"] == "sketch.circle.center"
            and math.isclose(c["params"].get("diameter", -1), diameter)]


def param(cmds: list, name: str) -> dict:
    return next(c for c in cmds if c["command"] == "parameters.change" and c["params"]["name"] == name)


def bolt_holes(cmds):
    return circles(cmds, 3.4)


def hole_small(cmds):
    for c in bolt_holes(cmds):
        c["params"]["diameter"] = 3.1


def hole_off_pcd(cmds):
    c = bolt_holes(cmds)[0]["params"]
    c["center"] = [c["center"][0] + 0.2, c["center"][1] + 0.2]


def hole_rotated(cmds):
    c = bolt_holes(cmds)[0]["params"]
    r, a = math.hypot(*c["center"]), math.atan2(c["center"][1], c["center"][0]) + math.radians(3)
    c["center"] = [r * math.cos(a), r * math.sin(a)]


def hole_missing(cmds):
    cmds.remove(bolt_holes(cmds)[-1])


def hole_extra(cmds):
    i = cmds.index(bolt_holes(cmds)[-1])
    cmds.insert(i + 1, {"command": "sketch.circle.center", "params": {"center": [0, 17.5], "diameter": 3.4}})


def bore_missing(cmds):
    cmds.remove(circles(cmds, 22)[0])  # the plate sketch's bore; the boss keeps its own


def too_thick(cmds):
    param(cmds, "thickness")["params"]["expression"] = "7.5 mm"


def boss_height(cmds):
    param(cmds, "boss_height")["params"]["expression"] = "4 mm"


def no_fillet(cmds):
    c = next(c for c in cmds if c["command"] == "sketch.rectangle.rounded")
    c["command"] = "sketch.rectangle.two_point"
    del c["params"]["radius"]


def literal_thickness(cmds):
    for c in cmds:
        if c["command"] == "solid.extrude" and c["params"].get("distance") == "thickness":
            c["params"]["distance"] = "6 mm"
        if c["command"] == "sketch.create" and c["params"].get("offset") == "thickness":
            c["params"]["offset"] = "6 mm"


def broken_command(cmds):
    next(c for c in cmds if c["command"] == "solid.extrude")["command"] = "solid.extrudee"


def file_export(cmds):
    cmds.append({"command": "file.export", "params": {"path": "../../escape.step"}})


MUTANTS = [hole_small, hole_off_pcd, hole_rotated, hole_missing, hole_extra, bore_missing,
           too_thick, boss_height, no_fillet, literal_thickness, broken_command, file_export]


def main() -> int:
    good = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for fn in MUTANTS:
        d = copy.deepcopy(good)
        fn(d["commands"])
        if d == good:
            print(f"mutants: {fn.__name__} made no change", file=sys.stderr)
            return 1
        (out / f"{fn.__name__}.json").write_text(json.dumps(d, indent=1) + "\n")
        print(f"mutants: wrote {fn.__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
