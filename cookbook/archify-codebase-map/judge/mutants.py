#!/usr/bin/env python3
"""Generate known-bad artifacts (mutants) of the good httpx-map example.

Each mutant is a single clear defect. They live under examples/bad/<name>/
and must each fail at least one judge gate (selftest.sh checks this).

Mutants:
  hallucinated_node     one component claims to be httpx/_telemetry.py (does not exist)
  hallucinated_edge     adds a bogus _client -> _telemetry edge (with a fake node)
  reversed_edges        all connections point the wrong way
  half_modules          every other module dropped (node recall < 0.9)
  mangled_json          diagram.json is syntactically broken
  stale_html            diagram.html hand-edited after render (not reproducible)
  blank_html            diagram.html is a blank page (renders empty)
  edge_via_missing_node connections reference an id with no component
"""

import copy
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
BASE = HERE.parent / "examples" / "good" / "httpx-map"
BAD = HERE.parent / "examples" / "bad"


def load():
    return json.loads((BASE / "diagram.json").read_text())


def write(name, spec):
    d = BAD / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "diagram.json").write_text(json.dumps(spec, indent=2) + "\n")
    print(f"mutant: {name}")


def m_hallucinated_node():
    d = load()
    d["components"].append({
        "id": "telemetry", "type": "backend", "label": "_telemetry",
        "sublabel": "httpx/_telemetry.py",
        "pos": [3450, 1780], "size": [176, 84],
        "sources": [{"path": "httpx/_telemetry.py"}],
    })
    write("hallucinated_node", d)


def m_hallucinated_edge():
    d = load()
    d["components"].append({
        "id": "telemetry", "type": "backend", "label": "_telemetry",
        "pos": [3450, 1780], "size": [176, 84],
        "sources": [{"path": "httpx/_telemetry.py"}],
    })
    d["connections"].append({"from": "client", "to": "telemetry"})
    write("hallucinated_edge", d)


def m_reversed_edges():
    d = load()
    for c in d["connections"]:
        c["from"], c["to"] = c["to"], c["from"]
    write("reversed_edges", d)


def m_half_modules():
    d = load()
    keep_ids = {c["id"] for i, c in enumerate(d["components"]) if i % 2 == 0}
    d["components"] = [c for c in d["components"] if c["id"] in keep_ids]
    d["connections"] = [c for c in d["connections"]
                        if c["from"] in keep_ids and c["to"] in keep_ids]
    write("half_modules", d)


def m_mangled_json():
    d = BAD / "mangled_json"
    d.mkdir(parents=True, exist_ok=True)
    text = load_text()
    (d / "diagram.json").write_text(text[:-5] + "}}}  not json")
    print("mutant: mangled_json")


def load_text():
    return (BASE / "diagram.json").read_text()


def m_stale_html():
    d = BAD / "stale_html"
    d.mkdir(parents=True, exist_ok=True)
    (d / "diagram.json").write_text(load_text())
    html = (BASE / "diagram.html").read_text()
    # hand-edited title — must not match a fresh render
    (d / "diagram.html").write_text(
        html.replace("module dependency map", "HAND EDITED TITLE"))
    print("mutant: stale_html")


def m_blank_html():
    d = BAD / "blank_html"
    d.mkdir(parents=True, exist_ok=True)
    (d / "diagram.json").write_text(load_text())
    (d / "diagram.html").write_text(
        "<!doctype html><html><body style='background:#fff'></body></html>")
    print("mutant: blank_html")


def m_edge_via_missing_node():
    d = load()
    d["connections"].append({"from": "client", "to": "no_such_node"})
    write("edge_via_missing_node", d)


ALL = [m_hallucinated_node, m_hallucinated_edge, m_reversed_edges,
       m_half_modules, m_mangled_json, m_stale_html, m_blank_html,
       m_edge_via_missing_node]

if __name__ == "__main__":
    if not (BASE / "diagram.json").is_file():
        sys.exit(f"missing good example at {BASE}/diagram.json")
    BAD.mkdir(parents=True, exist_ok=True)
    for m in ALL:
        m()
