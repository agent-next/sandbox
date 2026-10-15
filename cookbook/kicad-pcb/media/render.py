#!/usr/bin/env python3
"""Rebuild every media/ figure and video frame from media/data/.

All pixels come from real artifacts:
  * board / schematic images are produced by the pinned kicad-cli
    (`pcb render` for the 3D view, `pcb export svg` / `sch export svg`
    rasterised with PyMuPDF for the 2D views),
  * every number, verdict and marker coordinate is read from the judge
    verdict JSONs and the raw ERC/DRC reports in media/data/.

Marker placement: `sch export svg` and `pcb export svg
--page-size-mode 1` emit coordinates in the same mm space as the
.kicad_sch / .kicad_pcb sources, so ERC/DRC item positions map 1:1
(ERC item positions are mm/100 — verified against the shipped KiCad
demos and this project's flag coordinates).

Layout safety: check_layout() rasterises each figure and fails loudly
if any text is clipped by the canvas or overlaps another text.
"""

import json
import os
import re
import shutil
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                    # noqa: E402
import numpy as np                                 # noqa: E402
import pymupdf                                     # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")
MASTER = os.path.join(HERE, "master")
FRAMES = os.path.join(MASTER, "frames")
MUT_DIR = os.path.join(DATA, "mutants")
GOOD_DIR = os.path.join(DEMO, "examples", "good", "555-blinker")
SCH_NAME = "555-blinker.kicad_sch"
PCB_NAME = "555-blinker.kicad_pcb"

sys.path.insert(0, os.path.join(DEMO, "judge"))
from oracle import edge_cuts_points                # noqa: E402
import mutants as mut_mod                          # noqa: E402

# Okabe-Ito colour-blind-safe palette
C = {"pass": "#009E73", "fail": "#D55E00", "mark": "#D55E00",
     "ink": "#1a1a1a", "mut": "#0072B2", "chip": "#E69F00"}

GATE_ORDER = ["G1_erc", "G2_drc", "G3_netlist",
              "G4_outline", "G5_gerber", "G6_drill", "G7_limits"]
GATE_SHORT = {"G1_erc": "G1 ERC", "G2_drc": "G2 DRC", "G3_netlist": "G3 netlist",
              "G4_outline": "G4 outline", "G5_gerber": "G5 gerbers",
              "G6_drill": "G6 drill", "G7_limits": "G7 limits"}

# mutants that change the schematic vs the board (detected by diffing)
PT_PER_MM = 72.0 / 25.4


# ------------------------------------------------------------ data helpers --

def load(name):
    return json.load(open(os.path.join(DATA, name + ".json")))


def mutant_names():
    return sorted(d for d in os.listdir(MUT_DIR)
                  if os.path.isdir(os.path.join(MUT_DIR, d)))


def proj_dir(name):
    return GOOD_DIR if name == "good" else os.path.join(MUT_DIR, name)


def sch_changed(name):
    a = open(os.path.join(GOOD_DIR, SCH_NAME)).read()
    b = open(os.path.join(proj_dir(name), SCH_NAME)).read()
    return a != b


def mutant_blurb(name):
    """First line of the mutant's docstring — the reviewed description
    of the single edit."""
    fn = mut_mod.MUTANTS[name]
    para = " ".join((fn.__doc__ or "").strip().split("\n\n")[0].split())
    if len(para) > 100:               # keep the first whole clause
        cut = [i for i in (para.find(": "), para.find(". ")) if i > 0]
        para = para[:min(cut)] if cut else para
    return para


def fail_metric(gate, det):
    """Short measured-value string for a FAILED gate cell."""
    if gate == "G1_erc":
        short = {"endpoint_off_grid": "off grid",
                 "pin_not_connected": "pin unconn.",
                 "pin_to_pin": "pin to pin"}
        if det.get("erc_errors"):
            et = ",".join(short.get(t, t[:12])
                          for t in det.get("error_types", {})) or "error"
            return f"errors={det['erc_errors']}\n{et}"
        bad = det.get("warning_types_not_allowed", {})
        return "warn " + ",".join(f"{short.get(t, t[:12])} x{n}"
                                  for t, n in bad.items())
    if gate == "G2_drc":
        return (f"viol={det.get('drc_violations', 0)}\n"
                f"unconn={det.get('drc_unconnected_items', 0)}")
    if gate == "G3_netlist":
        top = []
        if det.get("only_in_sch") or det.get("only_in_pcb"):
            top.append(f"nets sch+{len(det.get('only_in_sch') or [])}"
                       f"/pcb+{len(det.get('only_in_pcb') or [])}")
        if det.get("unrouted_items"):
            top.append(f"unrouted={det['unrouted_items']}")
        bits = [" ".join(top)] if top else []
        low = []
        if det.get("member_mismatch"):
            low.append("pins: " + ",".join(list(det["member_mismatch"])[:3]))
        if det.get("floating_pins"):
            low.append(f"float={det['floating_pins']}")
        if low:
            bits.append(" ".join(low))
        return "\n".join(bits) if bits else "nets differ"
    if gate == "G4_outline":
        return f"open={det.get('open_endpoints', '?')}\nclosed={det.get('closed')}"
    if gate == "G5_gerber":
        ext = det.get("extents_mm")
        if isinstance(ext, dict):
            return f"dmax={ext['max_delta_mm']}mm"
        for lay, r in det.items():
            if isinstance(r, dict) and (r.get("apertures") == 0
                                        or r.get("ops") == 0):
                return f"{lay}\n0 geo"
            if r == "missing":
                return f"{lay}\nmissing"
        return "bad layer"
    if gate == "G6_drill":
        nd = det.get("no_drill_pads", 0) + det.get("no_drill_vias", 0)
        if nd:
            return (f"no drill\npads={det.get('no_drill_pads', 0)} "
                    f"vias={det.get('no_drill_vias', 0)}")
        if det.get("missing_tool_mm"):
            return "no tool for\n" + ",".join(
                f"{d}mm" for d in det["missing_tool_mm"])
        return (f"tools={det.get('tools', 0)}\n"
                f"hits={det.get('drill_hits', 0)}")
    if gate == "G7_limits":
        bits = []
        if not det.get("board_size_ok", True):
            bits.append("size=" + "x".join(
                str(v) for v in det.get("board_size_mm", ["?", "?"])))
        if det.get("netclass_violations"):
            bits.append("netclass\n" + ",".join(
                det["netclass_violations"]))
        return "\n".join(bits) if bits else "limits"
    return "fail"


def gate_row_text(gate, det):
    """One-line measured summary for a gate (used in tables)."""
    if gate == "G1_erc":
        wt = ",".join(det.get("warning_types", {})) or "none"
        return (f"{det.get('erc_errors', 0)} errors, "
                f"{det.get('erc_warnings', 0)} warn ({wt})")
    if gate == "G2_drc":
        return (f"{det.get('drc_violations', 0)} viol, "
                f"{det.get('drc_unconnected_items', 0)} unconn")
    if gate == "G3_netlist":
        return (f"{len(det.get('sch_nets', []))} nets sch==pcb, "
                f"{det.get('unrouted_items', 0)} unrouted")
    if gate == "G4_outline":
        return (f"{'closed' if det.get('closed') else 'OPEN'}; "
                f"{det.get('edge_cuts_items', 0)} items, "
                f"{det.get('open_endpoints', 0)} open")
    if gate == "G5_gerber":
        ext = det.get("extents_mm", {})
        n_ok = sum(1 for k, r in det.items()
                   if isinstance(r, dict) and r.get("apertures", 0) >= 1
                   and r.get("ops", 0) >= 1)
        return (f"{n_ok}/7 layers, extents dmax="
                f"{ext.get('max_delta_mm', '?')} mm")
    if gate == "G6_drill":
        return (f"{det.get('tools', 0)} tools, "
                f"{det.get('drill_hits', 0)}/"
                f"{det.get('expected_holes', '?')} hits, "
                f"{det.get('no_drill_pads', 0) + det.get('no_drill_vias', 0)}"
                " holes w/o drill")
    if gate == "G7_limits":
        size = det.get("board_size_mm", ["?", "?"])
        return (f"board {size[0]}x{size[1]} mm (<= "
                f"{det.get('board_limit_mm', '?')}), "
                f"netclass {'ok' if det.get('netclass_ok') else 'FAIL'}")
    return ""


# ------------------------------------------------------------- kicad-cli ----

def kicad_cli():
    cli = (os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")
           or os.path.expanduser("~/.local/kicad-pcb-demo/bin/kicad-cli"))
    if not os.path.exists(cli) and not shutil.which(cli):
        sys.exit("kicad-cli not found; run judge/setup.sh first")
    return cli


def run(cmd):
    print("  +", " ".join(os.path.basename(c) for c in cmd))
    subprocess.run(cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def render3d(pcb, png, w=1600, h=900):
    run([kicad_cli(), "pcb", "render", pcb, "--side", "top",
         "--width", str(w), "--height", str(h),
         "--quality", "high", "--background", "opaque", "-o", png])
    return png


def board_svg(pcb, svg):
    run([kicad_cli(), "pcb", "export", "svg", pcb,
         "--layers", "F.Cu,B.Cu,F.Silkscreen,Edge.Cuts",
         "--mode-single", "--page-size-mode", "1",
         "--exclude-drawing-sheet", "-o", svg])
    return svg


def sch_svg(sch, outdir):
    os.makedirs(outdir, exist_ok=True)
    run([kicad_cli(), "sch", "export", "svg", sch,
         "--exclude-drawing-sheet", "--no-background-color", "-o", outdir])
    out = os.path.join(outdir, SCH_NAME.replace(".kicad_sch", ".svg"))
    return out


# -------------------------------------------------------- raster helpers ----

def svg_points(svg_path):
    """All (x,y) coordinate pairs used by geometry in a KiCad SVG —
    for content bounding boxes (page-size-mode 1 => mm == file coords)."""
    pts = []
    for m in re.finditer(r'\bd="([^"]*)"', open(svg_path).read()):
        nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", m.group(1))]
        pts += list(zip(nums[0::2], nums[1::2]))
    for m in re.finditer(r'cx="([\d.]+)"\s+cy="([\d.]+)"',
                         open(svg_path).read()):
        pts.append((float(m.group(1)), float(m.group(2))))
    return pts


def sch_text_overlap(svg_path, tag):
    """Fail loudly if two rendered texts in a schematic SVG share
    pixels. KiCad draws text as stroke paths inside
    <g class="stroked-text"> groups whose <desc> is the string, so the
    path coordinates give the true glyph extents (rotation included).
    KiCad emits a few texts twice — identical (string, box) pairs are
    deduped before the pairwise test."""
    text = open(svg_path).read()
    uniq = {}
    for m in re.finditer(
            r'<g class="stroked-text"><desc>([^<]*)</desc>(.*?)</g>',
            text, re.S):
        desc, body = m.groups()
        nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", body)]
        xs, ys = nums[0::2], nums[1::2]
        if not xs:
            continue
        key = (desc, round(min(xs), 2), round(min(ys), 2),
               round(max(xs), 2), round(max(ys), 2))
        uniq[key] = (min(xs), min(ys), max(xs), max(ys), desc)
    boxes = sorted(uniq.values())
    bad = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ax0, ay0, ax1, ay1, sa = boxes[i]
            bx0, by0, bx1, by1, sb = boxes[j]
            ix = min(ax1, bx1) - max(ax0, bx0)
            iy = min(ay1, by1) - max(ay0, by0)
            if ix > 0.05 and iy > 0.05:
                bad.append(f"overlap: {sa!r} vs {sb!r} "
                           f"({ix:.2f}x{iy:.2f}mm)")
    if bad:
        for p in bad:
            print(f"  SCH_TEXT[{tag}] {p}", file=sys.stderr)
        raise SystemExit(f"schematic text overlap in {tag}: "
                         f"{len(bad)} pair(s)")


def rasterize(svg_path, clip_mm, px_target=1600):
    """Rasterise clip_mm=(x0,y0,x1,y1) mm region of a KiCad SVG.
    PyMuPDF page space is points: mm * 72/25.4.
    Returns (numpy RGB image, clip_mm actually used)."""
    x0, y0, x1, y1 = clip_mm
    zoom = px_target / ((x1 - x0) * PT_PER_MM)
    doc = pymupdf.open(svg_path)
    page = doc[0]
    clip = pymupdf.Rect(x0 * PT_PER_MM, y0 * PT_PER_MM,
                        x1 * PT_PER_MM, y1 * PT_PER_MM) & page.rect
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip,
                          alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8)
    img = img.reshape(pix.height, pix.width, pix.n)[:, :, :3].copy()
    doc.close()
    return img, (clip.x0 / PT_PER_MM, clip.y0 / PT_PER_MM,
                 clip.x1 / PT_PER_MM, clip.y1 / PT_PER_MM)


def board_clip(name, margin=6.0):
    """Board Edge.Cuts bbox (+margin) in mm — the region to show."""
    pts = edge_cuts_points(os.path.join(proj_dir(name), PCB_NAME))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) - margin, min(ys) - margin,
            max(xs) + margin, max(ys) + margin)


def sch_clip(svg_path, margin=12.0):
    pts = svg_points(svg_path)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (max(0, min(xs) - margin), max(0, min(ys) - margin),
            min(297.1, max(xs) + margin), min(210.1, max(ys) + margin))


# --------------------------------------------------------------- markers ----

def sch_markers(name):
    """Marker points (sch mm) + label from the raw ERC report."""
    rep = json.load(open(os.path.join(DATA, name + ".erc.json")))
    viols = [v for s in rep.get("sheets", []) for v in s["violations"]]
    pick = [v for v in viols if v.get("severity") == "error"]
    if not pick:                      # e.g. erc_off_grid: warnings only
        pick = [v for v in viols
                if v.get("type") not in ("lib_symbol_issues",)]
    if not pick:
        return [], ""
    v = pick[0]
    pts = [(it["pos"]["x"] * 100.0, it["pos"]["y"] * 100.0)
           for it in v.get("items", []) if "pos" in it]
    label = f"ERC {v['severity']}: {v['type']}"
    return pts, label


def pcb_markers(name):
    """Marker points (board mm) + label from the raw DRC report."""
    rep = json.load(open(os.path.join(DATA, name + ".drc.json")))
    # unconnected_items entries are violation-shaped (nested items) in
    # the KiCad 9 report — merge them so they can be picked too.
    viols = rep.get("violations", []) + rep.get("unconnected_items", [])
    pick = [v for v in viols if v.get("severity") == "error"] or viols
    if pick:
        # prefer the violation with the most marker items
        v = max(pick, key=lambda v: len(v.get("items", [])))
        pts = [(it["pos"]["x"], it["pos"]["y"])
               for it in v.get("items", [v]) if "pos" in it]
        return pts, (f"DRC {v.get('severity')}: {v['type']} "
                     f"({len(pts)} marked)")
    return [], ""


def label_marker(name, label):
    """Fallback marker: position of a `(label \"X\" (at ...))` in the
    mutant schematic (mm)."""
    sch = open(os.path.join(proj_dir(name), SCH_NAME)).read()
    m = re.search(r'\(label "' + re.escape(label) + r'" \(at ([\d.]+) ([\d.]+)',
                  sch)
    return [(float(m.group(1)), float(m.group(2)))] if m else []


def markers_for(name):
    """Return (kind, points_mm, label) where kind is 'sch' or 'pcb'."""
    if name == "good":
        return "pcb", [], ""
    if sch_changed(name):
        pts, lab = sch_markers(name)
        if not pts:                   # netlist_mismatch: no ERC marker
            pts = label_marker(name, "TRIGX")
            lab = "renamed net label (TRIG -> TRIGX)"
        return "sch", pts, lab
    pts, lab = pcb_markers(name)
    if not pts:                       # board_oversize: no DRC marker
        det = load(name)["gates"]["G7_limits"]["details"]
        if det.get("board_size_ok") is False:
            e = edge_cuts_points(os.path.join(proj_dir(name), PCB_NAME))
            x1 = max(p[0] for p in e)
            ys = [p[1] for p in e]
            pts = [(x1, (min(ys) + max(ys)) / 2)]
            w, h = det["board_size_mm"]
            lab = f"outline {w:.0f} x {h:.0f} mm > 50 mm limit"
    return "pcb", pts, lab


# -------------------------------------------------------- layout checking ---

def check_layout(fig, tag):
    """Fail loudly if any text is clipped by the canvas or two texts
    overlap. Call after the figure is fully drawn."""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    W, H = fig.canvas.get_width_height()
    tick_ids = set()
    for ax in fig.axes:
        for t in ax.get_xticklabels() + ax.get_yticklabels():
            tick_ids.add(id(t))
    boxes = []
    problems = []
    for t in fig.findobj(matplotlib.text.Text):
        s = t.get_text().strip()
        if not s or not t.get_visible():
            continue
        # tick labels of an axis("off") axes are not drawn
        if (id(t) in tick_ids and t.axes is not None
                and not t.axes.axison):
            continue
        bb = t.get_window_extent(renderer=rend)
        if not np.isfinite([bb.x0, bb.y0, bb.x1, bb.y1]).all():
            continue
        if (bb.x0 < -1 or bb.y0 < -1 or bb.x1 > W + 1 or bb.y1 > H + 1):
            problems.append(f"clipped: {s[:40]!r} bbox={bb}")
        if id(t) not in tick_ids:
            boxes.append((bb, s))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            b1, s1 = boxes[i]
            b2, s2 = boxes[j]
            ix = max(0, min(b1.x1, b2.x1) - max(b1.x0, b2.x0))
            iy = max(0, min(b1.y1, b2.y1) - max(b1.y0, b2.y0))
            if ix > 2 and iy > 2:
                problems.append(
                    f"overlap: {s1[:30]!r} vs {s2[:30]!r} "
                    f"({ix:.0f}x{iy:.0f}px)")
    if problems:
        for p in problems:
            print(f"  LAYOUT[{tag}] {p}", file=sys.stderr)
        raise SystemExit(f"layout check failed for {tag}: "
                         f"{len(problems)} problem(s)")


# ---------------------------------------------------------------- figures ---

def gate_table(ax, verdict, fontsize=10):
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.0, 0.97, "gate", fontsize=fontsize, weight="bold",
            family="monospace", va="top")
    ax.text(0.30, 0.97, "measured", fontsize=fontsize, weight="bold",
            family="monospace", va="top")
    ax.text(1.0, 0.97, "result", fontsize=fontsize, weight="bold",
            family="monospace", va="top", ha="right")
    y = 0.86
    step = 0.70 / len(GATE_ORDER)
    for g in GATE_ORDER:
        r = verdict["gates"][g]
        ok = r["pass"]
        ax.text(0.0, y, GATE_SHORT[g], fontsize=fontsize,
                family="monospace", va="top")
        ax.text(0.30, y, gate_row_text(g, r["details"]),
                fontsize=fontsize - 1.5, family="monospace", va="top",
                color="#333333")
        ax.text(1.0, y, "PASS" if ok else "FAIL", fontsize=fontsize,
                family="monospace", va="top", ha="right",
                weight="bold", color=C["pass"] if ok else C["fail"])
        y -= step
    overall = "PASS" if verdict["overall_pass"] else "FAIL"
    ax.text(0.0, y - 0.02, f"overall: {overall}",
            fontsize=fontsize + 3, weight="bold",
            color=C["pass"] if verdict["overall_pass"] else C["fail"],
            family="monospace", va="top")


def fig_result(img3d, good, out):
    fig = plt.figure(figsize=(12, 6))
    ax1 = fig.add_axes([0.02, 0.06, 0.46, 0.82])
    ax1.imshow(img3d)
    ax1.set_xticks([])
    ax1.set_yticks([])
    ax1.axis("off")
    ax1.set_title("kicad-cli pcb render (3D, top) — KiCad 9.0.9",
                  fontsize=11)
    ax2 = fig.add_axes([0.50, 0.06, 0.48, 0.82])
    gate_table(ax2, good)
    ax2.set_title("judge verdict — media/data/good.json (seed 42)",
                  fontsize=11)
    fig.suptitle("555 astable blinker — artifact + judge result",
                 fontsize=14, weight="bold")
    fig.savefig(out, dpi=200)
    check_layout(fig, "result.png")
    plt.close(fig)


def kill_matrix(ax, names, verdicts, fontsize=9):
    rows = len(names)
    cols = len(GATE_ORDER)
    for j, g in enumerate(GATE_ORDER):
        ax.text(j + 0.5, -0.32, GATE_SHORT[g], ha="center", va="bottom",
                fontsize=fontsize, weight="bold", rotation=0)
    for i, name in enumerate(names):
        v = verdicts[name]
        ax.text(-0.08, i + 0.5, name, ha="right", va="center",
                fontsize=fontsize, family="monospace")
        for j, g in enumerate(GATE_ORDER):
            r = v["gates"][g]
            ok = r["pass"]
            ax.add_patch(Rectangle((j, i), 1, 1,
                                   facecolor=C["pass"] if ok else C["fail"],
                                   edgecolor="white", lw=2))
            ax.text(j + 0.5, i + 0.5, "ok" if ok else fail_metric(
                    g, r["details"]), ha="center", va="center",
                    fontsize=fontsize - 2, color="white",
                    weight="bold" if not ok else "normal")
    ax.set_xlim(-0.2, cols + 0.05)
    ax.set_ylim(-0.6, rows)
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def fig_loop(names, verdicts, out):
    fig = plt.figure(figsize=(12, 6))
    ax = fig.add_axes([0.16, 0.10, 0.80, 0.74])
    kill_matrix(ax, names, verdicts)
    killed = sum(1 for n in names[1:] if not verdicts[n]["overall_pass"])
    fig.suptitle("self-test kill matrix — judge gates vs artifacts\n"
                 f"kill rate {killed}/{len(names) - 1} = "
                 f"{100 * killed // (len(names) - 1)} %  (required >= 90 %)",
                 fontsize=13, weight="bold")
    fig.text(0.16, 0.02,
             "cells coloured from media/data/*.json verdicts; "
             "red cells show the measured value that failed the gate",
             fontsize=9, color="#444444")
    fig.savefig(out, dpi=200)
    check_layout(fig, "loop.png")
    plt.close(fig)


# ---------------------------------------------------------------- frames ----

def new_frame():
    return plt.figure(figsize=(19.2, 10.8))


def img_panel(fig, rect, img, clip, title, markers=None, mark_label=""):
    ax = fig.add_axes(rect)
    x0, y0, x1, y1 = clip
    ax.imshow(img, extent=(x0, x1, y1, y0), interpolation="bilinear")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.tick_params(length=0)
    ax.set_title(title, fontsize=16)
    if markers:
        for mx, my in markers:
            r = max(x1 - x0, y1 - y0) * 0.045
            ax.add_patch(Circle((mx, my), r, fill=False,
                                edgecolor=C["mark"], lw=3, zorder=6))
        if mark_label:
            mx, my = markers[0]
            # label pinned inside the panel corner so it never clips
            ax.annotate(mark_label, (mx, my),
                        xytext=(x0 + (x1 - x0) * 0.03,
                                y0 + (y1 - y0) * 0.04),
                        fontsize=13, color=C["mark"], weight="bold",
                        va="top",
                        arrowprops=dict(arrowstyle="-", color=C["mark"],
                                        lw=1.5),
                        bbox=dict(boxstyle="round,pad=0.3",
                                  fc="white", ec=C["mark"], lw=1.5),
                        zorder=7)
    return ax


def gate_chips(fig, y, verdict, fontsize=13):
    x = 0.06
    for g in GATE_ORDER:
        r = verdict["gates"][g]
        ok = r["pass"]
        w = 0.12
        ax = fig.add_axes([x, y, w, 0.075])
        ax.axis("off")
        col = C["pass"] if ok else C["fail"]
        ax.add_patch(FancyBboxPatch((0, 0), 1, 1,
                                    boxstyle="round,pad=0.06",
                                    facecolor=col, edgecolor="none",
                                    transform=ax.transAxes,
                                    clip_on=False))
        if ok:
            ax.text(0.5, 0.5, GATE_SHORT[g], transform=ax.transAxes,
                    ha="center", va="center", fontsize=fontsize,
                    color="white", weight="bold")
        else:
            ax.text(0.5, 0.70, GATE_SHORT[g], transform=ax.transAxes,
                    ha="center", va="center", fontsize=fontsize,
                    color="white", weight="bold")
            ax.text(0.5, 0.28, fail_metric(g, r["details"]).replace("\n", " "),
                    transform=ax.transAxes, ha="center", va="center",
                    fontsize=fontsize - 3, color="white")
        x += w + 0.008


def frame_intro(img3d, out):
    fig = new_frame()
    ax = fig.add_axes([0.16, 0.10, 0.68, 0.62])
    ax.imshow(img3d)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.axis("off")
    fig.text(0.5, 0.94, "kicad-pcb demo", ha="center", fontsize=40,
             weight="bold")
    fig.text(0.5, 0.87,
             "a 555 astable LED blinker designed as a real KiCad 9 "
             "project, judged by pinned kicad-cli 9.0.9 + a stdlib "
             "oracle the agent cannot fool",
             ha="center", fontsize=20, color="#333333")
    fig.text(0.5, 0.06, "kicad-cli pcb render — 3D view, top side",
             ha="center", fontsize=14, color="#555555")
    fig.savefig(out, dpi=100)
    check_layout(fig, "f00")
    plt.close(fig)


def frame_good(img, clip, good, out):
    fig = new_frame()
    img_panel(fig, [0.03, 0.14, 0.55, 0.72], img, clip,
              "known-good artifact — pcb export svg (F.Cu B.Cu F.SilkS "
              "Edge.Cuts)")
    ax = fig.add_axes([0.60, 0.16, 0.38, 0.66])
    gate_table(ax, good, fontsize=14)
    ax.set_title("judge verdict — all gates pass", fontsize=16)
    fig.text(0.5, 0.95, "grading the known-good 555 blinker",
             ha="center", fontsize=34, weight="bold")
    gate_chips(fig, 0.045, good)
    fig.savefig(out, dpi=100)
    check_layout(fig, "f01")
    plt.close(fig)


def frame_mutant(name, idx, total, good_img, mut_img, clip, kind,
                 markers, mark_label, verdict, out):
    fig = new_frame()
    fig.text(0.5, 0.95, f"mutant {idx}/{total}: {name}",
             ha="center", fontsize=34, weight="bold")
    fig.text(0.5, 0.895, mutant_blurb(name), ha="center", fontsize=17,
             color="#333333", style="italic")
    layer = "schematic" if kind == "sch" else "board"
    img_panel(fig, [0.03, 0.16, 0.45, 0.66], good_img, clip,
              f"good {layer}")
    img_panel(fig, [0.52, 0.16, 0.45, 0.66], mut_img, clip,
              f"mutant {layer} — marker circled",
              markers=markers, mark_label=mark_label)
    fig.text(0.5, 0.145, "before / after — one edit",
             ha="center", fontsize=15, color="#555555")
    gate_chips(fig, 0.045, verdict)
    fig.savefig(out, dpi=100)
    check_layout(fig, f"mutant:{name}")
    plt.close(fig)


def frame_summary(names, verdicts, out):
    fig = new_frame()
    ax = fig.add_axes([0.24, 0.14, 0.60, 0.66])
    kill_matrix(ax, names, verdicts, fontsize=13)
    killed = sum(1 for n in names[1:] if not verdicts[n]["overall_pass"])
    fig.text(0.5, 0.94, "self-test: every mutant is killed",
             ha="center", fontsize=34, weight="bold")
    fig.text(0.5, 0.06,
             f"kill rate {killed}/{len(names) - 1} = 100 %   "
             "(judge exits 0 only when all seven gates pass; "
             "reproduce: python3 run.py)",
             ha="center", fontsize=18, color="#333333")
    fig.savefig(out, dpi=100)
    check_layout(fig, "f10")
    plt.close(fig)


# ------------------------------------------------------------------ main ----

def main():
    names = ["good"] + mutant_names()
    if len(names) != len(mut_mod.MUTANTS) + 1:
        sys.exit(f"expected good + {len(mut_mod.MUTANTS)} mutants in "
                 f"{MUT_DIR}, got {names}")
    verdicts = {n: load(n) for n in names}
    if not verdicts["good"]["overall_pass"]:
        sys.exit("media/data/good.json is not a pass — regenerate data")
    for n in names[1:]:
        if verdicts[n]["overall_pass"]:
            sys.exit(f"mutant {n} passes — data is stale or judge broken")

    os.makedirs(FRAMES, exist_ok=True)
    work = os.path.join(MASTER, "work")
    os.makedirs(work, exist_ok=True)

    # -- kicad-cli renders ---------------------------------------------------
    print("== kicad-cli renders")
    img3d_path = render3d(os.path.join(GOOD_DIR, PCB_NAME),
                          os.path.join(MASTER, "good_3d.png"))
    good_bsvg = board_svg(os.path.join(GOOD_DIR, PCB_NAME),
                          os.path.join(work, "good_board.svg"))
    good_ssvg = sch_svg(os.path.join(GOOD_DIR, SCH_NAME),
                        os.path.join(work, "good_sch"))
    sch_text_overlap(good_ssvg, "good")          # no text collisions

    svg_cache = {}
    for n in names[1:]:
        if sch_changed(n):
            svg = sch_svg(os.path.join(proj_dir(n), SCH_NAME),
                          os.path.join(work, f"{n}_sch"))
            sch_text_overlap(svg, n)
            svg_cache[n] = ("sch", svg)
        else:
            svg_cache[n] = ("pcb", board_svg(
                os.path.join(proj_dir(n), PCB_NAME),
                os.path.join(work, f"{n}_board.svg")))

    # -- rasterise -----------------------------------------------------------
    print("== rasterise")
    img3d = plt.imread(img3d_path)
    bclip = board_clip("good")
    good_board_img, bclip_used = rasterize(good_bsvg, bclip)
    good_sch_img = None
    renders = {}
    for n in names[1:]:
        kind, svg = svg_cache[n]
        if kind == "sch":
            if good_sch_img is None:
                sclip = sch_clip(good_ssvg)
                good_sch_img, _ = rasterize(good_ssvg, sclip)
            clip = sch_clip(svg)
            # show before/after on the same window: union of content
            u = (min(clip[0], sclip[0]), min(clip[1], sclip[1]),
                 max(clip[2], sclip[2]), max(clip[3], sclip[3]))
            m_img, clip_u = rasterize(svg, u)
            g_img, _ = rasterize(good_ssvg, u)
            renders[n] = (kind, g_img, m_img, clip_u)
        else:
            clip = board_clip(n)
            u = (min(clip[0], bclip_used[0]), min(clip[1], bclip_used[1]),
                 max(clip[2], bclip_used[2]), max(clip[3], bclip_used[3]))
            m_img, clip_u = rasterize(svg, u)
            g_img, _ = rasterize(good_bsvg, u)
            renders[n] = (kind, g_img, m_img, clip_u)

    # -- figures -------------------------------------------------------------
    print("== figures")
    fig_result(img3d, verdicts["good"], os.path.join(HERE, "result.png"))
    fig_loop(names, verdicts, os.path.join(HERE, "loop.png"))

    print("== frames")
    frame_intro(img3d, os.path.join(FRAMES, "f00.png"))
    frame_good(good_board_img, bclip_used, verdicts["good"],
               os.path.join(FRAMES, "f01.png"))
    for i, n in enumerate(names[1:], start=1):
        kind, g_img, m_img, clip = renders[n]
        mk_kind, pts, lab = markers_for(n)
        assert mk_kind == kind, (n, mk_kind, kind)
        frame_mutant(n, i, len(names) - 1, g_img, m_img, clip, kind,
                     pts, lab, verdicts[n],
                     os.path.join(FRAMES, f"f{1 + i:02d}.png"))
    frame_summary(names, verdicts,
                  os.path.join(FRAMES, f"f{len(names) + 1:02d}.png"))
    print(f"rendered result.png, loop.png, {len(os.listdir(FRAMES))} frames")


if __name__ == "__main__":
    main()
