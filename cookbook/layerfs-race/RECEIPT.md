# RECEIPT — layerfs-race

Two fresh end-to-end runs of `python3 cookbook/layerfs-race/run.py --local`
from the host (the local branch is not pushed, so runs package and upload the
worktree demo). Local commit at run time: `120997b36ccb247f853c3198b55de582bd4b2440`.
Each run: create sandbox -> upload -> setup -> selftest -> grade -> kill + confirm.

## Run A — sandbox `01a156ed-0f84-7ca0-9236-8c946585094a` (removed after)

```
[  0.6s] sandbox 01a156ed-0f84-7ca0-9236-8c946585094a
[   0.9s] upload: ok
[ 291.5s] setup: ok
[1795.8s] selftest: ok
    selftest: mutant KILLED: claim-wrong-winner (failing gates: winner-is-a-branch)
    selftest: mutant KILLED: cp-a (failing gates: artifact)
    selftest: mutant KILLED: fix-main-fs (failing gates: artifact)
    selftest: mutant KILLED: fs-write-only (failing gates: artifact)
    selftest: mutant KILLED: lie-volume (failing gates: artifact)
    selftest: mutant KILLED: merge-markers (failing gates: winner-green)
    selftest: mutant KILLED: publish-loser (failing gates: main-isolation,winner-is-a-branch,winner-green,losers-red)
    selftest: mutant KILLED: publish-nothing (failing gates: main-isolation,winner-is-a-branch,winner-green,losers-red)
    selftest: mutant KILLED: seven-branches (failing gates: artifact)
    selftest: mutant KILLED: shift-candidates (failing gates: main-isolation,winner-is-a-branch)
    selftest: kill rate: 10/10 (100%)
    selftest: determinism PASS (same seed -> identical verdict outside timing)
[ 207.0s] grade: ok
verdict: PASS
sandbox 01a156ed-0f84-7ca0-9236-8c946585094a removed
```

## Run B — sandbox `01a156ed-0f2c-7280-a236-bfb2f4066e34` (removed after)

```
[  0.5s] sandbox 01a156ed-0f2c-7280-a236-bfb2f4066e34
[   0.9s] upload: ok
[ 290.1s] setup: ok
[1797.7s] selftest: ok
    selftest: mutant KILLED: claim-wrong-winner (failing gates: winner-is-a-branch)
    selftest: mutant KILLED: cp-a (failing gates: artifact)
    selftest: mutant KILLED: fix-main-fs (failing gates: artifact)
    selftest: mutant KILLED: fs-write-only (failing gates: artifact)
    selftest: mutant KILLED: lie-volume (failing gates: artifact)
    selftest: mutant KILLED: merge-markers (failing gates: winner-green)
    selftest: mutant KILLED: publish-loser (failing gates: main-isolation,winner-is-a-branch,winner-green,losers-red)
    selftest: mutant KILLED: publish-nothing (failing gates: main-isolation,winner-is-a-branch,winner-green,losers-red)
    selftest: mutant KILLED: seven-branches (failing gates: artifact)
    selftest: mutant KILLED: shift-candidates (failing gates: main-isolation,winner-is-a-branch)
    selftest: kill rate: 10/10 (100%)
    selftest: determinism PASS (same seed -> identical verdict outside timing)
[ 206.6s] grade: ok
verdict: PASS
sandbox 01a156ed-0f2c-7280-a236-bfb2f4066e34 removed
```

## Verdict (Run A — Run B identical modulo timing)

All ten gates pass: artifact, bug-scope (2 failing on the bugged tree,
allowed 1-50), branches (`agent-0..7`, each with `via:exec` commits),
main-isolation (main moved only via publish; pre-publish layer holds the
bugged `lib/application.js` byte-identical), winner-is-a-branch (empty diff
vs main: agent-3 only; claimed agent-3; expected agent-3), winner-green
(main re-run: 1238 passing / 0 failing = clean baseline), losers-red
(`agent-0:3 agent-1:2 agent-2:5 agent-4:5 agent-5:5 agent-6:5 agent-7:2`),
storage, conflict-refused (`Conflict` on `/lib/application.js`), fork-latency.

## Measured numbers (Run A / Run B)

| metric | A | B |
|---|---|---|
| source tree | 47,682,104 B | 47,682,104 B |
| Store volume | 14,291,328 B | 14,233,888 B |
| Store / source | 0.2997 | 0.2985 |
| median `branch.fork` (forks 2-8, judge) | 0.0006 s | 0.0007 s |
| main suite (judge re-run) | 1238/0 | 1238/0 |
| per-agent suite (artifact) | 17.8-35.0 s | 17.4-35.0 s |
| wall: setup / selftest / grade | 291.5 / 1795.8 / 207.0 s | 290.1 / 1797.7 / 206.6 s |

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
- **no media** — figures and video are out of scope for this entry; the
  scaffold's placeholder media files were removed rather than shipped.
