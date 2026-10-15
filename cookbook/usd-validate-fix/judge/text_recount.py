#!/usr/bin/env python3
"""Clean-room recount for the usd-validate-fix judge (stdlib only).

Re-derives every judged quantity of SPEC.md gates 2 and 3 straight from
the .usda text with the standard library alone -- no pxr import, no USD
library, no composition -- so the judge never depends on a single stack:

  gate 2   judge/oracle.py recounts the properties with usd-core (pxr);
  gate 2b  this module parses the same file as plain text;
  grade_engine.py fails the grade if the two disagree on any number.

An artifact that somehow influenced the USD machinery feeding the oracle
(most importantly by composing in external layers) could not also change
what this parser reads, and vice versa.  Composed-in geometry would make
the pxr oracle pass while the text parser -- which only ever reads the
artifact's own layer -- still sees nothing, so every quantity it derives
is of the artifact itself and a `subLayers` reference is rejected outright.
It also cross-checks every number it shares with the oracle, so a forged
fact on either side surfaces as a gate error.

The parser deliberately does not implement USD composition, instancing or
subLayers: this artifact is a single self-contained ASCII USD layer.  The
tokenizer handles the pxr-exported ASCII layout (def/over prims with a
trailing `( metadata )`, `type[] name = [...] ( attrMetadata )` values,
`rel` bindings and root-layer metadata) as generic balanced chunks, so it
is not tied to any one generator's spacing.
"""
from __future__ import annotations

import math
import re

# SPEC.md: which material each mesh must be bound to.
BAND_BINDING = "/TrafficCone/Looks/WhitePlastic"
BODY_BINDING = "/TrafficCone/Looks/OrangePlastic"
REQUIRED_BINDINGS = {"/TrafficCone/Band": BAND_BINDING,
                     "/TrafficCone/Body": BODY_BINDING,
                     "/TrafficCone/Base": BODY_BINDING}

METERS_PER_UNIT = 0.01          # the asset is authored in centimetres
UNIT_TOL = 1e-4                 # |norm|-1 tolerance
AREA_TOL = 1e-9                 # cm^2, triangle-fan total cross product
EXTENT_TOL = 1e-5               # cm, extent must contain every point
BBOX_TOL = 1e-6                 # cm, vs the original asset's points bbox
# cross-check tolerances: the oracle computes on pxr float32 values, this
# module on the decimal text parsed as float64 -- allow the rounding gap.
XCHECK_DEV_TOL = 1e-6           # |norm|-1 deviation
XCHECK_BBOX_TOL = 1e-4          # cm

_FLOAT = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
_DEF = re.compile(r"^(def|over)\s+([A-Za-z_]\w*)\s+\"([^\"]+)\"")
_ATTR = re.compile(r"^(?:(?:[A-Za-z_]\w*)\s*(?:\[\])?)?\s*"
                   r"([A-Za-z_][\w:.]*)\s*=")
_REL = re.compile(r"^rel\s+([A-Za-z_][\w:.]*)\s*=\s*(.+)$")
_META = re.compile(r"^\s*(?:(?:prepend|append|delete|reorder|order)\s+)?"
                   r"([A-Za-z_][\w]*)\s*=\s*(.+?)\s*$")
_PATH = re.compile(r"<([^>]+)>")
_QUOTED = re.compile(r'^"([^"]*)"$')


def _strip_comment(line: str) -> str:
    """Cut a trailing //-free '#' comment, keeping '#' inside strings."""
    in_str = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_str = not in_str
        elif ch == "#" and not in_str:
            return line[:i]
    return line


def _chunks(text: str):
    """Yield logical chunks: balanced ()/[] units; {} braces at depth 0.

    pxr's ASCII export keeps a value and its `( metadata )` block on one
    logical statement (possibly across lines), so a chunk ends only when
    ()/[] nesting returns to zero at end-of-line.  `{` and `}` become
    their own chunks at depth 0 (prim scope delimiters).
    """
    buf: list[str] = []
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "#":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == '"':
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == '"':
                    break
                j += 1
            buf.append(text[i:j + 1])
            i = j + 1
            continue
        if ch in "([":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch in ")]":
            depth -= 1
            buf.append(ch)
            i += 1
            continue
        if ch == "\n":
            if depth == 0:
                s = "".join(buf).strip()
                if s:
                    yield s
                buf = []
            else:
                buf.append("\n")        # keep line breaks inside ()/[] blocks
            i += 1
            continue
        buf.append(ch)
        i += 1
    s = "".join(buf).strip()
    if s:
        yield s


def _wrap_meta(text: str) -> dict:
    """Parse a balanced `( key = value ... )` block (for def/attr metadata)."""
    out = {}
    inner = text.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    for line in inner.splitlines():
        mm = _META.match(line.strip())
        if mm:
            key, value = mm.group(1), mm.group(2)
            if key == "apiSchemas":
                out[key] = re.findall(r'"([^"]+)"', value)
            elif key == "interpolation":
                sm = _QUOTED.match(value.strip())
                out[key] = sm.group(1) if sm else None
    return out


def _split_attr_meta(rest: str) -> tuple[str, dict]:
    """Split `value ( attrMetadata )` into (value, metadata dict).

    A `type[] name = [...] ( ... )` value's metadata block sits after the
    closing brace of the array, so it is the outermost trailing `( ... )`.
    """
    rest = rest.strip()
    if not rest.endswith(")"):
        return rest, {}
    depth = 0
    for k in range(len(rest) - 1, -1, -1):
        ch = rest[k]
        if ch == ")":
            depth += 1
        elif ch == "(":
            depth -= 1
            if depth == 0:
                meta = _wrap_meta(rest[k:])
                return rest[:k].strip(), meta
    return rest, {}


def _numbers(value: str, as_int: bool = False):
    pat = re.compile(r"[-+]?\d+") if as_int else _FLOAT
    return [float(t) if not as_int else int(t) for t in pat.findall(value)]


def _triples(value: str):
    nums = _numbers(value)
    if len(nums) % 3:
        nums = nums[: len(nums) - len(nums) % 3]
    return [tuple(nums[i:i + 3]) for i in range(0, len(nums), 3)]


class Mesh:
    def __init__(self, path):
        self.path = path
        self.points = []
        self.counts = []
        self.indices = []
        self.normals = None
        self.normals_interpolation = None
        self.extent = None
        self.binding = None
        self.xform_ops = []          # xformOp:* names in authored order

    def fact(self):
        corners = sum(self.counts)
        dev = 0.0
        if self.normals:
            for n in self.normals:
                if not all(math.isfinite(c) for c in n):
                    dev = float("inf")
                    break
                dev = max(dev, abs(math.sqrt(n[0] ** 2 + n[1] ** 2
                                             + n[2] ** 2) - 1.0))
        return {"points": len(self.points),
                "face_corners": corners,
                "normals": len(self.normals) if self.normals else None,
                "normals_interpolation": self.normals_interpolation,
                "max_normal_dev": round(dev, 9) if self.normals else 0.0,
                "zero_area_faces": self._zero_area(),
                "extent": self._extent_fact(),
                "bound_material": self.binding,
                "xform_ops": list(self.xform_ops)}

    def _extent_fact(self):
        if not self.extent:
            return None
        lo, hi = self.extent
        return [[round(c, 6) for c in lo], [round(c, 6) for c in hi]]

    def _zero_area(self):
        if not (self.points and self.indices):
            return 0
        k = 0
        bad = 0
        for count in self.counts:
            idx = self.indices[k:k + count]
            k += count
            if count < 3:
                continue
            v0 = self.points[idx[0]]
            acc = (0.0, 0.0, 0.0)
            for j in range(1, count - 1):
                e1 = _sub(self.points[idx[j]], v0)
                e2 = _sub(self.points[idx[j + 1]], v0)
                acc = _add(acc, _cross(e1, e2))
            if math.sqrt(acc[0] ** 2 + acc[1] ** 2 + acc[2] ** 2) < AREA_TOL:
                bad += 1
        return bad


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def parse_usda(path):
    """Parse a self-contained .usda layer into metadata, prims and meshes."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    out = {"layer_metadata": {}, "sub_layers": [], "meshes": {},
           "materials": set(), "api_schemas": {}, "root_prims": [],
           "prim_types": {}, "xform_ops": {}}
    # only these prim types carry the attributes this parser re-derives;
    # everything else (Scope, Shader, Xform, ...) is skipped, so a transform
    # op is still recorded (see the xformOp branch below) but never turns a
    # non-mesh prim into a bogus "mesh" entry
    MESH_TYPES = ("Mesh",)
    ALL_TYPES = None
    stack: list[str] = []
    root_depth_children: set[str] = set()
    layer_metadata = {}
    pending_meta = None                # ("attr" | "prim", path) for stray blocks
    current_mesh = None

    for chunk in _chunks(text):
        stripped = chunk.strip()
        # comment-only chunk (may appear after strip)
        if not stripped:
            continue

        m = _DEF.match(stripped)
        if m:
            kind, dtype, name = m.groups()
            stack.append(name)
            top_level = len(stack) == 1
            path = "/" + "/".join(stack)
            current_mesh = None
            prim_is_mesh = dtype in MESH_TYPES
            out["prim_types"][path] = dtype
            pending_meta = ("prim", path)
            if dtype == "Material":
                out["materials"].add(path)
            if top_level:
                out["root_prims"].append(name)
            body = stripped[m.end():].strip()
            if body.startswith("("):                  # def-level metadata
                meta = _wrap_meta(body)
                if "apiSchemas" in meta:
                    out["api_schemas"][path] = meta["apiSchemas"]
                pending_meta = ("prim", path)
            elif body == "{}":                        # empty prim, one line
                stack.pop()
                pending_meta = None
            elif body and body != "{":
                raise ValueError("unexpected def body: %r" % body[:60])
            continue

        if stripped == "{":
            continue

        if stripped.startswith("}"):
            for _ in stripped.replace(" ", ""):
                if stack:
                    stack.pop()
            current_mesh = None
            continue

        if stripped.startswith("("):
            # stray metadata block: the layer block is handled only when the
            # stack is empty; attribute metadata is inlined in _ATTR chunks.
            if not stack:
                for meta_line in stripped[1:-1].splitlines():
                    mm = _META.match(meta_line.strip())
                    if not mm:
                        continue
                    key, value = mm.group(1), mm.group(2)
                    layer_metadata[key] = value
                    if key == "subLayers":
                        out["sub_layers"] = re.findall(r"@([^@]+)@", value)
            continue

        if not stack:
            mm = _META.match(stripped)
            if mm:
                layer_metadata[mm.group(1)] = mm.group(2)
            continue

        prim_path = "/" + "/".join(stack)

        rm = _REL.match(stripped)
        if rm:
            name = rm.group(1)
            if name.startswith("material:binding"):
                if out["prim_types"].get(prim_path) in MESH_TYPES:
                    mesh = out["meshes"].setdefault(
                        prim_path, Mesh(prim_path))
                    targets = _PATH.findall(rm.group(2))
                    mesh.binding = "<%s>" % targets[0] if targets else None
                    current_mesh = mesh
            continue

        am = _ATTR.match(stripped)
        if am:
            name = am.group(1)
            is_mesh = out["prim_types"].get(prim_path) in MESH_TYPES
            if name.startswith("xformOp") and name != "xformOpOrder":
                # A transform on ANY prim (the root Xform, an ancestor, or the
                # mesh itself): gate 4 rejects any xformOp the original does
                # not have, so "scale the mesh 100x" or "move and tip it over"
                # cannot pass by hiding the edit behind a transform.  Tracked
                # per prim path, so a transform on an Xform ancestor is
                # attributed to that ancestor and to every mesh under it.
                ops = out["xform_ops"].setdefault(prim_path, [])
                if name not in ops:
                    ops.append(name)
                continue
            if not is_mesh:
                continue                # not a Mesh: nothing to re-derive here
            value, attrmeta = _split_attr_meta(stripped[am.end():])
            mesh = out["meshes"].setdefault(prim_path, Mesh(prim_path))
            current_mesh = mesh
            if name == "points":
                mesh.points = _triples(value)
            elif name == "faceVertexCounts":
                mesh.counts = _numbers(value, as_int=True)
            elif name == "faceVertexIndices":
                mesh.indices = _numbers(value, as_int=True)
            elif name == "normals":
                mesh.normals = _triples(value)
                mesh.normals_interpolation = attrmeta.get("interpolation")
            elif name == "extent":
                nums = _numbers(value)
                if len(nums) == 6:
                    mesh.extent = (tuple(nums[:3]), tuple(nums[3:]))
            continue

    # A transform on an ancestor prim (the root Xform, a Scope, ...) moves
    # every mesh under it, so each mesh inherits the xformOps of itself and
    # of every prim on its path -- that is exactly what composed world space
    # applies, and what gate 4 must reject.
    for owner, ops in out["xform_ops"].items():
        for mid, mesh in out["meshes"].items():
            if mid == owner or mid.startswith(owner + "/"):
                for op in ops:
                    if op not in mesh.xform_ops:
                        mesh.xform_ops.append(op)

    out["layer_metadata"] = layer_metadata
    return out


# -- re-derivation (SPEC gate 2 mirror) ---------------------------------------


def check_asset(path):
    """Re-derive every SPEC gate-2 quantity from the artifact text."""
    errors = []
    doc = parse_usda(path)
    meta = doc["layer_metadata"]

    mpu = _scalar(meta.get("metersPerUnit"))
    upaxis = _unquote(meta.get("upAxis"))
    default_prim = _unquote(meta.get("defaultPrim"))

    if "metersPerUnit" not in meta:
        errors.append("metersPerUnit not authored on the root layer")
    elif mpu is None or abs(mpu - METERS_PER_UNIT) > 1e-9:
        errors.append("metersPerUnit = %r != %r"
                      % (mpu, METERS_PER_UNIT))
    if "upAxis" not in meta:
        errors.append("upAxis not authored on the root layer")
    elif upaxis != "Y":
        errors.append("upAxis = %r != 'Y'" % upaxis)
    if "defaultPrim" not in meta:
        errors.append("defaultPrim not authored on the root layer")
    elif default_prim is None or not _root_prim_exists(doc, default_prim):
        errors.append("defaultPrim /%s does not resolve to a prim"
                      % default_prim)

    if doc["sub_layers"]:
        errors.append("artifact subLayers the external layer(s) %s -- the "
                      "artifact must be one self-contained layer"
                      % doc["sub_layers"])

    meshes = doc["meshes"]
    if not meshes:
        errors.append("no Mesh prims in the artifact text")

    colliders = sum(1 for p in doc["api_schemas"]
                    if "PhysicsCollisionAPI" in doc["api_schemas"][p])
    if colliders == 0:
        errors.append("no prim carries UsdPhysics.CollisionAPI")

    materials = doc["materials"]
    mesh_facts = {}
    for mid in sorted(meshes):
        mesh = meshes[mid]
        fact = mesh.fact()
        if fact["normals"] is None:
            errors.append("%s: normals not authored" % mid)
        else:
            if fact["normals"] != fact["face_corners"]:
                errors.append("%s: %d normals != %d face-corners"
                              % (mid, fact["normals"], fact["face_corners"]))
            if fact["normals_interpolation"] != "faceVarying":
                errors.append("%s: normals interpolation %r != 'faceVarying'"
                              % (mid, fact["normals_interpolation"]))
            if fact["max_normal_dev"] > UNIT_TOL:
                errors.append("%s: a normal deviates from unit length by "
                              "%.3g > %g" % (mid, fact["max_normal_dev"],
                                             UNIT_TOL))
        if fact["zero_area_faces"]:
            errors.append("%s: %d face(s) with triangle-fan area < %g cm^2"
                          % (mid, fact["zero_area_faces"], AREA_TOL))
        want = REQUIRED_BINDINGS.get(mid)
        if not mesh.binding or mesh.binding.strip("<>") not in materials:
            errors.append("%s: no computable bound material" % mid)
        elif want is not None and mesh.binding.strip("<>") != want:
            errors.append("%s: bound to %s, must be %s (the reflective band "
                          "is the white plastic)" % (mid, mesh.binding, want))
        if mesh.extent is None:
            errors.append("%s: extent not authored" % mid)
        else:
            lo, hi = mesh.extent
            for pt in mesh.points:
                if any(pt[a] < lo[a] - EXTENT_TOL or pt[a] > hi[a] + EXTENT_TOL
                       for a in range(3)):
                    errors.append("%s: point (%g, %g, %g) outside authored "
                                  "extent by more than %g cm"
                                  % (mid, pt[0], pt[1], pt[2], EXTENT_TOL))
                    break
        mesh_facts[mid] = fact

    facts = {"metersPerUnit": mpu, "upAxis": upaxis,
             "defaultPrim": default_prim,
             "meshes": mesh_facts, "colliders": colliders}
    return errors, facts


def _root_prim_exists(doc, name):
    # defaultPrim must name a root-level prim with children or own geometry
    return name in doc["root_prims"] or \
        any(p == "/" + name or p.startswith("/" + name + "/")
            for p in list(doc["meshes"]) + list(doc["api_schemas"]))


def _scalar(text):
    if text is None:
        return None
    m = _FLOAT.match(text.strip())
    return float(m.group(0)) if m else None


def _unquote(text):
    if text is None:
        return None
    m = _QUOTED.match(text.strip())
    return m.group(1) if m else None


# -- re-derivation (SPEC gate 3 mirror) ---------------------------------------


def check_geometry(path, reference):
    """Re-derive gate 3 from both files' text: mesh paths, counts, bboxes and
    the transform stack -- no `xformOp` the original does not have."""
    errors = []

    def geometry(p):
        doc = parse_usda(p)
        out = {}
        for mid, mesh in doc["meshes"].items():
            pts = mesh.points
            if pts:
                lo = [min(q[a] for q in pts) for a in range(3)]
                hi = [max(q[a] for q in pts) for a in range(3)]
            else:
                lo = hi = [0.0, 0.0, 0.0]
            out[mid] = (len(pts), lo, hi, list(mesh.xform_ops))
        return out

    art, ref = geometry(path), geometry(reference)
    if set(art) != set(ref):
        errors.append("Mesh prim paths differ from the original: "
                      "artifact %s vs original %s" % (sorted(art), sorted(ref)))
    facts = {}
    for key in sorted(set(art) & set(ref)):
        n_art, lo_a, hi_a, ops_a = art[key]
        n_ref, lo_r, hi_r, ops_r = ref[key]
        worst = 0.0
        if n_art != n_ref:
            errors.append("%s: point count %d != original %d"
                          % (key, n_art, n_ref))
        for a in range(3):
            worst = max(worst, abs(lo_a[a] - lo_r[a]), abs(hi_a[a] - hi_r[a]))
        extra_ops = [o for o in ops_a if o not in ops_r]
        if extra_ops:
            errors.append("%s: the artifact adds transform op(s) %s that the "
                          "original does not have -- the repair must edit the "
                          "mesh's own data, not wrap it in a transform"
                          % (key, extra_ops))
        facts[key] = {"points": n_art, "xform_ops": ops_a,
                      "bbox_dev_cm": round(worst, 9)}
        if worst > BBOX_TOL:
            errors.append("%s: points bbox deviates from the original by "
                          "%.3g cm > %g cm" % (key, worst, BBOX_TOL))
    return errors, facts


# -- cross-check against the oracle's facts -----------------------------------


def cross_check(oracle_asset, recount_asset, oracle_geom, recount_geom):
    """Every quantity both sides derived must agree, or the grade fails."""
    errors = []

    def num_eq(a, b, tol):
        return a is not None and b is not None and abs(a - b) <= tol

    for key in ("metersPerUnit", "upAxis", "defaultPrim", "colliders"):
        a, b = oracle_asset.get(key), recount_asset.get(key)
        if a != b:
            errors.append("cross-check: oracle %s=%r != recount %r"
                          % (key, a, b))

    om = oracle_asset.get("meshes") or {}
    rm = recount_asset.get("meshes") or {}
    if set(om) != set(rm):
        errors.append("cross-check: mesh sets differ: oracle %s vs recount %s"
                      % (sorted(om), sorted(rm)))
    for mid in sorted(set(om) & set(rm)):
        o, r = om[mid], rm[mid]
        for key in ("points", "face_corners", "normals",
                    "zero_area_faces", "normals_interpolation"):
            if o.get(key) != r.get(key):
                errors.append("cross-check: %s %s oracle=%r recount=%r"
                              % (mid, key, o.get(key), r.get(key)))
        if not num_eq(o.get("max_normal_dev"), r.get("max_normal_dev"),
                      XCHECK_DEV_TOL):
            errors.append("cross-check: %s max_normal_dev oracle=%r "
                          "recount=%r" % (mid, o.get("max_normal_dev"),
                                          r.get("max_normal_dev")))
        oe, re_ = o.get("extent"), r.get("extent")
        if (oe is None) != (re_ is None):
            errors.append("cross-check: %s extent authored on one side only"
                          % mid)
        elif oe and re_:
            for a, b in zip(oe, re_):
                for x, y in zip(a, b):
                    if abs(x - y) > EXTENT_TOL:
                        errors.append("cross-check: %s extent oracle=%r "
                                      "recount=%r" % (mid, oe, re_))
                        break

    og = oracle_geom or {}
    rg = recount_geom or {}
    if set(og) != set(rg):
        errors.append("cross-check: geometry mesh sets differ: %s vs %s"
                      % (sorted(og), sorted(rg)))
    for mid in sorted(set(og) & set(rg)):
        if og[mid].get("points") != rg[mid].get("points"):
            errors.append("cross-check: %s points oracle=%r recount=%r"
                          % (mid, og[mid].get("points"), rg[mid].get("points")))
        if not num_eq(og[mid].get("bbox_dev_cm"), rg[mid].get("bbox_dev_cm"),
                      XCHECK_BBOX_TOL):
            errors.append("cross-check: %s bbox_dev oracle=%r recount=%r"
                          % (mid, og[mid].get("bbox_dev_cm"),
                             rg[mid].get("bbox_dev_cm")))
    return errors


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) not in (2, 3):
        print("usage: text_recount.py <artifact.usda> [reference.usda]",
              file=sys.stderr)
        sys.exit(2)
    errs, facts = check_asset(sys.argv[1])
    out = {"gate2b_recount": {"passed": not errs, "errors": errs},
           "facts": facts}
    if len(sys.argv) == 3:
        errs3, facts3 = check_geometry(sys.argv[1], sys.argv[2])
        out["gate3_recount"] = {"passed": not errs3, "errors": errs3}
        out["geometry"] = facts3
    print(json.dumps(out, indent=1, sort_keys=True))
    sys.exit(0 if not errs and (len(sys.argv) == 2 or not errs3) else 1)