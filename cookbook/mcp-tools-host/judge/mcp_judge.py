#!/usr/bin/env python3
"""Judge for the mcp-tools-host demo (gates G1..G8 of SPEC.md).

Speaks the real MCP protocol over stdio to a server.py artifact using
the pinned official ``mcp`` SDK client, and grades it against oracles
computed here, in this process — never against anything the artifact
produces or asserts:

* G3 sqlite_query  — this judge writes its own SQLite database (seeded
  by ``--seed``), runs the fixed SELECT through its own ``sqlite3`` and
  compares rows exactly (order and types preserved).
* G4 file_search   — this judge builds its own workspace tree (seeded)
  and compares against its own ``os.walk`` + substring scan.
* G5 unit_convert  — factors are exact decimals defined once here;
  temperature converts affinely through Celsius.
* G6 calculate     — the oracle parses the expression with ``ast`` and
  evaluates it with explicit operator dispatch (``operator`` module),
  independent of the artifact's parser.
* G7 traversal     — probes with absolute paths and ``..`` escapes that
  point at judge-private material outside the server's workspace must
  be cleanly refused, never answered with data.
* G8 robustness    — missing/wrong-typed arguments must error, not
  crash; the server must still answer ``ping`` at the end.

Judge integrity (J0): the sha256 of the whole ``judge/`` tree is taken
before and after grading; any change fails the run.  The artifact is
copied to a temp dir and launched from there with that dir as its
working directory — the workspace contract of SPEC.md.

The verdict is one JSON document (byte-identical across runs with the
same seed and artifact, except wall-time fields under ``timing``).
Exit status 0 only if every gate passes.

Usage:
    mcp_judge.py <artifact> [--seed N] [--json out.json]
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import operator
import os
import random
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

JUDGE_DIR = Path(__file__).resolve().parent

DEFAULT_SEED = 20261015
HANDSHAKE_TIMEOUT_S = 25.0   # SPEC G1
CALL_TIMEOUT_S = 30.0

SEARCH_TOKEN = "zebra"
SQL_SELECT = ("SELECT id, name, value, note FROM sensors "
              "WHERE id % 2 = 0 ORDER BY id;")

# G2: the four tools, exactly these names, inputSchema matching this
# pinned draft-07 subset (extra annotation keys like "title" are fine).
EXPECTED_TOOLS = {
    "sqlite_query": {
        "type": "object",
        "properties": {"query": "string", "db_path": "string"},
        "required": {"query", "db_path"},
    },
    "file_search": {
        "type": "object",
        "properties": {"pattern": "string", "root": "string"},
        "required": {"pattern", "root"},
    },
    "unit_convert": {
        "type": "object",
        "properties": {"value": "number", "from_unit": "string",
                       "to_unit": "string"},
        "required": {"value", "from_unit", "to_unit"},
    },
    "calculate": {
        "type": "object",
        "properties": {"expression": "string"},
        "required": {"expression"},
    },
}

# G5: exact decimal factors to the base unit (metre, kilogram).
LENGTH_FACTORS = {"m": 1, "km": 1000, "cm": 0.01, "mm": 0.001,
                  "mi": 1609.344, "ft": 0.3048, "in": 0.0254}
MASS_FACTORS = {"kg": 1, "g": 0.001, "lb": 0.45359237,
                "oz": 0.028349523125}
CONVERSION_CASES = [
    (5.0, "km", "mi"),
    (10.0, "kg", "lb"),
    (37.0, "C", "F"),
    (100.0, "m", "ft"),
    (250.0, "g", "oz"),
]

# G6: fixed expressions over the SPEC grammar (+ - * / ** ( ), numbers,
# unary minus); the oracle below evaluates them independently.
EXPRESSIONS = [
    "1+2*3", "(1+2)*3", "2**10", "-4+10", "1/3+1/3+1/3", "2.5*4",
    "(2+3)*(4-1)", "100/8", "-(3**2)", "1.5e3/10",
]
EXPRESSION_ERRORS = [
    "1/(2-2)",              # division by zero
    "1 + * 2",              # malformed
    "os.system('rm -rf /')",  # names/calls must be refused
]

# G7: judge-private material lives OUTSIDE the server workspace.
SECRET = "swordfish"


# ---------------------------------------------------------------------------
# Independent oracles.
# ---------------------------------------------------------------------------

def oracle_convert(value: float, from_unit: str, to_unit: str) -> float:
    src, dst = from_unit.lower(), to_unit.lower()
    if src in LENGTH_FACTORS and dst in LENGTH_FACTORS:
        return value * LENGTH_FACTORS[src] / LENGTH_FACTORS[dst]
    if src in MASS_FACTORS and dst in MASS_FACTORS:
        return value * MASS_FACTORS[src] / MASS_FACTORS[dst]
    if src in ("c", "f", "k") and dst in ("c", "f", "k"):
        celsius = {"c": value, "f": (value - 32.0) * 5.0 / 9.0,
                   "k": value - 273.15}[src]
        return {"c": celsius, "f": celsius * 9.0 / 5.0 + 32.0,
                "k": celsius + 273.15}[dst]
    raise ValueError(f"no conversion {from_unit}->{to_unit}")


_OPS = {
    "Add": operator.add,
    "Sub": operator.sub,
    "Mult": operator.mul,
    "Div": operator.truediv,
    "Pow": operator.pow,
}


def oracle_eval(text: str) -> float:
    """Evaluate ``text`` over the SPEC grammar with explicit dispatch."""

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or \
                    not isinstance(node.value, (int, float)):
                raise ValueError("non-numeric constant")
            return node.value
        if isinstance(node, ast.BinOp):
            fn = _OPS.get(type(node.op).__name__)
            if fn is None:
                raise ValueError(f"operator {type(node.op).__name__} "
                                 "not in the graded grammar")
            return fn(ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.UAdd):
                return +ev(node.operand)
            if isinstance(node.op, ast.USub):
                return -ev(node.operand)
            raise ValueError("unexpected unary operator")
        raise ValueError(f"construct {type(node).__name__} refused")

    return ev(ast.parse(text, mode="eval"))


# ---------------------------------------------------------------------------
# Judge-owned fixtures (built from the seed; the artifact never sees the
# recipe, only the resulting files inside its own workspace).
# ---------------------------------------------------------------------------

def build_workspace(srv: Path, seed: int) -> Path:
    ws = srv / "ws"
    rng = random.Random(seed)
    files = {
        "docs/readme.md": "sampler workspace for the mcp-tools-host demo\n",
        "docs/zebra_report.md": f"quarterly report, batch {rng.randrange(1000)}\n",
        "src/core/engine.py": "def run():\n    return 42\n",
        "src/core/zebra_patch.py": "patch notes: none\n",
        "data/run.csv": "t,v\n1,2\n3,4\n",
        "data/plain_01.txt": f"note {rng.randrange(1000)}: ZEBRA crossing at dawn\n",
        "data/plain_02.txt": "no match in here\n",
        "notes/keep.txt": "the quick brown fox\n",
        "notes/hints.md": "search for ZEBRA in the data folder\n",
        "top_level.txt": "a file at the workspace root\n",
    }
    for rel, text in files.items():
        p = ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return ws


def oracle_search(ws: Path, token: str) -> list:
    """Ground truth for file_search: own os.walk + substring scan."""
    needle = token.lower()
    hits = []
    for dirpath, _dirs, names in os.walk(ws):
        for name in names:
            full = Path(dirpath) / name
            rel = full.relative_to(ws).as_posix()
            if needle in rel.lower():
                hits.append(rel)
                continue
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if needle in text.lower():
                hits.append(rel)
    return sorted(hits)


def build_db(srv: Path, seed: int) -> Path:
    data = srv / "data"
    data.mkdir(parents=True, exist_ok=True)
    db = data / "app.db"
    rng = random.Random(seed ^ 0x5EED)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE sensors("
                "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "value REAL NOT NULL, note TEXT)")
    for i in range(1, 25):
        name = f"sensor-{i:02d}"
        value = round(rng.uniform(-20.0, 80.0), 3)
        note = None if i % 3 == 0 else f"calib {rng.randrange(100)}"
        con.execute("INSERT INTO sensors VALUES (?,?,?,?)",
                    (i, name, value, note))
    con.commit()
    con.close()
    return db


def oracle_query(db: Path, sql: str):
    con = sqlite3.connect(db)
    try:
        cur = con.execute(sql.rstrip(";"))
        rows = [list(r) for r in cur.fetchall()]
    finally:
        con.close()
    return rows


def build_private(tmp: Path) -> Path:
    """Judge-private dir OUTSIDE the server workspace (G7 probe target)."""
    priv = tmp / "private"
    priv.mkdir()
    (priv / "secret.txt").write_text(f"token: {SECRET}\n", encoding="utf-8")
    con = sqlite3.connect(priv / "vault.db")
    con.execute("CREATE TABLE vault(token TEXT)")
    con.execute("INSERT INTO vault VALUES (?)", (SECRET,))
    con.commit()
    con.close()
    return priv


def judge_tree_hash() -> str:
    h = hashlib.sha256()
    for p in sorted(JUDGE_DIR.rglob("*")):
        if p.is_file() and p.name != "VERSIONS.txt":
            rel = p.relative_to(JUDGE_DIR).as_posix()
            h.update(rel.encode())
            h.update(p.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# MCP client helpers.
# ---------------------------------------------------------------------------

def text_of(res) -> str:
    parts = []
    for block in res.content:
        txt = getattr(block, "text", None)
        if isinstance(txt, str):
            parts.append(txt)
    return "".join(parts)


def payload_of(res):
    if getattr(res, "structuredContent", None) is not None:
        return res.structuredContent
    txt = text_of(res).strip()
    if not txt:
        return None
    try:
        return json.loads(txt)
    except ValueError:
        return None


def clean_refusal(kind, res) -> bool:
    """A gate-passing refusal: isError, an MCP error response, or an
    error object — never data."""
    if kind == "mcp_error":
        return True
    if kind != "ok":
        return False
    if res.isError:
        return True
    obj = payload_of(res)
    return isinstance(obj, dict) and isinstance(obj.get("error"), str)


async def call(session, name, args, timeout=CALL_TIMEOUT_S):
    try:
        res = await asyncio.wait_for(session.call_tool(name, args), timeout)
        return "ok", res
    except Exception as exc:  # noqa: BLE001 - classified by caller
        from mcp.shared.exceptions import McpError
        if isinstance(exc, McpError):
            return "mcp_error", exc
        return "fail", exc


class Scrubber:
    """Keeps temp paths out of the verdict (byte-determinism)."""

    def __init__(self, tmp: Path):
        self.tokens = [str(tmp), os.path.realpath(tmp)]

    def __call__(self, value):
        if isinstance(value, str):
            for t in self.tokens:
                value = value.replace(t, "<tmp>")
            return re.sub(r"/tmp/[\w.-]{6,}", "<tmp>/…", value)
        if isinstance(value, list):
            return [self(v) for v in value]
        if isinstance(value, dict):
            return {k: self(v) for k, v in value.items()}
        return value


def rel_err(got, want) -> float:
    if want == 0:
        return abs(got - want)
    return abs(got - want) / abs(want)


# ---------------------------------------------------------------------------
# The gates.
# ---------------------------------------------------------------------------

async def grade(artifact: Path, seed: int) -> dict:
    scrub = None
    tmp = Path(tempfile.mkdtemp(prefix="mcpj-"))
    srv = tmp / "srv"
    srv.mkdir()
    shutil.copyfile(artifact, srv / "server.py")

    ws = build_workspace(srv, seed)
    db = build_db(srv, seed)
    priv = build_private(tmp)
    scrub = Scrubber(tmp)

    verdict = {
        "demo": "mcp-tools-host",
        "artifact": artifact.name,
        "seed": seed,
        "all_gates_passed": False,
        "gates": {},
        "timing": {"gates": {}, "total_seconds": None},
    }
    t_total = time.monotonic()
    tree_before = judge_tree_hash()

    def fail(name, detail, started):
        verdict["gates"][name] = {"passed": False, **detail}
        verdict["timing"]["gates"][name] = round(time.monotonic() - started, 3)

    def done(name, passed, detail, started):
        verdict["gates"][name] = {"passed": bool(passed), **detail}
        verdict["timing"]["gates"][name] = round(time.monotonic() - started, 3)

    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
           "HOME": str(srv)}
    params = StdioServerParameters(
        command=sys.executable, args=["server.py"], cwd=str(srv), env=env)

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                # ---- G1: protocol handshake -------------------------
                t0 = time.monotonic()
                try:
                    shebang = artifact.read_text(
                        encoding="utf-8").startswith("#!")
                    init = await asyncio.wait_for(
                        session.initialize(), HANDSHAKE_TIMEOUT_S)
                    await asyncio.wait_for(session.send_ping(),
                                           CALL_TIMEOUT_S)
                    g1 = {"protocol_version": init.protocolVersion,
                          "server_name": init.serverInfo.name,
                          "shebang": shebang}
                    done("G1_handshake", bool(
                        init.protocolVersion and init.serverInfo.name
                        and shebang), g1, t0)
                except Exception as exc:  # noqa: BLE001
                    fail("G1_handshake", {"error": scrub(repr(exc))}, t0)

                # ---- G2: tool list and schemas ----------------------
                t0 = time.monotonic()
                try:
                    listed = await asyncio.wait_for(
                        session.list_tools(), CALL_TIMEOUT_S)
                    names = sorted(t.name for t in listed.tools)
                    mismatches = []
                    for t in listed.tools:
                        exp = EXPECTED_TOOLS.get(t.name)
                        if exp is None:
                            continue
                        sch = t.inputSchema or {}
                        if sch.get("type") != exp["type"]:
                            mismatches.append(f"{t.name}: schema type")
                        props = sch.get("properties", {})
                        for pname, ptype in exp["properties"].items():
                            got = props.get(pname)
                            if not isinstance(got, dict):
                                mismatches.append(
                                    f"{t.name}: missing property {pname}")
                            elif got.get("type") != ptype:
                                mismatches.append(
                                    f"{t.name}.{pname}: type "
                                    f"{got.get('type')!r} != {ptype!r}")
                        if set(sch.get("required", [])) != exp["required"]:
                            mismatches.append(
                                f"{t.name}: required set mismatch")
                    ok = (names == sorted(EXPECTED_TOOLS)
                          and not mismatches)
                    done("G2_tools_and_schemas", ok,
                         {"tools": names,
                          "schema_mismatches": scrub(mismatches)}, t0)
                except Exception as exc:  # noqa: BLE001
                    fail("G2_tools_and_schemas",
                         {"error": scrub(repr(exc))}, t0)

                # ---- G3: sqlite_query vs own sqlite3 ----------------
                t0 = time.monotonic()
                try:
                    expected_rows = oracle_query(db, SQL_SELECT)
                    kind, res = await call(session, "sqlite_query",
                                           {"query": SQL_SELECT,
                                            "db_path": str(db)})
                    ok = kind == "ok" and not res.isError
                    got_rows = None
                    if ok:
                        obj = payload_of(res)
                        got_rows = (obj or {}).get("rows") \
                            if isinstance(obj, dict) else None
                        ok = got_rows == expected_rows
                        detail = {"rows_compared": len(expected_rows),
                                  "rows_returned": len(got_rows)
                                  if isinstance(got_rows, list) else 0}
                    else:
                        detail = {"error": scrub(text_of(res))
                                  if kind == "ok" else scrub(repr(res))}
                    done("G3_sqlite_query", ok, detail, t0)
                except Exception as exc:  # noqa: BLE001
                    fail("G3_sqlite_query", {"error": scrub(repr(exc))}, t0)

                # ---- G4: file_search vs own os.walk scan ------------
                t0 = time.monotonic()
                try:
                    expected_hits = oracle_search(ws, SEARCH_TOKEN)
                    kind, res = await call(session, "file_search",
                                           {"pattern": SEARCH_TOKEN,
                                            "root": str(ws)})
                    ok = kind == "ok" and not res.isError
                    if ok:
                        obj = payload_of(res) or {}
                        matches = obj.get("matches", []) \
                            if isinstance(obj, dict) else []
                        # order must already be sorted (SPEC G4)
                        got_hits = [m.get("path") if isinstance(m, dict)
                                    else m for m in matches]
                        ok = got_hits == expected_hits
                        detail = {"expected_matches": len(expected_hits),
                                  "returned_matches": len(got_hits),
                                  "paths": expected_hits}
                    else:
                        detail = {"error": scrub(text_of(res))
                                  if kind == "ok" else scrub(repr(res))}
                    done("G4_file_search", ok, scrub(detail), t0)
                except Exception as exc:  # noqa: BLE001
                    fail("G4_file_search", {"error": scrub(repr(exc))}, t0)

                # ---- G5: unit_convert vs exact decimals -------------
                t0 = time.monotonic()
                try:
                    worst = 0.0
                    ok = True
                    table = []
                    for value, fu, tu in CONVERSION_CASES:
                        want = oracle_convert(value, fu, tu)
                        kind, res = await call(session, "unit_convert",
                                               {"value": value,
                                                "from_unit": fu,
                                                "to_unit": tu})
                        got = None
                        if kind == "ok" and not res.isError:
                            obj = payload_of(res)
                            if isinstance(obj, dict):
                                got = obj.get("result")
                        if not isinstance(got, (int, float)) or \
                                isinstance(got, bool):
                            ok = False
                            table.append([value, fu, tu, want, None])
                            continue
                        err = rel_err(got, want)
                        worst = max(worst, err)
                        if err > 1e-9:
                            ok = False
                        table.append([value, fu, tu, want, got])
                    refused_unknown = clean_refusal(
                        *(await call(session, "unit_convert",
                                     {"value": 1.0, "from_unit": "warp",
                                      "to_unit": "mi"})))
                    refused_cross = clean_refusal(
                        *(await call(session, "unit_convert",
                                     {"value": 1.0, "from_unit": "km",
                                      "to_unit": "kg"})))
                    done("G5_unit_convert",
                         ok and refused_unknown and refused_cross,
                         {"conversions": table,
                          "max_rel_error": worst,
                          "unknown_unit_refused": refused_unknown,
                          "cross_dimension_refused": refused_cross}, t0)
                except Exception as exc:  # noqa: BLE001
                    fail("G5_unit_convert", {"error": scrub(repr(exc))}, t0)

                # ---- G6: calculate vs ast oracle --------------------
                t0 = time.monotonic()
                try:
                    worst = 0.0
                    ok = True
                    table = []
                    for expr in EXPRESSIONS:
                        want = oracle_eval(expr)
                        kind, res = await call(session, "calculate",
                                               {"expression": expr})
                        got = None
                        if kind == "ok" and not res.isError:
                            obj = payload_of(res)
                            if isinstance(obj, dict):
                                got = obj.get("result")
                        if not isinstance(got, (int, float)) or \
                                isinstance(got, bool):
                            ok = False
                            table.append([expr, want, None])
                            continue
                        err = rel_err(got, want)
                        worst = max(worst, err)
                        if err > 1e-9:
                            ok = False
                        table.append([expr, want, got])
                    errors_ok = True
                    for expr in EXPRESSION_ERRORS:
                        kind, res = await call(session, "calculate",
                                               {"expression": expr})
                        if not clean_refusal(kind, res):
                            errors_ok = False
                    done("G6_calculate", ok and errors_ok,
                         {"expressions": table, "max_rel_error": worst,
                          "bad_expressions_refused": errors_ok}, t0)
                except Exception as exc:  # noqa: BLE001
                    fail("G6_calculate", {"error": scrub(repr(exc))}, t0)

                # ---- G7: traversal refused ---------------------------
                t0 = time.monotonic()
                try:
                    probes = [
                        ("file_search", "file_search absolute outside",
                         {"pattern": "secret", "root": str(priv)}),
                        ("file_search", "file_search .. escape",
                         {"pattern": "secret",
                          "root": "ws/../../private"}),
                        ("sqlite_query", "sqlite_query absolute outside",
                         {"query": "SELECT token FROM vault",
                          "db_path": str(priv / "vault.db")}),
                        ("sqlite_query", "sqlite_query .. escape",
                         {"query": "SELECT token FROM vault",
                          "db_path": "ws/../../private/vault.db"}),
                    ]
                    refused = {}
                    leaked = {}
                    for tool, label, args in probes:
                        kind, res = await call(session, tool, args)
                        was_refused = clean_refusal(kind, res)
                        refused[label] = was_refused
                        if not was_refused:
                            blob = text_of(res) if kind == "ok" else repr(res)
                            leaked[label] = SECRET in blob
                    ok = all(refused.values()) and not any(leaked.values())
                    done("G7_traversal_refused", ok,
                         {"probes_refused": refused,
                          "leaked": leaked or None}, t0)
                except Exception as exc:  # noqa: BLE001
                    fail("G7_traversal_refused",
                         {"error": scrub(repr(exc))}, t0)

                # ---- G8: robustness ----------------------------------
                t0 = time.monotonic()
                try:
                    probes = [
                        ("sqlite_query", "missing args",
                         {"db_path": str(db)}),
                        ("file_search", "wrong-typed pattern",
                         {"pattern": {"deep": 1}, "root": str(ws)}),
                        ("unit_convert", "wrong-typed value",
                         {"value": "not-a-number", "from_unit": "m",
                          "to_unit": "km"}),
                        ("calculate", "wrong-typed expression",
                         {"expression": ["1+1"]}),
                        ("sqlite_query", "write attempt",
                         {"query": "DROP TABLE sensors",
                          "db_path": str(db)}),
                    ]
                    results = {}
                    for tool, label, args in probes:
                        kind, res = await call(session, tool, args)
                        results[label] = clean_refusal(kind, res)
                    try:
                        await asyncio.wait_for(session.send_ping(),
                                               CALL_TIMEOUT_S)
                        alive = True
                    except Exception:  # noqa: BLE001, B110
                        alive = False
                    done("G8_robustness", all(results.values()) and alive,
                         {"bad_input_refused": results,
                          "server_alive_at_end": alive}, t0)
                except Exception as exc:  # noqa: BLE001
                    fail("G8_robustness", {"error": scrub(repr(exc))}, t0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- J0: judge-tree integrity (fails closed) --------------------
    verdict["gates"]["J0_judge_integrity"] = {
        "passed": judge_tree_hash() == tree_before}
    verdict["timing"]["total_seconds"] = round(
        time.monotonic() - t_total, 3)
    verdict["all_gates_passed"] = all(
        g["passed"] for g in verdict["gates"].values())
    return verdict


def main() -> int:
    ap = argparse.ArgumentParser(description="mcp-tools-host judge")
    ap.add_argument("artifact", type=Path)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    artifact = args.artifact.resolve()
    if not artifact.is_file():
        print(f"mcp_judge: artifact not found: {artifact}", file=sys.stderr)
        return 2

    verdict = asyncio.run(grade(artifact, args.seed))
    text = json.dumps(verdict, indent=2, sort_keys=True)
    print(text)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
    return 0 if verdict["all_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
