# agent-next sandbox

Disposable cloud Linux sandboxes for your coding agent. Run long jobs,
untrusted code and heavy dependencies in the cloud instead of on your
machine, and share a public preview URL for anything that serves a port.

This repo holds three things that share one name, `sandbox`:

| piece | what it is | where |
| --- | --- | --- |
| Claude Code and Codex plugin | the sandbox MCP server plus the `sandbox` skill | [`plugins/sandbox`](plugins/sandbox) |
| `sbx` command-line tool | create, exec, list, kill from the shell | [`cli`](cli) |
| Cookbook | prompts to try with the plugin | [`cookbook`](cookbook) |

## Install the plugin

```bash
claude plugin marketplace add agent-next/sandbox
```

Then enable it and give it your API key:

```bash
claude plugin install sandbox@agent-next
export SBX_API_KEY=<your key>     # create one at https://sbx.agent-next.com/console
```

Start Claude Code from a shell where `SBX_API_KEY` is exported. Check with
`claude mcp list`: you should see the `sandbox` server.

Codex:

```bash
codex plugin marketplace add agent-next/sandbox
codex plugin add sandbox@agent-next
export SBX_API_KEY=<your key>     # Codex sends it as a bearer token
```

## Install the CLI

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
```

## Quickstart: create, exec, kill

```bash
export E2B_API_KEY=<your key>     # SBX_API_KEY also works

id=$(sbx create)                  # a fresh sandbox; prints its id
sbx exec "$id" 'echo hello'       # prints: hello
sbx kill "$id"                    # always kill what you create
```

`sbx exec` passes stdout and stderr through and exits with the command's own
exit code. A sandbox has a hard lifetime (default 5 minutes, set with
`sbx create --timeout-min N`); copy results out before it ends.

The same three steps from your agent: the plugin's tools are
`sandbox_create`, `sandbox_exec` and `sandbox_kill`, and the `sandbox` skill
tells the agent when to use them and to kill what it creates.

## Development

Agent and contributor instructions, the repo map and the checks CI actually runs
live in [AGENTS.md](AGENTS.md).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install './cli[test]'
.venv/bin/python -m pytest -q cli/tests
```

## License

MIT — see [LICENSE](LICENSE).

## Security

See [SECURITY.md](SECURITY.md).
