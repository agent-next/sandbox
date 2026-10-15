#!/usr/bin/env python3
"""Validate a Demo-composition props JSON for cookbook/tools/remotion.

Pure Python 3.10+ stdlib — runs without node; this is what CI exercises.
Usage: validate_props.py <props.json>   (exit 0 ok, 1 invalid, 2 unreadable)

The shape mirrors src/props.ts. Any key outside the contract is rejected,
as are image clips (.png/.jpg/...) — every shot must be real motion footage.
The timeline constants below must stay in sync with src/props.ts.
"""

from __future__ import annotations

import json
import os
import sys

# --- timeline constants (mirror src/props.ts; keep in sync) ------------------
FPS = 30
TRANSITION_S = 6 / FPS  # wipe between shots
END_CARD_S = 2.5
MODEL_SHOT_S = 6.0
MIN_TOTAL_S = 25.0  # video_gate.MIN_DURATION_S
MAX_TOTAL_S = 60.0  # video_gate.MAX_DURATION_S

VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif",
             ".tiff", ".avif", ".heic"}

TOP_KEYS = {"shots", "model3d", "verdict", "headline", "launch"}
SHOT_KEYS = {"clip", "start", "duration", "speed", "hud"}
HUD_KEYS = {"label", "value", "unit"}
VERDICT_KEYS = {"pass", "gates"}
GATE_KEYS = {"name", "measured", "threshold"}
LAUNCH_KEYS = {"command", "ask_agent"}
MODEL_KEYS = {"glb"}


class Invalid(Exception):
    pass


def _err(msg: str) -> Invalid:
    return Invalid(msg)


def _check_keys(obj: dict, allowed: set, where: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise _err(f"{where}: unknown key(s) {sorted(extra)}")


def _num(v, where: str, minimum: float | None = None,
         exclusive_min: bool = False) -> None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise _err(f"{where}: expected a number, got {v!r}")
    if minimum is not None:
        bad = v <= minimum if exclusive_min else v < minimum
        if bad:
            op = ">" if exclusive_min else ">="
            raise _err(f"{where}: expected {op} {minimum}, got {v}")


def _str(v, where: str, nonempty: bool = True) -> None:
    if not isinstance(v, str) or (nonempty and not v.strip()):
        raise _err(f"{where}: expected a non-empty string, got {v!r}")


def _req(obj: dict, key: str, where: str):
    if key not in obj:
        raise _err(f"{where}: missing required key '{key}'")
    return obj[key]


def _check_clip_path(path, where: str) -> None:
    _str(path, where)
    ext = os.path.splitext(path.split("?")[0])[1].lower()
    if ext in IMAGE_EXT:
        raise _err(
            f"{where}: '{ext}' is an image, not motion footage — "
            "every shot must play a real clip"
        )
    if ext not in VIDEO_EXT:
        raise _err(
            f"{where}: unsupported extension '{ext or '(none)'}' "
            f"(expected one of {sorted(VIDEO_EXT)})"
        )


def check(props: dict) -> None:
    if not isinstance(props, dict):
        raise _err("top level must be an object")
    _check_keys(props, TOP_KEYS, "props")
    for key in ("shots", "verdict", "headline", "launch"):
        _req(props, key, "props")

    shots = props["shots"]
    if not isinstance(shots, list) or not shots:
        raise _err("shots: expected a non-empty array")
    for i, shot in enumerate(shots):
        w = f"shots[{i}]"
        if not isinstance(shot, dict):
            raise _err(f"{w}: expected an object")
        _check_keys(shot, SHOT_KEYS, w)
        _check_clip_path(_req(shot, "clip", w), f"{w}.clip")
        _num(_req(shot, "duration", w), f"{w}.duration", 0, exclusive_min=True)
        if "start" in shot:
            _num(shot["start"], f"{w}.start", 0)
        if "speed" in shot:
            _num(shot["speed"], f"{w}.speed", 0, exclusive_min=True)
        if "hud" in shot:
            hud = shot["hud"]
            if not isinstance(hud, list) or not hud:
                raise _err(f"{w}.hud: expected a non-empty array")
            for j, entry in enumerate(hud):
                hw = f"{w}.hud[{j}]"
                if not isinstance(entry, dict):
                    raise _err(f"{hw}: expected an object")
                _check_keys(entry, HUD_KEYS, hw)
                _str(_req(entry, "label", hw), f"{hw}.label")
                _req(entry, "value", hw)
                if "unit" in entry:
                    _str(entry["unit"], f"{hw}.unit")

    if "model3d" in props:
        model = props["model3d"]
        if not isinstance(model, dict):
            raise _err("model3d: expected an object")
        _check_keys(model, MODEL_KEYS, "model3d")
        glb = _req(model, "glb", "model3d")
        _str(glb, "model3d.glb")
        if not glb.lower().endswith((".glb", ".gltf")):
            raise _err("model3d.glb: expected a .glb/.gltf path")

    verdict = props["verdict"]
    if not isinstance(verdict, dict):
        raise _err("verdict: expected an object")
    _check_keys(verdict, VERDICT_KEYS, "verdict")
    if not isinstance(_req(verdict, "pass", "verdict"), bool):
        raise _err("verdict.pass: expected a boolean")
    gates = _req(verdict, "gates", "verdict")
    if not isinstance(gates, list) or not gates:
        raise _err("verdict.gates: expected a non-empty array")
    for i, gate in enumerate(gates):
        gw = f"verdict.gates[{i}]"
        if not isinstance(gate, dict):
            raise _err(f"{gw}: expected an object")
        _check_keys(gate, GATE_KEYS, gw)
        _str(_req(gate, "name", gw), f"{gw}.name")
        for key in ("measured", "threshold"):
            v = _req(gate, key, gw)
            if isinstance(v, bool) or not isinstance(v, (int, float, str)):
                raise _err(f"{gw}.{key}: expected a number or string")

    _str(props["headline"], "headline")

    launch = props["launch"]
    if not isinstance(launch, dict):
        raise _err("launch: expected an object")
    _check_keys(launch, LAUNCH_KEYS, "launch")
    _str(_req(launch, "command", launch), "launch.command")
    _str(_req(launch, "ask_agent", launch), "launch.ask_agent")

    # The rendered length must land inside the video gate's 25-60 s window.
    n_items = len(shots) + (1 if "model3d" in props else 0)
    total = (
        sum(float(s["duration"]) for s in shots)
        + (MODEL_SHOT_S if "model3d" in props else 0.0)
        + END_CARD_S
        - (n_items - 1) * TRANSITION_S
    )
    if not MIN_TOTAL_S <= total <= MAX_TOTAL_S:
        raise _err(
            f"estimated video length {total:.1f}s is outside "
            f"{MIN_TOTAL_S:g}-{MAX_TOTAL_S:g}s (video gate)"
        )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <props.json>", file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as fh:
            props = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {argv[1]}: {exc}", file=sys.stderr)
        return 2
    try:
        check(props)
    except Invalid as exc:
        print(f"invalid props: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
