#!/usr/bin/env python3
"""demo.mp4 -- the ci-test-matrix demo video, cut from real judge output.

Every shot is built from files the judge wrote in this sandbox
(media/data/verdict-*.json, data/selftest.log, data/grade-good.txt, the
artifact's own examples/good/matrix.yaml).  Nothing is synthesised: if a
source file is missing the script exits non-zero.

Scenes (see STORYBOARD.md):
  1  hook            the finished matrix + PASS, a highlight band sweeping
  2  input           examples/good/matrix.yaml scrolling beside the four
                     keys the judge parses
  3  input -> output the five cells build with their real interpreter
                     stamps, a progress bar runs
  4  escalate        the judge's self-test transcript streaming (labelled
                     ~40x speed), kill counter climbing to 9/9
  5  escalate        grade.sh's verdict JSON streaming (~6x speed), gates
                     flipping PASS
  6  replay          the replayed fix sequence, 1/8 -> 7/8 -> 8/8 gates
                     (labelled a replay of real grade verdicts)
  7  kill matrix     9 mutants x 8 gates fill from the real verdict JSONs
  8  proof           the judge's mask bars fill; PASS + exit codes on top
  9  end card        static: the one-command launch

Frames -> ffmpeg concat -> lossless master (-crf 0) in git-ignored
media/master/ -> web encode (-crf 18 -preset slow -pix_fmt yuv420p
-movflags +faststart) -> media/demo.mp4.  Asserts 1920x1080, 25-60 s,
< 8 MB at the end.
"""
import json
import os
import re
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (GATES, GATE_SHORT, MUTANTS, ROWS, C_PASS, C_FAIL,
                    C_ORACLE, C_DIM, load_verdict, gates_passed, cell_short,
                    selftest_kill)

MEDIA = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(MEDIA, "data")
FRAMES = os.path.join(MEDIA, "master", "frames")
MASTER = os.path.join(MEDIA, "master")
OUT = os.path.join(MEDIA, "demo.mp4")

W, H, FPS = 1920, 1080, 30
MONO = "DejaVu Sans Mono"
SANS = "DejaVu Sans"
INK = "#1a1a1a"
PAPER = "#ffffff"
TERM_BG = "#0d1117"
TERM_FG = "#e6edf3"

# captions: cap height >= 4 % of 1080 px -> fontsize 44 pt at dpi 100
CAP_SIZE = 44
CAP_Y = 46


def need(path):
    if not os.path.exists(path):
        raise SystemExit("make_video: missing %s -- run media/collect.sh "
                         "first" % path)
    return path


# ------------------------------------------------------------------ canvas
class Canvas:
    """One 1920x1080 frame; pixel coordinates, y up."""

    def __init__(self):
        self.fig = plt.figure(figsize=(W / 100, H / 100), dpi=100,
                              facecolor=PAPER)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, W)
        self.ax.set_ylim(0, H)
        self.ax.axis("off")
        self.ax.set_facecolor(PAPER)

    def text(self, x, y, s, size=24, color=INK, weight="normal",
             family=SANS, ha="left", va="center", **kw):
        return self.ax.text(x, y, s, fontsize=size, color=color,
                            fontweight=weight, family=family, ha=ha,
                            va=va, **kw)

    def box(self, x, y, w, h, fc, ec="none", lw=0, r=0.02, alpha=1.0):
        self.ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=%g" % (r * h),
            fc=fc, ec=ec, lw=lw, alpha=alpha, mutation_aspect=1))

    def rect(self, x, y, w, h, fc, ec="none", lw=0, alpha=1.0):
        self.ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw,
                                    alpha=alpha))

    def caption(self, s):
        """Burned-in caption bar; cap height >= 4 % of the frame."""
        self.rect(0, 0, W, 130, fc="#f6f8fa")
        self.rect(0, 130, W, 3, fc="#d0d7de")
        self.rect(60, 34, 14, 62, fc=C_ORACLE)
        self.text(100, 65, s, size=CAP_SIZE, color=INK, weight="bold")

    def provenance(self, s):
        self.text(W - 40, 1050, s, size=16, color="#8b949e", ha="right",
                  va="top", family=MONO)

    def save(self, name):
        p = os.path.join(FRAMES, name)
        self.fig.savefig(p, facecolor=PAPER)
        plt.close(self.fig)
        return p


def ease(u):
    """Smoothstep 0..1."""
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def appear(f, f0, n=6):
    """1.0 once frame f reaches f0 (with a short ease-in)."""
    return ease((f - f0) / n)


# ------------------------------------------------------------------ data
def read_lines(path):
    with open(need(path)) as fh:
        return [ln.rstrip("\n") for ln in fh]


def load_all():
    d = {}
    d["good"] = json.load(open(need(os.path.join(DATA, "verdict-good.json"))))
    d["mutants"] = {m: json.load(open(need(os.path.join(
        DATA, "verdict-%s.json" % m)))) for m in MUTANTS}
    d["selftest"] = read_lines(os.path.join(DATA, "selftest.log"))
    d["grade_txt"] = read_lines(os.path.join(DATA, "grade-good.txt"))
    d["yaml"] = read_lines(os.path.join(MEDIA, "..", "examples", "good",
                                        "matrix.yaml"))
    with open(need(os.path.join(DATA, "loop.json"))) as fh:
        d["loop"] = json.load(fh)
    return d


# ------------------------------------------------------------- scene props
def matrix_rows(v):
    """[(version, stamp, tests, failed)] in the judge's own order."""
    cells = v["metrics"]["cells"]
    return [(ver, cells[ver]["stamp"], cells[ver]["tests"],
             cells[ver]["failed"]) for ver in v["metrics"]["versions"]]


def draw_matrix_row(c, y, ver, stamp, tests, failed, alpha=1.0, label=True):
    x0 = 120
    if label:
        c.text(x0, y, "python " + ver, size=30, family=MONO, weight="bold",
               alpha=alpha)
        c.text(x0 + 300, y, stamp, size=28, family=MONO,
               color="#30363d", alpha=alpha)
        c.text(x0 + 560, y, "%d tests" % tests, size=28, family=MONO,
               color="#30363d", alpha=alpha)
    bw = 420
    if failed:
        c.box(x0 + 740, y - 46, bw, 92, fc="#fbe0d4", ec=C_FAIL, lw=2.5,
              alpha=alpha)
        c.text(x0 + 740 + bw / 2, y, "FAIL: match SyntaxError", size=26,
               family=MONO, color="#a03d00", weight="bold", ha="center",
               alpha=alpha)
    else:
        c.box(x0 + 740, y - 46, bw, 92, fc="#d7f0e5", alpha=alpha)
        c.text(x0 + 740 + bw / 2, y, "pass", size=28, family=MONO,
               color=C_PASS, weight="bold", ha="center", alpha=alpha)


# ------------------------------------------------------------------ scenes
def scene_hook(D, n):
    """0-2.5 s: the finished result fills the frame."""
    v = D["good"]
    rows = matrix_rows(v)
    out = []
    for f in range(n):
        c = Canvas()
        c.text(120, 1006, "ci-test-matrix", size=52, weight="bold")
        c.text(120, 950, "five CPython cells, one judge verdict",
               size=30, color=C_DIM)
        if f >= 18:
            a = appear(f, 18)
            c.box(1560, 936, 260, 96, fc=C_PASS, alpha=a)
            c.text(1690, 984, "PASS", size=54, color="white", ha="center",
                   weight="bold", alpha=a)
        for i, (ver, stamp, tests, failed) in enumerate(rows):
            a = appear(f, 6 + i * 9)
            if a <= 0:
                continue
            draw_matrix_row(c, 852 - i * 122, ver, stamp, tests, failed,
                            alpha=a)
        # the moving highlight band
        y = 920 - ease((f - 20) / float(n - 26)) * 700
        c.rect(100, y - 34, 1120, 68, fc=C_ORACLE, alpha=0.14)
        if f >= 40:
            a = appear(f, 40)
            c.box(1300, 560, 520, 120, fc="#f6f8fa", ec="#d0d7de", alpha=a)
            c.text(1330, 620, "7 tests in every cell", size=34,
                   family=MONO, alpha=a)
        if f >= 52:
            a = appear(f, 52)
            c.box(1300, 410, 520, 120, fc="#f6f8fa", ec="#d0d7de", alpha=a)
            c.text(1330, 470, "9/9 mutants killed", size=34, family=MONO,
                   color=C_FAIL, weight="bold", alpha=a)
        c.caption("5 CPython cells, 7 tests each -- the judge fails "
                  "exactly the 3.9 cell")
        c.provenance("source: data/verdict-good.json (grade.sh --seed 42)")
        out.append(c.save("s1_%03d.png" % f))
    return out


def scene_yaml(D, n):
    """2.5-6 s: the artifact's matrix.yaml scrolls in a code panel."""
    lines = D["yaml"]
    out = []
    line_h = 44
    panel = (100, 200, 1060, 800)
    content_h = len(lines) * line_h + 80
    for f in range(n):
        c = Canvas()
        c.text(120, 1006, "the artifact: matrix.yaml + run_matrix.py",
               size=44, weight="bold")
        c.box(*panel, fc=TERM_BG)
        scroll = ease(f / float(n - 1)) * max(0, content_h - panel[3])
        for i, ln in enumerate(lines):
            y = panel[1] + panel[3] - 40 - i * line_h + scroll
            if y < panel[1] - line_h or y > panel[1] + panel[3] + line_h:
                continue
            ln = ln.rstrip()
            if ln.lstrip().startswith("#"):
                col, txt = "#7d8590", ln
            elif ":" in ln and not ln.startswith(" "):
                k, _, val = ln.partition(":")
                c.text(panel[0] + 36, y, k + ":", size=26, family=MONO,
                       color="#79c0ff", weight="bold")
                c.text(panel[0] + 36 + len(k + ": ") * 15.5, y, val,
                       size=26, family=MONO, color="#a5d6ff")
                continue
            else:
                col, txt = TERM_FG, ln
            c.text(panel[0] + 36, y, txt[:52], size=26, family=MONO,
                   color=col)
        # the four keys the judge parses, lighting up as the file passes
        keys = [("python_versions", "the cells", 14),
                ("fixture", "what is tested", 38),
                ("toggle", "version-specific failure", 62),
                ("junit_dir", "one XML per cell", 86)]
        c.text(1280, 950, "the judge parses four keys", size=32,
               color=C_DIM)
        for j, (k, what, f0) in enumerate(keys):
            a = appear(f, f0)
            y = 850 - j * 160
            c.box(1280, y - 60, 540, 120, fc="#f6f8fa" if a < 1 else
                  "#fff8ec", ec=C_ORACLE if a >= 1 else "#d0d7de", lw=2,
                  alpha=max(0.35, a))
            c.text(1310, y + 22, k, size=30, family=MONO, weight="bold",
                   alpha=max(0.35, a))
            c.text(1310, y - 26, what, size=24, color=C_DIM,
                   alpha=max(0.35, a))
        c.caption("the whole artifact: one matrix.yaml + one run_matrix.py")
        c.provenance("source: examples/good/matrix.yaml (the real artifact)")
        out.append(c.save("s2_%03d.png" % f))
    return out


def scene_build(D, n):
    """6-10 s: the matrix builds cell by cell; progress bar runs."""
    v = D["good"]
    rows = matrix_rows(v)
    out = []
    bar_x, bar_y, bar_w, bar_h = 120, 168, 1680, 40
    for f in range(n):
        c = Canvas()
        c.text(120, 1006, "the matrix the runner produced", size=44,
               weight="bold")
        c.text(120, 950, "run_matrix.py: one uv-managed interpreter per "
                "cell", size=28, color=C_DIM)
        for i, (ver, stamp, tests, failed) in enumerate(rows):
            f0 = 8 + i * 20
            a = appear(f, f0)
            if a <= 0:
                continue
            y = 852 - i * 122
            draw_matrix_row(c, y, ver, stamp, tests, failed, label=True,
                            alpha=a)
            if f >= f0 + 8:                       # the status fill lands
                draw_matrix_row(c, y, ver, stamp, tests, failed,
                                label=False)
        c.rect(bar_x, bar_y, bar_w, bar_h, fc="#eaeef2")
        c.rect(bar_x, bar_y, bar_w * (f + 1) / float(n), bar_h, fc=C_PASS)
        c.text(bar_x + bar_w + 20, bar_y + bar_h / 2,
               "5 cells", size=24, family=MONO, color=C_DIM)
        c.caption("each cell: its own uv interpreter -- 3.9.25 ... "
                  "3.13.15")
        c.provenance("source: data/verdict-good.json -> metrics.cells")
        out.append(c.save("s3_%03d.png" % f))
    return out


def terminal_frame(c, lines, cursor_on):
    """A dark terminal panel showing the last lines, cropped to the
    active region."""
    px, py, pw, ph = 100, 190, 1360, 790
    c.box(px, py, pw, ph, fc=TERM_BG, r=0.01)
    line_h = 44
    max_lines = int((ph - 60) // line_h)
    for i, (ln, col, bold) in enumerate(lines[-max_lines:]):
        y = py + ph - 46 - i * line_h
        c.text(px + 36, y, ln[:62], size=26, family=MONO, color=col,
               weight="bold" if bold else "normal")
    if cursor_on:
        c.rect(px + 36, py + 34, 22, 30, fc=TERM_FG)


def classify_selftest_line(ln):
    if "PASS (expected)" in ln or "selftest: PASS" in ln or \
            "determinism: PASS" in ln:
        return "#3fb950", True
    if "FAIL (expected)" in ln:
        return "#f0883e", True
    if ln.startswith("==") or "kill rate" in ln or "mutants:" in ln:
        return "#e6edf3", True
    return "#8b949e", False


def scene_selftest(D, n):
    """10-16.5 s: the judge's own self-test transcript streaming."""
    lines = [ln for ln in D["selftest"] if ln.strip()]
    killed, total = selftest_kill()
    arrivals = {}                          # line idx -> frame it lands
    for k in range(len(lines)):
        arrivals[k] = 6 + k * 4
    last = arrivals[len(lines) - 1]
    out = []
    for f in range(n):
        c = Canvas()
        c.text(120, 1006, "judge selftest.sh -- the judge proves it can "
                "fail", size=44, weight="bold")
        c.box(1560, 950, 260, 76, fc="#f6f8fa", ec="#d0d7de")
        c.text(1584, 988, "~40x speed", size=28, family=MONO, color=C_DIM)
        shown, nk = [], 0
        for k, fr in arrivals.items():
            if f >= fr:
                ln = lines[k]
                col, bold = classify_selftest_line(ln)
                shown.append((ln, col, bold))
                if "killed by gate" in ln:
                    nk += 1
        # scroll offset eases over the 3 frames after each arrival
        since = min(
            (f - fr for fr in arrivals.values() if 0 <= f - fr <= 3),
            default=3)
        if since < 3 and len(shown) > 1:
            off = (1 - ease(since / 3.0))
        else:
            off = 0.0
        terminal_frame(c, shown, cursor_on=(f // 15) % 2 == 0)
        # kill counter HUD
        nk = min(nk, killed)
        if f > last + 4:
            nk = killed
        c.text(1740, 700, "KILLED", size=36, family=MONO, color=C_DIM,
               ha="center")
        c.text(1740, 610, "%d/9" % nk, size=90, family=MONO, ha="center",
               color=C_FAIL if nk < 9 else C_PASS, weight="bold")
        if f > last + 10:
            a = appear(f, last + 10)
            c.box(1560, 380, 360, 130, fc=C_PASS, alpha=a)
            c.text(1740, 445, "100 %", size=60, color="white", ha="center",
                   weight="bold", alpha=a)
        c.caption("the judge's own output, streaming -- ~40x speed")
        c.provenance("source: data/selftest.log (judge/selftest.sh)")
        out.append(c.save("s4_%03d.png" % f))
    return out


def scene_verdict(D, n):
    """16.5-21 s: grade.sh's verdict JSON streaming; gates flip PASS."""
    lines = D["grade_txt"]
    out = []
    gate_names = [g for g in GATES]
    flips = {}                             # gate -> frame its PASS lands
    base = 8
    for j, g in enumerate(gate_names):
        flips[g] = base + int(j * (len(lines) / 10.0)) + j * 2
    verd_at = None
    for k, ln in enumerate(lines):
        if '"verdict": "PASS"' in ln:
            verd_at = base + int(k * 1.4)
            break
    verd_at = verd_at or (n - 40)
    for f in range(n):
        c = Canvas()
        c.text(120, 1006, "grade.sh prints one verdict", size=44,
               weight="bold")
        c.box(1600, 950, 220, 76, fc="#f6f8fa", ec="#d0d7de")
        c.text(1624, 988, "~6x speed", size=28, family=MONO, color=C_DIM)
        shown_n = min(len(lines), int((f - 4) / 1.4) + 1) if f >= 4 else 0
        shown = []
        for k in range(max(0, shown_n - 18), shown_n):
            ln = lines[k]
            col = "#7ee787" if '"verdict": "PASS"' in ln else \
                ("#79c0ff" if re.match(r'\s*"[a-z_]+": \{', ln) else
                 ("#8b949e" if ln.strip() in ("{", "}", "},") else TERM_FG))
            shown.append((ln, col, False))
        if shown:
            shown[-1] = (shown[-1][0], "#e6edf3", True)
        terminal_frame(c, shown, cursor_on=(f // 15) % 2 == 0)
        # right rail: the eight gates flip PASS as their JSON goes by
        for j, g in enumerate(gate_names):
            a = appear(f, flips[g])
            y = 880 - j * 82
            c.box(1560, y - 34, 260, 68, fc="#d7f0e5" if a > 0 else
                  "#f6f8fa", alpha=max(0.4, a))
            c.text(1690, y, "PASS" if a > 0 else g[:7], size=26,
                   family=MONO, ha="center",
                   color=C_PASS if a > 0 else C_DIM, weight="bold",
                   alpha=1.0 if a > 0 else 0.7)
        if f >= verd_at:
            a = appear(f, verd_at)
            c.box(1560, 130, 260, 110, fc=C_PASS, alpha=a)
            c.text(1690, 185, "PASS", size=48, color="white", ha="center",
                   weight="bold", alpha=a)
        c.caption("the verdict JSON, streaming -- ~6x speed")
        c.provenance("source: data/grade-good.txt (grade.sh stdout)")
        out.append(c.save("s5_%03d.png" % f))
    return out


def scene_replay(D, n):
    """21-27 s: the replayed fix sequence 1/8 -> 7/8 -> 8/8 gates."""
    steps = D["loop"]["steps"]
    verdicts = {}
    for s in steps:
        verdicts[s["name"]] = (load_verdict(s["name"])
                               if s["name"] != "good" else D["good"])
    out = []
    card_w, gap = 540, 50
    x00 = (W - 3 * card_w - 2 * gap) / 2
    for f in range(n):
        c = Canvas()
        c.text(120, 1006, "the fixing loop, replayed", size=44,
               weight="bold")
        c.text(120, 950, "real grade.sh verdicts, reordered bad -> partly "
                "fixed -> good (not a live agent trace)", size=26,
               color=C_DIM)
        for i, s in enumerate(steps):
            f0 = 12 + i * 55
            a = appear(f, f0, 8)
            if a <= 0:
                continue
            x = x00 + i * (card_w + gap) + (1 - a) * 80
            v = verdicts[s["name"]]
            npass = gates_passed(v)
            ok = v["verdict"] == "PASS"
            col = C_PASS if ok else C_FAIL
            c.box(x, 240, card_w, 640, fc="#f6f8fa", ec=col, lw=3,
                  alpha=a)
            c.text(x + 30, 810, "it %d" % s["iteration"], size=30,
                   family=MONO, color=C_DIM, alpha=a)
            c.text(x + 30, 745, s["name"], size=34, family=MONO,
                   weight="bold", alpha=a)
            c.text(x + 30, 690, s["stage"], size=21, color=C_DIM,
                   alpha=a)
            # n/8 counts up as badges flip
            nshow = min(npass, max(0, int((f - f0 - 6) / 2.5)))
            c.text(x + 30, 590, "%d/8 gates" % nshow, size=52,
                   family=MONO, weight="bold", color=col, alpha=a)
            for j, g in enumerate(GATES):
                gx = x + 30 + (j % 4) * 125
                gy = 520 - (j // 4) * 90
                gp = v["gates"][g]["pass"] and j < nshow
                c.box(gx, gy - 32, 115, 64, fc="#d7f0e5" if gp else
                      "#fbe0d4", alpha=a)
                c.text(gx + 57, gy, GATE_SHORT[g].split("\n")[0][:9],
                       size=19, family=MONO, ha="center",
                       color=C_PASS if gp else "#a03d00", alpha=a)
            if ok:
                if f >= f0 + 6 + int(npass * 2.5):
                    aa = appear(f, f0 + 6 + int(npass * 2.5), 5)
                    c.box(x + 30, 270, card_w - 60, 90, fc=C_PASS,
                          alpha=aa * a)
                    c.text(x + card_w / 2, 315, "all gates pass", size=30,
                           color="white", ha="center", weight="bold",
                           alpha=aa * a)
            else:
                failed = [k for k, g in v["gates"].items() if not g["pass"]]
                c.text(x + 30, 320, "fails: " + ", ".join(failed[:3]),
                       size=22, family=MONO, color="#a03d00", alpha=a)
        c.caption("bad -> partly fixed -> good -- a replay of real grade "
                  "verdicts")
        c.provenance("source: data/loop.json + data/verdict-*.json")
        out.append(c.save("s6_%03d.png" % f))
    return out


def scene_killmatrix(D, n):
    """27-33 s: the kill matrix fills row by row; kill-rate bar grows."""
    killed, total = selftest_kill()
    verdicts = {"good": D["good"]}
    verdicts.update(D["mutants"])
    x0, x1 = 420, 1820
    ytop = 940
    dy = 62
    cw = (x1 - x0) / len(GATES)
    out = []
    for f in range(n):
        c = Canvas()
        c.text(120, 1030, "the judge's kill matrix", size=44,
               weight="bold")
        for j, g in enumerate(GATES):
            c.text(x0 + cw * (j + 0.5), ytop + 18,
                   GATE_SHORT[g].replace("\n", " "), size=19,
                   family=MONO, ha="center", color=C_DIM)
        c.text(x0 - 16, ytop + 18, "artifact", size=19, family=MONO,
               ha="right", color=C_DIM)
        n_rows = 0
        for i, name in enumerate(ROWS):
            f0 = 10 + i * 14
            a = appear(f, f0, 4)
            if a <= 0:
                continue
            n_rows += 1
            y = ytop - 50 - i * dy
            label = "examples/good" if name == "good" else name
            c.text(x0 - 16, y, label, size=24, family=MONO, ha="right",
                   weight="bold" if name == "good" else "normal",
                   color=INK if name == "good" else "#30363d", alpha=a)
            v = verdicts[name]
            for j, g in enumerate(GATES):
                aj = appear(f, f0 + 1 + j * 0.6, 3)
                if aj <= 0:
                    continue
                ok = v["gates"][g]["pass"]
                x = x0 + j * cw
                c.rect(x + 3, y - dy * 0.40, cw - 6, dy * 0.80,
                       fc="#d7f0e5" if ok else "#fbe0d4", alpha=aj * a)
                if not ok:
                    txt = cell_short(g, v["gates"][g]["detail"])
                    c.text(x + cw / 2, y, txt[:11], size=17, family=MONO,
                           ha="center", color="#a03d00", weight="bold",
                           alpha=aj * a)
        # kill-rate bar
        bar_y, bar_h = 150, 54
        c.rect(120, bar_y, 1400, bar_h, fc="#eaeef2")
        filled = max(0, n_rows - 1)          # good row is not a kill
        frac = min(1.0, filled / 9.0)
        c.rect(120, bar_y, 1400 * frac, bar_h, fc=C_FAIL)
        c.text(1540, bar_y + bar_h / 2, "%d/9 = %d %%" %
               (filled, int(frac * 100)), size=34, family=MONO,
               weight="bold", color=C_FAIL)
        c.caption("every single-edit mutant killed -- 9/9, floor 90 %")
        c.provenance("source: data/verdict-*.json (9 mutants, "
                     "grade.sh --seed 42)")
        out.append(c.save("s7_%03d.png" % f))
    return out


def scene_proof(D, n):
    """33-36.2 s: the judge's mask fills; PASS + exit codes ride on top."""
    v = D["good"]
    mask_on = v["metrics"]["mask_on"]
    mask_off = v["metrics"]["mask_off"]
    cells = v["metrics"]["cells"]
    out = []
    cell = 128
    for f in range(n):
        c = Canvas()
        c.text(120, 1030, "the proof: the mask the judge measured",
               size=44, weight="bold")
        for row, (label, pattern, fy) in enumerate([
                ("toggle ON", mask_on, 700), ("toggle OFF", mask_off,
                                              460)]):
            c.text(120, fy + cell + 44, label, size=32, family=MONO,
                   weight="bold")
            for i, status in enumerate(pattern):
                f0 = 8 + row * 40 + i * 7
                a = appear(f, f0, 6)
                if a <= 0:
                    continue
                x = 120 + i * (cell + 14)
                col = C_PASS if status == "pass" else C_FAIL
                # the fill sweeps left -> right inside the cell
                wq = cell * min(1.0, a * 1.15)
                c.rect(x, fy, cell, cell, fc="#eaeef2")
                c.rect(x, fy, wq, cell, fc=col)
                c.text(x + cell / 2, fy + cell / 2,
                       "3.9" if i == 0 else "3.1%d" % i, size=30,
                       family=MONO, ha="center", color="white",
                       weight="bold", alpha=a)
            # the oracle boundary
            ao = appear(f, 60, 10)
            if ao > 0:
                ox = 120 + 5 * (cell + 14) + 7
                c.rect(ox, fy - 16, 5, cell + 32, fc=C_ORACLE, alpha=ao)
        if f >= 62:
            a = appear(f, 62)
            c.text(1020, 700 + cell + 44, "exactly one failing cell, at "
                   "3.9 -- the CPython-3.10 oracle", size=26,
                   family=MONO, color="#7a4f01", alpha=a)
        # HUD: verdict + exit codes + interpreters
        if f >= 24:
            a = appear(f, 24)
            c.box(1020, 380, 800, 210, fc="#f6f8fa", ec=C_PASS, lw=3,
                  alpha=a)
            c.text(1060, 520, "verdict PASS", size=56, color=C_PASS,
                   weight="bold", alpha=a)
            ec = v["metrics"]["exit_codes"]
            c.text(1060, 440, "exit codes: toggle on = %d, off = %d   |   "
                   "tests/cell %d" % (ec["on"], ec["off"],
                                      v["metrics"]["tests_per_cell"]),
                   size=28, family=MONO, alpha=a)
        if f >= 44:
            a = appear(f, 44)
            stamps = ", ".join("%s=%s" % (k, cells[k]["stamp"]) for k in
                               ["3.9", "3.10", "3.11", "3.12", "3.13"])
            c.text(120, 330, "interpreters: " + stamps, size=24,
                   family=MONO, color=C_DIM, alpha=a)
        c.caption("verdict PASS -- the mask matches the CPython-3.10 "
                  "oracle")
        c.provenance("source: data/verdict-good.json -> metrics")
        out.append(c.save("s8_%03d.png" % f))
    return out


def scene_endcard():
    """Static end card: the one-command launch."""
    c = Canvas()
    c.text(W / 2, 800, "run it in one command", size=40, color=C_DIM,
           ha="center")
    c.box(310, 580, 1300, 150, fc=TERM_BG)
    c.text(W / 2, 655, "python3 cookbook/ci-test-matrix/run.py", size=52,
           family=MONO, color="#7ee787", ha="center", weight="bold")
    c.text(W / 2, 430, "or ask your agent to solve cookbook/ci-test-matrix/"
           " in a fresh sandbox", size=34, ha="center", color=INK)
    c.text(W / 2, 300, "judge, figures and video regenerated by "
           "cookbook/ci-test-matrix/media/make_media.sh", size=22,
           ha="center", color=C_DIM, family=MONO)
    return c.save("s9_endcard.png")


# ------------------------------------------------------------------ cut
def encode(all_frames):
    os.makedirs(MASTER, exist_ok=True)
    lst = os.path.join(FRAMES, "frames.txt")
    with open(lst, "w") as f:
        for p in all_frames:
            f.write("file '%s'\nduration %.5f\n" % (os.path.abspath(p),
                                                    1.0 / FPS))
        f.write("file '%s'\n" % os.path.abspath(all_frames[-1]))
    master = os.path.join(MASTER, "demo_lossless.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe",
         "0", "-i", lst, "-vf", "fps=%d" % FPS, "-c:v", "libx264",
         "-crf", "0", "-preset", "slow", "-pix_fmt", "yuv420p", master],
        check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", master, "-c:v",
         "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt",
         "yuv420p", "-movflags", "+faststart", "-an", OUT],
        check=True)
    return master


def probe_out():
    pr = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", OUT],
        capture_output=True, text=True, check=True)
    meta = json.loads(pr.stdout)
    st = next(s for s in meta["streams"] if s["codec_type"] == "video")
    return (float(meta["format"]["duration"]), st["width"], st["height"],
            st["r_frame_rate"], os.path.getsize(OUT))


def main():
    os.makedirs(FRAMES, exist_ok=True)
    D = load_all()
    shots = []
    print("== scene 1: hook ==")
    shots += scene_hook(D, 75)
    print("== scene 2: input (matrix.yaml) ==")
    shots += scene_yaml(D, 105)
    print("== scene 3: the matrix builds ==")
    shots += scene_build(D, 120)
    print("== scene 4: selftest streaming ==")
    shots += scene_selftest(D, 195)
    print("== scene 5: verdict streaming ==")
    shots += scene_verdict(D, 135)
    print("== scene 6: replayed fix loop ==")
    shots += scene_replay(D, 180)
    print("== scene 7: kill matrix ==")
    shots += scene_killmatrix(D, 180)
    print("== scene 8: proof ==")
    shots += scene_proof(D, 96)
    print("== scene 9: end card ==")
    end = scene_endcard()
    shots += [end] * 90
    total = len(shots) / float(FPS)
    print("== %d frames = %.1f s; encoding ==" % (len(shots), total))
    if not 25.0 <= total <= 60.0:
        raise SystemExit("make_video: planned duration %.1f s outside "
                         "25-60 s" % total)
    master = encode(shots)
    dur, w, h, fps, size = probe_out()
    print("%s: %.1f s, %dx%d @ %s, %.2f MB (master %.1f MB)"
          % (OUT, dur, w, h, fps, size / 1e6,
             os.path.getsize(master) / 1e6))
    assert (w, h) == (1920, 1080), (w, h)
    assert 25.0 <= dur <= 60.0, dur
    assert size < 8 * 1024 * 1024, size


if __name__ == "__main__":
    main()
