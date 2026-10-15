"""Figures, factual captions and video cut from real Blender render evidence."""
import hashlib
import json
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


def font(size):
    return ImageFont.truetype("DejaVuSans.ttf", size)


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


def card(title, lines):
    image = hero()
    panel(image, (0, 0, 930, 1080))
    draw = ImageDraw.Draw(image)
    text(draw, (60, 70), title, 64, BLUE)
    for i, line in enumerate(lines):
        text(draw, (60, 230 + 105 * i), line, 64)
    return image


def kill_matrix(data):
    image = Image.new("RGB", (1920, 1080), BG)
    draw = ImageDraw.Draw(image)
    text(draw, (65, 40), f"JUDGE PROOF / {data['killed']} OF {data['total']} MUTANTS CAUGHT",
         70, BLUE)
    text(draw, (65, 140), "Blue = PASS. Orange = FAIL. Every row is measured.", 64)
    names = list(data["good"]["gates"])
    for j in range(5):
        text(draw, (1100 + 145*j, 245), f"G{j+1}", 64)
    for i, (name, verdict) in enumerate(data["mutants"].items()):
        y = 315 + 70*i
        text(draw, (65, y), name.replace("_", " "), 64)
        for j, gate in enumerate(names):
            color = BLUE if verdict["gates"][gate]["pass"] else ORANGE
            draw.rectangle((1100+145*j, y+8, 1190+145*j, y+60), fill=color)
    return image


def main():
    MASTER.mkdir(parents=True, exist_ok=True)
    data = json.loads((HERE / "data/selftest.json").read_text())
    if not data["pass"] or data["kill_rate"] != 1:
        raise RuntimeError("cannot publish PASS media from failing evidence")
    gates = data["good"]["gates"]
    render_rows = json.loads((SOURCE / "render.json").read_text())
    if len(render_rows) != 13:
        raise RuntimeError("need 12 actual turntable frames plus unlinked comparison")
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
    text(draw, (65, 155), "Single-setting repair: hero_x 1.6 m → 0 m", 50)
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
    shots.append((60, [hero()]))
    shots.append((120, [card("THE SPEC → RESULT", [
        "Center the hero", "Keep highlights intact", "Make the sweep smooth",
        "Spin exactly 360°", "Link rim to products",
        f"BBox: {gates['G1_framing']['bbox_fraction']:.4f}"])]))
    close = hero().crop((470, 170, 1450, 870)).resize((1920, 1080), Image.Resampling.LANCZOS)
    panel(close, (0, 960, 1920, 1080))
    text(ImageDraw.Draw(close), (60, 975), "REAL CYCLES / RED CAR PAINT CLOSE-UP", 64)
    shots.append((120, [close]))
    poses = []
    for i in range(1, 13):
        frame = Image.open(SOURCE / f"frame-{i:02}.png").convert("RGB")
        panel(frame, (0, 960, 1920, 1080))
        text(ImageDraw.Draw(frame), (50, 976), "REAL TURNTABLE / 12 POSES · 6 fps playback", 64)
        poses.append(frame)
    shots.append((180, poses))
    linking = Image.new("RGB", (1920, 1080), BG)
    for x, name in ((0, "good"), (960, "unlinked_rim")):
        image = Image.open(SOURCE / name / "rim-on.png").convert("RGB")
        linking.paste(image.resize((960, 540), Image.Resampling.NEAREST), (x, 240))
    draw = ImageDraw.Draw(linking)
    text(draw, (60, 55), "DIRECT RIM / PRODUCTS ONLY", 70, BLUE)
    text(draw, (50, 830), "Linked: PASS", 64, BLUE)
    text(draw, (1010, 830), "Unlinked: FAIL", 64, ORANGE)
    good_delta = gates["G5_linking"]["backdrop_direct_delta"]
    bad_delta = data["mutants"]["unlinked_rim"]["gates"]["G5_linking"]["backdrop_direct_delta"]
    text(draw, (50, 940), f"Backdrop Δ {good_delta:.6f}", 64)
    text(draw, (1010, 940), f"Backdrop Δ {bad_delta:.6f}", 64)
    before_after = Image.new("RGB", (1920, 1080), BG)
    before_after.paste(hero().resize((960, 540)), (0, 235))
    before_after.paste(Image.open(SOURCE / "unlinked.png").convert("RGB").resize(
        (960, 540)), (960, 235))
    draw = ImageDraw.Draw(before_after)
    text(draw, (60, 55), "LIGHT LINKING / REAL 1080p A–B RENDERS", 70, BLUE)
    text(draw, (50, 830), "Products-only rim", 64, BLUE)
    text(draw, (1010, 830), "Unlinked rim", 64, ORANGE)
    text(draw, (50, 950), "Next: isolate direct rim light to measure the difference.", 64)
    shots.append((120, [before_after, linking]))

    repair = Image.new("RGB", (1920, 1080), BG)
    repair.paste(Image.open(SOURCE / "off_center/hero.png").convert("RGB").resize((960, 540)),
                 (0, 155))
    repair.paste(hero().resize((960, 540)), (960, 155))
    draw = ImageDraw.Draw(repair)
    text(draw, (40, 45), "MUTANT → REPAIR / REAL SANDBOX PROCESS", 64, BLUE)
    text(draw, (55, 740), f"Off-center: {count}/5", 64, ORANGE)
    text(draw, (1040, 740), "Centered: 5/5", 64, BLUE)
    speed = data["timing"]["total_seconds"] / 3
    text(draw, (55, 900), f"Self-test output replay / {speed:.1f}x speed", 64)
    text(draw, (55, 990), f"Measured runtime {data['timing']['total_seconds']:.1f}s · seed 17", 64)
    # Real process rows revealed over the three-second slot.
    repairs = []
    for i in range(data["total"]):
        r = repair.copy()
        name = list(data["mutants"])[i]
        text(ImageDraw.Draw(r), (55, 815), f"KILLED: {name.replace('_', ' ')}", 64, BLUE)
        repairs.append(r)
    shots.append((90, repairs))
    proof = card("PASS / 5 OF 5 GATES", [
        "5 / 5 numeric gates",
        f"{data['killed']} / {data['total']} mutants caught",
        "Same seed: same JSON",
        "Judge hashes unchanged",
        f"Loop diff: {gates['G4_loop']['endpoint_mean_abs_diff']:.6f}",
        f"Exposure mean: {gates['G2_exposure']['mean_display_luminance']:.4f}"])
    matrix = kill_matrix(data)
    shots.append((120, [proof, matrix]))
    end = hero()
    panel(end, (0, 0, 1920, 340))
    text(ImageDraw.Draw(end), (100, 75), "YOUR AGENT. REAL BLENDER. A REAL JUDGE.", 68, BLUE)
    text(ImageDraw.Draw(end), (100, 210), "python3 run.py", 82)
    shots.append((90, [end]))

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
                index = (i // 5) % len(buffers) if len(images) == 12 else min(
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
    descriptions = {"result.png": "actual hero with numeric framing pass line",
                    "loop.png": "measured mutant-to-good repair and kill matrix",
                    "demo.mp4": "30 s real Cycles scene, turntable, light probes and proof"}
    for name, description in descriptions.items():
        path = HERE / name
        entries.append({"file": name, "shows": description,
                        "command": "sh media/make_media.sh",
                        "source": ["media/data/selftest.json", "media/source/render.json"],
                        "seed": 17, "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = {"files": entries, "render_command":
                "blender -b --factory-startup --python-exit-code 1 -t 4 "
                "-P media/render.py -- --out media/source --seed 17",
                "render": {"resolution": [1920, 1080], "samples": 8, "threads": 4,
                           "engine": "CYCLES", "device": "CPU"},
                "render_frames": render_rows,
                "tools": {"pillow": "10.2.0",
                          "blender": data["good"]["blender"],
                          "e2b": "2.40.0 (optional transfer only)",
                          "ffmpeg": subprocess.check_output(
                              ["ffmpeg", "-version"], text=True).splitlines()[0]}}
    manifest["source_sha256"] = {
        str(p.relative_to(HERE.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [HERE.parent / "examples/good/scene.py",
                  *sorted((HERE.parent / "judge").glob("*.py")),
                  *sorted((HERE.parent / "judge").glob("*.sh")),
                  HERE / "render.py", HERE / "compose.py", HERE / "capture.py",
                  HERE / "make_media.sh", HERE / "data/selftest.json",
                  HERE / "data/transfers.json"]}
    manifest["media_reproducibility"] = (
        "Regenerate the complete frame set in one sandbox run. Source sha256s "
        "identify this capture, not guaranteed byte-identical future PNGs. "
        "The judge requires identical verdict JSON excluding timing.")
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"media: 900 frames / 30 s / {(HERE/'demo.mp4').stat().st_size} bytes")


if __name__ == "__main__":
    main()
