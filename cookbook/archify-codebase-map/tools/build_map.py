#!/usr/bin/env python3
"""build_map.py — regenerate examples/good/httpx-map/diagram.json from the
REAL import graph of the pinned httpx tree.

Nothing here is hand-drawn: the modules and edges come from parsing
$HOME/ground-truth/httpx-0.28.1/httpx/*.py with Python's ast module (the
same derivation the judge uses). The layout is deterministic:

  1. Tarjan SCC condensation gives the dependency bands — entry points on
     top, leaf modules at the bottom, and the mutually-dependent core as
     one band in the middle (its internal edges run laterally, which is
     the honest picture of a cyclic subgraph),
  2. the core band is split into two sub-rows along its internal
     Eades order so no row is wider than the canvas budget,
  3. barycenter sweeps order nodes inside each row to minimise edge
     crossings,
  4. node size is fitted to the rendered label/sublabel/tag text at the
     renderer's own font metrics (textUnits * 0.6 * px + padding),
  5. component type encodes the module role (legend labels are set
     explicitly) and upward feedback edges are drawn dashed.

Usage: python3 tools/build_map.py [--truth ~/ground-truth/httpx-0.28.1]
                                  [--out  examples/good/httpx-map/diagram.json]
"""

import argparse
import ast
import json
import os
import sys

DEMO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TRUTH = os.path.expanduser("~/ground-truth/httpx-0.28.1")
DEFAULT_OUT = os.path.join(
    DEMO_DIR, "examples", "good", "httpx-map", "diagram.json")

HTTPX_COMMIT = "26d48e0634e6ee9cdc0533996db289ce4b430177"

# ---- Role -> archify component type (colour) -------------------------------
ROLE_OF = {
    "__init__": "frontend",
    "_api": "frontend",
    "_main": "frontend",
    "_client": "backend",
    "_models": "database", "_content": "database", "_decoders": "database",
    "_multipart": "database", "_urls": "database", "_urlparse": "database",
    "_status_codes": "database",
    "_config": "messagebus", "_auth": "messagebus",
    "_types": "cloud", "_utils": "cloud", "_exceptions": "cloud",
    "__version__": "cloud",
}
LEGEND_LABELS = {
    "frontend": "public API",
    "backend": "core client",
    "database": "models & codecs",
    "messagebus": "config & auth",
    "cloud": "shared internals",
}

# ---- Font fitting (mirrors archify shared/text-fit.mjs) ---------------------
FONT_PREFERRED = {"label": 11, "sublabel": 9, "tag": 7}
CHAR_EM = 0.6
TEXT_PAD = 8
SIDE_PAD = 14
NODE_H = 64
GAP_X = 64
GAP_Y = 46
MARGIN = 40
MAX_ROW = 6          # max nodes per visual row inside a band
LANE_PITCH = 9       # px between horizontal jog lanes inside a gap corridor
STUB = 10            # px of straight stub before/after a port


def fit_width(text, px):
    return len(text) * px * CHAR_EM + TEXT_PAD


def component_size(label, sublabel, tag):
    w = max(
        fit_width(label, FONT_PREFERRED["label"]),
        fit_width(sublabel, FONT_PREFERRED["sublabel"]),
        fit_width(tag, FONT_PREFERRED["tag"]),
    )
    return int(round(w + 2 * SIDE_PAD)), NODE_H


# ---- Real import graph (identical derivation to judge/check_gates.py) -------

def module_graph(truth_root):
    pkg = os.path.join(truth_root, "httpx")
    mods = sorted(p[:-3] for p in os.listdir(pkg) if p.endswith(".py"))
    mset = set(mods)
    edges = set()
    for fname in os.listdir(pkg):
        if not fname.endswith(".py"):
            continue
        src = fname[:-3]
        with open(os.path.join(pkg, fname), encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=fname)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("httpx."):
                        d = a.name.split(".")[1]
                        if d in mset:
                            edges.add((src, d))
            elif isinstance(node, ast.ImportFrom) and (node.level or 0) >= 1:
                if node.module:
                    d = node.module.split(".")[0]
                    if d in mset:
                        edges.add((src, d))
                else:
                    for a in node.names:
                        if a.name in mset:
                            edges.add((src, a.name))
    return mods, edges


# ---- Graph machinery --------------------------------------------------------

def tarjan_scc(mods, edges):
    adj = {m: [] for m in mods}
    for a, b in edges:
        adj[a].append(b)
    index, low, onstk, stk, sccs = {}, {}, set(), [], []
    counter = [0]
    sys.setrecursionlimit(10000)

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stk.append(v)
        onstk.add(v)
        for w in adj[v]:
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in onstk:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            scc = []
            while True:
                w = stk.pop()
                onstk.discard(w)
                scc.append(w)
                if w == v:
                    break
            sccs.append(sorted(scc))

    for m in mods:
        if m not in index:
            strong(m)
    return sccs


def eades_order(mods, edges):
    """Greedy feedback order: sinks appended right, sources prepended left,
    else the node with the best forward degree balance."""
    out_adj = {m: set() for m in mods}
    in_adj = {m: set() for m in mods}
    for a, b in edges:
        if a != b:
            out_adj[a].add(b)
            in_adj[b].add(a)
    left, right = [], []
    alive = set(mods)
    while alive:
        moved = True
        while moved:
            moved = False
            for m in sorted(alive):
                if not (out_adj[m] & alive):
                    right.append(m)
                    alive.discard(m)
                    moved = True
                    break
            if moved:
                continue
            for m in sorted(alive):
                if not (in_adj[m] & alive):
                    left.append(m)
                    alive.discard(m)
                    moved = True
                    break
        if alive and not moved:
            pick = max(sorted(alive), key=lambda m: (
                len(out_adj[m] & alive) - len(in_adj[m] & alive), m))
            left.append(pick)
            alive.discard(pick)
    return left + right[::-1]


def crossings(order_a, order_b, edges_ab):
    pos_b = {m: i for i, m in enumerate(order_b)}
    seq = sorted((order_a.index(a), pos_b[b]) for a, b in edges_ab
                 if a in order_a and b in pos_b)
    return sum(1 for i in range(len(seq)) for j in range(i + 1, len(seq))
               if seq[i][1] > seq[j][1])


def barycenter_sweep(rows, edges, sweeps=32):
    edge_list = sorted(edges)
    pos = {m: i for row in rows for i, m in enumerate(row)}
    for s in range(sweeps):
        rng = range(len(rows)) if s % 2 == 0 else range(len(rows) - 1, -1, -1)
        for l in rng:
            row = rows[l]
            if len(row) < 2:
                continue
            keys = {}
            for m in row:
                nb = []
                for a, b in edge_list:
                    if b == m:
                        nb.append(pos[a])
                    elif a == m:
                        nb.append(pos[b])
                keys[m] = (sum(nb) / len(nb)) if nb else float(pos[m])
            row.sort(key=lambda m: (keys[m], m))
            for i, m in enumerate(row):
                pos[m] = i
    return rows


def swap_pass(rows, edges, passes=8):
    """Swap adjacent nodes while the adjacent-row crossing count drops."""
    for _ in range(passes):
        changed = False
        for l, row in enumerate(rows):
            for i in range(len(row) - 1):
                def xcount():
                    n = 0
                    if l > 0:
                        n += crossings(row, rows[l - 1],
                                       [(a, b) for a, b in edges
                                        if b in row and a in rows[l - 1]])
                    if l + 1 < len(rows):
                        n += crossings(row, rows[l + 1],
                                       [(a, b) for a, b in edges
                                        if a in row and b in rows[l + 1]])
                    return n
                before = xcount()
                row[i], row[i + 1] = row[i + 1], row[i]
                if xcount() > before:
                    row[i], row[i + 1] = row[i + 1], row[i]
                else:
                    changed = True
        if not changed:
            break
    return rows


def band_split(members, edges):
    """Split a wide band into <=MAX_ROW sub-rows minimising the number of
    edges that stay inside one sub-row (those need lateral arc routes).
    For <= 12 members the exact optimum over subset sizes is enumerable."""
    import itertools
    members = sorted(members)
    n_rows = (len(members) + MAX_ROW - 1) // MAX_ROW
    if n_rows == 1:
        return [members]
    # 2-way split (the only case this demo needs: 11 -> 6+5)
    best, best_cost = None, None
    for size in (MAX_ROW, len(members) - MAX_ROW):
        if size <= 0 or size >= len(members):
            continue
        for combo in itertools.combinations(members, size):
            a_set = set(combo)
            b_set = set(members) - a_set
            cost = sum(1 for a, b in edges
                       if (a in a_set and b in a_set)
                       or (a in b_set and b in b_set))
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = (sorted(a_set), sorted(b_set))
    row_a, row_b = best
    # Orient the pair so internal edges mostly run top->bottom (fewer
    # upward feedback arcs), ties broken deterministically.
    fwd = sum(1 for a, b in edges if a in row_a and b in row_b)
    rev = sum(1 for a, b in edges if a in row_b and b in row_a)
    if rev > fwd:
        row_a, row_b = row_b, row_a
    return [row_a, row_b]


def build(truth_root):
    mods, edges = module_graph(truth_root)
    sccs = tarjan_scc(mods, edges)
    scc_of = {m: i for i, s in enumerate(sccs) for m in s}

    # Condensation DAG: band index = longest import-chain distance from the
    # entry points (top) down to the leaf modules (bottom).
    c_edges = {(scc_of[a], scc_of[b]) for a, b in edges
               if scc_of[a] != scc_of[b]}
    cdepth = {}

    def depth(s):
        if s not in cdepth:
            nxt = [depth(t) for f, t in c_edges if f == s]
            cdepth[s] = 1 + max(nxt) if nxt else 0
        return cdepth[s]

    for i in range(len(sccs)):
        depth(i)
    maxd = max(cdepth.values())
    band_of = {m: maxd - cdepth[scc_of[m]] for m in mods}

    bands = {}
    for m, b in band_of.items():
        bands.setdefault(b, []).append(m)

    rows = []
    for b in range(max(bands) + 1):
        members = bands.get(b, [])
        rows.extend(band_split(members, edges)
                    if len(members) > MAX_ROW else [sorted(members)])

    rows = barycenter_sweep(rows, edges)
    rows = swap_pass(rows, edges)

    row_of = {m: l for l, row in enumerate(rows) for m in row}

    # Which band each row belongs to, and whether it is the band's last row.
    band_rows = {}
    for l, row in enumerate(rows):
        band_rows.setdefault(band_of[row[0]], []).append(l)

    # Corridor planning --------------------------------------------------
    # Gap g is the band between the bottom of row g-1 and the top of row g.
    # Every spanning edge jogs horizontally through the gaps it crosses, on
    # a per-gap lane found by interval coloring; lateral (same-row) edges
    # arc through the corridor above their row (or below, for a band's last
    # sub-row). Lateral arcs of adjacent nodes stay automatic.
    n_rows = len(rows)
    span_edges = [(a, b) for a, b in sorted(edges) if row_of[a] != row_of[b]]
    lateral = {}
    for a, b in sorted(edges):
        if row_of[a] == row_of[b]:
            l = row_of[a]
            pos_in = {m: i for i, m in enumerate(rows[l])}
            ia, ib = sorted([pos_in[a], pos_in[b]])
            last_of_band = band_rows[band_of[a]][-1] == l
            lateral[(a, b)] = (l, ib - ia, last_of_band)

    def band_y(g):
        """Vertical range of gap corridor g (between rows g-1 and g)."""
        top = MARGIN + g * NODE_H + sum(gap_h[i] for i in range(1, g + 1))
        return top - gap_h[g], top

    # width needed by each gap corridor; iterate to fixpoint with lanes
    gap_h = {g: GAP_Y for g in range(n_rows + 1)}
    gap_h[0] = MARGIN
    gap_h[n_rows] = MARGIN

    row_top = {}
    y = MARGIN
    for l, row in enumerate(rows):
        row_top[l] = y
        y += NODE_H + gap_h[l + 1] if l + 1 < len(rows) else NODE_H

    indeg = {m: 0 for m in mods}
    for a, b in edges:
        indeg[b] += 1

    comps = []
    canvas_w = 0
    for l, row in enumerate(rows):
        sizes = {m: component_size(m, f"httpx/{m}.py",
                                   f"{indeg[m]} importers") for m in row}
        total = sum(s[0] for s in sizes.values()) + GAP_X * (len(row) - 1)
        canvas_w = max(canvas_w, total)
        x = -total / 2.0
        for m in row:
            w, h = sizes[m]
            cid = {"__init__": "init__", "__version__": "version__"}.get(
                m, m.lstrip("_"))
            comps.append({
                "id": cid,
                "type": ROLE_OF[m],
                "label": m,
                "sublabel": f"httpx/{m}.py",
                "tag": f"{indeg[m]} importers",
                "pos": [int(round(x)), row_top[l]],
                "size": [w, h],
                "sources": [{"path": f"httpx/{m}.py"}],
            })
            x += w + GAP_X

    for c in comps:
        c["pos"][0] += int(round(canvas_w / 2.0 + MARGIN))

    id_of = {c["sources"][0]["path"].split("/")[-1][:-3]: c["id"]
             for c in comps}
    cx_of = {c["id"]: c["pos"][0] + c["size"][0] / 2 for c in comps}

    # Assign each spanning lateral a corridor lane inside its gap.
    arc_via = {}
    for g, es in gap_arcs.items():
        def lane_key(e):
            ax, bx = sorted([cx_of[id_of[e[0]]], cx_of[id_of[e[1]]]])
            return (ax, -bx)
        for k, (a, b) in enumerate(sorted(es, key=lane_key)):
            l = g if g < len(rows) and lateral[(a, b)][2] is False else g - 1
            base = row_top[l] if l in row_top else row_top[l - 1] + NODE_H
            if lateral[(a, b)][2]:   # below the row
                y = base + NODE_H + ARC_CLEARANCE + 9 * k
            else:                    # above the row
                y = base - ARC_CLEARANCE - 9 * k
            ax, bx = cx_of[id_of[a]], cx_of[id_of[b]]
            arc_via[(a, b)] = [[round(ax), round(y)], [round(bx), round(y)]]

    back = {(a, b) for a, b in edges if row_of[a] > row_of[b]}

    connections = []
    for a, b in sorted(edges):
        conn = {"from": id_of[a], "to": id_of[b]}
        ra, rb = row_of[a], row_of[b]
        if ra > rb:
            # upward feedback edge — dashed, sides chosen by the router
            conn["variant"] = "dashed"
        elif ra == rb and (a, b) in arc_via:
            conn["fromSide"] = "top" if not lateral[(a, b)][2] else "bottom"
            conn["toSide"] = conn["fromSide"]
            conn["via"] = arc_via[(a, b)]
        connections.append(conn)

    spec = {
        "schema_version": 1,
        "diagram_type": "architecture",
        "meta": {
            "title": "httpx 0.28.1 — module dependency map",
            "subtitle": "top-level modules of the httpx package; edges are "
                        "direct imports; colour = module role",
            "output": "diagram.html",
            "repository": {
                "url": "https://github.com/encode/httpx",
                "provider": "github",
                "revision": HTTPX_COMMIT,
            },
            "legend": {
                "mode": "auto",
                "entries": {k: {"label": v} for k, v in LEGEND_LABELS.items()},
            },
        },
        "components": comps,
        "connections": connections,
    }
    return spec, rows, back


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--truth", default=DEFAULT_TRUTH)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()
    spec, rows, back = build(args.truth)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
        f.write("\n")
    xs2 = max(c["pos"][0] + c["size"][0] for c in spec["components"])
    ys2 = max(c["pos"][1] + c["size"][1] for c in spec["components"])
    print(f"[build_map] wrote {args.out}")
    print(f"[build_map] {len(spec['components'])} nodes, "
          f"{len(spec['connections'])} edges ({len(back)} dashed feedback), "
          f"{len(rows)} rows: " + " / ".join(str(len(r)) for r in rows))
    print(f"[build_map] content bounds {xs2}x{ys2}")


if __name__ == "__main__":
    main()
