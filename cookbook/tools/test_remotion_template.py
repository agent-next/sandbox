"""Tests for cookbook/tools/remotion/ — the Remotion demo-video template.

Two layers:

* Validator tests (always run, no node needed): the props JSON contract is
  checked by cookbook/tools/remotion/validate_props.py, a stdlib-only Python
  script. CI runs these; they must reject image clips and unknown keys.
* Render test (skipped when node/npm are absent): generates real motion
  clips with ffmpeg lavfi plus a tiny .glb written by
  cookbook/tools/remotion/gen_glb.py, renders a ~26 s example through
  remotion/render.sh, and asserts cookbook/tools/video_gate.py passes it.

Run from the repo root:  python3 -m pytest -q cookbook/tools/test_remotion_template.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parents[1]
REMOTION_DIR = TOOLS_DIR / "remotion"
VALIDATOR = REMOTION_DIR / "validate_props.py"
RENDER_SH = REMOTION_DIR / "render.sh"
EXAMPLE_PROPS = REMOTION_DIR / "props.example.json"
GEN_GLB = REMOTION_DIR / "gen_glb.py"

sys.path.insert(0, str(TOOLS_DIR))
import video_gate  # noqa: E402

CLIP_S = 8  # lavfi source length; the shots trim to `duration`
RATE = 30


def _run_validator(props_path: Path) -> subprocess.CompletedProcess:
    assert VALIDATOR.is_file(), f"missing {VALIDATOR}"
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(props_path)],
        capture_output=True,
        text=True,
    )


def _write_props(tmp: Path, obj: dict) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / "props.json"
    path.write_text(json.dumps(obj))
    return path


def _valid_props(**overrides) -> dict:
    props = {
        "headline": "Agent-built filter: PASS in 3 iterations",
        "shots": [
            {"clip": "a.mp4", "duration": 7,
             "hud": [{"label": "cutoff", "value": 1000, "unit": "Hz"}]},
            {"clip": "b.mp4", "duration": 7, "speed": 4},
            {"clip": "c.mp4", "duration": 7},
        ],
        "model3d": {"glb": "model.glb"},
        "verdict": {
            "pass": True,
            "gates": [
                {"name": "cutoff", "measured": "1000 Hz",
                 "threshold": "990-1010"},
            ],
        },
        "launch": {"command": "python3 run.py",
                   "ask_agent": "build me a filter and prove it"},
    }
    props.update(overrides)
    return props


# --- validator tests (run without node; this is what CI exercises) ----------


def test_props_example_validates():
    assert VALIDATOR.is_file(), f"missing {VALIDATOR}"
    assert EXAMPLE_PROPS.is_file(), f"missing {EXAMPLE_PROPS}"
    proc = _run_validator(EXAMPLE_PROPS)
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_validator_accepts_minimal(tmp_path: Path):
    path = _write_props(tmp_path, _valid_props())
    assert _run_validator(path).returncode == 0


def test_validator_rejects_image_clip(tmp_path: Path):
    for ext in (".png", ".jpg", ".jpeg"):
        path = _write_props(
            tmp_path / ext[1:],
            _valid_props(shots=[{"clip": f"still{ext}", "duration": 7},
                                {"clip": "ok.mp4", "duration": 7},
                                {"clip": "ok2.mp4", "duration": 7}]),
        )
        proc = _run_validator(path)
        assert proc.returncode != 0, f"{ext} clip was accepted"
        assert ext in proc.stderr


def test_validator_rejects_unknown_keys(tmp_path: Path):
    cases = [
        _valid_props(extra_top=1),  # unknown top-level key
        _valid_props(shots=[{"clip": "a.mp4", "duration": 7, "bogus": 1},
                            {"clip": "b.mp4", "duration": 7},
                            {"clip": "c.mp4", "duration": 7}]),
        _valid_props(verdict={"pass": True, "gates": [
            {"name": "g", "measured": 1, "threshold": 2, "wat": 3}]}),
        _valid_props(launch={"command": "x", "ask_agent": "y", "url": "z"}),
        _valid_props(model3d={"glb": "m.glb", "spin": 2}),
    ]
    for i, props in enumerate(cases):
        path = _write_props(tmp_path / f"c{i}", props)
        assert _run_validator(path).returncode != 0, f"case {i} accepted"


def test_validator_rejects_bad_shapes(tmp_path: Path):
    cases = [
        _valid_props(shots=[]),  # need >= 1 shot
        _valid_props(shots=[{"clip": "a.mp4"}]),  # duration required
        _valid_props(shots=[{"clip": "a.mp4", "duration": -3}]),
        _valid_props(headline=5),
        _valid_props(verdict={"pass": "yes", "gates": []}),
        _valid_props(verdict={"pass": True, "gates": []}),
        _valid_props(shots=[{"clip": "a.mp4", "duration": 7,
                             "hud": [{"label": "x"}]},
                            {"clip": "b.mp4", "duration": 7},
                            {"clip": "c.mp4", "duration": 7}]),
    ]
    for i, props in enumerate(cases):
        path = _write_props(tmp_path / f"b{i}", props)
        assert _run_validator(path).returncode != 0, f"case {i} accepted"


# --- end-to-end render (needs node, npm and ffmpeg) ---------------------------

HAVE_NODE = all(shutil.which(t) for t in ("node", "npm"))
HAVE_FFMPEG = all(shutil.which(t) for t in ("ffmpeg", "ffprobe"))


@pytest.mark.skipif(not HAVE_NODE, reason="node/npm not installed")
@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_render_example_passes_gate(tmp_path: Path):
    """Render a ~26 s example through render.sh; the video gate must pass."""
    clips = tmp_path / "clips"
    clips.mkdir()
    sources = [
        ("mandelbrot", "mandelbrot=s=640x360:r=30", "scale=1920:1080"),
        ("testsrc2", "testsrc2=s=1920x1080:r=30", "null"),
        ("cellauto", "cellauto=s=640x360:r=30:rule=110",
         "scale=1920:1080:flags=neighbor"),
    ]
    for name, src, vf in sources:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src,
             "-t", str(CLIP_S), "-vf", vf, "-c:v", "libx264", "-crf", "23",
             "-pix_fmt", "yuv420p", str(clips / f"{name}.mp4")],
            check=True,
        )
    subprocess.run(
        [sys.executable, str(GEN_GLB), str(clips / "torus.glb")],
        check=True,
    )
    glb_size = (clips / "torus.glb").stat().st_size
    assert glb_size < 50 * 1024, "committed/test glb must stay < 50 KB"

    props = {
        "headline": "Agent-built filter: PASS in 3 iterations",
        "shots": [
            {"clip": str(clips / "mandelbrot.mp4"), "duration": 6,
             "hud": [{"label": "cutoff", "value": 1000, "unit": "Hz"}]},
            {"clip": str(clips / "testsrc2.mp4"), "duration": 7},
            {"clip": str(clips / "cellauto.mp4"), "duration": 7},
        ],
        "model3d": {"glb": str(clips / "torus.glb")},
        "verdict": {
            "pass": True,
            "gates": [
                {"name": "cutoff", "measured": "1000 Hz",
                 "threshold": "990-1010"},
                {"name": "ripple", "measured": "0.42 dB",
                 "threshold": "<= 0.5"},
            ],
        },
        "launch": {"command": "python3 run.py",
                   "ask_agent": "build me a 1 kHz low-pass filter"},
    }
    props_path = _write_props(tmp_path, props)
    out = tmp_path / "demo.mp4"
    proc = subprocess.run(
        ["bash", str(RENDER_SH), str(props_path), str(out)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        f"render.sh failed\nSTDOUT:\n{proc.stdout[-4000:]}\n"
        f"STDERR:\n{proc.stderr[-4000:]}"
    )
    assert out.is_file() and out.stat().st_size > 0
    verdict = video_gate.judge(str(out))
    assert verdict["passed"], json.dumps(verdict, indent=2)
