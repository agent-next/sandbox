# github-ci-runners

Run GitHub Actions jobs in disposable sandboxes: one microVM per job, Docker
inside, a fresh single-use (JIT) runner each time, restored from a snapshot in
about a second.

## What you get (30 seconds)

Measured 2026-10-14: a 9-job workflow (`make check`, `setup-python` +
`setup-node`, `apt-get`, `docker build`, `docker compose`, a `container:` job,
a `services:` Redis job, two isolation checks) run 15 times on sandbox runners
and on GitHub-hosted `ubuntu-latest`, 2 vCPU each. 135/135 green on both.

| | sandbox runners | GitHub-hosted |
| --- | --- | --- |
| queue wait, `--warm 10` (median / worst) | 1 s / 2 s | 2 s / 3 s |
| `setup-python` + `setup-node` job (median) | 17 s | 18 s |
| `docker build` / `docker compose` job | 16 s / 16 s | 11 s / 15 s |
| CPU-bound `make check` | 94 s | 68 s |

Honest gap: jobs start sooner and toolchains are ready, but single-threaded
CPU work is about 1.4x slower on today's 2.5 GHz hosts (4 vCPU via `--size
standard` did not help a single-threaded suite). x86_64 Linux only; no
macOS, arm64, GPU or persistent cache volumes yet. A sandbox restores in
about a second with Docker running and Python 3.12/3.13 + Node 20/22 in the
tool cache. Each job's VM has its own kernel and nothing survives into the
next job, so a fork PR's build cannot touch your machine or the next job.

## Quick start (3 commands)

```bash
export E2B_API_KEY=<sandbox key>  GH_TOKEN=<token with admin rights on the org or repo>
snap=$(sbx runners image | tail -1)                 # ~2.5 min: Ubuntu 24.04 + Docker + runner
sbx runners serve --org <your-org> --snapshot "$snap" --warm 2 --max 4   # Ctrl-C drains
```

(For one repo use `--repo OWNER/REPO` instead of `--org`.) Then point a job at it:

Moving an existing repo over is one command. It rewrites only the `runs-on` lines of jobs on `ubuntu-latest`, `ubuntu-24.04` or `ubuntu-22.04` (matrix and other expressions are listed as skipped):

```bash
sbx runners migrate --repo OWNER/REPO            # dry run: unified diff + job table
sbx runners migrate --repo OWNER/REPO --apply    # branch sbx-runners-migrate + pull request
```

Options: `--label '[self-hosted, sbx]'`, `--only ci.yml`, `--jobs lint,test`, `--base BRANCH`. Revert by reverting the pull request.

```yaml
# .github/workflows/sandbox-ci.yml
on: push
jobs:
  test:
    runs-on: [self-hosted, sbx]
    steps:
      - uses: actions/checkout@v4
      - run: docker run --rm hello-world
```

Run on 2026-10-14 against a private org repo: `image` printed
`snap-9d8b9c8312342bb6a9b49127` after 2m33s, `serve` had 2 runners online in
about 10 s, and the push above queued for 2 s and finished green in 10 s on
runner `sbx-e8650e11`.

`--warm` is the number of idle runners kept ready: set it to the jobs one push
starts. `--max` is capped to your key's concurrent limit (a free key runs 2
sandboxes at once, so a 9-job push queues). Warm runners use credit while they
wait. Repeat `--watch-repo OWNER/REPO` to poll up to 20 repos for matching queued
jobs and cancelled jobs on this pool's runners. Without it, org pools discover
repos with runs in the last hour among the 20 most recently pushed repos
(refreshed every five minutes); repo pools watch their own repo.
`--poll-interval 5` sets the minimum polling interval, increased with API cost
and rate-limit backoff; ETags avoid downloading unchanged responses.
Demand boots the shortfall beyond idle/starting runners, capped by `--max`
and the key's limit. Cancelled jobs are killed when a poll sees their completed
cancellation, without waiting for runner shutdown. `demand` and `reclaimed`
JSON events report decisions and reclaim delay. `--webhook-port` also accepts
instant demand notifications (see the `sbx` README).

## Prompt for your coding agent

Headless, with `E2B_API_KEY` and `GH_TOKEN` exported and `sbx` installed. Works
in Claude Code, Codex and Cursor:

> Run this repository's GitHub Actions jobs in sandboxes. Run `sbx runners image` and keep the last line (a `snap-...` id). Start `sbx runners serve --org <your-org> --snapshot <id> --warm 2 --max 4` in the background, logging JSON lines to a file, and wait until the log shows an `online` event. Add `.github/workflows/sandbox-ci.yml` with one job, `runs-on: [self-hosted, sbx]`, steps `actions/checkout@v4` and `docker run --rm hello-world`, push it on a temp branch and wait for the run. Report how long the job waited (job `created_at` to `started_at`) and whether `docker run` worked. Then stop `serve` (SIGINT), delete the temp branch, and confirm no `sbx-*` runner remains in the org.

```bash
claude -p "<the prompt above>" --allowedTools "Bash(sbx:*)" "Bash(gh:*)" "Bash(git:*)" "Write(.github/workflows/*)" "Edit(.github/workflows/*)"
codex exec --sandbox danger-full-access "<the prompt above>"   # no sandbox: runs with your user's rights, as does the prompt's git push
cursor-agent -p --force "<the prompt above>"
```

(Agent invocations above: not run for this page; the underlying commands were.)

## For coding agents that run in CI

The cloud agents below can use these runners; only what their docs state is claimed.

- **GitHub Copilot cloud agent.** Its environment is a GitHub Actions job
  defined in `.github/workflows/copilot-setup-steps.yml`; set `runs-on` there
  to a self-hosted label, e.g. `runs-on: [self-hosted, sbx]`. Docs: Ubuntu x64
  and Windows only, single-use runners recommended, and the built-in firewall
  must be disabled on self-hosted runners. [Customize the
  environment](https://docs.github.com/copilot/how-tos/use-copilot-agents/coding-agent/customize-the-agent-environment),
  [configure the runner](https://docs.github.com/en/copilot/how-tos/administer-copilot/manage-for-organization/configure-runner-for-coding-agent).
  (Not run with sbx runners yet.)
- **Claude Code GitHub Action** (`anthropics/claude-code-action`). It runs as a
  normal workflow job, so `runs-on` is yours to set; its docs describe
  GitHub-hosted runners and do not say self-hosted is unsupported. Use
  `runs-on: [self-hosted, sbx]` on the job that calls it. [Docs](https://code.claude.com/docs/en/github-actions).
  (Not run with sbx runners yet.)
- **Cursor self-hosted workers.** Cursor's Self-Hosted Machines run a worker
  you register with the Cursor CLI in a team pool; this is not GitHub Actions
  based, and our runners do not replace it. E2B is on Cursor's partner list and
  `sbx` speaks the E2B API. [Docs](https://cursor.com/docs/cloud-agent/self-hosted).
  (Not run.)

## Agent recipe (machine-readable)

```yaml
recipe: github-ci-runners
requires: [sbx, gh, git]
env:
  E2B_API_KEY: sandbox key (required)
  GH_TOKEN: GitHub token with admin rights on the org or repo (required)
steps:
  - run: snap=$(sbx runners image | tail -1)
    success: $snap starts with "snap-"
  - run: sbx runners serve --org <org> --snapshot "$snap" --warm 2 --max 4 > serve.log &
    success: 'serve.log has an {"event": "online"} line within 60 s'
  - run: push a workflow with runs-on [self-hosted, sbx] to a temp branch
    success: gh run list shows conclusion "success"; job started_at - created_at is the wait
  - run: kill -INT <serve pid>; delete the temp branch
    success: gh api orgs/<org>/actions/runners lists no name starting "sbx-"; sbx list is empty
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `serve` logs repeated 429s, the pool never fills | free key: 2 concurrent sandboxes | `serve` caps `--max`/`--warm` to the key's limit; lower them or use a key with more concurrency |
| `actions/setup-python`: "version 3.12 not found for Debian 12" | runner built on a Debian template | re-bake with the default image (`ubuntu:24.04`); avoid `--template` on Debian templates |
| `ImportError: libGL.so.1` in a job | custom image lacks a native lib that GitHub's image has | use the default image, or add `libgl1` to your `--from-image` |
| `503 gateway is restarting` during a job | gateway deploy drops live streams | `serve` reattaches to the running job (up to 10 min); nothing to do. A `kill_failed` event means a sandbox is left: `sbx list`, then `sbx kill <id>` |
| `503 host disk nearly full: refusing new sandbox starts` on create or `image` | platform admission guard | wait a minute and retry; plain creates recover first |
| job never starts | label mismatch or runner group | the job needs `runs-on: [self-hosted, sbx]` (or your `--labels`); check `--group-id` lets the repo use the runners |

## Coming next

Runner debugging and stats are in review.
