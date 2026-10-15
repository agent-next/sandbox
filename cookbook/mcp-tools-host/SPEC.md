# SPEC — `cookbook/mcp-tools-host/`

An agent works on a real infrastructure problem inside a disposable
agent-next sandbox: build and fix a **stdio Model Context Protocol (MCP)
server** that an AI assistant can call, where a judge it cannot fool (the
official MCP Python SDK client, plus an independent stdlib oracle) decides
whether the server speaks the protocol and computes the right answers.

## Goal

Produce `server.py`, a stdio MCP server built on the official `mcp` Python
SDK (pinned, installed by `judge/setup.sh`), that registers exactly four
tools and answers them correctly, deterministically and safely:

1. **`sqlite_query`** — run one read-only SQL `SELECT` against an SQLite
   database file given by the caller as `db_path`, return rows.
2. **`file_search`** — list files under a caller-given workspace root whose
   relative path or text content matches a query (substring, case-insensitive).
3. **`unit_convert`** — convert a value between units of one physical
   dimension (length, mass, temperature) with exact decimal factors.
4. **`calculate`** — evaluate one arithmetic expression safely (no `eval` of
   arbitrary code; a small arithmetic parser).

A server that "runs" is not enough: the judge speaks the real MCP protocol
over stdio (initialize → tools/list → tools/call), checks every tool schema,
calls each tool with fixed inputs and compares the results against its own
stdlib computation, and requires that a path-traversal attempt is refused.

## Non-goals

- Streamable HTTP / SSE transports: stdio only (the judge and every MCP
  client launcher use stdio for local servers).
- Persistence, authentication, concurrency beyond one request at a time.
- SQL features beyond a single read-only `SELECT` (no `INSERT`/`UPDATE`/
  `DDL`, no semicolon-chained statements).
- Fuzzy or ranked search: exact case-insensitive substring semantics only.
- A general expression language: `+ - * / ( )`, numbers, unary minus, and
  `**` are all `calculate` must accept.
- Optimality (search speed, db size): correctness and safety only.

## Artifact

A single Python file, `server.py`, launched by the judge as
`python3 server.py` with stdio attached, containing:

- one MCP server object created through the pinned `mcp` SDK and run over
  the stdio transport;
- exactly four registered tools named `sqlite_query`, `file_search`,
  `unit_convert`, `calculate` (see gate G2 for the full schema rules);
- a shebang line (`#!/usr/bin/env python3`) and nothing that reads
  stdin/stdout except the MCP runtime (printing to stdout would corrupt the
  protocol; the server must not write to stdout).

The known-good example uses `mcp.server.fastmcp.FastMCP`; the gates below
apply to any server that registers the four tools with the required
schemas, however it is built on the pinned SDK.

## Judge gates (`judge/grade.sh <artifact> [--seed N] [--json out.json]`)

All gates are numeric/behavioral and deterministic. Exit 0 only if every
gate passes. The judge never executes the artifact's code directly; it only
launches it as a subprocess and speaks MCP to it.

- **G1 protocol handshake**: within **25 s** of launch the server answers
  `initialize` with a valid `InitializeResult` (protocol version, server
  info) and a subsequent `notifications/initialized` + `ping` round-trip
  succeeds. The server process must still be alive afterwards.
- **G2 tool list & schemas**: `tools/list` returns **exactly** the four tool
  names (no missing, no extra) and each tool's `inputSchema` matches its
  pinned schema (JSON Schema draft-07 subset: `type`, `properties`,
  `required`, and per-property `type`/`enum` where the SPEC fixes them).
  Full expected schemas are embedded in `judge/mcp_judge.py`.
- **G3 sqlite_query**: the judge builds its own SQLite db (seeded by
  `--seed`, default `20261015`) with a known table, calls
  `sqlite_query` with a fixed `SELECT`, and requires the returned rows to
  equal the judge's own `sqlite3` query result **exactly** (order
  preserved, types preserved), serialized as the SDK does.
- **G4 file_search**: the judge builds its own workspace tree (seeded),
  calls `file_search` with a query matching some files by path and some by
  content, and requires the returned relative-path list to equal the
  judge's own `os.walk` + substring scan exactly (sorted).
- **G5 unit_convert**: five fixed conversions (km↔mi, kg↔lb, °C↔°F, m↔ft,
  g↔oz) must each match the judge's own decimal computation within
  **1e-9 relative**; an unknown unit must produce a tool error (never a
  wrong number, never a traceback).
- **G6 calculate**: ten fixed expressions must each match Python's own
  `eval` of the same restricted grammar within **1e-9 relative**
  (the judge's oracle is `ast`-parsed and independently evaluated, not a
  copy of the artifact's parser); division by zero and malformed
  expressions must produce a tool error.
- **G7 path traversal refused**: `file_search` with `root` set outside the
  workspace it was given (an absolute path, and `../` escapes) and
  `sqlite_query` with a `db_path` pointing outside a caller-provided base
  directory must be **refused** with a tool error (`isError == true` or an
  MCP error response) — and must **not** succeed with data from outside.
- **G8 robustness**: after all of the above, a call with a missing required
  argument or a wrong-typed argument produces a tool/protocol error rather
  than a crash, and the server process is still alive and still answering
  `ping` at the end (a server that exits on bad input fails).

Violating any gate fails with the offending numbers printed.

## Acceptance oracle (independent of "it ran")

1. **The judge computes expected answers itself, from data it creates.** For
   G3/G4 the judge writes its own SQLite database and workspace directory in
   a temp dir (contents derived from `--seed`), then compares the tool's
   output against `sqlite3` / `os.walk` run by the judge process — never
   against anything the artifact produced or asserted.
2. **G5/G6 compare against independent math**, not against the artifact:
   unit factors are defined once in the SPEC/judge as exact decimals; the
   calculator oracle parses the expression with `ast` and evaluates it with
   explicit operator dispatch.
3. **The protocol oracle is the SDK itself.** A server that returns
   malformed JSON-RPC, hangs, exits early, or dies on bad input cannot
   produce the required `InitializeResult`/`ListToolsResult`/
   `CallToolResult` envelopes; the judge treats a dead child process or a
   timed-out call as a failed gate, not as "no answer".
4. **Refusal is graded as behavior.** G7 fails a server that answers a
   traversal probe with any content, or that crashes on it; only a clean
   error passes.

## Self-test (`judge/selftest.sh`)

- The known-good example passes all gates.
- ≥ 5 known-bad single-edit mutants of the good artifact each fail ≥ 1
  gate; mutants are generated by `judge/mutants.py` (one edit each) and
  include, at minimum: a tool removed from the list, a wrong schema, a
  wrong query result, path traversal allowed, and a server that exits on
  bad input.
- Kill rate ≥ 90 % printed by the self-test; exit non-zero otherwise.
- Determinism: two `grade.sh` runs with the same seed produce byte-identical
  verdict JSON (excluding wall-time fields under the `timing` key).

## Judge-integrity rule

The artifact under test runs as a subprocess the judge launches; the judge
compares `sha256` of its own `judge/` tree before and after every grade and
fails closed if anything changed. The artifact is also copied to a temp dir
before grading.

## Out of scope for the judge

- Whether the server is *good engineering* beyond the gates (style,
  logging, extra tools with correct behavior is a G2 failure by design:
  exactly four tools).
- Any claim the artifact makes in comments or its server-info string.

## Tools (pinned by `judge/setup.sh`)

- `mcp` **1.30.0** from PyPI (official MCP Python SDK, MIT licence),
  installed into a pinned venv under `$HOME` with every transitive
  dependency hash-pinned in `judge/requirements.txt`
  (`pip install --require-hashes`).
- Python 3.10+ (stdlib only) for the judge itself. No `sudo` needed.
