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
import time
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

# G7: physical limits published in SPEC.md ("Reference constraints").
# The judge enforces them so the published numbers are not advisory.
BOARD_MAX_MM = 50.0
NETCLASS_MIN_MM = {"clearance": 0.20, "track_width": 0.20,
                   "via_drill": 0.30}

# Judge-pinned DRC severities: the KiCad 9 default map.  Grading always
# runs with these — an artifact must not soften or silence the checks it
# is graded by.  Written into the graded copy of the .kicad_pro by
# pin_design_rules() (called from grade.sh).
PINNED_DRC_SEVERITIES = {
    "annular_width": "error",
    "clearance": "error",
    "connection_width": "warning",
    "copper_edge_clearance": "error",
    "copper_sliver": "warning",
    "courtyards_overlap": "error",
    "creepage": "error",
    "diff_pair_gap_out_of_range": "error",
    "diff_pair_uncoupled_length_too_long": "error",
    "drill_out_of_range": "error",
    "duplicate_footprints": "warning",
    "extra_footprint": "warning",
    "footprint": "error",
    "footprint_filters_mismatch": "ignore",
    "footprint_symbol_mismatch": "warning",
    "footprint_type_mismatch": "ignore",
    "hole_clearance": "error",
    "hole_to_hole": "warning",
    "holes_co_located": "warning",
    "invalid_outline": "error",
    "isolated_copper": "warning",
    "item_on_disabled_layer": "error",
    "items_not_allowed": "error",
    "length_out_of_range": "error",
    "lib_footprint_issues": "warning",
    "lib_footprint_mismatch": "warning",
    "malformed_courtyard": "error",
    "microvia_drill_out_of_range": "error",
    "mirrored_text_on_front_layer": "warning",
    "missing_courtyard": "ignore",
    "missing_footprint": "warning",
    "net_conflict": "warning",
    "nonmirrored_text_on_back_layer": "warning",
    "npth_inside_courtyard": "ignore",
    "padstack": "warning",
    "pth_inside_courtyard": "ignore",
    "shorting_items": "error",
    "silk_edge_clearance": "warning",
    "silk_over_copper": "warning",
    "silk_overlap": "warning",
    "skew_out_of_range": "error",
    "solder_mask_bridge": "error",
    "starved_thermal": "error",
    "text_height": "warning",
    "text_on_edge_cuts": "error",
    "text_thickness": "warning",
    "through_hole_pad_without_hole": "error",
    "too_many_vias": "error",
    "track_angle": "error",
    "track_dangling": "warning",
    "track_segment_length": "error",
    "track_width": "error",
    "tracks_crossing": "error",
    "unconnected_items": "error",
    "unresolved_variable": "error",
    "via_dangling": "warning",
    "zones_intersect": "error",
}


def pin_design_rules(pro_path):
    """Reset the judge-owned rule settings in a .kicad_pro in place.

    The artifact under test may not choose the severity of the checks it
    is graded by: rule_severities return to PINNED_DRC_SEVERITIES and
    drc_exclusions are cleared.  Any artifact "erc" section (its own
    severity map, pin-conflict map and exclusions) is dropped so KiCad
    applies its defaults.  grade.sh additionally removes any artifact
    .kicad_dru custom-rule file.
    """
    pro = json.load(open(pro_path))
    ds = pro.setdefault("board", {}).setdefault("design_settings", {})
    ds["rule_severities"] = dict(PINNED_DRC_SEVERITIES)
    ds["drc_exclusions"] = []
    pro.pop("erc", None)
    with open(pro_path, "w") as f:
        json.dump(pro, f, indent=2)
        f.write("\n")


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


def norm_net(name):
    """The one documented net-name normalization, applied identically
    to schematic and PCB names: drop the hierarchical sheet path — keep
    the last '/'-separated component ("/TRIG" == "TRIG"; a KiCad
    schematic-to-PCB update writes the hierarchical form).  Anything
    else that differs is a real mismatch, not a spelling difference."""
    return name.split("/")[-1] or name


def sch_net_names(netlist_xml):
    """Net names from the kicadxml netlist, normalized."""
    tree = ET.parse(netlist_xml)
    names = []
    for n in tree.iter("net"):
        name = n.get("name", "")
        # single-node synthetic nets name a floating pin -> count separately
        nodes = list(n.iter("node"))
        names.append((norm_net(name), len(nodes),
                      name.startswith("unconnected")))
    return names


def pcb_net_names(pcb_path):
    tree = parse_sexpr(open(pcb_path).read())
    names = []
    for net in find_all(tree, "net"):
        if len(net) >= 3 and net[1].isdigit():
            names.append(norm_net(net[2]))
    return names


def sch_net_nodes(netlist_xml, placed):
    """{normalized net name: {(ref, pin)}} from the kicadxml netlist.

    Nodes are restricted to `placed` refs (footprints on the board);
    power/flag symbols carry no pads.  Comparing members, not just
    names, is what makes a board that lands the right net names on the
    wrong pins fail — e.g. an LED mounted backwards.
    """
    nets = {}
    for n in ET.parse(netlist_xml).iter("net"):
        name = norm_net(n.get("name", ""))
        nodes = {(nd.get("ref"), nd.get("pin"))
                 for nd in n.iter("node") if nd.get("ref") in placed}
        if nodes:
            nets.setdefault(name, set()).update(nodes)
    return nets


def pcb_net_pads(pcb_path):
    """{normalized net name: {(ref, pad)}} — which pad sits on which
    net, from each footprint's pad (net N "name") children."""
    tree = parse_sexpr(open(pcb_path).read())
    nets = {}
    for fp in find_all(tree, "footprint"):
        ref = None
        for prop in fp:
            if (isinstance(prop, list) and len(prop) > 2
                    and prop[:2] == ["property", "Reference"]
                    and not prop[2].startswith("#")):
                ref = prop[2]
        if not ref:
            continue
        for pad in find_all(fp, "pad"):
            if len(pad) < 2:
                continue
            n = child(pad, "net")
            if n and len(n) >= 3 and n[2]:
                nets.setdefault(norm_net(n[2]), set()).add((ref, pad[1]))
    return nets


def sch_parts(netlist_xml):
    """{reference: "lib:part"} of the schematic's placed components."""
    return {c.get("ref"): "{}:{}".format(c.find("libsource").get("lib", ""),
                                         c.find("libsource").get("part", ""))
            for c in ET.parse(netlist_xml).iter("comp")
            if c.find("libsource") is not None}


def pcb_refs(pcb_path):
    """References of the footprints placed on the board."""
    tree = parse_sexpr(open(pcb_path).read())
    refs = set()
    for fp in find_all(tree, "footprint"):
        for prop in fp:
            if (isinstance(prop, list) and len(prop) > 2
                    and prop[:2] == ["property", "Reference"]
                    and not prop[2].startswith("#")):
                refs.add(prop[2])
    return refs


def gate_netlist(sch_xml, pcb_path, drc_path):
    """G3: schematic net set == PCB net set by NAME and by MEMBERS —
    for every net, the (ref, pin) set in the schematic netlist must equal
    the (ref, pad) set on that net in the .kicad_pcb — plus no unrouted
    pins, and the design is the assigned blinker: a 555 timer and an LED
    are placed and every schematic part has a footprint on the board
    (and vice versa)."""
    sch = sch_net_names(sch_xml)
    fps = pcb_refs(pcb_path)
    sch_members = sch_net_nodes(sch_xml, fps)
    pcb_members = pcb_net_pads(pcb_path)
    sch_named = set(sch_members)
    pcb = set(pcb_members)
    floating = [n for n, cnt, unc in sch if unc]
    rep = json.load(open(drc_path))
    unrouted = len(rep.get("unconnected_items", []))
    parts = sch_parts(sch_xml)
    missing = [k for k, hit in (
        ("555 timer", any("555" in p for p in parts.values())),
        ("LED", any(p.split(":")[-1].startswith("LED")
                    for p in parts.values()))) if not hit]
    member_diff = {n: {"sch_only": sorted(sch_members[n] - pcb_members[n]),
                       "pcb_only": sorted(pcb_members[n] - sch_members[n])}
                   for n in sch_named & pcb
                   if sch_members[n] != pcb_members[n]}
    ok = (sch_named == pcb and not member_diff and not floating
          and unrouted == 0 and not missing and set(parts) == fps)
    det = {
        "sch_nets": sorted(sch_named), "pcb_nets": sorted(pcb),
        "floating_pins": len(floating), "unrouted_items": unrouted,
        "only_in_sch": sorted(sch_named - pcb),
        "only_in_pcb": sorted(pcb - sch_named)}
    # reported only when they fail, so passing verdicts keep their shape
    if member_diff:
        det["member_mismatch"] = member_diff
    if missing:
        det["parts_missing"] = missing
    if set(parts) != fps:
        det["refs_only_in_sch"] = sorted(set(parts) - fps)
        det["refs_only_in_pcb"] = sorted(fps - set(parts))
    return ok, det


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
            elif tag in ("gr_rect", "gr_circle", "gr_poly"):
                segs.append(None)          # inherently closed shapes
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
    """G4: Edge.Cuts geometry forms a closed outline.  gr_rect,
    gr_circle and gr_poly are inherently closed shapes; gr_line, gr_arc
    and gr_curve endpoints must each be shared by >= 2 primitives."""
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
    ok = not open_ends and (closed_shapes > 0 or bool(lines))
    return ok, {"edge_cuts_items": len(segs),
                "open_endpoints": len(open_ends), "closed": bool(ok)}


APERTURE_RE = re.compile(r"%ADD\d+[A-Za-z]")
DCODE_RE = re.compile(r"D0?([123])\s*\*?$")
COORD_RE = re.compile(r"[XY]-?\.?\d")


def parse_gerber(path):
    """Return (aperture count, draw/flash op count).

    Only D01 draws and D03 flashes lay down geometry — a D02 coordinate
    block is a pen-up move and draws nothing.  The operation code is
    modal: a coordinate block without an explicit D-code takes the last
    one seen, and a bare D-code line just changes the mode.
    """
    text = open(path, errors="replace").read()
    apertures = len(APERTURE_RE.findall(text))
    ops = 0
    dop = "D01"                                    # modal operation
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("%", "G04")):
            continue
        m = DCODE_RE.search(line)
        if m:
            dop = "D0" + m.group(1)
        if COORD_RE.search(line) and dop in ("D01", "D03"):
            ops += 1
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
SLOT_RE = re.compile(r"G85")          # canned slot-rout cycle: 1 hole


def needed_holes(pcb_path):
    """Holes the .kicad_pcb actually requires: (drill_mm, kind) for
    every thru_hole / np_thru_hole pad and every via. A drill of 0 means
    'no hole' — for a through-hole pad that is itself the defect."""
    def drill_dia(node):
        """First numeric token of a (drill ...) child, else 0."""
        d = child(node, "drill")
        for tok in (d[1:] if d else []):
            try:
                return fnum(tok)
            except ValueError:
                continue          # e.g. (drill oval 1.0 1.4)
        return 0.0

    tree = parse_sexpr(open(pcb_path).read())
    holes = []
    for pad in find_all(tree, "pad"):
        ptype = pad[2] if len(pad) > 2 else ""
        if ptype in ("thru_hole", "np_thru_hole"):
            holes.append((drill_dia(pad), ptype))
    for via in find_all(tree, "via"):
        holes.append((drill_dia(via), "via"))
    return holes


def gate_drill(drill_dir, pcb_path):
    """G6: every through-hole pad and via needs a non-zero drill, the
    Excellon export must carry a tool for each required diameter, and
    the hit count must cover the holes the board needs."""
    files = [f for f in (os.listdir(drill_dir) if os.path.isdir(drill_dir)
                         else []) if f.endswith(".drl")]
    holes = needed_holes(pcb_path)
    no_drill = {}
    need_dia = set()
    for dia, kind in holes:
        if dia > 0:
            need_dia.add(round(dia, 4))
        else:
            no_drill[kind] = no_drill.get(kind, 0) + 1
    details = {"drill_files": len(files),
               "expected_holes": sum(1 for d, _ in holes if d > 0),
               "no_drill_pads": no_drill.get("thru_hole", 0)
               + no_drill.get("np_thru_hole", 0),
               "no_drill_vias": no_drill.get("via", 0)}
    if not files:
        return False, details
    tools = []                                       # diameters in mm
    hits = 0
    for f in files:
        unit = 25.4                                  # Excellon default
        for line in open(os.path.join(drill_dir, f), errors="replace"):
            line = line.strip()
            if line.startswith(";"):               # Excellon comment
                continue
            if line.split(",")[0] in ("METRIC", "M71"):
                unit = 1.0
            elif line.split(",")[0] in ("INCH", "M72"):
                unit = 25.4
            m = TOOL_RE.match(line)
            if m and float(m.group(1)) > 0:
                tools.append(float(m.group(1)) * unit)
            elif HIT_RE.match(line) or SLOT_RE.search(line):
                hits += 1
    details["tools"] = len(tools)
    details["drill_hits"] = hits
    missing = sorted(d for d in need_dia
                     if not any(abs(d - t) < 0.01 for t in tools))
    details["missing_tool_mm"] = missing
    ok = (tools and hits > 0 and not no_drill and not missing
          and hits >= details["expected_holes"])
    return bool(ok), details


def gate_limits(pcb_path, pro_path):
    """G7: the physical limits SPEC.md publishes are real pass rules.

    - the Edge.Cuts bounding box must fit in BOARD_MAX_MM square;
    - every netclass in the project must meet the published minima
      (NETCLASS_MIN_MM): clearance and track width >= 0.20 mm, via
      drill >= 0.30 mm.  The project must declare its classes — with no
      net_settings the file's own limits cannot be verified.
    """
    det = {"board_limit_mm": BOARD_MAX_MM,
           "netclass_min_mm": dict(NETCLASS_MIN_MM)}
    ok = True
    pts = edge_cuts_points(pcb_path)
    if pts:
        x0, y0, x1, y1 = bbox(pts)
        w, h = round(x1 - x0, 4), round(y1 - y0, 4)
        det["board_size_mm"] = [w, h]
        if w > BOARD_MAX_MM or h > BOARD_MAX_MM:
            det["board_size_ok"] = False
            ok = False
        else:
            det["board_size_ok"] = True
    else:
        det["board_size_ok"] = False
        ok = False
    pro = json.load(open(pro_path))
    classes = (pro.get("net_settings") or {}).get("classes") or []
    bad = {}
    for c in classes:
        for k, vmin in NETCLASS_MIN_MM.items():
            v = c.get(k)
            if v is None or float(v) < vmin:
                bad.setdefault(c.get("name", "?"), {})[k] = v
    if not classes:
        det["netclass_violations"] = {"<none>": "no netclass declared"}
        ok = False
    elif bad:
        det["netclass_violations"] = bad
        ok = False
    else:
        det["netclass_ok"] = True
    return ok, det


# ------------------------------------------------------------------- main ---

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcb", required=True)
    ap.add_argument("--pro", required=True)
    ap.add_argument("--erc", required=True)
    ap.add_argument("--drc", required=True)
    ap.add_argument("--sch-netlist", required=True)
    ap.add_argument("--gerber-dir", required=True)
    ap.add_argument("--drill-dir", required=True)
    ap.add_argument("--json")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--wall-start", type=float, default=None,
                    help="epoch seconds when grading began; recorded "
                         "under the verdict's 'timing' key")
    args = ap.parse_args()

    gates = {}
    checks = [
        ("G1_erc", gate_erc, (args.erc,)),
        ("G2_drc", gate_drc, (args.drc,)),
        ("G3_netlist", gate_netlist,
         (args.sch_netlist, args.pcb, args.drc)),
        ("G4_outline", gate_outline, (args.pcb,)),
        ("G5_gerber", gate_gerbers, (args.gerber_dir, args.pcb)),
        ("G6_drill", gate_drill, (args.drill_dir, args.pcb)),
        ("G7_limits", gate_limits, (args.pcb, args.pro)),
    ]
    for name, fn, fargs in checks:
        try:
            ok, det = fn(*fargs)
        except Exception as e:
            ok, det = False, {"oracle_error": f"{type(e).__name__}: {e}"}
        gates[name] = {"pass": bool(ok), "details": det}

    overall = all(g["pass"] for g in gates.values())
    verdict = {"gates": gates, "overall_pass": overall, "seed": args.seed}
    if args.wall_start is not None:
        verdict["timing"] = {"wall_seconds":
                             round(time.time() - args.wall_start, 3)}
    for name, g in gates.items():
        print(f"  {name}: {'PASS' if g['pass'] else 'FAIL'} "
              f"{json.dumps(g['details'], sort_keys=True)}")
    print(f"  overall: {'PASS' if overall else 'FAIL'}")
    if args.json:
        # An unwritable verdict is a judge failure, not a quiet pass.
        try:
            with open(args.json, "w") as f:
                json.dump(verdict, f, indent=2, sort_keys=True)
                f.write("\n")
        except OSError as e:
            print(f"oracle: cannot write verdict {args.json}: {e}",
                  file=sys.stderr)
            sys.exit(2)
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
