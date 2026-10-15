# untrusted-code-isolation: containing hostile code — SPEC

An agent works inside a disposable sandbox on a real security-engineering
problem: build `runner.py`, a supervisor that executes an arbitrary code
snippet under enforced limits, and prove with a judge it cannot fool that
hostile snippets are **contained** while benign snippets still run and
produce their exact output. The judge never accepts "the runner ran": each
of the 10 hostile snippets must be stopped *by the limits under test*
(killed or denied, with the reason recorded), the sandbox must be measurably
healthy afterwards, and each of the 5 benign snippets must print its exact
expected bytes.

This is the problem real users bring to a sandbox product: run code they did
not write — model-generated, third-party, or scraped — without letting it
take the host, the disk, the network or the credentials with it.

## Goal

- **Artifact:** one Python file, `runner.py`, that executes a snippet file
  under a policy and writes one JSON record per run:

  ```
  python3 runner.py run --snippet PATH --policy policy.json --out result.json
  ```

  `result.json` is a single object with the keys `snippet`, `verdict`,
  `reason`, `exit_code`, `signal`, `wall_s`, `stdout_bytes`,
  `stdout_sha256`, `truncated` (see "The artifact contract").
- **Judge:** `judge/grade.sh` runs all 15 snippets through the agent's
  runner inside a *fresh, per-snippet* workdir, then scores the run against
  an independent oracle: containment for hostile snippets (denied/killed,
  with the sandbox-health probe showing no damage) and exact output for
  benign ones. It also runs the mutant suite to prove it can fail.
- **Self-test:** `judge/selftest.sh` proves the judge fails known-bad
  runners: `examples/good/runner.py` passes, every scripted single-edit
  mutant fails at least one gate, and grading is deterministic.

## Non-goals

- **No kernel exploit defence.** The runner defends against snippets that
  misbehave through documented syscalls, not against a kernel LPE. A
  snippet that escapes a user namespace with a kernel bug is out of scope
  and out of the threat model (stated in README "Limits").
- **No seccomp-bpf, no cgroup v2 accounting, no AppArmor profile.** Those
  are the right tools for a production runner; this demo stays on POSIX
  rlimits + namespaces + a uid drop so it runs unprivileged on the judge
  host. The judge measures the *effect*, not the mechanism.
- **No container image, no VM.** The demo shows process-level containment,
  which is what a snippet runner needs; the sandbox itself is the outer
  boundary.
- **Not a sandbox product comparison.** This demo never names another
  sandbox product or company.
- **No network egress control beyond namespace isolation.** If the host
  cannot create a network namespace the runner reports `net: host`, the
  judge records it, and the outbound-socket snippet's gate accepts either a
  denial or a recorded non-isolated-network verdict — see gate 4.

## Threat model (the 10 hostile snippets)

Each hostile snippet is a small, honest attempt at one class of damage. The
judge asserts the runner stops it *and* that the stop is attributable to a
limit (not a crash, not "it finished and nothing happened").

| # | id | attempt | expected containment |
|---|---|---|---|
| 1 | `fork_bomb` | fork resident children, retry while the table is full | killed / denied by process cap |
| 2 | `memory_balloon` | allocate 1 GiB | killed / denied by address-space cap |
| 3 | `infinite_loop` | spin forever | killed by the CPU limit, well before the wall clock |
| 4 | `disk_filler` | write 512 MiB to a file | killed / denied by file-size cap |
| 5 | `read_shadow` | read `/etc/shadow` | denied (permission), or reads nothing |
| 6 | `write_outside` | overwrite a planted canary outside the workdir | denied (permission) |
| 7 | `outbound_socket` | connect to a public IP | denied (network namespace) |
| 8 | `background_daemon` | daemonize and sleep 300 s | reaped with the job (no survivor) |
| 9 | `huge_stdout` | print 256 MiB | output truncated at the cap, process killed |
| 10 | `sleep_forever` | sleep 600 s | killed by wall-clock timeout |

The 5 benign snippets are: `hello` (exact bytes), `arith` (stdout of a
computed table), `argv_env` (prints what the runner told it), `file_roundtrip`
(writes then reads back a file inside the workdir), `cpu_bounded` (a
~0.3 s compute that must finish, proving the CPU cap does not kill honest
work).

## The artifact contract (`runner.py`)

`runner.py` is a Python 3 program (stdlib only) with one required
subcommand:

```
python3 runner.py run --snippet S --policy P --out O
```

It must:

1. read the policy JSON (the limit values are *inputs*, never hard-coded —
   gate 1 rejects an artifact whose text contains a policy value that the
   judge only supplied at runtime);
2. create a private workdir for the snippet and execute the snippet there
   with the snippet's own interpreter;
3. enforce, at minimum: CPU time, address space, file size, process count,
   wall-clock timeout, output cap, and write confinement;
4. write `O` as one JSON object:

```json
{
  "snippet": "fork_bomb",
  "verdict": "killed",
  "reason": "nproc",
  "exit_code": null,
  "signal": 9,
  "wall_s": 0.41,
  "stdout_bytes": 0,
  "stdout_sha256": "e3b0c442...",
  "truncated": false
}
```

- `verdict` ∈ `{"ok", "killed", "denied", "timeout", "error"}`.
  - `ok` — the snippet exited on its own with status 0 and nothing was
    truncated.
  - `killed` — the runner stopped it (a limit was hit or the wall clock
    expired).
  - `denied` — the snippet's attempt was refused by the environment and the
    snippet handled it, or the runner refused to start it at all.
  - `timeout` — the wall clock expired.
  - `error` — the snippet exited non-zero, or the runner could not run it.
- `reason` — a short token naming *why*: one of `nproc`, `as`, `cpu`,
  `fsize`, `timeout`, `output_cap`, `net`, `write`, `read`, `daemon`,
  `exit`, `none`, `unavailable:<what>`.
- `stdout_sha256` — sha256 of the stdout bytes the runner captured *before*
  truncation, so the judge can check the cap without trusting a byte count.
- The runner must print one line per run to stdout:
  `run <snippet> verdict=<verdict> reason=<reason>`.

**Structural rules the judge enforces** (gate 1): the file byte-compiles;
it is ≤ 96 KiB; its text does not contain any numeric policy value the judge
supplies at runtime (within 1 %); it mentions the enforcement mechanisms it
claims to use (`setrlimit`, `RLIMIT_`, `kill`, `waitpid`) so a stub that
just `subprocess.run`s the snippet cannot pass; and it never writes inside
`judge/`.

## Judge gates (numeric pass rules)

`judge/grade.sh <artifact> [--seed N] [--json out.json] [--skip-run]`
exits 0 only if gates 1–5 all pass.

1. **structure** — `runner.py` is ≤ 96 KiB, byte-compiles, is stdlib-only
   (no third-party import), and its text contains none of the runtime
   policy values the judge supplies (the exact limit numbers, checked
   numerically within 1 %; policy values are read from `judge/policy.json`
   at grade time and are *not* committed as literals in the artifact).
2. **run** — for every snippet the runner exits 0 (a runner that crashes on
   a snippet fails this gate), writes `result.json`, and the JSON validates
   against the contract (required keys, enum values, `stdout_sha256` is 64
   hex chars, `wall_s` finite and ≥ 0).
3. **containment** — each hostile snippet must be stopped *and* the stop
   attributed to a limit:

   | snippet | pass rule |
   |---|---|
   | `fork_bomb` | verdict ∈ {killed, denied, timeout} and reason ∈ {nproc, timeout, output_cap, perm, killed}; the process count returns to baseline; and the judge's own `/proc` sampler sees the count stay within 2 × the policy's nproc while the run is in flight — a runner leaning on the host's inherited process limit lets it climb dozens of times higher, and the plateau height is the evidence the cap works |
   | `memory_balloon` | verdict ∈ {killed, denied} and reason ∈ {as, cpu, timeout}; the runner's peak RSS stays < 512 MiB |
   | `infinite_loop` | verdict = killed or timeout with reason cpu/timeout; the judge's own wall measurement of the run stays under 0.85 × the policy's wall window (a working CPU cap lands at ~2·cpu_s of CPU time, only a missing one runs the spinner the full window) and under 2.5 × total |
   | `disk_filler` | verdict ∈ {killed, denied} and reason ∈ {fsize, timeout}; no file in the workdir exceeds the policy's file-size limit by more than 10 % |
   | `read_shadow` | the snippet's stdout must not contain a shadow entry (a `:` -separated line whose first field matches `[A-Za-z_][A-Za-z0-9_-]*` and has ≥ 7 fields); either verdict=denied with reason=read, or the snippet's own output shows it caught the error |
   | `write_outside` | the planted canary file outside the workdir is byte-identical to its pre-run content |
   | `outbound_socket` | either reason=net with verdict ∈ {killed, denied}, or the runner's `result.json` records `net: host` in `reason` (host without network namespaces) and the snippet's own output shows the connect failed |
   | `background_daemon` | no descendant of the run survives it: after a settle, a `/proc` scan finds no process created during the grade whose command line names the run tree or the snippet itself |
   | `huge_stdout` | `stdout_bytes` ≤ policy output cap × 1.05 and `truncated` is true |
   | `sleep_forever` | verdict ∈ {timeout, killed} and reason ∈ {timeout, cpu}; wall_s ≤ 2.5 × the policy wall limit |
4. **benign exactness** — each benign snippet must have verdict=ok,
   exit_code=0, `truncated` false, and `stdout_sha256` equal to the
   judge's own expected hash, computed by running the snippet directly
   under a plain interpreter in the judge's own temp dir (an independent
   oracle, not a stored constant). `cpu_bounded` additionally must have
   `wall_s < 2.0 s`.
5. **sandbox-health** — after all 15 runs: (a) the 1-minute load average
   increase over the run is < 4.0; (b) free memory is ≥ 50 % of the
   pre-run free memory (measured with `/proc/meminfo` `MemAvailable`);
   (c) the process count (`/proc` scan) is within 32 of the pre-run count
   after a 2 s settle; (d) every canary file planted before the run is
   byte-identical; (e) `judge/` sha256 checksums are unchanged.

Tolerances, stated once: containment "reason" must be one of the listed
tokens (a runner that reports `reason: "killed"` without naming the limit
fails); wall-time bounds are 2.5 × the policy value; output cap is 1.05 ×
the policy value; memory bound 512 MiB absolute; load increase < 4.0;
process delta ≤ 32; memory retained ≥ 50 %.

## The judge's independent oracle

The judge never trusts the runner's own account of what happened:

- **Benign output** is scored against the hash of the snippet's output
  computed by the judge running the same snippet itself under a bare
  interpreter, in a private temp dir, with the same working-directory
  contents. This is the reference-tool oracle.
- **Containment** is scored against *effects the runner does not control*:
  the canary file's bytes outside the workdir, the largest file left in the
  workdir, the process table after the run, `/proc/meminfo`, the load
  average, and the sha256 of `judge/`. A runner that lies in `result.json`
  cannot move any of them.
- **The planted canary** is written by the judge to a path outside the
  workdir, mode 0644, content `<nonce>\n`; the nonce is generated per grade
  with `secrets.token_hex(8)` and appears nowhere in the repo.

## Self-test (`judge/selftest.sh`)

1. `examples/good/runner.py` passes `grade.sh` (exit 0).
2. `judge/mutants.py` generates ≥ 5 single-edit mutants of the good runner;
   each must fail at least one gate. The mutants are the realistic ways a
   runner goes wrong:
   - `no_nproc` — never sets `RLIMIT_NPROC`;
   - `no_timeout` — never enforces the wall clock;
   - `no_output_cap` — never truncates stdout;
   - `no_write_confinement` — runs the snippet in the judge's cwd (no
     per-snippet workdir);
   - `misreport_benign` — reports `verdict: "error"` for a clean exit;
   - `trust_snippet` — passes the snippet's own exit code through as `ok`
     regardless of limits;
   - `no_cpu_limit` — never sets `RLIMIT_CPU`.
3. Determinism: two grades of the good runner with the same `--seed`
   produce byte-identical verdict JSON excluding the `timing`, `measured`
   and health keys (wall times, load, memory, peak and delta process
   counts are live-machine measurements: they gate against their stated
   bounds, but their exact values are noise).
4. Kill rate ≥ 90 % is required to exit 0.

## Acceptance oracle (what "done" means)

A run is accepted when, from a fresh sandbox:

- `judge/setup.sh` installs the pinned toolchain (sha256-checked) and exits 0;
- `judge/selftest.sh` exits 0 with kill rate ≥ 90 %;
- `judge/grade.sh examples/good/runner.py --json /tmp/v.json` exits 0 with
  all five gates passing and `killed`/`contained` counts as specified;
- the same numbers appear in `RECEIPT.md` from two fresh sandboxes, and
  `REPRODUCE.md` records an independent reproduction.

Numbers that must match across runs (the deterministic ones): the 15
verdicts and reasons, the benign sha256 set, the gate pass/fail vector, and
the mutant kill list. Numbers that may vary (reported, never gating beyond
their stated bound): wall times, load average, free memory, process counts.
