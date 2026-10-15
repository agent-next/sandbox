#!/usr/bin/env python3
"""Drive FreeCAD through the freecad-mcp MCP server to build all three parts.

This is the demo's "agent" step, scripted for determinism: it starts nothing
itself. run.py's in-sandbox sequence has already started FreeCAD under Xvfb
(with the freecad-mcp addon auto-starting its RPC server on 127.0.0.1:9875)
and the freecad-mcp MCP server process; this script only talks to the MCP
server over stdio and asks it to execute the checked-in agent build scripts
inside FreeCAD.

Outputs land in examples/good/<part>/ (or --out-dir) and are then graded by
judge/grade.sh. This script never grades anything itself.
"""
import argparse
import os
import re
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from mcp_client import McpError, McpStdioClient, execute_build_script  # noqa: E402

PARTS = {
    "bushing": ("build_bushing.py", ["bushing.step", "bushing.stl"], None),
    "plate": ("build_plate.py", ["plate.step", "plate.stl"],
              ("draw_plate_dxf.py", ["plate.dxf"])),
    "bracket": ("build_bracket.py", ["bracket.step", "bracket.stl"], None),
}
RPC_PORT = 9875


def wait_rpc_port(host="127.0.0.1", port=RPC_PORT, timeout_s=180,
                  log_path="/tmp/freecad.log"):
    """Wait for the FreeCAD RPC addon to accept connections on its port."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            time.sleep(2)
    # Not up in time: show why FreeCAD did not start (or did not auto-start
    # the addon) before failing.
    try:
        with open(log_path, "r", errors="replace") as f:
            tail = "".join(f.readlines()[-25:])
    except OSError:
        tail = "(no %s; FreeCAD may have failed before creating it)" % log_path
    print("FATAL: FreeCAD RPC addon is not listening on port %d after %d s.\n"
          "Tail of %s:\n%s" % (port, timeout_s, log_path, tail), file=sys.stderr)
    return False


def wait_tool_ready(client, timeout_s=120):
    """The RPC server can be up before the GUI dispatch is; probe it."""
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            status = client.call_tool("get_rpc_status", {})
            if '"running"' in status and '"healthy"' in status:
                return True
            last = status
        except McpError as e:
            last = str(e)
        time.sleep(3)
    raise RuntimeError("FreeCAD RPC not healthy: %s" % last)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=os.path.join(ROOT, "examples", "good"))
    ap.add_argument("--parts", nargs="*", default=sorted(PARTS),
                    choices=sorted(PARTS))
    ap.add_argument("--mcp-command", nargs="+", default=["freecad-mcp"])
    ap.add_argument("--freecadcmd", default=None,
                    help="freecadcmd executable for execute_code_headless "
                         "(default: auto-detect)")
    ap.add_argument("--rpc-wait-s", type=int, default=180)
    args = ap.parse_args()

    if not wait_rpc_port(timeout_s=args.rpc_wait_s):
        return 2

    client = McpStdioClient(
        args.mcp_command + (["--freecadcmd", args.freecadcmd] if args.freecadcmd else []))
    ok = True
    try:
        info = client.initialize()
        print("[drive] MCP server initialized: %s" % info)
        wait_tool_ready(client)
        for part in args.parts:
            script, expected, followup = PARTS[part]
            out_dir = os.path.abspath(os.path.join(args.out_root, part))
            os.makedirs(out_dir, exist_ok=True)
            t0 = time.time()
            script_path = os.path.join(ROOT, "agent", script)
            # All builds go through execute_code_headless: the MCP server runs
            # them in isolated freecadcmd processes. This is the tool's
            # documented mode for script work that must not depend on the GUI
            # thread (the GUI + RPC addon are exercised above via
            # get_rpc_status through the same MCP server).
            text = execute_build_script(client, script_path, out_dir, headless=True)
            if followup is not None:
                text += "\n" + execute_build_script(
                    client, os.path.join(ROOT, "agent", followup[0]), out_dir,
                    headless=True)
            dt = time.time() - t0
            m = re.search(r"_OK volume=([0-9.]+)", text)
            missing = [f for f in expected if not os.path.exists(os.path.join(out_dir, f))]
            if m and not missing:
                print("[drive] %-8s OK  volume=%s mm^3  (%.1f s)" % (part, m.group(1), dt))
            else:
                ok = False
                print("[drive] %-8s FAILED (%.1f s): %s" % (part, dt, text[-400:]),
                      file=sys.stderr)
    finally:
        client.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
