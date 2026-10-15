#!/usr/bin/env python3
"""Real rendered frames + measured JSON -> figures and lossless storyboard."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

MEDIA = Path(__file__).resolve().parent
DEMO = MEDIA.parent
DATA, WORK = MEDIA / "data", MEDIA / "work"
sys.path.insert(0, str(DEMO / "judge"))
from mutants import INTENDED
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BG, INK, MUTED, GREEN, ORANGE, BLUE = (
    "#101827", "#f4f1e8", "#b5becf", "#52d9b0", "#ffad66", "#56b4e9")
W, H = 1920, 1080


def load(name):
    return json.loads((DATA / name).read_text())


def write(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True)+"\n")


def text(im, xy, value, size=64, colour=INK, bold=False):
    ImageDraw.Draw(im).text(xy, str(value), font=ImageFont.truetype(BOLD if bold else FONT, size),
                           fill=colour, stroke_width=0)


def canvas(colour=BG):
    return Image.new("RGB", (W, H), colour)


def panel(im, box, colour):
    ImageDraw.Draw(im).rounded_rectangle(box, radius=18, fill=colour)


def movie_frame(index):
    return Image.open(WORK / f"edit-{max(1,min(225,index+1)):03d}.png").convert("RGB")


def paste_fit(im, frame, box):
    x, y, w, h = box
    im.paste(frame.resize((w, h), Image.Resampling.LANCZOS), (x, y))


def metric(im, xy, label, value, limit, width=800):
    x, y = xy
    text(im, (x, y), label, 64, MUTED)
    text(im, (x, y+70), value, 110, GREEN, True)
    text(im, (x, y+200), limit, 64, INK)
    ImageDraw.Draw(im).line((x, y+280, x+width, y+280), fill="#344155", width=2)


def summarize():
    full = json.loads((WORK / "selftest-full.json").read_text())
    write(DATA / "selftest.json", {
        "deterministic": full["deterministic"], "intact": full["intact"],
        "mutants": {n: {"killed": r["killed"], "intended": r["intended"],
                        "failed_gate": r["verdict"]["failed_gate"]}
                    for n, r in full["mutants"].items()}})


def figure(v, f):
    im = canvas()
    text(im, (65, 35), "PREMIERE, OPEN SOURCE", 74, INK, True)
    text(im, (65, 130), "MLT renders. A second toolchain decides.", 52, MUTED)
    paste_fit(im, movie_frame(112), (65, 240, 1000, 562))
    text(im, (65, 840), "225 frames checked / 0 EDL mismatches", 46)
    text(im, (65, 920), "Barcode + moving test pattern + exact logo window", 32, MUTED)
    g = v["gates"]
    d = ImageDraw.Draw(im)
    x0, x1, top = 1210, 1820, 270
    d.line((x0+0.8*(x1-x0), top-20, x0+0.8*(x1-x0), top+520), fill=ORANGE, width=4)
    text(im, (1190, 205), "Error / pass limit", 46)
    ratios = [
        ("Dissolve ramp", g["dissolve"]["measured"], .20),
        ("Logo on error", 1-g["logo"]["measured"]["min_on"], .15),
        ("Logo off score", g["logo"]["measured"]["max_off"], .30),
        ("Loudness error", abs(g["loudness"]["measured"]["integrated_lufs"]+16), 1),
    ]
    for j, (label, measured, limit) in enumerate(ratios):
        y = top+j*105
        text(im, (1120, y), label, 35)
        width = max(3, int((x1-x0)*.8*measured/limit))
        d.rectangle((x0, y+50, x0+width, y+78), fill=BLUE)
        text(im, (x0+width+15, y+38), f"{measured/limit:.4f}", 34, INK)
    d.line((x0, 760, x1, 760), fill=MUTED, width=2)
    text(im, (x0-15, 770), "0", 34, MUTED)
    text(im, (x0+int(.8*(x1-x0))-15, 770), "1", 34, ORANGE)
    text(im, (1160, 835), "PASS LINE: ratio <= 1", 40, ORANGE)
    text(im, (1160, 910), f'Duck: {g["ducking"]["measured"]:.2f} dB >= 8', 44, GREEN)
    im.save(MEDIA / "result.png", dpi=(200, 200))


def loop_figure(v, matrix):
    im = canvas("#f4f1e8")
    text(im, (65, 45), "THE JUDGE MUST SAY NO", 74, BG, True)
    text(im, (65, 145), "Measured builder history, not an invented autonomous run", 42, "#344155")
    attempts = load("history.json")
    d = ImageDraw.Draw(im)
    labels = []
    for i, item in enumerate(attempts):
        passed = sum(g["pass"] for g in item["gates"].values())
        x = 130+i*295
        y = 650-int(passed/9*370)
        d.rectangle((x, y, x+140, 650), fill="#0072b2" if item["passed"] else "#d55e00")
        text(im, (x, 670), f"Edit {i+1}", 40, BG)
        text(im, (x, y-60), f"{passed}/9", 40, BG)
        labels.append(item.get("failed_gate") or "PASS")
        text(im, (x-15, 740), labels[-1], 32, BG)
    d.line((80, 280, 970, 280), fill="#009e73", width=4)
    text(im, (640, 215), "PASS = 9 gates", 32, "#007354")
    text(im, (1100, 245), "SELF-TEST", 60, BG, True)
    for i, name in enumerate(INTENDED):
        item = matrix["mutants"][name]
        text(im, (1110, 330+i*48), name.replace("_", " "), 30, BG)
        d.rectangle((1730, 339+i*48, 1810, 365+i*48),
                    fill="#009e73" if item["killed"] else "#d55e00")
    text(im, (100, 920), "Seed 1 / real grade history", 44, BG)
    text(im, (1100, 930), f'{sum(m["killed"] for m in matrix["mutants"].values())}/11 rejected', 54, "#007354")
    im.save(MEDIA / "loop.png", dpi=(200, 200))


def shot(t, verdict, measurements, matrix, bad):
    g = verdict["gates"]
    def readout(im, index, xy):
        code = measurements["decoded"][index]
        if 100 <= index <= 124:
            label = f"OUT {index:03d} / B {measurements['weights'][index-100]:.3f}"
        else:
            label = f"OUT {index:03d} = {'ABC'[code[0]]}:{code[1]:03d}"
        x, y = xy
        panel(im, (x-20, y-10, x+890, y+95), BG)
        text(im, (x, y), label, 64, GREEN, True)
    if t < 2:
        index = int(t*25)
        im = movie_frame(index).resize((W, H), Image.Resampling.LANCZOS)
        panel(im, (40, 40, 1880, 250), BG)
        text(im, (80, 60), "AN AI AGENT EDITED THIS VIDEO", 78, INK, True)
        text(im, (80, 160), "and a checker verified every frame", 60, MUTED)
        panel(im, (1290, 780, 1850, 925), "#0b6e4f")
        text(im, (1325, 810), "PASS 225/225", 66, INK, True)
        panel(im, (70, 780, 1250, 925), BG)
        text(im, (110, 805), "THE CUT. EVERY FRAME.", 78, INK, True)
        readout(im, index, (110, 300))
        return im
    if t < 5:
        im = canvas("#f4f1e8")
        text(im, (65, 55), "225 FRAMES.", 96, BG, True)
        text(im, (65, 170), "ZERO GUESSWORK.", 96, BG, True)
        index = int((t-2)*25)
        paste_fit(im, movie_frame(index), (760, 360, 1120, 630))
        readout(im, index, (800, 850))
        for j, line in enumerate(["1280 x 720 / 25 fps", "One 25-frame dissolve", "Logo: frames 0-99", "Music duck >= 8 dB"]):
            text(im, (65, 400+j*120), line, 64, BG)
        return im
    if t < 8:
        im = canvas("#23372f")
        text(im, (65, 40), "A > DISSOLVE > B > C", 82, INK, True)
        for i, name in enumerate("abc"):
            source = Image.open(WORK / f"source-{name}.png")
            paste_fit(im, source, (65+i*610, 190, 570, 320))
            text(im, (90+i*610, 200), name.upper(), 72, INK, True)
        index = 100+int((t-5)*25)
        paste_fit(im, movie_frame(index), (500, 560, 920, 518))
        readout(im, index, (520, 960))
        text(im, (65, 660), "SOURCE", 64)
        text(im, (65, 750), "TO CUT", 64)
        return im
    if t < 13:
        i = min(124, 100+int((t-8)*5))
        im = movie_frame(i).resize((W, H), Image.Resampling.LANCZOS)
        panel(im, (0, 100, W, 310), BG)
        text(im, (65, 115), "25 FRAMES. ONE DISSOLVE.", 78, INK, True)
        text(im, (65, 220), f'Frame {i} / B weight {measurements["weights"][i-100]:.3f}', 64, GREEN)
        panel(im, (60, 885, 1080, 1010), BG)
        text(im, (90, 910), "0.2x speed / real frames", 64)
        return im
    if t < 17:
        i = min(224, 195+int((t-13)*6))
        im = canvas("#e5edf3")
        paste_fit(im, movie_frame(i), (0, 300, W, H))
        panel(im, (0, 0, W, 300), BG)
        text(im, (65, 20), "THE CHECKER READS THE PIXELS.", 74, INK, True)
        cid, source = measurements["decoded"][i]
        text(im, (65, 125), f"OUTPUT {i:03d} = CLIP {'ABC'[cid]} : {source:03d}", 80, GREEN, True)
        text(im, (65, 220), "0.24x speed / real output", 64)
        return im
    if t < 21:
        im = canvas("#f4f1e8")
        text(im, (65, 50), "MUSIC DOWN. VOICE THROUGH.", 78, BG, True)
        text(im, (65, 170), "Music volume, measured from the exported audio", 64, "#344155")
        d = ImageDraw.Draw(im)
        inside = measurements["music_inside"]
        outside = measurements["music_outside"]
        base = sum(outside)/len(outside)
        for j, (label, values, colour) in enumerate((
                ("NO VOICE", outside, BLUE), ("VOICE ON", inside, "#009e73"))):
            y = 370+j*220
            rms = math.sqrt(sum(x*x for x in values)/len(values))
            d.rectangle((600, y, 600+int(1050*rms/base), y+100), fill=colour)
            text(im, (65, y+10), label, 68, BG, True)
        x = 600+int(1050*10**(-8/20))
        d.line((x, 550, x, 800), fill="#d55e00", width=6)
        text(im, (65, 855), f'Music {g["ducking"]["measured"]:.1f} dB quieter / needed 8 dB', 68, BG, True)
        text(im, (65, 955), "Orange line: loudest music allowed under voice", 64, "#9c4100")
        return im
    if t < 26:
        im = canvas("#102b27")
        text(im, (65, 45), "PASS: 225 / 225 FRAMES", 82, INK, True)
        text(im, (65, 150), "Measured from the pixels and the audio", 64, GREEN)
        loud = g["loudness"]["measured"]
        metric(im, (65, 310), "Wrong cuts", str(g["edl"]["measured"]), "allowed: 0")
        metric(im, (1030, 310), "Dissolve error", f'{g["dissolve"]["measured"]:.2f}', "allowed: up to 0.20")
        metric(im, (65, 660), "Loudness", "OK", f'{loud["integrated_lufs"]} / target -16')
        metric(im, (1030, 660), "Clipping", "NONE", f'peak {loud["true_peak_dbtp"]} dB')
        return im
    if t < 32:
        i = bad["first"]
        im = canvas()
        text(im, (65, 40), "ONE FRAME OFF? REJECTED.", 82, INK, True)
        text(im, (65, 150), f"Same output frame {i:03d}, two timelines", 64, MUTED)
        for col, (title, colour, code) in enumerate((
                ("GOOD EDIT", GREEN, measurements["decoded"][i]),
                ("OFF-BY-ONE CUT", "#d55e00", bad["decoded"][i]))):
            x = 65+col*930
            frame = Image.open((WORK if col == 0 else WORK / "bad") / f"edit-{i+1:03d}.png")
            paste_fit(im, frame, (x, 260, 860, 484))
            ImageDraw.Draw(im).rectangle((x-6, 254, x+866, 750), outline=colour, width=12)
            text(im, (x, 780), title, 64, colour, True)
            text(im, (x, 870), f"CLIP {'ABC'[code[0]]} : {code[1]:03d}", 72, INK, True)
        text(im, (65, 975), f'Checker: {bad["verdict"]["gates"]["edl"]["measured"]} wrong cuts / FAIL', 64, "#d55e00", True)
        return im
    if t < 36:
        im = canvas("#f4f1e8")
        text(im, (65, 45), "11 / 11 BAD EDITS REJECTED", 82, BG, True)
        names = [(name, matrix["mutants"][name]) for name in INTENDED]
        for j, (name, item) in enumerate(names):
            col, row = (0, j) if j < 6 else (1, j-6)
            x, y = 65+col*960, 230+row*130
            label = name.replace("_", " ")
            text(im, (x, y), label, 64, BG, True)
            text(im, (x, y+65), f'REJECT / {item["failed_gate"]}', 64, "#007354")
        return im
    im = canvas()
    text(im, (100, 200), "PREMIERE, OPEN SOURCE", 88, INK, True)
    text(im, (100, 360), "Write the timeline. Prove the cut.", 70, GREEN)
    text(im, (100, 610), "python3", 80, INK, True)
    text(im, (100, 720), "cookbook/video-edit-mlt/run.py", 76, INK, True)
    text(im, (100, 925), "Disposable sandbox. Independent judge.", 64, MUTED)
    return im


def build():
    WORK.mkdir(exist_ok=True)
    for path, expected in (
        (FONT, "abdc775b21b1bc470d50c97e790d276f2054b7504e56e5bd3e64f48d68582322"),
        (BOLD, "0d977336a6d5fba34eab8e3199eb218327161b5143749f802982c2bc34df0c96"),
    ):
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise RuntimeError("media: DejaVu font differs from pinned Debian 12 font")
    v, f, matrix = load("verdict.json"), load("frames.json"), load("selftest.json")
    assert v["passed"] and all(m["killed"] for m in matrix["mutants"].values())
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(DATA / "render.mp4"),
                    "-fps_mode", "passthrough", str(WORK / "edit-%03d.png")], check=True)
    for name in "abc":
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i",
                        str(DEMO / f"assets/clip_{name}.mp4"), "-frames:v", "1",
                        str(WORK / f"source-{name}.png")], check=True)
    figure(v, f)
    loop_figure(v, matrix)
    bad = load("offbyone/frames.json") | {"verdict": load("offbyone/verdict.json")}
    assert bad["verdict"]["failed_gate"] == "edl"
    bad["first"] = next(i for i, (a, b) in enumerate(zip(f["decoded"], bad["decoded"])) if a != b)
    (WORK / "bad").mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(DATA / "offbyone/render.mp4"),
                    "-fps_mode", "passthrough", str(WORK / "bad/edit-%03d.png")], check=True)
    with (WORK / "encode.log").open("wb") as err:
        p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo",
                              "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", "30",
                              "-i", "-", "-c:v", "libx264", "-crf", "0",
                              "-preset", "ultrafast", "-threads", "2",
                              str(MEDIA / "master/lossless.mp4")],
                             stdin=subprocess.PIPE, stderr=err)
        for frame in range(40*30):
            p.stdin.write(shot(frame/30, v, f, matrix, bad).tobytes())
        p.stdin.close()
        if p.wait() != 0:
            raise RuntimeError("lossless encode failed; see work/encode.log")
    manifest_spec = importlib.util.spec_from_file_location("result", DEMO.parent / "tools/result.py")
    result = importlib.util.module_from_spec(manifest_spec)
    manifest_spec.loader.exec_module(result)
    commit = (DATA / "commit.txt").read_text().strip()
    prompt = (DEMO / "README.md").read_text().split("## Ask your agent\n", 1)[1].split("\n## ", 1)[0]
    result.write_result(
        MEDIA / "result.json", demo="video-edit-mlt",
        headline="225 video frames checked; 11 of 11 bad edits rejected.",
        verdict="PASS", gates=[{
            "name": n, "pass": g["pass"],
            "measured": json.dumps(g["measured"], sort_keys=True),
            "threshold": json.dumps(g["threshold"], sort_keys=True)}
            for n, g in v["gates"].items()],
        numbers=[{"label": "EDL mismatches", "value": v["gates"]["edl"]["measured"], "unit": "frames",
                  "source": "media/data/verdict.json: gates.edl"},
                 {"label": "Mutants killed", "value": 11, "unit": "/11",
                  "source": "media/data/selftest.json"}],
        hero={"kind": "image", "path": "media/result.png", "caption": "Real edit and numeric pass lines"},
        gallery=[{"kind": "image", "path": "media/loop.png", "caption": "Builder history and mutant matrix"},
                 {"kind": "video", "path": "media/demo.mp4", "poster": "media/result.png",
                  "caption": "40-second edit and independent proof"}],
        launch={"command": "python3 cookbook/video-edit-mlt/run.py", "ask_agent": prompt.strip()},
        receipt="RECEIPT.md", sandbox_commit=commit)


def manifest():
    files = {}
    for name, what, source in (
        ("result.png", "Real edit and pass-limit chart", "data/render.mp4 + data/verdict.json"),
        ("loop.png", "Measured builder history and mutant matrix", "data/history.json + data/selftest.json"),
        ("demo.mp4", "40-second storyboard with real rendered edit", "data/render.mp4 + data/frames.json + data/offbyone"),
        ("result.json", "Result card from grade output", "data/verdict.json + data/selftest.json"),
        ("video_gate.json", "Mechanical video checks", "demo.mp4"),
        ("data/verdict.json", "All measured judge gates", "examples/good/edit.mlt + spec.json"),
        ("data/frames.json", "Every decoded frame and audio-band measurement", "data/render.mp4"),
        ("data/selftest.json", "Intended and observed mutant gates", "RECEIPT.md: RUN-1"),
        ("data/history.json", "Two measured builder iterations", "RECEIPT.md: Development iteration measurements + RUN-1"),
        ("data/run.log", "Verbatim selected fresh-run log lines", "RECEIPT.md: RUN-1"),
        ("data/commit.txt", "Sandbox clone commit", "git rev-parse HEAD"),
        ("REVIEW.json", "Explicitly unperformed blind review panel", "cookbook/tools/video_review_prompt.md"),
    ):
        path = MEDIA / name
        command = "bash cookbook/video-edit-mlt/media/make_media.sh"
        if name in {"data/verdict.json", "data/frames.json"}:
            command = "bash judge/grade.sh examples/good/edit.mlt --seed 1 --export media/data --json media/data/verdict.json"
        elif name in {"data/selftest.json", "data/run.log"}:
            command = "python3 cookbook/video-edit-mlt/run.py --ref sbx/demo-video-edit-mlt (selected stdout)"
        elif name == "data/history.json":
            command = "judge/grade.sh examples/good/edit.mlt --seed 1 (two recorded builder edits)"
        elif name == "data/commit.txt":
            command = "git rev-parse HEAD"
        elif name == "REVIEW.json":
            command = "(not done: two different-family blind video reviewers required)"
        files[name] = {"shows": what, "source": source,
                       "command": command,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    write(MEDIA / "MANIFEST.json", files)


if __name__ == "__main__":
    {"summarize": summarize, "build": build, "manifest": manifest}[sys.argv[1]]()
