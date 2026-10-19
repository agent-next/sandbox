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
    px, py, pad = 60, 150, 20
    rw = 1520
    rh = int(rw * render.size[1] / render.size[0])       # 4:3 -> 1140
    big = render.resize((rw, rh), Image.LANCZOS)
    img.paste(big, (px + pad, py + pad))
    d.rectangle([px, py, px + pad * 2 + rw, py + pad * 2 + rh],
                outline=(70, 78, 90), width=2)

    # oracle rectangles (the pass line), scaled from the 640x480 grade frame
    f_lab = font("bold", 40)
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
        d.text((box[0] + 10, max(py + pad, box[1] - 58)),
               f"{name}  k={m['illuminance_k']:.2f}", font=f_lab,
               fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))

    # axes around the render (the oracle's pixel space), with units
    fa = font("mono", 30)
    for xv in range(0, 641, 160):
        X = px + pad + xv * s
        d.line([X, py + pad + rh + 10, X, py + pad + rh + 26], fill=(120, 128, 140), width=2)
        d.text((X - 24, py + pad + rh + 32), f"{xv}", font=fa, fill=MUTED)
    d.text((px + pad + rw // 2 - 150, py + pad + rh + 76),
           "projected pixel x (px, 640-wide grade frame)", font=fa, fill=MUTED)
    for yv in range(0, 481, 120):
        Y = py + pad + yv * (rh / 480.0)
        d.line([px + pad - 26, Y, px + pad - 10, Y], fill=(120, 128, 140), width=2)
        d.text((px + pad - 100, Y - 16), f"{yv}", font=fa, fill=MUTED)

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

    # -- title + provenance footer
    d.text((60, 44), "nanousd-render - two USD implementations agree, "
                     "and a CPU render proves it",
           font=font("bold", 54), fill=INK)
    d.text((60, PH - 64),
           "judge/grade.sh examples/good/scene.usda --seed 0 "
           "--json media/build/verdict.json  |  render: pinned "
           "nanousd OpenGL ES renderer on llvmpipe  |  rectangles: G4 "
           "numpy pinhole oracle",
           font=font("mono", 27), fill=MUTED)

    img.save(os.path.join(HERE, "result.png"), dpi=(DPI, DPI))


# -------------------------------------------------------------------- loop

def edit(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit(f"iteration edit '{what}': pattern found "
                         f"{text.count(old)} times, expected 1")
    return text.replace(old, new, 1)


# Iterations of the agent loop: real single-edit artifacts, graded for
# real. Each edit undoes one fix from the known-good scene, so the loop
# replays the authoring history backwards (error -> error -> error -> pass).
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
        ("overlapping", edit(good, "float3 xformOp:translate = (-4.2, 0.6, 0)",
                             "float3 xformOp:translate = (-2.3, 0.6, 0)",
                             "overlapping")),
        ("sub 12 points", edit(good, "float3 xformOp:translate = (4.2, 0.55, 0)",
                               "float3 xformOp:translate = (4.2, 0.55, 0)",
                               "noop")),
    ]
    # iteration 4 is the unmodified good scene (the pass)
    its[3] = ("graded scene", good)
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
    step = (w - 160) / max(1, len(history) - 1)
    base_y = y0 + h - 90
    for gy in range(5):
        Y = base_y - gy * 62
        d.line([x0 + 120, Y, x0 + w - 40, Y], fill=(50, 56, 66), width=1)
        d.text((x0 + 64, Y - 18), str(gy), font=font("mono", 28), fill=MUTED)
    for i, it in enumerate(history):
        X = x0 + 120 + i * step
        col = PASS if it["pass"] else FAILC
        top = base_y - (4 - it["nfail"]) * 62
        d.rectangle([X - 52, top, X + 52, base_y], fill=col)
        d.text((X - 120, base_y + 16), f"it{i+1}: {it['name']}",
               font=font("mono", 27), fill=INK)
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
