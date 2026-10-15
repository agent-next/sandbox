#!/usr/bin/env python3
"""Build media/loop.png from real judge verdict JSONs.

Reads media/data/loop/*.json: good.json (known-good artifact) plus one verdict
per single-edit mutant (written by judge/grade.sh --json during a selftest
run, seed 42). Draws the artifact x gate matrix (green pass / red fail), the
measured-vs-limit numbers of the known-good run, and the mutant kill rate.
Nothing is invented: every cell is a gate result from a verdict file.

Run:  python3 media/make_loop.py
"""

import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP_DIR = os.path.join(HERE, "data", "loop")
OUT = os.path.join(HERE, "loop.png")

W, H = 2400, 1350
BG = "#101418"
PANEL = "#161b22"
INK = "#f0efec"
MUTED = "#9aa2ad"
FAINT = "#2a313c"
GOOD = "#45d052"
GOOD_BG = "#12351a"
BAD = "#ff5f56"
BAD_BG = "#3a1215"
ACCENT = "#3987e5"

FONT_DIR = "/usr/share/fonts/truetype/dejavu"

GATE_LIMITS = {  # measured vs limit, from the known-good verdict metrics
    "slice_clean": "orca rc=0",
    "artifact_matches": "hash == re-slice",
    "moves_inside_bed": "8007 in 250x210 bed",
    "moves_near_part": "2.39 mm <= 10 mm",
    "layer_z_sequence": "first Z 0.2 in 0.10-0.30, h 0.2 <= 0.32",
    "volume_matches_model": "3344 mm3 in 2381-5279, 4.15 g <= 12 g",
    "cube_crosscheck": "4858 mm3 in 3871-8046",
    "pla_temperatures": "nozzle 210 in 180-230, bed 60 in 35-70",
    "time_estimate": "1738 s vs 1855 s (+-25%), <= 5400 s",
    "klipper_batch": "rc=0, 0 error lines",
    "profile_contract": "walls 2 >= 2, infill 15 in 10-40%",
    "judge_intact": "sha256 unchanged",
}


def font(size, bold=False):
    f = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(os.path.join(FONT_DIR, f), size)


def load_verdicts():
    good = json.load(open(os.path.join(LOOP_DIR, "good.json")))
    muts = {}
    for fn in sorted(os.listdir(LOOP_DIR)):
        if fn.endswith(".json") and fn != "good.json":
            muts[fn[:-5]] = json.load(open(os.path.join(LOOP_DIR, fn)))
    return good, muts


def main():
    good, muts = load_verdicts()
    gate_names = list(good["gates"].keys())

    killed = [n for n, v in muts.items() if v["verdict"] != "PASS"]
    total = len(muts)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, H), fill=PANEL)
    d.rectangle((0, 0, W, H), outline=FAINT, width=2)

    pad = 60
    x, y = pad, 40
    d.text((x, y), "cookbook/3dprint-gcode", font=font(26, True), fill=ACCENT)
    y += 42
    d.text((x, y), "Self-test: the judge can fail", font=font(52, True), fill=INK)
    d.text((x + 760, y + 8),
           "known-good + %d single-edit mutants x 12 gates" % total,
           font=font(28), fill=MUTED)

    # kill-rate badge
    kbw, kbh = 560, 74
    d.rounded_rectangle((W - pad - kbw, 48, W - pad, 48 + kbh), radius=14,
                        fill=GOOD_BG, outline=GOOD, width=3)
    d.text((W - pad - kbw + 26, 66),
           "KILL RATE %d/%d (%d%%)" % (len(killed), total, 100 * len(killed) // total),
           font=font(34, True), fill=GOOD)

    y += 92

    # ---- matrix -----------------------------------------------------------
    label_w = 470
    grid_x = x + label_w
    grid_w = W - pad - grid_x
    col_w = grid_w / len(gate_names)
    head_h, row_h = 78, 52

    # column headers (wrapped gate names)
    f_head = font(19, True)
    for i, g in enumerate(gate_names):
        cx = grid_x + i * col_w
        words = g.split("_")
        lines, cur = [], ""
        for wd in words:
            t = (cur + "_" + wd) if cur else wd
            if d.textlength(t, font=f_head) <= col_w - 14:
                cur = t
            else:
                lines.append(cur)
                cur = wd
        lines.append(cur)
        for j, ln in enumerate(lines):
            d.text((cx + col_w / 2 - d.textlength(ln, font=f_head) / 2,
                    y + 8 + j * 22), ln, font=f_head, fill=MUTED)
    y += head_h

    f_lab, f_lab_b = font(22), font(22, True)
    rows = [("known-good", good, True)] + [(n, v, False) for n, v in sorted(muts.items())]
    for name, v, is_good in rows:
        verdict = v["verdict"]
        if is_good:
            d.rounded_rectangle((x, y + 3, x + label_w - 18, y + row_h - 3),
                                radius=8, fill=GOOD_BG)
            d.text((x + 16, y + 12), name, font=f_lab_b, fill=GOOD)
            d.text((x + 250, y + 12), "PASS", font=f_lab_b, fill=GOOD)
        else:
            d.text((x + 16, y + 12), name, font=f_lab, fill=INK)
            vy = y + 12
            d.text((x + 330, vy), verdict, font=f_lab_b,
                   fill=GOOD if verdict == "PASS" else BAD)
        for i, g in enumerate(gate_names):
            cx = grid_x + i * col_w
            ok = v["gates"][g]["pass"]
            fill = GOOD_BG if ok else BAD_BG
            col = GOOD if ok else BAD
            d.rounded_rectangle((cx + 5, y + 4, cx + col_w - 5, y + row_h - 4),
                                radius=8, fill=fill)
            mark = "✓" if ok else "✗"
            f_mark = font(26, True)
            d.text((cx + col_w / 2 - d.textlength(mark, font=f_mark) / 2,
                    y + 9), mark, font=f_mark, fill=col)
        y += row_h

    y += 6
    d.text((x, y), "green = gate passed, red = gate failed  (seed 42, one edit per mutant)",
           font=font(21), fill=MUTED)
    y += 46

    # ---- measured vs limit, known-good run --------------------------------
    d.text((x, y), "measured vs limit - known-good run", font=font(28, True), fill=INK)
    y += 48
    cards_across, card_h = 3, 64
    card_w = (W - 2 * pad - (cards_across - 1) * 24) / cards_across
    f_card_t, f_card_v = font(20, True), font(21)
    for i, g in enumerate(gate_names):
        cx = x + (i % cards_across) * (card_w + 24)
        cy = y + (i // cards_across) * (card_h + 14)
        d.rounded_rectangle((cx, cy, cx + card_w, cy + card_h), radius=10,
                            fill="#1b212b")
        d.text((cx + 18, cy + 8), g, font=f_card_t, fill=ACCENT)
        d.text((cx + 18, cy + 32), GATE_LIMITS[g], font=f_card_v, fill=MUTED)
    y += ((len(gate_names) + cards_across - 1) // cards_across) * (card_h + 14) + 24

    d.line((x, y, W - pad, y), fill=FAINT, width=2)
    y += 16
    d.text((x, y), "verdicts from judge/selftest.sh (judge/grade.sh --json, seed 42) - "
           "each mutant fails its SPEC-declared gate%s" % ("" if total == len(killed) else ""),
           font=font(22), fill=MUTED)

    img.save(OUT, optimize=True)
    print("wrote", OUT, img.size,
          "kill %d/%d" % (len(killed), total))


if __name__ == "__main__":
    main()
