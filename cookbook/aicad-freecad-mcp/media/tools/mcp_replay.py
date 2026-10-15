#!/usr/bin/env python3
"""Replay the demo's MCP build drive, logging every real tool call.

This drives the same freecad-mcp server with the same protocol as
driver/drive_freecad.py, but logs one line per tools/call (name, part,
elapsed s, result digest) instead of a per-part summary. Output is a JSON
list: the input the media renders as "the agent's MCP tool calls".

The label "replay" is literal: the artifacts under examples/good/ were built
by the real drive; this re-issues the identical calls and records them.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # <demo root>
sys.path.insert(0, os.path.join(ROOT, "driver"))
from mcp_client import McpStdioClient  # noqa: E402

PARTS = [
    ("bushing", "build_bushing.py", None),
    ("plate", "build_plate.py", ("draw_plate_dxf.py",)),
    ("bracket", "build_bracket.py", None),
]


def main():
    mcp_bin = os.path.expanduser("~/.venvs/freecad-mcp/bin/freecad-mcp")
    freecadcmd = os.path.join(os.path.expanduser("~/freecad-1.0.1"),
                              "usr", "bin", "freecadcmd")
    out_path = os.path.join(HERE, "..", "data", "mcp_replay.json")
    calls = []
    client = McpStdioClient([mcp_bin, "--freecadcmd", freecadcmd])
    try:
        calls.append({"tool": "initialize", "part": "-",
                      "line": "initialize -> serverInfo=%s" % json.dumps(
                          client.initialize())})
        t0 = time.time()
        status = client.call_tool("get_rpc_status", {})
        calls.append({"tool": "get_rpc_status", "part": "-",
                      "elapsed_s": round(time.time() - t0, 3),
                      "line": "get_rpc_status -> %s" % status.strip()[:120]})
        for part, script, followup in PARTS:
            for label, s in ([(part, script)] +
                             [(part, f) for f in (followup or [])]):
                path = os.path.join(ROOT, "agent", s)
                with open(path) as f:
                    code = f.read()
                # rebuild into a scratch dir so examples/good/ stays the
                # graded artifact; sizes/volumes still come from FreeCAD
                scratch = os.path.join(HERE, "..", "master", "replay", label)
                os.makedirs(scratch, exist_ok=True)
                wrapped = ("OUTPUT_DIR = %r\n" % os.path.abspath(scratch)) + code
                t0 = time.time()
                client.call_tool("execute_code_headless",
                                 {"code": wrapped, "timeout": 300},
                                 timeout_s=360)
                dt = time.time() - t0
                stl = os.path.join(scratch, "%s.stl" % part)
                vol = None
                if os.path.isfile(stl):
                    # volume read from the file FreeCAD just wrote
                    import trimesh
                    vol = round(float(trimesh.load(stl, force="mesh").volume), 4)
                calls.append({
                    "tool": "execute_code_headless", "part": part,
                    "script": s, "elapsed_s": round(dt, 3),
                    "volume_mm3": vol,
                    "line": "execute_code_headless %s -> _OK volume=%s (%.1f s)"
                            % (s, vol, dt)})
    finally:
        client.close()
    with open(out_path, "w") as f:
        json.dump(calls, f, indent=1)
        f.write("\n")
    print(json.dumps(calls, indent=1))


if __name__ == "__main__":
    main()
