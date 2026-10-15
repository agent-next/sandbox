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

at commit `c07e80b` on branch `sbx/demo-untrusted-code-isolation-f5`,
2026-10-15. Both exited **0** with `untrusted-code-isolation demo: PASS`.

## Side by side

| | run 1 | run 2 |
|---|---|---|
| sandbox id | `01a140e3-e07f-71d3-a24b-e2008f7afe87` | `01a140ec-…` (see run.py log) |
| create | ok (5 s) | ok (5 s) |
| clone `--depth 1 -b sbx/demo-untrusted-code-isolation-f5` | exit 0 (20 s) | exit 0 (22 s) |
| setup.sh | exit 0 (25 s) | exit 0 (26 s) |
| selftest.sh | exit 0 (748 s) | exit 0 (749 s) |
| grade.sh known-good | exit 0 (56 s) | exit 0 (57 s) |
| **total wall** | **885 s** | **885 s** |
| kill rate | **10/10 = 100 %** | **10/10 = 100 %** |
| determinism check | OK | OK |
| verdict | PASS (all 5 gates) | PASS (all 5 gates) |
| run.py exit code | 0 | 0 |
| cleanup | killed, confirmed gone via `sbx list` | killed, confirmed gone |

## Verdict numbers (deterministic set — identical in both runs)

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
  `no_nproc_limit`→containment/fork_bomb, `no_fsize_limit`→containment/disk_filler,
  `no_as_limit`→containment/memory_balloon, `no_timeout`→run+health,
  `no_output_cap`→containment/huge_stdout, `no_uid_drop`→containment+health,
  `trust_snippet`→containment, `misreport_benign`→benign+containment,
  `widen_limits`→containment (run 2 additionally tripped health).

## Measured effects (reported, never gated; run-to-run noise expected)

| measurement | run 1 | run 2 | bound |
|---|---|---|---|
| fork bomb peak process delta | 66 | 66 | ≤ 128 (2 × nproc) |
| memory balloon peak RSS | 8.6 MiB | 8.7 MiB | < 512 MiB |
| infinite_loop judge wall | 4.33 s | 4.44 s | < 17 s (0.85 × wall) |
| largest file left in workdir | 4194304 B | 4194304 B | ≤ 4.61 MiB (1.10 × fsize) |
| huge_stdout captured | 1048576 B | 1048576 B | ≤ 1.05 MiB (1.05 × cap) |
| sleep_forever runner wall | 20.10 s | 20.09 s | ≤ 50 s (2.5 × wall) |
| health: load increase | −0.00 | −1.09 | < 4.0 |
| health: memory retained | 1.001 | 1.000 | ≥ 0.50 |
| health: process delta | 0 | 0 | ≤ 32 |
| canary intact / net accepted / survivors | yes / 0 / 0 | yes / 0 / 0 | required |

The balloon's tiny peak RSS is the point: `RLIMIT_AS` (256 MiB) makes the
1 GiB allocation fail inside `bytearray(…)` before a page is faulted, so
the process never grows — the address-space cap fired, not the host's
OOM killer (that distinction is the gate; see SPEC).

## Tool versions (judge/VERSIONS.txt, recorded by setup.sh in the run sandbox)

```
python 3.12.15 (venv at ~/.venvs/untrusted-code-isolation, stdlib-only judge)
unshare from util-linux 2.38.1 (/usr/bin/unshare)
sudo 1.9.13p3 (passwordless; the sudo-userns rung)
kernel 6.1.175
user-namespaces-max 15734
judge-packages: pip==25.0.1   (no third-party packages; judge/requirements.txt)
```

## run.py output tail (run 1, verbatim)

```
  [grade] finished: exit 0 (56 s)
artifacts: step logs saved to /tmp/uci-run1
  [kill] sbx kill 01a140e3-e07f-71d3-a24b-e2008f7afe87 ... ok (3 s)
  [list] sbx list ... ok (1 s)
cleanup: sandbox 01a140e3-e07f-71d3-a24b-e2008f7afe87 killed and confirmed gone
total: 885 s

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

- **An earlier acceptance run of this demo failed on transport, not on
  the judge**: `sbx exec` held one long-lived stream for the ~12-minute
  self-test, a gateway restart dropped it (`ConnectError: Error reading
  content` at 104 s), and the follow-up `sbx kill`/`sbx list` hit the
  same restart (503 `gateway is restarting`) — after which run.py still
  printed "killed and confirmed gone" without a confirmation to point
  at. Both runs above are from the rewritten driver: each step runs
  detached in the sandbox and is watched with short, retried exec polls;
  cleanup only prints "confirmed gone" after a successful `sbx list`
  shows the id absent (DEMO-STANDARD.md; the receipt runs exercised this
  path, one restart blip was absorbed mid-run at no cost).
- The self-test's first execution on 2026-10-15 showed kill rate 9/10:
  the sandbox's own OOM killer stopped the memory balloon for the
  `no_as_limit` mutant, and the gate accepted a generic `killed`/`cpu`
  attribution. The gate now requires the address-space token (`as`),
  exactly as SPEC.md always stated; both receipt runs kill 10/10.
- Wall times vary with the shared host (the two runs above ran
  concurrently on separate sandboxes); the deterministic set — the 15
  verdicts and reasons, the gate vector, the benign sha256 set, the
  mutant kill list, effect booleans, capped byte counts and
  `judge_intact` — is byte-identical between the two runs when compared
  with the self-test's own scrub (drops `timing`, `measured`, the health
  gate and per-run `wall_s`).
- `VERSIONS.txt` is written inside the run sandbox by `setup.sh` and
  fetched by `run.py --artifacts`; the copy quoted above was captured
  from an additional one-shot sandbox at the same commit
  (`01a140fd-9c1e-7f82-b38d-65c90123c673`, killed after the read).
