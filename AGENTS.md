# AGENTS.md

Agent instructions for `agent-next/sandbox`. Read this before editing; `CLAUDE.md` imports it.

## Repo map

| path | what it is |
| --- | --- |
| `plugins/sandbox` | Claude Code + Codex plugin: `sandbox` skill, MCP configs, manifests |
| `plugins/sandbox/skills/sandbox/SKILL.md` | agent-facing rules for live sandboxes (kill what you create, hard TTL, per-key concurrency) |
| `cli` | `sbx` CLI: source `cli/src/sbx`, tests `cli/tests`, package `agent-next-sandbox` |
| `cookbook` | prompt examples for the plugin; review-gated, not run by CI |
| `.github/workflows/ci.yml` | the whole CI: job `cli` (pytest on 3.10 and 3.13) and job `manifests` (JSON + marketplace checks) |
| `.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json` | the two marketplace manifests |

Facts worth keeping: `sbx` reads `E2B_API_KEY` (or `SBX_API_KEY`), defaults
`E2B_DOMAIN` to `sbx.agent-next.com`, and `sbx list` uses `httpx` against
`https://api.$E2B_DOMAIN/sandboxes`. The plugin's MCP server is
`https://api.sbx.agent-next.com/mcp/v1`, credentialed with `SBX_API_KEY`.
Python >= 3.10; deps and the `test` extra live in `cli/pyproject.toml`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install './cli[test]'
```

Run pytest from the repo root, not from `cli/`: `cli/tests` has no `conftest.py`
and does `from sbx import cli`, so the package must be installed.

## Checks (these are what CI runs)

| check | command |
| --- | --- |
| CLI tests (CI matrix: Python 3.10 and 3.13) | `.venv/bin/python -m pytest -q cli/tests` |

Same as CI's `pytest -q` with `working-directory: cli`. JSON manifests come from the
`manifests` job of `.github/workflows/ci.yml`: that job is the executable copy of these
rules, so make manifest edits match it rather than forking it into a script.

```bash
# every tracked *.json must parse
for f in $(git ls-files '*.json'); do python -m json.tool "$f" >/dev/null || echo "INVALID $f"; done

# the marketplace plugin source directory must exist
src=$(python -c "import json;print(json.load(open('.claude-plugin/marketplace.json'))['plugins'][0]['source'])")
test -d "$src/.claude-plugin" && echo "plugin dir present: $src"    # ./plugins/sandbox
```

Required fields the same job enforces:

- `.claude-plugin/marketplace.json`: `name`; every `plugins[]` entry: `name`, `source`, `description`.
- `plugins/sandbox/.claude-plugin/plugin.json`: `name`, `description`, `version`.
- `plugins/sandbox/.codex-plugin/plugin.json`: `name`, `version`.
- `.agents/plugins/marketplace.json`: `name`.

## Tests: hermetic vs live

`cli/tests` is hermetic: an autouse fixture injects a fake `e2b` module into
`sys.modules` plus a dummy key, so no network, gateway or sandbox is involved.
Never add a test that reaches the service.

Live acceptance (create, exec, kill against `sbx.agent-next.com`) is opt-in and
never part of CI or of the normal loop: it needs a real `SBX_API_KEY` and spends
sandbox minutes and per-key concurrency. Run it deliberately, kill what you
created, and report what you saw. A green hermetic run is not proof that a live
sandbox works.

## The loop

issue -> reproduce -> minimal fix -> regression test -> independent review -> receipt

1. **Issue.** Name the failing input and the execution path in this repo it goes
   through (a `sbx` subcommand, a test, a manifest field).
2. **Reproduce.** Run the reporter's input and capture the failing output.
3. **Prove regression.** Show the reproduction fails on the original behaviour,
   then fix only that, minimally.
4. **Sibling paths.** The same bug often sits in a neighbour: other `sbx`
   subcommands and the helpers they share in `cli/src/sbx/cli.py`. Fix it there
   too or say why it does not apply.
5. **Regression test.** Cover the path in `cli/tests`, hermetic, like the existing
   fixtures. Docs-only changes need no new test — say so instead of adding a
   ceremonial one.
6. **Independent review.** Have a different agent or session read the diff and the
   test output; the author does not review its own change.
7. **Receipt.** Report the exact commands, test counts, the full commit SHA,
   limitations and any follow-up.

Skips and pre-existing reds need the exact commit SHA and output plus a tracked
follow-up — never a silent skip.

A green `.venv/bin/python -m pytest -q cli/tests` proves only that the paths
covered by `cli/tests` pass on this machine. It is not merge approval, not a
deploy and not live-service proof.

## Limits (owner-level, not negotiable in a PR)

No secrets in code, tests, logs or commit messages (the CLI scrubs key values from
its output; keep tests asserting that). No unrelated edits. No dependency,
workflow or CI changes. No releases, publishing, deploys or merges — the platform
runner pushes your branch and a human decides the rest. Keep these facts generic
enough for a public repo: no internal host paths, no operational details.

## Cleanup rule for live runs

Kill only sandbox ids this run created. Never `sbx list` and pick an id from the
listing — other agents, lanes and the user hold those. If a kill fails, report the
id and the error rather than retrying in a loop or guessing an id.
