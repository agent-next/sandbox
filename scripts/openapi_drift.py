#!/usr/bin/env python3
"""Detect drift between the live gateway OpenAPI document and the kit snapshot.

The snapshot (docs/contract/openapi.snapshot.json) is the contract the kit
docs describe. This script fetches the live document, normalizes both sides
and reports the difference as a human-readable summary.

Exit codes:
  0  no drift (documents equal after normalization)
  1  drift found (summary printed to stdout)
  2  fetch or input error (reported on stderr; never a silent pass)

Usage:
  openapi_drift.py                  compare live to the committed snapshot
  openapi_drift.py --update         fetch live and rewrite the snapshot
  openapi_drift.py --file F         compare file F to the snapshot (no network)
  openapi_drift.py --offline F      same as --file
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://api.sbx.agent-next.com/openapi.json"
DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[1] / "docs/contract/openapi.snapshot.json"

# Dotted paths dropped before comparing. Each changes for reasons the kit
# docs do not track:
#   info.version — the gateway's own release number, bumped per deploy;
#   servers      — deployment-specific domain variables (the E2B_DOMAIN of the
#                  environment), environment config, not route contract.
# Everything else (paths, components, tags, x-excluded-routes, prose
# descriptions) is contract surface: a change there is drift worth reporting.
VOLATILE_FIELDS = ("info.version", "servers")

# Cap for the catch-all "other changes" section so a prose rewrite of the
# whole document cannot bury the structural findings.
OTHER_CAP = 40


class FetchError(Exception):
    """The live document could not be retrieved or parsed."""


class InputError(Exception):
    """A local file could not be read or parsed."""


def normalize(doc):
    """Return a copy of the document with volatile top-level fields removed."""
    out = copy.deepcopy(doc)
    for path in VOLATILE_FIELDS:
        parts = path.split(".")
        parent = out
        for part in parts[:-1]:
            if not isinstance(parent, dict) or part not in parent:
                break
            parent = parent[part]
        else:
            if isinstance(parent, dict):
                parent.pop(parts[-1], None)
    return out


def canon(doc):
    """Canonical text form: sorted keys, stable indent, trailing newline."""
    return json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def fetch(url, timeout=30):
    """Fetch and parse the live OpenAPI document."""
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "agent-next-sandbox-drift-check"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except Exception as exc:
        raise FetchError(f"{url}: {exc}") from exc
    try:
        return json.loads(body)
    except ValueError as exc:
        raise FetchError(f"{url}: invalid JSON ({exc})") from exc


def load_json_file(path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"{path}: {exc}") from exc
    try:
        return json.loads(text)
    except ValueError as exc:
        raise InputError(f"{path}: invalid JSON ({exc})") from exc


def _short(value, limit=90):
    text = json.dumps(value, ensure_ascii=False)
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def _properties(schema):
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties")
    return props if isinstance(props, dict) else {}


def _required(schema):
    if not isinstance(schema, dict):
        return set()
    req = schema.get("required")
    return set(req) if isinstance(req, list) else set()


def schema_key_changes(label, old_schema, new_schema, out):
    """Report added/removed property names, required-list and per-property changes."""
    old_props, new_props = _properties(old_schema), _properties(new_schema)
    for name in sorted(set(new_props) - set(old_props)):
        out.append(f"{label}: property added: {name}")
    for name in sorted(set(old_props) - set(new_props)):
        out.append(f"{label}: property removed: {name}")
    for name in sorted(_required(new_schema) - _required(old_schema)):
        out.append(f"{label}: now required: {name}")
    for name in sorted(_required(old_schema) - _required(new_schema)):
        out.append(f"{label}: no longer required: {name}")
    for name in sorted(set(old_props) & set(new_props)):
        if old_props[name] != new_props[name]:
            generic_diff(f"{label}.{name}", old_props[name], new_props[name], out)
    if not old_props and not new_props and old_schema != new_schema:
        generic_diff(f"{label}.schema", old_schema, new_schema, out)


def generic_diff(prefix, old, new, out):
    """Collect changed leaf paths under `prefix` as one-line summaries."""
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            if key not in old:
                out.append(f"{prefix}.{key}: added ({_short(new[key])})")
            elif key not in new:
                out.append(f"{prefix}.{key}: removed (was {_short(old[key])})")
            else:
                generic_diff(f"{prefix}.{key}", old[key], new[key], out)
        return
    if isinstance(old, list) and isinstance(new, list):
        if old != new:
            out.append(f"{prefix}: changed ({_short(old)} -> {_short(new)})")
        return
    if old != new:
        out.append(f"{prefix}: changed ({_short(old)} -> {_short(new)})")


def _content_schemas(node):
    """Map media_type -> schema for a requestBody/response node."""
    content = node.get("content", {}) if isinstance(node, dict) else {}
    if not isinstance(content, dict):
        return {}
    return {
        media_type: content[media_type].get("schema")
        for media_type in sorted(content)
        if isinstance(content[media_type], dict) and content[media_type].get("schema") is not None
    }


def diff_operation(path, method, old_op, new_op, request_lines, response_lines, other_lines):
    label = f"{method.upper()} {path}"
    if "requestBody" not in old_op and "requestBody" in new_op:
        request_lines.append(f"{label}: request body added")
    elif "requestBody" in old_op and "requestBody" not in new_op:
        request_lines.append(f"{label}: request body removed")
    elif "requestBody" in old_op:
        old_types = _content_schemas(old_op["requestBody"])
        new_types = _content_schemas(new_op["requestBody"])
        for media_type in sorted(set(old_types) & set(new_types)):
            schema_key_changes(f"{label} request [{media_type}]", old_types[media_type],
                               new_types[media_type], request_lines)

    old_responses = old_op.get("responses") if isinstance(old_op.get("responses"), dict) else {}
    new_responses = new_op.get("responses") if isinstance(new_op.get("responses"), dict) else {}
    for code in sorted(set(new_responses) - set(old_responses), key=str):
        response_lines.append(f"{label}: response {code} added")
    for code in sorted(set(old_responses) - set(new_responses), key=str):
        response_lines.append(f"{label}: response {code} removed")
    for code in sorted(set(old_responses) & set(new_responses), key=str):
        old_types = _content_schemas(old_responses[code])
        new_types = _content_schemas(new_responses[code])
        for media_type in sorted(set(old_types) & set(new_types)):
            schema_key_changes(f"{label} response {code} [{media_type}]", old_types[media_type],
                               new_types[media_type], response_lines)

    # Parameters compared by their identity (in, name); everything else about
    # an operation falls into the catch-all section.
    def param_ids(op):
        params = op.get("parameters")
        if not isinstance(params, list):
            return set()
        return {(p.get("in"), p.get("name")) for p in params if isinstance(p, dict)}

    for in_, name in sorted(param_ids(old_op) - param_ids(new_op)):
        other_lines.append(f"{label}: parameter removed: {name} ({in_})")
    for in_, name in sorted(param_ids(new_op) - param_ids(old_op)):
        other_lines.append(f"{label}: parameter added: {name} ({in_})")

    structural = ("requestBody", "responses", "parameters")
    for key in sorted(set(old_op) | set(new_op)):
        if key in structural:
            continue
        if key not in old_op:
            other_lines.append(f"{label}.{key}: added ({_short(new_op[key])})")
        elif key not in new_op:
            other_lines.append(f"{label}.{key}: removed (was {_short(old_op[key])})")
        elif old_op[key] != new_op[key]:
            generic_diff(f"{label}.{key}", old_op[key], new_op[key], other_lines)


def diff_docs(old, new):
    """Return a list of human-readable drift lines (empty when equal)."""
    lines = []
    for key in sorted(set(old) | set(new)):
        if key in ("paths", "components"):
            continue
        if key not in old:
            lines.append(f"{key}: added ({_short(new[key])})")
        elif key not in new:
            lines.append(f"{key}: removed (was {_short(old[key])})")
        elif old[key] != new[key]:
            generic_diff(key, old[key], new[key], lines)

    old_paths = old.get("paths") if isinstance(old.get("paths"), dict) else {}
    new_paths = new.get("paths") if isinstance(new.get("paths"), dict) else {}
    if added := sorted(set(new_paths) - set(old_paths)):
        lines.append("paths added: " + ", ".join(added))
    if removed := sorted(set(old_paths) - set(new_paths)):
        lines.append("paths removed: " + ", ".join(removed))

    method_lines, request_lines, response_lines, other_lines = [], [], [], []
    for path in sorted(set(old_paths) & set(new_paths)):
        old_methods, new_methods = old_paths[path], new_paths[path]
        if not isinstance(old_methods, dict) or not isinstance(new_methods, dict):
            other_lines.append(f"{path}: path item changed ({_short(old_methods)} -> {_short(new_methods)})")
            continue
        for method in sorted(set(new_methods) - set(old_methods)):
            method_lines.append(f"{path}: method added: {method.upper()}")
        for method in sorted(set(old_methods) - set(new_methods)):
            method_lines.append(f"{path}: method removed: {method.upper()}")
        for method in sorted(set(old_methods) & set(new_methods)):
            diff_operation(path, method, old_methods[method], new_methods[method],
                           request_lines, response_lines, other_lines)

    old_components = old.get("components") if isinstance(old.get("components"), dict) else {}
    new_components = new.get("components") if isinstance(new.get("components"), dict) else {}
    old_schemas = old_components.get("schemas") if isinstance(old_components.get("schemas"), dict) else {}
    new_schemas = new_components.get("schemas") if isinstance(new_components.get("schemas"), dict) else {}
    schema_lines = []
    for name in sorted(set(new_schemas) - set(old_schemas)):
        schema_lines.append(f"component schema added: {name}")
    for name in sorted(set(old_schemas) - set(new_schemas)):
        schema_lines.append(f"component schema removed: {name}")
    for name in sorted(set(old_schemas) & set(new_schemas)):
        schema_key_changes(f"schema {name}", old_schemas[name], new_schemas[name], schema_lines)

    for heading, section in (
        ("methods", method_lines),
        ("request schemas", request_lines),
        ("response schemas", response_lines),
        ("component schemas", schema_lines),
    ):
        if section:
            lines.append(f"{heading}:")
            lines.extend("  " + line for line in section)

    for key in sorted(set(old_components) | set(new_components)):
        if key == "schemas":
            continue
        if old_components.get(key) != new_components.get(key):
            generic_diff(f"components.{key}", old_components.get(key),
                         new_components.get(key), other_lines)

    if other_lines:
        lines.append("other changes:")
        lines.extend("  " + line for line in other_lines[:OTHER_CAP])
        if len(other_lines) > OTHER_CAP:
            lines.append(f"  ... and {len(other_lines) - OTHER_CAP} more")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL, help="live openapi.json URL")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT, help="snapshot path")
    parser.add_argument("--update", action="store_true", help="fetch live and rewrite the snapshot")
    parser.add_argument("--file", "--offline", dest="file", type=Path, default=None,
                        help="compare this file to the snapshot instead of fetching")
    args = parser.parse_args(argv)

    if args.update:
        try:
            doc = fetch(args.url)
        except FetchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(canon(normalize(doc)), encoding="utf-8")
        print(f"snapshot updated: {args.snapshot}")
        return 0

    try:
        snapshot = normalize(load_json_file(args.snapshot))
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.file is not None:
        try:
            live = load_json_file(args.file)
        except InputError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        source = str(args.file)
    else:
        try:
            live = fetch(args.url)
        except FetchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        source = args.url

    lines = diff_docs(snapshot, normalize(live))
    if not lines:
        print(f"no drift: {source} matches {args.snapshot}")
        return 0
    print(f"API drift: {source} differs from {args.snapshot}")
    print()
    print("\n".join(lines))
    return 1


if __name__ == "__main__":
    sys.exit(main())
