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
CLIP_S = 2.0
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


def collect(run_dirs: list[Path]) -> dict[str, dict]:
    final: dict[str, dict] = {}
    for run in run_dirs:
        for res in sorted(run.glob("shard-*/out/results.json")):
            for r in json.loads(res.read_text()):
                if not r["id"].startswith("ctl-"):
                    stem = r["id"].removesuffix(".html")
                    final[r["id"]] = dict(r, png=res.parent / f"{stem}.png", mp4=res.parent / f"{stem}.mp4")
    visual = json.loads((HERE / "visual.json").read_text())
    notes = json.loads((HERE / "notes.json").read_text())
    for k, r in final.items():
        r["visual"] = visual.get(k, "RENDERED" if r["verdict"] == "PASS" else "NO_FRAME")
        r["note"] = notes.get(k, "")
    return dict(sorted(final.items()))


def result_png(final: dict[str, dict], out: Path) -> None:
    cols, tw, th, cap = 6, 480, 300, 34
    rows = (len(final) + cols - 1) // cols
    head = 110
    sheet = Image.new("RGB", (cols * tw, head + rows * (th + cap)), (16, 18, 22))
    d = ImageDraw.Draw(sheet)
    n = sum(r["visual"] == "RENDERED" for r in final.values())
    d.text((20, 18), f"img2threejs showcase on agent-next sandboxes: {n}/{len(final)} rendered", font=font(40), fill="white")
    d.text((20, 68), "headless Chromium, software WebGL, 4 vCPU / 16 GB sandboxes; verdict per tile "
                     "(green rendered, amber still loading, red no frame)", font=font(22), fill=(200, 200, 200))
    for i, (k, r) in enumerate(final.items()):
        x, y = (i % cols) * tw, head + (i // cols) * (th + cap)
        if r["png"].exists():
            im = Image.open(r["png"]).convert("RGB")
            im.thumbnail((tw - 8, th - 4))
            sheet.paste(im, (x + 4, y + cap))
        d.rectangle([x + 4, y + 4, x + tw - 4, y + cap - 4], fill=COLOURS[r["visual"]])
        d.text((x + 10, y + 7), f"{k}  {r['visual']}  {r['ms'] / 1000:.0f} s" + (" (2D)" if r["note"] else ""),
               font=font(16), fill="white")
    sheet.save(out, dpi=(200, 200))


def demo_mp4(final: dict[str, dict], master: Path, web: Path) -> None:
    shown = [(k, r) for k, r in final.items() if r["visual"] == "RENDERED"]
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, (k, r) in enumerate(shown):
            label = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(label)
            d.rectangle([0, H - 64, W, H], fill=(0, 0, 0, 190))
            d.text((24, H - 52), f"{i + 1}/{len(shown)}  {k}  rendered in {r['ms'] / 1000:.0f} s on a CPU sandbox"
                   + (f"  ({r['note']})" if r["note"] else ""),
                   font=font(30), fill="white")
            lp = Path(tmp, f"label{i}.png")
            label.save(lp)
            src = ["-sseof", f"-{CLIP_S}", "-i", str(r["mp4"])] if r["mp4"].exists() else \
                  ["-loop", "1", "-t", str(CLIP_S), "-i", str(r["png"])]
            part = Path(tmp, f"p{i:02d}.mkv")
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *src, "-i", str(lp), "-filter_complex",
                            f"[0:v]crop=iw*{VIEWPORT}:ih:0:0,scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                            f"fps=30,setsar=1[v];[v][1:v]overlay=0:0", "-t", str(CLIP_S),
                            "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv444p", str(part)], check=True)
            parts.append(part)
        lst = Path(tmp, "list.txt")
        lst.write_text("".join(f"file '{p}'\n" for p in parts))
        master.parent.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
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
    final = collect(runs)
    result_png(final, HERE / "result.png")
    demo_mp4(final, HERE / "master" / "demo.mp4", HERE / "demo.mp4")
    sources = {k: {"verdict": r["verdict"], "visual": r["visual"], "seconds": round(r["ms"] / 1000),
                   "clip": "recorded" if r["mp4"].exists() else "still", "note": r["note"]} for k, r in final.items()}
    manifest = {
        "result.png": {"shows": "final screenshot of every target with its verdict", "sha256": sha(HERE / "result.png")},
        "demo.mp4": {"shows": f"last {CLIP_S:.0f} s of each rendered target's recording (still frame where that run "
                              "kept no clip)", "sha256": sha(HERE / "demo.mp4")},
        "command": "python3 media/make_media.py " + " ".join(a.name for a in runs),
        "targets": sources,
    }
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{len(final)} targets, {sum(v['visual'] == 'RENDERED' for v in sources.values())} rendered; "
          f"demo.mp4 {(HERE / 'demo.mp4').stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
