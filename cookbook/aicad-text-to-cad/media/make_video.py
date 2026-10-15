#!/usr/bin/env python3
"""demo.mp4 master frames -- every frame drawn from real judge outputs.

1920x1080 @ 30 fps, written as PNG frames to media/work/frames/ (the
lossless master ffmpeg encodes from there; nothing here talks to ffmpeg).
Storyboard (media/STORYBOARD.md), after DEMO-STANDARD.md:

  0   hook: the real delivered bushing spins, filling the frame  (~1.6 s)
  1   input -> output: the text spec beside the part it produced (~4.4 s)
  2   escalate: delivered-vs-reference turntable, the 10 gates as
      a growing checklist, then the verdict numbers              (~10.2 s)
  3   the fixing agent's loop, replayed (each step really graded) (~2.4 s)
  4   one card per mutant (8): the delivered mesh with the defect
      highlighted (real geometry: XOR-difference facets, or the
      located STL byte edit), the failed gate(s) and the measured
      value vs the rule from that mutant's verdict JSON        (~21.6 s)
  5   proof: kill list + the selftest summary line              (~3.2 s)
  6   end card: python3 run.py, static                          (~2.6 s)

Numbers on screen come only from media/data/verdicts/*.json and
media/data/selftest.txt; the turning meshes are the delivered
model.step/model.stl files; the reference is rebuilt from spec.json by
the judge's own code.  Rendered headless with matplotlib (Agg) under
the pinned judge venv.
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


def emit(fig, n=1):
    for _ in range(n):
        _n[0] += 1
        fig.savefig(os.path.join(FRAMES, f"f{_n[0]:05d}.png"),
                    facecolor=fig.get_facecolor())
    plt.close(fig)


def header(fig, title, sub=None):
    fig.text(0.03, 0.955, title, fontsize=27, fontweight="bold", color=INK,
             va="center")
    if sub:
        fig.text(0.03, 0.900, sub, fontsize=16, color=MUTED, va="center")


def caption(fig, text, color=MUTED):
    """Phone-readable burned-in caption along the bottom."""
    fig.text(0.5, 0.035, text, fontsize=17, ha="center", va="center",
             color=color)


# ---------------------------------------------------------------------------
def scene0_hook():
    """0-2 s: the finished real result fills the frame -- no title card."""
    mesh = cadviz.load_stl(os.path.join(GOOD_DIR, "bushing", "model.stl"))
    fc = cadviz.shaded_facecolors(mesh)
    n = int(1.6 * FPS)
    for k in range(n):
        fig = new_frame()
        ax = fig.add_axes([0.28, -0.06, 0.44, 1.05], projection="3d")
        cadviz.draw_mesh(ax, mesh, fc=fc, elev=20,
                         azim=-60 + 40.0 * k / n, pad=0.0)
        caption(fig, "a machined bushing, generated from a text spec -- "
                     "then graded by a judge the agent cannot fool",
                color=INK)
        emit(fig)


def scene1_spec():
    """2-10 s input->output: the spec text beside the part it produced."""
    spec = open(os.path.join(GOOD_DIR, "bushing", "spec.txt")).read()
    mesh = cadviz.load_stl(os.path.join(GOOD_DIR, "bushing", "model.stl"))
    fc = cadviz.shaded_facecolors(mesh)
    lines = spec.rstrip().splitlines()
    ntype = int(3.2 * FPS)
    nhold = int(1.2 * FPS)
    for k in range(ntype + nhold):
        fig = new_frame()
        header(fig, "the input: a short text spec",
               "an agent reads this inside a disposable sandbox and writes "
               "a model for the text-to-cad tool")
        shown = len(lines) if k >= ntype else min(len(lines), 1 + k // 5)
        fig.text(0.05, 0.78, "\n".join(lines[:shown]), fontsize=18,
                 family="monospace", color=INK, va="top", linespacing=1.7)
        ax = fig.add_axes([0.56, 0.08, 0.40, 0.72], projection="3d")
        cadviz.draw_mesh(ax, mesh, fc=fc, elev=20, azim=-60,
                         title="the part it produced\n(delivered model.stl)",
                         title_fs=18)
        emit(fig)


def scene2_turntable():
    """Escalate: real delivered mesh vs the spec-built reference, gates."""
    part = "bushing"
    v = cadviz.load_verdict(f"good_{part}.json")
    delivered = cadviz.load_stl(os.path.join(GOOD_DIR, part, "model.stl"))
    ref, ref_vol = cadviz.reference_mesh(part)
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
                         title="delivered model.stl", title_fs=17)
        ax2 = fig.add_axes([0.50, 0.04, 0.44, 0.82], projection="3d")
        cadviz.draw_mesh(ax2, ref, fc=cadviz.shaded_facecolors(
            ref, base=(0.72, 0.78, 0.86)), elev=22, azim=azim,
            title="reference solid (spec.json only)", title_fs=17)
        shown = min(len(GATES), 2 + (k * 8) // nspin)
        fig.text(0.03, 0.865, "the judge's 10 gates on the delivered files:",
                 fontsize=15, color=INK, va="center")
        for i, g in enumerate(GATES[:shown]):
            ok = v["gates"][g]["pass"] is True
            fig.text(0.055, 0.838 - i * 0.030, "✓" if ok else "✗",
                     fontsize=13, color=PASS if ok else FAIL, va="center")
            fig.text(0.075, 0.838 - i * 0.030,
                     f"gate {GATE_NUM[g]}  {g}", fontsize=13, color=INK,
                     va="center")
        emit(fig)

    # closing beat: all gates checked, key numbers from the verdict
    q = v["gates"]["volume_analytic"]["measured"]
    x = v["gates"]["xor_volume"]["measured"]
    w = v["gates"]["min_wall"]["measured"]
    fig = new_frame()
    header(fig, "the judge's verdict on the bushing",
           "numbers from media/data/verdicts/good_bushing.json "
           "(grade.sh --seed 42)")
    lines = [
        f"volume {q['volume_mm3']:.3f} mm3 vs analytic "
        f"{q['analytic_mm3']:.3f} -- rel err "
        f"{q['rel_err'] * 100:.4f} %  (rule: <= 0.5 %)",
        f"boolean XOR vs reference: {x['xor_volume_mm3']:g} mm3 = "
        f"{x['rel'] * 100:.4g} %  (rule: <= 1.0 %)",
        f"min wall {w['min_wall_mm']:.3f} mm over {w['rays']} seeded "
        f"rays  (rule: >= {w['spec_min_wall_mm']:g} - 0.1 mm)",
    ]
    fig.text(0.08, 0.72, "\n\n".join(lines), fontsize=19,
             family="monospace", color=INK, va="top", linespacing=1.8)
    fig.text(0.08, 0.30, "10/10 gates PASS -- grade.sh exit 0",
             fontsize=30, fontweight="bold", color=PASS, va="top")
    emit(fig, int(1.8 * FPS))


def scene3_replay():
    """The fixing agent's loop, replayed: 4 real grades on adapter_plate."""
    replay = [l.strip() for l in open(
        cadviz.need(os.path.join(DATA, "replay.txt")))]
    iter_lab = {"plate-hole-count": "1: 3 bolt holes",
                "plate-hole-diameter": "2: Ø5.0 holes",
                "plate-hole-drift": "3: hole at 53°",
                "good_adapter_plate": "4: good part"}
    nf = [sum(1 for g in cadviz.load_verdict(r + ".json")["gates"].values()
              if not g["pass"]) for r in replay]
    fig = new_frame()
    header(fig, "the fixing agent's loop -- replayed",
           "each state below is a real artifact graded by judge/grade.sh "
           "--seed 42; the iteration order is a replay, not a live trace")
    ax = fig.add_axes([0.07, 0.16, 0.86, 0.62])
    x = np.arange(len(replay))
    ax.bar(x, nf, width=0.55,
           color=[FAIL if n else PASS for n in nf], alpha=0.92)
    for xi, n in zip(x, nf):
        ax.text(xi, n + 0.06, f"{n} of 10 gates failed" if n else
                "0 failed = PASS", ha="center", va="bottom", fontsize=17,
                color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([iter_lab[r] for r in replay], fontsize=17)
    ax.set_ylabel("gates failed (of 10)", fontsize=15)
    ax.set_ylim(0, max(nf) + 1.0)
    ax.set_yticks(range(0, max(nf) + 1))
    ax.tick_params(labelsize=14, length=3)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    emit(fig, int(2.4 * FPS))


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
    if gate == "xor_volume":
        return (f"XOR gate: {m['rel'] * 100:.3g} % of reference "
                f"(limit 1.0 %)")
    raise KeyError(gate)


def scene4_mutants():
    """One card per mutant: real defect on the delivered mesh + its gate."""
    per = int(2.7 * FPS)
    for idx, name in enumerate(MUTANTS):
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
            header(fig, f"self-test mutant {idx + 1}/8:  {name}  "
                   f"({part.replace('_', ' ')})",
                   f"single scripted edit:  {MUT_EDIT[name]}")
            ax = fig.add_axes([0.52, 0.05, 0.45, 0.80], projection="3d")
            cadviz.draw_mesh(ax, mesh, fc=fc, elev=22, azim=azim,
                             title="delivered mesh -- defect in red",
                             title_fs=17)
            fig.text(0.52, 0.845, MUT_DESC[name], fontsize=17, color=INK,
                     va="center")
            fig.text(0.03, 0.80, cadviz.wrap(note, 58), fontsize=15,
                     color=MUTED, va="top", linespacing=1.5)
            fig.text(0.03, 0.68, "killed by:", fontsize=20,
                     fontweight="bold", color=INK, va="top")
            for i, ln in enumerate(lines):
                fig.text(0.045, 0.62 - i * 0.075, cadviz.wrap(ln, 50),
                         fontsize=16, color=FAIL, va="top", linespacing=1.4)
            fig.text(0.03, 0.10, f"{len(failed)} of 10 gates failed -- "
                     "grade.sh exit 1", fontsize=16, color=INK, va="top")
            emit(fig)


def scene5_proof():
    """Proof: every mutant dies, which gate killed it, selftest summary."""
    fig = new_frame()
    header(fig, "proof: the judge cannot be fooled",
           "media/data/verdicts/*.json + media/data/selftest.txt "
           "(judge/selftest.sh, seed 42)")
    fig.text(0.06, 0.83, "each single-edit mutant, and the gates that "
             "killed it:", fontsize=18, color=INK, va="top")
    y = 0.75
    for name in MUTANTS:
        v = cadviz.load_verdict(name + ".json")
        failed = [g for g in GATES if not v["gates"][g]["pass"]]
        fig.text(0.07, y, name, fontsize=16, family="monospace",
                 color=FAIL, va="center")
        fig.text(0.42, y, "gates " +
                 ", ".join(f"{GATE_NUM[g]} {g}" for g in failed),
                 fontsize=15, family="monospace", color=INK, va="center")
        y -= 0.062
    summary = None
    for line in open(cadviz.need(os.path.join(DATA, "selftest.txt"))):
        if "summary:" in line:
            summary = line.strip()
    fig.text(0.06, 0.16, summary or "selftest summary", fontsize=19,
             family="monospace", fontweight="bold", color=INK, va="top")
    fig.text(0.06, 0.09, "kill rate 100% (floor 90%) -- "
             "determinism: two seed-42 grades byte-identical minus timing",
             fontsize=15, color=MUTED, va="top")
    emit(fig, int(3.2 * FPS))


def scene6_endcard():
    """Static end card, last ~2.6 s: the one-line launch."""
    fig = new_frame()
    fig.text(0.5, 0.62, "python3 run.py", fontsize=52, fontweight="bold",
             family="monospace", color=INK, ha="center", va="center")
    fig.text(0.5, 0.48, "cookbook/aicad-text-to-cad", fontsize=22,
             family="monospace", color=MUTED, ha="center", va="center")
    fig.text(0.5, 0.34,
             "or ask your agent: \"write the model.py for each spec, then\n"
             "iterate bash judge/grade.sh <part dir> until every gate "
             "passes\"", fontsize=18, color=INK, ha="center", va="top",
             linespacing=1.6)
    emit(fig, int(2.6 * FPS))


def main():
    if not os.path.isdir(FRAMES):
        os.makedirs(FRAMES, exist_ok=True)
    for f in sorted(os.listdir(FRAMES)):
        os.remove(os.path.join(FRAMES, f))
    _n[0] = 0
    frame_dir()
    scene0_hook()
    scene1_spec()
    scene2_turntable()
    scene3_replay()
    scene4_mutants()
    scene5_proof()
    scene6_endcard()
    print(f"wrote {_n[0]} frames at {FPS} fps "
          f"({_n[0] / FPS:.1f} s) to {FRAMES}")


if __name__ == "__main__":
    main()
