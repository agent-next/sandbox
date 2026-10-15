# Untrusted code isolation: 10 hostile snippets, one runner, a judge that reads the process table

An agent works on a real security-engineering problem inside a disposable
sandbox: build `runner.py`, a supervisor that executes a code snippet it
did not write under enforced limits — CPU, address space, file size,
process count, wall clock, output cap, write confinement, an isolated uid
and (where the host allows) mount/network/PID namespaces — and prove with
a judge it cannot fool that each of 10 genuinely hostile snippets (fork
bomb, memory balloon, CPU spinner, disk filler, `/etc/shadow` read,
write outside the workdir, outbound socket, background daemon, 256 MiB
stdout flood, eternal sleep) is stopped *by a limit it can name*, while
5 benign snippets still print their exact bytes. The judge never accepts
"the runner ran": containment is scored from effects the runner does not
control — a planted canary outside the workdir, the judge's own TCP
probe, the largest file left behind, a process-count sampler during the
fork bomb, the process table and `/proc/meminfo` afterwards — and benign
output is scored against the judge running the same snippets itself.

A sandbox helps twice over: the hostile snippets are real, so the whole
loop belongs in a disposable box, and the runner-under-test is graded
from a copy with `judge/` checksummed before and after, so the code
being judged cannot tamper with its own referee.

## One-command run

From this repository's root, with Python 3.10+ and the `sbx` CLI
(`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and `SBX_API_KEY` exported:

```bash
python3 cookbook/untrusted-code-isolation/run.py                     # fresh sandbox end-to-end
python3 cookbook/untrusted-code-isolation/run.py --ref sbx/demo-untrusted-code-isolation
python3 cookbook/untrusted-code-isolation/run.py --keep              # leave it up to explore
```

Each run prints wall time per step (create, clone, setup, selftest,
grade), the verdict JSON, and a short human summary, then kills the
sandbox and confirms it is gone. Measured on a 2 vCPU / ~3 GB sandbox
(see RECEIPT.md, two runs at commit `c07e80b`): create ~5 s, clone
~20–22 s, setup ~25 s (venv + sha256-checked `unshare` fallback),
selftest ~12.5 min (13 grades: the good runner, 10 mutants, 2
determinism runs), grade ~1 min, total ~885 s. A single grade is ~1 min
because containment is not fast-forwarded: the wall-clock snippets really
wait out their policy window so the judge can measure what actually
happened.

The gateway restarts under load and a long-lived `sbx exec` stream is
the casualty; the driver therefore runs every step detached in the
sandbox and polls it with short, retried exec calls, so a restart costs
one retry, not the run. Cleanup reports a sandbox gone only when
`sbx list` actually answers with the id absent — a failed kill or an
unreadable list is a non-zero exit naming the id.

To try the judge locally on a Linux box you control (a VM, not your
laptop — the snippets are hostile):

```bash
bash cookbook/untrusted-code-isolation/judge/setup.sh      # stdlib-only judge venv; records VERSIONS.txt
bash cookbook/untrusted-code-isolation/judge/selftest.sh   # known-good passes, 10/10 mutants killed
bash cookbook/untrusted-code-isolation/judge/grade.sh cookbook/untrusted-code-isolation/examples/good/runner.py --json /tmp/v.json
```

## The 15 snippets and what must happen to them

| hostile snippet | attempt | containment the judge requires |
|---|---|---|
| `fork_bomb` | fork resident children, retry while the table is full | denied/killed/timeout by the process cap; the judge's own `/proc` sampler sees ≤ 2× the policy cap processes during the run |
| `memory_balloon` | allocate 1 GiB | killed/denied by the address-space cap; peak RSS < 512 MiB |
| `infinite_loop` | spin a core forever | killed before 0.85 × the wall window (a working CPU cap lands at ~2–4 s; only a missing one runs the spinner to the wall clock) |
| `disk_filler` | write 512 MiB | killed/denied by the file-size cap; no file in the workdir exceeds 1.1 × the cap |
| `read_shadow` | read `/etc/shadow` | no shadow entry in stdout (uid drop / namespace denies it) |
| `write_outside` | append to a planted canary outside the workdir | the canary is byte-identical afterwards |
| `outbound_socket` | connect to the judge's probe and a public IP | no connection reaches the judge's listener |
| `background_daemon` | setsid + sleep 300 s | nothing from the run survives it |
| `huge_stdout` | print 256 MiB | stdout truncated at ≤ 1.05 × the 1 MiB cap, `truncated: true` |
| `sleep_forever` | sleep 600 s | killed by the wall clock within 2.5 × the window |

The 5 benign snippets (`hello`, `arith`, `argv_env`, `file_roundtrip`,
`cpu_bounded`) must exit 0 with verdict `ok`, untruncated, and a stdout
sha256 equal to what the judge itself gets running the same snippet
under a bare interpreter — `cpu_bounded` also under 2 s, proving the CPU
cap does not kill honest work.

## Ask your agent

With the sandbox plugin installed, paste this prompt. The agent designs
the containment runner itself in a sandbox and iterates with the judge
until it passes — that loop is the demo:

> Create a fresh sandbox. Inside it, clone
> https://github.com/agent-next/sandbox at ref `main`, then read
> `cookbook/untrusted-code-isolation/SPEC.md` carefully: you are to write
> `runner.py`, a supervisor that runs one untrusted code snippet under
> enforced limits and writes one JSON verdict record per run
> (`run --snippet S --policy P --out O`, contract in the spec). The limit
> values arrive in `judge/policy.json` at run time; hard-coding any of
> them in your file is rejected by gate 1. Your runner must contain the
> 10 hostile snippets in `judge/snippets/hostile/` by killing or denying
> them with a named limit, and run the 5 benign ones in
> `judge/snippets/benign/` to their exact output. First run
> `cookbook/untrusted-code-isolation/judge/setup.sh`, then write your
> runner in the sandbox, then iterate: `bash
> cookbook/untrusted-code-isolation/judge/grade.sh /path/to/your/runner.py
> --json /tmp/v.json` and read the verdict JSON until all five gates
> pass (structure, run, containment, benign, health). Run
> `cookbook/untrusted-code-isolation/judge/selftest.sh` once to watch the
> judge kill 10 broken mutants of a reference runner. The judge scores
> you on effects you do not control — a canary file, its own TCP probe,
> the process table, the largest file left behind — so a verdict you
> print that the sandbox contradicts fails. When every gate passes,
> report the verdict JSON (the 10 verdict/reason pairs, the benign
> hashes matched, the health numbers), then kill the sandbox and confirm
> it is gone. If you cannot get a gate to pass, say exactly which gate
> and what you tried, and stop.

## What the judge checks (short form)

| gate | rule |
|---|---|
| structure | ≤ 96 KiB, byte-compiles, stdlib-only, mentions its enforcement mechanisms, contains no policy value supplied at run time (checked within 1 %) |
| run | every one of the 15 snippets produces a contract-shaped JSON record and the runner exits 0 |
| containment | each hostile snippet stopped and the stop attributed to a named limit; effects measured by the judge (canary, probe, files, process table, peak process count) |
| benign | verdict `ok`, exit 0, untruncated, stdout sha256 = the judge's own run of the snippet; `cpu_bounded` < 2 s |
| health | after all 15: load rise < 4.0, ≥ 50 % memory retained, process count within ±32, canaries intact, `judge/` checksums unchanged |

The artifact is graded from a copy in a temp dir; `judge/` is checksummed
before and after. `judge/selftest.sh` grades 10 scripted single-edit
mutants (no CPU/as/fsize/nproc/timeout/output-cap limits, no uid drop,
trust-the-snippet, misreport-benign, widened limits) and a determinism
check — two grades of the good runner give byte-identical verdicts except
measured timings; kill rate must be ≥ 90 % (it is 10/10).

## Media

`media/` holds the figures and the short video, all regenerated from
real judge outputs by `media/make_media.sh ARTIFACTS_DIR` (needs
python3 + matplotlib and ffmpeg at generation time; the demo itself is
stdlib-only):

- `media/result.png` — each numerically bounded hostile snippet's
  measured effect against the judge's bound (pass line at 1.0), plus the
  four binary effect gates.
- `media/loop.png` — the self-test: 10/10 mutants killed against the
  required 90 % line, next to the five gate results.
- `media/demo.mp4` — 29.5 s, 1920×1080 at 30 fps, H.264; a step-through
  of the figures above (the physics here is not time-dependent).
- `media/MANIFEST.json` — what each file shows, the command that
  produced it, its source data, and its sha256.

Every plotted number is read from `run.py --artifacts` output
(`verdict.json`, `selftest.log`) and `judge/policy.json`; nothing is
hand-drawn.

## Limits, stated plainly

- **Not kernel-exploit defence.** The runner defends against snippets
  that misbehave through documented syscalls. A kernel LPE out of a user
  namespace is out of scope (SPEC.md, Non-goals).
- **No seccomp-bpf, cgroup v2 or AppArmor.** Those are production tools;
  this demo stays on POSIX rlimits + namespaces + a uid drop so the judge
  runs unprivileged. The judge measures the effect, not the mechanism.
- **Isolation ladder, reported per run.** `sudo-userns` (namespaces +
  uid drop) when passwordless sudo exists, `rootless-userns` (mounts
  read-only above the workdir, reads not confined — the record says so)
  when unprivileged user namespaces are allowed, else `none`, in which
  case reasons carry a `:host` suffix rather than implying confinement
  that did not happen. On a host without network namespaces the
  outbound-socket gate accepts a recorded non-isolated network.
- **The judge runs on x86-64 Linux, CPython 3.10–3.13**, the sandbox
  image's `sudo`/`unshare` are recorded in `judge/VERSIONS.txt`.
- **The snippets are sized for a 2 vCPU / ~3 GB box** (512 MiB fill, 1 GiB
  balloon attempt, 256 MiB stdout) so each grade finishes in ~1 minute,
  not hours; they are still genuinely hostile to an unconfined runner.
