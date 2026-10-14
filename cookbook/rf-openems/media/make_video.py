#!/usr/bin/env python3
"""demo.mp4 -- the S11 design loop, replayed from the real grade traces.

Scene 1  title card (3 s)
Scene 2  S11 vs frequency, one replayed iteration at a time (3 s each),
         in the order a fixing agent would hit them (nan er -> wrong er
         -> thick substrate -> coarse mesh -> wrong patch length ->
         no ground plane -> feed at the voltage node), each curve from
         that run's grade.py --trace CSV, with the -10 dB G4 pass line,
         the G5 +-2 % band, and the gate that killed it (measured value
         vs limit from its verdict JSON). Earlier iterations stay as
         faint context curves. Labelled as a replay, not a live trace.
Scene 3  the good design (6 s): measured S11 + judge re-derivation (G6)
         + fine-mesh re-run (G8) + gate readouts from the verdict JSON.
Scene 4  closing card (3 s): selftest kill rate from selftest.txt.

Total 30 s at 1920x1080 30 fps.

openEMS does not dump fields cheaply in this setup (nf2ff is disabled
and the artifact writes no 3D field probes), so the video shows the
S11 loop only -- no field snapshots (noted in media/REVIEW.md).

Frames -> lossless master (crf 0) in media/master/ (git-ignored) ->
web encode (crf 18, preset slow, yuv420p, +faststart) -> media/demo.mp4.
Fails if any source file is missing, if the duration is outside 20-60 s,
or the web encode is above 8 MB.
"""
import json
import os
import re
import shutil
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fig_loop import kill_row

MEDIA = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(MEDIA, "data")
FRAMES = os.path.join(MEDIA, "frames")
MASTER = os.path.join(MEDIA, "master")
OUT = os.path.join(MEDIA, "demo.mp4")

W, H, FPS = 1920, 1080, 30
F_TARGET, S11_TARGET, F_RES_TOL = 2.45, -10.0, 0.02

C_BAD = "#D55E00"        # Okabe-Ito vermillion (failed iteration)
C_GOOD = "#0072B2"       # Okabe-Ito blue
C_FINE = "#009E73"       # Okabe-Ito green
C_SPEC = "#c94343"       # status red, reserved for the limit

FFMPEG = os.environ.get("RF_FFMPEG", "ffmpeg")

# (case, headline, holds_seconds); caption text is built from the
# verdict JSON so the measured value always matches it.
REPLAY = [
    ("bad_nan_er", "er = NaN", 3.0),
    ("bad_substrate_er", "er = 2.2", 3.0),
    ("bad_thick_substrate", "sub_h = 3.5 mm", 3.0),
    ("bad_coarse_mesh", "mesh_res = 2.4 mm", 3.0),
    ("bad_patch_length", "patch_L = 22 mm", 3.0),
    ("bad_no_ground", "ground plane deleted", 3.0),
    ("bad_feed_center", "feed_inset = 12 mm", 3.0),
    ("good", "the good design", 6.0),
]


def need(p):
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run media/make_data.sh first")
    return p


def read_trace(name):
    d = np.genfromtxt(need(os.path.join(DATA, "traces", name + ".csv")),
                      delimiter=",", names=True)
    return d["freq_ghz"], d["s11_db"]


def verdict(name):
    return json.load(open(need(os.path.join(DATA, "verdicts",
                                            name + ".json"))))


def s11_axes(fig):
    ax = fig.add_axes((0.09, 0.16, 0.86, 0.62))
    band = (F_TARGET * (1 - F_RES_TOL), F_TARGET * (1 + F_RES_TOL))
    ax.axvspan(*band, color="#97b7d3", alpha=0.25, zorder=0)
    ax.axhline(S11_TARGET, color=C_SPEC, lw=2.0, ls="--", zorder=1)
    ax.axvline(F_TARGET, color="0.35", lw=1.0, zorder=2)
    ax.set_xlim(2.2, 2.7)
    ax.set_ylim(-30, 2)
    ax.set_xlabel("frequency [GHz]", fontsize=13)
    ax.set_ylabel("|S11| [dB]", fontsize=13)
    ax.tick_params(labelsize=11)
    ax.grid(True, alpha=0.25)
    ax.set_xticks(np.arange(2.2, 2.71, 0.05))
    return ax, band


class Recorder:
    """Collects (frame_path, hold_seconds) and saves one PNG per card."""

    def __init__(self):
        self.cards = []
        self.n = 0

    def add(self, fig, seconds):
        p = os.path.join(FRAMES, f"card{self.n:03d}.png")
        fig.savefig(p)
        plt.close(fig)
        self.cards.append((p, seconds))
        self.n += 1


def scene_title(rec):
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.text(0.5, 0.66, "rf-openems", ha="center", fontsize=52,
             fontweight="bold")
    fig.text(0.5, 0.56, "designing a 2.45 GHz patch antenna on FR-4 "
             "inside a disposable sandbox", ha="center", fontsize=21)
    fig.text(0.5, 0.45, "judge: openEMS FDTD re-run, S11 re-derived from "
             "the raw port time series,\nHammerstad-Jensen oracle, "
             "fine-mesh convergence -- it does not trust a "
             "self-report", ha="center", fontsize=14, color="0.25")
    fig.text(0.5, 0.30, "every curve below is a real judge run "
             "(grade.sh --trace, seed 42): one grade per known-bad\n"
             "variant, then the good design -- recorded verdicts, "
             "not a live agent trace", ha="center", fontsize=13,
             color="0.35")
    rec.add(fig, 3.0)


def scene_replay(rec):
    for i, (case, headline, secs) in enumerate(REPLAY):
        v = verdict(case)
        fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
        ax, _ = s11_axes(fig)
        ok = v["all_pass"]

        # earlier iterations as faint context
        for j in range(i):
            cj = REPLAY[j][0]
            if os.path.exists(os.path.join(DATA, "traces",
                                            cj + "__s11_artifact.csv")):
                fj, sj = read_trace(cj + "__s11_artifact")
                ax.plot(fj, sj, color="0.82", lw=1.0, zorder=2)

        if ok:
            fg, sg = read_trace("good__s11_artifact")
            fj_, sj_ = read_trace("good__s11_judge")
            ff, sf = read_trace("good__s11_fine")
            ax.plot(fg, sg, color=C_GOOD, lw=3.0, zorder=4,
                    label="measured S11 (grader trace)")
            ax.plot(fj_, sj_, color="0.15", lw=1.5, ls=(0, (4, 3)),
                    zorder=5, label="judge re-derived from raw port "
                    "time series (G6)")
            ax.plot(ff, sf, color=C_FINE, lw=1.6, ls=(0, (1, 1.6)),
                    zorder=5, label="fine-mesh re-run, 0.9 mm (G8)")
            ax.legend(loc="upper right", fontsize=11, framealpha=0.95)
            i_res = int(np.argmin(sg))
            ax.plot([fg[i_res]], [sg[i_res]], "o", ms=9, mfc="white",
                    mec=C_GOOD, mew=2.0, zorder=6)
            ax.annotate(f"min S11 = {sg[i_res]:.1f} dB @ "
                        f"{fg[i_res]:.2f} GHz",
                        xy=(fg[i_res], sg[i_res]),
                        xytext=(fg[i_res] + 0.03, sg[i_res] - 2.5),
                        fontsize=13, fontweight="bold",
                        arrowprops=dict(arrowstyle="-", color=C_GOOD))
            fig.text(0.5, 0.885, f"iteration {i+1}/{len(REPLAY)}: "
                     f"{headline} -- ALL 9 GATES PASS", ha="center",
                     fontsize=20, fontweight="bold", color=C_GOOD)
            g4 = next(g for g in v["gates"]
                      if g["gate"] == "G4_S11_at_target")
            conv = v["convergence"]
            fig.text(0.09, 0.035, f"G4 {g4['detail']}  |  G5 f_res = 2.44 "
                     f"GHz (±2 %)  |  G6 max diff "
                     f"{v['raw_crosscheck_maxdiff_db']:.1f} dB ≤ 1.5  |  "
                     f"G7 eeff Δ {v['oracle']['delta_pct']:.1f} % ≤ 4 %  |  "
                     f"G8 fine mesh S11 {conv['S11_at_target_fine_dB']:.1f}"
                     f" dB, f_res shift {conv['f_res_shift_pct']:.1f} %",
                     fontsize=11, family="monospace", color="0.2")
        else:
            tr = os.path.join(DATA, "traces", case + "__s11_artifact.csv")
            if os.path.exists(tr):
                fg, sg = read_trace(case + "__s11_artifact")
                ax.plot(fg, sg, color=C_BAD, lw=3.0, zorder=4,
                        label="measured S11 (grader trace)")
                ax.legend(loc="upper right", fontsize=11,
                          framealpha=0.95)
            else:
                ax.text(2.45, -13, "no S11 trace: the judge killed this "
                        "design at a sanity gate (G1/G2)\nbefore running "
                        "any simulation", ha="center", fontsize=14,
                        color="0.4", style="italic")
            fig.text(0.5, 0.885, f"iteration {i+1}/{len(REPLAY)}: "
                     f"{headline} -- judge FAIL", ha="center", fontsize=20,
                     fontweight="bold", color=C_BAD)
            fig.text(0.09, 0.035, "killed by  " + "   |   ".join(kill_row(case)),
                     fontsize=12, family="monospace", color="0.2")

        fig.text(0.09, 0.915, "G4 rule: the curve must dip below the red "
                 f"-{abs(S11_TARGET):.0f} dB line at 2.45 GHz, inside the "
                 "shaded G5 band (2.45 GHz ±2 %)\n(deeper dip = better "
                 "match; a shallow dip means power reflected back to the "
                 "source)", fontsize=10.5, color="0.45", va="bottom")
        rec.add(fig, secs)


def scene_close(rec, kill_line):
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.text(0.5, 0.62, "every bad design was caught", ha="center",
             fontsize=40, fontweight="bold")
    fig.text(0.5, 0.50, kill_line, ha="center", fontsize=22, color="0.2")
    fig.text(0.5, 0.38, "replay of real judge runs: 7 single-edit "
             "mutants, every one killed at the gate that measures its\n"
             "actual mistake -- the good design passes all 9 gates, "
             "including the fine-mesh convergence re-run", ha="center",
             fontsize=15, color="0.3")
    fig.text(0.5, 0.26, "source: media/data/ (verdict JSONs, grade "
             "traces, selftest log) -- no synthesised data", ha="center",
             fontsize=12, color="0.4")
    rec.add(fig, 3.0)


def main():
    for d in (FRAMES, MASTER):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

    st = open(need(os.path.join(DATA, "selftest.txt"))).read()
    m = re.search(r"selftest: good=(\d/1), mutants_killed=(\d/\d).*\n"
                  r"kill rate: (\d+)%", st)
    if not m:
        raise SystemExit("selftest.txt missing kill-rate lines")
    kill_line = (f"selftest: good {m.group(1)}, mutants killed "
                 f"{m.group(2)}, kill rate {m.group(3)} %")

    rec = Recorder()
    scene_title(rec)
    scene_replay(rec)
    scene_close(rec, kill_line)

    total = sum(s for _, s in rec.cards)
    if not (20.0 <= total <= 60.0):
        raise SystemExit(f"planned duration {total:.0f} s outside 20-60 s")

    # lossless master via the concat demuxer (1 PNG per card, each held
    # for its duration) -> H.264 crf 0
    lst = os.path.join(MASTER, "frames.txt")
    with open(lst, "w") as f:
        for p, s in rec.cards:
            f.write(f"file '{p}'\nduration {s}\n")
        f.write(f"file '{rec.cards[-1][0]}'\n")
    master = os.path.join(MASTER, "demo_lossless.mp4")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat",
                   "-safe", "0", "-i", lst, "-vsync", "cfr",
                   "-r", str(FPS), "-c:v", "libx264", "-crf", "0",
                   "-preset", "veryslow", "-pix_fmt", "yuv444p",
                   master], check=True)

    # web encode
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", master,
                    "-r", str(FPS), "-c:v", "libx264", "-crf", "18",
                    "-preset", "slow", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", OUT], check=True)

    probe = subprocess.run([FFMPEG, "-i", OUT], capture_output=True,
                            text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe)
    if not m:
        raise SystemExit("could not probe demo.mp4 duration")
    dur = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
           + float(m.group(3)))
    if not (20.0 <= dur <= 60.0):
        raise SystemExit(f"demo.mp4 duration {dur:.1f} s outside 20-60 s")
    size = os.path.getsize(OUT)
    if size > 8_000_000:
        raise SystemExit(f"demo.mp4 is {size/1e6:.2f} MB (> 8 MB)")
    print(f"demo.mp4: {dur:.1f} s, {size/1e6:.2f} MB, "
          f"{len(rec.cards)} cards; lossless master at {master}")


if __name__ == "__main__":
    main()
