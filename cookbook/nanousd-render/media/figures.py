#!/usr/bin/env python3
"""Build media/result.png and media/loop.png (run by make_media.sh).

result.png — the hero still: the judge's own graded render with the G4
oracle's projected rectangles (the pass line) and per-mesh numbers drawn
ON the real render, plus the verdict numbers beside it. 200 dpi,
colour-blind-safe (Okabe-Ito) overlay palette.

loop.png — the agent loop: gates passed per iteration until the grade
passes (each iteration is a REAL grade run on a real single-edit artifact
generated here from the good scene), plus the self-test kill-rate bars
per mutant. Every number is measured; nothing is illustrative.

Usage: PREFIX/venv/bin/python figures.py   (needs numpy + pillow)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
DEMO = os.path.dirname(HERE)
GOOD = os.path.join(DEMO, "examples", "good", "scene.usda")
GRADE = os.path.join(DEMO, "judge", "grade.sh")
FONT_DIR = os.environ.get(
    "DEMO_FONT_DIR", "/usr/share/fonts/truetype/dejavu")

DPI = 200
# 12.0 x 6.75 in at 200 dpi = 16:9, readable at 1200 px wide
PW, PH = 2400, 1350

INK = (232, 236, 242)
MUTED = (154, 162, 174)
PAPER = (13, 15, 19)
PANEL = (18, 21, 27)
PASS = (126, 231, 135)
FAILC = (240, 113, 99)
ACCENT = (255, 205, 60)
OI = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7"]


def font(kind, size):
    names = {"sans": "DejaVuSans.ttf", "bold": "DejaVuSans-Bold.ttf",
             "mono": "DejaVuSansMono.ttf", "monobold": "DejaVuSansMono-Bold.ttf"}
    return ImageFont.truetype(os.path.join(FONT_DIR, names[kind]), size)


def rgb(hexcol):
    return tuple(int(hexcol[j:j + 2], 16) for j in (1, 3, 5))


# ------------------------------------------------------------------ result

def build_result() -> None:
    verdict = json.load(open(os.path.join(BUILD, "verdict.json")))
    render = Image.open(os.path.join(BUILD, "render.png")).convert("RGB")
    g4 = verdict["gates"]["G4"]["meshes"]

    img = Image.new("RGB", (PW, PH), PAPER)
    d = ImageDraw.Draw(img, "RGBA")

    # -- left panel: the graded render with the pass line on it.
    #    The 130 px gutter on the left holds the y tick labels and the
    #    rotated y-axis label, so no tick text is clipped at the canvas edge.
    px, py, pad = 190, 150, 20
    rw = 1440
    rh = int(rw * render.size[1] / render.size[0])       # 4:3 -> 1140
    big = render.resize((rw, rh), Image.LANCZOS)
    img.paste(big, (px + pad, py + pad))
    d.rectangle([px, py, px + pad * 2 + rw, py + pad * 2 + rh],
                outline=(70, 78, 90), width=2)

    # oracle rectangles (the pass line), scaled from the 640x480 grade frame
    f_lab = font("bold", 40)
    # mesh labels sit above their rectangle, but never grow into the
    # right-hand verdict panel: a rectangle near the frame's right edge
    # gets its label right-aligned INSIDE it instead.
    label_right = px + pad + rw          # right edge of the render pane
    for i, (path, m) in enumerate(sorted(g4.items())):
        col = rgb(OI[i % len(OI)])
        x0, y0, x1, y1 = m["rect"]
        s = rw / 640.0
        box = [px + pad + x0 * s, py + pad + y0 * s,
               px + pad + x1 * s, py + pad + y1 * s]
        for off in (-4, 4):
            d.rectangle([box[0] + off, box[1] + off, box[2] - off, box[3] - off],
                        outline=col, width=5)
        name = path.rsplit("/", 1)[-1]
        txt = f"{name}  k={m['illuminance_k']:.2f}"
        tw = d.textlength(txt, font=f_lab)
        if box[0] + 10 + tw <= label_right:
            lx, ly = box[0] + 10, max(py + pad + 4, box[1] - 58)
        else:
            lx, ly = box[2] - 10 - tw, max(py + pad + 4, box[1] - 58)
        d.text((lx, ly), txt, font=f_lab,
               fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))

    # axes around the render (the oracle's pixel space), with units.
    # The tick labels are drawn INSIDE the plot gutter (the labels sit to
    # the left of x=0 / above y=0 are never cut by the canvas edge).
    fa = font("mono", 30)
    gutter = 130                      # room for the y tick labels
    for xv in range(0, 641, 160):
        X = px + pad + xv * s
        d.line([X, py + pad + rh + 10, X, py + pad + rh + 26],
               fill=(120, 128, 140), width=2)
        lab = str(xv)
        d.text((X - d.textlength(lab, font=fa) / 2, py + pad + rh + 32),
               lab, font=fa, fill=MUTED)
    d.text((px + pad + rw // 2 - 150, py + pad + rh + 76),
           "projected pixel x (px, 640-wide grade frame)",
           font=fa, fill=MUTED)
    for yv in range(0, 481, 120):
        Y = py + pad + yv * (rh / 480.0)
        d.line([px + pad - 26, Y, px + pad - 10, Y],
               fill=(120, 128, 140), width=2)
        lab = str(yv)
        d.text((px + pad - 40 - d.textlength(lab, font=fa), Y - 16),
               lab, font=fa, fill=MUTED)
    # the y axis gets a label and a unit too, drawn rotated up the gutter
    ylab = Image.new("RGBA", (760, 40), (0, 0, 0, 0))
    ImageDraw.Draw(ylab).text((0, 0), "projected pixel y (px, 480-tall frame)",
                              font=fa, fill=MUTED)
    ylab = ylab.rotate(90, expand=True)
    img.paste(ylab, (px - gutter + 42, py + pad + rh // 2 - ylab.size[1] // 2),
              ylab)

    # -- right panel: the verdict numbers
    qx = px + pad * 2 + rw + 46
    qw = PW - qx - 60
    d.rectangle([qx, py, qx + qw, py + 900], fill=PANEL, outline=(70, 78, 90))
    y = py + 34
    d.text((qx + 30, y), "JUDGE VERDICT", font=font("bold", 44), fill=ACCENT)
    y += 78
    d.text((qx + 30, y), f"pass: {str(verdict['pass']).lower()}   "
                         f"seed: {verdict['seed']}",
           font=font("monobold", 40), fill=PASS)
    y += 66
    for g in ("G1", "G2", "G3", "G4"):
        info = verdict["gates"][g]
        extra = f"  rendered_frac {info['rendered_frac']}" \
            if "rendered_frac" in info else ""
        d.text((qx + 30, y), f"{g}: {str(info['pass']).lower()}{extra}",
               font=font("mono", 36), fill=PASS)
        y += 54
    y += 18
    d.text((qx + 30, y), "G4 oracle per mesh", font=font("bold", 38), fill=INK)
    y += 56
    # legend: authored colour chip + measured k and deviation
    for i, (path, m) in enumerate(sorted(g4.items())):
        col = rgb(OI[i % len(OI)])
        d.rectangle([qx + 30, y + 6, qx + 62, y + 38], fill=col)
        name = path.rsplit("/", 1)[-1]
        d.text((qx + 76, y), f"{name:<12}", font=font("mono", 34), fill=INK)
        d.text((qx + 300, y), f"k={m['illuminance_k']:.3f}",
               font=font("mono", 34), fill=INK)
        d.text((qx + 480, y), f"dev={m['own_dev']:.3f}",
               font=font("mono", 34), fill=INK)
        y += 50
    y += 14
    d.text((qx + 30, y), f"judge_integrity_ok: "
                         f"{str(verdict['judge_integrity_ok']).lower()}",
           font=font("mono", 34), fill=INK)

    # -- title + provenance footer. Both are measured to fit: the title is
    #    scaled down to the canvas and the footer wrapped to two lines, so
    #    neither is ever clipped at the right edge.
    t1 = "nanousd-render - two USD implementations agree,"
    t2 = "and a CPU render proves it"
    ft = font("bold", 54)
    while ft.size > 30 and (
            d.textlength(t1 + " " + t2, font=ft) > PW - 120):
        ft = font("bold", ft.size - 2)
    d.text((60, 34), t1, font=ft, fill=INK)
    d.text((60, 34 + ft.size + 12), t2, font=ft, fill=INK)

    foot = ("judge/grade.sh examples/good/scene.usda --seed 0 --json "
            "media/build/verdict.json   |   render: pinned nanousd OpenGL "
            "ES renderer on llvmpipe   |   rectangles: the G4 numpy pinhole "
            "oracle re-projected from each reader's world transforms")
    ff = font("mono", 26)
    while ff.size > 16 and d.textlength(foot, font=ff) > PW - 120:
        ff = font("mono", ff.size - 1)
    # break the footer on the two "|" separators so both halves stay inside
    parts = foot.split("   |   ")
    d.text((60, PH - 104), parts[0], font=ff, fill=MUTED)
    d.text((60, PH - 104 + ff.size + 14), " | ".join(parts[1:]),
           font=ff, fill=MUTED)

    img.save(os.path.join(HERE, "result.png"), dpi=(DPI, DPI))


# -------------------------------------------------------------------- loop

def edit(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit(f"iteration edit '{what}': pattern found "
                         f"{text.count(old)} times, expected 1")
    return text.replace(old, new, 1)


# The authoring loop, replayed honestly: four single-edit artifacts derived
# from the known-good scene, each graded for real by judge/grade.sh. These
# are STAGED single-edit replays (the same edits judge/mutants.py makes, so
# each one's failure is a measured gate verdict), not a recorded agent
# session -- the figure title says so rather than implying otherwise.
# The fourth artifact is the unmodified graded scene: the pass.
def iteration_files(outdir):
    good = open(GOOD, encoding="utf-8").read()
    its = [
        ("no light", edit(good,
                          '    def DistantLight "Sun"\n    {\n        float inputs:intensity = 1\n'
                          '        float3 xformOp:rotateXYZ = (-45, 30, 0)\n'
                          '        uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]\n    }\n', "",
                          "no light")),
        ("camera off", edit(good, "float3 xformOp:rotateXYZ = (-14, 0, 0)",
                            "float3 xformOp:rotateXYZ = (85, 0, 0)",
                            "camera off")),
        ("half off screen", edit(good,
                                 "float3 xformOp:translate = (4.2, 0.55, 0)",
                                 "float3 xformOp:translate = (5.7, 0.55, 0)",
                                 "half off screen")),
        ("graded scene", good),
    ]
    paths = []
    for i, (name, text_) in enumerate(its, 1):
        p = os.path.join(outdir, f"iter{i}.usda")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text_)
        paths.append((name, p))
    return paths


def grade(path, out_json):
    p = subprocess.run(["bash", GRADE, path, "--seed", "0", "--json", out_json],
                       capture_output=True, text=True)
    try:
        return json.load(open(out_json)), p.returncode
    except ValueError:
        return None, p.returncode


def build_loop() -> None:
    itdir = os.path.join(BUILD, "iters")
    os.makedirs(itdir, exist_ok=True)
    history = []
    for name, path in iteration_files(itdir):
        v, rc = grade(path, os.path.join(BUILD, "verdict_iter.json"))
        gates = v["gates"] if v else {}
        nfail = sum(1 for g in gates.values() if not g.get("pass"))
        which = ",".join(sorted(k for k, g in gates.items()
                                if not g.get("pass"))) or "PASS"
        history.append({"name": name, "pass": rc == 0, "failed": which,
                        "nfail": nfail})
    selftest = json.load(open(os.path.join(BUILD, "selftest.json")))

    img = Image.new("RGB", (PW, PH), PAPER)
    d = ImageDraw.Draw(img, "RGBA")

    d.text((60, 40), "Staged authoring iterations, then the self-test kill "
                     "matrix",
           font=font("bold", 52), fill=INK)
    d.text((60, 104),
           "four single-edit artifacts, each graded for real by "
           "judge/grade.sh: the loop an agent walks, replayed here from "
           "measured runs",
           font=font("sans", 28), fill=MUTED)

    # -- top: gates passed (of 4) per iteration
    x0, y0, w, h = 90, 200, 2220, 430
    d.rectangle([x0, y0, x0 + w, y0 + h], fill=PANEL, outline=(70, 78, 90))
    d.text((x0 + 24, y0 + 16),
           "gates passed per iteration (1 bar = one real grade.sh run; "
           "the bar's label is the gates that failed)",
           font=font("bold", 34), fill=INK)
    # the y-axis tick labels live in a dedicated gutter at the left of the
    # plot area, so none of them can overlap the first bar's label
    ax_x = x0 + 150                    # left edge of the plot area
    step = (w - 260) / max(1, len(history) - 1)
    base_y = y0 + h - 96
    for gy in range(5):
        Y = base_y - gy * 62
        d.line([ax_x, Y, x0 + w - 40, Y], fill=(50, 56, 66), width=1)
        lab = str(gy)
        d.text((ax_x - 24 - d.textlength(lab, font=font("mono", 28)),
                Y - 16), lab, font=font("mono", 28), fill=MUTED)
    d.text((x0 + 34, y0 + 60), "gates", font=font("sans", 26), fill=MUTED)
    d.text((x0 + 34, base_y + 10), "passed", font=font("sans", 26),
           fill=MUTED)
    for i, it in enumerate(history):
        X = ax_x + 130 + i * step
        col = PASS if it["pass"] else FAILC
        top = base_y - (4 - it["nfail"]) * 62
        d.rectangle([X - 52, top, X + 52, base_y], fill=col)
        lab = f"it{i+1}: {it['name']}"
        fl = font("mono", 26)
        # centre the label under its bar and shrink it until it fits the
        # step, so the last one is never clipped by the panel edge
        while fl.size > 16 and d.textlength(lab, font=fl) > step - 16:
            fl = font("mono", fl.size - 1)
        d.text((X - d.textlength(lab, font=fl) / 2, base_y + 14), lab,
               font=fl, fill=INK)
        tag = "PASS" if it["pass"] else it["failed"]
        ft = font("monobold", 26)
        d.text((X - d.textlength(tag, font=ft) / 2, top - 36), tag,
               font=ft, fill=col)

    # -- bottom: kill-rate bars, one per mutant (1 = killed by a gate)
    y1 = 690
    d.rectangle([x0, y1, x0 + w, y1 + 520], fill=PANEL, outline=(70, 78, 90))
    d.text((x0 + 24, y1 + 16),
           f'self-test: {selftest["mutants_killed"]}/{selftest["mutants_total"]} '
           f'mutants killed by a named gate '
           f'(kill rate {selftest["kill_rate"]}; determinism '
           f'{"OK" if selftest["determinism_ok"] else "FAIL"})',
           font=font("bold", 36), fill=INK)
    muts = selftest["mutants"]
    bw = (w - 220) / max(1, len(muts))
    for i, m in enumerate(muts):
        X = x0 + 150 + i * bw
        col = PASS if m["verdict"] == "KILLED" else FAILC
        d.rectangle([X, y1 + 100, X + bw - 22, y1 + 400], fill=col)
        # the mutant name wraps on underscores and is centred inside its
        # column, shrinking to fit rather than overflowing its neighbour
        fl = font("mono", 22)
        words = m["name"].split("_")
        lines, cur = [], ""
        for w_ in words:
            trial = (cur + "_" + w_) if cur else w_
            if d.textlength(trial, font=fl) <= bw - 28 or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w_
        if cur:
            lines.append(cur)
        ty = y1 + 410
        for ln in lines:
            d.text((X + (bw - 22 - d.textlength(ln, font=fl)) / 2, ty),
                   ln, font=fl, fill=INK)
            ty += fl.size + 6
        d.text((X + 6, y1 + 100 - 34), m["gates_failed"].split(",")[0],
               font=font("monobold", 24), fill=MUTED)

    d.text((60, PH - 58),
           "iterations: judge/grade.sh on each single-edit artifact "
           "(media/figures.py)  |  kill matrix: judge/selftest.sh --json "
           "media/build/selftest.json",
           font=font("mono", 27), fill=MUTED)

    img.save(os.path.join(HERE, "loop.png"), dpi=(DPI, DPI))
    with open(os.path.join(BUILD, "loop_history.json"), "w") as fh:
        json.dump(history, fh, indent=2)


if __name__ == "__main__":
    build_result()
    build_loop()
    print("[figures] wrote result.png and loop.png")
