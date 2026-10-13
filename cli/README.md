# sbx

`sbx` creates, uses and kills [agent-next](https://agent-next.com) cloud
sandboxes from the shell. It is a thin command-line wrapper over the
E2B-compatible sandbox API at `sbx.agent-next.com`.

## Install

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
```

Needs Python 3.10 or newer. The PyPI name `agent-next-sandbox` is reserved
for a later release; today, install from GitHub as above. If pip warns that
`sbx` was installed outside `PATH`, add `~/.local/bin` to your `PATH`.

## Use

Get an API key at <https://sbx.agent-next.com/console>, then:

```bash
export E2B_API_KEY=<your key>     # SBX_API_KEY also works

id=$(sbx create)                  # prints the sandbox id
sbx exec "$id" 'echo hello'       # stdout/stderr pass through; exit code is the command's
sbx exec "$id" --timeout 30 -- ls -l /tmp   # several words: put -- first
sbx kill "$id"
```

## Commands

| command | what it does |
| --- | --- |
| `sbx create [--template T] [--timeout-min N]` | Start a sandbox and print its id. `--timeout-min` is the idle keep-alive in minutes (default 5); expiry deletes this CLI-created sandbox. |
| `sbx exec ID [--timeout S] -- COMMAND...` | Run a command. One argument is a shell line; several are quoted and joined. Put `--` before the command so its own options (`ls -l`) are not read as `sbx` options. Exits with the command's exit code. |
| `sbx list` | List the live sandboxes held by your key (id, template, start time). |
| `sbx kill ID` | Kill a sandbox. A sandbox that is already gone is not an error. |

Environment: `E2B_API_KEY` (or `SBX_API_KEY`) is required. `E2B_DOMAIN`
defaults to `sbx.agent-next.com`.

The CLI uses the SDK's kill-on-timeout mode (`autoPause=false`). Activity
restarts the idle clock; this is not a fixed wall-clock deadline. When the
idle timeout expires, the sandbox and its files are deleted. MCP-created CPU
sandboxes instead pause at expiry and resume on the next exec or files call.

Always kill what you create: a forgotten running sandbox holds one of your
concurrent slots and consumes credit until it is killed or its idle timeout
expires.

## Develop

```bash
pip install -e ".[test]"
pytest
```
