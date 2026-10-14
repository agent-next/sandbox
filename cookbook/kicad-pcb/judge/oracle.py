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
import os
import re
import sys
import xml.etree.ElementTree as ET

EXPECTED_LAYERS = [
    "F.Cu", "B.Cu", "F.Silkscreen", "B.Silkscreen",
    "F.Mask", "B.Mask", "Edge.Cuts",
]


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
    """G1: zero severity==error violations across all sheets."""
    rep = json.load(open(path))
    errors = warnings = 0
    kinds = {}
    for sheet in rep.get("sheets", []):
        for v in sheet.get("violations", []):
            if v.get("severity") == "error":
                errors += 1
                kinds[v.get("type", "?")] = kinds.get(v.get("type", "?"), 0) + 1
            else:
                warnings += 1
    return errors == 0, {"erc_errors": errors, "erc_warnings": warnings,
                         "error_types": kinds}


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


def gate_gerbers(gerber_dir):
    """G5: every expected layer file exists, parses, has apertures + ops."""
    details = {}
    ok = True
    files = os.listdir(gerber_dir) if os.path.isdir(gerber_dir) else []
    for layer in EXPECTED_LAYERS:
        fname = layer.replace(".", "_")
        match = [f for f in files if fname in f]
        if not match:
            ok = False
            details[layer] = "missing"
            continue
        ap, ops = parse_gerber(os.path.join(gerber_dir, match[0]))
        details[layer] = {"apertures": ap, "ops": ops,
                          "file": match[0]}
        if ap == 0 or ops == 0:
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
        ("G5_gerber", gate_gerbers, (args.gerber_dir,)),
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
