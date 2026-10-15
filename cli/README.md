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

Agents and CI have no browser for the console: load an existing key from
your secret store and export it. There is no interactive login; the key is
read from the environment.

## Commands

| command | what it does |
| --- | --- |
| `sbx create [--template T] [--timeout-min N]` | Start a sandbox and print its id. `--timeout-min` is the idle keep-alive in minutes (default 5); expiry deletes this CLI-created sandbox. |
| `sbx exec ID [--timeout S] -- COMMAND...` | Run a command. One argument is a shell line; several are quoted and joined. Put `--` before the command so its own options (`ls -l`) are not read as `sbx` options. Exits with the command's exit code. |
| `sbx list` | List the live sandboxes held by your key (id, template, start time). |
| `sbx kill ID` | Kill a sandbox. A sandbox that is already gone is not an error. |
| `sbx runners image` | Bake a GitHub Actions runner snapshot (runner + Docker) and print its id. |
| `sbx runners serve ...` | Serve GitHub Actions jobs from a warm pool of disposable sandboxes (see below). |
| `sbx runners debug JOB [--exec CMD]` | Restore a failed job's snapshot and print access commands. `--list` lists retained jobs; `--delete JOB` deletes a snapshot. |

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
snap=$(sbx runners image | tail -1)          # Ubuntu 24.04 + Docker + actions/runner, ~2 min
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

`image` imports `ubuntu:24.04` once as your key's own template (GitHub's
hosted runners are Ubuntu; `actions/setup-python` ships Ubuntu-only builds),
then adds build tools, Docker with Compose and buildx, Python 3.12/3.13 and
Node 20/22 in the tool cache (where `actions/setup-python` and
`actions/setup-node` find them, as on GitHub's image), and the runner, and
snapshots it. `--size standard` bakes 4 vCPU / 16 GB runners
instead of 2 vCPU / 8 GB; `--from-image` or `--template` choose another base.

`serve` keeps `--warm` single-use (JIT) runners registered and idle, so a
queued job starts at once; each runner takes one job, exits, and its sandbox
is killed while the pool refills. `--watch OWNER/REPO` (repeatable) selects
the repo set for job lookups and polls queued jobs to grow past `--warm`, up to `--max`,
even while warm runners are idle or starting. The target ready count is the
larger of `--warm` and queued demand, not their sum.
Without an explicit watch list, an org pool checks its 20 most recently pushed
repos for runs from the last hour, refreshing discovery every five minutes;
a repo pool watches its own repo. Only jobs whose requested labels are all
included in the pool's registered labels count (case-insensitively).
`--poll-interval` sets the minimum demand poll interval (default 5 seconds);
it grows with request cost (roughly 1,800 reads/hour) and backs off on errors
or rate limits. Conditional reads use ETags when GitHub supplies them.
Cancelled jobs assigned to this process's runners are reclaimed as soon as a
poll sees completion, without waiting for the runner to exit. Polls also scan
cancelled runs, so a job that starts and is cancelled between polls is not
missed. Recent cancellations are selected by update time, including reruns of
older workflows; failed polls retain their cancellation window. `demand` events
report queued count and spawn decisions; `reclaimed` reports `delay_s` since
job completion and `poll_delay_s` since observing the cancellation.
Idle runners are recycled after `--idle-min`; other than confirmed cancellations,
a runner GitHub reports busy is never removed. Ctrl-C (or SIGTERM) deregisters
the idle runners and lets busy ones finish; a second Ctrl-C kills the busy ones
too. Every event is one JSON line on stdout.

Add `--keep-failed` to retain snapshots of failed jobs (default cap five,
or `--keep-failed=N`). Resume one with `sbx runners debug JOB --exec CMD`.
See [Debug a failed job](../cookbook/github-ci-runners/README.md#debug-a-failed-job)
for retention, cleanup and local state details.

With `--webhook-port PORT` (and `GH_WEBHOOK_SECRET`), `serve` also takes
GitHub `workflow_job` webhooks: point an org or repo webhook (content type
JSON, event "Workflow jobs", same secret) at that port through a TLS proxy or
tunnel. Queued jobs then grow the pool the moment they are queued, instead of
at the next REST demand poll. REST polling still handles cancel reclaim when
webhooks are enabled.

Give the pool its own API key: the key's concurrent-sandbox quota caps the
pool, so CI bursts never take sandboxes from your other workloads. `serve`
lowers `--max` to that quota at start (a free key runs 2 at once); when the
gateway still answers 429 the pool pauses spawning until a sandbox is freed.
Warm runners are running sandboxes and use credit while they wait.

Jobs run as an unprivileged `user` with passwordless `sudo`, like
GitHub-hosted runners, and see their sandbox id in `E2B_SANDBOX_ID`. Use
`--group-id` to register into an organization runner group, and `--prefix` to
keep two pools apart: a pool manages only runners whose name starts with its
prefix, and on start it clears the idle runners and sandboxes an earlier
`serve` with the same prefix left behind (a runner still on a job finishes
first). Two running pools must not share a prefix.

## Develop

```bash
pip install -e ".[test]"
pytest
```
