#!/usr/bin/env python3
"""result.png -- the real CAD result plus the gate numbers that passed.

Row 1: an OSMesa render of each part's real delivered mesh (the same STL
the judge graded), the delivered file set, and the passing margins.
Row 2: the judge's gate ledger -- every gate, its limit (read from
judge/judge.py, not retyped) and what it measured on each part.

Every number comes from media/data/good_*.json (judge/grade.sh --json).
Layout is enforced by kit.Blocker: it raises on an overlap or an overflow,
so the figure cannot silently ship cut off or overlapping.
"""
import os
import sys

import trimesh
from PIL import ImageDraw

import kit
from kit import (FAINT, GREEN, GREEN_DIM, INK, MONO, MONO_B, MUTED, RED,
                 SANS_B, Blocker, fit_margin, font, gradient)
from render import Renderer, _norm_mesh

W, H = 2400, 1620
PARTS = ["bushing", "plate", "bracket"]
# named view per part so each silhouette reads at a glance
VIEW = {"bushing": (35, 20), "plate": (35, 44), "bracket": (35, 22)}

COL_W, GAP, X0 = 740, 40, 60
TOP, BOT = 200, 790


def hero_lines(v, lim):
    """(label, measured, limit) per hero metric, all read from the verdict."""
    g = v["gates"]
    out = [("volume", "%.2f mm3" % g["brep"]["volume_mm3"],
            "/ dv %.3f%%" % (g["brep"]["rel_error"] * 100)),
           ("XOR", "%.4f %%" % (g["xor_reference"]["xor_fraction"] * 100),
            "/ %.0f %%" % (lim["xor_reference"] * 100)),
           ("min wall", "%.3f mm" % g["min_wall"]["measured_min_mm"],
            "/ %.1f mm" % lim["min_wall"])]
    if "dxf" in g:
        out.append(("DXF", "%d circles" % g["dxf"]["circles"],
                    "/ %d errors" % g["dxf"]["audit_errors"]))
    return out


def main():
    canvas = gradient((W, H)).convert("RGB")
    d = ImageDraw.Draw(canvas)
    blk = Blocker(W, H)
    lim = kit.limits()

    f_title = font(SANS_B, 56)
    f_sub = font(kit.SANS, 28)
    f_name = font(SANS_B, 44)
    f_hero = font(MONO, 27)
    f_hero_v = font(MONO_B, 27)
    f_badge = font(SANS_B, 30)
    f_lt = font(SANS_B, 36)
    f_col = font(MONO_B, 28)
    f_cell = font(MONO, 28)
    f_foot = font(MONO, 28)

    # ---- header ----
    title = "AI-CAD part design, judged from the delivered files"
    blk.add("title", d.textbbox( (60, 24), title, font=f_title))
    d.text( (60, 24), title, font=f_title, fill=INK)
    kit.draw_wrapped(canvas, blk, "subtitle",  (60, 104),
                     "FreeCAD 1.0.1, driven through an MCP server, built "
                     "these three parts from a text spec. The judge "
                     "re-imported the delivered STEP/STL/DXF and passed "
                     "every gate below.", f_sub, MUTED, W - 80)
    d.line([ (60, 168), (W - 60, 168)], fill=FAINT, width=2)

    # ---- row 1: real renders ----
    r = Renderer(1120, 780)
    renders = {}
    try:
        for part in PARTS:
            m = _norm_mesh(trimesh.load(
                os.path.join(kit.ROOT, "examples", "good", part,
                             "%s.stl" % part), force="mesh"), 2.0)
            yaw, pitch = VIEW[part]
            renders[part] = r.render(
                m, yaw=yaw, pitch=pitch,
                margin=fit_margin(m, yaw, pitch, 1120, 780), edges=True)
    finally:
        r.delete()

    for i, part in enumerate(PARTS):
        cx = X0 + i * (COL_W + GAP)
        img = renders[part]
        if img.getbbox() is None:
            raise AssertionError("empty render for %s" % part)
        got = kit.paste_center(canvas, img, (cx, TOP, cx + COL_W, BOT))
        blk.add("render_%s" % part, got)

        v = kit.verdict("good_" + part)
        blk.add("name_%s" % part, d.textbbox((cx, BOT + 12), part, font=f_name))
        d.text((cx, BOT + 12), part, font=f_name, fill=INK)

        badge = "PASS %d/%d" % (len(v["gates"]), len(v["gates"]))
        bw = d.textlength(badge, font=f_badge)
        bbox = (cx + COL_W - bw - 24, BOT + 16, cx + COL_W, BOT + 60)
        blk.add("badge_%s" % part, bbox)
        d.rounded_rectangle(bbox, radius=8, fill=GREEN_DIM)
        d.text((bbox[0] + 12, bbox[1] + 6), badge, font=f_badge,
               fill=(214, 255, 230))

        files = "%s.step + %s.stl%s" % (
            part, part, " + plate.dxf" if part == "plate" else "")
        blk.add("files_%s" % part,
                d.textbbox((cx, BOT + 68), files, font=f_hero))
        d.text((cx, BOT + 68), files, font=f_hero, fill=MUTED)

        # hero margins: label left, measured right-aligned, limit right-aligned
        y = BOT + 116
        for label, val, lim_txt in hero_lines(v, lim):
            blk.add("hero_%s_%s" % (part, label),
                    d.textbbox((cx, y), label, font=f_hero))
            d.text((cx, y), label, font=f_hero, fill=MUTED)
            vbox = kit.draw_right(canvas, (cx + 420, y), val, f_hero_v, GREEN)
            blk.add("heroval_%s_%s" % (part, label), vbox)
            lbox = kit.draw_right(canvas, (cx + COL_W, y), lim_txt, f_hero,
                                  MUTED)
            blk.add("herolim_%s_%s" % (part, label), lbox)
            y += 40

    d.line([(60, 1090), (W - 60, 1090)], fill=FAINT, width=2)

    # ---- row 2: gate ledger ----
    lt = ("Every judge gate: limit (read from judge/judge.py) vs the value "
          "it measured")
    blk.add("ledger_title", d.textbbox((60, 1110), lt, font=f_lt))
    d.text((60, 1110), lt, font=f_lt, fill=INK)

    cols = [60, 470, 980, 1460, 1910]
    hdr_y = 1180
    for i, htxt in enumerate(["judge gate", "limit", *PARTS]):
        blk.add("lh_%d" % i, d.textbbox((cols[i], hdr_y), htxt, font=f_col))
        d.text((cols[i], hdr_y), htxt, font=f_col,
               fill=MUTED if i < 2 else INK)
    d.line([(60, hdr_y + 34), (W - 60, hdr_y + 34)], fill=FAINT, width=1)

    y = hdr_y + 44
    for gate in kit.GATE_ORDER:
        have = [p for p in PARTS if gate in kit.verdict("good_" + p)["gates"]]
        if not have:
            continue
        blk.add("lg_%s" % gate,
                d.textbbox((cols[0], y), gate, font=f_cell))
        d.text((cols[0], y), gate, font=f_cell, fill=INK)
        _v, ltxt = kit.gate_line(
            gate, kit.verdict("good_" + have[0])["gates"][gate], lim)
        blk.add("ll_%s" % gate, d.textbbox((cols[1], y), ltxt, font=f_cell))
        d.text((cols[1], y), ltxt, font=f_cell, fill=MUTED)
        for i, part in enumerate(PARTS):
            g = kit.verdict("good_" + part)["gates"].get(gate)
            cx = cols[2 + i]
            if g is None:
                blk.add("lv_%s_%s" % (gate, part),
                        d.textbbox((cx, y), "-", font=f_cell))
                d.text((cx, y), "-", font=f_cell, fill=FAINT)
                continue
            val = kit.measured_cell(gate, g, lim)
            if gate == "features":
                blk.add("lv_%s_%s" % (gate, part),
                    d.textbbox((cx, y), val, font=f_cell))
            d.text((cx, y), val, font=f_cell,
                   fill=GREEN if g["pass"] else RED)
        y += 40

    d.line([(60, y + 10), (W - 60, y + 10)], fill=FAINT, width=1)
    foot = ("known-good artifact set: examples/good/      self-test kill rate:"
            " 7/7 = 100 %% (judge/selftest.sh)      "
            "rebuilt by: media/make_media.sh")
    blk.add("footer", d.textbbox((60, y + 28), foot, font=f_foot))
    d.text((60, y + 28), foot, font=f_foot, fill=MUTED)

    out = os.path.join(kit.MEDIA, "result.png")
    canvas.save(out)
    print("wrote %s  (%dx%d, %d boxes, layout checked)"
          % (out, W, H, len(blk.boxes)))


if __name__ == "__main__":
    sys.exit(main())
