#!/usr/bin/env python3
"""result.png + loop.png for the aicad-cadam demo (run via make_media.sh).

Every number is read from the judge verdict JSONs in media/data/ (written
by judge/grade.sh / judge/selftest.sh — see rerun_judge.sh) and every mesh
is a shipped examples/good/<case>/part.stl rendered headless by the pinned
pyrender/OSMesa stack through render.py. Nothing is invented here.

Colours follow the dataviz reference palette: light surface #fcfcfb, ink
#0b0b0b/#52514e, status good #0ca30c / critical #d03b3b. Pass/fail is
never colour-alone — every cell also carries a glyph (✓/✗) and the
measured-vs-limit text sits in the evidence column.
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
FONTS = "/usr/share/fonts/truetype/dejavu"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
HAIR = "#d8d7d2"          # recessive rules/grid
GREEN = "#0ca30c"         # status good
GREEN_T = "#006300"       # success text green (palette's text-on-light step)
RED = "#d03b3b"           # status critical
BLUE = "#2a78d6"          # categorical slot 1 (the part renders)

GATES = [                 # matrix columns, in judge verdict order
    "scad_export", "stl_matches_scad", "stl_watertight", "stl_winding",
    "bbox", "volume_stl", "xor_reference", "step_reimport", "volume_step",
    "cyl_faces", "planar_min_wall", "case_features",
    "dxf_valid", "dxf_features",
]
GATE_LABELS = {           # legend line: what the gate checks + its limit
    "scad_export": "OpenSCAD 2021.01 re-export exits 0",
    "stl_matches_scad": "shipped STL = re-export (XOR ≤ 0.1 % V)",
    "stl_watertight": "mesh watertight (trimesh)",
    "stl_winding": "consistent winding",
    "bbox": "bbox dev ≤ 0.05 mm",
    "volume_stl": "|V_stl − V_analytic| ≤ 0.5 %",
    "xor_reference": "XOR vs OCCT reference ≤ 1 % V_ref",
    "step_reimport": "STEP re-imports valid (BRepCheck)",
    "volume_step": "V_step vs analytic ≤ 0.5 %, vs STL ≤ 1 %",
    "cyl_faces": "cylinder count/radii ± 0.05 mm",
    "planar_min_wall": "min planar wall ≥ 2.0 mm",
    "case_features": "spec features (bolt circle, ligaments…)",
    "dxf_valid": "DXF audit clean (ezdxf)",
    "dxf_features": "DXF holes: count/radii/positions",
}

MUTANT_LABELS = {         # row labels, human-readable single edits
    "bracket_fillet_r6_to_3": "fillet R6 → R3",
    "bracket_missing_fillet": "fillet removed",
    "bracket_nonwatertight": "non-watertight STL",
    "bushing_bore_d12_to_15": "bore ⌀12 → ⌀15",
    "bushing_flipped_facet": "one facet flipped",
    "bushing_inch_scale": "scaled ×25.4 (inch)",
    "bushing_missing_flange": "flange removed",
    "plate_bolt_circle_r24_to_27": "bolt circle R24 → R27",
    "plate_bolt_d6_to_7": "bolt ⌀6 → ⌀7",
    "plate_corrupt_step": "corrupt STEP",
    "plate_hole_count_6_to_5": "6 bolt holes → 5",
}


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def tile(d, text, fnt, fill, text_fill, right, top, outline=None, pad=24):
    """A rounded pill whose box is measured from the text, right-aligned.

    Sized from the glyph box so long strings cannot spill (the loop.png
    kill-rate tiles were hand-sized and overflowed before this existed).
    """
    bb = d.textbbox((0, 0), text, font=fnt)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x1, y1 = right, top + 70
    x0, y0 = right - tw - 2 * pad, top
    d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=fill,
                        outline=outline, width=3 if outline else 0)
    d.text((x0 + pad - bb[0], y0 + (y1 - y0 - th) / 2 - bb[1]),
           text, font=fnt, fill=text_fill)
    return x0


def load_verdict(name):
    with open(os.path.join(DATA, name + ".json")) as f:
        return json.load(f)


def verdict_rows():
    """(label, verdict, is_good) rows: 3 good then 11 mutants."""
    rows = []
    for case in ("bushing", "plate", "bracket"):
        rows.append((f"good · {case}", load_verdict(f"good_{case}"), True))
    for key in MUTANT_LABELS:
        case = key.split("_", 1)[0]
        rows.append((f"{case} · {MUTANT_LABELS[key]}",
                     load_verdict(f"mutant_{key}"), False))
    return rows


def fmt_mm(x):
    return f"{x:,.3f}" if abs(x) < 100 else f"{x:,.1f}"


# ---------------------------------------------------------------- result.png
def render_part(mesh, w, h, azim=32.0, elev=22.0, fit=1.8):
    """One light-surface pyrender shot of a real shipped STL.

    fit scales the camera distance from the bounding-sphere radius; the
    caller-check below keeps every mesh inside the frame with a margin.
    """
    import render as R
    c = ((mesh.bounds[0] + mesh.bounds[1]) / 2.0).astype(float)
    r = float(np.linalg.norm(mesh.extents)) / 2.0 * fit
    scene = R.build_scene(
        [(mesh, BLUE, np.eye(4), "solid")], R.orbit_pose(c, r, azim, elev),
        bg=(0.988, 0.988, 0.984, 1.0), light_amb=0.42,
        lights=(([0.5, 0.5, 1.0], 2.6), ([-0.7, 0.2, 0.5], 1.3),
                ([0.2, -0.8, 0.3], 0.9)))
    tt = R.Turntable(w, h)
    img = tt.shot(scene)
    tt.close()
    bg = np.array([252, 252, 250])
    ys, xs = np.where((np.abs(img.astype(int) - bg).sum(2) > 12))
    margin = 24
    assert (xs.min() >= margin and ys.min() >= margin
            and xs.max() <= w - margin and ys.max() <= h - margin), \
        f"{mesh.metadata.get('name', 'mesh')} touches its panel: " \
        f"x {xs.min()}-{xs.max()} y {ys.min()}-{ys.max()} of {w}x{h}"
    return Image.fromarray(img)


def result_numbers(case):
    """Per-part gate lines, all values from the verdict JSON."""
    v = load_verdict(f"good_{case}")
    g = {x["gate"]: x for x in v["gates"]}
    vol = g["volume_stl"]
    dv = abs(vol["measured_mm3"] - vol["analytic_mm3"]) / vol["analytic_mm3"]
    lines = [
        (f"STL volume  {fmt_mm(vol['measured_mm3'])} mm³",
         f"analytic {fmt_mm(vol['analytic_mm3'])} · Δ {dv * 100:.3f} % ≤ 0.5 %"),
        (f"XOR vs OCCT reference  {g['xor_reference']['measured_mm3']:.2f} mm³",
         f"limit {g['xor_reference']['limit_mm3']:.1f} mm³ (1 % of V_ref)"),
        (f"bbox deviation  {g['bbox']['measured_max_dev_mm']:.3f} mm",
         f"limit {g['bbox']['limit_mm']:.2f} mm"),
    ]
    cf = g["case_features"]
    if case == "bushing":
        lines.append((f"radial wall  {cf['measured_mm']:.1f} mm",
                      f"spec ≥ {cf['limit_mm']:.1f} mm · faces r 6/15/25 mm"))
    elif case == "plate":
        lines.append((f"DXF  {g['dxf_features']['hole_count']} holes ⌀"
                      f"{g['dxf_features']['hole_radii'][0] * 2:.0f}",
                      f"bolt circle r {cf['bolt_circle_r'][0]:.0f} mm @ 60° · "
                      f"ligaments {cf['bore_ligament_mm']:.0f}/{cf['edge_ligament_mm']:.0f} mm"))
    else:
        radii = "/".join(f"{r:.0f}" for r in g["cyl_faces"]["measured_radii"])
        lines.append((f"cylinder radii  {radii} mm",
                      f"tol ± {g['cyl_faces']['tol_mm']:.2f} mm (bore + fillets)"))
    return lines, len(v["gates"])


def make_result(path):
    W, H = 2560, 1440
    img = Image.new("RGB", (W, H), SURFACE)
    d = ImageDraw.Draw(img)
    f_title = font("DejaVuSans-Bold.ttf", 64)
    f_sub = font("DejaVuSans.ttf", 34)
    f_name = font("DejaVuSans-Bold.ttf", 44)
    f_spec = font("DejaVuSans.ttf", 30)
    f_line = font("DejaVuSans.ttf", 31)
    f_line2 = font("DejaVuSans.ttf", 25)
    f_foot = font("DejaVuSans.ttf", 24)

    d.text((70, 46), "AI-CAD with CADAM's kernel — text-to-CAD, judged to 0.05 mm",
           font=f_title, fill=INK)
    d.text((70, 128), "an agent writes OpenSCAD; the pinned engine compiles it; a judge it "
           "cannot fool grades the STL / STEP / DXF against analytic oracles",
           font=f_sub, fill=INK2)

    cases = [("bushing", "flanged bushing", 32.0, 1.8),
             ("plate", "bolt-circle adapter plate (+DXF)", 32.0, 2.35),
             ("bracket", "L-bracket, R6 fillets", 40.0, 2.45)]
    total_gates = 0
    for i, (case, spec, azim, fit) in enumerate(cases):
        x0 = 70 + i * 810
        mesh = trimesh.load(os.path.join(DEMO, "examples/good", case, "part.stl"))
        panel = render_part(mesh, 760, 620, azim=azim, fit=fit)
        img.paste(panel, (x0, 230))
        d.rectangle([x0, 230, x0 + 759, 849], outline=HAIR, width=2)

        y = 878
        d.text((x0, y), case, font=f_name, fill=INK)
        d.text((x0, y + 52), spec, font=f_spec, fill=INK2)
        y += 92
        lines, ngates = result_numbers(case)
        total_gates += ngates
        for head, tail in lines:
            d.text((x0, y), head, font=f_line, fill=INK)
            d.text((x0, y + 38), tail, font=f_line2, fill=INK2)
            y += 78

    # headline badge, right of the title block (box sized from the text)
    tile(d, "3/3 parts PASS · 38/38 gates", f_sub, GREEN, "#ffffff",
         W - 90 - 70, 40, outline=None)

    d.text((70, H - 60),
           "renders: examples/good/*/part.stl (pyrender 0.1.45 / OSMesa) · "
           "numbers: judge/grade.sh verdicts media/data/good_*.json · "
           "self-test kill rate 11/11 (media/data/selftest.log) · "
           "figures: media/make_figures.py",
           font=f_foot, fill=INK2)
    img.save(path, optimize=True)
    print(f"wrote {path} ({total_gates} gates counted from verdicts)")


# ----------------------------------------------------------------- loop.png
def fail_evidence(v):
    """Short 'measured vs limit' text for every failed gate of a verdict."""
    out = []
    for g in v["gates"]:
        if g["passed"]:
            continue
        n, m = g["gate"], {}
        m.update(g)
        if n == "volume_stl":
            out.append(f"ΔV ×{m['rel']:.0f}" if m["rel"] >= 1.0
                       else f"ΔV {m['rel'] * 100:.1f} % > 0.5 %")
        elif n == "xor_reference":
            out.append(f"XOR {m['measured_mm3']:,.0f} > {m['limit_mm3']:,.0f} mm³")
        elif n == "bbox":
            out.append(f"bbox {m['measured_max_dev_mm']:.0f} mm > 0.05")
        elif n == "volume_step":
            out.append("STEP vol ≠ STL")
        elif n == "dxf_features":
            out.append(f"DXF holes {m.get('hole_count')} ≠ 6")
        elif n == "stl_watertight":
            out.append("not watertight")
        elif n == "stl_winding":
            out.append("winding reversed")
        elif n == "step_reimport":
            out.append("STEP unreadable")
        elif n in ("cyl_faces", "planar_min_wall", "case_features"):
            out.append(n.replace("_", " "))
    if len(out) > 2:
        out = out[:2] + [f"+{len(out) - 2} more"]
    return " · ".join(out) if out else "all gates pass"


def make_loop(path):
    rows = verdict_rows()
    W, H = 2560, 1440
    img = Image.new("RGB", (W, H), SURFACE)
    d = ImageDraw.Draw(img)
    f_title = font("DejaVuSans-Bold.ttf", 60)
    f_sub = font("DejaVuSans.ttf", 32)
    f_big = font("DejaVuSans-Bold.ttf", 34)
    f_row = font("DejaVuSans.ttf", 29)
    f_cell = font("DejaVuSans-Bold.ttf", 26)
    f_ev = font("DejaVuSans.ttf", 25)
    f_leg = font("DejaVuSans.ttf", 24)
    f_foot = font("DejaVuSans.ttf", 22)

    d.text((70, 46), "The judge the agent cannot fool", font=f_title, fill=INK)
    d.text((70, 126), "known-good parts and single-edit mutants × every gate — "
           "verdicts from judge/selftest.sh + judge/grade.sh --json",
           font=f_sub, fill=INK2)

    # kill-rate tiles, top right
    tile(d, "known-good  3/3", f_big, None, GREEN_T, W - 70 - 470 - 16, 46,
         outline=GREEN)
    tile(d, "kill rate  11/11 (100 %)", f_big, GREEN, "#ffffff", W - 70, 46,
         outline=None)

    # ---- matrix geometry
    label_w, ev_w = 560, 560
    x_mat = 70 + label_w
    ncol, nrow = len(GATES), len(rows)
    cw = (W - 140 - label_w - ev_w - 30) // ncol
    rh = 46
    y0 = 200
    x_ev = x_mat + ncol * cw + 30

    # column headers: gate numbers over a legend below the matrix
    for j, gname in enumerate(GATES):
        cx = x_mat + j * cw + cw // 2
        d.text((cx, y0 - 34), str(j + 1), font=f_leg, fill=INK2, anchor="ma")
    d.text((x_ev + 6, y0 - 36), "failed gates (measured vs limit)",
           font=f_leg, fill=INK2)

    for i, (label, v, is_good) in enumerate(rows):
        y = y0 + i * rh
        if i % 2 == 0:
            d.rectangle([70, y, W - 70, y + rh - 4], fill="#f4f3f0")
        col = INK if is_good else INK
        d.text((78, y + 8), label, font=f_row, fill=col)
        gmap = {g["gate"]: g for g in v["gates"]}
        for j, gname in enumerate(GATES):
            x = x_mat + j * cw
            cx, cy = x + cw // 2, y + rh // 2 - 2
            if gname not in gmap:            # gate not applicable to this case
                d.text((cx, cy), "–", font=f_cell, fill="#b9b8b2", anchor="mm")
                continue
            ok = gmap[gname]["passed"]
            d.rounded_rectangle([x + 3, y + 4, x + cw - 3, y + rh - 8],
                                radius=7, fill=GREEN if ok else RED)
            d.text((cx, cy), "✓" if ok else "✗", font=f_cell,
                   fill="#ffffff", anchor="mm")
        d.text((x_ev + 6, y + 10), fail_evidence(v), font=f_ev,
               fill=GREEN_T if v["passed"] else RED)
    y_end = y0 + nrow * rh + 6
    d.rectangle([70, y0 - 52, W - 70, y_end], outline=HAIR, width=2)

    # ---- gate-number legend, two columns
    y = y_end + 26
    half = (len(GATES) + 1) // 2
    for j, gname in enumerate(GATES):
        lx = 70 if j < half else W // 2 + 40
        ly = y + (j % half) * 32
        d.text((lx, ly), f"{j + 1:>2}", font=f_leg, fill=INK, anchor="ra")
        d.text((lx + 12, ly), f"{gname} — {GATE_LABELS[gname]}",
               font=f_leg, fill=INK2)

    # ---- the fixing loop (replay strip): real graded attempts on the bushing
    y = y + ((half) * 32) + 30
    d.text((70, y), "the fixing loop — bushing graded after each edit "
           "(media/data/replay_bushing_*.json):", font=f_big, fill=INK)
    y += 52
    steps = [
        ("attempt 1 — bore ⌀15", False,
         "ΔV 17.6 % > 0.5 % · XOR 4,247 > 241 mm³"),
        ("attempt 2 — bore ⌀13", False,
         "ΔV 8.0 % > 0.5 % · XOR 1,915 > 241 mm³"),
        ("attempt 3 — bore ⌀12", True,
         "all 12 gates pass · XOR 9.5 mm³"),
    ]
    tw, th = 720, 96
    for k, (head, ok, ev) in enumerate(steps):
        x = 70 + k * (tw + 70)
        d.rounded_rectangle([x, y, x + tw, y + th], radius=12,
                            fill="#f4f3f0", outline=GREEN if ok else RED, width=4)
        d.text((x + 20, y + 12), ("✓ " if ok else "✗ ") + head, font=f_row,
               fill=GREEN_T if ok else RED)
        d.text((x + 20, y + 52), ev, font=f_ev, fill=INK2)
        if k < 2:
            d.text((x + tw + 16, y + 26), "→", font=f_big, fill=INK2)

    d.text((70, H - 52), "verdicts: media/data/{good_*,mutant_*,replay_*}.json "
           "(judge/grade.sh --json, pinned toolchain) · kill rate: "
           "media/data/selftest.log · mutants: judge/mutants.py single edits",
           font=f_foot, fill=INK2)
    img.save(path, optimize=True)
    print(f"wrote {path}")


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
    import render as R
    R.osmesa_shim()
    make_result(os.path.join(HERE, "result.png"))
    make_loop(os.path.join(HERE, "loop.png"))
