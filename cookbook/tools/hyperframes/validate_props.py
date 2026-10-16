#!/usr/bin/env python3
"""Validate a demo-video props file against the HyperFrames template's shape.

    python3 validate_props.py props.json [...]

Pure Python 3.10+ standard library: no node, no ffmpeg, no network. This is
what CI runs, so a props file can never drift from the shape `index.html`
expects.

The shape (props.example.json is a worked example):

    headline   string, required, non-empty
    launch     {command, ask_agent}, required, no extra keys
    verdict    {pass, gates[]}, required; each gate is
               {name, measured, threshold}, no extra keys
    shots      array, required, 1..12 entries; each shot is
               {clip, duration, start?, speed?, hud?}:
                 clip      relative path to an .mp4 in the same media tree,
                           or the literal "model" for the 3D turntable shot
                 duration  1..20 seconds
                 start     optional, must equal the running shot cursor
                 speed     optional, 1..10
                 hud       optional, at most 2 rows of {label, value, unit?}
    model3d    optional {glb}; required if and only if a shot uses "model"

Rejections worth naming: an image clip (.png/.jpg) is refused because a still
is not footage, and an unknown key anywhere is refused rather than silently
ignored. Both are the failures that reach a render as a slide deck.
"""

from __future__ import annotations

import json
import re
import sys

# --- shape constants (the single source of truth; tests import this module) --

TOP_KEYS = {"shots", "model3d", "verdict", "headline", "launch"}
SHOT_KEYS = {"clip", "start", "duration", "speed", "hud"}
HUD_KEYS = {"label", "value", "unit"}
GATE_KEYS = {"name", "measured", "threshold"}
LAUNCH_KEYS = {"command", "ask_agent"}
MODEL_KEYS = {"glb"}

MAX_SHOTS = 12
MIN_SHOT_S = 1.0
MAX_SHOT_S = 20.0
MAX_SHOT_DURATION_TOTAL_S = 90.0
MIN_SPEED = 1.0
MAX_SPEED = 10.0
MAX_HUD_PER_SHOT = 2
START_TOLERANCE_S = 0.001  # a start must match the running cursor this closely

MODEL_SENTINEL = "model"
VIDEO_SUFFIX = ".mp4"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff")

# A path that could escape the demo's media tree, or name a host.
ABSOLUTE_OR_URL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|/|\\\\)")


class PropsError(Exception):
    """A props file does not match the template's shape."""


def _is_number(value) -> bool:
    # bool is an int subclass; a boolean where a number belongs is a bug.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_object(value, where: str) -> dict:
    if not isinstance(value, dict):
        raise PropsError(f"{where}: must be an object, got {type(value).__name__}")
    return value


def _require_keys(
    obj: dict, allowed: set[str], required: set[str], where: str
) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise PropsError(
            f"{where}: unknown key(s) {unknown}; allowed keys are "
            f"{sorted(allowed)}"
        )
    missing = sorted(required - set(obj))
    if missing:
        raise PropsError(f"{where}: missing required key(s) {missing}")


def _require_string(value, where: str) -> str:
    if not isinstance(value, str):
        raise PropsError(f"{where}: must be a string, got {type(value).__name__}")
    if not value.strip():
        raise PropsError(f"{where}: must not be empty")
    return value


def _require_number(value, where: str, low: float, high: float) -> float:
    if not _is_number(value):
        raise PropsError(f"{where}: must be a number, got {type(value).__name__}")
    number = float(value)
    if number < low or number > high:
        raise PropsError(f"{where}: {number:g} is outside {low:g}..{high:g}")
    return number


def validate_clip_path(clip: str, where: str) -> None:
    """Reject stills, absolute paths, URLs and anything that is not an mp4."""
    lowered = clip.lower()
    if lowered.endswith(IMAGE_SUFFIXES):
        raise PropsError(
            f"{where}: clip {clip!r} is an image; the template plays footage, "
            "not stills — supply an .mp4"
        )
    if ABSOLUTE_OR_URL.match(clip):
        raise PropsError(
            f"{where}: clip {clip!r} must be a path relative to the media tree, "
            "not an absolute path or a URL"
        )
    if not lowered.endswith(VIDEO_SUFFIX):
        raise PropsError(
            f"{where}: clip {clip!r} must be an {VIDEO_SUFFIX} file (or the "
            f"literal {MODEL_SENTINEL!r} for the 3D shot)"
        )


def validate_hud(hud, where: str) -> None:
    if not isinstance(hud, list):
        raise PropsError(f"{where}: hud must be an array")
    if len(hud) > MAX_HUD_PER_SHOT:
        raise PropsError(
            f"{where}: {len(hud)} HUD rows; at most {MAX_HUD_PER_SHOT} fit on "
            "the panel"
        )
    for i, row in enumerate(hud):
        at = f"{where}[{i}]"
        row = _require_object(row, at)
        _require_keys(row, HUD_KEYS, {"label", "value"}, at)
        _require_string(row["label"], f"{at}.label")
        if not (_is_number(row["value"]) or isinstance(row["value"], str)):
            raise PropsError(f"{at}.value: must be a number or a string")
        if "unit" in row:
            _require_string(row["unit"], f"{at}.unit")


def validate_gate(gate, where: str) -> None:
    gate = _require_object(gate, where)
    _require_keys(gate, GATE_KEYS, GATE_KEYS, where)
    _require_string(gate["name"], f"{where}.name")
    for key in ("measured", "threshold"):
        value = gate[key]
        if not (_is_number(value) or isinstance(value, str)):
            raise PropsError(f"{where}.{key}: must be a number or a string")
        if isinstance(value, str) and not value.strip():
            raise PropsError(f"{where}.{key}: must not be empty")


def validate(props: dict) -> dict:
    """Validate a parsed props document and return it unchanged.

    Raises PropsError on the first problem, with the JSON path in the message.
    """
    props = _require_object(props, "props")
    _require_keys(props, TOP_KEYS, {"shots", "verdict", "headline", "launch"}, "props")

    _require_string(props["headline"], "props.headline")

    launch = _require_object(props["launch"], "props.launch")
    _require_keys(launch, LAUNCH_KEYS, LAUNCH_KEYS, "props.launch")
    _require_string(launch["command"], "props.launch.command")
    _require_string(launch["ask_agent"], "props.launch.ask_agent")

    verdict = _require_object(props["verdict"], "props.verdict")
    _require_keys(verdict, {"pass", "gates"}, {"pass", "gates"}, "props.verdict")
    if not isinstance(verdict["pass"], bool):
        raise PropsError("props.verdict.pass: must be a boolean")
    if not isinstance(verdict["gates"], list):
        raise PropsError("props.verdict.gates: must be an array")
    if not verdict["gates"]:
        raise PropsError("props.verdict.gates: must have at least one gate")
    for i, gate in enumerate(verdict["gates"]):
        validate_gate(gate, f"props.verdict.gates[{i}]")

    if "model3d" in props:
        model = _require_object(props["model3d"], "props.model3d")
        _require_keys(model, MODEL_KEYS, MODEL_KEYS, "props.model3d")
        _require_string(model["glb"], "props.model3d.glb")
        if not model["glb"].lower().endswith(".glb"):
            raise PropsError(
                f"props.model3d.glb: {model['glb']!r} must be a .glb file"
            )

    shots = props["shots"]
    if not isinstance(shots, list):
        raise PropsError("props.shots: must be an array")
    if not shots:
        raise PropsError("props.shots: must have at least one shot")
    if len(shots) > MAX_SHOTS:
        raise PropsError(
            f"props.shots: {len(shots)} shots; the template takes at most "
            f"{MAX_SHOTS}"
        )

    cursor = 0.0
    uses_model = False
    total = 0.0
    for i, shot in enumerate(shots):
        where = f"props.shots[{i}]"
        shot = _require_object(shot, where)
        _require_keys(shot, SHOT_KEYS, {"clip", "duration"}, where)

        clip = _require_string(shot["clip"], f"{where}.clip")
        if clip != MODEL_SENTINEL:
            validate_clip_path(clip, f"{where}.clip")
        else:
            uses_model = True

        duration = _require_number(
            shot["duration"], f"{where}.duration", MIN_SHOT_S, MAX_SHOT_S
        )
        total += duration

        if "start" in shot:
            start = _require_number(
                shot["start"], f"{where}.start", 0.0, MAX_SHOT_DURATION_TOTAL_S
            )
            if abs(start - cursor) > START_TOLERANCE_S:
                raise PropsError(
                    f"{where}.start: {start:g} does not follow the previous shot, "
                    f"which ends at {cursor:g}; shots play back to back"
                )
        if "speed" in shot:
            _require_number(
                shot["speed"], f"{where}.speed", MIN_SPEED, MAX_SPEED
            )
        if "hud" in shot:
            validate_hud(shot["hud"], f"{where}.hud")

        cursor += duration

    if total > MAX_SHOT_DURATION_TOTAL_S:
        raise PropsError(
            f"props.shots: {total:g} s of shots; the template takes at most "
            f"{MAX_SHOT_DURATION_TOTAL_S:g} s (the gate allows up to 60 s total "
            "including the end card)"
        )

    if uses_model and "model3d" not in props:
        raise PropsError(
            "props.model3d: a shot uses the 'model' clip, so props.model3d "
            "(with a 'glb' path) is required"
        )

    return props


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    failures = 0
    for path in argv:
        try:
            with open(path, encoding="utf-8") as fh:
                props = json.load(fh)
        except OSError as exc:
            print(f"{path}: cannot read: {exc}", file=sys.stderr)
            failures += 1
            continue
        except json.JSONDecodeError as exc:
            print(f"{path}: invalid JSON: {exc}", file=sys.stderr)
            failures += 1
            continue
        try:
            validate(props)
        except PropsError as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            failures += 1
            continue
        print(f"{path}: ok")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
