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
_KIND_TYPES = {
    "image": _IMAGE_TYPES,
    "video": _VIDEO_TYPES,
    "model3d": _MODEL3D_TYPES,
}
_PATH_FIELDS = ("path", "poster", "before", "after")


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
    required, properties, additionalProperties, items, anyOf, $ref."""
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
            if not any(_sub_valid(value, s, root_schema) for s in schema["anyOf"]):
                errors.append(f"{loc}: does not satisfy anyOf "
                              f"(need one of: path, url, before+after)")
    return errors


def _sub_valid(value, schema, root_schema):
    return not _validate(value, schema, "$", [], root_schema)


def validate_manifest(doc):
    """Return a list of schema violations (empty = valid)."""
    return _validate(doc, _load_schema(), "$", [], _load_schema())


# ------------------------------------------------------------- file check

def _sniff(path):
    """Return the format tag from magic bytes, or None if unknown."""
    try:
        head = path.open("rb").read(64)
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
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "mp4"
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
    return resolved


def _check_kind(loc, entry, root, errors):
    """Check the entry's kind against the referenced files' magic bytes."""
    kind = entry.get("kind")
    if kind in _KIND_TYPES:
        ref = entry.get("path")
        if isinstance(ref, str) and ref:
            resolved = _resolve(root, f"{loc}.path", ref, errors)
            if resolved is not None:
                found = _sniff(resolved)
                want = _KIND_TYPES[kind]
                if found not in want:
                    errors.append(
                        f"{loc}.path: kind {kind!r} but {ref!r} sniffs as "
                        f"{found or 'unknown'} (expected one of "
                        f"{sorted(want)})")
    for field in ("poster", "before", "after"):
        ref = entry.get(field)
        if isinstance(ref, str) and ref:
            resolved = _resolve(root, f"{loc}.{field}", ref, errors)
            if resolved is not None and _sniff(resolved) not in _IMAGE_TYPES:
                errors.append(f"{loc}.{field}: {ref!r} is not an image "
                              f"(png/jpg/webp/gif)")
    if kind == "compare" and "path" not in entry and \
            not ("before" in entry and "after" in entry) and \
            "url" not in entry:
        errors.append(f"{loc}: kind 'compare' needs before+after (or "
                      f"path/url)")


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
