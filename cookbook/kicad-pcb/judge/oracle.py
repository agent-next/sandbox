#!/usr/bin/env python3
"""Independent oracle for the KiCad PCB demo judge.

Parses the files produced by grade.sh (ERC/DRC JSON reports, schematic
netlist XML, exported Gerbers and Excellon drill) plus the .kicad_pcb
source itself, and emits a verdict JSON. No KiCad code runs here: every
number comes from parsing the artifacts directly.

Usage:
    oracle.py --pcb FILE --erc FILE --drc FILE --sch-netlist FILE
              --gerber-dir DIR --drill-dir DIR --json FILE
Exit 0 iff every gate passes.
"""

import argparse
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

EXPECTED_LAYERS = [
    "F.Cu", "B.Cu", "F.Silkscreen", "B.Silkscreen",
    "F.Mask", "B.Mask", "Edge.Cuts",
]

# ERC warning types G1 tolerates, with justification (see SPEC.md):
#   lib_symbol_issues — "library X not in the current configuration":
#   the artifact is deliberately self-contained (all symbols embedded in
#   lib_symbols) and grading runs kicad-cli headless with no sym-lib-table,
#   so every symbol instance earns this warning.  It is informational:
#   ERC resolves connectivity from the embedded symbols, as proven by the
#   netlist gate matching the PCB net set.
ERC_WARNING_ALLOWLIST = {"lib_symbol_issues"}

# G5: exported Edge.Cuts gerber extents must match the .kicad_pcb
# Edge.Cuts geometry within this tolerance (mm).
EXTENTS_TOL_MM = 0.1


# ---------------------------------------------------------------- s-expr ----

def parse_sexpr(text):
    """Minimal s-expression parser -> nested lists of str."""
    toks = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    pos = 0

    def walk():
        nonlocal pos
        out = []
        while pos < len(toks):
            t = toks[pos]
            pos += 1
            if t == "(":
                out.append(walk())
            elif t == ")":
                return out
            else:
                out.append(t[1:-1] if t.startswith('"') else t)
        return out

    return walk()


def find_all(tree, tag):
    """Yield all sub-lists of tree whose head is `tag`."""
    if isinstance(tree, list):
        if tree and tree[0] == tag:
            yield tree
        for it in tree:
            yield from find_all(it, tag)


def child(node, tag):
    """First sub-list of node whose head is `tag`, else None."""
    for it in node:
        if isinstance(it, list) and it and it[0] == tag:
            return it
    return None


def fnum(s):
    return float(s)


# ------------------------------------------------------------------ gates ---

def gate_erc(path):
    """G1: zero error violations, and every reported violation type must
    be in ERC_WARNING_ALLOWLIST (justified in SPEC.md)."""
    rep = json.load(open(path))
    errors = 0
    err_kinds, warn_kinds = {}, {}
    for sheet in rep.get("sheets", []):
        for v in sheet.get("violations", []):
            t = v.get("type", "?")
            if v.get("severity") == "error":
                errors += 1
                err_kinds[t] = err_kinds.get(t, 0) + 1
            else:
                warn_kinds[t] = warn_kinds.get(t, 0) + 1
    bad_warn = {t: n for t, n in warn_kinds.items()
                if t not in ERC_WARNING_ALLOWLIST}
    ok = errors == 0 and not bad_warn
    return ok, {"erc_errors": errors, "erc_warnings": sum(warn_kinds.values()),
                "error_types": err_kinds, "warning_types": warn_kinds,
                "warning_types_not_allowed": bad_warn,
                "warnings_allowlist": sorted(ERC_WARNING_ALLOWLIST)}


def gate_drc(path):
    """G2: zero violations and zero unconnected items."""
    rep = json.load(open(path))
    n_v = len(rep.get("violations", []))
    n_u = len(rep.get("unconnected_items", []))
    kinds = {}
    for v in rep.get("violations", []):
        kinds[v.get("type", "?")] = kinds.get(v.get("type", "?"), 0) + 1
    return n_v == 0 and n_u == 0, {
        "drc_violations": n_v, "drc_unconnected_items": n_u,
        "violation_types": kinds}


def sch_net_names(netlist_xml):
    """Net names from the kicadxml netlist, sheet prefix stripped."""
    tree = ET.parse(netlist_xml)
    names = []
    for n in tree.iter("net"):
        name = n.get("name", "")
        # single-node synthetic nets name a floating pin -> count separately
        nodes = list(n.iter("node"))
        names.append((name.split("/")[-1] or name, len(nodes),
                      name.startswith("unconnected")))
    return names


def pcb_net_names(pcb_path):
    tree = parse_sexpr(open(pcb_path).read())
    names = []
    for net in find_all(tree, "net"):
        if len(net) >= 3 and net[1].isdigit():
            names.append(net[2])
    return names


def gate_netlist(sch_xml, pcb_path, drc_path):
    """G3: schematic net set == PCB net set and no unrouted pins."""
    sch = sch_net_names(sch_xml)
    pcb = set(pcb_net_names(pcb_path)) - {""}
    sch_named = {n for n, cnt, unc in sch if not unc}
    floating = [n for n, cnt, unc in sch if unc]
    rep = json.load(open(drc_path))
    unrouted = len(rep.get("unconnected_items", []))
    ok = sch_named == pcb and not floating and unrouted == 0
    return ok, {
        "sch_nets": sorted(sch_named), "pcb_nets": sorted(pcb),
        "floating_pins": len(floating), "unrouted_items": unrouted,
        "only_in_sch": sorted(sch_named - pcb),
        "only_in_pcb": sorted(pcb - sch_named)}


def outline_segments(pcb_path):
    """All Edge.Cuts primitives as endpoint lists [(x,y),...]."""
    tree = parse_sexpr(open(pcb_path).read())
    segs = []
    for tag in ("gr_line", "gr_arc", "gr_rect", "gr_circle", "gr_poly",
                "gr_curve"):
        for el in find_all(tree, tag):
            lay = child(el, "layer")
            if not lay or "Edge.Cuts" not in lay[1]:
                continue
            if tag == "gr_line":
                s, e = child(el, "start"), child(el, "end")
                segs.append([(fnum(s[1]), fnum(s[2])),
                             (fnum(e[1]), fnum(e[2]))])
            elif tag == "gr_arc":
                pts = []
                for k in ("start", "mid", "end"):
                    p = child(el, k)
                    pts.append((fnum(p[1]), fnum(p[2])))
                segs.append(pts)
            elif tag in ("gr_rect", "gr_circle"):
                segs.append(None)          # inherently closed
            else:
                pts = child(el, "pts")
                xy = [(fnum(p[1]), fnum(p[2])) for p in pts[1:]]
                segs.append(xy)
    return segs


def _arc_sweep(p0, p1, c, ccw, n=257):
    """n+1 samples on the arc p0->p1 about centre c in direction ccw."""
    r = math.hypot(p0[0] - c[0], p0[1] - c[1])
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    span = ((a1 - a0) % (2 * math.pi)) if ccw else -((a0 - a1) % (2 * math.pi))
    return [(c[0] + r * math.cos(a0 + span * i / n),
             c[1] + r * math.sin(a0 + span * i / n)) for i in range(n + 1)]


def arc3_points(p0, pm, p1):
    """Samples along the 3-point arc p0->pm->p1 (kicad_pcb gr_arc)."""
    ax, ay = p0
    bx, by = pm
    cx, cy = p1
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return [p0, pm, p1]            # degenerate: treat as polyline
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    c = (ux, uy)
    a0 = math.atan2(p0[1] - uy, p0[0] - ux)
    am = math.atan2(pm[1] - uy, pm[0] - ux)
    a1 = math.atan2(p1[1] - uy, p1[0] - ux)
    ccw = (am - a0) % (2 * math.pi) <= (a1 - a0) % (2 * math.pi)
    return _arc_sweep(p0, p1, c, ccw)


def edge_cuts_points(pcb_path):
    """Sampled boundary points of every Edge.Cuts primitive (board side)."""
    tree = parse_sexpr(open(pcb_path).read())

    def pt(node):
        return (fnum(node[1]), fnum(node[2]))

    pts = []
    for tag in ("gr_line", "gr_arc", "gr_rect", "gr_circle", "gr_poly",
                "gr_curve"):
        for el in find_all(tree, tag):
            lay = child(el, "layer")
            if not lay or "Edge.Cuts" not in lay[1]:
                continue
            if tag == "gr_line":
                pts += [pt(child(el, "start")), pt(child(el, "end"))]
            elif tag == "gr_arc":
                pts += arc3_points(pt(child(el, "start")),
                                   pt(child(el, "mid")),
                                   pt(child(el, "end")))
            elif tag == "gr_rect":
                pts += [pt(child(el, "start")), pt(child(el, "end"))]
            elif tag == "gr_circle":
                c = pt(child(el, "center"))
                e = pt(child(el, "end"))
                r = math.hypot(e[0] - c[0], e[1] - c[1])
                pts += [(c[0] + r, c[1]), (c[0] - r, c[1]),
                        (c[0], c[1] + r), (c[0], c[1] - r)]
            else:                                   # gr_poly, gr_curve
                p = child(el, "pts")
                pts += [pt(q) for q in p[1:]]
    return pts


def gate_outline(pcb_path):
    """G4: Edge.Cuts geometry forms a closed outline."""
    segs = outline_segments(pcb_path)
    lines = [s for s in segs if s]
    closed_shapes = sum(1 for s in segs if s is None)
    if not segs:
        return False, {"edge_cuts_items": 0, "closed": False}
    # every segment endpoint must be shared by >= 2 endpoints (closed loop)
    deg = {}
    for s in lines:
        for p in (s[0], s[-1]):
            key = (round(p[0], 4), round(p[1], 4))
            deg[key] = deg.get(key, 0) + 1
    open_ends = [p for p, d in deg.items() if d < 2]
    ok = (closed_shapes > 0 or (lines and not open_ends))
    return ok, {"edge_cuts_items": len(segs),
                "open_endpoints": len(open_ends), "closed": bool(ok)}


APERTURE_RE = re.compile(r"%ADD\d+[A-Za-z]")
OP_RE = re.compile(r"[XY][\d.+-]+[XY]?[\d.+-]*D0?[123]\*?")


def parse_gerber(path):
    """Return (aperture count, draw/flash op count)."""
    text = open(path, errors="replace").read()
    apertures = len(APERTURE_RE.findall(text))
    ops = 0
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("%") or not line:
            continue
        if re.search(r"D0?[13]\*?$", line):      # D01 draw / D03 flash
            ops += 1
        elif re.search(r"[XY][-\d.]+.*D0?2\*?$", line):
            ops += 1                              # D02 pen-down move w/ coords
    return apertures, ops


def gerber_drawn_points(path):
    """Sampled points of drawn Gerber geometry (mm, gerber coords).

    Walks the data blocks: D01 draws (linear + G02/G03 arcs with I/J
    centres) and D03 flashes contribute points; D02 moves do not draw.
    Honours %FSLA digit format and %MO units.
    """
    text = open(path, errors="replace").read()
    dec = 6
    scale = 1.0
    for blk in re.findall(r"%([^%]*)%", text):
        f = re.search(r"FSLAX\d(\d)Y\d(\d)", blk)
        if f:
            dec = int(f.group(1))
        if "MOIN" in blk:
            scale = 25.4
    body = re.sub(r"%[^%]*%", "", text)
    pos = (0.0, 0.0)
    mode = "G01"
    dop = "D01"
    pts = []
    for cmd in body.split("*"):
        cmd = cmd.strip()
        if not cmd or cmd.startswith("G04"):
            continue
        g = re.match(r"G0?([123])\b", cmd)
        if g:
            mode = "G0" + g.group(1)
        d = re.search(r"D0?([123])\s*$", cmd)
        if d:
            dop = "D0" + d.group(1)
        nums = dict(re.findall(r"([XYIJ])([+-]?\d+)", cmd))
        if not ("X" in nums or "Y" in nums):
            continue

        def val(k):
            return int(nums[k]) / 10 ** dec * scale

        nx = val("X") if "X" in nums else pos[0]
        ny = val("Y") if "Y" in nums else pos[1]
        if dop == "D01":
            if mode in ("G02", "G03"):
                c = (pos[0] + (val("I") if "I" in nums else 0.0),
                     pos[1] + (val("J") if "J" in nums else 0.0))
                pts += _arc_sweep(pos, (nx, ny), c, ccw=(mode == "G03"))
            else:
                pts.append((nx, ny))
        elif dop == "D03":
            pts.append((nx, ny))
        pos = (nx, ny)
    return pts


def bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def gate_gerbers(gerber_dir, pcb_path):
    """G5: every expected layer file exists and parses with >=1 aperture
    and >=1 draw/flash op; the exported Edge.Cuts gerber's extents must
    match the board's Edge.Cuts geometry within EXTENTS_TOL_MM (gerber
    y-axis is inverted vs the board, so compare gy_min ~ -py_max)."""
    details = {}
    ok = True
    files = os.listdir(gerber_dir) if os.path.isdir(gerber_dir) else []
    edge_file = None
    for layer in EXPECTED_LAYERS:
        fname = layer.replace(".", "_")
        match = [f for f in files if fname in f]
        if not match:
            ok = False
            details[layer] = "missing"
            continue
        path = os.path.join(gerber_dir, match[0])
        ap, ops = parse_gerber(path)
        details[layer] = {"apertures": ap, "ops": ops, "file": match[0]}
        if ap == 0 or ops == 0:
            ok = False
        if layer == "Edge.Cuts":
            edge_file = path
    pcb_pts = edge_cuts_points(pcb_path)
    if edge_file is None:
        pass                                     # already failed above
    elif not pcb_pts:
        ok = False
        details["extents"] = "no Edge.Cuts geometry in .kicad_pcb"
    else:
        gpts = gerber_drawn_points(edge_file)
        if not gpts:
            ok = False
            details["extents"] = "no drawn geometry in Edge.Cuts gerber"
        else:
            gx0, gy0, gx1, gy1 = bbox(gpts)
            px0, py0, px1, py1 = bbox(pcb_pts)
            deltas = {"x_min": abs(gx0 - px0), "x_max": abs(gx1 - px1),
                      "y_min": abs(gy0 + py1), "y_max": abs(gy1 + py0)}
            worst = max(deltas.values())
            details["extents_mm"] = {
                "gerber": [round(v, 6) for v in (gx0, gy0, gx1, gy1)],
                "board": [round(v, 6) for v in (px0, -py1, px1, -py0)],
                "max_delta_mm": round(worst, 6),
                "tol_mm": EXTENTS_TOL_MM}
            if worst > EXTENTS_TOL_MM:
                ok = False
    return ok, details


TOOL_RE = re.compile(r"^T\d+C([\d.]+)")
HIT_RE = re.compile(r"^X-?[\d.]+Y-?[\d.]+$")


def gate_drill(drill_dir):
    """G6: Excellon file parses, >=1 tool, >=1 drilled hole."""
    files = [f for f in (os.listdir(drill_dir) if os.path.isdir(drill_dir)
                         else []) if f.endswith(".drl")]
    if not files:
        return False, {"drill_files": 0}
    tools = hits = 0
    for f in files:
        for line in open(os.path.join(drill_dir, f), errors="replace"):
            line = line.strip()
            m = TOOL_RE.match(line)
            if m and float(m.group(1)) > 0:
                tools += 1
            elif HIT_RE.match(line):
                hits += 1
    return tools > 0 and hits > 0, {"drill_files": len(files),
                                    "tools": tools, "drill_hits": hits}


# ------------------------------------------------------------------- main ---

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcb", required=True)
    ap.add_argument("--erc", required=True)
    ap.add_argument("--drc", required=True)
    ap.add_argument("--sch-netlist", required=True)
    ap.add_argument("--gerber-dir", required=True)
    ap.add_argument("--drill-dir", required=True)
    ap.add_argument("--json")
    args = ap.parse_args()

    gates = {}
    checks = [
        ("G1_erc", gate_erc, (args.erc,)),
        ("G2_drc", gate_drc, (args.drc,)),
        ("G3_netlist", gate_netlist,
         (args.sch_netlist, args.pcb, args.drc)),
        ("G4_outline", gate_outline, (args.pcb,)),
        ("G5_gerber", gate_gerbers, (args.gerber_dir, args.pcb)),
        ("G6_drill", gate_drill, (args.drill_dir,)),
    ]
    for name, fn, fargs in checks:
        try:
            ok, det = fn(*fargs)
        except Exception as e:
            ok, det = False, {"oracle_error": f"{type(e).__name__}: {e}"}
        gates[name] = {"pass": bool(ok), "details": det}

    overall = all(g["pass"] for g in gates.values())
    verdict = {"gates": gates, "overall_pass": overall}
    if args.json:
        with open(args.json, "w") as f:
            json.dump(verdict, f, indent=2, sort_keys=True)
            f.write("\n")
    for name, g in gates.items():
        print(f"  {name}: {'PASS' if g['pass'] else 'FAIL'} "
              f"{json.dumps(g['details'], sort_keys=True)}")
    print(f"  overall: {'PASS' if overall else 'FAIL'}")
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
