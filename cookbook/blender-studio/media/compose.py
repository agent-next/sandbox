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
FONT_SHA256 = "ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280"
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


def split_hero():
    image = Image.new("RGB", (1920, 1080), BG)
    image.paste(hero().crop((490, 0, 1450, 1080)), (960, 0))
    return image


def card(title, lines):
    image = split_hero()
    draw = ImageDraw.Draw(image)
    text(draw, (60, 70), title, 80, BLUE)
    for i, line in enumerate(lines):
        text(draw, (60, 230 + 105 * i), line, 64)
    return image


def kill_matrix(data, start):
    image = Image.new("RGB", (1920, 1080), BG)
    draw = ImageDraw.Draw(image)
    text(draw, (65, 35), f"JUDGE PROOF · {data['killed']}/{data['total']} caught", 84, BLUE)
    text(draw, (65, 155), "Deliberately broken versions", 76)
    names = list(data["good"]["gates"])
    for j in range(5):
        text(draw, (970 + 180*j, 245), f"G{j+1}", 96)
        text(draw, (970 + 180*j, 355), ("Frame", "Light", "Sweep", "Loop", "Rim")[j], 48)
    rows = list(data["mutants"].items())[start:start+5]
    for i, (name, verdict) in enumerate(rows):
        y = 435 + 105*i
        text(draw, (65, y), FAILURE_LABELS[name], 76)
        for j, gate in enumerate(names):
            color = BLUE if verdict["gates"][gate]["pass"] else ORANGE
            draw.rounded_rectangle((970+180*j, y+8, 1110+180*j, y+85),
                                   radius=12, fill=color)
    text(draw, (65, 965), "Blue = pass. Orange = fail.", 64)
    return image


def pose_index(output_frame):
    return output_frame * POSES_PER_SECOND // 30 % POSE_COUNT


def main():
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

    shots = []
    hook = hero()
    panel(hook, (0, 0, 1920, 130))
    text(ImageDraw.Draw(hook), (40, 28),
         "An AI agent built this in Blender. A judge checked it.", 64)
    shots.append((60, [hook]))
    shots.append((90, [card("THE BRIEF", [
        "Center the hero", "Keep the highlights", "Use a smooth backdrop",
        "Make a full turn", "Rim light: products only"])]))
    close = hero().crop((490, 190, 1450, 730)).resize(
        (1920, 1080), Image.Resampling.LANCZOS)
    panel(close, (0, 960, 1920, 1080))
    text(ImageDraw.Draw(close), (60, 975), "Red car paint. Real reflections.", 76)
    details = Image.new("RGB", (1920, 1080), BG)
    for x, box in ((0, (100, 400, 650, 950)), (960, (1350, 500, 1900, 1050))):
        details.paste(hero().crop(box).resize((960, 960), Image.Resampling.LANCZOS), (x, 0))
    text(ImageDraw.Draw(details), (60, 975), "Glass and gold. Same scene.", 76)
    shots.append((90, [close, details]))
    poses = []
    for i in range(1, POSE_COUNT+1):
        frame = Image.open(SOURCE / f"frame-{i:02}.png").convert("RGB")
        panel(frame, (0, 960, 1920, 1080))
        text(ImageDraw.Draw(frame), (50, 976), "48 real Cycles poses · 24 poses/s", 64)
        poses.append(frame)
    shots.append((180, poses))
    linking = Image.new("RGB", (1920, 1080), BG)
    for x, name in ((0, "good"), (960, "unlinked_rim")):
        image = Image.open(SOURCE / name / "rim-on.png").convert("RGB")
        linking.paste(image.resize((960, 540), Image.Resampling.NEAREST), (x, 240))
    draw = ImageDraw.Draw(linking)
    text(draw, (60, 55), "The judge isolates the rim light", 80, BLUE)
    text(draw, (50, 830), "Backdrop stays dark:", 68)
    text(draw, (50, 920), "PASS", 84, BLUE)
    text(draw, (1010, 830), "Backdrop lights up:", 68)
    text(draw, (1010, 920), "FAIL", 84, ORANGE)
    good_delta = gates["G5_linking"]["backdrop_direct_delta"]
    bad_delta = data["mutants"]["unlinked_rim"]["gates"]["G5_linking"]["backdrop_direct_delta"]
    text(draw, (360, 954), f"Change: {good_delta:.6f}", 42)
    text(draw, (1320, 954), f"Change: {bad_delta:.6f}", 42)
    before_after = Image.new("RGB", (1920, 1080), BG)
    before_after.paste(hero().resize((960, 540)), (0, 235))
    before_after.paste(Image.open(SOURCE / "unlinked.png").convert("RGB").resize(
        (960, 540)), (960, 235))
    draw = ImageDraw.Draw(before_after)
    text(draw, (60, 55), "Rim light hits only the products", 80, BLUE)
    text(draw, (50, 830), "Products only", 76, BLUE)
    text(draw, (1010, 830), "Hits everything", 76, ORANGE)
    text(draw, (50, 950), "Same scene. Only the rim light changes.", 64)
    shots.append((90, [before_after]))
    shots.append((60, [linking]))

    repair = Image.new("RGB", (1920, 1080), BG)
    repair.paste(Image.open(SOURCE / "off_center/hero.png").convert("RGB").resize((960, 540)),
                 (0, 155))
    repair.paste(hero().resize((960, 540)), (960, 155))
    draw = ImageDraw.Draw(repair)
    text(draw, (40, 35), "Broken → repaired", 84, BLUE)
    text(draw, (55, 740), f"Off-center: {count}/5", 64, ORANGE)
    text(draw, (1040, 740), "Centered: 5/5", 64, BLUE)
    speed = data["timing"]["total_seconds"] / 3
    text(draw, (55, 900), f"Local self-test replay / {speed:.1f}x speed" if
         capture["proof_backend"] == "local pinned Blender" else
         f"Sandbox self-test replay / {speed:.1f}x speed", 64)
    text(draw, (55, 990), f"Measured runtime {data['timing']['total_seconds']:.1f}s · seed 17", 64)
    # Real process rows revealed over the three-second slot.
    repairs = []
    for i in range(data["total"]):
        r = repair.copy()
        name = list(data["mutants"])[i]
        text(ImageDraw.Draw(r), (55, 815), f"Caught: {FAILURE_LABELS[name]}", 64, BLUE)
        repairs.append(r)
    shots.append((90, repairs))
    proof = split_hero()
    draw = ImageDraw.Draw(proof)
    text(draw, (55, 70), "PASS 5/5", 180, BLUE)
    text(draw, (55, 295), "All five checks passed", 76)
    text(draw, (55, 445), f"{data['killed']}/{data['total']} deliberately", 76)
    text(draw, (55, 545), "broken versions caught", 76)
    text(draw, (55, 705), "Same seed. Same verdict.", 64)
    shots.append((90, [proof]))
    shots.append((75, [kill_matrix(data, 0)]))
    shots.append((75, [kill_matrix(data, 5)]))
    end = hero()
    panel(end, (0, 0, 1920, 340))
    text(ImageDraw.Draw(end), (100, 75), "Build it. Check it. Run it.", 84, BLUE)
    text(ImageDraw.Draw(end), (100, 210), "python3 run.py", 82)
    shots.append((60, [end]))
    if sum(duration for duration, _ in shots) != 960:
        raise RuntimeError("storyboard must fill exactly 32 seconds")

    # Stream actual losslessly decoded PNG images, repeated into the 30 fps master.
    command = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", "1920x1080", "-r", "30", "-i", "-", "-an", "-c:v", "libx264",
               "-threads", "4", "-crf", "0", "-preset", "fast", "-pix_fmt", "yuv420p",
               str(MASTER / "demo.mp4")]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for duration, images in shots:
            buffers = [image.tobytes() for image in images]
            for i in range(duration):
                index = pose_index(i) if len(images) == POSE_COUNT else min(
                    len(images)-1, i * len(images) // duration)
                proc.stdin.write(buffers[index])
    finally:
        proc.stdin.close()
    if proc.wait():
        raise RuntimeError("lossless master encode failed")
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
                    "demo.mp4": "32 s real Cycles scene, turntable, light probes and proof"}
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
                              "interpolation": "none; repeats of actual Cycles renders",
                              "judge_frames": 12},
                "capture": capture,
                "render_frames": render_rows,
                "tools": {"pillow": "10.2.0",
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
                  HERE / "make_media.sh", HERE / "data/selftest.json",
                  HERE / "data/transfers.json", HERE / "data/capture.json"]}
    manifest["media_reproducibility"] = (
        "Regenerate the complete frame set in one sandbox run. Source sha256s "
        "identify this capture, not guaranteed byte-identical future PNGs. "
        "The judge requires identical verdict JSON excluding timing.")
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"media: 960 frames / 32 s / {(HERE/'demo.mp4').stat().st_size} bytes")


if __name__ == "__main__":
    main()
