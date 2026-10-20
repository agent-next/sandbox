# RECEIPT — layerfs-race

Fresh end-to-end run of `python3 cookbook/layerfs-race/run.py --local`
from the host (the branch is not pushed, so the run packages and uploads the
worktree demo). Local commit at run time: `f551e9df5f5ab203efd90652249d0e8f79938ea3`.
Each run: create sandbox -> upload -> setup -> selftest -> grade -> kill + confirm.

## Run — sandbox `01a157a9-d402-7a72-bd16-7315a55b9c04` (removed after proofs)

```
[  0.4s] sandbox 01a157a9-d402-7a72-bd16-7315a55b9c04
[   0.9s] upload: ok
[ 289.8s] setup: ok
[3309.3s] selftest: ok
    selftest: mutant KILLED: claim-wrong-winner (failing gates: winner-is-a-branch)
    selftest: mutant KILLED: cp-a (failing gates: artifact,artifact-exit)
    selftest: mutant KILLED: doctored-base (failing gates: base-intact)
    selftest: mutant KILLED: fix-main-fs (failing gates: artifact,artifact-exit)
    selftest: mutant KILLED: fs-write-only (failing gates: branches)
    selftest: mutant KILLED: lie-volume (failing gates: artifact)
    selftest: mutant KILLED: merge-markers (failing gates: winner-green)
    selftest: mutant KILLED: publish-loser (failing gates: main-isolation,winner-is-a-branch,oracle-intact,base-intact,winner-green,losers-red)
    selftest: mutant KILLED: publish-nothing (failing gates: main-isolation,winner-is-a-branch,oracle-intact,base-intact,winner-green,losers-red)
    selftest: mutant KILLED: seven-branches (failing gates: branches,oracle-intact,losers-red)
    selftest: mutant KILLED: shift-candidates (failing gates: main-isolation,winner-is-a-branch,oracle-intact,base-intact)
    selftest: kill rate: 11/11 (100%)
    selftest: determinism PASS (same seed -> identical verdict outside timing)
[ 331.3s] grade: ok
verdict: PASS
```

## Verdict (current run)

All twelve gates pass: artifact, bug-scope (2 failing on the bugged tree,
allowed 1-50), branches (`agent-0..7`, each with `via:exec` commits),
main-isolation (main moved only via publish; pre-publish layer holds the
bugged `lib/application.js` byte-identical), winner-is-a-branch (empty diff
vs main: agent-3 only; claimed agent-3; expected agent-3), oracle-intact
(every branch/main change vs the bugged base confined to `/lib/`),
base-intact (pre-publish base tree byte-identical to the judge's bugged
tree, full-tree digest), winner-green (main re-run: 1238 passing /
0 failing, suite exit 0 = clean baseline), losers-red
(`agent-0:3 agent-1:2 agent-2:5 agent-4:5 agent-5:5 agent-6:5 agent-7:2`),
storage, conflict-refused (`Conflict` on `/lib/application.js`),
fork-latency.

Mutant-attribution honesty: `cp-a` and `fix-main-fs` are still killed only
on `artifact,artifact-exit` — their artifacts crash before the grader
runs, so the tree/branch gates are never exercised by them. The other 9
mutants die on functional gates. `doctored-base` (new) is killed solely by
`base-intact`, which is the only gate that sees a poisoned shared base.

## Anti-tamper proofs (scratch, same sandbox)

- Planted verdict: a scratch artifact that writes a read-only
  `{"verdict":"PASS"}` at the judge's old verdict path
  (`dirname($RACE_OUT)/verdict.json`, chmod 444) and exits 0 -> `grade.sh`
  exited 1 and printed a real FAIL (`artifact` gate: race.json missing).
  The verdict is written to a fresh random dir created after the
  artifact's process group is dead, so the plant is ignored.
- Unwritable verdict: `grader.mjs` pointed at a chmod-555 output dir exits
  1 (previously the `uncaughtException -> finish -> exit(0)` path exited
  0), so `grade.sh` force-fails on `grader-exit`.

## Measured numbers (current run)

| metric | value |
|---|---|
| source tree | 47,682,104 B |
| Store volume | 14,262,776 B |
| Store / source | 0.2991 |
| median `branch.fork` (forks 2-8, judge) | 0.0007 s |
| main suite (judge re-run) | 1238 passing / 0 failing, suite exit 0 |
| resolved-deps.txt sha256 | `d933663706754058430b15f1823b38686b142a720299c99d89023a9c6f79ad5f` (matches committed `judge/resolved-deps.txt`) |
| bugged tree sha256 | `6fcba3551c1d9dc385e327d2866fc5c7f23559e48735edd4ff43aba8b1076553` |
| per-agent suite (artifact) | 15.5-31.1 s |
| wall: setup / selftest / grade | 289.8 / 3309.3 / 331.3 s (~66 min total) |

## Pre-fix runs (superseded)

- Hardened-judge run at local commit `a370a538` (pre-round-2 fixes):
  verdict PASS, kill rate 10/10, Store/source 0.3019, wall
  setup / selftest / grade 282.4 / 2874.3 / 317.3 s. Its gate set lacked
  `base-intact` and the planted-verdict defense; the current run above is
  authoritative.
- Two earlier end-to-end `run.py --local` runs (local commit
  `120997b36ccb247f853c3198b55de582bd4b2440`) passed with the
  pre-hardening judge: verdict PASS, kill rate 10/10, Store/source
  0.2997 / 0.2985, wall setup / selftest / grade 291.5 / 1795.8 / 207.0 s
  and 290.1 / 1797.7 / 206.6 s.

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
- **oracle/diff walls add ~4 min per grade** — the `oracle-intact` and
  `winner-is-a-branch` gates diff nine Store refs each against a
  judge-forked base (`diffs` + `oracle` wall_s ≈ 226 s per grade) plus the
  `base-intact` digest (~13 s), which is why the self-test now takes ~55 min.
- **verdict never touches a file** (after the round-3 review) — the run
  above wrote the verdict into a post-artifact random dir, which a child
  that escapes the artifact's session could still swap. The grader now
  prints it on stdout as one `VERDICT_JSON` line that `grade.sh` keeps in
  memory, and the `base-intact` digest now also covers file types, modes and
  symlink targets (a retargeted `node_modules/.bin/mocha` was invisible to
  the contents-only digest). Residual risk, stated in README Limits: an
  escaped child still runs during grading with the Docker socket.
- **no media** — figures and video are out of scope for this entry; the
  scaffold's placeholder media files were removed rather than shipped.
- **dependencies resolve as of a fixed date.** A `run.py --ref` at 2494bdb8
  failed setup on the drift check: `electron-to-chromium` moved from 1.5.459
  to 1.5.460 on npm after the run above, because express v5.2.1 ships no
  lockfile and `npm install` floats. A committed lockfile (180 KB) is over
  the cookbook's 50 KB file limit, so setup now runs
  `npm install --before=2026-10-19T00:00:00Z` (and pins `send@1.1.0` the same
  way); `judge/resolved-deps.txt` was regenerated from that resolution (3
  build-tool lines changed; the suite is still 1238 passing). The run above
  predates this; its deps sha256 is the old snapshot.
