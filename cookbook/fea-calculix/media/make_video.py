#!/usr/bin/env python3
"""demo.mp4 -- the real CalculiX deformation, then the mutants' failures.

Scene 1  title card
Scene 2  good artifact: the real fine-mesh .frd displacement field ramped
         0 -> full load.  Linear static: the displacement/stress field is
         scaled linearly and that is printed on every frame.
Scene 3  hold at full load + gate readouts from the verdict JSON
Scene 4  the 9 mutants' failures: one card each, straight from its real
         verdict JSON (failed gate + measured vs limit); 4 cards embed the
         mutant's own real deformed field (its own ccx run)
Scene 5  closing card: kill rate, verdict, provenance

Frames -> ffmpeg concat -> lossless master (crf 0) in media/master/ ->
web encode (crf 18, preset slow, yuv420p, +faststart) -> media/demo.mp4.
Fails if any source file is missing, if the video is outside 20-60 s,
or above 8 MB.
"""
import json
import os
import subprocess
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib import cm, colors

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import beamviz

MEDIA = os.path.dirname(os.path.abspath(__file__))
VERDICTS = os.path.join(MEDIA, "data", "verdicts")
FRAMES = os.path.join(MEDIA, "frames")
MASTER = os.path.join(MEDIA, "master")
OUT = os.path.join(MEDIA, "demo.mp4")

W, H, FPS = 1920, 1080, 30
CMAP = "viridis"
ALLOW = 250.0 / 1.5
ELEV, AZIM = 14, 75

MUTANTS = [
    ("no-stress-output", "deck drops *EL FILE S -- judge cannot read "
     "stress", None),
    ("coarse-mesh", "mesh_size = min(b,h): fewer than 2 elements across "
     "the width", None),
    ("load-wrong-dof", "tip load applied in +Y instead of -Z", None),
    ("load-on-ntip", "-250 N on every tip-face node, not the 4 corners",
     "load-on-ntip"),
    ("propped-tip", "tip clamped as well (propped cantilever)",
     "propped-tip"),
    ("units-in-metres", "design dimensions written in metres", None),
    ("overload-10x", "-2500 N per corner node = 10x the spec load",
     "overload-10x"),
    ("undersized", "b=8, h=40 mm -- too weak for the spec", "undersized"),
    ("unconverged", "b=30, h=60, mesh_size=15 -- meshes disagree", None),
]


def need(p):
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run solve_fields.py / the "
                         "verdict collection first")
    return p


def verdict(name):
    return json.load(open(need(os.path.join(VERDICTS, name + ".json"))))


def new_frame():
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    return fig


def save(fig, name):
    p = os.path.join(FRAMES, name)
    fig.savefig(p)
    plt.close(fig)
    return p


def draw_beam(ax, fields, lam, scale, vmax, colorbar=False, cb_label=True):
    """Draw the beam at load factor lam.  Returns the PolyCollection."""
    coords, disp, vm, conn = (fields["coords"], fields["disp"],
                              fields["vm"], fields["conn"])
    faces = beamviz.boundary_faces(conn)
    fxyz = (coords + scale * lam * disp)[faces]
    verts, order = beamviz.face_draw_order(fxyz, ELEV, AZIM)
    fvm = np.nan_to_num(lam * vm[faces].mean(axis=1), nan=0.0)[order]
    norm = colors.Normalize(0.0, vmax)
    coll = PolyCollection(verts, array=fvm, cmap=CMAP, norm=norm,
                          edgecolors="none", antialiased=False)
    ax.add_collection(coll)
    ax.set_aspect("equal")
    pad = 0.04 * coords[:, 0].max()
    ax.set_xlim(verts[..., 0].min() - pad, verts[..., 0].max() + pad)
    ax.set_ylim(verts[..., 1].min() - 2.5 * pad,
                verts[..., 1].max() + 2.5 * pad)
    ax.axis("off")
    cb = None
    if colorbar:
        cb = ax.figure.colorbar(cm.ScalarMappable(norm=norm, cmap=CMAP),
                                ax=ax, fraction=0.03, pad=0.02,
                                extend="max")
        cb.ax.axhline(ALLOW, color="red", lw=2.0)
        if cb_label:
            cb.set_label(f"von Mises [MPa]  (red = {ALLOW:.0f})",
                         fontsize=10)
        cb.ax.tick_params(labelsize=9)
    return coll


def scene_title():
    fig = new_frame()
    fig.text(0.5, 0.62, "fea-calculix", ha="center", fontsize=44,
             fontweight="bold")
    fig.text(0.5, 0.52, "sizing a steel cantilever with CalculiX "
             "inside a disposable sandbox", ha="center", fontsize=20)
    fig.text(0.5, 0.40,
             "fixed spec: P = 1000 N tip load | E = 200 GPa | "
             "allowable 250/1.5 = 166.7 MPa | delta <= L/100",
             ha="center", fontsize=15, color="0.25")
    fig.text(0.5, 0.30,
             "judge: gmsh mesh -> ccx solve -> Euler-Bernoulli oracle, "
             "mesh convergence, spec mask\n"
             "everything below is real solver/judge output "
             "(ccx 2.20, gmsh 4.10.0)",
             ha="center", fontsize=13, color="0.35")
    return save(fig, "title.png")


def scene_ramp(fields, good_v):
    """Render the 0->full-load ramp frames; returns list of paths."""
    m = good_v["metrics"]
    scale = 20.0                             # same amplification as result.png
    paths = []
    n = int(7.0 * FPS)
    fig = new_frame()
    ax = fig.add_axes([0.03, 0.16, 0.70, 0.70])
    coll = draw_beam(ax, fields, 1.0, scale, 1.15 * ALLOW, colorbar=True)
    faces = beamviz.boundary_faces(fields["conn"])
    lam_t = fig.text(0.03, 0.955, "", fontsize=15, va="top",
                     fontweight="bold")
    info_t = fig.text(0.03, 0.10, "", fontsize=12, va="bottom",
                      family="monospace",
                      bbox=dict(boxstyle="round,pad=0.4", fc="white",
                                ec="0.6"))
    note_t = fig.text(0.97, 0.955, "", fontsize=11, va="top", ha="right",
                      color="0.35")
    note_t.set_text("linear static: displacement field scaled x%.1f\n"
                    "stress shown = load factor x full-load .frd field"
                    % scale)
    for i in range(n):
        lam = i / (n - 1)
        fxyz = (fields["coords"] + scale * lam * fields["disp"])[faces]
        verts, order = beamviz.face_draw_order(fxyz, ELEV, AZIM)
        fvm = np.nan_to_num(
            lam * fields["vm"][faces].mean(axis=1), nan=0.0)[order]
        coll.set_verts(verts)
        coll.set_array(fvm)
        lam_t.set_text("good artifact -- load ramp 0 -> 1000 N   "
                       f"load factor {lam:.2f}")
        info_t.set_text(
            f"tip deflection {lam * m['delta_mm']:6.2f} mm "
            f"(limit 10.00)   "
            f"wall stress {lam * m['sigma_mpa']:6.1f} MPa "
            f"(allowable {ALLOW:.1f})")
        p = os.path.join(FRAMES, f"ramp_{i:04d}.png")
        fig.savefig(p)
        paths.append(p)
    plt.close(fig)
    return paths, scale


def scene_hold(fields, good_v, scale):
    fig = new_frame()
    m = good_v["metrics"]
    ax = fig.add_axes([0.03, 0.10, 0.66, 0.76])
    draw_beam(ax, fields, 1.0, scale, 1.15 * ALLOW, colorbar=True)
    fig.text(0.03, 0.955, "good artifact -- full load, verdict PASS",
             fontsize=16, va="top", fontweight="bold",
             color="#1a7a2f")
    g = good_v["gates"]
    txt = [
        f"verification: {g['verification']['detail']}",
        f"convergence:  {g['convergence']['detail']}",
        f"spec_limits:  {g['spec_limits']['detail']}",
        f"mass: {m['mass_g']:.0f} g",
    ]
    fig.text(0.745, 0.80, "\n\n".join(textwrap.wrap(
        "\n\n".join(txt), 46)), fontsize=11, va="top", family="monospace",
        bbox=dict(boxstyle="round,pad=0.6", fc="#f4f9f4", ec="#1a7a2f"))
    fig.text(0.03, 0.045, "real job.frd, fine mesh "
             f"({m['fine_elems']} elements); displacement scaled "
             f"x{scale:.1f}", fontsize=10, color="0.35")
    return save(fig, "hold.png")


def scene_mutant(name, edit, field_case):
    """One mutant failure card, straight from its verdict JSON."""
    v = verdict(name)
    fig = new_frame()
    fig.text(0.04, 0.90, f"mutant: {name}", fontsize=24,
             fontweight="bold", va="top")
    fig.text(0.04, 0.83, edit, fontsize=14, va="top", color="0.3")
    fig.text(0.87, 0.90, "FAIL", fontsize=30, fontweight="bold",
             color="#b71c1c", va="top", ha="left")
    y = 0.74
    for g in ("verification", "convergence", "spec_limits"):
        gate = v["gates"][g]
        mark = "PASS" if gate["pass"] else "FAIL"
        col = "#1a7a2f" if gate["pass"] else "#b71c1c"
        fig.text(0.04, y, f"{mark}", fontsize=12, fontweight="bold",
                 color=col, va="top")
        fig.text(0.10, y, f"{g}:", fontsize=12, va="top",
                 fontweight="bold", family="monospace")
        fig.text(0.26, y, textwrap.fill(gate["detail"], 60),
                 fontsize=10.5, va="top", family="monospace",
                 color="0.15")
        n_lines = len(textwrap.wrap(gate["detail"], 60))
        y -= 0.045 + 0.030 * n_lines
    if field_case:
        # the mutant's own real field, drawn straight onto the card at
        # ~56% of the card width (>= half), bottom right
        fields = beamviz.load_fields(field_case)
        s = json.load(open(need(os.path.join(
            MEDIA, "work", field_case, "summary.json"))))
        maxu = float(np.abs(fields["disp"]).max())
        scale = 0.0 if maxu == 0 else 0.16 * s["L_mm"] / maxu
        vmax = max(1.15 * ALLOW, float(np.nanmax(fields["vm"])))
        axf = fig.add_axes([0.42, 0.04, 0.56, 0.34])
        draw_beam(axf, fields, 1.0, scale, vmax, colorbar=True,
                  cb_label=False)
        axf.set_title(
            ("mutant's own ccx run (fine mesh) -- real deformed field, "
             f"displacements x{scale:.1f}") if scale > 0 else
            "mutant's own ccx run (fine mesh) -- field identically zero "
            "(clamped tip carries the load)",
            fontsize=10, color="0.35", loc="left")
    fig.text(0.04, 0.05, "verdict JSON: media/data/verdicts/"
             f"{name}.json (grade.sh --seed 42)", fontsize=9.5,
             color="0.45")
    return save(fig, f"card_{name}.png")


def scene_close(good_v, n_mut):
    fig = new_frame()
    fig.text(0.5, 0.68, "judge self-test: 9/9 mutants killed (100%)",
             ha="center", fontsize=26, color="#b71c1c")
    m = good_v["metrics"]
    fig.text(0.5, 0.55,
             "known-good: PASS   |   sigma_wall "
             f"{m['sigma_mpa']:.1f} <= 166.7 MPa   |   "
             f"delta {m['delta_mm']:.2f} <= 10.00 mm   |   "
             f"mass {m['mass_g']:.0f} g",
             ha="center", fontsize=16)
    fig.text(0.5, 0.42,
             "determinism: two --seed 42 grades byte-identical "
             "(excl. timing)\n"
             "mutant sequence shown as a replay of real grade JSONs",
             ha="center", fontsize=13, color="0.35")
    fig.text(0.5, 0.28, "cookbook/fea-calculix -- README.md / SPEC.md / "
             "RECEIPT.md", ha="center", fontsize=12, color="0.45")
    return save(fig, "close.png")


def main():
    os.makedirs(FRAMES, exist_ok=True)
    os.makedirs(MASTER, exist_ok=True)
    good_v = verdict("good")
    fields = beamviz.load_fields("good-fine")

    concat = []          # (path, duration_s)
    t = scene_title();            concat += [(t, 2.5)]
    ramp_paths, scale = scene_ramp(fields, good_v)
    concat += [(p, 1.0 / FPS) for p in ramp_paths]
    t = scene_hold(fields, good_v, scale);  concat += [(t, 3.5)]

    for name, edit, field_case in MUTANTS:
        t = scene_mutant(name, edit, field_case)
        concat += [(t, 2.0)]
    t = scene_close(good_v, len(MUTANTS));  concat += [(t, 2.5)]

    lst = os.path.join(FRAMES, "frames.txt")
    with open(lst, "w") as f:
        for p, d in concat:
            f.write(f"file '{os.path.abspath(p)}'\nduration {d:.5f}\n")
        f.write(f"file '{os.path.abspath(concat[-1][0])}'\n")

    master = os.path.join(MASTER, "demo_lossless.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-vf", f"fps={FPS}", "-c:v", "libx264",
                    "-crf", "0", "-preset", "slow", "-pix_fmt", "yuv420p",
                    master], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-i", master, "-c:v", "libx264",
                    "-crf", "18", "-preset", "slow", "-pix_fmt",
                    "yuv420p", "-movflags", "+faststart", OUT],
                   check=True, capture_output=True)

    size = os.path.getsize(OUT)
    pr = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                         "format=duration", "-show_entries",
                         "stream=width,height,r_frame_rate",
                         "-of", "json", OUT],
                        capture_output=True, text=True, check=True)
    meta = json.loads(pr.stdout)
    dur = float(meta["format"]["duration"])
    st = meta["streams"][0]
    print(f"{OUT}: {dur:.1f} s, {st['width']}x{st['height']} @ "
          f"{st['r_frame_rate']}, {size/1e6:.2f} MB "
          f"(master {os.path.getsize(master)/1e6:.1f} MB)")
    assert 20.0 <= dur <= 60.0, f"duration {dur} outside 20-60 s"
    assert size < 8e6, f"demo.mp4 {size} bytes > 8 MB"
    assert (st["width"], st["height"]) == (1920, 1080)


if __name__ == "__main__":
    main()
