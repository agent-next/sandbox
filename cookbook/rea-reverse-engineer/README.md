# Reverse-engineer anything — REA × stripped binaries × a judge that can't be fooled

A disposable agent-next sandbox installs a pinned, sha256-checked REA
(**Reverse Engineer Anything**, [morluto/rea](https://github.com/morluto/rea),
MIT, ~241k stars) — the `rea-agents` 3.1.0 npm CLI backed by Ghidra 12.1.2 —
and an agent must explain three small **stripped** ELF binaries it has never
seen: a custom 64-bit checksum, a byte-protocol parser, and a licence-key
checker with a hidden rule. A judge it cannot fool decides whether the
explanation is right: every claimed function address must fall inside a real
function from the unstripped symbol table, every Python re-implementation
must match the real binary byte for byte on 500 random inputs, the generated
licence key must be accepted by the real `keycheck` binary, and the REA
evidence files must carry the binary's own sha256. A sandbox helps because
the toolchain is heavy (~700 MB of JDK + Ghidra), the work is messy
(analysis databases, scratch disassembly), and the whole point is to throw it
away afterwards.

The artifact under test is a directory with one sub-directory per target:
a `report.json` (recovered algorithm + function roles + addresses), a
`reimpl.py`, and the REA Evidence JSON files the analysis actually produced.
Gates and thresholds are in [SPEC.md](SPEC.md); real command output is in
[RECEIPT.md](RECEIPT.md).

## Results

- All **21/21 gates pass** on the known-good artifact (seed 20261014, 500
  inputs per target, byte-exact).
- Self-test kills **7/7 known-bad mutants** (100 %; floor is 90 %): off-by-one
  rotate, reversed payload weights, wrong key, phantom function, missing
  target, faked evidence sha256, moved core address.
- Keycheck: the recovered hidden rule (three modular constraints on the
  32-symbol alphabet) yields key `AAAAA-KAYAA-AAAAY`, which the real binary
  accepts (`OK`, exit 0).

## Ask your agent

> Create a CPU sandbox (2 vCPU, ~4 GB RAM). In it, clone
> https://github.com/agent-next/sandbox and run
> `bash cookbook/rea-reverse-engineer/judge/setup.sh` to install the pinned
> REA toolchain (rea-agents 3.1.0 + Ghidra 12.1.2) and build the three
> stripped target binaries in `cookbook/rea-reverse-engineer/targets/`
> (do not look inside `cookbook/rea-reverse-engineer/judge/ground_truth/` —
> that is the judge's answer key; work only from the binaries). Then source
> `env.sh` and use the `rea` CLI (analyze / function / decompile) to work
> out, for each of the three binaries, what it does. Produce, in a directory
> of your own, one sub-directory per target containing: `report.json`
> (schema `rea-demo/report/1` — see SPEC.md), a `reimpl.py` that reproduces
> the binary's stdin→stdout behaviour exactly, and the REA evidence JSON
> files you produced; for `keycheck` also a `key.txt` with a key the binary
> accepts. Iterate with
> `bash cookbook/rea-reverse-engineer/judge/grade.sh <your-dir> --seed 20261014`
> until every gate passes. Report the final verdict JSON and kill the sandbox
> when done.

## One-command run (with sandbox API)

```bash
export SBX_API_KEY=<your key>
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
python3 cookbook/rea-reverse-engineer/run.py          # add --ref <branch> or --keep
```

`run.py` creates a sandbox, clones this repo at `--ref` (default `main`),
runs `judge/setup.sh`, `judge/selftest.sh`, then grades the known-good
artifact, prints the verdict JSON, and kills the sandbox (verifying it is
gone) unless `--keep` is given.

## In-sandbox / no API key (run directly inside any Debian 12 box)

If you already have a Debian 12 (bookworm) environment with 2 vCPU and
~4 GB RAM — or you are inside a sandbox created by another tool — you can
run the judge steps directly. Prerequisites: `gcc` 12.2.0 exactly,
passwordless `sudo` for the one-time apt step, Node.js ≥ 24.11 (the pinned
tarball is downloaded automatically if missing), ~2 GB disk for tools.

```bash
bash judge/setup.sh        # pinned JDK 21.0.9+10 + Ghidra 12.1.2 + rea-agents 3.1.0 (~700 MB)
bash judge/selftest.sh     # good artifact must pass + all 7 mutants must fail
bash judge/grade.sh examples/good --seed 20261014 --json /tmp/verdict.json
```

## The three targets

| target | what the agent must recover | core routine (from the unstripped symbol table) |
|---|---|---|
| `checksum` | 64-bit rotate-xor-add hash, FNV-1a basis + golden-ratio constant | `checksum_update` @ `0x1011a0` |
| `proto` | `0xAA cmd len payload chk` frame parser with 3 error classes | `proto_parse` @ `0x101190` |
| `keycheck` | `XXXXX-XXXXX-XXXXX` key over a 32-symbol alphabet, 3 hidden modular rules | `key_verify` @ `0x1011f0` |

The binaries are built by `judge/setup.sh` with `gcc -O2 -s` (pinned Debian
gcc 12.2.0); `judge/ground_truth/EXPECTED.sha256` pins their exact bytes so
the committed REA evidence (which embeds those sha256s) always matches.

## Measured wall times (2 vCPU, Debian 12, ~4 GB RAM)

| step | wall time |
|---|---|
| `judge/setup.sh` (cold: downloads JDK + Ghidra + rea, ~700 MB) | ~3 min 30 s |
| `judge/setup.sh` (warm, everything cached) | ~11 s |
| one `rea analyze` / `rea function` / `rea decompile` call | ~28–29 s each (Ghidra startup dominates) |
| `judge/grade.sh examples/good` (21 gates, 1500 process pairs) | ~31 s |
| `judge/selftest.sh` (good + determinism + 7 mutants) | ~5 min 16 s |

## Credit

- **REA — Reverse Engineer Anything**, [morluto/rea](https://github.com/morluto/rea)
  (~241k stars, MIT licence), used through its `rea-agents` npm CLI
  **3.1.0** (upstream tag `rea-agents-3.1.0`,
  commit `344b9b6dff9e65e9ba7e68067373ed5d24159c1c`), which drives
  **Ghidra 12.1.2 PUBLIC** (Apache-2.0, NationalSecurityAgency/ghidra,
  release build `20260605`) on **Eclipse Temurin JDK 21.0.9+10** (GPL-2.0
  with Classpath exception). All three are installed by `judge/setup.sh`
  with exact versions and sha256 checks recorded in
  [judge/VERSIONS.txt](judge/VERSIONS.txt). This demo uses only REA's
  static native workflow (`analyze`, `function`, `decompile`); the three
  target programs were written for this demo.

## Limits

- Ghidra is the only analysis provider exercised; REA's other providers are
  not covered.
- The judge checks behaviour and structural claims (addresses, evidence
  digests, byte-exact re-implementation, a working key) — not the English
  prose of the report.
- Targets are tiny (< 20 KiB, x86-64); nothing here benchmarks REA on large
  binaries.
- A first `rea` call in a fresh sandbox pays ~28 s of Ghidra JVM startup per
  command; the demo does not keep a long-lived analysis server.
