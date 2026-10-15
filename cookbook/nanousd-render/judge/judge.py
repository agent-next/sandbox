#!/usr/bin/env python3
"""Judge engine for cookbook/nanousd-render.

Grades one USDA artifact through four gates (see ../SPEC.md):

  G1 structure     both readers (nanousd C API via nanousd_dump, and
                   usd-core via an out-of-process dumper) parse the file
                   and see a conforming scene; composition arcs and
                   plugin schemas are rejected as the parsers report
                   them, plus a formatting-proof text net
  G2 agreement     the two independent readers agree exactly on the prim
                   set under /World, mesh paths, point counts, world
                   transforms, world bboxes
  G3 render        nanousd-opengl-renderer renders 640x480 headlessly
                   on llvmpipe, byte-deterministically, and the image
                   is not empty
  G4 oracle        closed-form numpy pinhole projection predicts where
                   every mesh must land; the rendered pixels inside each
                   predicted rectangle carry that mesh's displayColor

The artifact is only ever parsed and rendered by out-of-process helpers
(the C dumper, the usd-core dumper, the C renderer driver): a crafted
file cannot touch the judge's own process, and every judged quantity is
re-derived by the judge from those helpers' output.

Run through grade.sh (which resolves every binary path); direct use:
    python3 judge.py <artifact.usda> [--seed N] [--json out.json]

Exit 0 only if every gate passes. No randomness anywhere (the --seed
flag exists for interface uniformity and is echoed into the verdict).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

# ---------------------------------------------------------------------------
# pinned paths (written by setup.sh; NANOUSD_RENDER_PREFIX overrides for
# pre-provisioned environments)

PREFIX = os.environ.get("NANOUSD_RENDER_PREFIX",
                        os.path.expanduser("~/.nanousd-render"))
NANOUSD_DUMP = os.path.join(PREFIX, "bin", "nanousd_dump")
RENDER_ONCE = os.path.join(PREFIX, "bin", "render_once")
NANOUSD_LIB = os.path.join(PREFIX, "build", "nanousd", "Release", "libnanousd.so")

W, H = 640, 480

MIN_MESH_POINTS = 12
MIN_COLOR_BRIGHTNESS = 0.45       # L2 norm of displayColor
MIN_COLOR_CHANNEL = 0.05          # per channel (oracle divides by it)
MIN_COLOR_PAIR_DISTANCE = 0.30    # L2 distance between any two meshes' colors
APERTURE_RATIO_LO, APERTURE_RATIO_HI = 4 / 3 * 0.95, 4 / 3 * 1.05
MIN_RECT_AREA_PX = 400.0
MIN_ONSCREEN_FRAC = 0.90
MAX_RECT_OVERLAP_FRAC = 0.10      # of the smaller rectangle's area
# The pinned raster shader is exactly multiplicative in displayColor
# (color = displayColor * (ambient+key+fill+rim), gamma 2.2 at output),
# so in LINEAR space the oracle checks proportionality, not absolute
# color: a fitted illuminance k per mesh, a per-channel deviation from
# k, and decisiveness vs every other graded mesh's color.
K_MIN, K_MAX = 0.06, 1.30         # plausible linear illuminance band
PROP_TOL = 0.35                   # max |med_lin/c - k| / k, own color
PROP_MARGIN = 1.6                 # other colors must fit worse by this
PROP_OTHER_MIN = 0.30             # ... and at least this much worse
MIN_RENDERED_FRAC = 0.01          # pixels differing from the background

FORBIDDEN_TOKENS_COMPACT = (
    "references=", "prependreferences=", "appendreferences=",
    "payload=", "prependpayload=", "appendpayload=",
    "sublayers=", "inherits=", "prependinherits=", "appendinherits=",
    "variantsets=", "variantset=", "instanceable=true",
    "relmaterial:binding",
    # raw matrix transforms keep the two readers on separate code paths
    # (SPEC.md artifact rules)
    "xformOp:transform",
)
SCHEMA_FORBIDDEN_PREFIXES = ("SkelRoot", "PhysicsScene", "PhysicsRigidBody")


def text_arc_scan(text: str) -> list[str]:
    """Forbidden composition arcs by text, robust to formatting: comments
    stripped, ALL whitespace removed, compact tokens searched. The parsed
    arc report (usdcore_dump.py) is authoritative; this second net catches
    arcs a parser might silently ignore -- and a mutant smuggles one past
    the old spaced-token scan (``inherits=[</Nope>]``), which is exactly
    the cheat this closes."""
    body = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    compact = "".join(body.split())
    return [tok for tok in FORBIDDEN_TOKENS_COMPACT if tok in compact]


# ---------------------------------------------------------------------------
# helpers

def fail(gate: str, code: str, detail: str) -> dict:
    return {"gate": gate, "pass": False, "code": code, "detail": detail}


def timing() -> dict:
    return {"wall_s": round(time.time() - T0, 2)}


T0 = time.time()


def run(argv: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, **kw)


# ---------------------------------------------------------------------------
# usd-core side (out of process: the artifact is never parsed in the
# judge's own process -- see usdcore_dump.py)

USDCORE_DUMP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "usdcore_dump.py")
SUBPROC_TIMEOUT_S = {"nanousd": 120, "usdcore": 120, "render": 300}


def _run_guarded(argv: list[str], timeout_s: float, **kw
                 ) -> tuple[int, str, str, bool]:
    """run() with a timeout: a hung reader is an error, never a hang."""
    try:
        p = run(argv, timeout=timeout_s, **kw)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout_s:g}s", True
    return p.returncode, p.stdout or "", p.stderr or "", False


def read_usdcore(path: str) -> dict:
    """Open with usd-core IN ITS OWN PROCESS; return {'error': ...} or the
    record usdcore_dump.py prints (same shape as the nanousd dump, plus
    the parser-reported forbidden_arcs list)."""
    rc, out, err, timed_out = _run_guarded(
        [sys.executable, USDCORE_DUMP, path], SUBPROC_TIMEOUT_S["usdcore"])
    if timed_out or rc != 0:
        return {"error": f"usdcore_dump exited {rc}: "
                         f"{(err or out).strip()[:200]}"}
    try:
        return json.loads(out)
    except ValueError as e:
        return {"error": f"usdcore_dump emitted invalid JSON: {e}"}


# ---------------------------------------------------------------------------
# nanousd side

def read_nanousd(path: str) -> dict:
    env = dict(os.environ)
    env["NANOUSD_BACKEND"] = NANOUSD_LIB
    rc, out, err, timed_out = _run_guarded(
        [NANOUSD_DUMP, NANOUSD_LIB, path], SUBPROC_TIMEOUT_S["nanousd"],
        env=env)
    if timed_out or rc != 0:
        try:
            errmsg = json.loads(out).get("error", err.strip()[:200])
        except (ValueError, AttributeError):
            errmsg = err.strip()[:200] or f"exit {rc}"
        return {"error": f"nanousd_dump: {errmsg}"}
    try:
        rec = json.loads(out)
    except ValueError as e:
        return {"error": f"nanousd_dump emitted invalid JSON: {e}"}
    # nanousd_dump wraps each attribute as {"type": t, "value": v}; unwrap to
    # the plain value so the record has the same shape as the usd-core side
    # (attributes with a null payload are dropped there, so drop them here).
    for prim in rec.get("prims", []):
        flat_attribs = {}
        for name, spec in prim.get("attribs", {}).items():
            value = spec.get("value") if isinstance(spec, dict) else spec
            if value is not None:
                flat_attribs[name] = value
        prim["attribs"] = flat_attribs
    return rec


# ---------------------------------------------------------------------------
# world transform math

def world_matrix(prim, prims_by_path):
    """Compose the WORLD transform of one prim from the LOCAL transforms
    every reader resolves, walking up the ancestor chain and honouring
    ``resetXformStack!`` exactly as the readers do (see SPEC.md).

    Both nanousd_dump (local transforms) and usd-core dumper can report a
    local matrix; if a record ever carries an already-composed
    ``world_xform`` it is used unchanged (and cross-checked below). The
    chain order is parent-first: world = L(anc) @ ... @ L(parent) @ L(self).
    Each flat array is USD row-major ROW-vector (p' = p * G): compose in
    that layout and transpose at the end for column-vector math.
    """
    flat = prim.get("local_xform") or prim.get("xform")
    if flat is None or len(flat) != 16:
        return [1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0]
    reset = bool(prim.get("reset_xform_stack"))
    chain = [prim]
    cur = prim
    while True:
        parent_path = cur["path"].rsplit("/", 1)[0]
        if not parent_path or parent_path not in prims_by_path:
            break
        p = prims_by_path[parent_path]
        if reset or bool(p.get("reset_xform_stack")):
            break
        chain.append(p)
        cur = p
    for p in chain:
        flat = p.get("local_xform") or flat
    # chain is self-first; compose world = L(parent) @ ... @ L(self)
    acc = [[1.0, 0.0, 0.0, 0.0],
           [0.0, 1.0, 0.0, 0.0],
           [0.0, 0.0, 1.0, 0.0],
           [0.0, 0.0, 0.0, 1.0]]
    for p in reversed(chain):
        f = p.get("local_xform")
        if f is None or len(f) != 16:
            continue
        G = [[f[r * 4 + c] for c in range(4)] for r in range(4)]
        acc = rowvec_mul(acc, G)
    # column-vector M = transpose of the row-vector result
    return [acc[c][r] for r in range(4) for c in range(4)]


def rowvec_mul(a, b):
    """4x4 @ 4x4 in USD row-vector layout (p' = p * (a*b) = (p*a)*b)."""
    out = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            out[i][j] = sum(a[i][k] * b[k][j] for k in range(4))
    return out


def annotate_world_xforms(prims):
    """Add a composed 'world_xform' to every prim, and 'has_reset' for a
    resetXformStack anywhere on its ancestor chain (the reason its local
    transform IS its world transform)."""
    by_path = {p["path"]: p for p in prims}
    for p in prims:
        p["world_xform"] = world_matrix(p, by_path)
        cur, reset = p, False
        while cur["path"] in by_path:
            reset = reset or bool(cur.get("reset_xform_stack"))
            parent_path = cur["path"].rsplit("/", 1)[0]
            cur = by_path.get(parent_path)
            if cur is None or parent_path not in by_path:
                break
        p["has_reset"] = reset
    return prims


def flatten_prims(record: dict):
    """nanousd_dump emits a tree; flatten to a list of prim dicts."""
    out = []
    def rec(prim):
        out.append(prim)
        for ch in prim.get("children", []):
            rec(ch)
    for p in record.get("prims", []):
        rec(p)
    return out


# ---------------------------------------------------------------------------
# G1/G2 checks

def mesh_entries(prims, reader: str):
    meshes = [p for p in prims
              if p["type"] == "Mesh" and p["path"].startswith("/World/")]
    cameras = [p for p in prims
               if p["type"] == "Camera" and p["path"].startswith("/World/")]
    lights = [p for p in prims
              if p["type"] in ("DistantLight", "DomeLight", "RectLight")
              and p["path"].startswith("/World/")]
    return meshes, cameras, lights


def struct_check(prims, reader: str):
    """G1 for one reader. Returns (errors, meshes, camera). Composition
    arcs and forbidden schemas are checked from the parsed records in
    main() (formatting cannot hide what a parser reports)."""
    errs = []
    meshes, cameras, lights = mesh_entries(prims, reader)

    # SPEC: exactly 5 meshes, exactly 1 camera
    if len(meshes) < 5:
        errs.append(fail("G1", f"{reader}.too_few_meshes",
                         f"{reader}: {len(meshes)} meshes under /World, need exactly 5"))
        return errs, meshes, None
    if len(meshes) > 5:
        errs.append(fail("G1", f"{reader}.too_many_meshes",
                         f"{reader}: {len(meshes)} meshes under /World, need exactly 5"))
    if len(cameras) < 1:
        errs.append(fail("G1", f"{reader}.no_camera",
                         f"{reader}: no Camera prim under /World"))
        return errs, meshes, None
    if len(cameras) > 1:
        errs.append(fail("G1", f"{reader}.too_many_cameras",
                         f"{reader}: {len(cameras)} Camera prims under /World, "
                         f"need exactly 1"))
    if len(lights) < 1:
        errs.append(fail("G1", f"{reader}.no_light",
                         f"{reader}: no DistantLight/DomeLight/RectLight under /World"))
    else:
        # SPEC: at least one qualifying light with authored intensity > 0
        bright = [l for l in lights
                  if isinstance(l["attribs"].get("inputs:intensity"),
                                (int, float))
                  and l["attribs"]["inputs:intensity"] > 0]
        if not bright:
            errs.append(fail("G1", f"{reader}.light_intensity",
                f"{reader}: no light with authored inputs:intensity > 0"))

    for m in meshes:
        pts = m["attribs"].get("points")
        npts = len(pts) // 3 if isinstance(pts, list) else 0
        if npts < MIN_MESH_POINTS:
            errs.append(fail("G1", f"{reader}.points",
                f"{reader}: {m['path']} has {npts} points, need >= {MIN_MESH_POINTS}"))
        for need in ("faceVertexCounts", "faceVertexIndices"):
            if not isinstance(m["attribs"].get(need), list):
                errs.append(fail("G1", f"{reader}.{need}",
                    f"{reader}: {m['path']} missing {need}"))
        col = m["attribs"].get("primvars:displayColor")
        if not (isinstance(col, list) and len(col) >= 3):
            errs.append(fail("G1", f"{reader}.displayColor",
                f"{reader}: {m['path']} missing constant displayColor"))
        else:
            rgb = col[:3]
            norm = math.sqrt(sum(c * c for c in rgb))
            if norm < MIN_COLOR_BRIGHTNESS:
                errs.append(fail("G1", f"{reader}.color_dark",
                    f"{reader}: {m['path']} displayColor L2 {norm:.3f} < {MIN_COLOR_BRIGHTNESS}"))

    # pairwise color distance
    cols = [(m["path"], m["attribs"].get("primvars:displayColor", [])[:3])
            for m in meshes]
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            if not cols[i][1] or not cols[j][1]:
                continue
            d = math.sqrt(sum((a - b) ** 2
                              for a, b in zip(cols[i][1], cols[j][1])))
            if d < MIN_COLOR_PAIR_DISTANCE:
                errs.append(fail("G1", f"{reader}.colors_close",
                    f"{reader}: {cols[i][0]} vs {cols[j][0]} color distance "
                    f"{d:.3f} < {MIN_COLOR_PAIR_DISTANCE}"))

    cam = cameras[0]
    camattr = cam["attribs"]
    for k in ("focalLength", "horizontalAperture", "verticalAperture"):
        if not isinstance(camattr.get(k), (int, float)):
            errs.append(fail("G1", f"{reader}.camera_intrinsics",
                f"{reader}: camera missing authored {k}"))
    cr = camattr.get("clippingRange")
    if not (isinstance(cr, list) and len(cr) == 2):
        errs.append(fail("G1", f"{reader}.clippingRange",
            f"{reader}: camera missing authored clippingRange (near, far)"))
    if isinstance(camattr.get("horizontalAperture"), (int, float)) and \
       isinstance(camattr.get("verticalAperture"), (int, float)):
        ratio = camattr["horizontalAperture"] / camattr["verticalAperture"]
        if not (APERTURE_RATIO_LO <= ratio <= APERTURE_RATIO_HI):
            errs.append(fail("G1", f"{reader}.aperture_ratio",
                f"{reader}: aperture ratio {ratio:.3f} outside 4:3 +/-5%"))

    # forbidden plugin schemas, from each reader's own parsed prim types
    for p in prims:
        if p["type"].startswith(SCHEMA_FORBIDDEN_PREFIXES):
            errs.append(fail("G1", f"{reader}.forbidden_schema",
                f"{reader}: {p['path']} has plugin schema type "
                f"'{p['type']}'"))

    return errs, meshes, cam


def compare_readers(nn_flat, uc_prims):
    """G2: the two readers must agree on the full prim set under /World
    (a prim one reader silently drops is a divergence whatever its type),
    then on mesh paths, point counts, point values, judge-composed WORLD
    transforms (from each reader's own LOCAL chain, resetXformStack
    honoured) and judge-computed world bboxes."""
    annotate_world_xforms(nn_flat)
    annotate_world_xforms(uc_prims)
    errs = []
    nn_all = sorted(p["path"] for p in nn_flat
                    if p["path"].startswith("/World/"))
    uc_all = sorted(p["path"] for p in uc_prims
                    if p["path"].startswith("/World/"))
    if nn_all != uc_all:
        only_nn = sorted(set(nn_all) - set(uc_all))
        only_uc = sorted(set(uc_all) - set(nn_all))
        errs.append(fail("G2", "prim_paths",
            f"prim path sets differ: only nanousd={only_nn} "
            f"only usd-core={only_uc}"))

    nn_meshes, nn_cams, _ = mesh_entries(nn_flat, "nanousd")
    uc_meshes, uc_cams, _ = mesh_entries(uc_prims, "usd-core")

    nn_paths = sorted(m["path"] for m in nn_meshes)
    uc_paths = sorted(m["path"] for m in uc_meshes)
    if nn_paths != uc_paths:
        only_nn = sorted(set(nn_paths) - set(uc_paths))
        only_uc = sorted(set(uc_paths) - set(nn_paths))
        errs.append(fail("G2", "mesh_paths",
            f"mesh path sets differ: only nanousd={only_nn} only usd-core={only_uc}"))
        return errs

    nn_by_path = {m["path"]: m for m in nn_meshes}
    uc_by_path = {m["path"]: m for m in uc_meshes}
    for path in nn_paths:
        nn, uc = nn_by_path[path], uc_by_path[path]
        nn_pts = nn["attribs"].get("points") or []
        uc_pts = uc["attribs"].get("points") or []
        if len(nn_pts) != len(uc_pts):
            errs.append(fail("G2", "point_count",
                f"{path}: point count nanousd={len(nn_pts)//3} "
                f"usd-core={len(uc_pts)//3}"))
            continue
        try:
            worst = max(abs(a - b) for a, b in zip(nn_pts, uc_pts))
        except (TypeError, ValueError):
            worst = float("inf")
        if worst > 1e-6:
            errs.append(fail("G2", "points_values",
                f"{path}: points differ by {worst:.3g} between readers"))
        # world transform: judge-composed from each reader's own LOCAL
        # chain (both dumps emit local transforms; resetXformStack honoured)
        nn_w, uc_w = nn["world_xform"], uc["world_xform"]
        d_xf = max(abs(a - b) for a, b in zip(nn_w, uc_w))
        if d_xf > 1e-9:
            errs.append(fail("G2", "world_xform",
                f"{path}: world transform differs by {d_xf:.3g} > 1e-9"))
        # cross-check the judge's composition against each reader's own
        # resolved world transform, when the reader reports one -- a
        # composition bug would show up here, not as a silent pass
        for who, prim, composed in (("nanousd", nn, nn_w),
                                    ("usd-core", uc, uc_w)):
            own = prim.get("reader_world_xform")
            if own is None or len(own) != 16:
                continue
            d_own = max(abs(a - b) for a, b in zip(own, composed))
            if d_own > 1e-9:
                errs.append(fail("G2", "world_xform",
                    f"{path}: judge-composed world transform differs from "
                    f"{who}'s own resolved world matrix by {d_own:.3g} "
                    f"> 1e-9"))
        # world bbox computed by the judge from each reader's own data
        bb_nn = world_bbox(nn_pts, nn_w)
        bb_uc = world_bbox(uc_pts, uc_w)
        if bb_nn is None or bb_uc is None:
            errs.append(fail("G2", "bbox",
                f"{path}: cannot compute world bbox from a reader"))
            continue
        d_bb = max(abs(a - b) for a, b in zip(bb_nn, bb_uc))
        if d_bb > 1e-6:
            errs.append(fail("G2", "bbox",
                f"{path}: world bbox differs by {d_bb:.3g} > 1e-6 "
                f"(nanousd={['%.3f' % v for v in bb_nn]} "
                f"usd-core={['%.3f' % v for v in bb_uc]})"))

    # camera agreement (judge-composed world transform + intrinsics)
    if nn_cams and uc_cams:
        d_cam = max(abs(a - b) for a, b in zip(nn_cams[0]["world_xform"],
                                               uc_cams[0]["world_xform"]))
        if d_cam > 1e-9:
            errs.append(fail("G2", "camera_xform",
                f"camera world transform differs by {d_cam:.3g} > 1e-9"))
        for k in ("focalLength", "horizontalAperture", "verticalAperture"):
            a = nn_cams[0]["attribs"].get(k)
            b = uc_cams[0]["attribs"].get(k)
            if a is None or b is None or abs(float(a) - float(b)) > 1e-9:
                errs.append(fail("G2", "camera_intrinsics",
                    f"camera {k} disagrees: nanousd={a} usd-core={b}"))
    return errs


def world_bbox(flat_points, colmat_flat):
    """AABB of the world-transformed points; None if not computable.

    colmat_flat is a COLUMN-vector matrix (flat[r*4+c] = M[r][c], as
    world_xform is stored: p' = M @ p)."""
    if len(flat_points) < 3 or len(flat_points) % 3:
        return None
    pts = [tuple(flat_points[i:i + 3]) for i in range(0, len(flat_points), 3)]
    corners = []
    M = [[colmat_flat[r * 4 + c] for c in range(4)] for r in range(4)]
    for p in pts:
        corners.append(tuple(
            sum(p[k] * M[k][j] for k in range(3)) + M[3][j] for j in range(3)))
    return (min(c[0] for c in corners), min(c[1] for c in corners),
            min(c[2] for c in corners),
            max(c[0] for c in corners), max(c[1] for c in corners),
            max(c[2] for c in corners))


# ---------------------------------------------------------------------------
# main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    verdict = {
        "artifact": os.path.basename(args.artifact),
        "seed": args.seed,
        "gates": {},
        "timing": {},
    }
    gates = verdict["gates"]
    all_pass = True

    # judge integrity baseline: hash judge/ before touching anything
    judge_dir = os.path.dirname(os.path.abspath(__file__))
    judge_hash_before = hashlib.sha256()
    for root, _dirs, files in sorted(os.walk(judge_dir)):
        for f in sorted(files):
            fp = os.path.join(root, f)
            judge_hash_before.update(fp.encode())
            with open(fp, "rb") as fh:
                judge_hash_before.update(fh.read())

    # grade from a temp copy; the artifact never touches the judge
    tmpdir = tempfile.mkdtemp(prefix="nanousd-judge-")
    art = os.path.join(tmpdir, "artifact.usda")
    shutil.copyfile(args.artifact, art)
    text = open(args.artifact, "r", encoding="utf-8", errors="replace").read()

    def setgate(name, ok, info):
        nonlocal all_pass
        gates[name] = {"pass": bool(ok), **info}
        if not ok:
            all_pass = False

    try:
        # ---------------- read by both readers ------------------------
        nn = read_nanousd(art)
        uc = read_usdcore(art)

        if "error" in nn:
            setgate("G1", False, {"errors": [fail("G1", "nanousd.open", nn["error"])]})
            setgate("G2", False, {"errors": [fail("G2", "nanousd.open", "no nanousd record")]})
            setgate("G3", False, {"errors": [fail("G3", "skipped", "G1 failed")]})
            setgate("G4", False, {"errors": [fail("G4", "skipped", "G1 failed")]})
            verdict["pass"] = False
            finish(args, verdict, tmpdir, judge_dir, judge_hash_before)
            return 1
        if "error" in uc:
            setgate("G1", False, {"errors": [fail("G1", "usdcore.open", uc["error"])]})
            setgate("G2", False, {"errors": [fail("G2", "usdcore.open", "no usd-core record")]})
            setgate("G3", False, {"errors": [fail("G3", "skipped", "G1 failed")]})
            setgate("G4", False, {"errors": [fail("G4", "skipped", "G1 failed")]})
            verdict["pass"] = False
            finish(args, verdict, tmpdir, judge_dir, judge_hash_before)
            return 1

        nn_flat = flatten_prims(nn)
        errs1, meshes, cam = struct_check(nn_flat, "nanousd")
        errs1b, uc_meshes, uc_cam = struct_check(uc["prims"], "usd-core")
        # composition arcs: parser-reported first, then the formatting-
        # proof text net (both below G1; the artifact cannot forge these
        # from inside a subprocess)
        arc_errs = [fail("G1", "forbidden_arc",
                         f"composition arc reported by the parser at "
                         f"{a['where']}: {a['arc']} = {a['detail']}")
                    for a in uc.get("forbidden_arcs", [])]
        arc_errs += [fail("G1", "forbidden_arc",
                          f"forbidden composition arc in file: '{tok}'")
                     for tok in text_arc_scan(text)]
        g1_ok = not errs1 and not errs1b and not arc_errs
        setgate("G1", g1_ok, {"errors": errs1 + errs1b + arc_errs,
                              "nanousd_meshes": len(meshes),
                              "usdcore_meshes": len(uc_meshes)})

        errs2 = compare_readers(nn_flat, uc["prims"])
        setgate("G2", not errs2, {"errors": errs2,
                                  "prims_compared": sum(
                                      1 for p in nn_flat
                                      if p["path"].startswith("/World/")),
                                  "meshes_compared": len(meshes)})

        if not (g1_ok and not errs2):
            setgate("G3", False, {"errors": [fail("G3", "skipped", "G1/G2 failed")]})
            setgate("G4", False, {"errors": [fail("G4", "skipped", "G1/G2 failed")]})
            verdict["pass"] = False
            finish(args, verdict, tmpdir, judge_dir, judge_hash_before)
            return 1

        # ---------------- G3: render -------------------------------
        out_png = None
        if args.json:
            out_png = os.path.join(os.path.dirname(os.path.abspath(args.json)),
                                   "render.png")
        g3, render_ctx = gate_render(art, nn_flat, cam, tmpdir, out_png)
        setgate("G3", g3["pass"], g3)

        # ---------------- G4: projection oracle ----------------------
        if not g3["pass"]:
            setgate("G4", False, {"errors": [fail("G4", "skipped", "G3 failed")]})
        else:
            g4 = gate_oracle(nn_flat, cam, render_ctx)
            setgate("G4", g4["pass"], g4)

        verdict["pass"] = all_pass
        integrity_ok = finish(args, verdict, tmpdir, judge_dir,
                              judge_hash_before)
        return 0 if (all_pass and integrity_ok) else 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def finish(args, verdict, tmpdir, judge_dir, hash_before):
    # judge integrity: judge/ tree must be untouched by the graded run --
    # and the check FAILS CLOSED: a changed judge tree forces pass:false
    # and a non-zero exit, whatever the gates said (SPEC.md).
    h = hashlib.sha256()
    for root, _dirs, files in sorted(os.walk(judge_dir)):
        for f in sorted(files):
            fp = os.path.join(root, f)
            h.update(fp.encode())
            with open(fp, "rb") as fh:
                h.update(fh.read())
    integrity_ok = h.hexdigest() == hash_before.hexdigest()
    verdict["judge_integrity_ok"] = integrity_ok
    if not integrity_ok:
        verdict["pass"] = False
        verdict.setdefault("gates", {})["integrity"] = {
            "pass": False,
            "errors": [fail("integrity", "judge_tree_modified",
                "the judge/ tree changed during the grade: hashes differ; "
                "the verdict is void")],
        }
    verdict["timing"] = timing()
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
            fh.write("\n")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return integrity_ok


def gate_render(art, nn_flat, cam, tmpdir, out_png=None):
    """G3: headless deterministic 640x480 render; returns context for G4."""
    import numpy as np
    from PIL import Image

    eye, view, proj, fov_v = camera_math(cam, np)
    camfile = os.path.join(tmpdir, "cam.bin")
    with open(camfile, "wb") as fh:
        fh.write(struct.pack("<39f",
                             *(view + proj + list(eye) + [W, H, 0.0, 0.0])))

    env = dict(os.environ)
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["GALLIUM_DRIVER"] = "llvmpipe"
    libs = [os.path.join(PREFIX, "build", "nanousd-opengl-renderer"),
            os.path.join(PREFIX, "build", "nanousd-opengl-renderer", "Release"),
            os.path.join(PREFIX, "build", "nanousd", "Release")]
    env["LD_LIBRARY_PATH"] = ":".join(libs + [env.get("LD_LIBRARY_PATH", "")])
    raw1 = os.path.join(tmpdir, "a.raw")
    raw2 = os.path.join(tmpdir, "b.raw")
    rc, _out, err, timed_out = _run_guarded(
        [RENDER_ONCE, art, camfile, raw1, raw2], SUBPROC_TIMEOUT_S["render"],
        env=env)
    if timed_out or rc != 0:
        return {"pass": False, "errors": [fail("G3", "render_failed",
            (err or f"exit {rc}").strip()[:300])]}, None
    img = np.fromfile(raw1, dtype=np.uint8)
    if img.size != W * H * 4:
        return {"pass": False, "errors": [fail("G3", "shape",
            f"render output {img.size} bytes, want {W*H*4}")]}, None
    img = img.reshape(H, W, 4)

    # byte-determinism is enforced inside render_once (it compares both
    # renders); re-verify here from the two files
    with open(raw2, "rb") as fh:
        if fh.read() != open(raw1, "rb").read():
            return {"pass": False, "errors": [fail("G3", "nondeterministic",
                "two renders differ")]}, None

    corner = img[2:12, 2:12].reshape(-1, 4).mean(axis=0)
    diff = (np.abs(img[:, :, :3].astype(int)
                   - corner[:3].astype(int)).max(axis=2) > 13)
    frac = float(diff.mean())
    if frac < MIN_RENDERED_FRAC:
        return {"pass": False, "errors": [fail("G3", "empty_render",
            f"only {frac*100:.2f}% of pixels differ from background "
            f"(need >= {MIN_RENDERED_FRAC*100:.0f}%)")]}, None
    if out_png:
        try:
            Image.fromarray(img[:, :, :3]).save(out_png)
        except OSError:
            pass
    return {"pass": True, "rendered_frac": round(frac, 4)}, {
        "img": img, "view": view, "proj": proj, "eye": eye, "fov_v": fov_v}


def camera_math(cam, np):
    """World eye + view/proj matrices for the render, derived ONLY from
    the artifact's camera world transform and authored intrinsics.

    Both matrices are 4x4 column-vector matrices (p' = M @ p) serialized
    ROW-MAJOR (flat[r*4+c] = M[r][c]) — the layout measured to be what
    viewer_render_to_rgba consumes (its header comment once said
    "column-major", which was wrong: the row-major transpose is what
    actually draws — verified against a known scene on llvmpipe).

    The reader's world_xform (judge-composed, see world_matrix) is already
    a COLUMN-vector matrix: flat[r*4+c] = M[r][c], so it reshapes straight
    into M @ p with no transpose.
    """
    M = np.array(cam["world_xform"], dtype=float).reshape(4, 4)
    right = M[:3, 0]
    up    = M[:3, 1]
    fwd   = -M[:3, 2]     # USD cameras look down local -Z
    eye   = M[:3, 3]

    # Standard lookAt (column-vector): the third row is -fwd, so a point
    # in front of the camera gets a NEGATIVE view-space z (OpenGL clip
    # convention, w_clip = -z_view). With +fwd the whole scene lands
    # behind the camera and the renderer's frustum culling rejects all
    # of it -- measured on llvmpipe (camz +11..+12 -> empty render).
    view = np.eye(4)
    view[:3, :3] = np.array([right, up, -fwd])
    view[:3, 3] = view[:3, :3] @ -eye

    f  = float(cam["attribs"]["focalLength"])
    ha = float(cam["attribs"]["horizontalAperture"])
    va = float(cam["attribs"]["verticalAperture"])
    near, far = 0.1, 1000.0
    fov_v = 2.0 * math.atan(va / (2.0 * f))
    fov_h = 2.0 * math.atan(ha / (2.0 * f))
    proj = np.zeros((4, 4))
    proj[0, 0] = 1.0 / math.tan(fov_h / 2)
    proj[1, 1] = 1.0 / math.tan(fov_v / 2)
    proj[2, 2] = -(far + near) / (far - near)
    proj[2, 3] = -(2 * far * near) / (far - near)
    proj[3, 2] = -1.0

    flat = lambda m: [float(m[r][c]) for r in range(4) for c in range(4)]
    return [float(x) for x in eye], flat(view), flat(proj), fov_v


def gate_oracle(nn_flat, cam, ctx):
    """G4: closed-form numpy pinhole projection vs the rendered pixels."""
    import numpy as np

    errs = []
    img = ctx["img"].astype(int)
    V = np.array(ctx["view"], dtype=float).reshape(4, 4)
    P = np.array(ctx["proj"], dtype=float).reshape(4, 4)
    VP = P @ V

    meshes, _, _ = mesh_entries(nn_flat, "nanousd")
    rects = {}      # UNCLAMPED: what the math says, even off frame
    clamped = {}    # for pixel sampling only
    colors = {}
    for m in meshes:
        pts = np.array(m["attribs"]["points"], dtype=float).reshape(-1, 3)
        # judge-composed world matrix (column-vector, flat[r*4+c]=M[r][c])
        Mw = np.array(m["world_xform"], dtype=float).reshape(4, 4)
        ones = np.ones((len(pts), 1))
        Pw = (Mw @ np.hstack([pts, ones]).T).T          # keep w for VP

        clip = (VP @ Pw.T).T
        with np.errstate(divide="ignore", invalid="ignore"):
            w = clip[:, 3]
            # in front of the camera: view-space z < 0
            camz = (V @ Pw.T).T[:, 2]
            # NDC in x/y with the sign fixed by w (w = -z_view > 0 in
            # front of the camera; behind-camera points are dropped by
            # the camz test, not silently mirrored into frame)
            ok_w = np.abs(w) > 1e-12
            ndc = np.full_like(clip[:, :2], np.nan)
            np.divide(clip[:, :2], w[:, None], out=ndc, where=ok_w[:, None])
        px = (ndc[:, 0] * 0.5 + 0.5) * W
        py = (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * H   # top-left origin
        ok = np.isfinite(px) & np.isfinite(py) & (camz < -0.05)
        if ok.sum() < 4:
            errs.append(fail("G4", "projection",
                f"{m['path']}: too few projectable points"))
            continue
        rects[m["path"]] = (
            float(px[ok].min()), float(py[ok].min()),
            float(px[ok].max()), float(py[ok].max()))
        clamped[m["path"]] = (
            max(0.0, rects[m["path"]][0]), max(0.0, rects[m["path"]][1]),
            min(float(W), rects[m["path"]][2]),
            min(float(H), rects[m["path"]][3]))
        colors[m["path"]] = m["attribs"]["primvars:displayColor"][:3]

    # ---- per-mesh rectangle rules
    for path, (x0, y0, x1, y1) in rects.items():
        area = (x1 - x0) * (y1 - y0)
        if area < MIN_RECT_AREA_PX:
            errs.append(fail("G4", "rect_small",
                f"{path}: projected area {area:.0f}px^2 < {MIN_RECT_AREA_PX:.0f}"))
        visible = max(0.0, min(W, x1) - max(0.0, x0)) * \
                  max(0.0, min(H, y1) - max(0.0, y0))
        if area > 0 and visible / area < MIN_ONSCREEN_FRAC:
            errs.append(fail("G4", "offscreen",
                f"{path}: only {visible/area*100:.0f}% of projected rect "
                f"on screen (need >= {MIN_ONSCREEN_FRAC*100:.0f}%)"))

    # ---- pairwise overlap rule
    paths = sorted(rects)
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            ax0, ay0, ax1, ay1 = rects[paths[i]]
            bx0, by0, bx1, by1 = rects[paths[j]]
            ow = max(0.0, min(ax1, bx1) - max(ax0, bx0))
            oh = max(0.0, min(ay1, by1) - max(ay0, by0))
            ov = ow * oh
            sa = min((ax1 - ax0) * (ay1 - ay0), (bx1 - bx0) * (by1 - by0))
            if sa > 0 and ov / sa > MAX_RECT_OVERLAP_FRAC:
                errs.append(fail("G4", "rects_overlap",
                    f"{paths[i]} vs {paths[j]}: overlap {ov/sa*100:.0f}% "
                    f"of smaller rect (max {MAX_RECT_OVERLAP_FRAC*100:.0f}%)"))

    # ---- color proportionality in the inner (middle 50%) of each rectangle
    # The pinned raster shader multiplies displayColor by an illuminance and
    # gamma-encodes at output, so the oracle undoes the gamma and checks that
    # the inner-rect median is proportional to the authored displayColor:
    # med_lin ~= k * color with one k per mesh. Background pixels (k ~ 0),
    # wrong colors and swapped colors all break the fit.
    info = {"meshes": {}}
    fits = {}
    for path, (x0, y0, x1, y1) in rects.items():
        ix0 = int(math.ceil(x0 + (x1 - x0) * 0.25))
        iy0 = int(math.ceil(y0 + (y1 - y0) * 0.25))
        ix1 = int(x1 - (x1 - x0) * 0.25)
        iy1 = int(y1 - (y1 - y0) * 0.25)
        if ix1 - ix0 < 2 or iy1 - iy0 < 2:
            errs.append(fail("G4", "inner_rect",
                f"{path}: inner rectangle degenerate"))
            continue
        patch = img[max(0, iy0):iy1, max(0, ix0):ix1, :3].reshape(-1, 3)
        med = np.median(patch, axis=0) / 255.0
        med_lin = med ** 2.2                      # undo the output gamma
        own = np.array(colors[path])
        if min(own) < MIN_COLOR_CHANNEL:
            # G1 already requires brightness; this keeps the fit from
            # dividing by ~0 on a mutant that reaches G4 anyway.
            errs.append(fail("G4", "color",
                f"{path}: displayColor channel < {MIN_COLOR_CHANNEL}"))
            continue
        k = float(np.median(med_lin / own))       # fitted illuminance
        dev = float(np.abs(med_lin / own - k).max() / k)
        fits[path] = (k, dev, med, own, (x0, y0, x1, y1))
        if not (K_MIN <= k <= K_MAX):
            errs.append(fail("G4", "color",
                f"{path}: linear illuminance k={k:.3f} outside "
                f"[{K_MIN}, {K_MAX}] (rect samples background?)"))
        if dev > PROP_TOL:
            errs.append(fail("G4", "color",
                f"{path}: median {med.round(3).tolist()} not proportional "
                f"to authored {own.round(3).tolist()} "
                f"(k={k:.3f}, max dev {dev*100:.0f}% > {PROP_TOL*100:.0f}%)"))

    # ---- decisiveness: every OTHER mesh's color must fit the pixels worse
    for path, (k, dev, med, own, rect) in fits.items():
        med_lin = med ** 2.2
        worst_other = None
        for opath, (_ok, _odev, _omed, oown, _orect) in fits.items():
            if opath == path:
                continue
            k2 = float(np.median(med_lin / oown))
            dev2 = float(np.abs(med_lin / oown - k2).max() / k2) \
                if k2 > 0 else float("inf")
            if worst_other is None or dev2 < worst_other[1]:
                worst_other = (opath, dev2)
        if worst_other:
            opath, dev2 = worst_other
            if not (dev2 - dev >= PROP_OTHER_MIN or
                    (dev > 0 and dev2 / dev >= PROP_MARGIN)):
                errs.append(fail("G4", "color_confusion",
                    f"{path}: pixels fit another mesh's color too "
                    f"(own dev {dev*100:.0f}% vs {opath} dev {dev2*100:.0f}%)"))
        info["meshes"][path] = {
            "rect": [round(v, 1) for v in rect],
            "median_rgb": [round(v, 3) for v in med.tolist()],
            "authored_rgb": [round(v, 3) for v in own.tolist()],
            "illuminance_k": round(k, 3),
            "own_dev": round(dev, 3),
        }
    return {"pass": not errs, "errors": errs, **info}


if __name__ == "__main__":
    sys.exit(main())
