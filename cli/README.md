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
| `sbx runners image` | Bake a GitHub Actions runner snapshot (runner + Docker) and print its id. |
| `sbx runners serve ...` | Serve GitHub Actions jobs from a warm pool of disposable sandboxes (see below). |

Environment: `E2B_API_KEY` (or `SBX_API_KEY`) is required. `E2B_DOMAIN`
defaults to `sbx.agent-next.com`.

The CLI uses the SDK's kill-on-timeout mode (`autoPause=false`). Activity
restarts the idle clock; this is not a fixed wall-clock deadline. When the
idle timeout expires, the sandbox and its files are deleted. MCP-created CPU
sandboxes instead pause at expiry and resume on the next exec or files call.

Always kill what you create: a forgotten running sandbox holds one of your
concurrent slots and consumes credit until it is killed or its idle timeout
expires.

## GitHub Actions runners

`sbx runners` runs GitHub Actions jobs in disposable sandboxes: every job gets
a fresh sandbox with Docker, and the sandbox is killed when the job ends.

```bash
export GH_TOKEN=<token>            # admin rights on the org (admin:org) or repo
snap=$(sbx runners image | tail -1)          # actions/runner + running dockerd, ~40 s
sbx runners serve --org my-org --snapshot "$snap" --labels sbx --warm 2 --max 10
```

Then target the pool from a workflow:

```yaml
jobs:
  test:
    runs-on: [self-hosted, sbx]
    steps:
      - uses: actions/checkout@v4
      - run: docker run --rm hello-world
```

`serve` keeps `--warm` single-use (JIT) runners registered and idle, so a
queued job starts at once; each runner takes one job, exits, and its sandbox
is killed while the pool refills. `--watch OWNER/REPO` counts that repo's
queued jobs to grow past `--warm` (up to `--max`) when every runner is busy.
Idle runners are recycled after `--idle-min`; a runner GitHub reports busy is
never removed. Ctrl-C (or SIGTERM) deregisters the idle runners and lets busy
ones finish; a second Ctrl-C kills the busy ones too. Every event is one JSON
line on stdout.

With `--webhook-port PORT` (and `GH_WEBHOOK_SECRET`), `serve` also takes
GitHub `workflow_job` webhooks: point an org or repo webhook (content type
JSON, event "Workflow jobs", same secret) at that port through a TLS proxy or
tunnel. Queued jobs then grow the pool the moment they are queued, instead of
after the warm runners are used up.

Give the pool its own API key: the key's concurrent-sandbox quota caps the
pool, so CI bursts never take sandboxes from your other workloads. Keep
`--max` at or below that quota; when the gateway answers 429 the pool pauses
spawning until a sandbox is freed.

Runners run as the sandbox user with passwordless `sudo`, like GitHub-hosted
runners. Use `--group-id` to register into an organization runner group, and
`--prefix` to keep two pools apart: a pool manages only runners whose name
starts with its prefix, and on start it clears the idle runners and sandboxes
an earlier `serve` with the same prefix left behind (a runner still on a job
finishes first). Two running pools must not share a prefix.

## Develop

```bash
pip install -e ".[test]"
pytest
```
