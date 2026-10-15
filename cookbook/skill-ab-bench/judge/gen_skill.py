#!/usr/bin/env python3
"""Build the two skill packages the bench puts on the desk.

The skill arm reads a real package (`examples/good/skill/`, checked in); the
placebo arm reads a package that *looks* like one but adds no technique; the
no-skill arm gets an empty desk.  So the three packages differ in exactly one
way: what is on the desk.

Recipe (deterministic, no RNG):

  * `skill/` is copied byte for byte from `examples/good/skill/`;
  * `noskill/` is created empty;
  * `placebo/` is the real package with `SKILL.md` and `reference.py`
    replaced by `README.md`, whose single rule ("skip commented-out lines")
    is a plausible tip that changes exactly one task's answer.

`judge/bench.py` calls `build()`; the directories land in the bench's scratch
tree, so a stale copy can never be graded by accident.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

JDIR = Path(__file__).resolve().parent
DEMO = JDIR.parent
REAL_SKILL = DEMO / "examples" / "good" / "skill"

# The placebo's whole technique.  It is deliberately one rule long: the bench
# must be unable to crown it, and a rule that changes nothing at all would
# make that trivial.  This one changes exactly one task (kv05).
PLACEBO_README = """\
# regex-cookbook (README only)

A short guide to reading values out of config files.

## The one rule

**Skip commented-out lines.** A line whose first non-blank character is `#`
or `;` is a comment, not an assignment. Ignore it and read the value from the
first remaining matching line.

That is the whole technique: look for `key = value`, take the first match,
and remember that a commented-out line does not count.

There are no snippets here, and no worked examples -- read your own code
carefully and it should be fine.
"""

# Files the placebo keeps from the real package: none of them carry technique.
PLACEBO_DROPS = ("SKILL.md", "reference.py")


def build(dest_root: str | Path) -> dict[str, Path]:
    """Write `skill/`, `noskill/` and `placebo/` under `dest_root`.

    `noskill/` is created **empty** on purpose: the no-skill arm's whole
    definition is that no package is on the desk, and an empty directory
    makes that checkable (`arm_runner.py` refuses to answer if it finds
    anything in there).
    """
    root = Path(dest_root)
    skill = root / "skill"
    noskill = root / "noskill"
    placebo = root / "placebo"

    for path in (skill, noskill, placebo):
        if path.exists():
            shutil.rmtree(path)

    shutil.copytree(REAL_SKILL, skill)

    noskill.mkdir(parents=True)

    shutil.copytree(REAL_SKILL, placebo)
    for name in PLACEBO_DROPS:
        (placebo / name).unlink()
    (placebo / "README.md").write_text(PLACEBO_README, encoding="utf-8")

    # Invariants: the packages must differ, the placebo must carry no code,
    # and the no-skill desk must be genuinely empty.
    if (skill / "reference.py").read_bytes() == (placebo / "README.md").read_bytes():
        raise SystemExit("gen_skill: placebo content equals the skill package")
    if list(placebo.glob("*.py")):
        raise SystemExit(f"gen_skill: placebo still has code: "
                         f"{[p.name for p in placebo.glob('*.py')]}")
    if not (placebo / "README.md").is_file():
        raise SystemExit("gen_skill: placebo has no README.md")
    if any(noskill.iterdir()):
        raise SystemExit("gen_skill: noskill desk is not empty")
    return {"skill": skill, "noskill": noskill, "placebo": placebo}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: gen_skill.py <dest_root>", file=sys.stderr)
        return 2
    paths = build(sys.argv[1])
    for arm, path in sorted(paths.items()):
        files = sorted(p.name for p in path.iterdir())
        print(f"gen_skill: {arm} -> {path} ({', '.join(files)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
