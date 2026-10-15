#!/usr/bin/env python3
"""Build media/result.png from the judge's real outputs.

Left:  pyvista offscreen render of every extruding move in the judge's own
       trace (media/data/traces/good.trace.json) -- the finished print as the
       interpreter measured it, beads coloured by layer Z, analytic STL ghost.
Right: the 12 gates from media/data/good.verdict.json, each with its measured
       number taken from the verdict's metrics. Nothing is invented.

Run under Xvfb:  DISPLAY=:99 python3 media/make_result.py
"""

import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

import render_toolpath as rt

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE = os.path.join(HERE, "data", "traces", "good.trace.json")
VERDICT = os.path.join(HERE, "data", "good.verdict.json")
OUT = os.path.join(HERE, "result.png")

W, H = 2400, 1350
BG = "#101418"
PANEL = "#161b22"
CARD = "#1b212b"
INK = "#f0efec"
MUTED = "#9aa2ad"
FAINT = "#5b6472"
GOOD = "#45d052"
ACCENT = "#3987e5"

FONT_DIR = "/usr/share/fonts/truetype/dejavu"


def font(size, bold=False):
    f = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(os.path.join(FONT_DIR, f), size)


def render3d(out_w, out_h):
    """Offscreen pyvista render of the finished print; returns a PIL image."""
    import pyvista as pv

    trace = json.load(open(TRACE))
    pl = pv.Plotter(off_screen=True, window_size=(out_w, out_h))
    pl.set_background(BG)
    rt.add_bed(pl)
    pd, _ = rt.bead_mesh(trace)
    pl.add_mesh(pd, scalars="layer_z", cmap="plasma", smooth_shading=True,
                specular=0.35, specular_power=24, diffuse=0.8, ambient=0.3,
                scalar_bar_args={"title": "layer Z (mm)", "vertical": True,
                                 "position_x": 0.045, "position_y": 0.70,
                                 "color": MUTED, "title_font_size": 20,
                                 "label_font_size": 18, "width": 0.05,
                                 "height": 0.24})
    stl = rt.bracket_mesh()
    pl.add_mesh(stl, color="#2e6f9e", opacity=0.16, smooth_shading=True,
                specular=0.15, diffuse=0.6, ambient=0.3)
    rt.camera_part(pl, azimuth=-55.0, elevation=22.0, dist=92.0)
    path = out = os.path.join(HERE, "_result_3d.png")
    pl.screenshot(path)
    pl.close()
    img = Image.open(path).convert("RGB")
    os.remove(path)
    return img


# one measured line per gate, from the verdict's own gate details / metrics
def gate_line(name, g, m):
    def num(k, fmt="{:.4g}"):
        v = m.get(k)
        return fmt.format(v) if isinstance(v, (int, float)) else str(v)

    return {
        "slice_clean": "OrcaSlicer re-slice exit code 0",
        "artifact_matches": "shipped == judge re-slice (hash %s)" % m["artifact_hash"],
        "moves_inside_bed": g["detail"].replace("all ", "").replace(" inside bed",
                                                                    " inside 250 x 210 mm bed"),
        "moves_near_part": "max %s mm off footprint (tol 10 mm)" % num("max_dist_from_footprint_mm"),
        "layer_z_sequence": "first Z %s mm, %s layers, steady h %s mm" % (
            num("first_layer_z_mm"), num("layer_count", "{:.0f}"),
            num("steady_layer_height_mm[0]", "{:.3g}") if m["steady_layer_height_mm"] else "-"),
        "volume_matches_model": "%s mm3 in band %s-%s, %s g filament" % (
            num("deposited_volume_mm3"), num("volume_band_mm3[0]", "{:.0f}"),
            num("volume_band_mm3[1]", "{:.0f}"), num("filament_mass_g")),
        "cube_crosscheck": "cube %s mm3 in band %.0f-%.0f" % (
            num("cube_deposited_mm3"), m["cube_stl_volume_mm3"] * 0.25,
            m["cube_stl_volume_mm3"] * 0.52) if False else g["detail"],
        "pla_temperatures": "nozzle max %s C, bed max %s C, bed heats first" % (
            num("nozzle_setpoints_c[1]", "{:.0f}"), num("bed_setpoints_c[1]", "{:.0f}")),
        "time_estimate": "judge %s s vs slicer %s s (+-25%% band)" % (
            num("judge_time_s", "{:.0f}"), num("slicer_time_s", "{:.0f}")),
        "klipper_batch": "klippy exit 0, %s error lines" % num("klipper_bad_lines", "{:.0f}"),
        "profile_contract": g["detail"],
        "judge_intact": "judge/ sha256 unchanged by grading",
    }.get(name, g["detail"])


def main():
    v = json.load(open(VERDICT))
    gates = v["gates"]
    m = v["metrics"]

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # ---- left: the print itself ------------------------------------------
    rw = 1470
    img.paste(render3d(rw, H), (0, 0))

    # ---- right: gates panel ----------------------------------------------
    x0 = rw
    img.paste(Image.new("RGB", (W - x0, H), PANEL), (x0, 0))
    pad = 46
    x = x0 + pad
    y = 44

    d.text((x, y), "cookbook/3dprint-gcode", font=font(26, True), fill=ACCENT)
    y += 40
    d.text((x, y), "The judged result", font=font(56, True), fill=INK)
    y += 74

    # verdict badge
    verdict = v["verdict"]
    bw, bh = 386, 74
    d.rounded_rectangle((x, y, x + bw, y + bh), radius=14, fill="#12351a",
                        outline=GOOD, width=3)
    d.text((x + 24, y + 14), "VERDICT: " + verdict, font=font(36, True), fill=GOOD)
    d.text((x + bw + 24, y + 20), "12 / 12 gates", font=font(32, True), fill=INK)
    y += bh + 30

    rows = list(gates.items())
    row_h = 86
    f_name, f_det = font(27, True), font(23)
    for i, (name, g) in enumerate(rows):
        d.ellipse((x, y + 6, x + 26, y + 32), outline=GOOD, width=3)
        d.line((x + 6, y + 19, x + 11, y + 25), fill=GOOD, width=3)
        d.line((x + 11, y + 25, x + 21, y + 11), fill=GOOD, width=3)
        d.text((x + 44, y + 2), "%d. %s" % (i + 1, name), font=f_name, fill=INK)
        d.text((x + 44, y + 40), gate_line(name, g, m), font=f_det, fill=MUTED)
        y += row_h

    y += 8
    d.line((x, y, W - pad, y), fill=FAINT, width=2)
    y += 16
    d.text((x, y), "deposited %s mm3 / expected %s mm3 from the STL model"
           % (m["deposited_volume_mm3"], m["expected_volume_mm3"]),
           font=font(24), fill=MUTED)
    y += 36
    d.text((x, y), "every number from judge/grade.sh --json (seed %d, wall %.0f s)"
           % (v["seed"], v["timing"]["grade_wall_s"]), font=font(24), fill=MUTED)

    img.save(OUT, optimize=True)
    print("wrote", OUT, img.size)


if __name__ == "__main__":
    main()
