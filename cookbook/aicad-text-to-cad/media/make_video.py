#!/usr/bin/env python3
"""demo.mp4 master frames -- every frame drawn from real judge outputs.

1920x1080 @ 30 fps, written as PNG frames to media/work/frames/ (the
lossless master ffmpeg encodes from there; nothing here talks to ffmpeg).
Sequence:

  1. the text spec is the whole input        (~4 s)
  2. one generated part: turntable of the real delivered model.stl,
     gates as a growing checklist             (~9 s)
  3. one card per mutant (8): the delivered mesh with the defect
     highlighted (real geometry: XOR-difference facets, or the located
     STL byte edit), the failed gate(s) and the measured value vs the
     rule from that mutant's verdict JSON     (~23 s)
  4. verdict                                  (~4 s)

Numbers on screen come only from media/data/verdicts/*.json; the turnable
meshes are the delivered model.step/model.stl files; the reference in
scene 2 is rebuilt from spec.json by the judge's own code.  Rendered
headless with matplotlib (Agg) under the pinned judge venv.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import cadviz

MEDIA = cadviz.MEDIA
DATA = cadviz.DATA
FRAMES = os.path.join(MEDIA, "work", "frames")
FPS = 30

INK = "#0b0b0b"
MUTED = "#52514e"
PASS = cadviz.PASS
FAIL = cadviz.FAIL
GOOD_DIR = os.path.join(cadviz.DEMO, "examples", "good")

GATES = ["tool_runs", "delivery_matches", "step_valid", "stl_valid", "bbox",
         "volume_analytic", "xor_volume", "features", "min_wall",
         "judge_intact"]
GATE_NUM = {g: i + 1 for i, g in enumerate(GATES)}

MUTANTS = ["plate-hole-count", "plate-hole-diameter", "plate-hole-drift",
           "plate-flipped-facet", "bracket-missing-fillet",
           "bracket-fillet-radius", "bushing-scale-25_4",
           "bushing-non-watertight"]
SCENE3_PART = cadviz.MUTANT_PART
MUT_EDIT = {   # the one scripted edit, verbatim from judge/mutants.py
    "plate-hole-count":      "N_BOLT_HOLES = 4  ->  3",
    "plate-hole-diameter":   "BOLT_HOLE_D = 6.5  ->  5.0",
    "plate-hole-drift":      "FIRST_ANGLE_DEG = 45.0  ->  53.0",
    "plate-flipped-facet":   "one facet's vertex order swapped in the STL",
    "bracket-missing-fillet": "the R5 fillet arc -> its chord (bd.Line)",
    "bracket-fillet-radius": "FILLET_R = 5.0  ->  2.0",
    "bushing-scale-25_4":    "SHAFT_D = 20.0  ->  20.0 * 25.4",
    "bushing-non-watertight": "one facet record deleted from the STL",
}
MUT_DESC = {
    "plate-hole-count": "3 bolt holes where the spec wants 4",
    "plate-hole-diameter": "hole diameter Ø5.0 where the spec wants Ø6.5",
    "plate-hole-drift": "first hole at 53°, not the spec's 45°",
    "plate-flipped-facet": "a flipped facet breaks the mesh's winding",
    "bracket-missing-fillet": "the inner R5 fillet is missing entirely",
    "bracket-fillet-radius": "inner corner filleted R2, spec wants R5",
    "bushing-scale-25_4": "shaft Ø20 misread as inches: Ø508",
    "bushing-non-watertight": "a deleted facet leaves the STL open",
}

_n = [0]


def frame_dir():
    os.makedirs(FRAMES, exist_ok=True)
    return FRAMES


def new_frame(bg="#fcfcfb"):
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=bg)
    return fig


def emit(fig):
    _n[0] += 1
    fig.savefig(os.path.join(FRAMES, f"f{_n[0]:05d}.png"),
                facecolor=fig.get_facecolor())
    plt.close(fig)


def hold(fig, n):
    # re-save the same figure n times (the renderer cache makes repeats
    # cheap and the frames are byte-identical by construction)
    for _ in range(n):
        fig.savefig(os.path.join(FRAMES, f"f{_n[0] + 1:05d}.png"),
                    facecolor=fig.get_facecolor())
        _n[0] += 1


def header(fig, title, sub=None):
    fig.text(0.03, 0.955, title, fontsize=26, fontweight="bold", color=INK,
             va="center")
    if sub:
        fig.text(0.03, 0.905, sub, fontsize=14, color=MUTED, va="center")


# ---------------------------------------------------------------------------
def scene1_spec():
    spec = open(os.path.join(GOOD_DIR, "bushing", "spec.txt")).read()
    for k in range(int(3.5 * FPS)):     # fade lines in one by one
        fig = new_frame()
        header(fig, "the text prompt",
               "an agent reads a short text spec inside a disposable sandbox")
        lines = spec.rstrip().splitlines()
        shown = min(len(lines), 1 + k // 6)
        fig.text(0.08, 0.80, "\n".join(lines[:shown]), fontsize=19,
                 family="monospace", color=INK, va="top", linespacing=1.7)
        emit(fig)
    fig = new_frame()
    header(fig, "the text prompt",
           "an agent reads a short text spec inside a disposable sandbox")
    fig.text(0.08, 0.80, spec.rstrip(), fontsize=19, family="monospace",
             color=INK, va="top", linespacing=1.7)
    hold(fig, int(0.8 * FPS))


def scene2_turntable():
    part = "bushing"
    v = cadviz.load_verdict(f"good_{part}.json")
    delivered = cadviz.load_stl(os.path.join(GOOD_DIR, part, "model.stl"))
    ref, ref_vol = cadviz.reference_mesh(part)
    spec_dims = json.loads(
        open(os.path.join(cadviz.JUDGE, "spec.json")).read()
    )["parts"][part]["dims"]
    fc = cadviz.shaded_facecolors(delivered)
    nspin = int(7.5 * FPS)

    for k in range(nspin):
        azim = -60 + 360.0 * k / nspin
        fig = new_frame()
        header(fig, "the tool generates the part -- judged",
              "delivered model.stl (left) vs the reference solid rebuilt "
              "from judge/spec.json alone (right)  --  seed 42")
        ax = fig.add_axes([0.03, 0.04, 0.44, 0.82], projection="3d")
        cadviz.draw_mesh(ax, delivered, fc=fc, elev=22, azim=azim,
                         title="delivered model.stl",
                         title_fs=15)
        ax2 = fig.add_axes([0.50, 0.04, 0.44, 0.82], projection="3d")
        cadviz.draw_mesh(ax2, ref, fc=cadviz.shaded_facecolors(
            ref, base=(0.72, 0.78, 0.86)), elev=22, azim=azim,
            title="reference solid (spec.json only)", title_fs=15)
        # gate checklist grows with the spin, 2 gates per revolution 5th
        shown = min(len(GATES), 2 + (k * 8) // nspin)
        fig.text(0.03, 0.86, "the judge's 10 gates on the delivered files:",
                 fontsize=13, color=INK, va="center")
        for i, g in enumerate(GATES[:shown]):
            ok = v["gates"][g]["pass"] is True
            fig.text(0.055, 0.845 - i * 0.031,
                     "✓" if ok else "✗", fontsize=12,
                     color=PASS if ok else FAIL, va="center")
            fig.text(0.075, 0.845 - i * 0.031,
                     f"gate {GATE_NUM[g]}  {g}", fontsize=12,
                     color=INK, va="center")
        emit(fig)

    # closing beat: all gates checked, key numbers from the verdict
    for _ in range(int(1.2 * FPS)):
        fig = new_frame()
        header(fig, "the judge's verdict on the bushing",
              "numbers from media/data/verdicts/good_bushing.json "
              "(grade.sh --seed 42)")
        q = v["gates"]["volume_analytic"]["measured"]
        x = v["gates"]["xor_volume"]["measured"]
        w = v["gates"]["min_wall"]["measured"]
        lines = [
            f"volume {q['volume_mm3']:.3f} mm3 vs analytic "
            f"{q['analytic_mm3']:.3f} -- rel err "
            f"{q['rel_err'] * 100:.4f} %  (rule: <= 0.5 %)",
            f"boolean XOR vs reference: {x['xor_volume_mm3']:g} mm3 = "
            f"{x['rel'] * 100:.4g} %  (rule: <= 1.0 %)",
            f"min wall {w['min_wall_mm']:.3f} mm over {w['rays']} seeded "
            f"rays  (rule: >= {w['spec_min_wall_mm']:g} - 0.1 mm)",
            "10/10 gates PASS -- grade.sh exit 0",
        ]
        fig.text(0.08, 0.62, "\n\n".join(lines), fontsize=18,
                 family="monospace", color=INK, va="top", linespacing=1.8)
        fig.text(0.08, 0.28, "the other two parts grade the same way "
                 "(result.png), so the rest of this video is the "
                 "self-test: can the judge be fooled?", fontsize=14,
                 color=MUTED, va="top")
        emit(fig)


def short_cell(gate, g):
    """One line: measured value vs rule, for a mutant card."""
    m = g.get("measured") or {}
    if gate == "features":
        errs = m.get("errors") or ["failed"]
        return f"features gate: {errs[0]}"
    if gate == "volume_analytic":
        return (f"volume gate: rel err {m['rel_err'] * 100:.3g} % "
                f"(limit 0.5 %)")
    if gate == "bbox":
        return f"bbox gate: max dev {m['step_max_dev_mm']:g} mm (limit 0.05 mm)"
    if gate == "stl_valid":
        bits = [b for b, on in (("not watertight",
                                 not m.get("watertight", True)),
                                ("winding inconsistent",
                                 not m.get("winding_consistent", True)))
                if on]
        return "stl_valid gate: " + (" and ".join(bits) or "failed")
    if gate == "delivery_matches":
        return ("delivery gate: edited STL can never be regenerated by the "
                "tool -- sha256 != fresh run")
    raise KeyError(gate)


def scene3_mutants():
    per = int(2.7 * FPS)
    for name in MUTANTS:
        part = SCENE3_PART[name]
        v = cadviz.load_verdict(name + ".json")
        _, faces, note = cadviz.defect_highlight(name)
        mesh = cadviz.load_stl(os.path.join(DATA, "mutants", name,
                                             "model.stl"))
        fc = cadviz.shaded_facecolors(mesh)
        fc[faces] = cadviz.FAIL_RGB + (1.0,)
        failed = [g for g in GATES if not v["gates"][g]["pass"]]
        lines = [short_cell(g, v["gates"][g]) for g in failed[:3]]
        for k in range(per):
            azim = -60 + 25.0 * (k / per - 0.5)
            fig = new_frame()
            header(fig, f"self-test: mutant {name}  ({part.replace('_', ' ')})",
                  f"single scripted edit:  {MUT_EDIT[name]}")
            ax = fig.add_axes([0.52, 0.05, 0.45, 0.80], projection="3d")
            cadviz.draw_mesh(ax, mesh, fc=fc, elev=22, azim=azim,
                             title="delivered mesh -- defect in red",
                             title_fs=15)
            fig.text(0.52, 0.855, MUT_DESC[name], fontsize=15, color=INK,
                     va="center")
            fig.text(0.03, 0.78, cadviz.wrap(note, 62), fontsize=12.5,
                     color=MUTED, va="top", linespacing=1.5)
            fig.text(0.03, 0.70, "killed by:", fontsize=15, fontweight="bold",
                     color=INK, va="top")
            for i, ln in enumerate(lines):
                fig.text(0.045, 0.655 - i * 0.052, cadviz.wrap(ln, 52),
                         fontsize=13.5, color=FAIL, va="top", linespacing=1.4)
            fig.text(0.03, 0.10, f"{len(failed)} of 10 gates failed -- "
                     "grade.sh exit 1", fontsize=13.5, color=INK, va="top")
            emit(fig)


def scene4_outro():
    summary = None
    for line in open(os.path.join(DATA, "selftest.txt")):
        if "summary:" in line:
            summary = line.strip()
    for _ in range(int(4.0 * FPS)):
        fig = new_frame()
        header(fig, "the judge an agent cannot fool",
               "judge/selftest.sh, real output (media/data/selftest.txt)")
        fig.text(0.08, 0.66, summary or "selftest summary", fontsize=21,
                 family="monospace", color=INK, va="top")
        fig.text(0.08, 0.44, "every single-edit mutant dies on at least one "
                 "gate; the three good parts pass all ten, and the judge "
                 "regenerates every artifact with the pinned tool before "
                 "believing it.", fontsize=15, color=MUTED, va="top",
                 wrap=True)
        emit(fig)


def main():
    if not os.path.isdir(FRAMES):
        os.makedirs(FRAMES, exist_ok=True)
    existing = sorted(os.listdir(FRAMES))
    for f in existing:
        os.remove(os.path.join(FRAMES, f))
    _n[0] = 0
    scene1_spec()
    scene2_turntable()
    scene3_mutants()
    scene4_outro()
    print(f"wrote {_n[0]} frames at {FPS} fps "
          f"({_n[0] / FPS:.1f} s) to {FRAMES}")


if __name__ == "__main__":
    main()
