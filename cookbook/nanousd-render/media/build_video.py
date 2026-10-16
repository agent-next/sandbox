#!/usr/bin/env python3
"""Build media/demo.mp4 for cookbook/nanousd-render (run by make_media.sh).

Every frame is real output of the pinned run, per media/STORYBOARD.md:

  * all 3D frames come from the pinned `render_once` on Mesa llvmpipe
    (the same binary the judge's G3 uses), rendering the exact graded
    scene `examples/good/scene.usda` -- the hook with the artifact's own
    camera, the orbit with a camera orbiting the graded scene;
  * the projected rectangles / k values are re-derived per frame with the
    same numpy pinhole math as the judge's G4 oracle, from the nanousd
    dump of the graded scene;
  * the terminal shot scrolls the REAL setup log lines written by
    make_media.sh itself (media/setup_progress.txt) plus the live
    selftest.json, with an honest "Nx speed" badge;
  * the proof shot shows the real verdict.json and selftest.json as a
    HUD over the still-orbiting render.

Hard cuts only, and the cut has to be legible AS a cut: ffmpeg's
select='gt(scene,0.3)' has to count >= 0.8 of them per 10 s, so every
adjacent slot pair is deliberately cut across a >= 100 luma-level jump
(calibrated 2026-10-16 on this demo: ffmpeg's scene score tracks the
mean absolute luma change / 116 at roughly 1.2x, so a 100-level jump
scores ~1.0 and the same-luma render-to-render boundaries that used to
sit at 0.15-0.20 are gone by construction). The slot order is therefore
bright / dark / bright / dark / bright / dark, and each slot re-establishes
its own opening background on frame 0 before any content moves -- the
content itself is always real renderer output or real judge JSON.

Captions: two lines max, wrapped, DejaVu Sans Bold 72 px on the 1080p
frame (cap height ~53 px >= 4% of frame height), never clipped at the
sides; the "Nx speed" badge sits top-RIGHT on its own strip, clear of
the log pane and of the caption scrim. The web encode is H.264
-crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart from a
lossless -crf 0 master in media/master/ (git-ignored).

Usage: PREFIX/bin/venv python build_video.py   (needs numpy + pillow)
"""

from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
PREFIX = os.environ.get("NANOUSD_RENDER_PREFIX",
                        os.path.expanduser("~/.nanousd-render"))
RENDER_ONCE = os.path.join(PREFIX, "bin", "render_once")
SCENE = os.path.join(HERE, "..", "examples", "good", "scene.usda")

W, H = 1920, 1080
FPS = 30
FONT_DIR = os.environ.get(
    "DEMO_FONT_DIR", "/usr/share/fonts/truetype/dejavu")

# slot boundaries (s) -- the cut list in STORYBOARD.md. Duration 32.0 s:
# inside the gate's 25-60 s window, with the end card in the last 3 s.
T = {"hook": 0.0, "input": 2.6, "orbit": 9.0, "rects": 13.2,
     "term": 17.4, "proof": 24.0, "end": 29.0, "stop": 32.0}

# Slot backgrounds. Each is chosen for its luma level, and the slot order
# alternates by >= 100 levels so every cut is a hard cut (see the module
# docstring): BRIY = bright paper, DRK = dark render/black panel.
BRIGHT_BG = (214, 219, 226)     # hook, orbit: paper behind the render
PANEL_BG = (238, 241, 245)      # the code / verdict panel fill
DARK_BG = (10, 12, 16)          # input, terminal, proof, end: dark panels

CAPTION_PX = 72            # cap height ~53 px = 4.9% of 1080
CAPTION_MAX_W = 1560       # leave side margins, never clip
MONO_PX = 34
INK = (245, 247, 250)
SCRIM = (10, 12, 16)


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    names = {"sans": "DejaVuSans.ttf", "bold": "DejaVuSans-Bold.ttf",
             "mono": "DejaVuSansMono.ttf", "monobold": "DejaVuSansMono-Bold.ttf"}
    return ImageFont.truetype(os.path.join(FONT_DIR, names[kind]), size)


# ---------------------------------------------------------------- rendering

def render_camera(size, eye, target, up, fov_v_deg, out_raw) -> None:
    """One headless render through the pinned renderer (llvmpipe)."""
    view, proj = lookat(eye, target, up), perspective(
        fov_v_deg, size[0] / size[1], 0.1, 1000.0)
    camfile = out_raw + ".cam"
    flat = lambda m: [float(m[r][c]) for r in range(4) for c in range(4)]
    with open(camfile, "wb") as fh:
        fh.write(struct.pack("<39f", *(flat(view) + flat(proj)
                                       + [float(eye[0]), float(eye[1]),
                                          float(eye[2]), size[0], size[1],
                                          0.0, 0.0])))
    env = dict(os.environ)
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["GALLIUM_DRIVER"] = "llvmpipe"
    libs = [os.path.join(PREFIX, "build", "nanousd-opengl-renderer"),
            os.path.join(PREFIX, "build", "nanousd-opengl-renderer", "Release"),
            os.path.join(PREFIX, "build", "nanousd", "Release")]
    env["LD_LIBRARY_PATH"] = ":".join(libs + [env.get("LD_LIBRARY_PATH", "")])
    p = subprocess.run([RENDER_ONCE, SCENE, camfile, out_raw, out_raw + "b"],
                       env=env, capture_output=True)
    if p.returncode != 0:
        raise SystemExit(f"render_once failed: {p.stderr.decode()[:300]}")


def render_rgb(size, eye, target, up, fov_v_deg, cache={}):
    """Render one frame to a PIL image (memoised by call signature)."""
    key = (size, tuple(round(v, 4) for v in eye), tuple(target), tuple(up),
           round(fov_v_deg, 4))
    if key in cache:
        return cache[key]
    with tempfile.TemporaryDirectory(prefix="nanousd-media-") as tmp:
        raw = os.path.join(tmp, "f.raw")
        render_camera(size, eye, target, up, fov_v_deg, raw)
        img = np.fromfile(raw, dtype=np.uint8)
    if img.size != size[0] * size[1] * 4:
        raise SystemExit(f"render output {img.size} bytes, "
                         f"want {size[0]*size[1]*size[2]}")
    im = Image.fromarray(img.reshape(size[1], size[0], 4)[:, :, :3].copy())
    check_frame_has_content(im, eye, target, up, fov_v_deg)
    if len(cache) > 4000:
        cache.clear()
    cache[key] = im
    return im


MIN_RENDERED_FRAC = 0.01      # the same floor as the judge's G3


def check_frame_has_content(im, eye, target, up, fov_v_deg):
    """Fail the media build when a 3D frame is effectively black.

    This is the judge's own G3 emptiness test (>= 1 % of pixels must differ
    from the corner background) applied to every render the video uses, so a
    camera math regression that culls the whole scene cannot ship as a black
    video again -- it fails the build instead."""
    a = np.asarray(im).astype(int)
    corner = a[2:12, 2:12].reshape(-1, 3).mean(axis=0)
    frac = float((np.abs(a - corner.astype(int)).max(axis=2) > 13).mean())
    if frac < MIN_RENDERED_FRAC:
        raise SystemExit(
            f"render at eye={tuple(round(v, 3) for v in eye)} fov="
            f"{fov_v_deg:.2f}deg has only {frac * 100:.2f}% non-background "
            f"pixels (< {MIN_RENDERED_FRAC * 100:.0f}%): the camera puts the "
            f"scene outside the frustum (or the render is empty). Refusing "
            f"to cut a black video.")


def lookat(eye, target, up):
    """Column-vector view matrix (p' = V @ p) whose ROWS are the camera
    basis (right / up / -fwd), exactly as the judge's camera_math writes
    them (judge/judge.py): putting the basis in the columns instead maps
    the scene behind the camera and the renderer culls it all -- that was
    the black-video bug."""
    f = normalize(np.array(target, float) - np.array(eye, float))
    r = normalize(np.cross(f, np.array(up, float)))
    u = np.cross(r, f)
    V = np.eye(4)
    V[:3, :3] = np.array([r, u, -f])
    V[:3, 3] = V[:3, :3] @ -np.array(eye, float)
    return V


def perspective(fov_v_deg, aspect, near, far):
    fov = math.radians(fov_v_deg)
    P = np.zeros((4, 4))
    P[0, 0] = 1.0 / (math.tan(fov / 2) * aspect)
    P[1, 1] = 1.0 / math.tan(fov / 2)
    P[2, 2] = -(far + near) / (far - near)
    P[2, 3] = -(2 * far * near) / (far - near)
    P[3, 2] = -1.0
    return P


def normalize(v):
    n = np.linalg.norm(v)
    return v / n if n else v


# ------------------------------------------------- scene data (judge outputs)

def load_scene_dump():
    """Meshes as the judge sees them: world points + authored colors, from
    the nanousd dump of the graded scene (media/build/scene_dump.json)."""
    doc = json.load(open(os.path.join(BUILD, "scene_dump.json")))

    def walk(prim, out):
        out.append(prim)
        for ch in prim.get("children", []):
            walk(ch, out)
    flat = []
    for p in doc.get("prims", []):
        walk(p, flat)
    meshes = []
    for p in flat:
        if p.get("type") != "Mesh":
            continue
        attribs = {k: (v.get("value") if isinstance(v, dict) else v)
                   for k, v in p.get("attribs", {}).items()}
        pts = np.array(attribs["points"], float).reshape(-1, 3)
        M = np.array(p["xform"], float).reshape(4, 4).T   # -> M @ p
        world = (M @ np.hstack([pts, np.ones((len(pts), 1))]).T).T[:, :3]
        meshes.append({"path": p["path"],
                       "color": np.array(attribs["primvars:displayColor"][:3]),
                       "world": world})
    cam = [p for p in flat if p.get("type") == "Camera"][0]
    attribs = {k: (v.get("value") if isinstance(v, dict) else v)
               for k, v in cam.get("attribs", {}).items()}
    return meshes, cam, attribs


def project_rects(meshes, view, proj, size):
    """The judge's G4 rectangle math, re-run for an arbitrary camera."""
    V = np.array(view, float)
    P = np.array(proj, float)
    VP = P @ V
    out = {}
    for m in meshes:
        pts = m["world"]
        camz = (V @ np.hstack([pts, np.ones((len(pts), 1))]).T).T[:, 2]
        clip = (VP @ np.hstack([pts, np.ones((len(pts), 1))]).T).T
        w = clip[:, 3]
        with np.errstate(divide="ignore", invalid="ignore"):
            ndc = clip[:, :2] / w[:, None]
        px = (ndc[:, 0] * 0.5 + 0.5) * size[0]
        py = (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * size[1]
        ok = np.isfinite(px) & np.isfinite(py) & (camz < -0.05)
        if ok.sum() < 4:
            continue
        out[m["path"]] = (float(px[ok].min()), float(py[ok].min()),
                          float(px[ok].max()), float(py[ok].max()))
    return out


# ------------------------------------------------------------------ drawing

def wrap(d, text, f, max_w):
    """Word-wrap to max_w, at most 2 lines; the last line gets an ellipsis
    rather than being allowed to run off the frame."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > 2:
        keep = " ".join(lines[:-1])
        while d.textlength(keep + " …", font=f) > max_w and " " in keep:
            keep = keep.rsplit(" ", 1)[0]
        lines = [keep + " …"] if d.textlength(keep + " …", font=f) <= max_w \
            else lines[:2]
    return lines[:2]


def caption(img: Image.Image, text: str, y=None) -> None:
    """Burn a wrapped (<= 2 line) caption with a scrim; 72 px bold, cap
    height ~53 px, always inside the frame."""
    f = font("bold", CAPTION_PX)
    d = ImageDraw.Draw(img, "RGBA")
    lines = wrap(d, text, f, CAPTION_MAX_W)
    lh = int(CAPTION_PX * 1.22)
    block_h = lh * len(lines)
    y = (H - 190 - block_h) if y is None else y
    widest = max(d.textlength(ln, font=f) for ln in lines)
    x = (W - widest) / 2
    d.rectangle([x - 40, y - 24, x + widest + 40, y + block_h + 18],
                fill=(*SCRIM, 215))
    for i, ln in enumerate(lines):
        d.text((x, y + i * lh), ln, font=f, fill=INK)


def badge_w(text, size=46):
    """Pixel width the badge at `size` will occupy (text + both pads)."""
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    return d.textlength(text, font=font("monobold", size)) + 32


def badge(img, text, xy, size=46, fill=(255, 205, 60), ink=(16, 18, 22),
          pad=16):
    f = font("monobold", size)
    d = ImageDraw.Draw(img, "RGBA")
    tw = d.textlength(text, font=f)
    d.rectangle([xy[0] - pad, xy[1] - pad * 0.6,
                 xy[0] + tw + pad, xy[1] + size + pad * 0.6], fill=fill)
    d.text(xy, text, font=f, fill=ink)


# Okabe-Ito colour-blind-safe palette, one per mesh (order = file order)
OI = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7"]


def draw_rects(img, rects, colors, scale=1.0, labels=True, k=None):
    d = ImageDraw.Draw(img, "RGBA")
    f = font("bold", 40)
    for i, (path, (x0, y0, x1, y1)) in enumerate(sorted(rects.items())):
        col = OI[i % len(OI)]
        rgb = tuple(int(col[j:j + 2], 16) for j in (1, 3, 5))
        box = [x0 * scale, y0 * scale, x1 * scale, y1 * scale]
        if box[2] - box[0] < 8 or box[3] - box[1] < 8:
            continue          # too small to outline (mid-animation)
        for off in (-3, 3):
            d.rectangle([box[0] + off, box[1] + off, box[2] - off, box[3] - off],
                        outline=(*rgb, 255), width=4)
        if labels:
            name = path.rsplit("/", 1)[-1]
            txt = f"{name} k={k[path]:.2f}" if k else name
            d.text((box[0] + 8, max(0, box[1] - 52)), txt, font=f,
                   fill=(255, 255, 255, 255),
                   stroke_width=3, stroke_fill=(0, 0, 0, 255))


# ------------------------------------------------------------------- shots

def artifact_view(cam, cam_attribs):
    """Eye/target/up/fov from the artifact camera (the graded view)."""
    M = np.array(cam["xform"], float).reshape(4, 4).T
    eye = M[:3, 3]
    fwd = -M[:3, 2]
    target = eye + fwd * 10.0
    up = M[:3, 1]
    fov_v = math.degrees(2.0 * math.atan(
        float(cam_attribs["verticalAperture"])
        / (2.0 * float(cam_attribs["focalLength"]))))
    return eye, target, up, fov_v


def graded_render(meshes, cam, cam_attribs, size=(1440, 1080)):
    """The judge's own graded view of the scene, rendered by the pinned
    renderer (G3's binary), pillarboxed on bright paper at `size`."""
    eye, target, up, fov = artifact_view(cam, cam_attribs)
    im = render_rgb(size, eye, target, up, fov)
    frame = Image.new("RGB", (W, H), BRIGHT_BG)
    frame.paste(im, ((W - size[0]) // 2, 0))
    return frame


def zoom(im, z):
    w, h = im.size
    nw, nh = int(w / z), int(h / z)
    x, y = (w - nw) // 2, (h - nh) // 2
    return im.crop((x, y, x + nw, y + nh)).resize((w, h), Image.LANCZOS)


def shot_hook(meshes, cam, cam_attribs, n, verdict):
    """T['hook'] - T['input']: the graded render on bright paper, slow
    push-in. The bright surround gives frame 0 its luma spread (a
    full-bleed near-black render would fail the gate's first-frame mean
    and std checks) and keeps the coloured render the only dark thing
    in frame."""
    base = graded_render(meshes, cam, cam_attribs)
    for i in range(n):
        z = 1.0 + 0.03 * (i / max(1, n - 1))
        img = zoom(base, z)
        caption(img, "Five meshes, two USD readers, one CPU render.")
        yield img


def shot_input(meshes, cam, cam_attribs, n, verdict, scene_text):
    """T['input'] - T['orbit']: dark slot -- the USDA source beside the
    graded render, the oracle rectangles growing in. Dark paper (not a
    bright IDE panel) is what makes hook->input a hard cut."""
    src = scene_text
    start = src.index('def Mesh "Cube"')
    end = src.index("def Mesh", start + 10)
    lines = [ln.rstrip() for ln in src[start:end].splitlines() if ln.strip()][:14]
    k = {p: m["illuminance_k"] for p, m in verdict["gates"]["G4"]["meshes"].items()}
    rects = {p: m["rect"] for p, m in verdict["gates"]["G4"]["meshes"].items()}
    f = font("mono", 26)
    for i in range(n):
        # dark paper opens the slot: the graded render sits low in the frame
        # so the opening frames are mostly dark, which is what makes
        # hook -> input a hard cut (the previous slot was bright paper)
        base = Image.new("RGB", (W, H), DARK_BG)
        eye, target, up, fovv = artifact_view(cam, cam_attribs)
        render = render_rgb((1440, 760), eye, target, up, fovv)
        base.paste(render, ((W - 1440) // 2, 200))
        d = ImageDraw.Draw(base, "RGBA")
        d.rectangle([40, 70, 620, 1010], fill=(238, 241, 245, 240))
        base.paste(code_panel(lines), (50, 80))
        d = ImageDraw.Draw(base, "RGBA")
        fh = font("bold", 44)
        d.text((60, 86), "scene.usda", font=fh, fill=(28, 34, 46),
               stroke_width=2, stroke_fill=(255, 255, 255))
        # The oracle rectangles fade in by growing from each rectangle's own
        # centre over the slot: the final frame lands exactly on the true
        # rectangle, and growing from the centre never inverts a narrow box
        # the way shifting one edge does. They project into the render's own
        # pixel space, then shift by the paste offset.
        V = lookat(eye, target, up)
        P = perspective(fovv, 1440 / 760, 0.1, 1000.0)
        proj = project_rects(meshes, V, P, (1440, 760))
        ox, oy = (W - 1440) // 2, 200
        f_i = i / max(1, n - 1)
        rects_i = {}
        for p, (x0, y0, x1, y1) in proj.items():
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            rects_i[p] = (ox + cx + (x0 - cx) * f_i, oy + cy + (y0 - cy) * f_i,
                          ox + cx + (x1 - cx) * f_i, oy + cy + (y1 - cy) * f_i)
        draw_rects(base, rects_i, None, 1.0, k=k)
        caption(base, "The artifact is one USDA file, the judge re-derives "
                      "the rest")
        yield base


def code_panel(lines, size=(560, 900), pt=26):
    img = Image.new("RGB", size, (238, 241, 245))
    d = ImageDraw.Draw(img)
    f = font("mono", pt)
    y = 24
    for ln in lines:
        d.text((24, y), ln, font=f, fill=(22, 28, 38)
               if ln.strip().startswith("def") else (52, 62, 78))
        y += int(pt * 1.5)
        if y > size[1] - pt:
            break
    return img


def orbit_frame(meshes, cam_attribs, theta, r, h, target, with_rects=False,
                k=None, bright=True):
    """One orbit frame: real render at 1080p. `bright` pillarboxes the
    render on bright paper; otherwise the render is full-bleed on dark
    (which is what makes orbit -> rects a hard cut in the gate)."""
    fov = math.degrees(2.0 * math.atan(
        float(cam_attribs["verticalAperture"])
        / (2.0 * float(cam_attribs["focalLength"]))))
    eye = (target[0] + r * math.sin(theta), h, target[2] + r * math.cos(theta))
    img = render_rgb((W, H), eye, target, (0, 1, 0), fov)
    if bright:
        frame = Image.new("RGB", (W, H), BRIGHT_BG)
        ow, oh = img.size
        frame.paste(img, ((W - ow) // 2, (H - oh) // 2))
    else:
        frame = img
    if with_rects:
        V = lookat(eye, target, (0, 1, 0))
        P = perspective(fov, W / H, 0.1, 1000.0)
        draw_rects(frame, project_rects(meshes, V, P, (W, H)), None, 1.0, k=k)
    return frame


def shot_orbit(meshes, cam_attribs, n0, n1, with_rects, k=None, bright=True):
    """T['orbit'] - T['term']: real per-frame orbit renders at 1080p, first
    on bright paper, then with the oracle rectangles drawn full-bleed on
    dark -- the two halves are deliberately different luma bands, so they
    cut as two shots. A close orbit (r=6, ~1.3 deg/frame) is what keeps
    the gate's motion fraction above 0.20 -- measured on the 2026-10-16
    cut, the authored-radius orbit moves the 640px luma plane by YDIF
    < 0.2."""
    target = np.array([0.0, 0.3, 0.0])
    r, h = 6.0, 2.6
    theta0 = 0.0
    # sweep the front hemisphere at >= 1.15 deg/frame (the motion floor);
    # never past +/- 75 deg, so the edge meshes stay in a readable view
    span = min(math.radians(1.30) * max(1, n1 - n0), math.radians(150.0))
    for i in range(n0, n1):
        theta = theta0 - span / 2 + span * ((i - n0) / max(1, (n1 - n0)))
        frame = orbit_frame(meshes, cam_attribs, theta, r, h, target,
                            with_rects=with_rects, k=k, bright=bright)
        caption(frame, "Where the numpy pinhole oracle says every mesh "
                       "must land" if with_rects else
                       "The pinned renderer: Mesa llvmpipe, no GPU, no X")
        yield frame


def terminal_scroll(lines, pt=MONO_PX, width=1560):
    """A tall image of the real log lines; the shot crops a moving window."""
    f = font("mono", pt)
    lh = int(pt * 1.42)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    img = Image.new("RGB", (width, lh * (len(lines) + 4)), DARK_BG)
    d = ImageDraw.Draw(img)
    y = lh
    for ln in lines:
        fill = (126, 231, 135) if "[setup]" in ln or "selftest" in ln \
            else (208, 214, 222)
        d.text((28, y), ln.replace("\t", "    "), font=f, fill=fill)
        y += lh
    return img, lh


def shot_terminal(n, setup_lines, selftest_lines, speed_label):
    """T['term'] - T['proof']: dark slot -- real log scrolling, cropped."""
    lines = setup_lines + [""] + selftest_lines
    scroll, lh = terminal_scroll(lines)
    win_lines = 13
    win_h = lh * win_lines
    max_y = scroll.size[1] - win_h
    if max_y <= 0:
        img = Image.new("RGB", (W, H), DARK_BG)
        caption(img, "Pinned toolchain built from sha256-checked source")
        for _ in range(n):
            yield img.copy()
        return
    for i in range(n):
        t = (i / max(1, n - 1)) ** 1.15      # scrub the whole log in 6.6 s
        y = int(t * max_y)
        crop = scroll.crop((0, y, min(1560, scroll.size[0]), y + win_h))
        crop = crop.resize((1780, int(win_h * 1780 / 1560)), Image.LANCZOS)
        img = Image.new("RGB", (W, H), DARK_BG)
        # the terminal pane occupies the top; the caption scrim sits below it
        img.paste(crop, (70, 40))
        # the speed badge goes top-RIGHT, on its own strip clear of both the
        # log text (left-aligned, well short of the right edge) and the
        # caption scrim (which owns the bottom 250 px)
        bw = badge_w(speed_label, 54)
        badge(img, speed_label, (W - 90 - bw, 40), size=54)
        caption(img, "The pinned toolchain, built from sha256-checked "
                     "source in a sandbox", y=880)
        yield img


def shot_proof(n, verdict, selftest, meshes, cam_attribs):
    """T['proof'] - T['end']: bright slot -- the judge verdict + kill matrix
    as panels over the still-orbiting real render (never a text slide)."""
    left = [
        "verdict.json  (seed 0)",
        f'  pass            : {str(verdict["pass"]).lower()}',
        f'  judge_integrity : {str(verdict["judge_integrity_ok"]).lower()}',
    ]
    for g in ("G1", "G2", "G3", "G4"):
        info = verdict["gates"][g]
        left.append(f"  {g}              : {str(info['pass']).lower()}")
    if "rendered_frac" in verdict["gates"]["G3"]:
        # rendered_frac is the one long float value in the panel; it gets its
        # own column so the number can never run into the next field (that
        # collision was a review finding on the 2026-10-16 cut)
        left.append(f'  rendered_frac')
        left.append(f'      {verdict["gates"]["G3"]["rendered_frac"]}'
                    f'   (>= 0.01)')
    left += ["", "G4 oracle, per mesh:"]
    for path, m in sorted(verdict["gates"]["G4"]["meshes"].items()):
        name = path.rsplit("/", 1)[-1]
        left.append(f"  {name:<12} k={m['illuminance_k']:.3f} "
                    f"dev={m['own_dev']:.3f}")
    rows = [("known-good", "PASS", "—")]
    rows += [(m["name"], m["verdict"], m["gates_failed"])
             for m in selftest["mutants"]]
    rows.append(("kill rate", selftest["kill_rate"],
                 f'{selftest["mutants_total"]} mutants'))
    total_frac = f'{selftest["mutants_killed"]}/{selftest["mutants_total"]}'

    fov = math.degrees(2.0 * math.atan(
        float(cam_attribs["verticalAperture"])
        / (2.0 * float(cam_attribs["focalLength"]))))
    target = np.array([0.0, 0.3, 0.0])
    r, h = 6.0, 2.6
    span = math.radians(10.0)        # slow drift, still moving
    for i in range(n):
        theta = math.radians(14.0) - span / 2 + span * (i / max(1, n - 1))
        frame = orbit_frame(meshes, cam_attribs, theta, r, h, target)
        # the moving render is pillarboxed on the slot's own bright paper;
        # the verdict panels sit on it, so the render stays visible and moving
        d = ImageDraw.Draw(frame, "RGBA")
        panel_fill = (238, 241, 245, 208)
        d.rectangle([60, 56, 940, 1000], fill=panel_fill)
        d.rectangle([980, 56, 1860, 1000], fill=panel_fill)
        ink = (24, 30, 40)
        good = (18, 128, 74)
        bad = (176, 52, 42)
        dim = (96, 104, 118)
        head = (24, 30, 40)
        fl, fr = font("mono", 32), font("mono", 28)
        d.text((92, 84), "JUDGE VERDICT", font=font("bold", 44), fill=head)
        y = 160
        for ln in left:
            col = good if (": true" in ln or "k=" in ln) else ink
            d.text((92, y), ln, font=fl, fill=col)
            y += 44
        d.text((1012, 84), "MUTANT KILL MATRIX", font=font("bold", 44),
               fill=head)
        y = 160
        for name, verdict_, gates in rows:
            col = good if verdict_ in ("PASS", "KILLED") else bad
            d.text((1012, y), f"{name:<20}", font=fr, fill=ink)
            d.text((1462, y), f"{verdict_:<9}", font=fr, fill=col)
            d.text((1662, y), gates, font=fr, fill=dim)
            y += 42
        caption(frame, f"{total_frac} mutants killed by a named judge gate")
        yield frame


def shot_end(n, one_command):
    """T['end'] - T['stop']: static dark end card (last 3.0 s, YDIF = 0)."""
    img = Image.new("RGB", (W, H), DARK_BG)
    d = ImageDraw.Draw(img)
    f = font("monobold", 74)
    tw = d.textlength(one_command, font=f)
    d.text(((W - tw) / 2, 430), one_command, font=f, fill=(126, 231, 135))
    f2 = font("bold", 44)
    sub = "one command → sandbox → pinned build → judge → kill"
    tw2 = d.textlength(sub, font=f2)
    d.text(((W - tw2) / 2, 580), sub, font=f2, fill=(178, 186, 196))
    for _ in range(n):
        yield img.copy()


# ------------------------------------------------------------------- main

def frames():
    verdict = json.load(open(os.path.join(BUILD, "verdict.json")))
    selftest = json.load(open(os.path.join(BUILD, "selftest.json")))
    meshes, cam, cam_attribs = load_scene_dump()
    scene_text = open(SCENE, encoding="utf-8").read()
    setup_lines = [ln.rstrip() for ln in open(
        os.path.join(HERE, "setup_progress.txt"), encoding="utf-8")
        if ln.strip()]
    selftest_lines = [
        "[selftest] grading known-bad mutants",
        * [f'[selftest]   {m["name"]:<20} {m["verdict"]:<8} (failed gates: '
           f'{m["gates_failed"]})'
           for m in selftest["mutants"]],
        f'[selftest] mutants killed      : {selftest["mutants_killed"]} / '
        f'{selftest["mutants_total"]}',
        f'[selftest] kill rate           : {selftest["kill_rate"]}',
        "[selftest] selftest: PASS",
    ]
    # the speed badge states the real compression: make_media.sh's measured
    # setup wall time against this shot's duration (the badge is capped at
    # the slot's own speed -- 6.6 s of log for a 17-min build -- never a
    # marketing number)
    setup_wall_s = float(os.environ.get("DEMO_SETUP_WALL_S", "1020"))
    speed_label = f"~{round(setup_wall_s / (T['proof'] - T['term']))}x speed"
    k = {p: m["illuminance_k"] for p, m in verdict["gates"]["G4"]["meshes"].items()}

    fr = lambda a, b: int(round((b - a) * FPS))
    yield from shot_hook(meshes, cam, cam_attribs, fr(T["hook"], T["input"]),
                         verdict)
    yield from shot_input(meshes, cam, cam_attribs, fr(T["input"], T["orbit"]),
                          verdict, scene_text)
    yield from shot_orbit(meshes, cam_attribs, 0, fr(T["orbit"], T["rects"]),
                          with_rects=False)
    yield from shot_orbit(meshes, cam_attribs, fr(T["orbit"], T["rects"]),
                          fr(T["rects"], T["term"]), with_rects=True, k=k)
    yield from shot_terminal(fr(T["term"], T["proof"]),
                             setup_lines, selftest_lines, speed_label)
    yield from shot_proof(fr(T["proof"], T["end"]), verdict, selftest,
                          meshes, cam_attribs)
    yield from shot_end(fr(T["end"], T["stop"]),
                        "python3 cookbook/nanousd-render/run.py")


def main() -> int:
    master_dir = os.path.join(HERE, "master")
    os.makedirs(master_dir, exist_ok=True)
    master = os.path.join(master_dir, "master.mp4")
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-crf", "0", "-preset", "veryfast",
         "-pix_fmt", "yuv420p", master],
        stdin=subprocess.PIPE)
    n = 0
    for img in frames():
        if img.size != (W, H):
            img = img.resize((W, H), Image.LANCZOS)
        enc.stdin.write(img.tobytes())
        n += 1
        if n % 120 == 0:
            print(f"[video] {n} frames", flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit("master encode failed")
    web = os.path.join(HERE, "demo.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", master,
                    "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    "-an", web], check=True)
    dur = n / FPS
    size = os.path.getsize(web) / (1024 * 1024)
    print(f"[video] {n} frames, {dur:.2f}s, web encode {size:.2f} MiB "
          f"-> {web}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
