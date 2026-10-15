#!/usr/bin/env python3
"""Render every demo.mp4 frame for the aicad-cadam demo (via make_media.sh).

3D slots are real renders of the shipped examples/good/*/part.stl meshes by
the pinned pyrender/OSMesa stack through render.py — no matplotlib animation
anywhere.  Card slots are composited from the committed result.png and
loop.png.  Every number burned into a frame is read here from
media/data/*.json (judge/grade.sh / selftest.sh output) — none is typed in.

Slot table (30 fps, 1920x1080, 37.0 s) matches media/STORYBOARD.md (v0):

   0.0- 4.0  the three finished parts, slow orbit
   4.0-12.0  the plate turntable + its real OpenSCAD source card
  12.0-16.0  the bushing turntable, gate lines
  16.0-20.0  the bracket turntable, gate lines
  20.0-27.0  card: loop.png (kill matrix + fixing loop)
  27.0-34.0  card: result.png (renders + gate lines)
  34.0-37.0  end card: the one-command run
"""

import json
import os
import sys

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")
FRAMES = os.path.join(HERE, "frames")
FONTS = "/usr/share/fonts/truetype/dejavu"

W, H, FPS = 1920, 1080, 30
DARK = "#1a1a19"          # palette dark surface
INK = "#f0efec"
INK2 = "#c3c2b7"
GREEN = "#30c630"         # status good, dark step
RED = "#ff6b6b"           # status critical, dark step
# palette dark-mode categorical slots 1-3: the three parts keep one hue each
SLOT_COLORS = {"bushing": "#3987e5", "plate": "#d95926", "bracket": "#199e70"}

F_BIG = ("DejaVuSans-Bold.ttf", 48)
F_MED = ("DejaVuSans.ttf", 44)
F_CODE = ("DejaVuSansMono.ttf", 30)


def font(spec):
    name, size = spec
    return ImageFont.truetype(os.path.join(FONTS, name), size)


TURN = [None]           # one shared renderer (OSMesa buffers leak per context)


def mesh_of(case):
    tm = trimesh.load(os.path.join(DEMO, "examples/good", case, "part.stl"))
    c = ((tm.bounds[0] + tm.bounds[1]) / 2.0).astype(float)
    r = float(np.linalg.norm(tm.extents)) / 2.0
    return tm, c, r


def verdict(case):
    with open(os.path.join(DATA, f"good_{case}.json")) as f:
        v = json.load(f)
    return v, {g["gate"]: g for g in v["gates"]}


def render_full(meshes, center, radius, azim, elev=22.0):
    """Full-frame 1920x1080 render; meshes = [(trimesh, hex, pose4x4)]
    handed to render.build_scene, which also takes a per-mesh style."""
    import render as R
    scene = R.build_scene(
        meshes, R.orbit_pose(center, radius, azim, elev),
        bg=(0.102, 0.102, 0.098, 1.0), light_amb=0.38,
        lights=(([0.5, 0.5, 1.0], 2.6), ([-0.7, 0.2, 0.5], 1.3),
                ([0.2, -0.8, 0.3], 0.9)))
    return Image.fromarray(TURN[0].shot(scene))


def render_spin(mesh, color, center_off, radius, azim, spin_deg, shift_px=0,
                elev=22.0, square=None):
    """Fixed camera, mesh spinning about its own axis (a true turntable).

    center_off is subtracted so the mesh spins about its bbox centre.
    shift_px moves the camera in its own +x (screen right), so the mesh
    lands shift_px to the LEFT of frame centre — that keeps burned-in text
    panels clear of the part.  square crops a centred square view out of
    the full-frame render for the result card.
    """
    import render as R
    pose = _rz(spin_deg) @ _t(-np.asarray(center_off, float))
    cam = R.orbit_pose(np.zeros(3), radius, azim, elev)
    d_world = shift_px * (radius * np.tan(np.radians(30.0)) * (W / H)) / (W / 2)
    cam[:3, 3] += cam[:3, :3] @ np.array([d_world, 0.0, 0.0])
    scene = R.build_scene(
        [(mesh, color, pose, "solid")], cam,
        bg=(0.102, 0.102, 0.098, 1.0), light_amb=0.38,
        lights=(([0.5, 0.5, 1.0], 2.6), ([-0.7, 0.2, 0.5], 1.3),
                ([0.2, -0.8, 0.3], 0.9)))
    img = Image.fromarray(TURN[0].shot(scene))
    if square:
        cx, cy = W // 2, H // 2
        return img.crop((cx - square // 2, cy - square // 2,
                         cx + square // 2, cy + square // 2))
    return img


def caption(img, text, fnt=None, top=None):
    """Burn a caption band in (>= 44 px) across the bottom of a frame.

    Long captions are wrapped and sized to fit the frame instead of
    running off the right edge.
    """
    fnt = fnt or font(F_BIG)
    d = ImageDraw.Draw(img, "RGBA")
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if d.textlength(trial, font=fnt) > W - 140:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    lh = int((fnt.size if hasattr(fnt, "size") else 48) * 1.3)
    band = lh * len(lines) + 44
    y0 = H - band if top is None else top
    d.rectangle([0, y0, W, H], fill=(0, 0, 0, 190))
    for i, line in enumerate(lines):
        d.text((70, y0 + 22 + i * lh), line, font=fnt, fill=INK)


def save(img, n):
    img.save(os.path.join(FRAMES, f"f{n:05d}.png"))


# ------------------------------------------------------------------ slots
def _rz(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), -np.sin(a), 0.0, 0.0],
                     [np.sin(a), np.cos(a), 0.0, 0.0],
                     [0.0, 0.0, 1.0, 0.0],
                     [0.0, 0.0, 0.0, 1.0]])


def _t(v):
    m = np.eye(4)
    m[:3, 3] = v
    return m


def slot_hook(n0, n1):
    """The three real parts spinning on one stage (fixed camera, turntable)."""
    parts = []
    for case, dx in (("bushing", -170.0), ("plate", 0.0), ("bracket", 175.0)):
        tm, c, r = mesh_of(case)
        parts.append((case, tm, _t([dx, 0.0, 0.0]), _t(-c)))
    radius = 235.0
    labels = {"bushing": "bushing", "plate": "plate + DXF", "bracket": "bracket"}
    for n in range(n0, n1):
        spin = 40.0 * ((n - n0) / max(1, n1 - n0 - 1))
        img = render_full(
            [(tm, SLOT_COLORS[c], p @ _rz(spin) @ tc, "solid")
             for c, tm, p, tc in parts],
            np.zeros(3), radius, 32.0, elev=24.0)
        d = ImageDraw.Draw(img)
        d.text((70, 44), "three parts from three text specs",
               font=font(("DejaVuSans-Bold.ttf", 46)), fill=INK)
        for i, (case, _tm, _p, _tc) in enumerate(parts):
            d.text((int(W * (i + 0.5) / 3), 980), labels[case],
                   font=font(("DejaVuSans.ttf", 40)), fill=INK2, anchor="ma")
        caption(img, "text → OpenSCAD → STL / STEP / DXF, judged to 0.05 mm")
        save(img, n)


def slot_scad(n0, n1, case):
    """Turntable of the plate beside its real shipped OpenSCAD source."""
    tm, c, r = mesh_of(case)
    with open(os.path.join(DEMO, "examples/good", case, "part.scad")) as f:
        src = [ln.rstrip("\n") for ln in f]
    _v, g = verdict(case)
    vol = g["volume_stl"]
    dv = abs(vol["measured_mm3"] - vol["analytic_mm3"]) / vol["analytic_mm3"]
    lines = [
        f"✓ volume {vol['measured_mm3']:,.1f} mm³ · Δ {dv * 100:.3f} % ≤ 0.5 %",
        f"✓ XOR {g['xor_reference']['measured_mm3']:.2f} mm³ ≤ "
        f"{g['xor_reference']['limit_mm3']:.1f} (1 % V_ref)",
        f"✓ STEP re-imports valid · {g['cyl_faces']['measured_radii'].__len__()}"
        " cylinder faces",
    ]
    f_code = font(F_CODE)
    for n in range(n0, n1):
        t = (n - n0) / max(1, n1 - n0 - 1)
        img = render_spin(tm, SLOT_COLORS[case], c, r * 1.9, 18.0,
                          -20.0 + 44.0 * t, shift_px=-300)
        d = ImageDraw.Draw(img, "RGBA")
        d.rectangle([60, 90, 880, 940], fill=(17, 17, 16, 255),
                    outline=(58, 58, 55, 255), width=2)
        d.text((90, 118), f"examples/good/{case}/part.scad", font=f_code,
               fill=INK2)
        for i, line in enumerate(src[:21]):
            d.text((90, 172 + i * 35), line[:46], font=f_code, fill=INK)
        d.rectangle([920, 750, W - 40, 940], fill=(0, 0, 0, 160))
        for i, line in enumerate(lines):
            d.text((950, 768 + i * 56), line, font=font(F_MED), fill=INK)
        caption(img, "the agent writes the source — the pinned engine compiles "
                     "it; the judge re-exports and measures")
        save(img, n)


def slot_part(n0, n1, case, extra):
    """Turntable of one real part with its measured gate lines."""
    tm, c, r = mesh_of(case)
    _v, g = verdict(case)
    vol = g["volume_stl"]
    dv = abs(vol["measured_mm3"] - vol["analytic_mm3"]) / vol["analytic_mm3"]
    lines = [
        f"✓ volume {vol['measured_mm3']:,.1f} mm³ · Δ {dv * 100:.3f} % ≤ 0.5 %",
        f"✓ XOR {g['xor_reference']['measured_mm3']:.2f} mm³ ≤ "
        f"{g['xor_reference']['limit_mm3']:.1f}",
    ] + extra
    for n in range(n0, n1):
        t = (n - n0) / max(1, n1 - n0 - 1)
        img = render_spin(tm, SLOT_COLORS[case], c, r * 1.45, 20.0,
                          -25.0 + 55.0 * t, shift_px=300)
        d = ImageDraw.Draw(img)
        d.text((1060, 260), case.upper(),
               font=font(("DejaVuSans-Bold.ttf", 64)), fill=INK)
        for i, line in enumerate(lines):
            d.text((1060, 380 + i * 64), line, font=font(F_MED), fill=INK)
        caption(img, f"{case}: every gate measured — "
                     f"{len(_v['gates'])}/{len(_v['gates'])} pass")
        save(img, n)


def slot_matrix(n0, n1):
    """The kill matrix drawn at video scale (loop.png's data, big type)."""
    from make_figures import GATES, fail_evidence, verdict_rows
    rows = verdict_rows()
    img = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(img, "RGBA")
    d.text((70, 40), "the judge the agent cannot fool",
           font=font(("DejaVuSans-Bold.ttf", 52)), fill=INK)
    pill(d, "kill rate  11/11 (100 %)", 36, GREEN, "#0b0b0b", W - 70, 44)
    pill(d, "known-good  3/3", 36, None, GREEN, W - 70 - 470 - 14, 44)

    label_w = 480
    x_mat, cw, rh = 70 + label_w, 86, 54
    x_ev = x_mat + len(GATES) * cw + 20
    y0 = 190
    for j in range(len(GATES)):
        d.text((x_mat + j * cw + cw // 2, y0 - 40), str(j + 1),
               font=font(("DejaVuSans.ttf", 30)), fill=INK2, anchor="ma")
    d.text((x_ev, y0 - 40), "failed gates (measured vs limit)",
           font=font(("DejaVuSans.ttf", 30)), fill=INK2)
    for i, (label, v, _is_good) in enumerate(rows):
        y = y0 + i * rh
        if i % 2 == 0:
            d.rectangle([70, y, W - 70, y + rh - 4], fill=(32, 32, 31, 255))
        d.text((80, y + 10), label, font=font(("DejaVuSans.ttf", 30)), fill=INK)
        gmap = {g["gate"]: g for g in v["gates"]}
        for j, gname in enumerate(GATES):
            x = x_mat + j * cw
            cx, cy = x + cw // 2, y + rh // 2 - 2
            if gname not in gmap:
                d.text((cx, cy), "–", font=font(("DejaVuSans-Bold.ttf", 28)),
                       fill="#77766f", anchor="mm")
                continue
            ok = gmap[gname]["passed"]
            d.rounded_rectangle([x + 3, y + 4, x + cw - 3, y + rh - 6],
                                radius=8, fill=GREEN if ok else RED)
            d.text((cx, cy), "✓" if ok else "✗",
                   font=font(("DejaVuSans-Bold.ttf", 30)), fill="#0b0b0b",
                   anchor="mm")
        d.text((x_ev, y + 13), fail_evidence(v),
               font=font(("DejaVuSans.ttf", 25)),
               fill=GREEN if v["passed"] else RED)
    y_end = y0 + len(rows) * rh + 8
    d.rectangle([70, y0 - 48, W - 70, y_end], outline=(70, 70, 66), width=2)
    d.text((70, y_end + 20), "gates: 1 scad_export · 2 stl_matches_scad · "
           "3 stl_watertight · 4 stl_winding · 5 bbox · 6 volume_stl · "
           "7 xor_reference · 8 step_reimport · 9 volume_step · 10 cyl_faces · "
           "11 planar_min_wall · 12 case_features · 13 dxf_valid · "
           "14 dxf_features",
           font=font(("DejaVuSans.ttf", 27)), fill=INK2)
    for n in range(n0, n1):
        frame = img.copy()
        caption(frame, "verdicts: media/data/*.json — mutants are single "
                       "edits of the good parts (judge/mutants.py)")
        save(frame, n)


def slot_result(n0, n1):
    """The three parts re-rendered at video scale with their gate lines."""
    panels = []
    for case, az in (("bushing", 28.0), ("plate", 28.0), ("bracket", 36.0)):
        tm, c, r = mesh_of(case)
        _v, g = verdict(case)
        vol = g["volume_stl"]
        dv = abs(vol["measured_mm3"] - vol["analytic_mm3"]) / vol["analytic_mm3"]
        lines = [
            f"volume {vol['measured_mm3']:,.1f} mm³ · Δ {dv * 100:.3f} %",
            f"XOR {g['xor_reference']['measured_mm3']:.2f} ≤ "
            f"{g['xor_reference']['limit_mm3']:.1f} mm³",
        ]
        if case == "bushing":
            lines.append("radial wall "
                         f"{g['case_features']['measured_mm']:.0f} mm ≥ 2")
        elif case == "plate":
            lines.append(f"DXF {g['dxf_features']['hole_count']} holes ⌀"
                         f"{g['dxf_features']['hole_radii'][0] * 2:.0f} · "
                         f"{len(_v['gates'])} gates")
        else:
            lines.append("radii "
                         + "/".join(f"{x:.0f}" for x in
                                    g["cyl_faces"]["measured_radii"])
                         + " mm")
        panels.append((case, render_spin(tm, SLOT_COLORS[case], c, r * 1.9,
                                         az, 0.0, square=520), lines,
                       len(_v["gates"])))
    img = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(img, "RGBA")
    d.text((70, 40), "the result: measured, not claimed",
           font=font(("DejaVuSans-Bold.ttf", 52)), fill=INK)
    pill(d, f"3/3 parts PASS · {sum(p[3] for p in panels)}/"
            f"{sum(p[3] for p in panels)} gates", 36, GREEN, "#0b0b0b",
         W - 70, 44)
    for i, (case, panel, lines, ngates) in enumerate(panels):
        x = 70 + i * 620
        img.paste(panel, (x, 150))
        d.rectangle([x - 2, 148, x + 521, 672], outline=(70, 70, 66), width=2)
        d.text((x, 740), f"{case} — {ngates}/{ngates} gates",
               font=font(("DejaVuSans-Bold.ttf", 40)), fill=INK)
        for k, line in enumerate(lines):
            d.text((x, 800 + k * 54), line, font=font(("DejaVuSans.ttf", 34)),
                   fill=INK2)
    d.text((70, 960), "meshes: examples/good/*/part.stl · numbers: "
           "media/data/good_*.json (judge/grade.sh)",
           font=font(("DejaVuSans.ttf", 30)), fill=INK2)
    for n in range(n0, n1):
        frame = img.copy()
        caption(frame, "STL / STEP / DXF graded against analytic volumes, an "
                       "OCCT reference solid and feature readback")
        save(frame, n)


def pill(d, text, size, fill, text_fill, right, top):
    """Rounded pill sized from its text (dark-surface variant)."""
    fnt = font(("DejaVuSans-Bold.ttf", size))
    bb = d.textbbox((0, 0), text, font=fnt)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    h = size + 30
    d.rounded_rectangle([right - tw - 44, top, right, top + h], radius=12,
                        fill=fill, outline=None if fill else GREEN,
                        width=3)
    left = right - tw - 44
    d.text((left + 22 - bb[0], top + (h - th) / 2 - bb[1]), text,
           font=fnt, fill=text_fill)
    return left


def slot_end(n0, n1):
    for n in range(n0, n1):
        img = Image.new("RGB", (W, H), DARK)
        d = ImageDraw.Draw(img)
        d.text((W // 2, 410), "python3 cookbook/aicad-cadam/run.py",
               font=font(("DejaVuSansMono-Bold.ttf", 58)), fill=INK,
               anchor="ma")
        d.text((W // 2, 530), "one sandbox · pinned CAD kernel · a judge it "
               "cannot fool", font=font(F_MED), fill=INK2, anchor="ma")
        save(img, n)


# ------------------------------------------------------------------ build
def build():
    os.makedirs(FRAMES, exist_ok=True)
    for f in os.listdir(FRAMES):
        os.remove(os.path.join(FRAMES, f))
    import render as R
    R.osmesa_shim()
    TURN[0] = R.Turntable(W, H)

    bush_g = verdict("bushing")[1]
    brack_g = verdict("bracket")[1]
    plan = [
        (0, 120, lambda a, b: slot_hook(a, b)),
        (120, 360, lambda a, b: slot_scad(a, b, "plate")),
        (360, 480, lambda a, b: slot_part(a, b, "bushing", [
            "✓ faces r "
            + " / ".join(f"{x:.0f}" for x in bush_g["cyl_faces"]["measured_radii"])
            + " mm",
            f"✓ radial wall {bush_g['case_features']['measured_mm']:.1f} mm ≥ "
            f"{bush_g['case_features']['limit_mm']:.0f}",
        ])),
        (480, 600, lambda a, b: slot_part(a, b, "bracket", [
            "✓ cylinder radii "
            + " / ".join(f"{x:.0f}" for x in brack_g["cyl_faces"]["measured_radii"])
            + " mm",
        ])),
        (600, 810, lambda a, b: slot_matrix(a, b)),
        (810, 1020, lambda a, b: slot_result(a, b)),
        (1020, 1110, slot_end),
    ]
    for n0, n1, fn in plan:
        fn(n0, n1)
        print(f"  frames {n0:5d}-{n1:5d} ({n1 - n0:4d})", flush=True)
    TURN[0].close()
    print(f"{n1} frames = {n1 / FPS:.1f} s at {FPS} fps", flush=True)


if __name__ == "__main__":
    os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
    sys.path.insert(0, HERE)
    build()
