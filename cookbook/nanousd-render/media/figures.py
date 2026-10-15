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

    # -- left panel: the graded render with the pass line on it
    # Left margin leaves room for the y-axis tick labels (measured: a 3-digit
    # mono-30 label is ~60 px wide, and the gridline carriage is 26 px).
    px, py, pad = 150, 150, 20
    rw = 1490
    rh = int(rw * render.size[1] / render.size[0])       # 4:3 -> 1118
    big = render.resize((rw, rh), Image.LANCZOS)
    img.paste(big, (px + pad, py + pad))
    d.rectangle([px, py, px + pad * 2 + rw, py + pad * 2 + rh],
                outline=(70, 78, 90), width=2)

    # oracle rectangles (the pass line), scaled from the 640x480 grade frame
    s = rw / 640.0
    f_lab = font("bold", 38)
    render_right = px + pad + rw
    for i, (path, m) in enumerate(sorted(g4.items())):
        col = rgb(OI[i % len(OI)])
        x0, y0, x1, y1 = m["rect"]
        box = [px + pad + x0 * s, py + pad + y0 * s,
               px + pad + x1 * s, py + pad + y1 * s]
        for off in (-4, 4):
            d.rectangle([box[0] + off, box[1] + off, box[2] - off, box[3] - off],
                        outline=col, width=5)
        name = path.rsplit("/", 1)[-1]
        # the label must stay inside the render panel: a mesh flush against
        # the right frame edge (the Tetra sits at x=640) must not spill its
        # label under the verdict panel beside it
        tw = d.textlength(f"{name}  k={m['illuminance_k']:.2f}", font=f_lab)
        lx = min(box[0] + 10, render_right - tw - 8)
        ly = max(py + pad, box[1] - 58)
        d.text((lx, ly), f"{name}  k={m['illuminance_k']:.2f}", font=f_lab,
               fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))

    # axes around the render (the oracle's pixel space), with units
    fa = font("mono", 28)
    for xv in range(0, 641, 160):
        X = px + pad + xv * s
        d.line([X, py + pad + rh + 10, X, py + pad + rh + 26], fill=(120, 128, 140), width=2)
        d.text((X - 24, py + pad + rh + 32), f"{xv}", font=fa, fill=MUTED)
    d.text((px + pad + rw // 2 - 160, py + pad + rh + 76),
           "projected pixel x (px, 640-wide grade frame)", font=fa, fill=MUTED)
    for yv in range(0, 481, 120):
        Y = py + pad + yv * (rh / 480.0)
        d.line([px + pad - 26, Y, px + pad - 10, Y], fill=(120, 128, 140), width=2)
        d.text((px + pad - 96, Y - 16), f"{yv}", font=fa, fill=MUTED)
    # rotated y-axis caption ("projected pixel y"), rendered on its own
    # image so it can be rotated 90 degrees beside the axis
    ylab = "projected pixel y (px)"
    lb = font("mono", 28).getbbox(ylab)
    lw, lh = lb[2] - lb[0], lb[3] - lb[1]
    li = Image.new("RGBA", (lw + 40, lh + 20), (0, 0, 0, 0))
    ImageDraw.Draw(li).text((20 - lb[0], 10 - lb[1]), ylab, font=font("mono", 28),
                            fill=(*MUTED, 255))
    li = li.rotate(90, expand=True)
    img.paste(li, (px - 40 - li.size[0], py + pad + rh // 2 - li.size[1] // 2),
              li)

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
        extra = f"  r_frac {info['rendered_frac']}" \
            if "rendered_frac" in info else ""
        d.text((qx + 30, y), f"{g}: {str(info['pass']).lower()}{extra}",
               font=font("mono", 36), fill=PASS)
        y += 54
    y += 18
    d.text((qx + 30, y), "G4 oracle per mesh", font=font("bold", 38), fill=INK)
    y += 56
    # legend: authored colour chip + measured k and deviation
    # The verdict panel is ~614 px wide; three fixed columns at mono-34
    # collide (a 10-char name already reaches the k column), so use mono-28
    # and stack name/k/dev on one line within the panel width.
    fleg = font("mono", 28)
    for i, (path, m) in enumerate(sorted(g4.items())):
        col = rgb(OI[i % len(OI)])
        d.rectangle([qx + 30, y + 6, qx + 62, y + 38], fill=col)
        name = path.rsplit("/", 1)[-1]
        d.text((qx + 76, y), name, font=fleg, fill=INK)
        tw = d.textlength(name, font=fleg)
        d.text((qx + 76 + tw + 18, y), f"k={m['illuminance_k']:.3f}",
               font=fleg, fill=INK)
        d.text((qx + 76 + 330, y), f"dev={m['own_dev']:.3f}",
               font=fleg, fill=INK)
        y += 44
    y += 14
    d.text((qx + 30, y), f"judge_integrity_ok: "
                         f"{str(verdict['judge_integrity_ok']).lower()}",
           font=font("mono", 34), fill=INK)

    # -- title + provenance footer (footer is two lines so neither clips
    # at the 2400 px frame edge -- review finding: the single-line footer
    # overflowed the right edge)
    d.text((80, 44), "nanousd-render - two USD implementations agree, "
                     "and a CPU render proves it",
           font=font("bold", 54), fill=INK)
    d.text((80, PH - 100),
           "judge/grade.sh examples/good/scene.usda --seed 0 "
           "--json media/build/verdict.json",
           font=font("mono", 27), fill=MUTED)
    d.text((80, PH - 62),
           "render: pinned nanousd OpenGL ES renderer on llvmpipe   |   "
           "rectangles: G4 numpy pinhole oracle",
           font=font("mono", 27), fill=MUTED)

    img.save(os.path.join(HERE, "result.png"), dpi=(DPI, DPI))


# -------------------------------------------------------------------- loop

def edit(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit(f"iteration edit '{what}': pattern found "
                         f"{text.count(old)} times, expected 1")
    return text.replace(old, new, 1)


# Iterations of the agent loop: real single-edit artifacts, graded for
# real. Each edit is one regression against the current known-good scene
# (patterns are validated against the committed example, so a changed
# layout fails the build instead of silently no-op'ing the loop): three
# failing iterations, then the graded scene. Every bar is a real
# `grade.sh` run's verdict.
def iteration_files(outdir):
    good = open(GOOD, encoding="utf-8").read()
    its = [
        ("no light", edit(good,
                          '    def DistantLight "Sun"\n    {\n        float inputs:intensity = 1\n'
                          '        float3 xformOp:rotateXYZ = (-45, 30, 0)\n'
                          '        uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]\n    }\n', "",
                          "no light")),
        ("camera off", edit(good, "float3 xformOp:rotateXYZ = (-18, 0, 0)",
                            "float3 xformOp:rotateXYZ = (85, 0, 0)",
                            "camera off")),
        ("meshes overlap", edit(good, "float3 xformOp:translate = (-2.44, 0.4, 0)",
                                "float3 xformOp:translate = (-1.5, 0.4, 0)",
                                "meshes overlap")),
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

    d.text((60, 40), "The agent loop - grade verdicts per iteration, and "
                     "the self-test kill rate",
           font=font("bold", 52), fill=INK)

    # -- top: gates passed (of 4) per iteration
    x0, y0, w, h = 90, 190, 2220, 420
    d.rectangle([x0, y0, x0 + w, y0 + h], fill=PANEL, outline=(70, 78, 90))
    d.text((x0 + 24, y0 + 18), "gates passed per iteration (1 = one grade run)",
           font=font("bold", 36), fill=INK)
    # plot area leaves an x gutter for the 0-4 y labels and a y gutter for
    # the per-iteration captions below the axis
    plot_x0, plot_x1 = x0 + 190, x0 + w - 40
    plot_y0, plot_y1 = y0 + 100, y0 + h - 90
    step = (plot_x1 - plot_x0) / max(1, len(history) - 1)
    for gy in range(5):
        Y = plot_y1 - gy * 62
        d.line([plot_x0, Y, plot_x1, Y], fill=(50, 56, 66), width=1)
        d.text((plot_x0 - 60 - len(str(gy)) * 10, Y - 18), str(gy),
               font=font("mono", 28), fill=MUTED)
    for i, it in enumerate(history):
        X = plot_x0 + i * step
        col = PASS if it["pass"] else FAILC
        top = plot_y1 - (4 - it["nfail"]) * 62
        d.rectangle([X - 52, top, X + 52, plot_y1], fill=col)
        label = f"it{i+1}: {it['name']}"
        lab_w = d.textlength(label, font=font("mono", 27))
        lx = min(max(X - lab_w / 2, plot_x0), plot_x1 - lab_w)
        d.text((lx, plot_y1 + 16), label, font=font("mono", 27), fill=INK)
        d.text((X - 52, top - 38), "PASS" if it["pass"] else it["failed"],
               font=font("monobold", 27), fill=col)

    # -- bottom: kill-rate bars, one per mutant (1 = killed by a gate)
    y1 = 680
    d.rectangle([x0, y1, x0 + w, y1 + 520], fill=PANEL, outline=(70, 78, 90))
    d.text((x0 + 24, y1 + 18),
           f'self-test: {selftest["mutants_killed"]}/{selftest["mutants_total"]} '
           f'mutants killed by a named gate '
           f'(kill rate {selftest["kill_rate"]}; determinism '
           f'{"OK" if selftest["determinism_ok"] else "FAIL"})',
           font=font("bold", 36), fill=INK)
    muts = selftest["mutants"]
    bw = (w - 200) / max(1, len(muts))
    for i, m in enumerate(muts):
        X = x0 + 140 + i * bw
        col = PASS if m["verdict"] == "KILLED" else FAILC
        d.rectangle([X, y1 + 100, X + bw - 18, y1 + 420], fill=col)
        d.text((X - 12, y1 + 436), m["name"].replace("_", "\n"),
               font=font("mono", 22), fill=INK, align="center")
        d.text((X - 12, y1 + 96 - 34), m["gates_failed"].split(",")[0],
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
