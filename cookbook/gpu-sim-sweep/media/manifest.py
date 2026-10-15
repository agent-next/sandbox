"""Content-addressed provenance for every media output and its inputs."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_files(media, manifest):
    assert set(manifest["outputs"]) == {"result.png", "loop.png", "demo.mp4"}
    for name, row in manifest["outputs"].items():
        path = media / name
        assert path.is_file(), f"Missing media file: {name}"
        assert path.stat().st_size == row["bytes"], f"Size mismatch: {name}"
        assert digest(path) == row["sha256"], f"SHA mismatch: {name}"
    for name, sha in manifest["source_sha256"].items():
        path = media.parent / name
        assert path.is_file(), f"Missing source file: {name}"
        assert digest(path) == sha, f"Source SHA mismatch: {name}"


def main():
    sources = ("examples/good/sweep.json", "judge/_grade.py", "judge/_sweep.py",
               "judge/scene.py", "media/data/report.json", "media/data/gpu-run.log",
               "media/data/cpu-qpos.npy", "media/data/model.xml", "media/data/replay.json",
               "media/data/loop.json", "media/evidence.py", "media/render.py",
               "media/make_media.sh", "media/requirements.txt",
               "media/manifest.py", "media/test_media.py")
    descriptions = {
        "result.png": "Four real MuJoCo 3D key moments of the arm and eight boxes; "
                      "graded CPU oracle vs pass bounds per tile; measured GPU ladder "
                      "and throughput pass line drawn with Pillow.",
        "loop.png": "Pillow config-fixing replay of two measured bad grades and the "
                    "good grade (explicitly not a live agent trace), all six final "
                    "gates and the 8/8 self-test kill rate.",
        "demo.mp4": "26 s simulator-native MuJoCo CPU reference replay of world 0; "
                    "native 3D camera orbits of the arm reaching and eight boxes "
                    "falling/settling; single, 2x2 and 4x4 animated identical-world "
                    "replays; measured ladder reveal; moving PASS/kill-matrix HUD; "
                    "static launch frame only in the last 2 s.",
    }
    manifest = {
        "generated_by": "bash cookbook/gpu-sim-sweep/media/make_media.sh",
        "source_sha256": {p: digest(DEMO / p) for p in sources},
        "measurement_command": "python3 cookbook/gpu-sim-sweep/run.py --ref sbx/sweep-r4 --gpu",
        "measurement_date": "2026-10-15",
        "seed": 0,
        "render_backend": "mujoco.Renderer; EGL preferred, OSMesa fallback",
        "state_checks": "All CPU states re-run with judge cpu_reference; graded CPU "
                        "oracle within 1e-9; every rendered qpos within 1e-9 of the "
                        "CPU data; retained float32 GPU samples within judge tolerance 0.05.",
        "video": {"width": 1920, "height": 1080, "fps": 30, "seconds": 26,
                  "web_encode": "-crf 18 -preset slow -pix_fmt yuv420p "
                                "-maxrate 2100k -bufsize 2100k -movflags +faststart",
                  "simulator_clips": "media/clips/shot-00.mp4 through shot-09.mp4 "
                                     "(lossless, git-ignored; concatenated into master)",
                  "lossless_master": "media/master/demo.mp4 (-crf 0, git-ignored)"},
        "outputs": {},
    }
    for name, what in descriptions.items():
        path = HERE / name
        manifest["outputs"][name] = {
            "what": what, "command": manifest["generated_by"],
            "sha256": digest(path), "bytes": path.stat().st_size,
            "source_data": ["media/data/report.json", "media/data/cpu-qpos.npy",
                            "media/data/model.xml", "media/data/loop.json"],
        }
    validate_files(HERE, manifest)
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("MANIFEST: files, sizes, source and output SHA256 verified")


if __name__ == "__main__":
    main()
