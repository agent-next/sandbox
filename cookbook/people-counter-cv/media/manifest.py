"""Hash the shipped media and name its exact, regenerable inputs."""

import hashlib
import json
from pathlib import Path
import platform
import subprocess

import matplotlib
import numpy

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json",
        str(HERE / "demo.mp4"),
    ]))
    video = probe["streams"][0]
    assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
    assert (video["width"], video["height"], video["r_frame_rate"]) == (1920, 1080, "30/1")
    assert 20 <= float(probe["format"]["duration"]) <= 60
    assert int(probe["format"]["size"]) < 8_000_000
    sources = [
        "judge/spec.json", "judge/_grade.py", "judge/grade.sh", "judge/setup.sh",
        "judge/selftest.sh", "judge/mutants.py", "judge/ref_count.py",
        "judge/gen_scene.py", "judge/requirements.lock",
        "examples/good/counter.py", "examples/good/loop.json",
        "examples/loop.py", "media/requirements.txt", "media/collect.py",
        "media/render.py", "media/manifest.py", "media/make_media.sh",
        "media/test_media.py", "media/data/grade.json",
        "media/data/selftest.txt",
    ] + [f"media/data/{n}" for n in
         ("crossings.csv", "ref_crossings.csv", "truth.json")]
    descriptions = {
        "result.png": (
            "Four panels: a clip frame with the tripwire; truth vs artifact "
            "crossings on the time axis; per-event crossing-time error against "
            "the 300 ms max and 150 ms MAE judge limits; counts (truth vs "
            "artifact vs the judge's MOG2 reference).",
            ["media/data/crossings.csv", "media/data/ref_crossings.csv",
             "media/data/truth.json", "media/data/grade.json",
             "judge/spec.json", "judge/_grade.py"]),
        "loop.png": (
            "Graded agent loop: matched/phantom/missed events per iteration "
            "until the 20/20 pass, plus the real selftest kill bars for the "
            "good counter and nine mutants labelled with their failing gates.",
            ["examples/good/loop.json", "media/data/selftest.txt"]),
        "demo.mp4": (
            "48 s: the deterministic clip plays with the tripwire drawn and "
            "the counter's cumulative east/west counts rising against truth "
            "ticks, ending on the judge PASS table. Web crf 18 / preset slow "
            "from ignored crf 0 media/master/demo.mp4.",
            ["media/data/crossings.csv", "media/data/truth.json",
             "media/data/grade.json", "judge/spec.json"]),
    }
    files = []
    for name, (what, data) in descriptions.items():
        path = HERE / name
        files.append({"file": name, "what": what,
                      "command": "bash cookbook/people-counter-cv/media/make_media.sh",
                      "source_data": data,
                      "sha256": digest(path), "bytes": path.stat().st_size})
    manifest = {
        "demo": "cookbook/people-counter-cv",
        "seed": 0,
        "note": "No invented measurements. crossings.csv/ref_crossings.csv "
                "are re-produced by the good counter and the judge's "
                "reference counter on the regenerated clip, and their oracle "
                "metrics asserted exactly equal to the full-run grade "
                "(media/collect.py). data/grade.json excludes only timing. "
                "The judge is copied unchanged to ignored scratch before "
                "setup (which writes VERSIONS.txt). The 18.7 MB clip itself "
                "and its decoded frames are regenerated and ignored, never "
                "shipped.",
        "files": files,
        "source_sha256": {s: digest(DEMO / s) for s in sources},
        "toolchain": {
            "python": platform.python_version(),
            "matplotlib": matplotlib.__version__,
            "numpy_rendering": numpy.__version__,
            "judge": (HERE / "data/versions.txt").read_text().splitlines()[0][2:],
            "ffmpeg": subprocess.run(["ffmpeg", "-version"],
                                     capture_output=True, text=True
                                     ).stdout.split()[2],
        },
        "video": {
            "codec_name": video["codec_name"],
            "width": video["width"],
            "height": video["height"],
            "r_frame_rate": video["r_frame_rate"],
            "pix_fmt": video["pix_fmt"],
            "nb_frames": video.get("nb_frames"),
        },
        "duration_s": round(float(probe["format"]["duration"]), 1),
    }
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest: {len(files)} files hashed")


if __name__ == "__main__":
    main()
