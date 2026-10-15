#!/usr/bin/env python3
"""Real rendered frames + measured JSON -> figures and lossless storyboard."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
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


def movie_frame(index):
    return Image.open(WORK / f"edit-{max(1,min(225,index+1)):03d}.png").convert("RGB")


def paste_fit(im, frame, box):
    x, y, w, h = box
    im.paste(frame.resize((w, h), Image.Resampling.LANCZOS), (x, y))


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
    figure(v, f)
    loop_figure(v, matrix)
    bad = load("offbyone/verdict.json")
    assert bad["failed_gate"] == "edl"
    bad_decoded = load("offbyone/frames.json")["decoded"]
    public = MEDIA / "video/public"
    public.mkdir(exist_ok=True)
    shutil.copyfile(DATA / "render.mp4", public / "render.mp4")
    shutil.copyfile(DATA / "offbyone/render.mp4", public / "bad.mp4")
    for name in "abc":
        shutil.copyfile(DEMO / f"assets/clip_{name}.mp4", public / f"clip_{name}.mp4")
    g = v["gates"]
    loud = g["loudness"]["measured"]
    write(WORK / "props.json", {
        "decoded": f["decoded"], "weights": f["weights"],
        "musicInside": f["music_inside"], "musicOutside": f["music_outside"],
        "ducking": g["ducking"]["measured"], "dissolve": g["dissolve"]["measured"],
        "lufs": loud["integrated_lufs"], "peak": loud["true_peak_dbtp"],
        "edl": g["edl"]["measured"], "frames": len(f["decoded"]),
        "gates": [
            {"name": "wrong cuts", "value": str(g["edl"]["measured"])},
            {"name": "dissolve error", "value": f'{g["dissolve"]["measured"]:.3f} (max 0.20)'},
            {"name": "logo on", "value": f'frames 0-99, score {g["logo"]["measured"]["min_on"]:.3f}'},
            {"name": "music under voice", "value": f'-{g["ducking"]["measured"]:.1f} dB'},
            {"name": "loudness", "value": f'{loud["integrated_lufs"]} LUFS (target -16)'},
            {"name": "peak", "value": f'{loud["true_peak_dbtp"]} dB, no clipping'},
            {"name": "format", "value": "1280x720, 25 fps"},
        ],
        "mutants": [{"name": n, "gate": matrix["mutants"][n]["failed_gate"]} for n in INTENDED],
        "bad": {"decoded": bad_decoded, "edl": bad["gates"]["edl"]["measured"],
                "first": next(i for i, (a, b) in enumerate(zip(f["decoded"], bad_decoded)) if a != b)}})
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
