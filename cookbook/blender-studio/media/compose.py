"""Figures, factual captions and video cut from real Blender render evidence."""
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "source"
MASTER = HERE / "master"
BG = (13, 22, 36)
WHITE = (245, 249, 255)
BLUE = (83, 189, 232)
ORANGE = (245, 158, 65)
POSE_COUNT = 48
POSES_PER_SECOND = 24
VIDEO_SECONDS = 28
FAILURE_LABELS = {
    "clipped_hero": "Cropped hero",
    "filtered_seam": "Edge seam",
    "high_seam": "Raised seam",
    "off_center": "Off-center hero",
    "orbiting_hero": "Drifting hero",
    "overexposed": "Too bright",
    "unlinked_halo": "Stray glow",
    "unlinked_rim": "Stray rim light",
    "visible_seam": "Backdrop seam",
    "wrong_period": "Incomplete turn",
}
FONT_SHA256 = "abdc775b21b1bc470d50c97e790d276f2054b7504e56e5bd3e64f48d68582322"
FONT_PATH = Path(ImageFont.truetype("DejaVuSans.ttf", 64).path)
if hashlib.sha256(FONT_PATH.read_bytes()).hexdigest() != FONT_SHA256:
    raise RuntimeError("requires the pinned DejaVuSans.ttf; see README.md")


@lru_cache(maxsize=16)
def font(size):
    return ImageFont.truetype(str(FONT_PATH), size)


def text(draw, xy, value, size=64, color=WHITE):
    face = font(size)
    left, top, right, bottom = draw.textbbox(xy, value, font=face, stroke_width=1)
    width, height = draw.im.size
    if left < 0 or top < 0 or right > width or bottom > height:
        raise ValueError(f"caption outside frame: {value}")
    draw.text(xy, value, font=face, fill=color, stroke_width=1)


def panel(image, box, fill=BG):
    ImageDraw.Draw(image).rectangle(box, fill=fill)


def hero():
    return Image.open(SOURCE / "frame-01.png").convert("RGB")


def prepare_media():
    MASTER.mkdir(parents=True, exist_ok=True)
    data = json.loads((HERE / "data/selftest.json").read_text())
    capture = json.loads((HERE / "data/capture.json").read_text())
    if not data["pass"] or data["kill_rate"] != 1:
        raise RuntimeError("cannot publish PASS media from failing evidence")
    gates = data["good"]["gates"]
    render_rows = json.loads((SOURCE / "render.json").read_text())
    if len(render_rows) != POSE_COUNT + 1:
        raise RuntimeError("need 48 actual turntable poses plus unlinked comparison")
    for i, row in enumerate(render_rows[:-1]):
        if (row["file"] != f"frame-{i+1:02}.png" or row["pose"] != i+1 or
                row["frame"] != 1 + i / 4 or
                abs(row["angle_radians"] - 2 * math.pi * i / POSE_COUNT) > 0.00001):
            raise RuntimeError("media metadata must sample the unchanged 12-frame spin")
    if render_rows[-1]["file"] != "unlinked.png":
        raise RuntimeError("missing full-resolution rim-light comparison")
    for row in render_rows:
        path = SOURCE / row["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise RuntimeError(f"render source checksum mismatch: {path.name}")
        if Image.open(path).size != (1920, 1080):
            raise RuntimeError("media source must be actual 1080p Blender output")
    # Figure: actual 3D render plus normalized framing tolerance overlay.
    result = hero()
    draw = ImageDraw.Draw(result)
    draw.rectangle((77, 43, 1843, 1037), outline=BLUE, width=4)
    draw.line((int(.445*1920), 140, int(.445*1920), 750), fill=BLUE, width=3)
    draw.line((int(.555*1920), 140, int(.555*1920), 750), fill=BLUE, width=3)
    panel(result, (0, 820, 1920, 1080))
    draw = ImageDraw.Draw(result)
    text(draw, (45, 840), "STUDIO / PASS 5 of 5", 64, BLUE)
    text(draw, (45, 925), f"BBox {gates['G1_framing']['bbox_fraction']:.4f} in [0.07, 0.22]"
         "  |  blue: 4% crop margin / center band", 43)
    text(draw, (45, 993), "Frame coordinates normalized 0–1  |  seed 17  |  Cycles CPU", 37)
    result.save(HERE / "result.png", dpi=(200, 200))

    # Loop: measured single-edit repair path, not a fabricated agent optimization.
    loop = Image.new("RGB", (1920, 1080), BG)
    draw = ImageDraw.Draw(loop)
    text(draw, (65, 50), "MEASURED REPAIR LOOP + JUDGE SELF-TEST", 64, BLUE)
    old = data["mutants"]["off_center"]
    count = sum(g["pass"] for g in old["gates"].values())
    text(draw, (65, 135), "Repair: hero_x 1.6 m → 0 m", 46)
    draw.line((100, 465, 890, 465), fill=WHITE, width=3)
    draw.line((100, 235, 100, 465), fill=WHITE, width=3)
    for x, value in ((270, count), (680, 5)):
        y = 465 - 42 * value
        draw.rectangle((x-55, y, x+55, 465), fill=BLUE if value == 5 else ORANGE)
        text(draw, (x-50, y-65), f"{value}/5", 46)
    draw.line((110, 255, 870, 255), fill=BLUE, width=3)
    text(draw, (110, 510), "Failed scene        Repaired scene", 42)
    text(draw, (65, 625), f"PASS line = 5 gates. Kill rate {data['killed']}/{data['total']}.", 50)
    for i, (name, verdict) in enumerate(data["mutants"].items()):
        y = 190 + i * 72
        draw.rectangle((1010, y, 1080, y+55), fill=BLUE if not verdict["pass"] else ORANGE)
        text(draw, (1110, y), name.replace("_", " "), 45)
    text(draw, (65, 965), "Source: selftest.json, seed 17. Known mutant → good, not inferred history.", 35)
    loop.save(HERE / "loop.png", dpi=(200, 200))
    return data, capture, render_rows


def video_props(data):
    good = data["good"]["gates"]
    gates = [
        ("Hero centered and in frame", f"box {good['G1_framing']['bbox_fraction']:.4f} of frame, 12/12 poses"),
        ("Highlights not clipped", f"clipped {good['G2_exposure']['clipped_fraction']:.4f}"),
        ("Smooth backdrop sweep", f"max 2nd difference {good['G3_backdrop']['max_second_difference']:.4f}"),
        ("Seamless full turn", f"endpoint difference {good['G4_loop']['endpoint_mean_abs_diff']:.6f}"),
        ("Rim light on products only", f"products +{good['G5_linking']['product_direct_delta']:.4f}, "
                                        f"backdrop +{good['G5_linking']['backdrop_direct_delta']:.4f}"),
    ]
    mutants = [{"name": name, "label": FAILURE_LABELS[name],
                "failed": [not verdict["gates"][gate]["pass"] for gate in good]}
               for name, verdict in data["mutants"].items()]
    return {"gates": [{"label": label, "value": value} for label, value in gates],
            "mutants": mutants, "killed": data["killed"], "total": data["total"]}


def main():
    data, capture, render_rows = prepare_media()
    (MASTER / "props.json").write_text(json.dumps(video_props(data), indent=2) + "\n")
    # Remotion animates real Cycles poses with a measured HUD; ffmpeg only encodes.
    subprocess.run(["npm", "run", "render"], cwd=HERE / "video", check=True)

    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(MASTER / "demo.mp4"),
                    "-an", "-c:v", "libx264", "-threads", "4", "-crf", "18",
                    "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    "-map_metadata", "-1", str(HERE / "demo.mp4")], check=True)
    if (HERE / "demo.mp4").stat().st_size > 8_000_000:
        raise RuntimeError("web video exceeds requested 8 MB")
    entries = []
    compose_command = ("sh media/make_media.sh" if capture["mode"] == "single_sandbox"
                       else "STUDIO_REUSE_SOURCE=1 sh media/make_media.sh")
    descriptions = {"result.png": "actual hero with numeric framing pass line",
                    "loop.png": "measured mutant-to-good repair and kill matrix",
                    "demo.mp4": f"{VIDEO_SECONDS} s real Cycles scene, turntable, light probes and proof"}
    for name, description in descriptions.items():
        path = HERE / name
        entries.append({"file": name, "shows": description,
                        "command": compose_command,
                        "source": ["media/data/selftest.json", "media/source/render.json"],
                        "seed": 17, "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = {"files": entries, "render_command":
                "blender -b --factory-startup --python-exit-code 1 -t 4 "
                "-P media/render.py -- --out media/source --seed 17",
                "render": {"resolution": [1920, 1080], "samples": 8, "threads": 4,
                           "engine": "CYCLES", "device": "CPU"},
                "turntable": {"poses": POSE_COUNT, "poses_per_second": POSES_PER_SECOND,
                              "sampling": "existing animation at quarter-frame steps",
                              "interpolation": "none; actual Cycles renders in pose order",
                              "judge_frames": 12},
                "capture": capture,
                "render_frames": render_rows,
                "tools": {"pillow": "10.2.0", "remotion": "4.0.531",
                          "font": {"file": "DejaVuSans.ttf", "sha256": FONT_SHA256},
                          "blender": data["good"]["blender"],
                          "transfer": "sbx CLI, stdlib base64 chunks",
                          "ffmpeg": subprocess.check_output(
                              ["ffmpeg", "-version"], text=True).splitlines()[0]}}
    manifest["source_sha256"] = {
        str(p.relative_to(HERE.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [HERE.parent / "examples/good/scene.py",
                  *sorted((HERE.parent / "judge").glob("*.py")),
                  *sorted((HERE.parent / "judge").glob("*.sh")),
                  HERE / "render.py", HERE / "compose.py", HERE / "capture.py",
                  HERE / "make_media.sh", HERE / "video/src/Demo.tsx",
                  HERE / "video/package-lock.json", HERE / "data/selftest.json",
                  HERE / "data/transfers.json", HERE / "data/capture.json"]}
    manifest["media_reproducibility"] = (
        "Regenerate the complete frame set in one sandbox run. Source sha256s "
        "identify this capture, not guaranteed byte-identical future PNGs. "
        "The judge requires identical verdict JSON excluding timing.")
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"media: {VIDEO_SECONDS * 30} frames / {VIDEO_SECONDS} s / "
          f"{(HERE/'demo.mp4').stat().st_size} bytes")


if __name__ == "__main__":
    main()
