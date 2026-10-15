# Receipt — 2026-10-15

Two runs from two fresh clones of branch `sbx/demo-web-scrape-dataset`, each with
its own empty `WSD_HOME`, on a 2 vCPU / 4 GB Debian sandbox (Linux 6.1.175,
x86_64), `python3` 3.12.15. Both use the default seed `20261015`.

The commands below are the exact ones `run.py` sends into a sandbox, run here
in-sandbox-equivalent form (the sandbox cannot create sandboxes). `run.py`
itself was checked with `python3 -m py_compile` and by running its in-sandbox
command sequence directly; the lead runs it end to end.

## Tool versions (`judge/VERSIONS.txt`, written by `setup.sh`)

```
playwright_python: 1.63.0
python: Python 3.12.15
browsers_path: /opt/ms-playwright
chromium_headless_shell_rev: 1243
chromium_headless_shell_version: Google Chrome for Testing 153.0.8010.12
chromium_binary_sha256: ded93a9c9a53a1ae040f08124badcca95c938e9d5015ff340c3b5538c41bf39e
uname: Linux 6.1.175 x86_64
```

## Run 1 — `bash judge/setup.sh`

```
[setup] installing Playwright 1.63.0 (hash-pinned requirements)
[setup] playwright 1.63.0 importable
[setup] using the pre-installed browser tree at /opt/ms-playwright
[setup] all browser shared libraries present
[setup] versions:
  playwright_python: 1.63.0
  python: Python 3.12.15
  browsers_path: /opt/ms-playwright
  chromium_headless_shell_rev: 1243
  chromium_headless_shell_version: Google Chrome for Testing 153.0.8010.12
  chromium_binary_sha256: ded93a9c9a53a1ae040f08124badcca95c938e9d5015ff340c3b5538c41bf39e
  uname: Linux 6.1.175 x86_64
[setup] done

real	1m5.433s
```

Exit code **0**. A cold setup installs the hash-pinned Playwright wheel; the
Chromium tree was already present in this image, so `setup.sh` reused it and
recorded its version and binary hash instead of downloading 115 MB.

## Run 1 — `bash judge/selftest.sh --json /tmp/selftest.json`

```
[selftest] good example
[selftest] good example PASS (11 11 gates)
[selftest] determinism (two runs, same seed)
[selftest] determinism PASS (verdicts identical minus timing/base_url)
[selftest] generating mutants
[selftest] mutants:
  drops_malformed_rows: killed by runs,row_count,no_missing_ok
  dup_rows: killed by row_count,no_dup_rows
  misses_page_2plus: killed by row_count,no_missing_ok
  no_browser_ua: killed by used_browser
  reads_prejs_price: killed by no_missing_ok,malformed_flagged
  scrapes_disallowed_path: killed by no_internal_paths,row_count,no_invented
  unflagged_malformed: killed by malformed_flagged
[selftest] kill rate: 7/7 = 100.0%
[selftest] PASS: good example passes, all 7 mutants killed

real	5m43.358s
```

Exit code **0**. Kill rate **100 %** (7/7); the standard's floor is 90 %.

## Run 1 — `bash judge/grade.sh examples/good/scrape.py --json /tmp/verdict.json`

```
runs               PASS
no_internal_paths  PASS
csv_readable       PASS
row_count          PASS
field_exact        PASS
no_missing_ok      PASS
malformed_flagged  PASS
no_dup_rows        PASS
no_invented        PASS
used_browser       PASS
judge_integrity    PASS
```

Exit code **0**, verdict `"pass": true`, 11/11 gates.
`timing: {"artifact_seconds": 37.796, "total_seconds": 37.841}`.
`requests_seen: {"total": 57, "distinct_paths": 52, "to_disallowed": 0}`.
`truth: {"products": 50, "ok": 47, "malformed": 3, "malformed_skus":
["PROD-0001", "PROD-0014", "PROD-0017"]}`.

## Run 2 — fresh clone, fresh home

| step | command | exit | wall time |
|---|---|---|---|
| setup | `bash judge/setup.sh` | 0 | 1m16.096s |
| selftest | `bash judge/selftest.sh --json /tmp/selftest.json` | 0 | 5m42.906s |
| grade | `bash judge/grade.sh examples/good/scrape.py --json /tmp/verdict.json` | 0 | 38.329s |

Run 2 selftest tail:

```
[selftest] good example PASS (11 11 gates)
[selftest] determinism PASS (verdicts identical minus timing/base_url)
[selftest] kill rate: 7/7 = 100.0%
[selftest] PASS: good example passes, all 7 mutants killed
```

Run 2 grade: verdict `"pass": true`, 11/11 gates,
`timing: {"artifact_seconds": 38.154, "total_seconds": 38.329}`,
`requests_seen: {"total": 57, "distinct_paths": 52, "to_disallowed": 0}`.

## Side by side

| number | run 1 | run 2 |
|---|---|---|
| setup exit / wall | 0 / 1m5.4s | 0 / 1m16.1s |
| selftest exit / wall | 0 / 5m43.4s | 0 / 5m42.9s |
| kill rate | 7/7 = 100 % | 7/7 = 100 % |
| grade exit / verdict | 0 / pass, 11/11 | 0 / pass, 11/11 |
| grade wall | 37.8s | 38.3s |
| requests seen | 57 total, 0 to disallowed | 57 total, 0 to disallowed |
| malformed SKUs | PROD-0001/0014/0017 | PROD-0001/0014/0017 |

Every number matches. The only difference is wall time, which is expected on a
shared 2 vCPU host; `timing` is excluded from the determinism check for that
reason.

## Seed independence

The good example also passes at other seeds, so the oracle is not tuned to one
catalogue:

| seed | grade exit | verdict | malformed SKUs |
|---|---|---|---|
| 20261015 (default) | 0 | pass | PROD-0001, PROD-0014, PROD-0017 |
| 7 | 0 | pass | PROD-0017, PROD-0028, PROD-0047 |
| 999 | 0 | pass | PROD-0007, PROD-0017, PROD-0044 |

## Deviations

- **(not done: media)** `media/` is out of scope for this task by the lead's
  instruction; a later task produces `result.png`, `loop.png`, `demo.mp4`,
  `MANIFEST.json` and `make_media.sh`.
- **(not done: REPRODUCE.md)** independent reproduction by a different agent is
  required before merge (DEMO-STANDARD, Reproducibility); not performed here.
- **(not done: real `run.py` end to end)** this sandbox cannot create sandboxes,
  so `run.py` was verified by `py_compile`, by its `--help`/no-key paths, and by
  running the exact in-sandbox command sequence (`setup.sh` → `selftest.sh` →
  `grade.sh`) from a fresh clone. The lead runs `run.py` against the API.
- `setup.sh` reuses a pre-installed Playwright browser tree when one is present
  (`/opt/ms-playwright` here) and hashes it into `VERSIONS.txt`, rather than
  always downloading the 115 MB archive. On an image without one it downloads
  the pinned zip and checks it against sha256
  `a9da028861a0cf789ff25c2fed45f5f1aaf969ed9247835b6a7821a4f7af9d1d`
  (verified by hand during development).
- The fixture's render script originally ran inline at the end of `<body>`,
  which runs during parsing and left no pre-JS window — the `reads_prejs_price`
  mutant survived. It now runs on the `load` event plus a 150 ms delay. Detail
  pages now carry the same `.product` class so the dedup path is live, and the
  crawl now considers every pager link so the robots gate is a real trap. Gate
  5 (`no_missing_ok`) was tightened from "present" to "present with
  `status=ok`" after the self-test showed the pre-JS mutant surviving it.
