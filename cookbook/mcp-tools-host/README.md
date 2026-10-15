# mcp-tools-host — a stdio MCP tool server, graded by a judge it cannot fool

An agent works on a real infrastructure problem inside a disposable
agent-next sandbox: build a **stdio Model Context Protocol (MCP)
server** — the kind an AI assistant launches locally and calls as tools
— hosting exactly four tools (`sqlite_query`, `file_search`,
`unit_convert`, `calculate`). A disposable sandbox helps because the
server is untrusted plumbing: it speaks JSON-RPC over stdio against the
pinned official MCP SDK, must never write to stdout, must keep serving
after bad input, and must refuse every path that escapes the workspace
the host gave it. The judge is the SDK's own client plus an independent
stdlib oracle (its own SQLite query, its own `os.walk` scan, exact
decimal unit factors, an `ast`-dispatch calculator), so a server that
merely "runs" cannot pass: wrong rows, an inverted factor, an unsorted
match list, an allowed traversal or a crash on bad input each fail a
named gate.

## Ask your agent

> Read `cookbook/mcp-tools-host/SPEC.md` in this repo, then build
> `cookbook/mcp-tools-host/examples/good/server.py`: a stdio MCP server
> on the pinned `mcp` SDK (installed by `judge/setup.sh`) that
> registers exactly the four tools with the schemas pinned in
> `judge/mcp_judge.py`, keeps every caller-given path inside the
> workspace it was launched in (refuse absolute paths and `..`
> escapes with a tool error), never writes to stdout and never exits on
> bad input. Prove it with `bash judge/selftest.sh` (your server must
> pass; every mutant must fail) and `bash judge/grade.sh
> examples/good/server.py`.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/mcp-tools-host/run.py --ref main
```

Creates a sandbox, clones this repo at `--ref` inside it, installs the
hash-pinned toolchain (`judge/setup.sh`, mcp 1.30.0 + deps), proves the
judge can fail (`judge/selftest.sh`: the known-good server passes, 9/9
single-edit mutants are killed, verdicts are deterministic), then
grades the known-good server (`judge/grade.sh`), prints the verdict
JSON and kills the sandbox. Exits non-zero the moment any step fails.
`--keep` leaves the sandbox up for exploration, `--seed` re-seeds the
judge's fixtures.

## Measured wall time (fresh sandbox, 2026-10-15)

| step | wall time |
|---|---|
| `sbx create --timeout-min 30` | ~2 s |
| `git clone --depth 1` (this repo, in sandbox) | ~6 s |
| `judge/setup.sh` (venv + hash-pinned mcp 1.30.0) | ~30 s |
| `judge/selftest.sh` (good + 9 mutants + determinism) | ~85 s |
| `judge/grade.sh examples/good/server.py` | ~10 s (judge total 3.5 s) |
| `sbx kill` + confirm via `sbx list` | ~4 s |

## Limits, stated plainly

- stdio transport only; no HTTP/SSE, auth, persistence or concurrency.
- SQL is one read-only `SELECT` (one statement, optional trailing `;`);
  nothing else is graded.
- `file_search` is exact case-insensitive substring over the relative
  path or the UTF-8-decoded content — no ranking, no regex.
- `calculate` is `+ - * / **`, parentheses, numbers, unary minus
  (the server also accepts `//` and `%`; the judge grades the SPEC
  grammar only).
- Paths are confined to the working directory the host launches the
  server with; anything else must be refused (gate G7).
- The pinned wheels target CPython 3.12, linux x86_64 (the pinned
  sandbox image); `judge/setup.sh` fails fast elsewhere.

See `SPEC.md` for gates G1–G8, `RECEIPT.md` for two fresh-sandbox runs,
`media/` for figures and the video.
