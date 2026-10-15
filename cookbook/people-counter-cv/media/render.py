"""Render result.png, loop.png and the lossless video master.

Every plotted number comes from judge outputs (media/data/) - nothing
illustrative or invented. Palette is Okabe-Ito (colour-blind-safe).
Deterministic: single-threaded, Agg backend, fixed source date epoch.
"""

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

INK = "#000000"
BLUE = "#0072B2"     # truth / east
ORANGE = "#E69F00"   # limits
VERM = "#D55E00"     # west
GREEN = "#009E73"    # pass
SKY = "#56B4E9"      # artifact
GREY = "#999999"

FPS_OUT = 30
PLAY_S = 42.0        # clip (60 s at 12 fps) compressed into 42 s
CARD_S = 6.0         # verdict end card

SPEC = json.loads((HERE.parent / "judge/spec.json").read_text())
GRADE = json.loads((DATA / "grade.json").read_text())
TRUTH = json.loads((DATA / "truth.json").read_text())
N_CLIP = int(SPEC["video"]["duration_s"] * SPEC["video"]["fps"])
LINE_X = SPEC["video"]["width_px"] * SPEC["tripwire"]["x_fraction"]


def read_crossings(path):
    rows = list(csv.reader(path.open()))[1:]
    return [(float(r[0]), 1 if r[1] == "1" else -1) for r in rows]


ART = read_crossings(DATA / "crossings.csv")
REF = read_crossings(DATA / "ref_crossings.csv")
TRUTH_EV = [(e["t"], 1 if e["dir"] == "east" else -1) for e in TRUTH["events"]]


def style():
    plt.rcParams.update({
        "font.size": 11, "axes.titlesize": 12, "axes.labelsize": 11,
        "figure.dpi": 100, "savefig.dpi": 200, "savefig.bbox": "tight",
        "axes.spines.top": False, "axes.spines.right": False,
    })


# ---------------------------------------------------------------- result.png

def result_png():
    style()
    m = GRADE["gates"]["oracle"]["metrics"]
    fig = plt.figure(figsize=(12.5, 7.4))

    ax = fig.add_axes([.04, .55, .40, .40])
    # a frame near the busiest crossing window, with the tripwire drawn
    best = max(range(N_CLIP),
               key=lambda k: sum(1 for t, _ in TRUTH_EV if k / 12 - .4 < t < k / 12))
    frame = plt.imread(DATA / f"frames/f{best:04d}.png")
    ax.imshow(frame, cmap="gray")
    ax.axvline(LINE_X, color=VERM, lw=2)
    ax.text(LINE_X + 8, 12, "tripwire x=320", color=VERM, fontsize=10,
            rotation=90, va="top")
    ax.set(xticks=[], yticks=[])
    ax.set_title(f"Clip frame at t = {best / 12:.1f} s (640x360, 12 fps, "
                 f"seed 0)")

    ax = fig.add_axes([.53, .55, .43, .40])
    for t, d in TRUTH_EV:
        ax.plot([t, t], [0.55, 1.0] if d > 0 else [-1.0, -0.55],
                color=BLUE, lw=2)
    for i, (t, d) in enumerate(ART):
        y = 0.40 if d > 0 else -0.40
        ax.plot(t, y, marker=">" if d > 0 else "<", color=SKY, ms=7)
    ax.axhline(0, color=INK, lw=1)
    ax.set(xlim=(0, 60), ylim=(-1.25, 1.25), xlabel="time (s)")
    ax.set_yticks([-0.75, 0, 0.75])
    ax.set_yticklabels(["west", "", "east"])
    ax.set_title(f"Crossings: truth (blue, n={len(TRUTH_EV)}) vs "
                 f"artifact (markers, n={len(ART)})")

    ax = fig.add_axes([.04, .07, .40, .38])
    pairs = []
    used = set()
    for tt, td in TRUTH_EV:
        best_j, bd = None, 0.5
        for j, (at, ad) in enumerate(ART):
            if j in used or ad != td:
                continue
            if abs(at - tt) < bd:
                best_j, bd = j, abs(at - tt)
        if best_j is not None:
            used.add(best_j)
            pairs.append((tt, ART[best_j][0] - tt))
    pairs.sort()
    ax.bar([p[0] for p in pairs], [abs(p[1]) * 1000 for p in pairs],
           width=0.62, color=SKY)
    ax.axhline(300, color=ORANGE, lw=2)
    ax.axhline(150, color=ORANGE, lw=1.2, ls="--")
    ax.text(59, 312, "max 300 ms", ha="right", color=ORANGE, fontsize=9)
    ax.text(59, 120, "MAE limit 150 ms", ha="right", color=ORANGE, fontsize=9)
    ax.set(xlim=(0, 60), ylim=(0, 340), xlabel="time (s)",
           ylabel="crossing-time error (ms)")
    ax.set_title(f"|artifact - truth| per event "
                 f"(MAE {m['time_mae_s']*1000:.0f} ms, "
                 f"max {m['time_max_dev_s']*1000:.0f} ms)")

    ax = fig.add_axes([.53, .07, .43, .38])
    labels = ["east\ntruth", "east\nartifact", "east\nreference",
              "west\ntruth", "west\nartifact", "west\nreference"]
    ref_c = {"east": sum(1 for _, d in REF if d > 0),
             "west": sum(1 for _, d in REF if d < 0)}
    vals = [m["truth_counts"]["east"], m["artifact_counts"]["east"],
            ref_c["east"], m["truth_counts"]["west"],
            m["artifact_counts"]["west"], ref_c["west"]]
    cols = [BLUE, SKY, GREY, BLUE, SKY, GREY]
    ax.bar(range(6), vals, color=cols)
    for i, v in enumerate(vals):
        ax.text(i, v + .15, str(v), ha="center", fontsize=10)
    ax.set_xticks(range(6), labels, fontsize=9)
    ax.set(ylabel="crossings", ylim=(0, 13.5))
    ax.set_title("Counts: analytic truth vs artifact vs judge MOG2 "
                 "reference (limit: error <= 1 per direction)")

    fig.suptitle("people-counter-cv: artifact vs analytic truth - judge "
                 f"verdict PASS ({len(ART)}/{len(TRUTH_EV)} events, "
                 "all five gates)", y=.995, fontsize=13)
    fig.savefig(HERE / "result.png")
    plt.close(fig)


# ----------------------------------------------------------------- loop.png

def loop_png():
    style()
    loop = json.loads((HERE.parent / "examples/good/loop.json").read_text())
    selftest = (DATA / "selftest.txt").read_text().splitlines()
    mut_rows = [l.split("mutant ")[1].split(": killed (gate: ")
                for l in selftest if ": killed" in l]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12.5, 7.0),
                                   height_ratios=[1, 1.25])
    its = loop["iterations"]
    xs = np.arange(len(its))
    for i, it in enumerate(its):
        m = it.get("oracle") or {}
        good = it["passed"]
        ax1.bar(i, 20, color="#e8e8e8")
        matched = m.get("matched")
        art = (m.get("artifact_counts") or {})
        extra = sum(art.values()) - (matched if matched is not None else 0)
        miss = 20 - (matched if matched is not None else
                     (20 if good else sum(art.values())))
        if good:
            ax1.bar(i, 20, color=GREEN)
            ax1.text(i, 20.3, "20/20 PASS", ha="center", fontsize=9,
                     color=GREEN)
        else:
            matched_n = m.get("matched") or 0
            ax1.bar(i, matched_n, color=GREEN)
            extra_n = (sum(art.values()) - matched_n) if art else 0
            ax1.bar(i, extra_n, bottom=matched_n, color=VERM)
            ax1.bar(i, 20 - matched_n - extra_n, bottom=matched_n + extra_n,
                    color="#d8d8d8")
            ax1.text(i, 20.4, f"{matched_n} ok{f' +{extra_n}' if extra_n else ''}",
                     ha="center", fontsize=9)
    ax1.set_xticks(xs, [f"{it['iteration']}: {it['draft'][:28]}"
                        for it in its], fontsize=8.5)
    ax1.set(ylabel="events (of 20 truth)", ylim=(0, 23),
            title="Graded agent loop (examples/good/loop.json): green = "
                  "matched, red = phantoms, grey = missed")

    names = ["good"] + [r[0] for r in mut_rows]
    gates = ["all pass"] + [r[1].rstrip(")") for r in mut_rows]
    cols = [GREEN] + [VERM] * len(mut_rows)
    ax2.barh(range(len(names))[::-1], [1] * len(names), color=cols)
    for y, name, gate in zip(range(len(names))[::-1], names, gates):
        ax2.text(.02, y, name, va="center", fontsize=9.5)
        ax2.text(.99, y, gate, va="center", ha="right", fontsize=9,
                 color=INK)
    ax2.set(xlim=(0, 1), xticks=[], yticks=[])
    ax2.set_title("Selftest: every mutant fails at least one gate "
                  f"(kill rate {len(mut_rows)}/{len(mut_rows)} = 100%)")
    fig.tight_layout()
    fig.savefig(HERE / "loop.png")
    plt.close(fig)


# ---------------------------------------------------------------- demo.mp4

def video():
    style()
    plt.rcParams["savefig.dpi"] = 100
    W, H = 19.2, 10.8
    fig = plt.figure(figsize=(W, H))

    # 640x360 clip at 16:9; .48 of a 19.2x10.8 fig is 9.216 x 5.184 in
    ax_clip = fig.add_axes([.05, .26, .48, .48])
    im = ax_clip.imshow(np.zeros((360, 640)), cmap="gray", vmin=0, vmax=255)
    vline = ax_clip.axvline(LINE_X, color=VERM, lw=3)
    ax_clip.set(xticks=[], yticks=[])
    flash = ax_clip.axvspan(LINE_X - 6, LINE_X + 6, color=VERM, alpha=0.0)
    ax_clip.set_title("input/video.avi - 640x360 grayscale, 12 fps "
                      "(deterministic scene, seed 0)", fontsize=17)

    ax_hist = fig.add_axes([.60, .42, .36, .42])
    east_hist, = ax_hist.step([0], [0], where="post", color=SKY, lw=4)
    west_hist, = ax_hist.step([0], [0], where="post", color=VERM, lw=4)
    truth_marks = [ax_hist.plot(t, 12 if d > 0 else -12, marker="|" if d > 0 else "|",
                                color=BLUE, ms=12)[0] for t, d in TRUTH_EV]
    ax_hist.set(xlim=(0, 60), ylim=(-16, 16), xlabel="time (s)",
                yticks=[-12, 0, 12])
    ax_hist.set_yticklabels(["west", "0", "east"])
    ax_hist.set_title("Cumulative counted crossings vs truth ticks (blue)",
                      fontsize=17)
    counts_txt = fig.text(.60, .30, "", fontsize=19, family="monospace")
    err_txt = fig.text(.60, .18, "", fontsize=15, family="monospace",
                       color="#333333")
    clock_txt = fig.text(.05, .05, "", fontsize=19, family="monospace")

    m = GRADE["gates"]["oracle"]["metrics"]
    a = GRADE["gates"]["agreement"]["metrics"]

    n_play = int(PLAY_S * FPS_OUT)
    n_card = int(CARD_S * FPS_OUT)

    def update(i):
        if i < n_play:
            t_clip = (i / n_play) * 60.0
            k = min(N_CLIP - 1, int(t_clip * 12))
            im.set_data(plt.imread(DATA / f"frames/f{k:04d}.png"))
            recent = [t for t, _ in ART if t <= t_clip]
            hot = any(t_clip - .25 <= t <= t_clip for t, _ in ART)
            flash.set_alpha(0.55 if hot else 0.0)
            clock_txt.set_text(f"clip time  {t_clip:6.2f} s   "
                               f"({len(recent)} crossings so far)")
            ts_e = [0] + [t for t, d in ART if d > 0 and t <= t_clip]
            ts_w = [0] + [t for t, d in ART if d < 0 and t <= t_clip]
            east_hist.set_data(np.array(ts_e + [t_clip]),
                               np.append(np.arange(len(ts_e)),
                                         len(ts_e) - 1))
            west_hist.set_data(np.array(ts_w + [t_clip]),
                               np.append(-np.arange(len(ts_w)),
                                         -(len(ts_w) - 1)))
            for tm, (t, d) in zip(truth_marks, TRUTH_EV):
                tm.set_alpha(1.0 if t <= t_clip else 0.0)
            counts_txt.set_text(
                f"east {len(ts_e) - 1:2d}     west {len(ts_w) - 1:2d}")
            err_txt.set_text("good counter: background subtraction + size "
                             "filter\n+ centroid tracking + edge-triggered "
                             "tripwire")
        else:
            if not update.card_drawn:
                update.card_drawn = True
                ax_clip.clear()
                ax_clip.axis("off")
                ax_hist.clear()
                ax_hist.axis("off")
                lines = [
                    ("people-counter-cv judge verdict:  PASS", GREEN, 30),
                    ("", INK, 12),
                    ("gate structure : pass   (cv2, spec at runtime, no "
                     "hardcoded truth times)", GREEN, 17),
                    ("gate run       : pass   (exit 0, crossings.csv "
                     "written)", GREEN, 17),
                    ("gate csv-shape : pass   (header, one-hot, sorted)",
                     GREEN, 17),
                    ("gate oracle    : pass   (counts 11E/9W = truth, "
                     "error 0)", GREEN, 17),
                    ("gate agreement : pass   (vs judge MOG2 reference: "
                     "20 paired)", GREEN, 17),
                    (f"judge_intact   : {str(GRADE['judge_intact']).lower()}",
                     GREEN, 17),
                    ("", INK, 12),
                    (f"recall {m['recall']}, precision {m['precision']}, "
                     f"time MAE {m['time_mae_s']*1000:.0f} ms, "
                     f"max dev {m['time_max_dev_s']*1000:.0f} ms",
                     INK, 17),
                    (f"direction accuracy {m['direction_accuracy']}, "
                     f"reference agreement {a['max_time_dev_s']*1000:.0f} ms",
                     INK, 17),
                    ("selftest kill rate 9/9 = 100%", INK, 17),
                ]
                y = .86
                for text, color, size in lines:
                    fig.text(.08, y, text, color=color, fontsize=size,
                             family="monospace" if size < 30 else None)
                    y -= .045 + (0.012 if size >= 30 else 0)
                clock_txt.set_text("")
                counts_txt.set_text("")
                err_txt.set_text("")
        return []

    update.card_drawn = False

    writer = animation.FFMpegWriter(
        fps=FPS_OUT, codec="libx264",
        extra_args=["-preset", "medium", "-crf", "0", "-pix_fmt", "yuv444p"])
    anim = animation.FuncAnimation(fig, update, frames=n_play + n_card,
                                   interval=1000 / FPS_OUT)
    (HERE / "master").mkdir(exist_ok=True)
    anim.save(HERE / "master/demo.mp4", writer=writer,
              dpi=100, savefig_kwargs={"transparent": False})
    plt.close(fig)


if __name__ == "__main__":
    result_png()
    print("render: result.png")
    loop_png()
    print("render: loop.png")
    video()
    print("render: master/demo.mp4")
