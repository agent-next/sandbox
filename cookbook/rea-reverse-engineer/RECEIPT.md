# RECEIPT — rea-reverse-engineer

Two real runs in **two different disposable Debian 12 (bookworm) sandboxes**
(2 vCPU, ~3–4 GB RAM) on 2026-10-15. Sandbox A hosted the builder pass;
sandbox B was a fresh, empty machine (no `~/.rea-demo-tools`, no
`~/.cache/rea-demo`) used for the second cold reproduction. Toolchain on
both (all pinned + sha256/sha512-checked by `judge/setup.sh`, recorded in
`judge/VERSIONS.txt`):

- gcc (Debian) **12.2.0**
- node **v24.21.0** (image-provided; satisfies the ≥ 24.11 floor)
- Eclipse Temurin JDK **21.0.9+10** (sha256 `810d3773…`)
- Ghidra **12.1.2 PUBLIC 20260605** (sha256 `b62e81a0…`)
- rea-agents **3.1.0** npm CLI (sha512 `8a9f6376…`)

`judge/setup.sh` regenerated `judge/VERSIONS.txt` byte-identically on both
sandboxes; `git status` stayed clean after every run.

## Side-by-side (the standard's two-fresh-sandbox table)

| step / metric | sandbox A | sandbox B |
|---|---|---|
| `judge/setup.sh` cold (downloads ~700 MB) | exit 0, **3 m 1 s** | exit 0, **3 m 17 s** |
| `judge/setup.sh` warm re-run | exit 0, **19 s** | exit 0, **24 s** |
| `judge/grade.sh examples/good --seed 20261014` | exit 0, **21/21 gates**, 74 s | exit 0, **21/21 gates**, 144 s |
| `judge/selftest.sh` | exit 0, **7/7 mutants (100 %)**, 18 m 5 s | exit 0, **7/7 mutants (100 %)**, 19 m 43 s |
| verdict JSON (same seed, minus `timing`) | `"pass": true`, 21/21 | `"pass": true`, 21/21 — identical |
| built target sha256 | matches `EXPECTED.sha256` | matches `EXPECTED.sha256` (same 3 hashes) |
| one `rea analyze --detail detailed --format json` | ~29 s | ~78 s |

Verdicts, kill rate, and recovered key are identical across the two
sandboxes; only wall times differ (sandbox B's vCPUs are slower — the
differential gate spawns 1500 process pairs, so it scales with CPU).
That variance is exactly what `timing` fields are for; the standard's
determinism rule (same-seed verdicts identical minus `timing`) holds on
both.

## Sandbox B — cold `bash judge/setup.sh` — exit 0, 3 m 17 s

Fresh machine (empty `~/.rea-demo-tools` and `~/.cache/rea-demo`):

```
setup: gcc 12.2.0 ok
setup: node v24.21.0 ok
setup: downloading OpenJDK21U-jdk_x64_linux_hotspot_21.0.9_10.tar.gz
setup: extracting OpenJDK21U-jdk_x64_linux_hotspot_21.0.9_10.tar.gz
setup: downloading ghidra_12.1.2_PUBLIC_20260605.zip
setup: extracting ghidra_12.1.2_PUBLIC_20260605.zip
setup: downloading rea-agents-3.1.0.tgz
setup: installing rea-agents 3.1.0 into /home/user/.rea-demo-tools/npm
npm warn install-scripts 1 package has install scripts not yet covered by allowScripts:
npm warn install-scripts   rea-agents@3.1.0 (prepare: node scripts/prepare.mjs)
checksum: OK
proto: OK
keycheck: OK
setup: targets built in .../targets (stripped)
setup: reference builds + symbols.json in .../judge/ground_truth/build
setup: wrote .../env.sh and .../judge/VERSIONS.txt
setup: done

real    3m17.172s
EXIT=0
```

(npm notice lines trimmed.) The image's npm 11.19.0 warns that
rea-agents' `prepare` install script is not covered by `allowScripts`;
the script is not required — `rea --version` reports 3.1.0 and a real
`rea analyze` against a target ran to completion (below).

`checksum/proto/keycheck: OK` are `sha256sum -c` against
`judge/ground_truth/EXPECTED.sha256`: the freshly built stripped
binaries are byte-identical to the ones the committed REA evidence was
produced from. Built target sha256 (identical on both sandboxes):

```
8f827dae20e69d532d13b73c67ca67efdf450cebe09cd501d143ce15a9422353  checksum
1c7329b2ce82619527fd4c29f67c6d977951ec5759fbb464b10aa62a81514b5f  proto
63d64ba64a2cda236d6407a5c4d196da03432eb87f4f3c4e8aa94b6913f6c893  keycheck
```

### warm re-run — exit 0, 24 s (idempotent)

```
setup: gcc 12.2.0 ok
setup: node v24.21.0 ok
setup: jdk already present
setup: ghidra already present
setup: rea-agents already present
checksum: OK
proto: OK
keycheck: OK
setup: targets built ... / setup: done

real    0m23.740s
EXIT=0
```

## Sandbox B — `bash judge/selftest.sh` — exit 0, 19 m 43 s, kill rate 100 %

```
== selftest ==========================================================
--- known-good -------------------------------------------------------
PASS  known-good artifact (21/21 gates)  exit=0

--- determinism ------------------------------------------------------
PASS  two same-seed runs give identical verdict JSON (minus timing)

--- known-bad mutants -----------------------------------------------
MUTANT                 EXIT  GATES FAILED
fake-evidence          1     rea_evidence_checksum
missing-target         1     core_addr_proto,differential_proto,no_phantom_proto,rea_evidence_proto,reimpl_static_proto,report_schema_proto,targets_present
payload-order-swap     1     differential_proto
phantom-function       1     no_phantom_checksum
reimpl-off-by-one      1     differential_checksum
wrong-core-addr        1     core_addr_checksum
wrong-key              1     key_accepted

== summary ===========================================================
known-good     : PASS (21/21 gates)
mutants killed : 7/7
kill rate      : 100 %

SELFTEST PASSED: judge passes the good artifact and kills 7 mutants

real    19m42.860s
EXIT=0
```

Every mutant fails the gate it was designed to trip (`missing-target`
trips `targets_present` plus every per-target gate for `proto`, as
expected — one edit removes the whole target). Kill rate 7/7 = 100 %,
above the 90 % floor.

## Sandbox B — `bash judge/grade.sh examples/good --seed 20261014` — exit 0, 2 m 24 s

```
verdict: PASS
  targets_present            pass  all three target dirs present
  rea_evidence_checksum      pass  3 evidence files bound to binary sha256
  report_schema_checksum     pass  schema ok, 2 functions claimed
  reimpl_static_checksum     pass  self-contained python
  differential_checksum      pass  500 inputs byte-identical
  core_addr_checksum         pass  core_function.address inside checksum's core routine
  no_phantom_checksum        pass  all claimed addresses inside real functions
  ... (proto, keycheck identical set) ...
  key_accepted               pass  keycheck accepted key.txt
  judge_intact               pass  judge checksum unchanged
```

Verdict JSON tail (`/tmp/verdict.json`):

```json
  "gates_passed": 21,
  "gates_total": 21,
  "inputs_per_target": 500,
  "pass": true,
  "schema": "rea-reverse-engineer/grade/1",
  "seed": 20261014,
  "timing": { "elapsed_s": 144 }
```

```
real    2m24.440s
EXIT=0
```

## Sandbox B — live REA reproduction of the committed evidence

To prove the committed `examples/good/**/rea/*.json` are real REA output
and reproducible (not curated fixtures), sandbox B ran, after setup:

```
$ . ./env.sh
$ rea analyze targets/checksum --detail detailed --format json
```

in 78 s. Comparing that output to
`examples/good/checksum/rea/overview.json`: identical `evidence_id`
(`ev_39bff3ea72ee2fdebf495c13616f922d855d9adb165ab52dc80ca394593e9f56`),
identical `subject.digest.sha256`, identical `normalized_result`; the only
top-level difference is `subject.local_path`, which is sanitised to
`<sandbox>` in the committed copy for repo hygiene.

Note: `rea` 3.1.0's default output format is TOON; Evidence JSON needs
`--format json`. `media/MANIFEST.json` records the flag in each command.

## Sandbox A — earlier builder-pass logs (kept verbatim)

`bash judge/setup.sh` cold — exit 0, 3 m 1 s:

```
setup: gcc 12.2.0 ok
setup: node v24.21.0 ok
setup: downloading OpenJDK21U-jdk_x64_linux_hotspot_21.0.9_10.tar.gz
setup: extracting OpenJDK21U-jdk_x64_linux_hotspot_21.0.9_10.tar.gz
setup: downloading ghidra_12.1.2_PUBLIC_20260605.zip
setup: extracting ghidra_12.1.2_PUBLIC_20260605.zip
setup: downloading rea-agents-3.1.0.tgz
setup: installing rea-agents 3.1.0 into /home/user/.rea-demo-tools/npm
checksum: OK
proto: OK
keycheck: OK
setup: targets built in .../targets (stripped)
setup: reference builds + symbols.json in .../judge/ground_truth/build
setup: wrote .../env.sh and .../judge/VERSIONS.txt
setup: done

real    3m0.810s
EXIT=0
```

warm re-run — exit 0, 19 s. `bash judge/selftest.sh` — exit 0,
18 m 5 s, same 21/21 + 7/7 table as sandbox B above.
`bash judge/grade.sh examples/good --seed 20261014` — exit 0, 1 m 14 s,
`"timing": { "elapsed_s": 74 }`, 21/21 gates.

## Key numbers

| metric | value | rule |
|---|---|---|
| good artifact gates | **21 / 21 pass** (both sandboxes) | all must pass |
| inputs per differential gate | 500 | byte-identical stdout + exit code |
| mutant kill rate | **7 / 7 (100 %)** (both sandboxes) | ≥ 90 % |
| determinism | two same-seed verdicts byte-identical minus `timing` | must be identical |
| `judge_intact` | judge/ sha256 unchanged after grading | must be unchanged |
| recovered key | `AAAAA-KAYAA-AAAAY` → binary prints `OK`, exit 0 | binary decides |

## run.py verification

`python3 -m py_compile run.py` and `bash -n` on every judge script pass
(re-verified on sandbox B). The in-sandbox command sequence run.py sends
to `sbx exec` was exercised directly in both sandboxes (the same
`bash -c 'cd repo/… && bash judge/setup.sh && bash judge/selftest.sh &&
bash judge/grade.sh …'` shown above), and the clone step was verified
against the public remote `https://github.com/agent-next/sandbox`.

*not done:* an end-to-end `run.py` cloud run — neither sandbox has an
`SBX_API_KEY` and neither can create child sandboxes. The lead runs it
end to end.

## REPRODUCE.md

*not done (this pass):* the standard requires a different agent of a
different model family to reproduce from README alone into REPRODUCE.md
before merge. Out of scope for this builder pass; left for a follow-up.

## Media

*not done (this pass):* the standard's `media/result.png`, `loop.png` and
`demo.mp4` + a rendering `make_media.sh` are deferred to a later media
step per the task brief. What ships now is a real-run frame set —
`media/rea-analyze-checksum.png`, `media/rea-function-keycheck.png`,
`media/binary-vs-reimpl.png`, `media/judge-verdict.png` (each < 300 KB,
all real output, none synthesized) with `media/MANIFEST.json` naming the
command and source data per frame.

## Deviations

- **node 24.21.0 vs the setup.sh fallback pin (24.9.0):** both sandbox
  images ship node v24.21.0 at `/usr/local/bin/node`. It satisfies the
  pinned engine floor (≥ 24.11), so setup.sh uses it and does not unpack
  its own tarball. The tarball branch is still pinned + sha256-checked
  for images that lack node.
- **End-to-end `run.py`:** not run from inside a sandbox (no cloud
  credentials); syntax + the exact in-sandbox command sequence were
  verified on two real sandboxes instead. See "run.py verification".
- **REPRODUCE.md / full media:** deferred; see above.
