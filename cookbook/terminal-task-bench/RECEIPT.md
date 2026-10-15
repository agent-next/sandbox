# RECEIPT — `cookbook/terminal-task-bench/`

Real command output, pasted as produced. Both runs below were made on this
branch's working tree, in a Debian sandbox (2 vCPU, 4 GB RAM, Python
3.12.15). Each run purged `sqlite3` first, so `judge/setup.sh` installed it
from nothing — the whole judge comes up from an empty image plus the pinned
`.deb`.

## Two fresh-setup runs, side by side

| | RUN-A | RUN-B |
|---|---|---|
| `judge/setup.sh` | exit 0, 29.8 s (download + install) | exit 0, 16.5 s |
| `judge/grade.sh examples/good` | exit 0, 10.2 s | exit 0, 8.3 s |
| `judge/selftest.sh` | exit 0, 102.6 s | exit 0, 81.4 s |
| sha256 of the `.deb` download | `58e59f7d…d1b819909` OK (`sha256sum -c`) | same, OK |
| sqlite3 installed | 3.40.1-2+deb12u2 | 3.40.1-2+deb12u2 |
| G1 solved | **10/10** | **10/10** |
| G2 pristine trees rejected | **10/10** | **10/10** |
| G3 negative control | **0/10** | **0/10** |
| G4 total verifier time | 3.056 s (limit 300) | 3.015 s (limit 300) |
| G5 judge tree unchanged | yes | yes |
| kill rate | **12/12 = 100 %** | **12/12 = 100 %** |
| verdict JSON (timing stripped) | identical | identical |

`diff` of the two verdict JSONs with `timing` removed → **no differences**
(compared in Python, `A == B` → `True`). The only numbers that move between
runs are the wall times under `timing`.

## `bash judge/setup.sh` (RUN-A, from a purged image)

```text
=== RUN-A: purge sqlite3 (everything setup.sh installs), then run setup.sh ===
Removing sqlite3 (3.40.1-2+deb12u2) ...
setup: installing sqlite3 3.40.1-2+deb12u2 from the Debian pool
/tmp/tmp.8QmNJK4iL4/sqlite3.deb: OK
Setting up sqlite3 (3.40.1-2+deb12u2) ...
setup: tool versions
Python 3.12.15
git version 2.39.5
3.40.1 2022-12-28 14:03:47 df5c253c0b3dd24916e4ec7cf77d3db5294cc9fd45ae7b9c5e82ad8197f3alt1
GNU bash, version 5.2.15(1)-release (x86_64-pc-linux-gnu)
tar (GNU tar) 1.34
setup: wrote .../judge/VERSIONS.txt
setup: done
[exit 0, 29776 ms]
```

(`dpkg`'s `Reading database ... N%` progress and the sandbox's
`sudo: unable to resolve host` line are elided; nothing else is.) Idempotent
re-run:

```text
setup: sqlite3 3.40.1-2+deb12u2 already installed (skipping)
setup: tool versions
...
setup: done
```

`judge/VERSIONS.txt` (written by `setup.sh` on every install; byte-identical
in RUN-A and RUN-B):

```text
# terminal-task-bench judge: versions installed by judge/setup.sh
# (Linux x86_64)
python3 3.12.15
git 2.39.5
sqlite3 3.40.1
sqlite3 debian package: 3.40.1-2+deb12u2
bash 5.2.15(1)-release
tar 1.34
```

## `bash judge/grade.sh examples/good --json /tmp/v.json` (RUN-A)

Exit 0. The full verdict, as printed:

```json
{
  "agent": "examples/good",
  "failed_gate": null,
  "gates": {
    "G1_solve_count": { "passed": true, "required": 8, "solved": 10, "total": 10 },
    "G2_pristine_fails": { "accepted_broken_tree": [], "passed": true, "tasks": 10 },
    "G3_negative_control": { "negctl_solved": 0, "passed": true, "required": 0 },
    "G4_budget": { "limit_seconds": 300.0, "over_budget": false, "passed": true },
    "G5_judge_untouched": { "judge_sha256_after": "fce78ef0ecad76a1",
                            "judge_sha256_before": "fce78ef0ecad76a1", "passed": true }
  },
  "passed": true,
  "seed": 20261015,
  "tasks": [
    { "apply_exit": 0, "negative_control_verify_exit": 1, "pristine_verify_exit": 1, "solved": true, "task": "bugfix-python",   "verify_exit": 0 },
    { "apply_exit": 0, "negative_control_verify_exit": 1, "pristine_verify_exit": 1, "solved": true, "task": "cron-repair",     "verify_exit": 0 },
    { "apply_exit": 0, "negative_control_verify_exit": 1, "pristine_verify_exit": 1, "solved": true, "task": "csv-normalize",   "verify_exit": 0 },
    { "apply_exit": 0, "negative_control_verify_exit": 1, "pristine_verify_exit": 1, "solved": true, "task": "git-lost-branch", "verify_exit": 0 },
    { "apply_exit": 0, "negative_control_verify_exit": 1, "pristine_verify_exit": 1, "solved": true, "task": "json-config",     "verify_exit": 0 },
    { "apply_exit": 0, "negative_control_verify_exit": 1, "pristine_verify_exit": 1, "solved": true, "task": "perms-maze",      "verify_exit": 0 },
    { "apply_exit": 0, "negative_control_verify_exit": 1, "pristine_verify_exit": 1, "solved": true, "task": "symlink-maze",    "verify_exit": 0 },
    { "apply_exit": 0, "negative_control_verify_exit": 1, "pristine_verify_exit": 1, "solved": true, "task": "systemd-unit",    "verify_exit": 0 },
    { "apply_exit": 0, "negative_control_verify_exit": 1, "pristine_verify_exit": 1, "solved": true, "task": "tar-restore",     "verify_exit": 0 },
    { "apply_exit": 0, "negative_control_verify_exit": 1, "pristine_verify_exit": 1, "solved": true, "task": "wal-repair",      "verify_exit": 0 }
  ],
  "timing": { "total_apply_seconds": 2.711, "total_verify_seconds": 3.056 }
}
[exit 0, 10192 ms]
```

Every row shows the three things the gates are built on: the repair ran
(`apply_exit` 0), the *pristine* tree was rejected (`pristine_verify_exit`
1) and the negative control was rejected too (`negative_control_verify_exit`
1), while the repaired copy passed (`verify_exit` 0).

## `bash judge/selftest.sh` (RUN-A)

Exit 0. Tail, as printed (the pristine-tree lines above it are elided; all
ten say `pristine <task> fails, as it must`):

```text
selftest: grading the known-good agent (.../examples/good)
selftest: known-good PASSED every gate
selftest:   solved 10/10, negative control scored 0/10
selftest: G2: every pristine tree must fail its own verifier
selftest:   pristine wal-repair fails, as it must
... (all ten)
selftest: G2 OK: all 10 pristine trees rejected
selftest: G3 OK: the negative control (runs `true` only) scored 0/10
selftest: building single-edit mutants of the known-good agent
mutants: wal-writes-aside  (wal-repair)  ...
mutants: git-detached-head  (git-lost-branch)  ...
mutants: unit-wrong-exec  (systemd-unit)  ...
mutants: perms-chmod-777  (perms-maze)  ...
mutants: csv-keeps-ragged  (csv-normalize)  ...
mutants: json-string-bool  (json-config)  ...
mutants: symlink-absolute  (symlink-maze)  ...
mutants: tar-skips-modes  (tar-restore)  ...
mutants: python-off-by-one  (bugfix-python)  ...
mutants: cron-names-dow  (cron-repair)  ...
mutants: csv-drops-quoting  (csv-normalize)  ...
mutants: tar-keeps-leftover  (tar-restore)  ...
mutants: wrote 12 mutants to /tmp/.../mutants
selftest:   killed    cron-names-dow (task cron-repair: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest:   killed    csv-drops-quoting (task csv-normalize: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest:   killed    csv-keeps-ragged (task csv-normalize: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest:   killed    git-detached-head (task git-lost-branch: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest:   killed    json-string-bool (task json-config: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest:   killed    perms-chmod-777 (task perms-maze: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest:   killed    python-off-by-one (task bugfix-python: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest:   killed    symlink-absolute (task symlink-maze: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest:   killed    tar-keeps-leftover (task tar-restore: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest:   killed    tar-skips-modes (task tar-restore: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest:   killed    unit-wrong-exec (task systemd-unit: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest:   killed    wal-writes-aside (task wal-repair: gate G1_solve_count, verify exit 1, pristine exit 1)
selftest: kill rate 12/12 = 100%
selftest: determinism: two --seed 1 runs must agree byte for byte
selftest: determinism OK (two --seed 1 runs byte-identical, timing stripped)
selftest: second seed: the verifiers must not be tuned to one fixture instance
selftest: seed 7 OK: known-good still passes every gate
selftest: OK
[exit 0, 102599 ms]
```

**Kill rate 12/12 = 100 %** (requirement ≥ 90 %, ≥ 5 known-bad). RUN-B's
tail is identical apart from the temp paths and `[exit 0, 81392 ms]`.

## Criterion-by-criterion evidence

1. **Pinned + sha256-checked tools.** `judge/setup.sh` installs exactly one
   package, `sqlite3` 3.40.1-2+deb12u2, from a URL whose sha256
   (`58e59f7d…d1b819909`) is checked with `sha256sum -c` before install
   (paste above: `sqlite3.deb: OK`). No `latest`, no pip, no tarball. Every
   other tool is required to be present and the script fails loudly if one
   is missing. `judge/VERSIONS.txt` records what was actually installed.
2. **Independent oracle.** No verifier accepts "the tool ran": see SPEC.md's
   oracle table. `wal-repair`, `csv-normalize`, `symlink-maze` and
   `tar-restore` compare against literals recorded *before* the fixture was
   damaged; `git-lost-branch` asks `git`; `systemd-unit` and `perms-maze`
   execute the program the artifact names; `json-config` and `cron-repair`
   apply a numeric spec mask; `bugfix-python` runs a test the verifier
   carries, covering a boundary the shipped test never reaches.
3. **The judge can fail.** The self-test above: known-good passes, all ten
   pristine trees fail, the `true`-only negative control scores 0/10, and 12
   scripted single-edit mutants are all killed on the task they target.
4. **Deterministic.** `selftest.sh` runs `grade.sh --seed 1 --strip` twice
   and compares byte for byte (`determinism OK` above). Every wall time is
   confined to the `timing` key and to the `over_budget` boolean, so nothing
   a slow machine can change reaches the pass rule.
5. **Two fresh-sandbox runs.** Table at the top; verdicts byte-identical
   after stripping `timing`.
6. **`examples/good/`** is original to this demo (no third-party source), and
   is graded by the same `judge/grade.sh` as any other agent — the verdict
   above is that grading.

## run.py verification

(not done: end-to-end `sbx` run — this authoring sandbox has no `sbx` CLI
and no API key, and cannot create cloud sandboxes. The lead runs it end to
end.) What was done instead, per the demo standard:

- `python3 -m py_compile run.py` — OK; `run.py --help` renders.
- The exact in-sandbox command sequence `run.py` sends to `sbx exec` was
  run directly from this branch's working tree —
  `bash judge/setup.sh`, `bash judge/selftest.sh`,
  `bash judge/grade.sh examples/good --jobs 2 --json /tmp/verdict.json` —
  and its output is pasted above; `run.py` echoes those same lines.
- `run.py` always kills the sandbox in a `finally` block and confirms with
  `sbx list`; a kill that is not confirmed exits non-zero naming the id.

## Deviations

- **The artifact is an agent directory, not a single file.** The standard's
  `grade.sh <artifact>` signature is kept (`grade.sh <agent-dir>`); the
  artifact is a directory because a bench agent is inherently ten programs.
- **`perms-maze` uses no root.** The brief's fixture is a permissions maze;
  the original design made the tree root-owned and dropped privileges to
  `nobody`. That needs `sudo` at grade time and behaves differently under a
  root-run judge, so the fixture instead owns every path with mode bits that
  deny access: the symptom (Permission denied) is real, the repair is
  checkable by reading modes, and the judge needs no privileges. The mask
  punishes both blanket repairs (`chmod -R 777` leaves a world-writable
  path; `chmod -R 755` exposes the credential file).
- **The WAL task is graded on the database file, not on "a WAL exists".**
  The fixture tears the WAL header checksum; a repair may replay the frames
  itself or recover the data any other way. The verifier requires the
  committed rows to read back from `app.db` with no non-empty `-wal` beside
  it. An earlier draft only *noted* a leftover WAL, and the mutant
  `wal-writes-aside` survived it; the verifier was tightened until it was
  killed (kill rate 9/10 → 12/12).
- **Two spec masks are deliberately not in `task.md`** (the `audit` table in
  `wal-repair`; the world-writable rule in `perms-maze`), so a repair aimed
  only at the stated symptom still fails. Stated in SPEC.md.
- **The systemd task is graded without systemd.** No systemd exists on the
  image, so the verifier parses the unit with the real unit grammar and then
  *executes* the program `ExecStart` names. It accepts either an absolute
  path that exists on the image or the tree-relative path (the fixture is a
  stand-in root).
- **No media in this task.** `media/` (figures, video, `make_media.sh`) is
  produced by a separate later task; this receipt and README carry the
  numbers instead.
- **Wall times differ between RUN-A and RUN-B** (29.8 s vs 16.5 s for setup)
  — network and apt cache, as expected; no verdict field changes with them.
- Third-party content: none beyond the pinned Debian `sqlite3` package
  (public-domain-ish SQLite CLI, from the Debian bookworm pool; URL and
  sha256 in `judge/setup.sh`). All fixtures are generated by
  `fixtures/make_fixtures.py` from a seed.
