#!/usr/bin/env python3
"""sbx-mcp-tools: a small stdio MCP server that hosts four tools.

The server speaks MCP over stdio using the official ``mcp`` Python SDK
(FastMCP).  It is the known-good artifact for the mcp-tools-host demo.

Workspace contract
------------------
The host launches the server with its working directory set to the
workspace the tools are allowed to touch.  Every tool that takes a
path (``root`` for file_search, ``db_path`` for sqlite_query) resolves
it and refuses — by raising a tool error (MCP ``isError: true``),
never by returning data from outside — any path that escapes that
workspace, whether by absolute path or by ``..`` components.  The
server never writes to stdout (that would corrupt the JSON-RPC
protocol stream) and never exits on bad input: it raises a tool error
and keeps answering.

Tools
-----
``sqlite_query(query, db_path)``
    Run one read-only SQL SELECT and return ``{"columns", "rows"}``.
``file_search(pattern, root)``
    Return files under ``root`` whose relative path or text content
    contains ``pattern`` (case-insensitive), as posix paths relative
    to ``root``, sorted.
``unit_convert(value, from_unit, to_unit)``
    Convert between units of one physical dimension (length, mass,
    temperature) using exact decimal factors (temperature affinely).
``calculate(expression)``
    Evaluate pure arithmetic (+ - * / // % ** and parentheses, unary
    minus, no names or calls) with a small AST-walking parser.
"""

from __future__ import annotations

import ast
import os
import sqlite3
import urllib.parse
from pathlib import Path

from mcp.server.fastmcp import FastMCP

SERVER_NAME = "sbx-mcp-tools"

mcp = FastMCP(SERVER_NAME)


# ---------------------------------------------------------------------------
# Workspace containment: paths must resolve inside the server's working
# directory (the workspace the host gave it at launch).
# ---------------------------------------------------------------------------

def _resolve_inside(raw: str, what: str) -> Path:
    """Resolve ``raw`` and refuse anything outside the launch workspace."""
    base = Path.cwd().resolve()
    target = Path(raw)
    if not target.is_absolute():
        target = base / target
    target = target.resolve()
    if target != base and base not in target.parents:
        raise PermissionError(
            f"{what} must stay inside the workspace ({base}); refused: {raw}"
        )
    return target


# ---------------------------------------------------------------------------
# Unit conversion: multiplicative factors to the base unit (m, kg);
# temperature converts affinely through degrees Celsius.
# ---------------------------------------------------------------------------

UNIT_FACTORS: dict[str, dict[str, float]] = {
    "length": {
        "m": 1.0,
        "km": 1000.0,
        "cm": 0.01,
        "mm": 0.001,
        "mi": 1609.344,
        "ft": 0.3048,
        "in": 0.0254,
    },
    "mass": {
        "kg": 1.0,
        "g": 0.001,
        "lb": 0.45359237,
        "oz": 0.028349523125,
    },
}


def _convert(value: float, from_unit: str, to_unit: str) -> float:
    src, dst = from_unit.lower(), to_unit.lower()
    for table in UNIT_FACTORS.values():
        if src in table and dst in table:
            return value * table[src] / table[dst]
    if src in ("c", "f", "k") and dst in ("c", "f", "k"):
        celsius = {"c": value, "f": (value - 32.0) * 5.0 / 9.0,
                   "k": value - 273.15}[src]
        return {"c": celsius, "f": celsius * 9.0 / 5.0 + 32.0,
                "k": celsius + 273.15}[dst]
    known = sorted({u for t in UNIT_FACTORS.values() for u in t} |
                   {"c", "f", "k"})
    raise ValueError(f"unknown or mismatched units {from_unit!r} -> "
                     f"{to_unit!r} (known: {', '.join(known)})")


# ---------------------------------------------------------------------------
# Safe arithmetic: parse to an AST, walk it with no names/calls/builtins.
# ---------------------------------------------------------------------------

_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"constant {node.value!r} is not a number")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_safe_eval(node.left),
                                       _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _safe_eval(node.operand)
        return v if isinstance(node.op, ast.UAdd) else -v
    raise ValueError(f"expression uses a forbidden construct "
                     f"({type(node).__name__})")


# ---------------------------------------------------------------------------
# The four tools.
# ---------------------------------------------------------------------------

@mcp.tool()
def sqlite_query(query: str, db_path: str) -> dict:
    """Run one read-only SQL SELECT against an SQLite database file.

    ``db_path`` must point inside the server's workspace.  Returns
    ``{"columns": [...], "rows": [[...], ...]}`` on success.  Anything
    invalid (missing file, bad SQL, non-SELECT statement, path outside
    the workspace) raises a tool error (``isError: true``).
    """
    try:
        path = _resolve_inside(db_path, "db_path")
        q = query.strip()
        if q.endswith(";"):  # one optional trailing terminator is fine
            q = q[:-1].strip()
        if ";" in q:
            raise ValueError("exactly one statement, no ';' chaining")
        if not q.lower().startswith("select"):
            raise ValueError("only a single read-only SELECT is supported")
        uri = "file:" + urllib.parse.quote(str(path)) + "?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            cur = con.execute(q)  # read-only connection, one statement
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [list(r) for r in cur.fetchall()]
        finally:
            con.close()
        return {"columns": columns, "rows": rows}
    except Exception as exc:
        # A clean refusal: raise so the SDK reports isError=true; the
        # server itself survives and keeps answering.
        raise ValueError(f"{type(exc).__name__}: {exc}") from exc


@mcp.tool()
def file_search(pattern: str, root: str) -> dict:
    """List files under ``root`` whose relative path or content matches.

    ``root`` must point inside the server's workspace; a path that
    escapes it raises a tool error (``isError: true``).  A file matches
    when its path relative to ``root`` or its text content contains
    ``pattern`` (case-insensitive).  Returns ``{"matches": [{"path":
    ...}, ...]}`` with posix paths relative to ``root``, sorted.
    """
    try:
        base = _resolve_inside(root, "root")
        if not base.is_dir():
            raise NotADirectoryError(root)
        needle = pattern.lower()
        hits = []
        for dirpath, _dirnames, filenames in os.walk(base):
            for fname in filenames:
                full = Path(dirpath) / fname
                rel = full.relative_to(base).as_posix()
                if needle in rel.lower():
                    hits.append(rel)
                    continue
                try:
                    text = full.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue  # unreadable file: not a match, not an error
                if needle in text.lower():
                    hits.append(rel)
        hits.sort()
        return {"matches": [{"path": h} for h in hits]}
    except Exception as exc:
        # A clean refusal: raise so the SDK reports isError=true; the
        # server itself survives and keeps answering.
        raise ValueError(f"{type(exc).__name__}: {exc}") from exc


@mcp.tool()
def unit_convert(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert ``value`` between units of one physical dimension.

    Length (m, km, cm, mm, mi, ft, in), mass (kg, g, lb, oz) and
    temperature (C, F, K) are supported.  Returns ``{"result": number,
    "unit": to_unit}``; unknown units or a dimension mismatch raise a
    tool error (``isError: true``).
    """
    try:
        result = _convert(value, from_unit, to_unit)
        return {"result": result, "unit": to_unit}
    except Exception as exc:
        # A clean refusal: raise so the SDK reports isError=true.
        raise ValueError(f"{type(exc).__name__}: {exc}") from exc


@mcp.tool()
def calculate(expression: str) -> dict:
    """Evaluate one arithmetic expression safely (no eval of code).

    Accepts + - * / // % ** ( ), numbers and unary minus; names, calls
    and any other construct are refused.  Returns ``{"result": number}``;
    malformed input or division by zero raise a tool error
    (``isError: true``).
    """
    try:
        tree = ast.parse(expression, mode="eval")
        return {"result": _safe_eval(tree)}
    except Exception as exc:
        # Malformed input, forbidden constructs, division by zero: a
        # clean tool error (isError: true), never a crash.
        raise ValueError(f"{type(exc).__name__}: {exc}") from exc


def main() -> int:
    mcp.run()  # stdio transport; never writes to stdout
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
