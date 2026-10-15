#!/usr/bin/env python3
"""Media for the solidcraft-cad demo, from real tool output only.

  make_media.py data     SolidCraft renders + judge verdicts -> media/data/
  make_media.py figures  media/result.png, media/loop.png
  make_media.py frames   1920x1080 PNG frames into $FRAMES_DIR
  make_media.py manifest media/MANIFEST.json

Run by media/make_media.sh with the judge venv's python (pinned matplotlib).
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

MEDIA = Path(__file__).resolve().parent
DEMO = MEDIA.parent
DATA = MEDIA / "data"
RENDERS = DATA / "renders"
GOOD = DEMO / "examples/good/design.json"
CLI = Path.home() / ".local/solidcraft-0.10.1-linux-x86_64/bin/solidcraft-cli"

# Okabe-Ito (colour-blind safe)
OK, BAD, INK, MUTED, ACCENT = "#009E73", "#D55E00", "#222222", "#888888", "#0072B2"

STAGES = [  # (prefix length of the good script, caption)
    (10, "1  sketch: rounded rectangle R5, bore, 4 bolt holes on the PCD"),
    (11, "2  solid.extrude distance = thickness"),
    (15, "3  boss sketch on a plane offset by thickness"),
    (16, "4  solid.extrude boss_height, join"),
]
SWEEP = [6.0, 6.5, 7.0, 7.5, 8.0]
REPLAY = [  # scripted repair replay: draft with three mistakes, fixed one per step
    ("draft", ["boss_height", "hole_off_pcd", "literal_thickness"]),
    ("fix boss height", ["hole_off_pcd", "literal_thickness"]),
    ("move hole onto PCD", ["literal_thickness"]),
    ("use the thickness\nparameter", []),
]
FLOOR = 1e-12  # ratios below this are drawn at the floor (exact to float precision)
GATES = ["build", "occt_shape", "volume", "features", "mass", "cross_check", "parametric", "stl"]


def load_mutants():
    spec = importlib.util.spec_from_file_location("mutants", DEMO / "judge/mutants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def snapshot(script: Path, out: Path, view="iso", w=1200, h=900):
    p = run([str(CLI), "snapshot", str(script), "--out", str(out), "--width", str(w),
             "--height", str(h), "--view", view])
    if p.returncode != 0:
        sys.exit(f"media: snapshot failed for {script}: {p.stderr[-500:]}")


def grade(script: Path, out: Path) -> dict:
    run(["bash", str(DEMO / "judge/grade.sh"), str(script), "--json", str(out)])
    v = json.loads(out.read_text())
    v.pop("timing", None)
    return v


def cmd_data(work: Path):
    RENDERS.mkdir(parents=True, exist_ok=True)
    good = json.loads(GOOD.read_text())
    mut = load_mutants()

    for n, _ in STAGES:
        s = work / f"stage{n}.json"
        s.write_text(json.dumps({"commands": good["commands"][:n]}))
        snapshot(s, RENDERS / f"stage{n}.png")
    for view in ("iso", "top", "front"):
        snapshot(GOOD, RENDERS / f"final_{view}.png", view)

    sweep = []
    for t in SWEEP:
        d = copy.deepcopy(good)
        for c in d["commands"]:
            if c["command"] == "parameters.change" and c["params"]["name"] == "thickness":
                c["params"]["expression"] = f"{t} mm"
        s = work / f"sweep{t}.json"
        s.write_text(json.dumps(d))
        snapshot(s, RENDERS / f"sweep_{t}.png", "front")
        ev = json.loads(run([str(CLI), "eval", str(s)]).stdout)
        sweep.append({"thickness_mm": t, "solidcraft_volume_mm3": ev["bodies"][0]["volume_mm3"],
                      "render": f"renders/sweep_{t}.png"})
    print("media: renders + parametric sweep done")

    verdicts = {"good": grade(GOOD, work / "good.json")}
    csg = json.loads((DEMO / "examples/good/design-csg.json").read_text())
    for base, fn in [(good, f) for f in mut.MUTANTS] + [(csg, f) for f in mut.CSG_MUTANTS]:
        d = copy.deepcopy(base)
        fn(d["commands"])
        s = work / f"m_{fn.__name__}.json"
        s.write_text(json.dumps(d))
        verdicts[fn.__name__] = grade(s, work / f"v_{fn.__name__}.json")
    print(f"media: good + {len(verdicts) - 1} mutants graded")

    replay = []
    for label, bugs in REPLAY:
        d = copy.deepcopy(good)
        for b in bugs:
            getattr(mut, b)(d["commands"])
        s = work / f"replay{len(replay)}.json"
        s.write_text(json.dumps(d))
        v = grade(s, work / f"r{len(replay)}.json")
        replay.append({"step": label, "mistakes_left": bugs, "passed": v["passed"],
                       "gates": {g: v["gates"].get(g, {}).get("pass") for g in GATES}})
    print("media: repair replay graded")

    (DATA / "verdicts.json").write_text(json.dumps(verdicts, indent=1, sort_keys=True) + "\n")
    (DATA / "sweep.json").write_text(json.dumps(sweep, indent=1) + "\n")
    (DATA / "replay.json").write_text(json.dumps(replay, indent=1) + "\n")


# ------------------------------------------------------------------ figures --

def checks(g: dict) -> list[tuple[str, float, float]]:
    """(label, measured deviation, limit) for every numeric pass rule."""
    G = g["gates"]
    f = G["features"]
    return [
        ("volume vs analytic", G["volume"]["rel_dev"], G["volume"]["limit_rel"]),
        ("bounding box (mm)", G["occt_shape"]["bbox_max_dev_mm"], G["occt_shape"]["limit_mm"]),
        ("bolt hole Ø (mm)", f["bolt_diameter_max_dev_mm"], 0.02),
        ("on pitch circle (mm)", f["pcd_max_dev_mm"], 0.05),
        ("hole spacing (deg)", f["spacing_max_dev_deg"], 0.1),
        ("mass (g)", G["mass"]["mass_g"], G["mass"]["limit_g"]),
        ("kernels: volume", G["cross_check"]["volume_rel_dev"], G["cross_check"]["limit_rel"]),
        ("kernels: area", G["cross_check"]["area_rel_dev"], G["cross_check"]["limit_rel"]),
        ("kernels: centre of mass (mm)", G["cross_check"]["com_max_dev_mm"], G["cross_check"]["limit_com_mm"]),
        ("parametric ΔV (+2 mm)", G["parametric"]["rel_dev"], G["parametric"]["limit_rel"]),
        ("STL vs STEP volume", G["stl"]["rel_dev_vs_step"], G["stl"]["limit_rel"]),
    ]


def draw_result(fig, v: dict):
    import matplotlib.image as mpimg
    ax_img = fig.add_axes([0.0, 0.08, 0.46, 0.80])
    ax_img.imshow(mpimg.imread(RENDERS / "final_iso.png"))
    ax_img.axis("off")
    ax_img.set_title("Part built by SolidCraft 0.10.1 (solidcraft-cli snapshot)", fontsize=12)

    ax = fig.add_axes([0.62, 0.12, 0.35, 0.74])
    rows = checks(v)
    ratios = [max(m / lim, FLOOR) for _, m, lim in rows]
    y = range(len(rows))[::-1]
    ax.barh(list(y), ratios, color=[OK if r <= 1 else BAD for r in ratios], height=0.6)
    ax.axvline(1.0, color=BAD, lw=2, ls="--")
    ax.text(0.7, len(rows) - 0.4, "pass line", color=BAD, fontsize=10, va="top", ha="right")
    ax.set_xscale("log")
    ax.set_xlim(FLOOR / 10, 30)
    ax.set_yticks(list(y))
    ax.set_yticklabels([r[0] for r in rows], fontsize=10)
    ax.set_xlabel("measured deviation / pass limit (log scale; < 1 passes)", fontsize=10)
    ax.set_title("Judge gates on the delivered STEP/STL (OpenCascade 8.0.1)", fontsize=12)
    for yi, r in zip(y, ratios):
        ax.text(min(r * 1.6, 3), yi, "≤ 1e-12 (exact)" if r <= FLOOR else f"{r:.1e}",
                va="center", fontsize=8, color=INK)
    ok = v["passed"]
    fig.suptitle(f"solidcraft-cad — verdict: {'PASS' if ok else 'FAIL'}  "
                 f"(OCCT volume {v['gates']['volume']['occt_mm3']} mm³ vs analytic "
                 f"{v['gates']['volume']['analytic_mm3']} mm³, mass {v['gates']['mass']['mass_g']} g)",
                 fontsize=14, color=OK if ok else BAD)


def draw_loop(fig, verdicts: dict, replay: list):
    ax = fig.add_axes([0.07, 0.15, 0.38, 0.68])
    n = [sum(1 for g in GATES if r["gates"].get(g)) for r in replay]
    ax.plot(range(len(n)), n, "-o", color=ACCENT, lw=2, ms=9)
    ax.axhline(len(GATES), color=OK, ls="--", lw=2)
    ax.text(0, len(GATES) + 0.15, f"pass: all {len(GATES)} gates", color=OK, fontsize=10)
    for i, r in enumerate(replay):
        failed = [g for g in GATES if r["gates"].get(g) is False]
        ax.annotate("fails:\n" + "\n".join(failed) if failed else "PASS", (i, n[i]),
                    textcoords="offset points", xytext=(0, -14), ha="center", va="top",
                    fontsize=9, color=BAD if failed else OK)
    ax.set_xticks(range(len(replay)))
    ax.set_xticklabels([r["step"] for r in replay], fontsize=9)
    ax.set_xlim(-0.5, len(replay) - 0.5)
    ax.set_ylim(0, len(GATES) + 1)
    ax.set_ylabel("judge gates passed (of 8)")
    ax.set_title("Repair replay: a draft with 3 mistakes, fixed one per grade\n"
                 "(scripted replay graded by the real judge, not a recorded agent run)", fontsize=11)

    ax2 = fig.add_axes([0.60, 0.15, 0.37, 0.68])
    names = ["good"] + [k for k in verdicts if k != "good"]
    yy = range(len(names))[::-1]
    colors = [OK if verdicts[k]["passed"] else BAD for k in names]
    ax2.barh(list(yy), [1] * len(names), color=colors, height=0.65)
    for yi, k in zip(yy, names):
        v = verdicts[k]
        ax2.text(0.02, yi, f"{k}: " + ("passes all gates" if v["passed"] else f"killed at {v['failed_gate']}"),
                 va="center", fontsize=9, color="white")
    killed = sum(1 for k in names[1:] if not verdicts[k]["passed"])
    ax2.set_yticks([])
    ax2.set_xticks([])
    ax2.set_title(f"Self-test: {killed}/{len(names) - 1} single-edit mutants killed "
                  f"({killed / (len(names) - 1):.0%}, need ≥ 90 %)\nfirst failing gate shown", fontsize=11)
    fig.suptitle("solidcraft-cad — agent loop and judge power", fontsize=14)


def cmd_figures():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    verdicts = json.loads((DATA / "verdicts.json").read_text())
    replay = json.loads((DATA / "replay.json").read_text())
    fig = plt.figure(figsize=(14, 6.5))
    draw_result(fig, verdicts["good"])
    fig.savefig(MEDIA / "result.png", dpi=200)
    plt.close(fig)
    fig = plt.figure(figsize=(14, 6.5))
    draw_loop(fig, verdicts, replay)
    fig.savefig(MEDIA / "loop.png", dpi=200)
    plt.close(fig)
    print("media: result.png, loop.png")


# ------------------------------------------------------------------- video --

def cmd_frames():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    out = Path(os.environ["FRAMES_DIR"])
    verdicts = json.loads((DATA / "verdicts.json").read_text())
    replay = json.loads((DATA / "replay.json").read_text())
    sweep = json.loads((DATA / "sweep.json").read_text())
    spec = json.loads((DEMO / "spec.json").read_text())
    good = verdicts["good"]
    k = 0

    def emit(fig, seconds: float):
        nonlocal k
        fig.savefig(out / "tmp.png", dpi=100)
        plt.close(fig)
        data = (out / "tmp.png").read_bytes()
        for _ in range(int(seconds * 30)):
            (out / f"frame{k:05d}.png").write_bytes(data)
            k += 1

    def canvas(title: str, sub: str = ""):
        fig = plt.figure(figsize=(19.2, 10.8))
        fig.text(0.04, 0.93, title, fontsize=30, weight="bold", color=INK)
        if sub:
            fig.text(0.04, 0.885, sub, fontsize=17, color=MUTED)
        return fig

    def image(fig, path, rect, crop=None):
        img = mpimg.imread(path)
        if crop:  # (top, bottom, left, right) as fractions of the render
            h, w = img.shape[:2]
            img = img[int(crop[0] * h):int(crop[1] * h), int(crop[2] * w):int(crop[3] * w)]
        ax = fig.add_axes(rect)
        ax.imshow(img)
        ax.axis("off")

    fig = canvas("Agent-built CAD part: PASS, 8/8 gates",
                 "SolidCraft built it in a sandbox; OpenCascade re-measured the delivered STEP")
    image(fig, RENDERS / "final_iso.png", [0.18, 0.0, 0.64, 0.86])
    emit(fig, 2.5)

    fig = canvas("Parametric CAD in a disposable sandbox",
                 "An agent writes a SolidCraft script; OpenCascade re-measures what SolidCraft delivers")
    p = spec
    lines = [f"Part: {p['part']}",
             f"Plate {p['plate']['length']:g} × {p['plate']['width']:g} × thickness {p['plate']['thickness']:g} mm, corners R{p['plate']['corner_radius']:g}",
             f"Bore Ø{p['bore']['diameter']:g}, boss Ø{p['boss']['outer_diameter']:g} × {p['boss']['height']:g} mm",
             f"{p['bolt_holes']['count']} × Ø{p['bolt_holes']['diameter']:g} holes on PCD {p['bolt_holes']['pitch_circle_diameter']:.4f} mm",
             f"6061 aluminium, mass ≤ {p['mass_limit_g']:g} g; must rebuild when thickness changes",
             "", "Artifact: design.json (SolidCraft commands)   Judge: 8 numeric gates"]
    for i, ln in enumerate(lines):
        fig.text(0.06, 0.72 - i * 0.065, ln, fontsize=24, color=INK)
    emit(fig, 4)

    for n, cap in STAGES:
        fig = canvas("SolidCraft builds the design script", cap)
        image(fig, RENDERS / f"stage{n}.png", [0.2, 0.02, 0.6, 0.84])
        emit(fig, 2)

    fig = canvas("Delivered part", "solidcraft-cli snapshot: iso, top and front views")
    for i, v in enumerate(("iso", "top", "front")):
        image(fig, RENDERS / f"final_{v}.png", [0.01 + i * 0.33, 0.12, 0.32, 0.7])
    emit(fig, 4)

    vol0 = sweep[0]["solidcraft_volume_mm3"]
    for s in sweep:
        fig = canvas("Parametric: change thickness, the whole part rebuilds",
                     "front view; volume reported by solidcraft-cli eval for each value")
        # the front view leaves the part small in the middle; crop to it (same crop every frame)
        image(fig, RENDERS / f"sweep_{s['thickness_mm']}.png", [0.02, 0.1, 0.62, 0.7], crop=(0.38, 0.62, 0.12, 0.88))
        fig.text(0.67, 0.6, f"thickness = {s['thickness_mm']:.1f} mm", fontsize=34, color=ACCENT, weight="bold")
        fig.text(0.67, 0.5, f"V = {s['solidcraft_volume_mm3']:.1f} mm³", fontsize=28, color=INK)
        fig.text(0.67, 0.43, f"ΔV = {s['solidcraft_volume_mm3'] - vol0:+.1f} mm³", fontsize=28, color=INK)
        emit(fig, 1.6)
    pg = good["gates"]["parametric"]
    fig = canvas("Judge's parametric gate", "thickness 6 → 8 mm, re-measured in OpenCascade")
    for i, ln in enumerate([f"OCCT ΔV = {pg['volume_delta_mm3']} mm³",
                            f"analytic ΔV = A_net × 2 mm = {pg['analytic_delta_mm3']} mm³",
                            f"relative deviation {pg['rel_dev']:.1e}  (limit {pg['limit_rel']})",
                            f"top face z = {pg['top_z_mm']} mm (expected {pg['expected_top_z_mm']})"]):
        fig.text(0.08, 0.68 - i * 0.1, ln, fontsize=30, color=INK)
    emit(fig, 4)

    rows = checks(good)
    for upto in (4, 8, len(rows)):
        fig = canvas("Judge verdict on the delivered STEP / STL",
                     "OpenCascade 8.0.1 measurements vs analytic values from spec.json")
        for i, (lab, m, lim) in enumerate(rows[:upto]):
            okr = m <= lim
            fig.text(0.07, 0.8 - i * 0.065, ("PASS  " if okr else "FAIL  ") + lab, fontsize=24,
                     color=OK if okr else BAD, weight="bold")
            fig.text(0.55, 0.8 - i * 0.065, f"{m:.3g}  (limit {lim:g})", fontsize=24, color=INK)
        emit(fig, 2.2)

    for name, secs in (("loop.png", 6), ("result.png", 4)):  # the published figures, full frame
        fig = plt.figure(figsize=(19.2, 10.8))
        image(fig, MEDIA / name, [0.0, 0.05, 1.0, 0.9])
        emit(fig, secs)
    fig = canvas("Run it yourself", "one command: creates a sandbox, installs the tools, grades, kills the sandbox")
    fig.text(0.06, 0.6, "python3 cookbook/solidcraft-cad/run.py", fontsize=40, family="monospace", color=ACCENT)
    fig.text(0.06, 0.45, "github.com/agent-next/sandbox", fontsize=30, color=INK)
    emit(fig, 3)
    (out / "tmp.png").unlink()
    print(f"media: {k} frames ({k / 30:.1f} s)")


def cmd_manifest():
    ff = run(["ffmpeg", "-version"]).stdout.split("\n")[0]
    import matplotlib
    files = {
        "result.png": ("Delivered part (SolidCraft render) + every judge pass rule as measured/limit, pass line at 1",
                       "bash media/make_media.sh (make_media.py figures)", "data/verdicts.json"),
        "loop.png": ("Scripted repair replay (3 mistakes fixed one per grade) + self-test kill rate over 12 mutants",
                     "bash media/make_media.sh (make_media.py figures)", "data/replay.json, data/verdicts.json"),
        "demo.mp4": ("Spec -> SolidCraft build stages -> delivered views -> parametric sweep -> judge verdict -> loop",
                     "bash media/make_media.sh (make_media.py frames + ffmpeg crf 0 master -> crf 18 web)",
                     "data/*.json, data/renders/*.png"),
    }
    m = {"tools": {"solidcraft": "0.10.1", "matplotlib": matplotlib.__version__, "ffmpeg": ff},
         "files": {k: {"shows": a, "command": b, "source": c,
                       "sha256": hashlib.sha256((MEDIA / k).read_bytes()).hexdigest()}
                   for k, (a, b, c) in files.items()}}
    m["files"]["data/renders"] = {"shows": "SolidCraft snapshot PNGs used by the figures and video",
                                  "command": "solidcraft-cli snapshot <script> --view iso|top|front",
                                  "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                             for p in sorted(RENDERS.glob("*.png"))}}
    (MEDIA / "MANIFEST.json").write_text(json.dumps(m, indent=1) + "\n")
    print("media: MANIFEST.json")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "data":
        cmd_data(Path(sys.argv[2]))
    else:
        {"figures": cmd_figures, "frames": cmd_frames, "manifest": cmd_manifest}[cmd]()
