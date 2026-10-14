# Reverse-engineer three stripped binaries with REA

## Goal

Show an agent doing real reverse engineering with the open-source **REA
(Reverse Engineer Anything)** toolkit — `morluto/rea`, MIT licence,
`rea-agents` npm CLI **3.1.0**, backed by **Ghidra 12.1.2** — inside a
disposable agent-next sandbox, and have a judge it cannot fool decide whether
the explanation of each binary is right.

The agent is given three stripped ELF executables in `targets/`. It must run
REA against them, work out what each program computes, and hand back an
artifact that a differential judge verifies against the real binaries.

## Non-goals

- Not a decompiler bake-off. Ghidra is the only provider exercised (Hopper
  and IDA are commercial and cannot ship in the demo).
- Not a general REA feature tour. Only the static native workflow is used
  (`analyze`, `search --kind procedures`, `instructions`, `decompile`).
- Not a proof that the agent's prose is "true". The judge checks behaviour
  (byte-exact re-implementation, a working key) and structural claims
  (function addresses that exist) — not the English narrative.
- Not a benchmark. REA+Ghidra timing is reported because a judge that takes
  an hour is useless, not because speed is graded.
- The ground-truth C sources live in `judge/ground_truth/` in this repo.
  They are part of the judge, not part of the puzzle: the "Ask your agent"
  prompt tells the agent to stay out of `judge/`. Nothing about the grading
  relies on the agent honouring that — every gate still measures the artifact
  against the binaries.

## The three targets

Built by `judge/setup.sh` from `judge/ground_truth/*.c` with
`gcc -O2 -s` (pinned Debian gcc 12.2.0), x86-64 PIE, stripped:

| target | what it is | core routine (symbol in the unstripped build) |
|---|---|---|
| `checksum` | reads stdin, prints a custom 64-bit rotate-xor-add checksum | `checksum_update` |
| `proto` | parses a byte stream of `0xAA cmd len payload chk` frames, prints one verdict line per frame | `proto_parse` |
| `keycheck` | reads a `XXXXX-XXXXX-XXXXX` licence key from stdin, prints `OK`/`DENIED` | `key_verify` |

The unstripped reference builds and their symbol tables are written to
`judge/ground_truth/build/` by `setup.sh` (git-ignored, regenerated each
setup). The agent only sees `targets/<name>`.

## The artifact

The judged artifact is a directory with one sub-directory per target:

```
<artifact>/
  checksum/
    report.json        # schema below
    reimpl.py          # python3 stdin->stdout re-implementation
    rea/               # >= 2 REA Evidence JSON files, incl. one binary_overview
  proto/               # same shape
  keycheck/            # same shape, plus key.txt
```

`report.json` (one per target):

```json
{
  "schema": "rea-demo/report/1",
  "target": "checksum",
  "sha256": "<sha256 of the target binary>",
  "core_function": {"label": "<any>", "address": "0x1011a0"},
  "functions": [{"label": "<any>", "address": "0x...", "role": "<any>"}],
  "algorithm": "<free text>"
}
```

`key.txt` (keycheck only): the candidate licence key, fed verbatim to the
binary's stdin.

## Acceptance oracle

The judge never trusts the artifact to report about itself. Four independent
oracles:

1. **The binaries themselves** — every `reimpl.py` is run against the real
   stripped binary on 500 seeded pseudo-random inputs and must match stdout
   and exit code byte for byte.
2. **The binary, again** — `key.txt` is fed to the real `keycheck` binary,
   which alone decides `OK`/`DENIED`.
3. **The unstripped symbol table** — the report's claimed function addresses
   must fall inside real function ranges recovered from the identical
   unstripped build (`nm`), which the artifact cannot see.
4. **REA's own Evidence format** — the `rea/` files must be well-formed REA
   Evidence v2 objects whose embedded `subject.digest.sha256` equals the
   sha256 of the judged binary, so a file cannot be copied from a different
   target or invented from whole cloth.

## Gates

`judge/grade.sh <artifact> [--seed N] [--json out.json]` prints exactly one
verdict JSON object; exit 0 only if every gate passes. Gates are recorded
per target where the check is per target (`<gate>_<target>`).

| gate | what is measured | pass rule |
|---|---|---|
| `targets_present` | the artifact directory | contains `checksum/`, `proto/`, `keycheck/` sub-directories |
| `rea_evidence_<t>` | `rea/*.json` under target `t` | ≥ 2 files; each parses, has `schema_version`, `predicate_type` starting `rea.`, `subject.digest.sha256` == sha256(`targets/t`); at least one has `operation` `binary_overview` |
| `report_schema_<t>` | `report.json` | parses; `schema` == `rea-demo/report/1`; `target` == `t`; `sha256` == binary's; `core_function.address`, `functions` list, `algorithm` present |
| `differential_<t>` | run binary vs `reimpl.py` on 500 inputs | **all** 500 identical (stdout bytes + exit code) |
| `core_addr_<t>` | `core_function.address` vs symbol table | address ∈ [start, end) of the target's core symbol, in ELF or Ghidra (+0x100000) space |
| `no_phantom_<t>` | every `functions[].address` | each ∈ some real function's [start, end), either address space |
| `key_accepted` | `keycheck/key.txt` into the binary | binary exits 0 and prints `OK` |
| `judge_intact` | sha256 of every file under `judge/` before vs after | identical |

### Input generation

500 inputs per target, from `judge/gen_inputs.py` with `random.Random(seed)`:

- `checksum`: arbitrary byte strings, length 0–300.
- `proto`: 70 % well-formed random frames, 30 % corrupted (bad sync byte,
  truncated, wrong check byte) or pure garbage.
- `keycheck`: 50 % correctly-shaped random keys, 50 % random printable
  garbage.

### Address spaces

Ghidra loads a PIE at image base `0x100000`; ELF symbol addresses are the
raw virtual addresses. A claimed address `A` counts as inside a range
`[s, e)` iff `A ∈ [s, e)` or `A − 0x100000 ∈ [s, e)`. The same rule is used
by `core_addr` and `no_phantom`, so neither gate is stricter than the other.

## Known-bad artifact family

`judge/mutants.py` generates ≥ 5 single-edit mutants of
`examples/good/`; every mutant must fail at least one gate:

| mutant | edit | gate that must fail |
|---|---|---|
| `reimpl-off-by-one` | checksum reimpl rotate `5` -> `6` | `differential_checksum` |
| `endianness-swap` | proto reimpl reads `len` field as `len+1` | `differential_proto` |
| `wrong-key` | one key character changed | `key_accepted` |
| `phantom-function` | report gains a function outside all real ranges | `no_phantom_checksum` |
| `missing-target` | `proto/` deleted | `targets_present` |
| `fake-evidence` | evidence sha256 byte-flipped | `rea_evidence_checksum` |
| `wrong-core-addr` | core address moved to a different function | `core_addr_checksum` |

`judge/selftest.sh` runs the known-good artifact (must pass), two same-seed
grades of it (verdict JSON minus `timing` must be byte-identical), then every
mutant (each must fail); it prints the kill rate and exits non-zero below 90 %.

## What this demo does not prove

- That the agent understood anything it was not asked to reproduce. A reimpl
  could be lifted from `judge/ground_truth/`; the REA-evidence gate only
  proves REA ran against these exact binaries, which is the thing being
  showcased.
- Anything about other REA providers, other architectures, or binaries bigger
  than a few KiB.
- Timing: an artifact that took hours to produce still passes.
