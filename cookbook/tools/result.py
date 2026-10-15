#!/usr/bin/env python3
"""Write and check cookbook demo result.json manifests.

One `media/result.json` per demo drives the in-chat result card, the demo
gallery and the video storyboard with the same numbers. The manifest
schema lives in `result.schema.json` next to this file.

As a library:

    from result import write_result
    write_result("media/result.json", demo="cfd-openfoam", headline=..., ...)

`write_result` validates the fields against the schema and writes the
file; pass `root=<demo dir>` to also verify that every referenced path
exists and that hero/gallery kinds match the files' magic bytes.

As a command:

    python3 cookbook/tools/result.py check <result.json> [--root <demo dir>]

`check` validates the schema (hand-rolled, no jsonschema dependency),
verifies every referenced path exists under <demo dir> (default: the
manifest's parent's parent when it lives in `media/`), and checks that
`kind` matches the file's magic bytes:

    model3d -> glTF/glb,  video -> mp4/webm,  image -> png/jpg/webp/gif

`path` fields are checked against their kind's formats, while `poster`,
`before` and `after` must always be images. An MP4 is only accepted when
its ftyp brands fit MP4 *and* a `vide` track handler shows up in the
first few MB — so AVIF stills and audio-only M4A do not pass as video.

It exits non-zero and prints every reason found.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_ID = "agent-next/result@1"
SCHEMA_FILE = Path(__file__).resolve().with_name("result.schema.json")

_IMAGE_TYPES = {"png", "jpeg", "webp", "gif"}
_VIDEO_TYPES = {"mp4", "webm"}
_MODEL3D_TYPES = {"glb", "gltf"}
_ALL_TYPES = _IMAGE_TYPES | _VIDEO_TYPES | _MODEL3D_TYPES
_KIND_TYPES = {
    "image": _IMAGE_TYPES,
    "video": _VIDEO_TYPES,
    "model3d": _MODEL3D_TYPES,
}
_PATH_FIELDS = ("path", "poster", "before", "after")

# ftyp major/compatible brands that may carry MP4 video. Brands such as
# avif, heic, mif1 or msf1 are still images, and M4A is audio-only — none
# of those are in this set.
_MP4_BRANDS = {b"isom", b"iso2", b"iso3", b"iso4", b"iso5", b"iso6",
               b"mp41", b"mp42", b"avc1", b"dash", b"M4V "}
# A video track must also show up: scan the first few MB for an mdia/hdlr
# box whose handler type is 'vide'.
_SNIFF_WINDOW = 4 * 1024 * 1024


# ---------------------------------------------------------------- schema

def _load_schema():
    return json.loads(SCHEMA_FILE.read_text())


def _check_type(value, expected):
    """JSON-schema `type` check; bool is not a number."""
    ok = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "null": lambda v: v is None,
    }
    types = expected if isinstance(expected, list) else [expected]
    return any(ok[t](value) for t in types)


def _validate(value, schema, loc, errors, root_schema):
    """Validate `value` against the draft 2020-12 subset used by
    result.schema.json: type, enum, const, pattern, minLength, minItems,
    required, properties, additionalProperties, items, anyOf, oneOf,
    $ref."""
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#/$defs/"):
            schema = root_schema["$defs"][ref.split("/")[-1]]
        else:
            errors.append(f"{loc}: unsupported $ref {ref!r}")
            return
    if "type" in schema and not _check_type(value, schema["type"]):
        errors.append(f"{loc}: expected type {schema['type']}, got "
                      f"{type(value).__name__}")
        return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{loc}: must be {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{loc}: must be one of {schema['enum']}, got {value!r}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{loc}: string shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{loc}: {value!r} does not match "
                          f"{schema['pattern']!r}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{loc}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                _validate(item, schema["items"], f"{loc}[{i}]", errors,
                          root_schema)
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{loc}: missing required field {key!r}")
        props = schema.get("properties", {})
        for key, val in value.items():
            if key in props:
                _validate(val, props[key], f"{loc}.{key}", errors, root_schema)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{loc}: unexpected field {key!r}")
        if "anyOf" in schema:
            if not any(_sub_valid(value, s, root_schema)
                       for s in schema["anyOf"]):
                errors.append(f"{loc}: does not satisfy anyOf")
        if "oneOf" in schema:
            matched = sum(_sub_valid(value, s, root_schema)
                          for s in schema["oneOf"])
            if matched != 1:
                errors.append(
                    f"{loc}: kind {value.get('kind')!r} does not satisfy "
                    f"its field rules (image/video/model3d need path or "
                    f"url; compare needs before+after; app needs url)")
    return errors


def _sub_valid(value, schema, root_schema):
    return not _validate(value, schema, "$", [], root_schema)


def validate_manifest(doc):
    """Return a list of schema violations (empty = valid)."""
    return _validate(doc, _load_schema(), "$", [], _load_schema())


# ------------------------------------------------------------- file check

def _sniff_ftyp(head):
    """Classify an ISO-BMFF file by its ftyp box. 'mp4' only when a brand
    known to carry MP4 video appears *and* a 'vide' track handler shows up
    inside the scanned prefix — so AVIF/HEIC stills and audio-only M4A
    return None."""
    size = int.from_bytes(head[:4], "big")
    if size < 16:
        return None
    brands = [head[8:12]] + [head[i:i + 4]
                             for i in range(16, min(size, len(head)), 4)]
    if not any(b in _MP4_BRANDS for b in brands):
        return None
    pos = 0
    while True:
        i = head.find(b"hdlr", pos)
        if i < 0:
            return None
        # hdlr box: size+type, then version/flags(4), pre_defined(4),
        # handler_type(4) — so the handler sits 12 bytes past 'hdlr'.
        if head[i + 12:i + 16] == b"vide":
            return "mp4"
        pos = i + 4


def _moov_box(f):
    """The top-level moov box (up to _SNIFF_WINDOW bytes), found by walking
    box headers — files written without +faststart keep it after mdat."""
    end = f.seek(0, 2)
    f.seek(0)
    while True:
        header = f.read(8)
        if len(header) < 8:
            return b""
        size, typ = int.from_bytes(header[:4], "big"), header[4:]
        if size == 1:
            size = int.from_bytes(f.read(8), "big") - 8
        elif size == 0:
            size = None  # box runs to end of file
        if size is not None and size < 8:
            return b""
        if typ == b"moov":
            return header + f.read(_SNIFF_WINDOW)
        if size is None or f.tell() + size - 8 > end:
            return b""
        f.seek(size - 8, 1)


def _sniff(path):
    """Return the format tag from magic bytes, or None if unknown."""
    try:
        with path.open("rb") as f:
            head = f.read(64)
            if len(head) >= 12 and head[4:8] == b"ftyp":
                head += f.read(_SNIFF_WINDOW - len(head))
                return _sniff_ftyp(head) or _sniff_ftyp(head[:64] + _moov_box(f))
    except OSError:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if head[:4] == b"glTF":
        return "glb"
    if head.lstrip()[:1] == b"{":
        try:
            doc = json.loads(path.read_bytes())
        except (OSError, ValueError):
            return None
        if isinstance(doc, dict) and "asset" in doc:
            return "gltf"
    return None


def _hero_entries(doc):
    yield "hero", doc.get("hero") or {}
    for i, item in enumerate(doc.get("gallery") or []):
        yield f"gallery[{i}]", item or {}


def _referenced_paths(doc):
    """Every manifest field that is a path relative to the demo root."""
    refs = []
    receipt = doc.get("receipt")
    if isinstance(receipt, str) and receipt:
        refs.append(("receipt", receipt))
    for loc, entry in _hero_entries(doc):
        for field in _PATH_FIELDS:
            val = entry.get(field)
            if isinstance(val, str) and val:
                refs.append((f"{loc}.{field}", val))
    return refs


def _resolve_quiet(root, ref):
    """Resolve `ref` under root without reporting; None when unusable —
    absolute, escaping the root, missing or not a regular file."""
    p = Path(ref)
    if p.is_absolute():
        return None
    resolved = (root / p).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved if resolved.is_file() else None


def _resolve(root, loc, ref, errors):
    """Resolve a referenced path under root; return it or None."""
    p = Path(ref)
    if p.is_absolute():
        errors.append(f"{loc}: {ref!r} is absolute; paths are relative to "
                      f"the demo root")
        return None
    resolved = (root / p).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        errors.append(f"{loc}: {ref!r} escapes the demo root")
        return None
    if not resolved.exists():
        errors.append(f"{loc}: {ref!r} does not exist under {root}")
        return None
    if not resolved.is_file():
        errors.append(f"{loc}: {ref!r} is not a regular file")
        return None
    return resolved


def _check_kind(loc, entry, root, errors):
    """Check the entry's kind against the referenced files' magic bytes.

    Fields required per kind (mirroring result.schema.json):
    image/video/model3d need path or url, compare needs before+after,
    app needs url. Every local file field is magic-checked: `path`
    against the kind's formats, `poster`/`before`/`after` as images.
    Paths were already resolved (and reported) by the first pass, so
    this resolves silently to avoid duplicate diagnostics."""
    kind = entry.get("kind")
    if kind in _KIND_TYPES and not (entry.get("path") or entry.get("url")):
        errors.append(f"{loc}: kind {kind!r} needs 'path' or 'url'")
    elif kind == "compare" and \
            not (entry.get("before") and entry.get("after")):
        errors.append(f"{loc}: kind 'compare' needs 'before' and 'after'")
    elif kind == "app" and not entry.get("url"):
        errors.append(f"{loc}: kind 'app' needs 'url'")
    for field in _PATH_FIELDS:
        ref = entry.get(field)
        if not (isinstance(ref, str) and ref):
            continue
        resolved = _resolve_quiet(root, ref)
        if resolved is None:
            continue
        found = _sniff(resolved)
        if field == "path":
            want = _KIND_TYPES.get(kind, _ALL_TYPES)
            if found not in want:
                errors.append(
                    f"{loc}.path: kind {kind!r} but {ref!r} sniffs as "
                    f"{found or 'unknown'} (expected one of "
                    f"{sorted(want)})")
        elif found not in _IMAGE_TYPES:
            errors.append(f"{loc}.{field}: {ref!r} is not an image "
                          f"(png/jpg/webp/gif)")


def check_manifest(path, root=None):
    """Return the list of problems with the manifest at `path`.

    Checks schema validity, that every referenced path exists under
    `root`, and that hero/gallery kinds match file magic bytes."""
    path = Path(path)
    errors = []
    try:
        doc = json.loads(path.read_text())
    except OSError as e:
        return [f"{path}: cannot read: {e}"]
    except ValueError as e:
        return [f"{path}: invalid JSON: {e}"]
    if not isinstance(doc, dict):
        return [f"{path}: top level must be an object"]

    errors.extend(validate_manifest(doc))
    if errors:
        return errors

    if root is None:
        parent = path.resolve().parent
        root = parent.parent if parent.name == "media" else parent
    root = Path(root)
    if not root.is_dir():
        return [f"root {root} is not a directory"]

    for loc, ref in _referenced_paths(doc):
        _resolve(root, loc, ref, errors)
    for loc, entry in _hero_entries(doc):
        _check_kind(loc, entry, root, errors)
    return errors


# ----------------------------------------------------------------- writer

def write_result(path, root=None, **fields):
    """Validate `fields` against the manifest schema and write `path`.

    `schema` defaults to the current schema id. With `root`, referenced
    paths must also exist under it and match their declared kinds.
    Raises ValueError listing every problem found."""
    fields.setdefault("schema", SCHEMA_ID)
    errors = validate_manifest(fields)
    if not errors and root is not None:
        root = Path(root)
        for loc, ref in _referenced_paths(fields):
            _resolve(root, loc, ref, errors)
        for loc, entry in _hero_entries(fields):
            _check_kind(loc, entry, root, errors)
    if errors:
        raise ValueError("invalid result manifest:\n  " + "\n  ".join(errors))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields, indent=2) + "\n")
    return path


# -------------------------------------------------------------------- cli

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check", help="validate a result.json manifest")
    ck.add_argument("result", type=Path, help="path to result.json")
    ck.add_argument("--root", type=Path, default=None,
                    help="demo dir referenced paths resolve under "
                         "(default: parent of media/)")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        errors = check_manifest(args.result, args.root)
        if errors:
            for e in errors:
                print(f"FAIL {args.result}: {e}", file=sys.stderr)
            return 1
        print(f"OK {args.result}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
