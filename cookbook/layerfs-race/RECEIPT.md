# RECEIPT — layerfs-race

Fresh end-to-end run of `python3 cookbook/layerfs-race/run.py --local`
from the host (the branch is not pushed, so the run packages and uploads the
worktree demo). Local commit at run time: `a370a5386e928a89f518542041c284f4ffd584fa`.
Each run: create sandbox -> upload -> setup -> selftest -> grade -> kill + confirm.

## Run — sandbox `01a1575a-cf2d-7213-9e12-24ea239cb5b0` (removed after)

```
[  0.5s] sandbox 01a1575a-cf2d-7213-9e12-24ea239cb5b0
[   0.9s] upload: ok
[ 282.4s] setup: ok
[2874.3s] selftest: ok
    selftest: mutant KILLED: claim-wrong-winner (failing gates: winner-is-a-branch)
    selftest: mutant KILLED: cp-a (failing gates: artifact,artifact-exit)
    selftest: mutant KILLED: fix-main-fs (failing gates: artifact,artifact-exit)
    selftest: mutant KILLED: fs-write-only (failing gates: branches)
    selftest: mutant KILLED: lie-volume (failing gates: artifact)
    selftest: mutant KILLED: merge-markers (failing gates: winner-green)
    selftest: mutant KILLED: publish-loser (failing gates: main-isolation,winner-is-a-branch,oracle-intact,winner-green,losers-red)
    selftest: mutant KILLED: publish-nothing (failing gates: main-isolation,winner-is-a-branch,oracle-intact,winner-green,losers-red)
    selftest: mutant KILLED: seven-branches (failing gates: branches,oracle-intact,losers-red)
    selftest: mutant KILLED: shift-candidates (failing gates: main-isolation,winner-is-a-branch,oracle-intact)
    selftest: kill rate: 10/10 (100%)
    selftest: determinism PASS (same seed -> identical verdict outside timing)
[ 317.3s] grade: ok
verdict: PASS
sandbox 01a1575a-cf2d-7213-9e12-24ea239cb5b0 removed
```

## Verdict (current run)

All eleven gates pass: artifact, bug-scope (2 failing on the bugged tree,
allowed 1-50), branches (`agent-0..7`, each with `via:exec` commits),
main-isolation (main moved only via publish; pre-publish layer holds the
bugged `lib/application.js` byte-identical), winner-is-a-branch (empty diff
vs main: agent-3 only; claimed agent-3; expected agent-3), oracle-intact
(every branch/main change vs the bugged base confined to `/lib/`),
winner-green (main re-run: 1238 passing / 0 failing, suite exit 0 = clean
baseline), losers-red
(`agent-0:3 agent-1:2 agent-2:5 agent-4:5 agent-5:5 agent-6:5 agent-7:2`),
storage, conflict-refused (`Conflict` on `/lib/application.js`), fork-latency.

## Measured numbers (current run)

| metric | value |
|---|---|
| source tree | 47,682,104 B |
| Store volume | 14,394,520 B |
| Store / source | 0.3019 |
| median `branch.fork` (forks 2-8, judge) | 0.0007 s |
| main suite (judge re-run) | 1238 passing / 0 failing, suite exit 0 |
| resolved-deps.txt sha256 | `d933663706754058430b15f1823b38686b142a720299c99d89023a9c6f79ad5f` (matches committed `judge/resolved-deps.txt`) |
| per-agent suite (artifact) | 16.4-32.7 s |
| wall: setup / selftest / grade | 282.4 / 2874.3 / 317.3 s (~58 min total) |

## Pre-fix runs (superseded)

Two earlier end-to-end `run.py --local` runs (local commit
`120997b36ccb247f853c3198b55de582bd4b2440`) passed with the pre-hardening
judge: verdict PASS, kill rate 10/10, Store/source 0.2997 / 0.2985, wall
setup / selftest / grade 291.5 / 1795.8 / 207.0 s and
290.1 / 1797.7 / 206.6 s. Their gate set lacked `oracle-intact` and the
artifact/grader exit checks; the current run above is authoritative.

## Deviations

- **express v5.2.1 instead of v5.3.0** — v5.3.0 was published <14 days before
  the pin date, violating SPEC's "nothing published in the last two weeks".
  v5.2.1 (dbac741a) is used; its `.npmrc` disables lockfiles, so deps are
  installed with `npm install` and the resolved tree is recorded
  (`resolved-deps.txt` + SHA256), per the SPEC's no-lockfile allowance.
- **send pinned to 1.1.0** — v5.2.1 floats `send@^1.1.0` and the current
  send@1.2.x breaks 55 `res.sendFile`/`res.download` tests at this tag. The
  tag-era `send@1.1.0` is installed (`--no-save`) and recorded in the
  resolved-deps snapshot.
- **`--local` receipt runs** — the branch was not pushed at receipt time, so
  the runs used `run.py --local` (tar + upload). They record the local
  commit SHA above; `run.py --ref <ref>` runs the same pipeline from a
  pushed git ref.
- **judge mounts `judge-main`, a fork of `main`** — `main` after publish is a
  Layer pointer, not a mountable Branch (`sandbox.mount` refuses it with
  `NoSuchBranch`). The judge forks `judge-main` off `main` (zero-copy,
  identical tree) and re-runs the suite on that mount — same tree, still
  read from the Store by the judge, never from `race.json`.
- **install prefix is `$HOME/layerfs-race`, not a dot-dir** — `send` treats
  any path segment starting with `.` as a dotfile and returns 404 for every
  `sendFile`; an earlier draft used `$HOME/.layerfs-race` and failed.
- **artifact closes the service Sandbox** — the SDK's internal service
  Sandbox keeps node's event loop alive; `race.mjs`/`grader.mjs` close it and
  call `process.exit(0)` so graders cannot hang the pipeline.
- **`sbx exec` steps redirect to a file** — `start-docker`'s `sudo`+`dockerd`
  daemonize while inheriting the exec's stdout, holding the stream open past
  the command's exit. `run.py` runs each step as `(cmd) > /tmp/step-*.log;
  cat /tmp/step-*.log` so the stream ends with the step.
- **`npx mocha --exit`** — without it the suite can sit on open handles after
  the last test (ep_poll) and never exit.
- **oracle/diff walls add ~2 min per grade** — the `oracle-intact` and
  `winner-is-a-branch` gates diff nine Store refs each against a
  judge-forked base (`diffs` + `oracle` wall_s ≈ 220 s per grade), which is
  why the self-test now takes ~48 min.
- **no media** — figures and video are out of scope for this entry; the
  scaffold's placeholder media files were removed rather than shipped.
