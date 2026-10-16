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

    # The independent agent's own 12 designs (REPRODUCE.md), re-graded with this judge,
    # next to the grades it recorded with the judge it had at the time.
    recorded = json.loads((DATA / "agent_run_recorded.json").read_text())["attempts"]
    agent = []
    for r in recorded:
        v = grade(DATA / "agent_attempts" / f"{r['attempt']}.json", work / f"a{r['attempt']}.json")
        agent.append({"attempt": r["attempt"], "recorded_gates": r["gates"],
                      "gates": {g: v["gates"].get(g, {}).get("pass") for g in GATES},
                      "failed_gate": v["failed_gate"]})
    print("media: independent agent's 12 designs re-graded")

    (DATA / "verdicts.json").write_text(json.dumps(verdicts, indent=1, sort_keys=True) + "\n")
    (DATA / "sweep.json").write_text(json.dumps(sweep, indent=1) + "\n")
    (DATA / "agent_run.json").write_text(json.dumps(agent, indent=1) + "\n")


# ------------------------------------------------------------------ figures --

def checks(g: dict) -> list[tuple[str, float, float]]:
    """(label, measured deviation, limit) for every numeric pass rule."""
    G = g["gates"]
    f = G["features"]
    return [  # label = "<gate>: <check>"; 8 gates, 12 numeric checks
        ("volume: vs analytic", G["volume"]["rel_dev"], G["volume"]["limit_rel"]),
        ("occt_shape: bounding box (mm)", G["occt_shape"]["bbox_max_dev_mm"], G["occt_shape"]["limit_mm"]),
        ("features: bolt hole Ø (mm)", f["bolt_diameter_max_dev_mm"], 0.02),
        ("features: on pitch circle (mm)", f["pcd_max_dev_mm"], 0.05),
        ("features: hole spacing (deg)", f["spacing_max_dev_deg"], 0.1),
        ("features: pattern at 45° (mm)", f["position_max_dev_mm"], 0.05),
        ("mass: 44.9 g of 52 g", G["mass"]["mass_g"], G["mass"]["limit_g"]),
        ("cross_check: volume", G["cross_check"]["volume_rel_dev"], G["cross_check"]["limit_rel"]),
        ("cross_check: area", G["cross_check"]["area_rel_dev"], G["cross_check"]["limit_rel"]),
        ("cross_check: centre of mass (mm)", G["cross_check"]["com_max_dev_mm"], G["cross_check"]["limit_com_mm"]),
        ("parametric: ΔV (+2 mm)", G["parametric"]["rel_dev"], G["parametric"]["limit_rel"]),
        ("stl: volume vs STEP", G["stl"]["rel_dev_vs_step"], G["stl"]["limit_rel"]),
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
    ax.set_xlim(FLOOR / 10, 300)
    ax.set_yticks(list(y))
    ax.set_yticklabels([r[0] for r in rows], fontsize=10)
    ax.set_xlabel("measured value or deviation / pass limit (log scale; < 1 passes)", fontsize=10)
    ax.set_title("12 numeric checks, labelled by their gate (build: pass/fail)", fontsize=12)
    for yi, r in zip(y, ratios):
        ax.text(1.5 if r > 1e-3 else r * 1.6, yi, "≤ 1e-12 (exact)" if r <= FLOOR else f"{r:.1e}",
                va="center", fontsize=8, color=INK)
    ok = v["passed"]
    fig.suptitle(f"solidcraft-cad — verdict: {'PASS' if ok else 'FAIL'}  "
                 f"(OCCT volume {v['gates']['volume']['occt_mm3']} mm³ vs analytic "
                 f"{v['gates']['volume']['analytic_mm3']} mm³, mass {v['gates']['mass']['mass_g']} g)",
                 fontsize=14, color=OK if ok else BAD)


def draw_loop(fig, verdicts: dict, agent: list):
    ax = fig.add_axes([0.07, 0.15, 0.40, 0.66])
    x = [int(a["attempt"]) for a in agent]
    then = [sum(1 for g in GATES if a["recorded_gates"].get(g)) for a in agent]
    now = [sum(1 for g in GATES if a["gates"].get(g)) for a in agent]
    ax.plot([i - 0.12 for i in x], then, "-o", color=BAD, lw=2, ms=8, label="graded by the judge it had (features gate too narrow)")
    ax.plot(x, now, "--s", color=ACCENT, lw=2, ms=7, label="same designs, fixed judge (this commit)")
    ax.axhline(len(GATES), color=OK, ls=":", lw=2)
    ax.text(1, len(GATES) + 0.2, f"pass = all {len(GATES)} gates", color=OK, fontsize=10)
    bad = [a for a in agent if a["failed_gate"] == "build"]
    for a in bad:
        ax.annotate("its own unit error\n(fails build)", (int(a["attempt"]), 0), textcoords="offset points",
                    xytext=(-150, 60), fontsize=10, color=INK, arrowprops={"arrowstyle": "->", "color": MUTED})
    ax.set_xticks(x)
    ax.set_ylim(-0.5, len(GATES) + 1.2)
    ax.set_xlabel("attempt (each a design.json the agent wrote and graded)")
    ax.set_ylabel(f"judge gates passed (of {len(GATES)})")
    ax.legend(loc="lower left", fontsize=9, frameon=False)
    ax.set_title("A real agent loop: an independent agent (GPT-6.1 Sol) modelled the part itself, 12 designs.\n"
                 "Its designs exposed a judge gap (B-spline cylinders), now fixed: see REPRODUCE.md", fontsize=11)

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
    ax2.set_title(f"Self-test: {killed}/{len(names) - 1} broken designs rejected "
                  f"({killed / (len(names) - 1):.0%}, need ≥ 90 %)\n"
                  "green = known-good passes; orange = broken, rejected (first failing gate)",
                  fontsize=11)
    fig.suptitle("solidcraft-cad — agent loop and judge power", fontsize=14)


def cmd_figures():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    verdicts = json.loads((DATA / "verdicts.json").read_text())
    agent = json.loads((DATA / "agent_run.json").read_text())
    fig = plt.figure(figsize=(14, 6.5))
    draw_result(fig, verdicts["good"])
    fig.savefig(MEDIA / "result.png", dpi=200)
    plt.close(fig)
    fig = plt.figure(figsize=(14, 6.5))
    draw_loop(fig, verdicts, agent)
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
    agent = json.loads((DATA / "agent_run.json").read_text())
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

    def chapter(n: int, title: str, sub: str):
        # a dark card between light slides: marks the chapter (and gives the
        # video gate a real scene cut)
        fig = plt.figure(figsize=(19.2, 10.8), facecolor=INK)
        fig.text(0.06, 0.56, f"{n} / 4", fontsize=34, color=MUTED)
        fig.text(0.06, 0.44, title, fontsize=60, weight="bold", color="white")
        fig.text(0.06, 0.34, sub, fontsize=26, color="#d0d0d0")
        emit(fig, 1.2)

    def image(fig, path, rect, crop=None):
        img = mpimg.imread(path)
        if crop:  # (top, bottom, left, right) as fractions of the render
            h, w = img.shape[:2]
            img = img[int(crop[0] * h):int(crop[1] * h), int(crop[2] * w):int(crop[3] * w)]
        ax = fig.add_axes(rect)
        ax.imshow(img)
        ax.axis("off")

    fig = canvas("Agent-built CAD part: PASS, 8/8 gates (12 checks)",
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
        fig.text(0.06, 0.74 - i * 0.08, ln, fontsize=30, color=INK)
    emit(fig, 4)

    chapter(1, "Build", "SolidCraft runs the agent's command script, step by step")
    for n, cap in STAGES:
        fig = canvas("SolidCraft builds the design script", cap)
        image(fig, RENDERS / f"stage{n}.png", [0.2, 0.02, 0.6, 0.84])
        emit(fig, 2)

    fig = canvas("Delivered part", "solidcraft-cli snapshot: iso, top, front. Holes sit at 45° on the pitch circle; "
                 "the iso view turns them to the screen axes")
    for i, v in enumerate(("iso", "top", "front")):
        image(fig, RENDERS / f"final_{v}.png", [0.0 + i * 0.335, 0.02, 0.33, 0.84], crop=(0.15, 0.85, 0.1, 0.9))
    emit(fig, 4)

    chapter(2, "Parametric", "change one parameter, the whole part rebuilds")
    vol0 = sweep[0]["solidcraft_volume_mm3"]
    for s in sweep:
        fig = canvas("Parametric: change thickness, the whole part rebuilds",
                     "front views, same scale: 6 mm (top) vs the rebuilt part (bottom); volume from solidcraft-cli eval")
        # the front view leaves the part small in the middle; crop to it (same crop every frame)
        image(fig, RENDERS / f"sweep_{sweep[0]['thickness_mm']}.png", [0.02, 0.47, 0.62, 0.38], crop=(0.4, 0.6, 0.12, 0.88))
        image(fig, RENDERS / f"sweep_{s['thickness_mm']}.png", [0.02, 0.05, 0.62, 0.38], crop=(0.4, 0.6, 0.12, 0.88))
        fig.text(0.67, 0.6, f"thickness = {s['thickness_mm']:.1f} mm", fontsize=34, color=ACCENT, weight="bold")
        fig.text(0.67, 0.5, f"V = {s['solidcraft_volume_mm3']:.1f} mm³", fontsize=28, color=INK)
        fig.text(0.67, 0.43, f"ΔV = {s['solidcraft_volume_mm3'] - vol0:+.1f} mm³", fontsize=28, color=INK)
        emit(fig, 1.6)
    pg = good["gates"]["parametric"]
    fig = canvas("Judge's parametric gate", "the judge sets thickness 6 → 8 mm, rebuilds, and re-grades the new part")
    for i, ln in enumerate([f"OCCT ΔV = {pg['volume_delta_mm3']} mm³",
                            f"analytic ΔV = A_net × 2 mm = {pg['analytic_delta_mm3']} mm³",
                            f"relative deviation {pg['rel_dev']:.1e}  (limit {pg['limit_rel']})",
                            f"bounding box within {pg['bbox_max_dev_mm']:.1e} mm, top z = {pg['top_z_mm']} mm",
                            f"all features + {pg['wall_checks']} wall checks pass on the rebuilt part"]):
        fig.text(0.06, 0.74 - i * 0.12, ln, fontsize=36, color=INK)
    emit(fig, 4)

    chapter(3, "Judge", "OpenCascade re-measures the delivered STEP and STL")
    rows = checks(good)
    for upto in (4, 8, len(rows)):
        fig = canvas("Judge verdict: 8 gates, 12 numeric checks",
                     "each row: gate: check (7 gates have numeric checks; build is pass/fail) — OCCT 8.0.1 vs spec.json")
        for i, (lab, m, lim) in enumerate(rows[:upto]):
            okr = m <= lim
            fig.text(0.05, 0.81 - i * 0.07, ("PASS  " if okr else "FAIL  ") + lab, fontsize=26,
                     color=OK if okr else BAD, weight="bold")
            fig.text(0.62, 0.81 - i * 0.07, f"{m:.3g}  (limit {lim:g})", fontsize=26, color=INK)
        emit(fig, 2.2)

    chapter(4, "Agent loop", "a real independent agent, and broken designs the judge rejects")
    for name, secs in (("loop.png", 6), ("result.png", 4)):  # the published figures, full frame
        fig = plt.figure(figsize=(19.2, 10.8))
        image(fig, MEDIA / name, [0.0, 0.05, 1.0, 0.9])
        emit(fig, secs)
    fig = canvas("Run it yourself", "one command: creates a sandbox, installs the tools, grades, kills the sandbox")
    fig.text(0.06, 0.62, "python3 cookbook/solidcraft-cad/run.py", fontsize=44, family="monospace", color=ACCENT)
    fig.text(0.06, 0.48, "github.com/agent-next/sandbox", fontsize=34, color=INK)
    fig.text(0.06, 0.34, "SolidCraft: github.com/bherbruck/solidcraft (MIT OR Apache-2.0)", fontsize=24, color=MUTED)
    emit(fig, 3)
    (out / "tmp.png").unlink()
    print(f"media: {k} frames ({k / 30:.1f} s)")


def cmd_manifest():
    ff = run(["ffmpeg", "-version"]).stdout.split("\n")[0]
    import matplotlib
    hf = run(["node", "-p",
              "require('./video/node_modules/hyperframes/package.json').version"],
             cwd=MEDIA).stdout.strip()
    files = {
        "result.png": ("Delivered part (SolidCraft render) + every judge pass rule as measured/limit, pass line at 1",
                       "bash media/make_media.sh (make_media.py figures)", "data/verdicts.json"),
        "loop.png": ("Independent agent's 12 designs: gates passed as recorded vs re-graded by this judge + self-test kills",
                     "bash media/make_media.sh (make_media.py figures)",
                     "data/agent_run.json, data/agent_run_recorded.json, data/agent_attempts/, data/verdicts.json"),
        "demo.mp4": ("Animated cut of this run's own geometry: the graded part turning, its real "
                     "SolidCraft build stages, an exploded view and a section sweep of the bore, "
                     "selftest.sh replayed from its stamped log at 51x, the parametric thickness "
                     "sweep, then the PASS badge over the still-moving part; composed by HyperFrames "
                     "(media/video/), see media/STORYBOARD.md",
                     "bash media/make_media.sh (export_glb.py + build_overlay_data.py + hyperframes "
                     "render -> ffmpeg crf 18)",
                     "data/verdicts.json, data/sweep.json, data/selftest.stamped.log, "
                     "examples/good/design.json via video/assets/*.glb"),
    }
    m = {"tools": {"solidcraft": "0.10.1", "matplotlib": matplotlib.__version__, "ffmpeg": ff,
                   "hyperframes": hf, "three": "0.180.0 (vendored in video/lib/, see lib/VENDORED.md)"},
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
