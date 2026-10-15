"""Check the shipped media: sizes, formats, and manifest hashes."""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent


def main():
    man = json.loads((HERE / "MANIFEST.json").read_text())
    problems = []

    import hashlib
    for entry in man["files"]:
        p = HERE / entry["file"]
        if hashlib.sha256(p.read_bytes()).hexdigest() != entry["sha256"]:
            problems.append(f"{entry['file']}: sha256 does not match manifest")
        if p.stat().st_size > 5_000_000:
            problems.append(f"{entry['file']}: over the 5 MB repo limit")
    for src, sha in man["source_sha256"].items():
        p = DEMO / src
        if not p.exists():
            problems.append(f"{src}: listed as source but missing")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            problems.append(f"{src}: source hash stale vs manifest")

    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of",
        "json", str(HERE / "demo.mp4")]))
    v = probe["streams"][0]
    if (v["codec_name"], v["width"], v["height"], v["r_frame_rate"],
            v["pix_fmt"]) != ("h264", 1920, 1080, "30/1", "yuv420p"):
        problems.append(f"demo.mp4: {v['codec_name']} {v['width']}x"
                        f"{v['height']} {v['r_frame_rate']} {v['pix_fmt']}")
    dur = float(probe["format"]["duration"])
    if not 20 <= dur <= 60:
        problems.append(f"demo.mp4: {dur:.1f} s outside 20-60 s")
    size = int(probe["format"]["size"])
    if size >= 8_000_000:
        problems.append(f"demo.mp4: {size} bytes >= 8 MB")

    for png in ("result.png", "loop.png"):
        out = subprocess.run(["python3", "-c",
                              f"from PIL import Image; "
                              f"im = Image.open(r'{HERE / png}'); "
                              f"print(im.width, im.height)"],
                             capture_output=True, text=True)
        if out.returncode != 0:
            problems.append(f"{png}: unreadable")
        else:
            w, h = map(int, out.stdout.split())
            if w < 1200:
                problems.append(f"{png}: {w} px wide < 1200")

    grade = json.loads((HERE / "data/grade.json").read_text())
    if not all(g["pass"] for g in grade["gates"].values()) \
            or not grade["judge_intact"]:
        problems.append("data/grade.json is not an all-gates-pass verdict")

    if problems:
        print("\n".join(f"test_media: {p}" for p in problems), file=sys.stderr)
        sys.exit(1)
    print(f"test_media: ok ({len(man['files'])} files, {dur:.0f} s video, "
          f"{size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
