#!/usr/bin/env python3
"""check_gates.py — gates for the archify-codebase-map demo.

Grades an artifact directory ({diagram.json, diagram.html}) against the
true top-level module dependency graph of the pinned httpx source tree,
which is computed here from first principles with Python's `ast` module.
Nothing about the answer key is hard-coded.

Usage: check_gates.py <artifact_dir> [--json out.json]
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile

ARCHIFY_CLI = os.path.expanduser("~/archify-skill/archify/bin/archify.mjs")
TRUTH_ROOT = os.path.expanduser("~/ground-truth/httpx-0.28.1")
TRUTH_PKG = os.path.join(TRUTH_ROOT, "httpx")
_NODE_MARKER = os.path.expanduser("~/.archify_demo_node")


def node_bin():
    """Prefer the pinned binary setup.sh recorded; fall back to PATH."""
    try:
        with open(_NODE_MARKER) as f:
            p = f.read().strip()
            if p and os.path.isfile(p):
                return p
    except OSError:
        pass
    return "node"

# Grade only stems that look like modules of a real package; the judge
# never grades 'external' type components (those are non-code deps).
PIXEL_STDEV_MIN = 8.0   # blank-page stdev is < 1; real diagram > 20


# ---------------------------------------------------------------------------
# Ground truth from the pinned tree
# ---------------------------------------------------------------------------

def truth_modules():
    """Return sorted top-level module stems of httpx/."""
    return sorted(p[:-3] for p in os.listdir(TRUTH_PKG) if p.endswith(".py"))


def truth_edges(mods):
    """Return {(src_stem, dst_stem)} direct-module import edges of httpx/."""
    mods = set(mods)
    edges = set()
    for fname in os.listdir(TRUTH_PKG):
        if not fname.endswith(".py"):
            continue
        src = fname[:-3]
        path = os.path.join(TRUTH_PKG, fname)
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # `import httpx` / `import httpx.x` (rare inside the pkg)
                    if alias.name.startswith("httpx."):
                        dst = alias.name.split(".")[1]
                        if dst in mods:
                            edges.add((src, dst))
            elif isinstance(node, ast.ImportFrom):
                if (node.level or 0) >= 1:
                    # `from . import x`            -> module is None
                    # `from ._client import Client` -> module == '_client'
                    if node.module:
                        dst = node.module.split(".")[0]
                        if dst in mods:
                            edges.add((src, dst))
                    else:
                        for alias in node.names:
                            if alias.name in mods:
                                edges.add((src, alias.name))
    return edges


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def gates_log(msg):
    print(f"[gates] {msg}", flush=True)


class Verdict:
    def __init__(self):
        self.gates = []

    def add(self, gate, passed, detail):
        self.gates.append({"gate": gate, "passed": bool(passed), "detail": detail})
        mark = "PASS" if passed else "FAIL"
        gates_log(f"{gate:<28} {mark}  {detail}")

    @property
    def ok(self):
        return all(g["passed"] for g in self.gates)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, **kw)


# ---------------------------------------------------------------------------
# Gate implementations
# ---------------------------------------------------------------------------

def gate_valid_and_reproducible(artifact, scratch, v):
    """Gate 1: archify validates diagram.json; diagram.html is reproducible."""
    djson = os.path.join(artifact, "diagram.json")
    if not os.path.isfile(djson):
        v.add("valid+reproducible", False, "diagram.json missing")
        return None
    try:
        with open(djson, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        v.add("valid+reproducible", False, f"diagram.json not valid JSON: {e}")
        return None

    p = run([node_bin(), ARCHIFY_CLI, "validate", "architecture", djson,
             "--repo-root", TRUTH_ROOT])
    if p.returncode != 0:
        tail = (p.stdout + p.stderr).strip().splitlines()
        v.add("valid+reproducible", False,
              f"archify validate failed: {tail[-1] if tail else 'no output'}")
        return None

    rendered = os.path.join(scratch, "rendered.html")
    p = run([node_bin(), ARCHIFY_CLI, "render", "architecture", djson, rendered,
             "--repo-root", TRUTH_ROOT])
    if p.returncode != 0 or not os.path.isfile(rendered):
        tail = (p.stdout + p.stderr).strip().splitlines()
        v.add("valid+reproducible", False,
              f"archify render failed: {tail[-1] if tail else 'no output'}")
        return None

    shipped = os.path.join(artifact, "diagram.html")
    repro_ok = True
    repro_detail = "schema ok; rendered HTML matches shipped HTML"
    if os.path.isfile(shipped):
        with open(shipped, "rb") as f:
            a = f.read()
        with open(rendered, "rb") as f:
            b = f.read()
        if a != b:
            repro_ok = False
            repro_detail = ("diagram.html is not what `archify render` produces "
                            "from diagram.json (hand-edited or stale HTML)")
    else:
        repro_detail = "schema ok; no shipped diagram.html to compare"
    v.add("valid+reproducible", repro_ok, repro_detail)
    # Prefer the shipped HTML when present and valid, else the fresh render:
    # browser gate should exercise what the agent actually shipped when it
    # passes reproducibility; the fresh render stands in when it doesn't.
    return (shipped if (os.path.isfile(shipped) and repro_ok) else rendered)


def gate_renders_clean(html_path, scratch, v):
    """Gate 2: headless Chromium renders with no console errors, non-blank."""
    shot = os.path.join(scratch, "screenshot.png")
    log = os.path.join(scratch, "chrome.log")
    url = f"file://{os.path.abspath(html_path)}"
    cmd = [
        "chromium", "--headless", "--disable-gpu", "--no-sandbox",
        "--hide-scrollbars", "--window-size=1280,800",
        "--virtual-time-budget=8000",
        "--enable-logging=stderr", "--v=0",
        f"--screenshot={shot}", url,
    ]
    with open(log, "w") as lf:
        p = subprocess.run(cmd, text=True, timeout=180,
                           stdout=lf, stderr=subprocess.STDOUT)
    console_errors = []
    try:
        with open(log, "r", errors="replace") as lf:
            for line in lf:
                # Chromium logs JS console errors as "ERROR:CONSOLE(n)"
                if "ERROR:CONSOLE" in line and "Uncaught" in line or \
                   "console.error" in line.lower():
                    console_errors.append(line.strip()[:200])
    except OSError:
        pass
    if p.returncode != 0:
        v.add("renders-clean", False, f"chromium exited {p.returncode}")
        return
    if console_errors:
        v.add("renders-clean", False,
              f"console errors: {console_errors[0]}")
        return
    if not os.path.isfile(shot):
        v.add("renders-clean", False, "no screenshot produced")
        return
    stdev, ncolors = _png_stats(shot)
    if stdev is None:
        v.add("renders-clean", False, "could not decode screenshot")
        return
    if stdev < PIXEL_STDEV_MIN:
        v.add("renders-clean", False,
              f"blank canvas (pixel stdev {stdev:.1f} < {PIXEL_STDEV_MIN})")
        return
    # Stdev is rounded to whole pixels to keep the verdict JSON deterministic:
    # font anti-aliasing can shift the figure by <0.05 between headless runs.
    v.add("renders-clean", True,
          f"no console errors; pixel stdev {stdev:.0f}(>= {PIXEL_STDEV_MIN})")


def _png_stats(path):
    """Return (stdev, n_distinct_colors) of a PNG without third-party libs.

    Uses Chromium's own ImageMagick-free path: rely on zlib + struct to decode
    an 8-bit RGB/RGBA PNG of the form headless Chromium writes (truecolor,
    no interlace). Returns (None, None) if not decodable that way.
    """
    import struct
    import zlib
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    pos = 8
    idat = b""
    w = h = None
    bit_depth = color_type = None
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            w, h, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if w is None or bit_depth != 8 or color_type not in (2, 6):
        return None, None
    raw = zlib.decompress(idat)
    channels = 3 if color_type == 2 else 4
    stride = w * channels
    vals = []
    colors = set()
    prev = bytearray(stride)
    i = 0
    for _y in range(h):
        ftype = raw[i]
        i += 1
        line = bytearray(raw[i:i + stride])
        i += stride
        _unfilter(ftype, line, prev, channels)
        vals.extend(line[::channels])  # R channel of every pixel
        # sample distinct colors every 16th pixel to bound memory/time
        for x in range(0, stride, channels * 16):
            colors.add(bytes(line[x:x + 3]))
        prev = line
    n = len(vals)
    mean = sum(vals) / n
    var = sum((c - mean) ** 2 for c in vals) / n
    return var ** 0.5, len(colors)


def _unfilter(ftype, line, prev, bpp):
    if ftype == 0:
        return
    if ftype == 1:  # Sub
        for x in range(bpp, len(line)):
            line[x] = (line[x] + line[x - bpp]) & 0xFF
    elif ftype == 2:  # Up
        for x in range(len(line)):
            line[x] = (line[x] + prev[x]) & 0xFF
    elif ftype == 3:  # Average
        for x in range(len(line)):
            left = line[x - bpp] if x >= bpp else 0
            line[x] = (line[x] + ((left + prev[x]) >> 1)) & 0xFF
    elif ftype == 4:  # Paeth
        for x in range(len(line)):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            line[x] = (line[x] + pr) & 0xFF


# ---------------------------------------------------------------------------
# Gates 3 & 4: compare nodes/edges to ground truth
# ---------------------------------------------------------------------------

MODULE_TYPE = {"frontend", "backend", "database", "cloud", "security",
               "messagebus", "external"}


def load_diagram(artifact):
    with open(os.path.join(artifact, "diagram.json"), encoding="utf-8") as f:
        return json.load(f)


def graded_components(spec):
    """Components that claim to map onto source files (any type except
    'external') — those we check against the module list."""
    out = []
    for c in spec.get("components", []):
        if c.get("type") == "external":
            continue
        out.append(c)
    return out


def resolve_stem(comp):
    """Identity of a graded node = stem of its first sources path
    (must be httpx/<stem>.py). Returns None if unmappable."""
    srcs = comp.get("sources") or []
    if not srcs:
        return None
    p = srcs[0].get("path", "")
    m = re.fullmatch(r"httpx/([A-Za-z0-9_]+)\.py", p or "")
    if not m:
        return None
    return m.group(1)


def gate_nodes(spec, v):
    mods = set(truth_modules())
    comps = graded_components(spec)

    id_to_stem = {}
    no_source = []
    bad_paths = []
    hallucinated = []
    for c in comps:
        cid = c.get("id", "")
        stem = resolve_stem(c)
        if stem is None:
            no_source.append(cid or "<no id>")
        else:
            id_to_stem[cid] = stem
            if stem not in mods:
                hallucinated.append(f"{cid}->{stem}")
        for s in c.get("sources") or []:
            p = s.get("path", "")
            if p and not os.path.isfile(os.path.join(TRUTH_ROOT, p)):
                bad_paths.append(f"{cid}:{p}")

    stems = [s for s in id_to_stem.values() if s in mods]
    recall = len(set(stems)) / len(mods) if mods else 0.0
    ok = (recall >= 0.9) and not no_source and not hallucinated and not bad_paths
    detail = (f"recall {recall:.2f} ({len(set(stems))}/{len(mods)} modules)"
              f"{'; nodes without sources: ' + ','.join(no_source[:4]) if no_source else ''}"
              f"{'; hallucinated: ' + ','.join(hallucinated[:4]) if hallucinated else ''}"
              f"{'; bad sources: ' + ','.join(bad_paths[:3]) if bad_paths else ''}")
    v.add("node-recall+no-hallucination", ok, detail)
    return id_to_stem, mods


def edge_set(spec, id_to_stem, mods):
    """Claimed directed edges, mapped to (src_stem, dst_stem) tuples.
    Connections that reference unknown module ids are ignored here but
    counted against precision as hallucinated edges."""
    out = set()
    dangling = 0
    for c in spec.get("connections", []) or []:
        a, b = c.get("from", ""), c.get("to", "")
        sa, sb = id_to_stem.get(a), id_to_stem.get(b)
        if sa is None or sb is None:
            dangling += 1
            continue
        if sa != sb:
            out.add((sa, sb))
    return out, dangling


def gate_edges(spec, id_to_stem, mods, v):
    true_edges = truth_edges(mods)
    claimed, dangling = edge_set(spec, id_to_stem, mods)
    if not claimed and not dangling:
        v.add("edge-precision-recall", False,
              "no module-to-module connections claimed")
        return
    correct = claimed & true_edges
    reversed_wrong = {(b, a) for (a, b) in true_edges} & (claimed - correct)
    hallucinated_edges = claimed - correct - reversed_wrong

    total_claimed = len(claimed) + dangling
    precision = len(correct) / total_claimed if total_claimed else 0.0
    recall = len(correct) / len(true_edges)
    ok = (precision >= 0.8 and recall >= 0.6 and not reversed_wrong)
    detail = (f"precision {precision:.2f} ({len(correct)}/{total_claimed} claimed), "
              f"recall {recall:.2f} ({len(correct)}/{len(true_edges)})"
              f"{'; REVERSED: ' + str(len(reversed_wrong)) if reversed_wrong else ''}"
              f"{'; dangling endpoint refs: ' + str(dangling) if dangling else ''}"
              f"{'; hallucinated edges: ' + str(len(hallucinated_edges)) if hallucinated_edges else ''}")
    v.add("edge-precision-recall", ok, detail)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact_dir")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    artifact = os.path.abspath(args.artifact_dir)
    if not os.path.isdir(artifact):
        print(f"[gates] ERROR: not a directory: {artifact}", file=sys.stderr)
        sys.exit(2)
    if not os.path.isfile(ARCHIFY_CLI):
        print(f"[gates] ERROR: archify CLI not found at {ARCHIFY_CLI}; "
              "run judge/setup.sh first", file=sys.stderr)
        sys.exit(2)
    if not os.path.isdir(TRUTH_PKG):
        print(f"[gates] ERROR: ground-truth tree missing at {TRUTH_PKG}; "
              "run judge/setup.sh first", file=sys.stderr)
        sys.exit(2)

    v = Verdict()
    scratch = tempfile.mkdtemp(prefix="archify-judge.")
    try:
        rendered = gate_valid_and_reproducible(artifact, scratch, v)
        if rendered:
            gate_renders_clean(rendered, scratch, v)
            spec = load_diagram(artifact)
            id_to_stem, mods = gate_nodes(spec, v)
            gate_edges(spec, id_to_stem, mods, v)
    finally:
        # scratch holds files written under the judge's watch only; safe to rm
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)

    verdict = {
        "artifact": os.path.basename(artifact.rstrip(os.sep)) or artifact,
        "all_gates_passed": v.ok,
        "gates": v.gates,
    }
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(verdict, f, indent=2)
            f.write("\n")
    print(f"[gates] all_gates_passed = {v.ok}")
    sys.exit(0 if v.ok else 1)


if __name__ == "__main__":
    main()
