# github-ci-runners

Prompt:

> Run this repository's GitHub Actions jobs in sandboxes: bake a runner image, keep two warm runners for the org, point one workflow job at them with `runs-on: [self-hosted, sbx]`, and show me how long the job waited and whether `docker run` worked.

Run:

```bash
claude -p "Run this repository's GitHub Actions jobs in sandboxes: bake a runner image with 'sbx runners image', keep two warm runners with 'sbx runners serve --org <your-org> --snapshot <the image id> --warm 2 --max 8', point one workflow job at them with runs-on: [self-hosted, sbx], and show me how long the job waited and whether 'docker run' worked. Stop serve with Ctrl-C when done." --allowedTools "Bash(sbx:*)" "Bash(gh:*)"
```

Or by hand:

```bash
export E2B_API_KEY=<sandbox key>  GH_TOKEN=<token with admin:org>
snap=$(sbx runners image | tail -1)
sbx runners serve --org <your-org> --snapshot "$snap" --warm 2 --max 8
```

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

What we measured (5 rounds of a 16-job matrix, same jobs on GitHub-hosted
runners and two other self-hosted pools):

| | queue wait (median / worst) | `docker run` |
| --- | --- | --- |
| sandbox runners, 4 warm | 1 s / 1 s | 5/5 |
| GitHub-hosted `ubuntu-latest` | 2 s / 3 s | 5/5 |
| VM pool (droplets) | 2 s / 402 s | 0/5 (no Docker) |
| container pool | 5 s / 13 s | 0/5 (no Docker) |

A sandbox restores from the runner snapshot in about a second, with Docker
already running. Bursts past the warm pool scale up to `--max` and to your
key's concurrent-sandbox quota; add `--webhook-port` (see the `sbx` README)
so queued jobs grow the pool the moment they are queued.
