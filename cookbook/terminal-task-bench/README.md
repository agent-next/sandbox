# terminal-task-bench — a terminal task bench you host yourself

Ten broken filesystems, one agent program, one plain-JSON leaderboard. Each
task is a `task.md` problem statement, a filesystem that is genuinely broken
(a SQLite database whose WAL header was torn, a detached-HEAD repo with a
deleted branch, a systemd unit no parser accepts, a permissions maze, and
six more), and a `verify.sh` that decides whether the repair is right. Every
task runs in its own sandbox; the judge fans them out, scores them and
prints a leaderboard. A disposable sandbox is the right place for this: the
agent gets a throwaway root to break and repair, the verifiers run against a
copy so the fixture is never consumed, and a run leaves nothing behind.

The judge is not "the repair script exited 0". Every verifier compares
against an oracle that is independent of the repair: an analytic expectation
recorded before the fixture was damaged, the `git` reference implementation,
the program the repaired unit names (actually executed), a numeric spec mask,
or a test the verifier carries itself.

## Results

The known-good agent (`examples/good/`) repairs all ten tasks; an agent that
does nothing scores zero.

| gate | what it checks | measured |
|---|---|---|
| G1 | solved ≥ 8 of 10 | **10/10** |
| G2 | every pristine tree fails its own verifier | **10/10 rejected** |
| G3 | a `true`-only agent scores 0/10 | **0/10** |
| G4 | total verifier wall time ≤ 300 s | **~5 s** (2 vCPU) |
| G5 | the agent cannot modify `judge/` | **unchanged** |

**Self-test kill rate: 12/12 = 100 %** — twelve scripted single-edit mutants
of the good agent, each killed on the task it targets.

## Ask your agent

> Clone https://github.com/agent-next/sandbox and set up a sandbox
> (`python3 cookbook/terminal-task-bench/run.py` does it end to end, or
> `sbx create` and clone it yourself). Read
> `cookbook/terminal-task-bench/SPEC.md` and
> `cookbook/terminal-task-bench/fixtures/*/task.md`, then write **your own
> agent** at `cookbook/terminal-task-bench/examples/<your-name>/`, with one
> `solutions/<task-id>/apply.sh` per task that repairs that task's `work/`
> tree in place. Iterate with
> `bash cookbook/terminal-task-bench/judge/grade.sh examples/<your-name> --json v.json`
> until it exits 0, then paste the verdict JSON and the per-task timing
> table. Do not edit anything under `judge/` or `fixtures/*/verify.sh`; if
> you believe a verifier is wrong, say so instead of working around it. Kill
> the sandbox when you are done.

`examples/good/` is a worked answer — the reference repairs, each one
verified by the same gates. A working agent does not have to look like it.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/terminal-task-bench/run.py        # --ref main --keep --jobs N
```

Creates a sandbox, clones the repo, installs the pinned tools, runs the
judge self-test, grades `examples/good/`, prints the verdict JSON and a
summary line, then kills the sandbox and confirms it is gone. Stdlib only;
exits non-zero on any failure, naming the sandbox id if cleanup cannot be
confirmed.

## Measured wall time (Debian sandbox, 2 vCPU, 4 GB)

| step | wall time |
|---|---|
| `git clone --depth 1` | ~1 s |
| `judge/setup.sh` (fresh: downloads one .deb) | 20 s (idempotent re-run: 0.1 s) |
| `judge/grade.sh examples/good` | 11 s |
| `judge/selftest.sh` (good + 10 pristine + 12 mutants + determinism + 2nd seed) | 103 s |

Grading is seconds; the self-test does 40+ full bench runs and is the slow
part. `run.py` prints a per-step timing line.

## The ten tasks

| # | task id | broken thing | oracle |
|---|---|---|---|
| 1 | `wal-repair` | SQLite db with a torn WAL header | analytic expectation |
| 2 | `git-lost-branch` | detached HEAD; branch tip only in the reflog | reference tool (`git`) |
| 3 | `systemd-unit` | duplicate key, dead `ExecStart`, unknown `User` | reference execution |
| 4 | `perms-maze` | tool unreadable/unexecutable, leaked credential | reference execution + mask |
| 5 | `csv-normalize` | dirty CSV (CRLF, ragged rows, quoted junk) | analytic expectation |
| 6 | `json-config` | duplicate keys, trailing comma, wrong types | spec mask + invariant |
| 7 | `symlink-maze` | dangling link and a symlink cycle | analytic expectation |
| 8 | `tar-restore` | partial, partly wrong restore of an archive | analytic expectation |
| 9 | `bugfix-python` | boundary bug the shipped test does not catch | independent test |
| 10 | `cron-repair` | crontab lines no scheduler accepts | spec mask (field expansion) |

## Limits, plainly

- **No network at grade time.** Fixtures are generated from a seed by
  `fixtures/make_fixtures.py`; the only download is the pinned `sqlite3`
  Debian package in `judge/setup.sh`, sha256-checked.
- **No real systemd and no cron daemon.** The unit task is graded by parsing
  the unit and *running* the program `ExecStart` names; the cron task by
  expanding every field and comparing the value sets. Neither boots anything.
- **No model is invoked.** The "agent" is a shell program. This demo grades
  the bench, not a language model; which model writes an agent is up to you.
- **Two tasks carry a mask `task.md` does not enumerate** (the `audit` table
  in `wal-repair`, the world-writable rule in `perms-maze`), so a repair
  aimed only at the obvious symptom still fails. That is deliberate — see
  SPEC.md.
- The `sqlite3` pin is a Debian bookworm `.deb`; a non-Debian base image
  needs a different pin (the judge needs `sudo` once, for that install).
- `perms-maze` needs no root: the tree is owner-owned with mode bits that
  deny access, so the symptom is real without dropping privileges.
