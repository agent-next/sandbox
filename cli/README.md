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
| `sbx gpu create [--vram GiB] [--template NAME] [--class C]` | Start a GPU lease and print its id (`gl-...`). Needs a key with a GPU grant. |
| `sbx gpu exec ID (--code FILE \| -c SRC) [--timeout S]` | Run Python source on the lease; prints the job's stdout, exits 1 if the job fails. `--json` prints the full reply with `report` and meters. `--timeout` (default 120, max 3600) is a hard wall: an overrun kills the lease. |
| `sbx gpu pause ID` / `sbx gpu resume ID` | Release the GPU between jobs (state is kept) and take a seat again. A paused lease still counts toward your lease cap. |
| `sbx gpu kill ID` | Destroy the lease and confirm it is gone. |
| `sbx gpu templates` / `sbx gpu info ID` | List GPU templates; show a lease's phase, slice and billing meters. |
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

## GPU leases

```bash
id=$(sbx gpu create --vram 4)
sbx gpu exec "$id" -c 'import torch; print(torch.cuda.get_device_name(0))'
sbx gpu pause "$id"; sbx gpu resume "$id"     # optional: free the GPU between jobs
sbx gpu info "$id"                            # billed_s and the other meters
sbx gpu kill "$id"
```

Every `gpu` verb takes `--json`. Failures print one line with a hint and exit
non-zero: 402 no GPU credit, 403 no GPU access on this key, 409 conflict (job
failed, job already running, lease cap), 429/503 busy or at capacity (the line
carries the `Retry-After` seconds). A job that raises exits 1 with the error
tail; the lease survives. Jobs run with no network access. Always `kill` what
you create.

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
is killed while the pool refills. `--watch OWNER/REPO` counts that repo's
queued jobs to grow past `--warm` (up to `--max`) when every runner is busy.
Idle runners are recycled after `--idle-min`; a runner GitHub reports busy is
never removed. Ctrl-C (or SIGTERM) deregisters the idle runners and lets busy
ones finish; a second Ctrl-C kills the busy ones too. Every event is one JSON
line on stdout.

Add `--keep-failed` to retain snapshots of failed jobs (default cap five,
or `--keep-failed=N`). Resume one with `sbx runners debug JOB --exec CMD`.
See [Debug a failed job](../cookbook/github-ci-runners/README.md#debug-a-failed-job)
for retention, cleanup and local state details.

With `--webhook-port PORT` (and `GH_WEBHOOK_SECRET`), `serve` also takes
GitHub `workflow_job` webhooks: point an org or repo webhook (content type
JSON, event "Workflow jobs", same secret) at that port through a TLS proxy or
tunnel. Queued jobs then grow the pool the moment they are queued, instead of
after the warm runners are used up.

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
