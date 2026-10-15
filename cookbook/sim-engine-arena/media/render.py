"""Headless figures and CSV-driven animation. No illustrative measurements."""

import importlib.util
import json
import math
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon
from matplotlib.text import Text
from matplotlib.ticker import MaxNLocator
import numpy as np

from collect import read_selftest

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
DATA = HERE / "data"
BLUE, ORANGE, GREEN, PURPLE = "#0072B2", "#D55E00", "#009E73", "#CC79A7"
INK, GREY = "#172B3A", "#677783"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12, "text.color": INK,
    "axes.labelcolor": INK, "axes.titleweight": "bold", "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.alpha": .16,
    "axes.axisbelow": True, "legend.framealpha": .95,
    "savefig.facecolor": "white",
})
module = importlib.util.spec_from_file_location("grade", DEMO / "judge/_grade.py")
grade = importlib.util.module_from_spec(module)
module.loader.exec_module(grade)
SPEC = json.loads((DEMO / "judge/spec.json").read_text())
SCENES = {s["name"]: s for s in SPEC["scenarios"]}
ORACLE = grade.oracle_values(SPEC)
VERDICT = json.loads((DATA / "grade.json").read_text())
METRIC = {n: s["oracle"] for n, s in VERDICT["scenarios"].items()}
TRAJ = {n: {k: np.asarray(v) for k, v in grade.parse_traj(
    DATA / s["output"]).items()} for n, s in SCENES.items()}


def check_text(fig, name):
    """Check all visible labels, ticks, legends and dynamic readouts in pixels."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = []
    # Locators retain Text objects for ticks outside the view interval.
    # Axis.draw does not draw those, even though Text.get_visible() is True.
    undrawn = set()
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            lo, hi = sorted(axis.get_view_interval())
            for tick in axis.get_major_ticks() + axis.get_minor_ticks():
                if not lo <= tick.get_loc() <= hi:
                    undrawn.update((tick.label1, tick.label2))
    for text in fig.findobj(Text):
        if text in undrawn or not text.get_visible() or not text.get_text().strip():
            continue
        box = text.get_window_extent(renderer)
        if box.width == 0 or box.height == 0:
            continue
        assert (box.x0 >= 0 and box.y0 >= 0 and
                box.x1 <= fig.bbox.width and box.y1 <= fig.bbox.height), \
            f"{name}: clipped text {text.get_text()!r}"
        # Inset each bbox by one pixel: touching edges are not a collision.
        box = box.padded(-1)
        for previous, other in boxes:
            assert not box.overlaps(other), \
                f"{name}: overlapping {text.get_text()!r} / {previous!r}"
        boxes.append((text.get_text(), box))


def save(fig, name):
    check_text(fig, name)
    fig.savefig(HERE / name, dpi=200, metadata={"Software": None})
    plt.close(fig)
    print(f"{name}: all text in bounds; no overlapping text")


def slope(name):
    rows = TRAJ[name]
    th = ORACLE[name]["theta"]
    s = rows["x"] * math.cos(th) - rows["z"] * math.sin(th)
    return s - s[0]


def theta_guide(t):
    # This is a labelled cosine PERIOD guide, not the exact nonlinear orbit.
    return SCENES["pendulum"]["theta0_rad"] * np.cos(
        2 * np.pi * t / ORACLE["pendulum"]["period"])


def result():
    fig, axs = plt.subplots(2, 2, figsize=(12, 8.8), dpi=200)
    fig.subplots_adjust(left=.085, right=.98, bottom=.12, top=.87,
                        hspace=.68, wspace=.28)
    fig.suptitle("Physics-engine arena | measured trajectories, analytic judge",
                 fontsize=17, y=.97, weight="bold")
    fig.text(.5, .92, "MuJoCo CPU · good artifact · seed 0 · all five gates PASS",
             ha="center", fontsize=12)
    a, b, c, d = axs.flat
    r = TRAJ["drop"]
    a.plot(r["t"], r["z"], color=BLUE, lw=2.5, label="MuJoCo center height")
    t = np.linspace(0, ORACLE["drop"]["t_contact"], 400)
    a.plot(t, SCENES["drop"]["body"]["pos"][2] - SPEC["gravity"] * t**2 / 2,
           "--", color=ORANGE, lw=2, label="Analytic free fall (pre-contact)")
    contact = METRIC["drop"]["t_contact"]
    a.axvline(contact, color=GREEN, ls=":", lw=2,
              label=f"Measured contact {contact:.4f} s")
    a.set(title="A  Drop onto a floor", xlabel="Time (s)", ylabel="Center height z (m)",
          xlim=(0, SCENES["drop"]["duration_s"]), ylim=(-.05, 1.55))
    a.legend(loc="upper right", fontsize=10)
    for name, color, label in (
        ("incline_slide", BLUE, "35° slide: MuJoCo"),
        ("incline_stick", GREEN, "20° stick: MuJoCo"),
    ):
        rows = TRAJ[name]
        b.plot(rows["t"], slope(name), color=color, lw=2.5, label=label)
    t = TRAJ["incline_slide"]["t"]
    b.plot(t, .5 * ORACLE["incline_slide"]["accel"] * t**2, "--",
           color=ORANGE, lw=2, label="Slide oracle: ½at²")
    b.plot(t, np.zeros_like(t), ":", color=PURPLE, lw=2,
           label="Stick oracle: s = 0")
    b.set(title="B  Friction: slide vs stick", xlabel="Time (s)",
          ylabel="Downhill travel s (m)", ylim=(-.04, 1.25), xlim=(0, 1))
    b.legend(loc="upper left", fontsize=10)
    rows = TRAJ["pendulum"]
    c.plot(rows["t"], rows["theta"], color=BLUE, lw=2.5, label="MuJoCo angle")
    c.plot(rows["t"], theta_guide(rows["t"]), "--", color=ORANGE, lw=1.8,
           label="Cosine guide using oracle period")
    c.set(title="C  Pendulum about the anchor", xlabel="Time (s)",
          ylabel="Angle θ (rad)", xlim=(0, SCENES["pendulum"]["duration_s"]),
          ylim=(-.14, .21))
    c.legend(loc="upper right", fontsize=10)
    c.text(.03, .12, f"Measured T = {METRIC['pendulum']['period']:.7f} s\n"
           f"Oracle T = {ORACLE['pendulum']['period']:.7f} s",
           transform=c.transAxes, fontsize=10,
           bbox={"facecolor": "white", "edgecolor": "none", "alpha": .95})
    values = [
        METRIC["drop"]["t_contact_err"] / grade.TOL["contact_time"],
        METRIC["incline_slide"]["accel_err"] / grade.TOL["accel"],
        METRIC["pendulum"]["period_err"] / grade.TOL["period"],
        METRIC["incline_stick"]["travel_m"] / grade.STICK_TRAVEL_M,
    ]
    d.bar(range(4), np.array(values) * 100,
          color=[BLUE, ORANGE, PURPLE, GREEN], width=.58)
    d.axhline(100, color=INK, ls="--", lw=1.5, label="SPEC pass limit (100%)")
    labels = [
        f"{METRIC['drop']['t_contact_err'] * 100:.3f}% / {100 * grade.TOL['contact_time']:g}%",
        f"{METRIC['incline_slide']['accel_err'] * 100:.3f}% / {100 * grade.TOL['accel']:g}%",
        f"{METRIC['pendulum']['period_err'] * 100:.1e}% / {100 * grade.TOL['period']:g}%",
        f"{METRIC['incline_stick']['travel_m'] * 1000:.2f} / "
        f"{grade.STICK_TRAVEL_M * 1000:g} mm",
    ]
    for x, value, label in zip(range(4), values, labels):
        d.text(x, max(value * 100, 0) + 6, label, ha="center", fontsize=9)
    d.set(title="D  Oracle error relative to each limit",
          ylabel="Error / SPEC limit (%)", ylim=(0, 145),
          xticks=range(4), xticklabels=["Drop", "Slide", "Pendulum", "Stick"])
    d.legend(loc="upper left", fontsize=10)
    for ax in axs.flat:
        if ax is not d:
            ax.xaxis.set_major_locator(MaxNLocator(5, integer=ax is c))
        ax.yaxis.set_major_locator(MaxNLocator(5))
    fig.text(.5, .035, "Stick uses travel / 20 mm, not relative error to zero. "
             "Cosine guide shows the SPEC period, not an exact nonlinear orbit.",
             ha="center", fontsize=10)
    save(fig, "result.png")


def gate_label(gates):
    entries = gates.split(",")
    suffixes = {g.split(".")[-1] for g in entries}
    if suffixes == {"csv_shape"}:
        return f"csv-shape ({len(entries)} scenes)"
    if suffixes == {"oracle"}:
        short = {"drop": "drop", "incline_slide": "slide",
                 "incline_stick": "stick", "pendulum": "pendulum"}
        return "oracle: " + ", ".join(short[g.split(".")[0]] for g in entries)
    return ", ".join(entries)


def loop():
    history = json.loads((DEMO / "examples/good/loop.json").read_text())["iterations"]
    mutants = read_selftest(DATA / "selftest.txt")
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 8), dpi=200,
                               gridspec_kw={"width_ratios": [1, 1.5]})
    fig.subplots_adjust(left=.07, right=.98, top=.81, bottom=.17, wspace=.70)
    fig.suptitle("The fixing loop, and a judge that rejects broken ports",
                 fontsize=17, y=.97, weight="bold")
    fig.text(.5, .915, "Recorded draft replay (not a live agent trace) + real judge/selftest.sh",
             ha="center")
    xs = [r["iteration"] for r in history]
    ys = [sum(s["pass"] for s in r["scenarios"].values()) for r in history]
    a.plot(xs, ys, color=BLUE, lw=2, marker="o", ms=9)
    for x, y, row in zip(xs, ys, history):
        a.text(x, y + .22, "PASS" if row["passed"] else "FAIL",
               ha="center", color=INK, weight="bold")
    a.axhline(len(SCENES), color=GREEN, ls="--", label="All scenes pass")
    a.set(title="A  Judge result per iteration", xlabel="Draft iteration",
          ylabel="Scenes passing CSV + oracle gates (count)",
          xlim=(.6, 3.4), ylim=(0, 5.2), xticks=xs, yticks=range(5))
    a.legend(loc="lower right", fontsize=10)
    a.text(.02, -.18, "1  Wrong pendulum pivot\n2  Box not aligned to incline\n"
           "3  Both corrected; agreement PASS", transform=a.transAxes, fontsize=10)
    labels = ["good"] + [name for name, _ in mutants]
    b.barh(range(len(labels)), [0] + [1] * len(mutants), color=BLUE, height=.60)
    b.scatter([0], [0], marker="o", color=GREEN, s=50, zorder=3)
    for y, label in enumerate(["PASS (not killed)"] +
                              [gate_label(g) for _, g in mutants]):
        b.text(1.07, y, label, va="center", fontsize=10)
    b.set(title=f"B  Selftest: {len(mutants)}/{len(mutants)} = 100% killed",
          xlabel="Rejected by judge (fraction)", yticks=range(len(labels)),
          yticklabels=labels, xlim=(-.04, 2.13), xticks=[0, .5, 1],
          ylim=(len(labels) - .4, -.9))
    b.tick_params(axis="y", labelsize=10)
    fig.text(.5, .035, "Good must pass; every mutant must fail. "
             "Gate labels come from selftest stdout, not the SPEC's predicted kills.",
             ha="center", fontsize=10)
    save(fig, "loop.png")


def at(name, column, t):
    return float(np.interp(t, TRAJ[name]["t"], TRAJ[name][column]))


def video_base(title, subtitle):
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor="white")
    fig.text(.055, .935, title, fontsize=28, weight="bold")
    fig.text(.055, .875, subtitle, fontsize=17, color=GREY)
    fig.text(.055, .04, "sim-engine-arena | MuJoCo CPU | seed 0 | "
             "CSV samples + SPEC-derived analytic guides", fontsize=15, color=GREY)
    return fig


def readouts(fig, lines):
    return [fig.text(.66, .76 - i * .07, line, fontsize=19)
            for i, line in enumerate(lines)]


def drop_video():
    fig = video_base("01 / Drop: free fall, then contact",
                     "A sphere, as simulated in the SPEC. Horizontal lanes separate the overlays.")
    ax = fig.add_axes([.07, .18, .48, .61])
    ax.set(xlim=(-.25, 1.1), ylim=(-.08, 1.15), ylabel="Center height z (m)",
           xticks=[0, .65], xticklabels=["Measured (CSV)", "Analytic ghost"])
    ax.set_aspect("equal")
    ax.axhline(0, color=INK, lw=2)
    radius = SCENES["drop"]["body"]["radius"]
    ball = Circle((0, 1), radius, color=BLUE)
    ghost = Circle((.65, 1), radius, fill=False, ec=ORANGE, lw=3, ls="--")
    ax.add_patch(ball)
    ax.add_patch(ghost)
    text = readouts(fig, ["", "", "", "", "", ""])
    def update(t):
        z = at("drop", "z", t)
        free = SCENES["drop"]["body"]["pos"][2] - SPEC["gravity"] * t*t/2
        ball.center = (0, z)
        ghost.center = (.65, max(radius, free))
        lines = [
            f"Simulation time       {t:6.3f} s",
            f"Measured height       {z:.4f} m",
            (f"Free-fall height       {free:.4f} m" if t <= ORACLE["drop"]["t_contact"]
             else "Ghost held at first contact"),
            f"Measured contact      {METRIC['drop']['t_contact']:.5f} s",
            f"Oracle contact           {ORACLE['drop']['t_contact']:.5f} s",
            f"Relative error             {100 * METRIC['drop']['t_contact_err']:.3f}%",
        ]
        for artist, line in zip(text, lines):
            artist.set_text(line)
    return fig, update


def box_vertices(center, theta, hx, hz):
    rotation = np.array([[math.cos(theta), math.sin(theta)],
                         [-math.sin(theta), math.cos(theta)]])
    return np.array([[-hx, -hz], [hx, -hz], [hx, hz], [-hx, hz]]) @ rotation.T + center


def incline_video():
    fig = video_base("02 / Inclines: friction separates slide from stick",
                     "Blue: CSV center positions. Orange dashed: analytic ghost. Outlines retain initial orientation.")
    patches = []
    for i, name in enumerate(("incline_slide", "incline_stick")):
        scene = SCENES[name]
        theta = ORACLE[name]["theta"]
        ax = fig.add_axes([.08, .53 - i * .34, .46, .24])
        ax.set(xlim=(-.15, .95), ylim=(-.65, .19), xlabel="x (m)", ylabel="z (m)")
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(f"{scene['plane']['tilt_deg']:g}°  |  μ = {scene['plane']['friction_mu']:g}",
                     fontsize=15)
        x = np.array([-.15, .95])
        ax.plot(x, -x * math.tan(theta), color=INK, lw=2)
        real = Polygon(np.zeros((4, 2)), color=BLUE)
        ghost = Polygon(np.zeros((4, 2)), fill=False, ec=ORANGE, lw=3, ls="--")
        ax.add_patch(real)
        ax.add_patch(ghost)
        patches.append((name, real, ghost))
    text = readouts(fig, [""] * 7)
    def update(t):
        for name, real, ghost in patches:
            scene = SCENES[name]
            theta = ORACLE[name]["theta"]
            hx, _, hz = scene["body"]["half_extents"]
            s = .5 * ORACLE[name]["accel"] * t*t if name == "incline_slide" else 0
            center = np.array([hz * math.sin(theta) + s * math.cos(theta),
                               hz * math.cos(theta) - s * math.sin(theta)])
            real.set_xy(box_vertices([at(name, "x", t), at(name, "z", t)], theta, hx, hz))
            ghost.set_xy(box_vertices(center, theta, hx, hz))
        measured_s = float(np.interp(t, TRAJ["incline_slide"]["t"], slope("incline_slide")))
        stick_s = float(np.interp(t, TRAJ["incline_stick"]["t"], slope("incline_stick")))
        lines = [
            f"Simulation time          {t:.3f} s",
            f"Slide: measured s       {measured_s:.4f} m",
            f"Slide: oracle ½at²       {.5 * ORACLE['incline_slide']['accel'] * t*t:.4f} m",
            f"Fitted acceleration     {METRIC['incline_slide']['accel']:.5f} m/s²",
            f"Oracle acceleration   {ORACLE['incline_slide']['accel']:.5f} m/s²",
            f"Stick travel now          {abs(stick_s) * 1000:.2f} mm",
            "Stick oracle                 0 mm",
        ]
        for artist, line in zip(text, lines):
            artist.set_text(line)
    return fig, update


def pendulum_video():
    fig = video_base("03 / Pendulum: the pivot belongs at the anchor",
                     "Orange ghost: θ₀ cos(2πt / T_oracle), a period guide, not the exact nonlinear orbit.")
    scene = SCENES["pendulum"]
    height, length = scene["anchor"][2], scene["link"]["L_m"]
    ax = fig.add_axes([.08, .16, .47, .63])
    ax.set(xlim=(-.45, .45), ylim=(height - length - .12, height + .1),
           xlabel="x (m)", ylabel="z (m)")
    ax.set_aspect("equal")
    ax.scatter([0], [height], color=INK, s=70)
    line, = ax.plot([], [], color=BLUE, lw=4)
    ghost, = ax.plot([], [], color=ORANGE, ls="--", lw=2)
    bob = Circle((0, height - length), .025, color=BLUE)
    guide = Circle((0, height - length), .035, fill=False, ec=ORANGE, lw=2)
    ax.add_patch(bob)
    ax.add_patch(guide)
    text = readouts(fig, [""] * 6)
    def update(t):
        angle, oracle_angle = at("pendulum", "theta", t), float(theta_guide(t))
        for theta, rod, mass in ((angle, line, bob), (oracle_angle, ghost, guide)):
            x, z = length * math.sin(theta), height - length * math.cos(theta)
            rod.set_data([0, x], [height, z])
            mass.center = (x, z)
        for artist, value in zip(text, [
            f"Simulation time     {t:.3f} s",
            f"Measured angle      {angle:+.5f} rad",
            f"Period-guide angle {oracle_angle:+.5f} rad",
            f"Measured period     {METRIC['pendulum']['period']:.7f} s",
            f"Oracle period          {ORACLE['pendulum']['period']:.7f} s",
            f"Relative error          {100 * METRIC['pendulum']['period_err']:.2e}%",
        ]):
            artist.set_text(value)
    return fig, update


def table_video():
    assert all(g["pass"] for g in VERDICT["gates"].values())
    assert all(g["pass"] for s in VERDICT["scenarios"].values() for g in s.values())
    fig = video_base("PASS / All five judge gates",
                     "Full grade.sh execution, seed 0. Values below come from data/grade.json.")
    rows = [
        ["Drop contact", f"{METRIC['drop']['t_contact']:.5f} s",
         f"{ORACLE['drop']['t_contact']:.5f} s ± {100 * grade.TOL['contact_time']:g}%", "PASS"],
        ["Incline slide", f"{METRIC['incline_slide']['accel']:.5f} m/s²",
         f"{ORACLE['incline_slide']['accel']:.5f} m/s² ± {100 * grade.TOL['accel']:g}%", "PASS"],
        ["Incline stick", f"{1000 * METRIC['incline_stick']['travel_m']:.2f} mm",
         f"< {1000 * grade.STICK_TRAVEL_M:g} mm", "PASS"],
        ["Pendulum period", f"{METRIC['pendulum']['period']:.7f} s",
         f"{ORACLE['pendulum']['period']:.7f} s ± {100 * grade.TOL['period']:g}%", "PASS"],
    ]
    cols = [.07, .32, .57, .89]
    for x, title in zip(cols, ["Scene / metric", "Measured", "Oracle / SPEC limit", "Judge"]):
        fig.text(x, .73, title, fontsize=20, weight="bold")
    for y, row in zip([.63, .53, .43, .33], rows):
        for x, value in zip(cols, row):
            fig.text(x, y, value, fontsize=20, color=GREEN if value == "PASS" else INK)
    fig.text(.07, .19, "Structure  PASS    Run  PASS    CSV shape  PASS    "
             "Oracle  PASS    Reference agreement  PASS", fontsize=19)
    fig.text(.07, .12, f"Judge intact: {VERDICT['judge_intact']}    "
             f"Selftest: {len(read_selftest(DATA / 'selftest.txt'))}/8 mutants killed",
             fontsize=19)
    return fig, lambda t: None


def video():
    fps = 30
    command = [
        "ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", "1920x1080", "-r", str(fps), "-i", "-", "-an",
        "-c:v", "libx264", "-threads", "2", "-crf", "0", "-preset", "ultrafast",
        "-pix_fmt", "yuv444p", "-map_metadata", "-1", str(HERE / "master/demo.mp4"),
    ]
    # Every frame is drawn at 30 fps. Each chapter covers the complete CSV span.
    chapters = [(drop_video, 6, SCENES["drop"]["duration_s"]),
                (incline_video, 8, SCENES["incline_slide"]["duration_s"]),
                (pendulum_video, 10, SCENES["pendulum"]["duration_s"]),
                (table_video, 4, 0)]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
        try:
            for constructor, seconds, span in chapters:
                fig, update = constructor()
                for t in np.linspace(0, span, seconds * fps):
                    update(float(t))
                    check_text(fig, constructor.__name__)
                    encoder.stdin.write(fig.canvas.buffer_rgba())
                plt.close(fig)
                print(f"{constructor.__name__}: every frame text-checked", flush=True)
        finally:
            encoder.stdin.close()
        assert encoder.wait() == 0, "Lossless encoding failed"


if __name__ == "__main__":
    result()
    loop()
    video()
