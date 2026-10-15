#!/usr/bin/env python3
"""Minimal scripted MCP client (stdio JSON-RPC 2.0) for the freecad-mcp server.

Standard library only. Speaks just enough of the MCP protocol for this demo:
initialize handshake, tools/list, tools/call.
"""
import json
import subprocess
import sys


class McpError(RuntimeError):
    pass


class McpStdioClient:
    def __init__(self, command, stderr_path="/tmp/mcp_server_stderr.log"):
        self.command = command
        self.proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=open(stderr_path, "ab"), text=True, bufsize=1)
        self._id = 0

    def _send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _request(self, method, params):
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise McpError("MCP server closed stdout")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue  # non-JSON noise on stdout
            if msg.get("id") == rid:
                if "error" in msg:
                    raise McpError("MCP error: %s" % msg["error"])
                return msg["result"]

    def initialize(self, client_name="demo-driver", client_version="1.0"):
        result = self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": client_name, "version": client_version}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result.get("serverInfo", {})

    def list_tools(self):
        return [t["name"] for t in self._request("tools/list", {})["tools"]]

    def call_tool(self, name, arguments, timeout_s=180):
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            texts = [c.get("text", "") for c in result.get("content", [])
                     if c.get("type") == "text"]
            raise McpError("tool %s failed: %s" % (name, " | ".join(texts)))
        texts = [c.get("text", "") for c in result.get("content", [])
                 if c.get("type") == "text"]
        return "\n".join(texts)

    def close(self):
        try:
            self._send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}})
        except Exception:
            pass
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def execute_build_script(client, script_path, output_dir, timeout_s=300, headless=False):
    """Run an agent build script inside FreeCAD via execute_code.

    The script's source is passed with OUTPUT_DIR injected as a global, so the
    script itself stays plain FreeCAD Python. With headless=True the script is
    run by the execute_code_headless tool in a separate freecadcmd process
    (used for Draft DXF export, which cannot run on the GUI thread).
    """
    with open(script_path) as f:
        code = f.read()
    wrapped = ("OUTPUT_DIR = %r\n" % output_dir) + code
    tool = "execute_code_headless" if headless else "execute_code"
    return client.call_tool(tool, {"code": wrapped, "timeout": timeout_s},
                            timeout_s=timeout_s + 60)


def main():
    cmd = sys.argv[1:] if len(sys.argv) > 1 else ["freecad-mcp"]
    c = McpStdioClient(cmd)
    try:
        info = c.initialize()
        print("MCP server: %s" % json.dumps(info))
        print("tools: %s" % ", ".join(sorted(c.list_tools())))
        print(c.call_tool("get_rpc_status", {}))
    finally:
        c.close()


if __name__ == "__main__":
    main()
