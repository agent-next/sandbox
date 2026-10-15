# RECEIPT — `cookbook/scheduled-agent-digest/`

Real command output from two fresh sandbox-like runs (Debian 12, Python
3.12.15, 2 vCPU / ~4 GB), on 2026-10-15. The demo cannot create cloud
sandboxes from inside a build sandbox, so "fresh sandbox" here is a fresh
`git clone` of this repo into an empty directory with `$HOME` cleared of the
pinned tools — the same sequence `run.py` sends to `sbx exec` (see
"Deviations"). Every command was run from
`cookbook/scheduled-agent-digest/`.

## Run 1 — fresh clone, system sqlite3 3.40.1 already present

```
$ bash judge/setup.sh
[setup] python3 3.12.15 present
[setup] sqlite3 3.40.1 already present -> /usr/bin/sqlite3
[setup] done.
  sqlite3 -> /usr/bin/sqlite3 (3.40.1)
  python3 -> /usr/local/bin/python3
  versions -> .../cookbook/scheduled-agent-digest/judge/VERSIONS.txt
exit=0
```

```
$ time bash judge/selftest.sh
selftest: known-good PASS
selftest: mutant KILLED: all-rows-counted (failed gate: digest)
selftest: mutant KILLED: busiest-tie-wrong (failed gate: digest)
selftest: mutant KILLED: cron-hour-3 (failed gate: schedule)
selftest: mutant KILLED: extra-key (failed gate: shape)
selftest: mutant KILLED: mean-unrounded (failed gate: digest)
selftest: mutant KILLED: no-events-as-zero (failed gate: negative)
selftest: mutant KILLED: p95-off-by-one (failed gate: digest)
selftest: mutant KILLED: paused-skipped (failed gate: schedule)
selftest: kill rate 8/8 (100%)
selftest: determinism PASS (same seed -> identical verdict)
selftest: PASS
exit=0
real  0m36.468s
```

```
$ time bash judge/grade.sh examples/good --json /tmp/v.json
{
  "artifact": "examples/good",
  "seed": 20261015,
  "gates": {
    "digest": {
      "passed": true,
      "2026-10-12_events": 128,
      "2026-10-12_errors": 16,
      "2026-10-12_server_errors": 1,
      "2026-10-12_error_rate": 0.125,
      "2026-10-12_mean_ms": 2908.883,
      "2026-10-12_p50_ms": 281,
      "2026-10-12_p95_ms": 16447,
      "2026-10-12_max_ms": 19837,
      "2026-10-13_events": 141,
      "2026-10-13_errors": 18,
      "2026-10-13_server_errors": 4,
      "2026-10-13_error_rate": 0.12766,
      "2026-10-13_mean_ms": 3380.007,
      "2026-10-13_p50_ms": 281,
      "2026-10-13_p95_ms": 16098,
      "2026-10-13_max_ms": 19987,
      "2026-10-14_events": 96,
      "2026-10-14_errors": 15,
      "2026-10-14_server_errors": 4,
      "2026-10-14_error_rate": 0.15625,
      "2026-10-14_mean_ms": 3352.594,
      "2026-10-14_p50_ms": 292,
      "2026-10-14_p95_ms": 14552,
      "2026-10-14_max_ms": 19859,
      "busiest": {"2026-10-12": "api", "2026-10-13": "api", "2026-10-14": "batch"}
    },
    "dates": {"passed": true, "counts": {"2026-10-12": 128, "2026-10-13": 141, "2026-10-14": 96}},
    "shape": {"passed": true, "keys": ["busiest_project", "date", "error_rate", "errors",
      "events", "max_ms", "mean_ms", "p50_ms", "p95_ms", "projects", "server_errors", "status"]},
    "schedule": {"passed": true, "cron": "0 2 * * *",
      "steps": ["sleep_until_fire", "resume", "digest", "collect", "pause"]},
    "lifecycle": {"passed": true, "fires": ["2026-10-12", "2026-10-13", "2026-10-14"],
      "states_between_runs": ["paused", "paused", "paused"], "pause_seconds": 0.05, "sandbox": null},
    "negative": {"passed": true, "status": "no events", "events": 0},
    "failure": {"passed": true, "exit_code": 1, "names_log": true},
    "integrity": {"passed": true, "copied_to": "<temp>/artifact", "judge_untouched": true}
  },
  "passed": true,
  "failed_gate": null,
  "reason": "",
  "timing": {"wall_seconds": 3.487}
}
grade: PASS (all gates; judge integrity verified)
exit=0
real  0m3.935s
```

## Run 2 — fresh clone, `$HOME` cleared, pinned debs downloaded and sha256-checked

`PATH` was shadowed with a fake `sqlite3` reporting `3.99.9` so `setup.sh`
takes its download branch; `$HOME` was an empty directory.

```
$ PATH="/tmp/shadow:$PATH" HOME=/tmp/fh2 bash judge/setup.sh
[setup] python3 3.12.15 present
[setup] downloading sqlite3_3.40.1-2+deb12u2_amd64.deb
[setup] downloading libsqlite3-0_3.40.1-2+deb12u2_amd64.deb
[setup] installed /tmp/fh2/.scheduled-agent-digest/bin/sqlite3 (3.40.1-2+deb12u2)
[setup] done.
  sqlite3 -> /tmp/fh2/.scheduled-agent-digest/bin/sqlite3 (3.40.1)
  python3 -> /usr/local/bin/python3
  versions -> .../judge/VERSIONS.txt

  add the pinned tools to PATH: export PATH="/tmp/fh2/.scheduled-agent-digest/bin:$PATH"
exit=0
real  0m3.346s
```

```
$ PATH="/tmp/fh2/.scheduled-agent-digest/bin:$PATH" bash judge/selftest.sh
selftest: known-good PASS
selftest: mutant KILLED: all-rows-counted (failed gate: digest)
selftest: mutant KILLED: busiest-tie-wrong (failed gate: digest)
selftest: mutant KILLED: cron-hour-3 (failed gate: schedule)
selftest: mutant KILLED: extra-key (failed gate: shape)
selftest: mutant KILLED: mean-unrounded (failed gate: digest)
selftest: mutant KILLED: no-events-as-zero (failed gate: negative)
selftest: mutant KILLED: p95-off-by-one (failed gate: digest)
selftest: mutant KILLED: paused-skipped (failed gate: schedule)
selftest: kill rate 8/8 (100%)
selftest: determinism PASS (same seed -> identical verdict)
selftest: PASS
exit=0
real  0m45.236s
```

```
$ PATH="/tmp/fh2/.scheduled-agent-digest/bin:$PATH" bash judge/grade.sh examples/good --json /tmp/v2.json
grade: PASS (all gates; judge integrity verified)
exit=0
real  0m4.756s
```

## Two fresh runs side by side

| | Run 1 (system sqlite3) | Run 2 (pinned sqlite3 from `$HOME`) |
|---|---|---|
| `setup.sh` exit | 0 | 0 |
| `selftest.sh` exit | 0 | 0 |
| kill rate | 8/8 (100 %) | 8/8 (100 %) |
| `grade.sh` exit | 0 | 0 |
| night 1 events / errors / p50 / p95 | 128 / 16 / 281 / 16447 | 128 / 16 / 281 / 16447 |
| night 2 events / errors / p50 / p95 | 141 / 18 / 281 / 16098 | 141 / 18 / 281 / 16098 |
| night 3 events / errors / p50 / p95 | 96 / 15 / 292 / 14552 | 96 / 15 / 292 / 14552 |
| states between fires | paused, paused, paused | paused, paused, paused |
| `grade.sh` wall | 3.935 s | 4.756 s |
| verdict JSON, timing removed | byte-identical | byte-identical |

The two verdict JSONs are equal after removing the `timing` key
(`a == b` → `True`); only `timing.wall_seconds` differs (3.487 vs 4.150),
which SPEC.md excludes from the determinism check.

## Tool versions actually installed

```
$ cat judge/VERSIONS.txt
# recorded by judge/setup.sh (re-running setup leaves this file unchanged)
sqlite3 3.40.1-2+deb12u2 (upstream 3.40.1)
python3 3.12.15
```

Pinned download: `sqlite3_3.40.1-2+deb12u2_amd64.deb`
sha256 `58e59f7db8a88f87333c3f9896b98146fdf4dc33eda75a1f79d9100d1b819909`;
`libsqlite3-0_3.40.1-2+deb12u2_amd64.deb`
sha256 `a8d78b40e9b4e422224aeebfe0e4dfc243f6acf3532490b0c05480d4283d41e2`,
both from `deb.debian.org`.

## Deviations

- **No cloud sandbox was created for this receipt.** The build environment
  cannot create agent-next sandboxes, so each "fresh sandbox" is a fresh
  `git clone` into an empty directory (Run 1) and a fresh clone with `$HOME`
  cleared and the pinned tools downloaded from scratch (Run 2). The exact
  in-sandbox sequence `run.py` sends to `sbx exec` — `judge/setup.sh` →
  `judge/selftest.sh` → `judge/grade.sh examples/good` — was run verbatim
  under `bash -c` in both, so `run.py`'s command sequence is verified even
  though `sbx create`/`sbx kill` themselves were not exercised here. The lead
  runs `run.py` end to end.
- **`run.py` was verified with `python3 -m py_compile` and by running its
  in-sandbox command sequence directly**, not by creating a sandbox. Its
  `sbx create` / `sbx exec` / `sbx kill` / `sbx list` calls follow the same
  shape as `cookbook/plc-st/run.py`.
- **Media is not done in this task** (a later task adds `media/`). This
  receipt therefore has no figure references; README's Results section is a
  table of the same pinned numbers, each naming the command that produced it.
- **`REPRODUCE.md` is not done in this task** — the standard requires an
  independent reproduction by a different agent before merge; that is a
  separate step.
- `judge/setup.sh` installs into `$HOME/.scheduled-agent-digest` and prints the
  `export PATH=...` line; `judge/grade.sh` prepends that directory to `PATH`
  itself, so the pinned binary is used automatically when present and the
  system `sqlite3` otherwise (both paths exercised above).
