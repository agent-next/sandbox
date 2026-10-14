# RECEIPT — `cookbook/spice-filter/`

Real command output, pasted as produced. The "Hardening" runs below were
produced by the committed code on this branch (commits `085c510`..`7d1f4a3`),
in a Debian sandbox (2 vCPU, 4 GB RAM) at this repo's working tree.

## Hardening (DEMO-STANDARD.md `sbx/sim-demos-20261014` compliance)

Everything `judge/setup.sh` installs is the ngspice Debian package. Each
fresh-setup run below purged it first (`sudo apt-get purge -y ngspice`),
then ran `setup.sh` → `selftest.sh` → `grade.sh` from nothing.

### Two fresh-setup runs side by side

| | RUN-A | RUN-B |
|---|---|---|
| `judge/setup.sh` | exit 0, 3.3 s (download + install) | exit 0, 3.3 s (download + install) |
| `judge/selftest.sh` | exit 0, 7.0 s | exit 0, 6.4 s |
| `judge/grade.sh examples/good/lpf4sk.cir` | exit 0, 2.1 s | exit 0, 2.1 s |
| sha256 of `.deb` download | `710bc58f…c42d32f9` OK (`sha256sum -c`) | same, OK |
| ngspice installed | 39.3+ds-1 | 39.3+ds-1 |
| kill rate | **9/9 = 100 %** | **9/9 = 100 %** |
| verdict JSON | identical (see below) | identical |
| `ripple_db` | 0.096 | 0.096 |
| `stopband_max_db` | −56.14 | −56.14 |
| `max_deviation_db` (ideal) | 0.0 | 0.0 |
| `gbw_deviation_db` (1 MHz macro-model) | 0.15029 | 0.15029 |
| MC `pass_fraction` | 1.0 (100 runs) | 1.0 (100 runs) |

`diff RUN-A_verdict.json RUN-B_verdict.json` → **no differences** (both
fresh runs reproduce byte-identically).

```text
=== RUN-A: purge ngspice (everything setup.sh installs) ===
(Reading database ... 30273 files and directories currently installed.)
Removing ngspice (39.3+ds-1) ...
=== RUN-A: setup.sh ===
setup: downloading ngspice 39.3+ds-1 from Debian pool
/tmp/tmp.S9EyT47Y4h/ngspice.deb: OK
Selecting previously unselected package ngspice.
(Reading database ... [dpkg progress elided] ... 30273 files and directories currently installed.)
Preparing to unpack .../ngspice_39.3+ds-1_amd64.deb ...
Unpacking ngspice (39.3+ds-1) ...
Setting up ngspice (39.3+ds-1) ...
setup: tool versions
** ngspice-39 : Circuit level simulation program
ngspice debian package: 39.3+ds-1
Python 3.12.15
setup: wrote .../judge/VERSIONS.txt
setup: done
[setup exit 0, 3.3 s]
```

RUN-B printed the same lines with a different temp dir; both runs'
`judge/VERSIONS.txt` (byte-identical):

```text
# spice-filter judge: versions installed by judge/setup.sh
# (Linux x86_64)
ngspice ngspice-39
ngspice debian package: 39.3+ds-1
python3 3.12.15
```

Selftest (identical in both runs except temp paths and wall time):

```text
selftest: grading known-good .../examples/good/lpf4sk.cir
selftest: known-good PASSED all gates
mutants: r-decade-up.cir  edit: 'R1 in s1a 750' -> 'R1 in s1a 7.5k'
mutants: c-decade-down.cir  edit: 'C3 s2a out 680n' -> 'C3 s2a out 68n'
mutants: off-series.cir  edit: 'R2 s1a s1b 750' -> 'R2 s1a s1b 740'
mutants: swap-nodes.cir  edit: 'C1 s1a out1 120n' -> 'C1 s1b out1 120n'
mutants: missing-ground.cir  edit: 'C2 s1b 0 100n' -> 'C2 s1b gnd0 100n'
mutants: opamp-gain.cir  edit: 'E2 out 0 s2b 0 1' -> 'E2 out 0 s2b 0 100'
mutants: include-directive.cir  edit: +'.include "helpers.inc"'
mutants: unrecognised-topology.cir  edit: +'Rbias s1a s1b 1meg' (parallel damping resistor: valid design, shape the oracle cannot verify)
mutants: swap-feedback.cir  edit: 'C1 s1a out1 120n' -> 'C1 s1a 0 120n'
mutants: wrote 9 mutants to /tmp/.../mutants
selftest: killed    c-decade-down (gate: mask)
selftest: killed    include-directive (gate: parse)
selftest: killed    missing-ground (gate: parse)
selftest: killed    off-series (gate: series)
selftest: killed    opamp-gain (gate: sanity)
selftest: killed    r-decade-up (gate: mask)
selftest: killed    swap-feedback (gate: mask)
selftest: killed    swap-nodes (gate: mask)
selftest: killed    unrecognised-topology (gate: analytic)
selftest: kill rate 9/9 = 100%
selftest: determinism OK (two --seed 1 runs byte-identical)
selftest: OK
[selftest exit 0, 7.0 s]   (RUN-B: 6.4 s)
```

**Kill rate 9/9 = 100 %** (requirement ≥ 90 %, ≥ 5 known-bad): kills by
`parse`, `mask` (×4), `series`, `sanity` and the new fail-closed
`analytic` gate.

### Grade verdict (identical in RUN-A and RUN-B)

```json
{
  "artifact": "examples/good/lpf4sk.cir",
  "seed": 20261014,
  "passed": true,
  "gates": {
    "parse":      { "passed": true, "points": 801, "f_grid": "10..100000 200/dec" },
    "sanity":     { "passed": true, "dc_gain_db": -0.0 },
    "mask":       { "passed": true, "ripple_db": 0.096,
                    "stopband_max_db": -56.14 },
    "analytic":   { "passed": true, "max_deviation_db": 0.0,
                    "gbw_deviation_db": 0.15029, "gbw_hz": 1000000.0 },
    "series":     { "passed": true, "off_series": [] },
    "montecarlo": { "passed": true, "runs": 100, "seed": 20261014,
                    "pass_fraction": 1.0,
                    "worst_ripple_db": 0.757,
                    "worst_stopband_db": -53.193 }
  }
}
```

### Criterion-by-criterion evidence

1. **Pinned + sha256-checked.** `judge/VERSIONS.txt` (above, written by
   `setup.sh` on every install). `judge/requirements.txt` pins the
   matplotlib wheel set with sha256 hashes (`--require-hashes`), for
   `media/make_media.sh` only — the judge is stdlib-only. The ngspice
   `.deb` download is verified with `sha256sum -c` (paste above:
   `ngspice.deb: OK`).
2. **Determinism.** `selftest.sh` now runs `grade.sh --seed 1` twice and
   compares the verdict JSON byte-for-byte (paste above:
   `determinism OK`). The verdict has no wall-time field at all, so the
   two files are fully identical.
3. **Two fresh-setup runs.** Side-by-side table above; both verdicts
   byte-identical, no differences to explain.
4. **Judge strength.** Kill rate 100 % with 9 scripted known-bad
   mutants. Every gate compares against something independent of "the
   tool ran": mask vs the numeric spec, series vs the E24/E12 tables,
   sanity vs DC gain 1, Monte-Carlo vs the relaxed mask over 100 seeded
   runs, and the analytic gate vs closed-form math — twice (ideal
   buffers: 0.0 dB exact; 1 MHz-GBW macro-model: 0.15029 dB, limit 0.5).
5. **Lead findings** — see below.

### Lead findings, fixed (evidence)

- **run.py hid selftest output.** Fixed: `run.py` now echoes the
  selftest and grade stdout (`show()` in `run.py`, `echo=True` steps), so
  the user sees each `selftest: killed <mutant> (gate: ...)` line, the
  `kill rate 9/9 = 100%` line, the determinism line and the full grade
  verdict, plus the summary line. Verified locally:
  `python3 -m py_compile run.py` OK; the `echo` steps produce the exact
  lines pasted above (same scripts, run directly).
- **Analytic gate passed `skipped:true` on unrecognized topologies.**
  Fixed: it now fails closed (`failed_gate: "analytic"`, exit 1) unless
  `--allow-unverified` is given, which grades the other gates and marks
  the verdict `"unverified": true`. Exercised by the new mutant
  `unrecognised-topology` (a parallel 1 MΩ damping resistor — a valid
  design choice the shape check cannot verify):

  ```text
  $ bash judge/grade.sh mutants/unrecognised-topology.cir --json v.json
  { "passed": false, "failed_gate": "analytic",
    "reason": "topology not recognised by the closed-form oracle; the judge
    refuses to pass a design it cannot verify against independent math
    (re-run with --allow-unverified ...)", ... }        exit 1
  $ bash judge/grade.sh mutants/unrecognised-topology.cir --allow-unverified
  { "passed": true, ..., "gates": { "analytic":
    { "passed": false, "unverified": true, ... } }, "unverified": true }
                                                        exit 0
  ```

  Killed in the selftest: `selftest: killed unrecognised-topology (gate:
  analytic)`.
- **0.0 dB analytic deviation trivially exact.** Fixed: SPEC.md/README
  state why the ideal case is exact (the `E` source *is* the textbook
  ideal unity buffer, so the simulated stage is the closed-form stage),
  and the judge now runs a second case — the same netlist re-simulated
  with a 1 MHz-GBW one-pole op-amp macro-model — where the good design
  deviates a real **0.15029 dB** (limit 0.5 dB), so the oracle comparison
  is no longer trivially exact. The new `swap-feedback` mutant (feedback
  cap to ground) is caught by the mask gate first; it would also fail the
  topology check (the cap is no longer between junction and output), but
  gates run in order and mask fails first.

### `bash judge/setup.sh` (idempotent re-run)

```text
setup: ngspice 39.3+ds-1 already installed (skipping download)
setup: tool versions
** ngspice-39 : Circuit level simulation program
ngspice debian package: 39.3+ds-1
Python 3.12.15
setup: wrote .../judge/VERSIONS.txt
setup: done
```

## run.py verification

(not done: end-to-end `sbx` run — this authoring sandbox has no `sbx`
CLI and no API key, and cannot create cloud sandboxes. The lead runs it
end to end.) What was done instead, per the demo standard:

- `python3 -m py_compile run.py` — OK; `run.py --help` renders.
- The exact in-sandbox command sequence `run.py` sends to `sbx exec` was
  executed directly (`setup.sh`, `selftest.sh`, `grade.sh` pastes above),
  from this branch's working tree, and the echoed output matches what
  `run.py` now prints step by step.

## Deviations

- The brief said "ngspice AC analysis + .meas"; the judge instead reads
  the full AC sweep from an ngspice ASCII raw file. Reason: the mask
  gates need the maximum ripple/stopband over the whole band and a
  per-frequency comparison against the closed form, which `.meas`
  cannot express. Equivalent measurement, stronger use.
- The closed-form oracle covers the Sallen-Key cascade shape (the
  example's topology). Since the hardening, other topologies fail the
  analytic gate (fail closed) unless `--allow-unverified` is given;
  then the verdict is marked `"unverified": true` — by design, stated
  in SPEC.md.
- The 1 MHz-GBW macro-model oracle case uses a one-pole
  GBW model (VCCS + RC + VCVS), not a specific commercial op-amp
  model; SPEC pins it as a judge constant (`GBW_HZ`), not an artifact
  requirement.
- `judge/requirements.txt` resolves for CPython 3.12 manylinux x86_64
  (the interpreter VERSIONS.txt records); wheel tags are
  interpreter-specific, so the file pins the cp312-resolved set with
  hashes and lists cp311 hashes where the same version ships cp311
  wheels.
- Third-party content: none beyond the pinned Debian `ngspice` package
  (BSD-family licence, from Debian bookworm, URL and sha256 in
  `judge/setup.sh`). The filter design is original to this demo,
  derived with the classic unity-gain Sallen-Key equations.
- Receipt numbers were measured in the authoring sandbox, not through
  `sbx create`; the lead's end-to-end run is expected to differ by
  network time only.
- An earlier draft of `judge/requirements.txt` contained placeholder
  hashes; it was rewritten from real `pip download` + `sha256sum` of the
  resolved wheels before anything was committed (recorded here because
  the mistake happened, not because it shipped).
