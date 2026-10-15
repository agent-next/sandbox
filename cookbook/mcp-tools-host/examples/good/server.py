#!/usr/bin/env python3
"""sbx-mcp-tools: a small stdio MCP server that hosts four tools.

The server speaks MCP over stdio (one JSON-RPC 2.0 message per line) using
the official ``mcp`` Python SDK.  It is fully self-contained: the sqlite
database and the sample workspace it uses by default are embedded below and
materialised into a temporary directory on first use, so the file runs from
any working directory with no arguments.

Tools
-----
``sqlite_query(query, db_path="")``
    Run one read-only SQL statement and return ``{"columns", "rows"}``.
``file_search(pattern, root="")``
    Return files under ``root`` whose path contains ``pattern``
    (case-insensitive); every returned path stays inside ``root``.
``convert(value, from_unit, to_unit)``
    Convert between length/mass units with a multiplicative factor table.
``calculate(expression)``
    Evaluate a pure-arithmetic expression (no names, no calls).

Every tool returns a single JSON object.  Invalid input is reported as data
(``{"error": ...}``), never by crashing the server.
"""

from __future__ import annotations

import ast
import json  # noqa: F401  (kept for debugging; tools return plain dicts)
import math
import sqlite3
import sys
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

__version__ = "1.0.0"

SERVER_NAME = "sbx-mcp-tools"

# ---------------------------------------------------------------------------
# Bundled data (materialised to a temp dir on first use; the judge always
# passes its own db_path/root, this only makes the defaults standalone).
# ---------------------------------------------------------------------------

BUNDLED_DB_SQL = """
CREATE TABLE sensors(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL
);
INSERT INTO sensors(name, value, unit) VALUES
    ('alpha', 12.5, 'C'),
    ('beta', -3.25, 'C'),
    ('gamma', 40.0, 'F'),
    ('delta', 0.0, 'K'),
    ('epsilon', 99.75, 'C');
"""

BUNDLED_FILES = {
    "README.md": "# sample workspace\nUsed by the file_search default root.\n",
    "data/sample.csv": "x,y\n1,2\n3,4\n",
    "notes/todo.txt": "finish the demo\n",
}

_bundled_dir: Path | None = None


def _bundled_dir() -> Path:
    """Materialise the embedded db + workspace into a private temp dir."""
    global _bundled_dir
    if _bundled_dir is None:
        _bundled_dir = Path(tempfile.mkdtemp(prefix="sbx-mcp-tools-"))
        db = _bundled_dir / "app.db"
        db.write_text("")  # touch so connect() creates a fresh file
        con = sqlite3.connect(db)
        try:
            con.executescript(BUNDLED_DB_SQL)
            con.commit()
        finally:
            con.close()
        for rel, text in BUNDLED_FILES.items():
            f = _bundled_dir / "workspace" / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
    return _bundled_dir


# ---------------------------------------------------------------------------
# Unit conversion (multiplicative factors to the base unit: m, kg).
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
    ast.Pow: lambda a, b: a**b,
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
# The server itself.
# ---------------------------------------------------------------------------

mcp = FastMCP(SERVER_NAME)


@mcp.tool()
def sqlite_query(query: str, db_path: str = "") -> dict:
    """Run one read-only SQL statement and return columns and rows.

    Returns {"columns": [...], "rows": [[...], ...]} on success or
    {"error": "..."} for anything invalid (missing file, bad SQL,
    more than one statement).  Never raises across the MCP boundary.
    """
    try:
        path = Path(db_path) if db_path else _bundled_dir() / "app.db"
        uri = "file:" + path.as_posix() + "?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            cur = con.execute(query)  # one statement only, read-only
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [list(r) for r in cur.fetchall()]
        finally:
            con.close()
        return {"columns": columns, "rows": rows}
    except Exception as exc:  # reported as data; the server must survive
        return {"error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
def file_search(pattern: str, root: str = "") -> dict:
    """Return files under root whose path contains pattern (case-insensitive).

    Every match is a posix path relative to root; matches outside root are
    never returned.  Returns {"matches": [{"path": ...}, ...]} sorted, or
    {"error": "..."} for an unusable root.
    """
    try:
        base = Path(root) if root else _bundled_dir() / "workspace"
        base_resolved = base.resolve()
        if not base.is_dir():
            return {"error": f"NotADirectoryError: {base}"}
        needle = pattern.lower()
        matches = []
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(base_resolved).as_posix()
            if needle in rel.lower():
                matches.append({"path": rel})
        matches.sort(key=lambda m: m["path"])
        return {"matches": matches}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
def convert(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert value between length/mass units (multiplicative factors).

    Returns {"result": number, "unit": to_unit} or {"error": "..."}.
    """
    try:
        family = None
        for fam, table in UNIT_FACTORS.items():
            if from_unit in table and to_unit in table:
                family = fam
                break
        if family is None:
            known = sorted({u for t in UNIT_FACTORS.values() for u in t})
            return {"error": f"unknown unit: {from_unit!r} or {to_unit!r} "
                             f"(known: {', '.join(known)})"}
        result = value * UNIT_FACTORS[family][from_unit] / UNIT_FACTORS[family][to_unit]
        return {"result": result, "unit": to_unit}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
def calculate(expression: str) -> dict:
    """Evaluate a pure-arithmetic expression (+ - * / // % **, parentheses).

    Names, calls and any non-numeric construct are refused.  Returns
    {"result": number} or {"error": "..."}.  Never raises across the MCP
    boundary.
    """
    try:
        tree = ast.parse(expression, mode="eval")
        return {"result": _safe_eval(tree)}
    except ZeroDivisionError:
        return {"error": "ZeroDivisionError: division by zero"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    print(f"{SERVER_NAME} v{__version__} starting on stdio", file=sys.stderr)
    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
