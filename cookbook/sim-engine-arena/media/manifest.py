"""Hash shipped media and the exact graded inputs used for MuJoCo rendering."""

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

import mujoco
import numpy
import PIL

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
COMMAND = "bash cookbook/sim-engine-arena/media/make_media.sh"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_files(root, recorded):
    for entry in recorded["files"]:
        path = root / entry["file"]
        assert path.is_file(), f"Missing media file: {entry['file']}"
        assert digest(path) == entry["sha256"], f"Hash mismatch: {entry['file']}"


def main():
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json",
        str(HERE / "demo.mp4")]))
    video = probe["streams"][0]
    assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
    assert (video["width"], video["height"], video["r_frame_rate"]) == (1920, 1080, "30/1")
    assert 20 <= float(probe["format"]["duration"]) <= 60
    assert int(probe["format"]["size"]) < 8_000_000
    sources = [
        "judge/spec.json", "judge/_grade.py", "judge/grade.sh", "judge/setup.sh",
        "judge/selftest.sh", "judge/mutants.py", "judge/ref_sim.py",
        "judge/requirements.lock", "examples/good/sim.py", "examples/good/loop.json",
        "examples/loop.py", "media/requirements.txt", "media/collect.py",
        "media/render.py", "media/manifest.py", "media/make_media.sh", "media/test_media.py",
        "media/data/grade.json", "media/data/selftest.txt", "media/data/render-checks.json",
    ]
    for name in ("drop", "incline_slide", "incline_stick", "pendulum"):
        sources.extend(f"media/data/{prefix}{name}.{ext}" for prefix, ext in
                       (("traj_", "csv"), ("model_", "xml"), ("render_", "xml"), ("state_", "npy")))
        sources.append(f"examples/good/mjcf/model_{name}.xml")
    sources.extend(("media/master/demo.mp4", "media/data/versions.txt"))
    descriptions = {
        "result.png": (
            "Grid of twelve real 3D MuJoCo frames: release/contact/settling drop; "
            "35-degree sliding and 20-degree sticking boxes at three times each; "
            "pendulum at both extrema and center. Every tile gives measured vs "
            "oracle and its numeric PASS line.",
            ["media/data/traj_*.csv", "media/data/model_*.xml", "media/data/state_*.npy",
             "media/data/grade.json", "judge/spec.json"]),
        "loop.png": (
            "Pillow table/bars: actual recorded draft verdicts 3/4, 3/4, 4/4; "
            "FAIL, FAIL, PASS; known-good passes and eight mutants are killed.",
            ["examples/good/loop.json", "media/data/selftest.txt"]),
        "demo.mp4": (
            "28 seconds of mujoco.Renderer 3D replay: drop at 4x slow motion, "
            "inclines side by side at 8x slow motion, pendulum in real time, "
            "then a PASS card over the final rendered state. Pillow captions. "
            "Web crf 18/preset slow from ignored lossless crf 0 master.",
            ["media/data/traj_*.csv", "media/data/model_*.xml", "media/data/state_*.npy",
             "media/data/grade.json", "media/data/selftest.txt", "media/master/demo.mp4"]),
    }
    manifest = {
        "demo": "cookbook/sim-engine-arena", "seed": 0,
        "command": COMMAND,
        "note": "collect.py invokes the unchanged judge main with a run_artifact "
        "observer that copies the ACTUAL graded CSVs and generated MJCF before "
        "judge cleanup. It does not rerun the artifact to reconstruct evidence. "
        "All replay samples match all CSV columns within 1e-9. For free joints, "
        "the artifact logs pre-integration xpos, so rendered qpos is that same "
        "pre-step state; pendulum logs updated qpos. Every rendered frame checks "
        "qpos and the graded position/angle. data/grade.json excludes only timing.",
        "render_only_changes": [
            "Generated artifact MJCF remains the physics source, not ref_sim.py.",
            "Render-only XML adds skybox/checker textures, materials, lights and "
            "offscreen settings. Cameras are runtime view settings; shadows enabled.",
            "Pendulum gets a zero-mass, noncolliding visible link, anchor and floor. "
            "Existing masses, inertia, geometry, friction, contact parameters, "
            "transforms, gravity and timestep are asserted unchanged.",
        ],
        "files": [{"file": n, "what": what, "command": COMMAND, "source": data,
                   "sha256": digest(HERE / n), "bytes": (HERE / n).stat().st_size}
                  for n, (what, data) in descriptions.items()],
        "source_sha256": {s: digest(DEMO / s) for s in sources},
        "toolchain": {
            "python": platform.python_version(), "mujoco": mujoco.__version__,
            "numpy": numpy.__version__, "pillow": PIL.__version__,
            "gl_backend": os.environ["MUJOCO_GL"],
            "font": "DejaVu Sans (system font, checksummed below)",
            "font_sha256": {n: digest(Path("/usr/share/fonts/truetype/dejavu") / n)
                            for n in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")},
            "judge": (HERE / "data/versions.txt").read_text().splitlines()[0].lstrip("# "),
            "ffmpeg": subprocess.check_output(
                ["ffmpeg", "-version"], text=True).splitlines()[0].split()[2],
        },
        "video": {k: video[k] for k in ("codec_name", "width", "height",
                                      "r_frame_rate", "pix_fmt", "nb_frames")},
        "duration_s": float(probe["format"]["duration"]),
    }
    validate_files(HERE, manifest)
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("MANIFEST.json: hashes written; video meets duration/size/format limits")


if __name__ == "__main__":
    main()
