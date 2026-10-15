# scheduled-agent-digest: the agent that works while you sleep

A cron-triggered agent-next sandbox wakes at 02:00, digests yesterday's
request log, files a summary, and **pauses itself again** — so the idle hours
between runs cost nothing. The agent writes the two pieces the platform needs:
`digest.py` (the work that runs inside the sandbox for a few seconds a night)
and `schedule.json` (the job: cron, command, timezone, and the five lifecycle
steps `sleep_until_fire → resume → digest → collect → pause`).

A judge the agent cannot fool then checks the result with numbers, not vibes:
every aggregate in each night's digest is recomputed by an **independent
sqlite3 oracle** and compared field by field, and the sandbox state *between*
fires is read from the lifecycle the judge drives — it must read `paused`
between every pair of fires and `running` during each. An empty event log must
produce a digest that says `"no events"`, not zeros fabricated from a stale
run. Eight single-edit mutants of the good artifact prove the judge can fail.

Why a sandbox: the point of the job is that it runs unattended on a schedule
and costs nothing while paused. The demo grades that whole lifecycle —
including the pause/resume state transitions — through a replaceable
transport, so it runs end to end with no cloud account, no API key and no
bill; the same five steps wire to the real `sbx` CLI in `run.py`.

## Results

| | |
|---|---|
| **Verdict** | ✅ **PASS** — all 8 gates passed, 8/8 mutants killed (100 % kill rate) |
| **Night 1** (2026-10-12) | 128 events, 16 errors, error_rate 0.125, p50 281 ms, p95 16447 ms, busiest `api` |
| **Night 2** (2026-10-13) | 141 events, 18 errors, error_rate 0.12766, p50 281 ms, p95 16098 ms, busiest `api` |
| **Night 3** (2026-10-14) | 96 events, 15 errors, error_rate 0.15625, p50 292 ms, p95 14552 ms, busiest `batch` |
| **State between fires** | `paused` after every one of the three nights |
| **Determinism** | Verified — same `--seed` produces byte-identical verdict JSON |

Every number above is from `judge/grade.sh examples/good --json verdict.json`
with the default seed; they are pinned in [SPEC.md](SPEC.md) and recomputed by
the oracle on every run.

## What the artifact must do

See [SPEC.md](SPEC.md). The deliverable is a directory holding:

- `digest.py` — stdlib-only; `python3 -I digest.py --log LOG --date DATE --out
  OUT` writes one JSON object with the exact pinned key set (`date`, `status`,
  `events`, `errors`, `server_errors`, `error_rate`, `mean_ms`, `p50_ms`,
  `p95_ms`, `max_ms`, `projects`, `busiest_project`). Percentiles are
  nearest-rank (`ceil(q·n)`, 1-based); an empty selection is `"status": "no
  events"` with zeroed numerics; a malformed row makes it exit non-zero, name
  the log and the row, and leave nothing behind.
- `schedule.json` — one nightly job firing `0 2 * * *`, with
  `pause_between_runs: true` and exactly the five canonical steps.

## One-command run

```bash
export SBX_API_KEY=<your key>     # https://sbx.agent-next.com/console
python3 cookbook/scheduled-agent-digest/run.py   # needs the sbx CLI (pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli")
```

`run.py` creates a disposable sandbox (`sbx create --timeout-min 30`), clones
this repo at `--ref main` (default; `--ref` to override), runs
`judge/setup.sh` → `judge/selftest.sh` →
`judge/grade.sh examples/good`, prints the verdict JSON and a short summary,
and **always** kills the sandbox in a `finally` block, confirming with
`sbx list` that the id is gone. Non-zero exit on any failure, naming the
sandbox id if cleanup could not be confirmed. `--keep` leaves the sandbox up
and prints its id.

Without a key, run the same steps in any Debian 12 box, from
`cookbook/scheduled-agent-digest/`:

```bash
bash judge/setup.sh                                   # pinned sqlite3 (Debian 3.40.1-2+deb12u2), sha256-checked
bash judge/selftest.sh                                # good artifact + 8 mutants + determinism
bash judge/grade.sh examples/good --json verdict.json # default seed 20261015
```

Measured wall times (2 vCPU, ~4 GB, Debian bookworm, the sandbox's own shell):

| step | wall |
| --- | --- |
| `judge/setup.sh` (sqlite3 already present) | ~0.4 s |
| `judge/setup.sh` (fresh, downloads both pinned debs) | ~1.8 s |
| `judge/selftest.sh` (good + 8 mutants + determinism) | ~25 s |
| `judge/grade.sh examples/good` | ~2.2 s |

## Ask your agent

Paste this into a session with the sandbox plugin enabled:

> In a sandbox, build the nightly-digest artifact for
> `cookbook/scheduled-agent-digest` from scratch. Read `SPEC.md` first, then
> write your own `digest.py` (stdlib only) and `schedule.json` so the nightly
> job wakes a paused sandbox at 02:00, digests yesterday's event log, collects
> the digest, and pauses again. Iterate with `bash judge/selftest.sh` and
> `bash judge/grade.sh <your-artifact-dir> --json /tmp/v.json` until the judge
> passes every gate and your artifact is not one of the eight known-bad
> single-edit mutants. Show me the three nights' digests (the key numbers per
> night), the sandbox state between fires, and the final verdict JSON. Do not
> modify anything under `judge/`.

The agent works on the artifact inside the disposable sandbox; the judge lives
in the repo and is never modified by what the agent runs.

## Rebuilding the fixtures

The event logs are generated, not downloaded, by `judge/make_fixtures.py` from
a fixed seed, so every number is byte-reproducible and nothing is fetched at
grade time:

```bash
python3 judge/make_fixtures.py --outdir /tmp/fixtures
```

Each night's log holds that day's events plus a few rows from the previous day
and the two hours after midnight of the fire day, so a digester that totals the
whole file instead of filtering by date is caught immediately (138/150/109
rows in the files vs the pinned 128/141/96 on the log dates).

## Limits (stated plainly)

- The sandbox lifecycle is graded through a **replaceable transport** that
  simulates the pause locally (`paused_sleep`): no real cloud sandbox, no real
  pause/resume, no cost. The `sbx`-facing shims are wired against a fake
  client and proven by the judge; a real run wires them to the `sbx` CLI
  exactly as `run.py` does. See [SPEC.md](SPEC.md) "Canonical run".
- The three "nights" are three fixture logs graded in one process, not three
  real wall-clock days. The state between fires is read from the transport the
  judge drives, which is the same state a scheduler would observe.
- The digest's presentation (formatting, prose) is out of scope; only the
  pinned JSON fields are graded.
- `digest.py` is stdlib-only and single-threaded; the whole grade is a few
  seconds on 2 vCPU / ~3 GB.

## Pinned tools and licences

- **sqlite3 CLI 3.40.1-2+deb12u2** — Debian bookworm package, downloaded from
  `deb.debian.org` and sha256-checked (`judge/setup.sh`), providing the judge's
  independent aggregate engine. Licence: public domain (SQLite).
- **Python 3.10+**, standard library only — `digest.py`, the judge, the
  mutants. No pip packages are installed.

Nothing is fetched with `latest`; nothing is published in the last two weeks.
Versions actually installed are recorded in `judge/VERSIONS.txt`.
