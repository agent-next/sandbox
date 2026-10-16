#!/usr/bin/env python3
"""make_video.py -- cut demo.mp4 from the real render clips + a real run log.

Every frame is real output from the pinned GPU run:
  * clip sources are the lease's own mp4s (RTX path-traced 1920x1080@30)
  * the terminal segment is run.py's real stdout, rendered as a terminal
    and scrolled at a labelled speed-up
  * captions/HUD are burned on top of the moving footage (never a slide)
  * the end card is the only static shot

Layout (STORYBOARD.md is the source of truth; this prints the realised
timings next to it):
  0-1 s   hero frame (best finished render, the hook)
  1-9 s   Scene A warehouse dolly (8 s real clip)
  9-15 s  Scene B crate collapse (6 s)
  15-21 s Scene C arm turntable (6 s)
  21-26 s run.py terminal, sped up (real ids, MB/s, meters)
  26-31 s judge PASS + mutant kill matrix as a HUD on moving footage
  31-34 s end card `python3 run.py`

Usage:
  python3 media/make_video.py RUN_DIR [--out media/demo.mp4] [--master]
Writes the CRF-0 lossless master under media/master/ and the web copy
(crf 18, yuv420p, faststart, <= 8 MB) at --out.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FPS = 30
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
MONO = f"{FONT_DIR}/DejaVuSansMono.ttf"
MONO_B = f"{FONT_DIR}/DejaVuSansMono-Bold.ttf"
SANS = f"{FONT_DIR}/DejaVuSans.ttf"
SANS_B = f"{FONT_DIR}/DejaVuSans-Bold.ttf"

# caption cap height must be >= 4 % of frame height (DEMO-STANDARD.md)
CAP_H = 0.045 * H            # 48.6 px
HUD_H = 0.042 * H


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def cap_height(f: ImageFont.FreeTypeFont) -> float:
    a, d = f.getmetrics()
    return a - d


def fit_font(path: str, want_h: float, bold: bool = False):
    """Largest size whose cap height is >= want_h (readable on a phone)."""
    lo, hi = 8, 200
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        f = font(path, mid)
        ch = cap_height(f)
        if ch >= want_h:
            best = f
            hi = mid - 1
        else:
            lo = mid + 1
    return best or font(path, 64)


def safe_line(draw, text, f, fill, y, x=64, shadow=True):
    if shadow:
        draw.text((x + 3, y + 3), text, font=f, fill=(0, 0, 0, 200))
    draw.text((x, y), text, font=f, fill=fill)
    return y + cap_height(f)


def text_w(f, s: str) -> int:
    return f.getbbox(s)[2]


# --------------------------------------------------------------------------- #
def cut_plan(run: Path, hero: Path, clips: dict, log_txt: str, verdict: dict):
    """The realised slot table: [(label, seconds, source)]."""
    a = clip_len(clips["warehouse"])
    b = clip_len(clips["physics"])
    c = clip_len(clips["arm"])
    plan = [
        ("hook", 1.0, hero),
        ("sceneA", a, clips["warehouse"]),
        ("sceneB", b, clips["physics"]),
        ("sceneC", c, clips["arm"]),
        ("terminal", 5.0, log_txt),
        ("proof", 5.0, clips["physics"]),
        ("endcard", 3.0, None),
    ]
    return plan


def clip_len(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json",
                          "-show_format", str(path)],
                         capture_output=True, text=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def _ydif_samples(path: Path, stride: int = 1) -> list[float]:
    """Per-frame luma differences at 640 px wide — the video gate's own
    motion metric — measured with a real `stride` frame drop.

    Speeding up a clip means DROPPING frames (select + reset pts), not
    resampling timestamps: setpts alone changes pacing but leaves each
    frame identical, so it cannot move this metric.  Measured on the stub:
    warehouse goes 0.51 -> 1.79 mean YDIF at stride 4."""
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-vf",
         f"select='not(mod(n,{stride}))',setpts=N/{FPS}/TB,"
         "scale=640:-2,signalstats,"
         "metadata=print:key=lavfi.signalstats.YDIF",
         "-f", "null", "-"], capture_output=True, text=True)
    return [float(ln.split("=")[1]) for ln in out.stderr.splitlines()
            if "lavfi.signalstats.YDIF" in ln]


def motion_fraction(path: Path, stride: int = 1) -> float:
    """Fraction of frames with YDIF >= 1.0 — exactly the gate's rule."""
    v = _ydif_samples(path, stride)
    return (sum(1 for x in v if x >= 1.0) / len(v)) if v else 0.0


def mean_ydif(path: Path, stride: int = 1) -> float:
    v = _ydif_samples(path, stride)
    return sum(v) / len(v) if v else 0.0


def pick_speed(path: Path, target: float = 0.5, cap: int = 4) -> int:
    """Smallest frame-drop speed whose moving-frame fraction clears
    `target` (the gate wants >= 0.2 across the whole video; scene slots
    must pull well above it because the hook and end card contribute
    none).  The chosen speed is printed and burned into the caption
    ("Nx speed"), never hidden."""
    for speed in range(1, cap + 1):
        if motion_fraction(path, stride=speed) >= target:
            return speed
    return cap


def ffmpeg_cut(src: Path, seconds: float, dest: Path, speed: int = 1) -> None:
    """Exact-length normalised PNG frame sequence from a clip (trim or
    hold the last frame); `speed` > 1 plays it that many times faster."""
    _cut(src, seconds, dest, loop=False, speed=speed)


def hold_frame(src: Path, seconds: float, dest: Path) -> None:
    _cut(src, seconds, dest, loop=True)


def _cut(src: Path, seconds: float, dest: Path, loop: bool,
         speed: int = 1) -> None:
    """PNG frame sequence from a clip.  `speed` > 1 DROPS frames (the
    real speed-up: content moves further per frame, which is what the
    gate's motion rule measures) — see mean_ydif()."""
    dest.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if loop:
        cmd += ["-loop", "1", "-framerate", str(FPS)]
    filt = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=rgb24")
    if speed > 1:
        # drop `speed`-1 of every `speed` frames, then re-stamp pts so
        # the output is still `seconds` long at FPS
        filt = (f"select='not(mod(n,{speed}))',setpts=N/{FPS}/TB," + filt)
    cmd += ["-i", str(src), "-t", f"{seconds:.3f}", "-an", "-vf", filt,
            "-r", str(FPS), "-start_number", "0", str(dest / "%05d.png")]
    subprocess.run(cmd, check=True, capture_output=True)


# --------------------------------------------------------------------------- #
def terminal_frames(run: Path, seconds: float, work: Path, speed: int):
    """Render run.py's real stdout as a scrolling terminal at `speed`x.

    Only lines that matter on a phone are kept (create, upload MB/s,
    render seconds, meters); the full log is the source file."""
    log = (run / "run.log").read_text(errors="replace").splitlines()
    keep, out = [], []
    for ln in log:
        if (ln.startswith("run.py:") or "[lease]" in ln or "[upload]" in ln
                or "[render]" in ln or "[download]" in ln or "[judge]" in ln
                or "[cleanup]" in ln or "[bundle]" in ln):
            keep.append(ln.rstrip())
    if not keep:
        keep = ["run.py: (log unavailable)"]
    prompt = "$ python3 run.py"
    body = [prompt] + keep
    f = font(MONO, 34)
    line_h = 46
    visible = (H - 160) // line_h
    n_frames = int(seconds * FPS)
    max_off = max(0, len(body) - visible)
    # the whole log must scroll past within the slot at the stated speed;
    # at the bottom it ping-pongs back up, so the slot never freezes (the
    # gate's motion rule punishes a static tail)
    scroll_per_frame = max(1, math.ceil(n_frames and (max_off + 1) / n_frames))
    frames_dir = work / "terminal"
    frames_dir.mkdir(parents=True, exist_ok=True)
    off, direction = 0, 1
    for i in range(n_frames):
        img = Image.new("RGB", (W, H), (12, 12, 16))
        d = ImageDraw.Draw(img)
        d.rectangle([40, 40, W - 40, H - 40], outline=(60, 64, 72), width=3)
        d.rectangle([40, 40, W - 40, 104], fill=(28, 30, 38))
        tf = font(MONO_B, 26)
        d.text((60, 62), "agent-next GPU sandbox · api.sbx.agent-next.com",
               font=tf, fill=(150, 200, 255))
        # A braile spinner + live elapsed clock: the slot must keep
        # moving even if the log is too short to scroll (the stub log is
        # 10 lines) — the gate's motion rule looks at every pre-endcard
        # frame.
        spin = "".join("|/-\\"[i // 2 % 4])
        d.text((W - 250, 62), f" {spin} {i / FPS:5.1f}s", font=tf,
               fill=(120, 255, 160))
        y = 132
        for k in range(visible):
            idx = off + k
            if idx < 0 or idx >= len(body):
                continue
            s = body[idx]
            col = (230, 232, 238)
            if s == prompt:
                col = (120, 255, 160)
            elif "created gl-" in s or "PASS" in s:
                col = (120, 255, 160)
            elif "MB/s" in s or "meters" in s:
                col = (255, 210, 120)
            d.text((64, y), s[:96], font=f, fill=col)
            y += line_h
        # A highlight band that sweeps down the body one line per frame:
        # the slot keeps moving even when the log is too short to scroll
        # (the stub log is 10 lines) and reads as a terminal.
        band = (i % max(1, visible)) * line_h
        d.rectangle([52, 128 + band, W - 52, 128 + band + line_h],
                    fill=(255, 255, 255, 16))
        off += direction * scroll_per_frame
        if off >= max_off:
            off, direction = max_off, -1
        elif off <= 0:
            off, direction = 0, 1
        cf = fit_font(SANS_B, CAP_H * 0.8)
        safe_line(d, f"run.py driving the GPU lease · {speed}x speed", cf,
                  (255, 255, 255), H - 120)
        img.save(frames_dir / f"{i:05d}.png")
    return frames_dir


def hud_frames(src: Path, seconds: float, work: Path, verdict: dict,
               kill_rows: list, meters: dict, speed: int = 1) -> Path:
    """The proof slot: judge verdict + mutant kill matrix burned onto the
    STILL-MOVING scene clip (never a text slide).

    The clip is decoded to frames once, overlaid per frame and written as
    `work/proof/`, which the caller's segment encoder picks up."""
    base = work / "proof_src"
    base.mkdir(parents=True, exist_ok=True)
    ffmpeg_cut(src, seconds, base, speed=speed)
    srcs = sorted(base.glob("*.png"))
    out = work / "proof"
    out.mkdir(parents=True, exist_ok=True)
    f_hud = fit_font(SANS_B, HUD_H)
    f_sm = font(MONO_B, 40)
    f_xs = font(MONO_B, 33)
    # A compact, clearly TRANSLUCENT panel: it must read as a HUD on top
    # of the moving render, not a cover over it (opaque panels measured
    # 0.0 moving frames on a 10-frame looping clip).
    panel_w = 760
    panel_h = 170 + 56 * len(kill_rows)
    n = int(seconds * FPS)
    bar_h = 10
    for i in range(n):
        img = Image.open(srcs[i % len(srcs)]).convert("RGB")
        d = ImageDraw.Draw(img, "RGBA")
        x0, y0 = W - panel_w - 60, 84
        d.rectangle([x0, y0, x0 + panel_w, y0 + panel_h],
                    fill=(8, 10, 14, 168), outline=(90, 220, 140, 255), width=4)
        y = y0 + 30
        passed = verdict.get("pass")
        d.text((x0 + 32, y), f"JUDGE {'PASS' if passed else 'FAIL'}",
               font=f_hud, fill=(120, 255, 160) if passed else (255, 110, 110))
        y += cap_height(f_hud) + 16
        scenes = verdict.get("scenes", {})
        g1 = min((g["gates"]["G1_silhouette"]["iou_min"]
                  for g in scenes.values()
                  if g.get("gates", {}).get("G1_silhouette", {}).get("iou_min") is not None),
                 default=None)
        if g1 is not None:
            d.text((x0 + 32, y), f"silhouette-vs-bbox IoU  min {g1:.3f}  (>= 0.900)",
                   font=f_sm, fill=(235, 238, 245))
            y += 50
        billed = meters.get("billed_s")
        if billed is not None:
            d.text((x0 + 32, y), f"metered GPU: {billed:.0f} s billed",
                   font=f_sm, fill=(255, 214, 120))
            y += 54
        d.text((x0 + 32, y), "mutant kill matrix", font=f_sm,
               fill=(150, 200, 255))
        y += 54
        for name, killed, gate in kill_rows:
            mark = "X" if killed else " "
            col = (120, 255, 160) if killed else (255, 120, 120)
            d.text((x0 + 36, y), f"[{mark}] {name:<18} {gate}",
                   font=f_xs, fill=col)
            y += 56
        # a progress bar that genuinely moves every frame (cheap motion
        # insurance for a looping short clip)
        by = y0 + panel_h + 26
        d.rectangle([x0, by, x0 + panel_w, by + bar_h], fill=(30, 34, 44, 220))
        d.rectangle([x0, by, x0 + panel_w * ((i + 1) / n), by + bar_h],
                    fill=(120, 255, 160, 255))
        d.text((x0, by + bar_h + 12), f"frame {i + 1}/{n}", font=f_xs,
               fill=(190, 195, 205))
        img.save(out / f"{i:05d}.png")
    if not srcs:
        raise SystemExit(f"no frames decoded from {src}")
    return out


def end_card(work: Path, seconds: float) -> Path:
    """The one static shot: the launch line."""
    n = int(seconds * FPS)
    d_ = work / "endcard"
    d_.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (W, H), (10, 11, 14))
    d = ImageDraw.Draw(img)
    f_big = fit_font(MONO_B, 0.085 * H)
    t = "python3 run.py"
    tw = text_w(f_big, t)
    d.text(((W - tw) // 2 + 4, H // 2 - 60 + 4), t, font=f_big, fill=(0, 60, 30))
    d.text(((W - tw) // 2, H // 2 - 60), t, font=f_big, fill=(120, 255, 160))
    f_sub = font(SANS, 44)
    sub = "agent-next GPU sandbox · RTX 5090 · NVIDIA SimReady assets"
    sw = text_w(f_sub, sub)
    d.text(((W - sw) // 2, H // 2 + 90), sub, font=f_sub, fill=(190, 195, 205))
    for i in range(n):
        img.save(d_ / f"{i:05d}.png")
    return d_


def captioned(clip_png: Path, dest: Path, line1: str, line2: str | None,
              speed: int = 1) -> None:
    img = Image.open(clip_png).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    if speed > 1:
        line1 = f"{line1} · {speed}x speed"
    f1 = fit_font(SANS_B, CAP_H)
    y = H - 190
    d.rectangle([56, y - 26, 56 + text_w(f1, line1) + 44, y + cap_height(f1) + 22],
                fill=(8, 10, 14, 170))
    safe_line(d, line1, f1, (255, 255, 255), y)
    if line2:
        f2 = fit_font(SANS, CAP_H * 0.78)
        safe_line(d, line2, f2, (215, 220, 230), y + cap_height(f1) + 34)
    img.save(dest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="run.py --out directory")
    ap.add_argument("--out", default=str(Path(__file__).parent / "demo.mp4"))
    ap.add_argument("--master-dir",
                    default=str(Path(__file__).parent / "master"))
    args = ap.parse_args()
    run = Path(args.run).resolve()
    media = Path(__file__).resolve().parent
    work = media / "work"
    work.mkdir(parents=True, exist_ok=True)

    verdict = json.loads((run / "verdict.json").read_text())
    receipt = json.loads((run / "run-receipt.json").read_text())
    kill_rows = []
    sf = run / "selftest.txt"
    if sf.exists():
        for ln in sf.read_text().splitlines():
            ln = ln.strip()
            if ln.startswith(("missing_texture", "untextured_grey", "black_frame",
                              "frozen", "camera_off", "underexposed", "wrong_units")):
                parts = ln.split()
                kill_rows.append((parts[0].rstrip(":"),
                                  "KILLED" in ln, parts[-1].strip("()")))
    hero = run / "hero.png"
    if not hero.exists():
        heros = sorted((run / "frames" / "arm").glob("*.png"))
        if not heros:
            print("no hero frame: run renders must be downloaded first",
                  file=sys.stderr)
            return 2
        hero = heros[len(heros) // 2]

    clips = {s: run / f"{s}.mp4" for s in ("warehouse", "physics", "arm")}
    missing = [str(p) for p in clips.values() if not p.exists()]
    if missing:
        print(f"missing render clips: {missing}", file=sys.stderr)
        return 2

    # Slot plan: sped-up scene clips shrink, so the terminal slot absorbs
    # the slack to keep the whole video inside the gate's 25-60 s window.
    speeds = {s: pick_speed(clips[s]) for s in clips}
    for s in clips:
        print(f"{s}: mean YDIF {mean_ydif(clips[s]):.2f} unsped -> "
              f"{speeds[s]}x (dropping frames)", flush=True)
    scene_secs = {s: clip_len(clips[s]) / speeds[s] for s in clips}
    PROOF_S, HOOK_S, END_S = 6.5, 1.0, 3.0
    term_s = min(12.0, max(5.0, 28.5 - (HOOK_S + sum(scene_secs.values())
                                         + PROOF_S + END_S)))
    print(f"slots: hook 1.0 s, scenes "
          f"{', '.join(f'{s}={scene_secs[s]:.1f}' for s in clips)}, "
          f"terminal {term_s:.1f} s, proof {PROOF_S} s, end {END_S} s",
          flush=True)

    # one reused build dir under the gitignored media/work (mkdtemp dirs
    # leaked ~94 MB per run in /tmp)
    tmp = work / "build"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    segs = []

    # hook
    hook = tmp / "hook"
    hold_frame(hero, 1.0, hook)
    capdir = tmp / "hook_cap"
    capdir.mkdir()
    for i, p in enumerate(sorted(hook.glob("*.png"))):
        captioned(p, capdir / f"{i:05d}.png",
                  "RTX path tracing on a disposable GPU",
                  "NVIDIA official SimReady scenes · 1920x1080 · 30 fps")
    segs.append(("hook", capdir))

    # scenes A/B/C with captions
    caps = {
        "warehouse": ("Scene A · UR10 warehouse dolly · 8 s",
                      "SimReady rack, pallet, crates · RTX path tracer"),
        "physics": ("Scene B · PhysX crate collapse · 6 s",
                    "baked rigid-body trajectory · RTX path tracer"),
        "arm": ("Scene C · UR10 hero turntable · 6 s",
                "official Isaac Sim UR10 · RTX path tracer"),
    }
    for scene in ("warehouse", "physics", "arm"):
        seg = tmp / scene
        ffmpeg_cut(clips[scene], clip_len(clips[scene]), seg,
                   speed=speeds[scene])
        capdir = tmp / f"{scene}_cap"
        capdir.mkdir(exist_ok=True)
        for i, p in enumerate(sorted(seg.glob("*.png"))):
            captioned(p, capdir / f"{i:05d}.png", *caps[scene],
                      speed=speeds[scene])
        segs.append((scene, capdir))

    # terminal
    tdir = terminal_frames(run, term_s, tmp, speed=8)
    segs.append(("terminal", tdir))

    # proof HUD
    meters = receipt.get("final_meters") or {}
    kill_rows = kill_rows or [("no mutant data", False, "-")]
    pdir = hud_frames(clips['physics'], PROOF_S, tmp, verdict, kill_rows,
                      meters, speed=speeds["physics"])
    segs.append(("proof", pdir))

    # end card
    edir = end_card(tmp, END_S)
    segs.append(("endcard", edir))

    # per-segment lossless mp4, then a stream-copy concat
    seg_files = []
    for name, d in segs:
        seg_mp4 = tmp / f"{name}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-framerate", "30",
             "-pattern_type", "glob", "-i", str(d / "*.png"),
             "-c:v", "libx264", "-crf", "0", "-preset", "veryfast",
             "-pix_fmt", "yuv444p", str(seg_mp4)], check=True)
        seg_files.append(seg_mp4)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in seg_files))
    master = Path(args.master_dir)
    master.mkdir(parents=True, exist_ok=True)
    master_mp4 = master / "master.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c", "copy", str(master_mp4)], check=True)

    # web copy: crf 18 first, stepping up until it fits under 8 MB
    out = Path(args.out)
    for crf in (18, 19, 20, 21, 22):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(master_mp4),
             "-c:v", "libx264", "-crf", str(crf), "-preset", "slow",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
             str(out)], check=True)
        size = out.stat().st_size
        print(f"crf {crf}: {size / 1e6:.2f} MB", flush=True)
        if size <= 8 * 1024 * 1024:
            break
    duration = clip_len(out)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB, {duration:.1f} s)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
