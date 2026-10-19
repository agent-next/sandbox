# RECEIPT: two fresh sandbox runs

Both runs below are complete, independent executions of the one-command
run from nothing (no pre-warmed sandbox, `setup.sh` built the judge venv
from scratch in each):

```
export SBX_API_KEY=<your key>
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
python3 cookbook/untrusted-code-isolation/run.py \
    --ref sbx/demo-untrusted-code-isolation-f5
```

at commit `f767ccf` on branch `sbx/demo-untrusted-code-isolation-f5`,
2026-10-15. Both exited **0** with `untrusted-code-isolation demo: PASS`.

## Side by side

| | run 1 | run 2 |
|---|---|---|
| sandbox id | `01a14125-ef0d-7c62-86f0-494853054926` | `01a14136-3223-7fa0-82ef-9695d4741817` |
| create | ok (5 s) | ok (4 s) |
| clone `--depth 1 -b sbx/demo-untrusted-code-isolation-f5` | exit 0 (26 s) | exit 0 (23 s) |
| setup.sh | exit 0 (47 s) | exit 0 (23 s) |
| selftest.sh | exit 0 (821 s) | exit 0 (792 s) |
| grade.sh known-good | exit 0 (63 s) | exit 0 (61 s) |
| **total wall** | **1006 s** | **947 s** |
| kill rate | **10/10 = 100 %** | **10/10 = 100 %** |
| determinism check | OK | OK |
| verdict | PASS (all 5 gates) | PASS (all 5 gates) |
| run.py exit code | 0 | 0 |
| cleanup | killed, confirmed gone via `sbx list` | killed, confirmed gone |

## Verdict numbers (deterministic set — identical in both runs)

The two runs' verdict JSON is byte-identical after the self-test's own
scrub (drops `timing`, `measured`, the health gate and per-run `wall_s`;
verified with `python3` on both `--artifacts` verdict files).

| hostile snippet | verdict | reason |
|---|---|---|
| fork_bomb | denied | nproc |
| memory_balloon | denied | as |
| infinite_loop | killed | cpu |
| disk_filler | denied | fsize |
| read_shadow | denied | perm |
| write_outside | denied | perm |
| outbound_socket | ok | none |
| background_daemon | ok | none |
| huge_stdout | killed | output_cap |
| sleep_forever | timeout | timeout |

- containment 10/10, benign 5/5 exact, health pass, judge checksums
  unchanged (`judge_intact: true` in both).
- benign stdout sha256 (identical in both runs; produced by the judge's
  own reference run, not stored): `hello 4b5f9b4a3c3c…`,
  `arith 1970205415bf…`, `argv_env 36a2eb1da71c…`,
  `file_roundtrip 4b5b424d27d6…`, `cpu_bounded 3f2766b7f41b…`.
- mutant kill list (same ten mutants killed by the same primary gates in
  both runs): `no_cpu_limit`→containment/infinite_loop,
  `no_nproc_limit`→containment/fork_bomb,
  `no_fsize_limit`→containment/disk_filler,
  `no_as_limit`→containment/memory_balloon, `no_timeout`→run+health,
  `no_output_cap`→containment/huge_stdout,
  `no_uid_drop`→containment+health, `trust_snippet`→containment,
  `misreport_benign`→benign+containment,
  `widen_limits`→containment.

## Measured effects (reported, never gated; run-to-run noise expected)

| measurement | run 1 | run 2 | bound |
|---|---|---|---|
| fork bomb peak process delta | 66 | 66 | ≤ 128 (2 × nproc) |
| memory balloon peak RSS | 8.6 MiB | 8.7 MiB | < 512 MiB |
| infinite_loop judge wall | 5.86 s | 5.93 s | < 17 s (0.85 × wall) |
| largest file left in workdir | 4194304 B | 4194304 B | ≤ 4.61 MiB (1.10 × fsize) |
| huge_stdout captured | 1048576 B | 1048576 B | ≤ 1.05 MiB (1.05 × cap) |
| sleep_forever runner wall | 20.09 s | 20.06 s | ≤ 50 s (2.5 × wall) |
| health: load increase | 0.17 | 0.07 | < 4.0 |
| health: memory retained | 0.998 | 0.999 | ≥ 0.50 |
| health: process delta | 0 | 0 | ≤ 32 |
| canary intact / net accepted / survivors | yes / 0 / 0 | yes / 0 / 0 | required |

The balloon's tiny peak RSS is the point: `RLIMIT_AS` (256 MiB) makes the
1 GiB allocation fail inside `bytearray(…)` before a page is faulted, so
the process never grows — the address-space cap fired, not the host's
OOM killer (that distinction is the gate; see SPEC).

## Tool versions (judge/VERSIONS.txt, recorded by setup.sh in run 1's sandbox)

```
## python 3.12.15
## unshare unshare from util-linux 2.38.1
## unshare path /usr/bin/unshare
## sudo 1.9.13p3
## kernel 6.1.175
## user-namespaces-max 15734
## judge-packages
pip==25.0.1
```

Run 2's `VERSIONS.txt` (fetched by `--artifacts`, in `/tmp/uci-run2`)
records the same toolchain.

## run.py output tail (run 1, verbatim)

```
  [grade] finished: exit 0 (63 s)
artifacts: step logs and VERSIONS.txt saved to /tmp/uci-run1
  [kill] sbx kill 01a14125-ef0d-7c62-86f0-494853054926 ... ok (5 s)
  [list] sbx list ... ok (3 s)
cleanup: sandbox 01a14125-ef0d-7c62-86f0-494853054926 killed and confirmed gone
total: 1006 s

untrusted-code-isolation demo: PASS
  gate benign: pass  (5/5 benign exact)
  gate containment: pass  (10/10 hostile contained)
  gate health: pass
  gate run: pass
  gate structure: pass
  hostile verdicts:
    fork_bomb          denied   nproc        ok
    memory_balloon     denied   as           ok
    infinite_loop      killed   cpu          ok
    disk_filler        denied   fsize        ok
    read_shadow        denied   perm         ok
    write_outside      denied   perm         ok
    outbound_socket    ok       none         ok
    background_daemon  ok       none         ok
    huge_stdout        killed   output_cap   ok
    sleep_forever      timeout  timeout      ok
```

## Deviations

- **The first lead-acceptance attempt of 2026-10-15 failed on transport,
  not on the judge** (`ConnectError: Error reading content` at 104 s of
  the self-test, then 503 `gateway is restarting` on the follow-up
  kill/list): the driver retried gateway restarts only when the marker
  text arrived on stderr, and the CLI prints some transport errors on
  stdout. The driver now searches both streams for the transient markers
  (`ConnectError`, 503 restart, resets, SSL), captures output on every
  call so the check can see it, treats a transport-garbled kill as an
  unconfirmed kill, and appends to (instead of truncating) each step's
  status file, failing a poll that finds more than one line. Both runs
  above are from the fixed driver; the self-test has run to completion
  three times today (the two runs above plus the determinism grades
  inside each self-test), all through the same polling path with no
  lost step.
- The self-test's first execution on 2026-10-15 showed kill rate 9/10:
  the sandbox's own OOM killer stopped the memory balloon for the
  `no_as_limit` mutant, and the gate accepted a generic `killed`/`cpu`
  attribution. The gate now requires the address-space token (`as`),
  exactly as SPEC.md always stated; both receipt runs kill 10/10.
- Wall times vary with the shared host; the deterministic set — the 15
  verdicts and reasons, the gate vector, the benign sha256 set, the
  mutant kill list, effect booleans, capped byte counts and
  `judge_intact` — is byte-identical between the two runs (checked with
  the self-test's own scrub).
- `VERSIONS.txt` is written inside the run sandbox by `setup.sh` and
  fetched by `run.py --artifacts`; the copy quoted above is run 1's,
  fetched before its sandbox was killed.
- `media/result.png` was regenerated from run 1's `verdict.json` by
  `media/figures.py /tmp/uci-run1 stills` (same command
  `make_media.sh` runs); its sha256 in `media/MANIFEST.json` matches the
  committed file. `demo.mp4` and `loop.png` are from the same pipeline
  at the previous receipt run; their manifest hashes match the committed
  files.
