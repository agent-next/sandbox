# Coding in agent-next/sandbox

Read the [org agent standard](https://github.com/agent-next/.github/blob/main/AGENT-STANDARD.md)
and these repo-specific instructions. `CLAUDE.md` imports this file.

## Map and setup

- `cli/src/sbx/cli.py`: `sbx` CLI; `cli/tests`: CLI regression tests.
- `cli/pyproject.toml`: Python >=3.10, dependencies, test extra and package entrypoint.
- `plugins/sandbox`: Claude/Codex manifests, MCP configs and `skills/sandbox/SKILL.md`.
- `.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`: marketplaces.
- `cookbook`: examples; `.github/workflows/ci.yml`: current executable CI checks.

From the repo root, in an isolated checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install './cli[test]'
.venv/bin/python -m pytest -q cli/tests
```

Keep the virtualenv untracked. CI tests Python 3.10 and 3.13; name the version you
actually ran. Root and `cli/` invocations both work after installing the package.

## Manifest checks

The `manifests` CI job is authoritative. Run its checks for plugin/manifest edits;
the following root command mirrors its JSON, path and required-field checks:

```bash
python3 - <<'PY'
import json, pathlib, subprocess
files = subprocess.check_output(['git', 'ls-files', '-z', '*.json']).split(b'\0')
for name in filter(None, files):
    json.loads(pathlib.Path(name.decode()).read_text())
def require(path, keys):
    data = json.loads(pathlib.Path(path).read_text())
    missing = [key for key in keys if not data.get(key)]
    if missing:
        raise SystemExit(f'{path}: missing {missing}')
    return data
market = require('.claude-plugin/marketplace.json', ['name'])
for plugin in market['plugins']:
    if any(not plugin.get(key) for key in ('name', 'source', 'description')):
        raise SystemExit('marketplace plugin entry missing required field')
if not pathlib.Path(market['plugins'][0]['source'], '.claude-plugin').is_dir():
    raise SystemExit('marketplace plugin source directory missing')
require('plugins/sandbox/.claude-plugin/plugin.json', ['name', 'description', 'version'])
require('plugins/sandbox/.codex-plugin/plugin.json', ['name', 'version'])
require('.agents/plugins/marketplace.json', ['name'])
print('Manifest checks passed')
PY
```

## Development loop

1. Fetch and pin the base SHA; inspect local changes, open PRs and worktrees for
   overlap. Use an owned branch/worktree and preserve other lanes' state.
2. State the expected user result and reproduce the actual reported input on its
   CLI/plugin path. Make the smallest fix and check related callers/subcommands.
3. For bug fixes, add a regression that fails on the original behavior and passes
   after the fix. A collection/import error or skipped test is not that proof.
   Documentation edits need accurate commands and links, not ceremonial tests.
4. Run relevant checks and independent review by a different model family on
   the exact head. Recheck changed
   content after review fixes. Simplify unnecessary code and duplicated rules.
5. Record SHA, commands, real results, reviewer verdict and untested surfaces in
   the PR receipt. A new head invalidates earlier review. A red baseline needs its
   fetched SHA, output and tracked follow-up; do not silently waive it.
6. Turn a confirmed recurring failure into a targeted regression or review rule.
   Report implementation, tests, review, merge and live acceptance separately.

`cli/tests` substitutes SDK and HTTP behavior; passing it proves simulated CLI
behavior. It does not prove the plugin connects or a deployed sandbox works.
For changes to those surfaces, separately verify the installed plugin or CLI
against the intended service when authorized, recording create -> exec -> kill
and cleanup of the exact IDs created. Docs-only changes need no live allocation.
If access is unavailable, record the remaining acceptance check and its owner.

## Boundaries and closeout

This repo is public: no credentials, private host paths or internal operations
material in code, logs or receipts. Never read or rewrite real agent config for
unit tests. Use isolated fixtures. Do not alter dependencies or CI without owner
approval; publishing, releases, deployment and merges retain their existing
approval gates. Prepare reviewable changes and async decision cards for those
steps; ordinary implementation and verification run headlessly.

Clean only your own scratch. Preserve unpushed work and useful evidence before
ending an attempt. Never select sandboxes to delete from a shared listing: kill
only IDs this run created, and report any cleanup failure with its exact ID.
