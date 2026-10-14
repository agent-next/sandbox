"""Shared bits for the control-tuning demo media.

Every number the figures show is read here from a judge output file under
media/data/ (verdict JSONs and --trace CSVs written by judge/grade.sh during
the replay run); nothing is synthesised. A missing file is a hard error.

Palette: the validated dataviz reference palette (light mode) - categorical
blue/orange/aqua, status good/critical, recessive gray chrome.
"""

import csv
import json
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.dirname(HERE)
DATA = os.path.join(MEDIA, "data")
MASTER = os.path.join(MEDIA, "master")

# --- validated palette (dataviz reference, light mode) -------------------
BLUE = "#2a78d6"       # categorical slot 1 - the good controller
ORANGE = "#eb6834"     # categorical slot 2 - the failed candidates
AQUA = "#1baf7a"       # categorical slot 3 - reserved
GOOD = "#0ca30c"       # status: pass
CRIT = "#d03b3b"       # status: fail
INK = "#0b0b0b"        # primary text
INK2 = "#52514e"       # secondary text
MUTED = "#898781"      # axis labels
GRID = "#e1e0d9"       # hairline gridlines
AXIS = "#c3c2b7"       # baseline
SURFACE = "#fcfcfb"    # chart surface

# --- spec constants (judge/judge_lib.py, fixed by SPEC.md) ----------------
F_MAX = 10.0        # N, actuator limit (|F| <= 10)
TAU_MAX = 1.0       # N m, actuator limit (|tau| <= 1)
THETA0 = 0.15       # rad, scenario-1 lean initial condition
S1_THETA_BAND = 0.02 * THETA0   # rad, 2 % settling band, scenario 1
S1_X_BAND = 0.01                 # m, settling band, scenario 1
S2_X_BAND = 0.02                 # m, settling band, scenario 2
S1_SETTLE_MAX = 5.0  # s, settling limit, scenario 1
S2_SETTLE_MAX = 7.0  # s, settling limit, scenario 2
S2_THETA_PEAK_MAX = 0.5          # rad, "never falls over", scenario 2
MC_X_SETTLE_MAX = 7.0            # s, per-sample x settling limit (MC)
MC_THETA_SETTLE_MAX = 8.0        # s, per-sample theta settling limit (MC)
MC_FRACTION_MIN = 0.95           # gate 6 pass fraction


def die(msg):
    sys.exit(f"make_media: {msg}")


def require(relpath):
    """Absolute path to a required media/data file; hard-fail if missing."""
    p = os.path.join(DATA, relpath)
    if not os.path.isfile(p):
        die(f"missing judge output {relpath} - regenerate it with "
            "media/regen_data.sh (grades the committed examples with "
            "judge/grade.sh --trace media/data/<name>)")
    return p


def verdict(name):
    """The verdict dict a judge run wrote for candidate <name>."""
    with open(require(f"{name}/verdict.json"), encoding="utf-8") as fh:
        return json.load(fh)


def trace(name, scenario):
    """Columns of one simulation trace the judge dumped via --trace.

    scenario is 1 or 2. Returns (t, x, xdot, theta, thetadot, F, tau).
    """
    path = require(f"{name}/s{scenario}_trace.csv")
    cols = [[] for _ in range(7)]
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0].startswith("t_s"):
                continue
            for i, v in enumerate(row):
                cols[i].append(float(v))
    return tuple(cols)


def mc_samples(name):
    """Rows of mc_samples.csv: (sample, M, m, l, theta_settle, x_settle, ok)."""
    rows = []
    with open(require(f"{name}/mc_samples.csv"), encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0] == "sample":
                continue
            rows.append((int(row[0]), *(float(v) for v in row[1:6]),
                         int(row[6])))
    return rows


def rc_params():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "figure.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
    })
    return plt


def style_axis(ax):
    """Recessive chrome: hairline solid grid, muted ticks, no top spines."""
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=1.0, linestyle="-", zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(1.0)
    ax.tick_params(colors=MUTED, labelsize=11, length=4)


def caption(fig, text, width=160):
    """Figure caption in secondary ink, bottom-left under everything.

    Wrapped to `width` chars per line so it can never run off the figure's
    right edge (check_layout verifies the result).
    """
    fig.text(0.012, 0.010, "\n".join(textwrap.wrap(text, width)),
             fontsize=10.2, color=INK2, ha="left", va="bottom")


def check_layout(fig, pad=1.0, min_overlap=2.0):
    """Layout gate: fail the build on clipped or colliding text.

    Every text artist (titles, axis labels, tick labels, annotations,
    in-axes notes, figure caption) and every legend must lie fully inside
    the figure canvas; no two text bounding boxes, and no text/legend
    pair, may overlap by more than `min_overlap` px in both directions.
    Call after the figure is fully populated, before savefig.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fw, fh = fig.canvas.get_width_height()
    problems = []

    def short(t):
        s = t.get_text().replace("\n", "\\n")
        return s[:50] + "..." if len(s) > 50 else s

    def in_view(axis_obj, locs_getter):
        lo, hi = sorted(axis_obj.get_view_interval())
        eps = (hi - lo) * 1e-4
        return [lo - eps <= loc <= hi + eps for loc in locs_getter()]

    artists = [(f"figure text", t) for t in fig.texts]
    suptitle = getattr(fig, "_suptitle", None)
    if suptitle is not None and all(t is not suptitle for _, t in artists):
        artists.append(("suptitle", suptitle))
    legends = []
    for i, ax in enumerate(fig.axes):
        artists.append((f"ax{i} title", ax.title))
        artists.append((f"ax{i} xlabel", ax.xaxis.label))
        artists.append((f"ax{i} ylabel", ax.yaxis.label))
        # tick labels outside the view interval are culled at draw time
        for keep, t in zip(in_view(ax.xaxis, ax.get_xticks),
                           ax.get_xticklabels()):
            if keep:
                artists.append((f"ax{i} xtick", t))
        for keep, t in zip(in_view(ax.yaxis, ax.get_yticks),
                           ax.get_yticklabels()):
            if keep:
                artists.append((f"ax{i} ytick", t))
        artists.extend((f"ax{i} text", t) for t in ax.texts)
        leg = ax.get_legend()
        if leg is not None:
            legends.append((f"ax{i} legend", leg.get_window_extent(renderer)))

    seen = set()
    artists = [(n, t) for n, t in artists
               if not (id(t) in seen or seen.add(id(t)))]

    def inside(bb):
        return (bb.x0 >= -pad and bb.y0 >= -pad
                and bb.x1 <= fw + pad and bb.y1 <= fh + pad)

    def overlap(a, b):
        iw = min(a.x1, b.x1) - max(a.x0, b.x0)
        ih = min(a.y1, b.y1) - max(a.y0, b.y0)
        return iw > min_overlap and ih > min_overlap

    boxes = []
    for name, t in artists:
        if not t.get_visible() or not t.get_text().strip():
            continue
        bb = t.get_window_extent(renderer)
        label = f'{name} "{short(t)}"'
        boxes.append((label, bb))
        if not inside(bb):
            problems.append(
                f"clipped: {label} bbox ({bb.x0:.0f},{bb.y0:.0f})-"
                f"({bb.x1:.0f},{bb.y1:.0f}) escapes {fw:.0f}x{fh:.0f} canvas")
    for name, bb in legends:
        if not inside(bb):
            problems.append(
                f"clipped: {name} bbox ({bb.x0:.0f},{bb.y0:.0f})-"
                f"({bb.x1:.0f},{bb.y1:.0f}) escapes {fw:.0f}x{fh:.0f} canvas")
    def fmt(bb):
        return f"({bb.x0:.0f},{bb.y0:.0f})-({bb.x1:.0f},{bb.y1:.0f})"

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if overlap(boxes[i][1], boxes[j][1]):
                problems.append(f"overlap: {boxes[i][0]} {fmt(boxes[i][1])}"
                                f" vs {boxes[j][0]} {fmt(boxes[j][1])}")
    for label, bb in boxes:
        for lname, lb in legends:
            if overlap(bb, lb):
                problems.append(f"overlap: {label} {fmt(bb)}"
                                f" vs {lname} {fmt(lb)}")

    if problems:
        for p in problems:
            print(f"layout-check: {p}", file=sys.stderr)
        die(f"layout check failed: {len(problems)} problem(s)")
