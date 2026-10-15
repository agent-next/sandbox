#!/usr/bin/env python3
"""Tests for the HyperFrames demo-video template (cookbook/tools/hyperframes/).

Two layers:

* props validation — pure Python 3 stdlib, no node required. This is the
  part CI runs: it exercises validate_props.py against the committed
  props.example.json and a set of rejected inputs.
* end-to-end render — skipped with a clear reason when `node` is absent.
  Otherwise it generates real lavfi motion clips plus a tiny glb, renders a
  ~26 s example through render_demo_video.sh and asserts video_gate.py
  passes on the output.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
HF_DIR = TOOLS / "hyperframes"
VALIDATOR = HF_DIR / "validate_props.py"
RENDER_SH = TOOLS / "render_demo_video.sh"
VIDEO_GATE = TOOLS / "video_gate.py"
EXAMPLE_PROPS = HF_DIR / "props.example.json"
MAKE_GLB = HF_DIR / "scripts" / "make_example_glb.py"

FPS = 30


def _validator(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _write_props(tmp_path: Path, props: dict) -> Path:
    path = tmp_path / "props.json"
    path.write_text(json.dumps(props), encoding="utf-8")
    return path


def _minimal_props() -> dict:
    return {
        "shots": [{"clip": "media/clips/a.mp4", "duration": 25}],
        "verdict": {
            "pass": True,
            "gates": [{"name": "g", "measured": "1", "threshold": ">= 0"}],
        },
        "headline": "demo",
        "launch": {"command": "python3 run.py", "ask_agent": "run the demo"},
    }


# --- validator tests (no node required — what CI runs) ------------------------


def test_example_props_validate() -> None:
    proc = _validator(str(EXAMPLE_PROPS))
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_rejects_image_clip(tmp_path: Path) -> None:
    for ext in (".png", ".jpg"):
        props = _minimal_props()
        props["shots"][0]["clip"] = f"media/clips/still{ext}"
        proc = _validator(str(_write_props(tmp_path, props)))
        assert proc.returncode != 0, f"{ext} clip was accepted"
        assert "image" in (proc.stderr + proc.stdout).lower()


def test_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    props = _minimal_props()
    props["bogus"] = True
    proc = _validator(str(_write_props(tmp_path, props)))
    assert proc.returncode != 0
    assert "bogus" in (proc.stderr + proc.stdout)


def test_rejects_unknown_shot_key(tmp_path: Path) -> None:
    props = _minimal_props()
    props["shots"][0]["poster"] = "x.png"
    proc = _validator(str(_write_props(tmp_path, props)))
    assert proc.returncode != 0
    assert "poster" in (proc.stderr + proc.stdout)


def test_rejects_model_shot_without_model3d(tmp_path: Path) -> None:
    props = _minimal_props()
    props["shots"][0]["clip"] = "model"
    proc = _validator(str(_write_props(tmp_path, props)))
    assert proc.returncode != 0
    assert "model3d" in (proc.stderr + proc.stdout)


def test_rejects_missing_required(tmp_path: Path) -> None:
    props = _minimal_props()
    del props["launch"]
    proc = _validator(str(_write_props(tmp_path, props)))
    assert proc.returncode != 0
    assert "launch" in (proc.stderr + proc.stdout)


def test_rejects_overshoot_duration(tmp_path: Path) -> None:
    props = _minimal_props()
    props["shots"] = [{"clip": "media/clips/a.mp4", "duration": 90}]
    proc = _validator(str(_write_props(tmp_path, props)))
    assert proc.returncode != 0


# --- end-to-end render (needs node + ffmpeg + chrome headless shell) ----------


def _make_clip(path: Path, lavfi: str, seconds: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", lavfi,
            "-t", f"{seconds}",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-crf", "22",
            str(path),
        ],
        check=True,
        timeout=900,
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not on PATH")
def test_render_end_to_end(tmp_path: Path) -> None:
    """Render a ~26 s example through render_demo_video.sh and gate it.

    Clip budget (all 1920x1080 @ 30 fps): 22.5 s of footage + 2.5 s end
    card = 25.0-26.0 s after frame rounding — inside the gate's 25-60 s.
    """
    media = tmp_path / "media"
    clips = media / "clips"
    clips.mkdir(parents=True)

    _make_clip(clips / "testsrc2.mp4", "testsrc2=size=1920x1080:rate=30", 8)
    _make_clip(clips / "life.mp4", "life=size=1920x1080:rate=30:mold=10", 8)
    _make_clip(
        clips / "mandel.mp4",
        "mandelbrot=size=1920x1080:rate=30",
        24,  # 5.5 s at 4x consumes ~22 s of source
    )

    glb = media / "model.glb"
    subprocess.run(
        [sys.executable, str(MAKE_GLB), str(glb)],
        check=True,
        timeout=60,
    )
    assert 0 < glb.stat().st_size <= 50 * 1024

    props = {
        "shots": [
            {
                "clip": "clips/testsrc2.mp4",
                "duration": 6,
                "hud": [
                    {"label": "RMS error", "value": 0.031, "unit": "mm"},
                    {"label": "solve", "value": 812, "unit": "ms"},
                ],
            },
            {"clip": "clips/life.mp4", "duration": 6},
            {"clip": "model", "duration": 5},
            {
                "clip": "clips/mandel.mp4",
                "duration": 5.5,
                "speed": 4,
                "hud": [{"label": "iterations", "value": 96}],
            },
        ],
        "model3d": {"glb": "model.glb"},
        "verdict": {
            "pass": True,
            "gates": [
                {"name": "rms_error", "measured": "0.031", "threshold": "<= 0.05"},
                {"name": "mesh_watertight", "measured": "true", "threshold": "true"},
                {"name": "selftest_kill_rate", "measured": "6/6", "threshold": ">= 90 %"},
            ],
        },
        "headline": "solver converged in 3 passes",
        "launch": {
            "command": "python3 run.py",
            "ask_agent": "run the sim demo in a sandbox",
        },
    }
    props_path = _write_props(media, props)
    out = tmp_path / "demo.mp4"

    proc = subprocess.run(
        ["bash", str(RENDER_SH), str(props_path), str(out)],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    assert proc.returncode == 0, (
        f"render_demo_video.sh failed\nstdout:\n{proc.stdout[-4000:]}\n"
        f"stderr:\n{proc.stderr[-4000:]}"
    )
    assert out.is_file() and out.stat().st_size > 0

    gate = subprocess.run(
        [sys.executable, str(VIDEO_GATE), str(out)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert gate.returncode == 0, f"video gate failed\n{gate.stdout}"
