"""Build media/ from run.py output directories.

usage: python3 media/make_media.py RUN_DIR [RUN_DIR ...]   (oldest first; a later run's verdict wins)
needs: Pillow, ffmpeg. Writes result.png, demo.mp4, MANIFEST.json here and a lossless master/demo.mp4.

Each target's tile and clip come from the run that gave its final verdict. A clip is used only when that
same run recorded one; otherwise the final screenshot is shown as a still, so no clip from an earlier,
unfinished render stands in for the verdict. notes.json labels targets that are not Three.js. visual.json holds the by-eye verdicts (checked by two models)
and overrides the automatic gate where they differ.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
# storyboard (media/STORYBOARD.md): hook, input -> output, sped-up process, highlights, every result, proof, end card
HERO, HERO_S = "doraemon-house", 3.0  # bright first frame for the video gate
INPUT_S = 4.0
PROCESS, WINDOW_S, SPEED = "tropical-island", 450, 50  # page load, loading overlay, scene lit; checked by eye
# (later in the recording the page is resized for the screenshot)
HIGHLIGHTS = ["electric-mouse-mascot", "crown-chest", "sony-wf1000xm3", "snowy-village", "prs-ocean", "mars-cat",
              "monster", "regret-warrior-reconstruction", "warhauler"]
CLIP_S = 2.5
GRID_S, PROOF_S, END_S = 2.5, 5.0, 3.0  # each 4x3 page of results, the proof card, the static end card
HEADER = 0.12  # top of the viewport holding the page's title, cropped off in the clips
ZOOM = 0.25  # push-in over each clip, added in post
W, H = 1920, 1080
VIEWPORT = 872 / 1280  # the 3D viewport; the recorder leaves the inspector panel grey
COLOURS = {"RENDERED": (46, 160, 67), "LOADING": (219, 145, 22), "NO_FRAME": (207, 34, 46)}


def font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def collect(run_dirs: list[Path]) -> tuple[dict[str, dict], list[dict]]:
    final: dict[str, dict] = {}
    controls: list[dict] = []
    for run in run_dirs:
        for res in sorted(run.glob("shard-*/out/results.json")):
            for r in json.loads(res.read_text()):
                if r["id"].startswith("ctl-"):
                    controls.append(r)
                else:
                    stem = r["id"].removesuffix(".html")
                    final[r["id"]] = dict(r, png=res.parent / f"{stem}.png", mp4=res.parent / f"{stem}.mp4")
    visual = json.loads((HERE / "visual.json").read_text())
    notes = json.loads((HERE / "notes.json").read_text())
    for k, r in final.items():
        r["visual"] = visual.get(k, "RENDERED" if r["verdict"] == "PASS" else "NO_FRAME")
        r["note"] = notes.get(k, "")
    return dict(sorted(final.items())), controls


def result_png(final: dict[str, dict], out: Path) -> None:
    cols, tw, th, cap = 6, 480, 300, 40
    rows = (len(final) + cols - 1) // cols
    head = 190
    sheet = Image.new("RGB", (cols * tw, head + rows * (th + cap)), (16, 18, 22))
    d = ImageDraw.Draw(sheet)
    n = sum(r["visual"] == "RENDERED" for r in final.values())
    d.text((20, 18), f"img2threejs showcase on agent-next sandboxes: {n}/{len(final)} rendered", font=font(72), fill="white")
    d.text((20, 112), "headless Chromium, software WebGL, 4 vCPU / 16 GB sandboxes; verdict per tile "
                     "(green rendered, amber still loading, red no frame)", font=font(36), fill=(200, 200, 200))
    for i, (k, r) in enumerate(final.items()):
        x, y = (i % cols) * tw, head + (i // cols) * (th + cap)
        if r["png"].exists():
            im = Image.open(r["png"]).convert("RGB")
            im.thumbnail((tw - 8, th - 4))
            sheet.paste(im, (x + 4, y + cap))
        d.rectangle([x + 4, y + 4, x + tw - 4, y + cap - 4], fill=COLOURS[r["visual"]])
        d.text((x + 10, y + 8), f"{k}  {r['ms'] / 1000:.0f} s" + (" (2D)" if r["note"] else "")
               + ("" if r["visual"] == "RENDERED" else f"  {r['visual']}"),
               font=font(21), fill="white")
    sheet.save(out, dpi=(200, 200))


def text_card(lines: list[tuple[str, int, tuple | str]], out: Path, art: Path | None = None) -> None:
    """A card of (text, size, colour) lines on the left; an optional picture fills the right."""
    im = Image.new("RGB", (W, H), (16, 18, 22))
    if art:
        pic = Image.open(art).convert("RGB")
        pic.thumbnail((W - 1020, H - 80))
        im.paste(pic, (W - pic.width - 40, (H - pic.height) // 2))
    d = ImageDraw.Draw(im)
    y = (H - sum(size + 30 for _, size, _ in lines)) // 2
    for t, size, c in lines:
        assert 80 + font(size).getlength(t) <= (1000 if art else W - 40), f"card text too wide: {t}"
        d.text((80, y), t, font=font(size), fill=c)
        y += size + 30
    im.save(out)


def proof_lines(final: dict[str, dict], controls: list[dict]) -> list[tuple[str, int, tuple | str]]:
    v = [r["visual"] for r in final.values()]
    pos = [c for c in controls if c["id"] == "ctl-pos.html"]
    neg = [c for c in controls if c["id"] == "ctl-neg.html"]
    assert pos and neg and all(c["verdict"] == "PASS" for c in pos) and all(c["verdict"] == "FAIL" for c in neg)
    grey = (200, 200, 200)
    lines = [(f"{v.count('RENDERED')} of {len(v)} rendered", 120, COLOURS["RENDERED"])]
    lines += [(f"{k}: still loading after {r['ms'] / 1000:.0f} s" if r["visual"] == "LOADING" else
               f"{k}: no frame in {r['ms'] / 60000:.0f} min", 56, COLOURS[r["visual"]])
              for k, r in final.items() if r["visual"] != "RENDERED"]
    lines += [("judge: screenshot pixels + loading overlay, then by eye", 46, "white"),
              (f"control on all {len(pos)} sandboxes: WebGL triangle PASS, "
               f"luma std {min(c['canvas']['lumaStd'] for c in pos):g}", 40, grey),
              (f"control on all {len(neg)} sandboxes: empty canvas FAIL, "
               f"luma std {max(c['canvas']['lumaStd'] for c in neg):g}", 40, grey)]
    return lines


def grid_pages(final: dict[str, dict], tmp: Path) -> list[Path]:
    """result.png split into phone-readable 4x3 pages: the 3D viewport of each target with its verdict."""
    cols, rows, cap = 4, 3, 44
    tw, th = W // cols, H // rows
    items, pages = list(final.items()), []
    for start in range(0, len(items), cols * rows):
        im = Image.new("RGB", (W, H), (16, 18, 22))
        d = ImageDraw.Draw(im)
        page = items[start:start + cols * rows]
        y0 = (rows - (len(page) + cols - 1) // cols) * th // 2
        for i, (k, r) in enumerate(page):
            x, y = (i % cols) * tw, y0 + (i // cols) * th
            if r["png"].exists():
                shot = Image.open(r["png"]).convert("RGB")
                shot = shot.crop((0, 0, round(shot.width * VIEWPORT), shot.height))
                shot.thumbnail((tw - 6, th - cap))
                im.paste(shot, (x + (tw - shot.width) // 2, y + cap))
            d.rectangle([x + 3, y + 3, x + tw - 3, y + cap - 3], fill=COLOURS[r["visual"]])
            d.text((x + 10, y + 8), f"{k.removesuffix('.html')}  {r['ms'] / 1000:.0f} s"
                   + ("" if r["visual"] == "RENDERED" else f"  {r['visual']}"), font=font(25), fill="white")
        pages.append(tmp / f"grid{len(pages)}.png")
        im.save(pages[-1])
    return pages


def still(png: Path, seconds: float, out: Path) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-t", str(seconds), "-i", str(png), "-vf",
                    f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x101216,"
                    "fps=30,setsar=1", "-t", str(seconds), "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv444p",
                    str(out)], check=True)


def clip(r: dict, seconds: float, lines: list[str], size: int, tmp: Path, out: Path) -> None:
    """The 3D viewport (page header cropped off) above a caption band, on a blurred copy of itself;
    a slow push-in is added in post."""
    band = len(lines) * (size + 22) + 40
    label = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(label)
    d.rectangle([0, H - band, W, H], fill=(10, 12, 16, 255))
    for i, t in enumerate(lines):
        assert font(size).getlength(t) <= W - 96, f"caption too wide: {t}"
        d.text((48, H - band + 20 + i * (size + 22)), t, font=font(size), fill="white")
    lp = tmp / f"{out.stem}.png"
    label.save(lp)
    src = ["-sseof", f"-{seconds}", "-i", str(r["mp4"])] if r["mp4"].exists() else \
          ["-loop", "1", "-t", str(seconds), "-i", str(r["png"])]
    frames, top = round(seconds * 30), H - band
    z = f"(1+{ZOOM}*n/{frames})"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *src, "-i", str(lp), "-filter_complex",
                    f"[0:v]crop=iw*{VIEWPORT}:ih*{1 - HEADER}:0:ih*{HEADER},fps=30,setsar=1,split[a][b];"
                    f"[a]scale={W}:{top}:force_original_aspect_ratio=increase,crop={W}:{top},gblur=sigma=40,"
                    f"eq=brightness=-0.12[bg];"
                    f"[b]scale=-2:{top},scale=iw*{z}:-2:eval=frame,crop=iw/{z}:ih/{z}[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2,pad={W}:{H}:0:0[v];[v][1:v]overlay=0:0",
                    "-t", str(seconds), "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv444p", str(out)], check=True)


def process_clip(r: dict, tmp: Path, out: Path) -> None:
    """The first WINDOW_S of one target's recording, from page load to the lit scene, at SPEED x."""
    seconds = WINDOW_S / SPEED
    caption = f"{PROCESS} loading in a sandbox: its first {WINDOW_S} s at {SPEED}x speed"
    label = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(label)
    d.rectangle([0, H - 116, W, H], fill=(10, 12, 16, 255))
    assert font(50).getlength(caption) <= W - 96, caption
    d.text((48, H - 92), caption, font=font(50), fill="white")
    label.save(tmp / "process.png")
    top = H - 116
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(r["mp4"]), "-i", str(tmp / "process.png"),
                    "-filter_complex",
                    f"[0:v]trim=0:{WINDOW_S},setpts=PTS/{SPEED},crop=iw*{VIEWPORT}:ih:0:0,fps=30,scale=-2:{top},"
                    f"pad={W}:{H}:(ow-iw)/2:0:color=0x101216,setsar=1[v];[v][1:v]overlay=0:0",
                    "-t", str(seconds), "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv444p", str(out)], check=True)


def demo_mp4(final: dict[str, dict], controls: list[dict], master: Path, web: Path) -> None:
    n = sum(r["visual"] == "RENDERED" for r in final.values())
    grey = (200, 200, 200)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        parts = [t / "p00.mkv"]
        clip(final[HERO], HERO_S, [f"{len(final)} web 3D scenes, rendered in cloud sandboxes",
                                   f"with no GPU: {n} of {len(final)} rendered"], 54, t, parts[0])
        text_card([("input: one repo, one command", 46, "white"),
                   ("$ python3 run.py", 60, COLOURS["RENDERED"]),
                   ("8 sandboxes, 4 vCPU / 16 GB each", 36, grey),
                   ("clone img2threejs-showcase", 36, grey), ("npm ci, vite build", 36, grey),
                   ("headless Chromium, software WebGL", 36, grey),
                   (f"output: {len(final)} screenshots + clips", 46, "white")], t / "input.png", HERE / "result.png")
        parts.append(t / "input.mkv")
        still(t / "input.png", INPUT_S, parts[-1])
        parts.append(t / "process.mkv")
        process_clip(final[PROCESS], t, parts[-1])
        for i, k in enumerate(HIGHLIGHTS, 1):
            r = final[k]
            assert r["visual"] == "RENDERED", k
            parts.append(t / f"p{i:02d}.mkv")
            clip(r, CLIP_S, [f"{k}  ·  first frame after {r['ms'] / 1000:.0f} s"], 54, t, parts[-1])
        for page in grid_pages(final, t):
            parts.append(page.with_suffix(".mkv"))
            still(page, GRID_S, parts[-1])
        text_card(proof_lines(final, controls), t / "proof.png")
        parts.append(t / "proof.mkv")
        still(t / "proof.png", PROOF_S, parts[-1])
        text_card([("Ask your agent:", 54, grey),
                   ("Build the img2threejs showcase in sandboxes,", 56, "white"),
                   ("render every demo headless, and tell me", 56, "white"),
                   ("which ones render.", 56, "white"),
                   ("", 30, grey),
                   ("or run:  python3 cookbook/img2threejs-showcase/run.py", 46, COLOURS["RENDERED"]),
                   ("github.com/agent-next/sandbox", 46, grey)], t / "end.png")
        parts.append(t / "end.mkv")
        still(t / "end.png", END_S, parts[-1])
        (t / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
        master.parent.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(t / "list.txt"),
                        "-c", "copy", str(master)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(master), "-c:v", "libx264", "-crf", "18",
                    "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(web)], check=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    runs = [Path(a) for a in sys.argv[1:]]
    if not runs:
        print(__doc__)
        return 2
    final, controls = collect(runs)
    result_png(final, HERE / "result.png")
    demo_mp4(final, controls, HERE / "master" / "demo.mp4", HERE / "demo.mp4")
    sources = {k: {"verdict": r["verdict"], "visual": r["visual"], "seconds": round(r["ms"] / 1000),
                   "clip": "recorded" if r["mp4"].exists() else "still", "note": r["note"]} for k, r in final.items()}
    manifest = {
        "result.png": {"shows": "final screenshot of every target with its verdict", "sha256": sha(HERE / "result.png")},
        "demo.mp4": {"shows": "storyboard in media/STORYBOARD.md: " + f"{HERO} ({HERO_S:g} s); the command and pipeline "
                              f"beside result.png; the first {WINDOW_S} s of the {PROCESS} recording at {SPEED}x speed; the last "
                              f"{CLIP_S:g} s of {len(HIGHLIGHTS)} highlight recordings (blurred backdrop and a {ZOOM:.0%} "
                              "push-in added in post); every target on 4x3 pages; the verdicts and controls; the "
                              "launch prompt", "sha256": sha(HERE / "demo.mp4")},
        "command": "python3 media/make_media.py " + " ".join(a.name for a in runs),
        "targets": sources,
    }
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{len(final)} targets, {sum(v['visual'] == 'RENDERED' for v in sources.values())} rendered; "
          f"demo.mp4 {(HERE / 'demo.mp4').stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
