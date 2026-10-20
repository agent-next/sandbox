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

There is no `sbx login`: the key comes only from the environment. Agents
and CI have no browser for the console — load an existing key from your
secret store and export it.

```bash
export E2B_API_KEY=<your key>     # SBX_API_KEY also works

id=$(sbx create)                  # a fresh sandbox; prints its id
sbx exec "$id" 'echo hello'       # prints: hello
sbx kill "$id"                    # always kill what you create
```

`sbx exec` passes stdout and stderr through and exits with the command's own
exit code. `sbx create --timeout-min N` sets an idle keep-alive (default
5 minutes); activity restarts the clock. The CLI opts into deletion at idle
expiry, so copy durable results out. CPU sandboxes created by the MCP plugin
instead pause at idle expiry and resume on the next exec or files call.

The same three steps from your agent: the plugin's tools are
`sandbox_create`, `sandbox_exec` and `sandbox_kill`, and the `sandbox` skill
tells the agent when to use them and to kill what it creates.

GPU from the shell: `sbx gpu create --vram 4`, then `sbx gpu exec ID -c '...'`,
`pause`, `resume` and `kill` (see [cli/README.md](cli/README.md#gpu-leases)).
For CUDA work, also try the [1 GiB small-GPU quickstart](cookbook/small-gpu/README.md).
It includes a Python client that checks a tiny GPU computation and destroys
the lease. GPU-enabled keys and available capacity are required. This MIT
repository contains the client kit; the hosted service's backend is separate.

## Development

Start with [AGENTS.md](AGENTS.md) for the check commands and acceptance rules.
CLI setup and usage are in [cli/README.md](cli/README.md). The release process
is in [RELEASING.md](RELEASING.md).

[nightly-smoke.yml](.github/workflows/nightly-smoke.yml) runs `scripts/release_smoke.py`
against the latest tag each night and uploads its JSON receipt. Set the `SBX_SMOKE_KEY`
secret for live checks. Missing credentials fail the nightly gate and leave a JSON
receipt; scheduled failures file a "nightly smoke failed" issue auto-closed after
a successful live run.

## License

MIT — see [LICENSE](LICENSE).

## Security

See [SECURITY.md](SECURITY.md).
