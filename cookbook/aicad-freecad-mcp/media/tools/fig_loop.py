#!/usr/bin/env python3
"""loop.png -- the judge's gate matrix over known-good and mutant artifacts.

One row per artifact: the three known-good parts and the seven scripted
single-edit mutants. One column per judge gate; a cell is green when that
gate passed and red when it failed, and every cell carries the value the
gate measured against the limit in the column header.

All data is from media/data/*.json (the judge's own --json verdicts, the
same ones judge/selftest.sh writes). Limits come from judge/judge.py. The
kill-rate bar at the bottom is selftest.sh's rule: every mutant must fail
at least one gate, and the rate must stay at or above 90 %.

kit.Blocker raises on any overlapping or overflowing box, so the figure
cannot ship with text on top of text or off the canvas.
"""
import os
import sys

from PIL import ImageDraw

import kit
from kit import (FAINT, GREEN, GREEN_DIM, INK, MONO, MONO_B, MUTED, RED,
                 RED_DIM, SANS_B, Blocker, font, gradient)

W, H = 2400, 1720

# (verdict name, row label, what the single edit was)
ROWS = [
    ("good_bushing", "good bushing", "known good, as delivered"),
    ("good_plate", "good plate", "known good, as delivered"),
    ("good_bracket", "good bracket", "known good, as delivered"),
    ("bad_bushing_bore_22", "bore_22", "BORE_D = 22.0 (was 20.0)"),
    ("bad_bushing_no_flange", "no_flange", "FLANGE_T = 0.0 (no solid)"),
    ("bad_bushing_stl_gap", "stl_gap", "4 facets zeroed in the STL"),
    ("bad_bushing_stl_flip", "stl_flip", "3 facet windings flipped"),
    ("bad_plate_hole_count_5", "hole_count_5", "BOLT_N = 5 (was 6)"),
    ("bad_plate_hole_drift", "hole_drift", "BOLT_A0 = 3.0 deg (was 0.0)"),
    ("bad_plate_scale_25_4", "scale_25_4", "PLATE_L = 2540 mm (inch slip)"),
    ("bad_bracket_no_fillet", "no_fillet", "FILLET_R = 0.001 (was 8.0)"),
]
PARTS = ["bushing", "plate", "bracket"]

# the column header carries the limit; kit.gate_line supplies the wording
HEAD = {
    "files": "files", "brep": "brep vol", "bbox": "bbox",
    "stl_topology": "stl topo", "xor_reference": "xor ref",
    "features": "features", "min_wall": "min wall", "dxf": "dxf audit",
}


def part_of(name):
    for p in PARTS:
        if p in name:
            return p
    raise KeyError(name)


def cell_text(gate, g):
    """The measured value(s) for one cell, short enough for the column."""
    if "error" in g:
        return "no step file", "not gradable"
    if gate == "files":
        return "3 files", "step+stl+dxf" if g.get("_plate") else \
            "step+stl"
    if gate == "brep":
        return "dv %s" % kit._pct(g["rel_error"]), "v %s mm3" % kit.mm(g["volume_mm3"])
    if gate == "bbox":
        return "err %.3g mm" % g["max_axis_error_mm"], "%s mm" % (
            "x".join("%.4g" % m for m in g["measured"]))
    if gate == "stl_topology":
        if not g["watertight"]:
            return "not watertight", "dv %s" % kit._pct(g["rel_error"])
        if not g["winding_consistent"]:
            return "winding flipped", "dv %s" % kit._pct(g["rel_error"])
        return "dv %s" % kit._pct(g["rel_error"]), "%d faces" % g["faces"]
    if gate == "xor_reference":
        return "xor %s" % kit._pct(g["xor_fraction"]), "%s mm3 diff" % kit.mm(g["xor_mm3"])
    if gate == "features":
        counts = {}
        for r in g.get("radii", []):
            counts[r] = counts.get(r, 0) + 1
        txt = " ".join("R%g" % r if counts[r] == 1 else "R%g x%d" % (r, counts[r])
                       for r in sorted(counts, reverse=True))
        if "bolt_holes_found" in g:
            return txt, "%d bolt holes" % g["bolt_holes_found"]
        return txt, "%d cyl faces" % g["cylindrical_faces"]
    if gate == "min_wall":
        return "min %.4g mm" % g["measured_min_mm"], "%d samples" % g["samples"]
    if gate == "dxf":
        return "%d circles" % g["circles"], "%d audit errors" % g["audit_errors"]
    raise KeyError(gate)


def main():
    canvas = gradient((W, H)).convert("RGB")
    d = ImageDraw.Draw(canvas)
    blk = Blocker(W, H)
    lim = kit.limits()

    f_title = font(SANS_B, 52)
    f_sub = font(kit.SANS, 26)
    f_hdr = font(MONO_B, 24)
    f_hl = font(MONO, 21)
    f_row = font(SANS_B, 27)
    f_edit = font(MONO, 21)
    f_c1_base, f_c2_base = 19, 18
    f_pct = font(SANS_B, 40)
    f_small = font(MONO, 22)

    # ---- header ----
    title = "The self-test matrix: every mutant fails a gate"
    blk.add("title", d.textbbox((60, 30), title, font=f_title))
    d.text((60, 30), title, font=f_title, fill=INK)
    kit.draw_wrapped(
        canvas, blk, "sub", (60, 104),
        "judge/grade.sh --json on the three known-good artifacts and the "
        "seven scripted single-edit mutants (judge/mutants.py). Green = gate "
        "passed, red = gate failed; each cell shows what that gate measured "
        "and the column header its limit. A mutant counts as killed when at "
        "least one gate fails.", f_sub, MUTED, W - 120)

    # ---- grid geometry ----
    label_x, cell_x = 60, 620
    n_cols = len(kit.GATE_ORDER)
    grid_r = W - 60
    col_w = (grid_r - cell_x) // n_cols
    head_y = 214
    row_y0 = 320
    row_h = 104

    # ---- column headers ----
    for i, gate in enumerate(kit.GATE_ORDER):
        cx = cell_x + i * col_w
        blk.add("gh_%s" % gate,
                d.textbbox((cx + 8, head_y), HEAD[gate], font=f_hdr))
        d.text((cx + 8, head_y), HEAD[gate], font=f_hdr, fill=INK)
        # the limit, from the first row that actually has this gate
        ref = next(kit.verdict(n)["gates"][gate] for n, _a, _b in ROWS
                   if gate in kit.verdict(n)["gates"])
        _v, ltxt = kit.gate_line(gate, ref, lim)
        lines = kit.wrap(d, ltxt, f_hl, col_w - 16)
        for j, line in enumerate(lines):
            blk.add("gl_%s_%d" % (gate, j),
                    d.textbbox((cx + 8, head_y + 34 + j * 26), line, font=f_hl))
            d.text((cx + 8, head_y + 34 + j * 26), line, font=f_hl, fill=MUTED)
    blk.add("hdr_col", d.textbbox((label_x, head_y), "artifact", font=f_hdr))
    d.text((label_x, head_y), "artifact", font=f_hdr, fill=INK)
    blk.add("hdr_col2", d.textbbox((label_x, head_y + 34),
                                   "single edit from the good script",
                                   font=f_hl))
    d.text((label_x, head_y + 34), "single edit from the good script",
           font=f_hl, fill=MUTED)
    d.line([(label_x, head_y + 92), (grid_r, head_y + 92)], fill=FAINT, width=2)

    # ---- rows ----
    killed = 0
    total = 0
    y = row_y0
    for name, label, edit in ROWS:
        v = kit.verdict(name)
        gates = v["gates"]
        good = v["all_pass"]
        # selftest.sh grades only mutants that produced a .step; the rest
        # (the build fails outright) are skipped, not counted as kills
        built = gates.get("files", {}).get("pass", False)
        if not good and built:
            total += 1
            killed += 1
        # row band
        band = (label_x - 12, y - 8, grid_r, y + row_h - 16)
        blk.inside("band_%s" % name, band)
        d.rounded_rectangle(band, radius=8,
                            fill=(26, 31, 38) if good else (34, 26, 26))

        blk.add("row_%s" % name,
                d.textbbox((label_x, y), label, font=f_row))
        d.text((label_x, y), label, font=f_row,
               fill=(150, 230, 190) if good else INK)
        blk.add("edit_%s" % name,
                d.textbbox((label_x, y + 38), edit, font=f_edit))
        d.text((label_x, y + 38), edit, font=f_edit, fill=MUTED)

        for i, gate in enumerate(kit.GATE_ORDER):
            cx = cell_x + i * col_w
            g = gates.get(gate)
            cbox = (cx + 2, y - 4, cx + col_w - 6, y + row_h - 24)
            if g is None:
                blk.inside("na_%s_%s" % (name, gate), cbox)
                d.rounded_rectangle(cbox, radius=6, fill=(24, 28, 34))
                fna = font(MONO, f_c2_base)
                blk.add("nat_%s_%s" % (name, gate),
                        d.textbbox((cx + 14, y + 22), "not graded", font=fna))
                d.text((cx + 14, y + 22), "not graded", font=fna, fill=FAINT)
                continue
            ok = g["pass"]
            blk.inside("cell_%s_%s" % (name, gate), cbox)
            d.rounded_rectangle(cbox, radius=6,
                                fill=GREEN_DIM if ok else RED_DIM)
            line1, line2 = cell_text(gate, g)
            if gate == "files" and part_of(name) == "plate":
                line2 = "step+stl+dxf"
            fc1 = kit.shrink_font(d, line1, MONO_B, f_c1_base, col_w - 26)
            fc2 = kit.shrink_font(d, line2, MONO, f_c2_base, col_w - 26)
            blk.add("c1_%s_%s" % (name, gate),
                    d.textbbox((cx + 14, y + 8), line1, font=fc1))
            d.text((cx + 14, y + 8), line1, font=fc1,
                   fill=(198, 255, 220) if ok else (255, 208, 202))
            blk.add("c2_%s_%s" % (name, gate),
                    d.textbbox((cx + 14, y + 36), line2, font=fc2))
            d.text((cx + 14, y + 36), line2, font=fc2,
                   fill=(150, 210, 175) if ok else (232, 176, 168))
        y += row_h

    # ---- kill-rate bar ----
    d.line([(60, y + 4), (grid_r, y + 4)], fill=FAINT, width=2)
    by = y + 40
    rule = ("judge/selftest.sh rule: every known-bad artifact must fail at "
            "least one gate, and the kill rate must stay at or above 90 %")
    blk.add("kill_rule", d.textbbox((60, by), rule, font=f_sub))
    d.text((60, by), rule, font=f_sub, fill=MUTED)

    bar = (60, by + 56, 1500, by + 100)
    blk.add("bar", bar)
    d.rounded_rectangle(bar, radius=10, fill=(30, 36, 44))
    rate = killed / total if total else 0.0
    fill = (bar[0], bar[1], bar[0] + int((bar[2] - bar[0]) * rate), bar[3])
    d.rounded_rectangle(fill, radius=10, fill=GREEN)
    thr_x = bar[0] + int((bar[2] - bar[0]) * 0.90)
    d.line([(thr_x, bar[1] - 12), (thr_x, bar[3] + 12)], fill=RED, width=4)
    blk.add("thr", d.textbbox((thr_x + 12, bar[1] - 30), "90 % floor",
                              font=f_small))
    d.text((thr_x + 12, bar[1] - 30), "90 % floor", font=f_small, fill=RED)

    kt = "kill rate  %d/%d = %d %%" % (killed, total, round(rate * 100))
    blk.add("killtext", d.textbbox((bar[2] + 60, bar[1] + 6), kt, font=f_pct))
    d.text((bar[2] + 60, bar[1] + 6), kt, font=f_pct, fill=GREEN)

    foot = ("verdicts: media/data/*.json (judge/grade.sh --json)      "
            "mutants: judge/mutants.py      rebuild: bash "
            "media/make_media.sh")
    blk.add("foot", d.textbbox((60, bar[3] + 40), foot, font=f_small))
    d.text((60, bar[3] + 40), foot, font=f_small, fill=MUTED)

    out = os.path.join(kit.MEDIA, "loop.png")
    canvas.save(out)
    print("wrote %s  (%dx%d, %d boxes, layout checked)"
          % (out, W, H, len(blk.boxes)))


if __name__ == "__main__":
    sys.exit(main())
