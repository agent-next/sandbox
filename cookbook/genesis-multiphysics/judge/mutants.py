#!/usr/bin/env python3
"""Regenerate examples/bad/* as single-edit mutants of examples/good.

Each mutant rewrites one constant in the SCENARIO dict, producing a case
that must fail at least one judge gate (see SPEC.md "Known-bad mutants").
"""

import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
GOOD = BASE / "examples" / "good" / "scenario.py"
BAD = BASE / "examples" / "bad"


def mutate(text: str, key: str, new_value) -> str:
    """Replace a single top-level SCENARIO entry `"key": <value>,`."""
    pat = re.compile(rf'^\s*"{re.escape(key)}":\s*[^,]+,', re.MULTILINE)
    new, n = pat.subn(f'    "{key}": {new_value},', text, count=1)
    if n != 1:
        raise SystemExit(f"mutants.py: could not mutate key {key!r}")
    return new


def main():
    src = GOOD.read_text()
    BAD.mkdir(parents=True, exist_ok=True)

    mutants = {
        # gravity points up: free-fall fit is a=+9.81 but ballistic window
        # never brings it back down; gates 3 & 5 fail.
        "gravity_flipped": mutate(src, "gravity", "+9.81"),
        # gravity typo'd to zero: no fall, column never collapses; gates 3 & 5.
        "gravity_off": mutate(src, "gravity", "0.0"),
        # one big substep: MPM unstable at dt 2e-3 on this grid; gate 1 or 3.
        "dt_blowup": mutate(mutate(src, "dt", "2e-3"), "substeps", "1"),
        # peg removed (shrunk to a millimetre cube at floor level): the
        # column lands flat; the spread radius no longer matches the
        # wrapped-heap range; gate 5.
        "no_obstacle": mutate(
            mutate(src, "obstacle_size", "[0.001, 0.001, 0.001]"),
            "obstacle_pos", "[0.40, 0.40, 0.0005]"),
        # short run: still moving / not collapsed at the end; gate 5.
        "too_few_steps": mutate(src, "steps", "350"),
        # nearly rigid bouncy chunks, no yielding; gate 5.
        "wrong_material": mutate(
            mutate(src, "E", "1e8"), "yield_stress", "1e6"),
    }

    for name, text in mutants.items():
        d = BAD / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "scenario.py").write_text(text)
        print(f"[mutants] wrote examples/bad/{name}/scenario.py")


if __name__ == "__main__":
    main()
