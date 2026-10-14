# github-ci-runners

Prompt:

> Run this repository's GitHub Actions jobs in sandboxes: bake a runner image, keep four warm runners for the org, point one workflow job at them with `runs-on: [self-hosted, sbx]`, and show me how long the job waited and whether `docker run` worked.

Run:

```bash
claude -p "Run this repository's GitHub Actions jobs in sandboxes: bake a runner image with 'sbx runners image', keep four warm runners with 'sbx runners serve --org <your-org> --snapshot <the image id> --warm 4 --max 10', point one workflow job at them with runs-on: [self-hosted, sbx], and show me how long the job waited and whether 'docker run' worked. Stop serve with Ctrl-C when done." --allowedTools "Bash(sbx:*)" "Bash(gh:*)"
```

Or by hand:

```bash
export E2B_API_KEY=<sandbox key>  GH_TOKEN=<token with admin:org>
snap=$(sbx runners image | tail -1)
sbx runners serve --org <your-org> --snapshot "$snap" --warm 4 --max 10
```

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

Why a sandbox per job: each job gets a fresh VM with its own kernel and a
Docker daemon, nothing survives into the next job, and the runner is
single-use (JIT), so a fork PR's build cannot touch the next job or your
machine.

What we measured (2026-10-14, a 9-job workflow run 15 times on sandbox runners
and on GitHub-hosted `ubuntu-latest`, 2 vCPU each, two runs at 4 vCPU): every
sandbox job passed (135/135, as on GitHub-hosted): `make check` of a Python
repo, `setup-python` + `setup-node`, `sudo apt-get`, `docker build`, `docker
compose`, a `container:` job, a `services:` (Redis) job, and a check that the
next job sees nothing the previous one left (files, Docker images).

| | sandbox runners | GitHub-hosted |
| --- | --- | --- |
| queue wait, `--warm 10` (median / worst, 3 runs of 9 jobs) | 1 s / 2 s | 2 s / 3 s |
| `setup-python` + `setup-node` job (median of 4) | 17 s | 18 s |
| `docker build` / `docker compose` job | 16 s / 16 s | 11 s / 15 s |
| CPU-bound `make check` | 94 s | 68 s |
| cancelled job's sandbox reclaimed | 45 s after cancel | - |

Jobs start sooner and toolchains are ready; CPU-bound steps run slower on
today's hosts (2.5 GHz cores; 4 vCPU runners via `--size standard` did not
change a single-threaded suite).

A sandbox restores from the runner snapshot in about a second, with Docker
running and Python 3.12/3.13 and Node 20/22 in the tool cache. Set `--warm` to
the jobs one push starts: with `--warm 2`, a 9-job push waited 11 s (median)
while the pool grew. `serve` keeps `--max` within your key's concurrent limit
(a free key runs 2 at once, so a 9-job push queues), and warm runners use
credit while they wait. Add `--webhook-port` (see the `sbx` README) so queued
jobs grow the pool the moment they are queued.
