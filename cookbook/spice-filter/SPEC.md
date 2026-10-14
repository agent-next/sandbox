# SPEC — `cookbook/spice-filter/`

An agent works on a real analog design problem inside a disposable agent-next
sandbox: produce a SPICE netlist of an active low-pass filter that meets a
numeric spec mask, where a judge it cannot fool (ngspice + an analytic
reference + a component-value gate) decides whether the result is right.

## Goal

Design and fix a 4th-order active low-pass filter, expressed as one SPICE
netlist, so that simulation meets a two-sided frequency mask, survives a
Monte-Carlo tolerance sweep, and uses only real, orderable component values.

## Non-goals

- Op-amp realism (slew rate, noise, supply current): the op-amp may be ideal
  (a `VCVS` / `E` source, or a macro-model). DC gain of the filter must be 1.
- Voltage levels, power supply, biasing, layout, temperature drift.
- Netlist *style* (subcircuits, `.include`, naming) beyond the format rules
  below; any valid ngspice netlist that meets the mask is fine.
- Optimality: no reward for margin beyond the pass rules.

## Artifact

A single SPICE netlist file (the file graded by `judge/grade.sh <artifact>`)
readable by `ngspice -b`, containing:

- an AC source driving node `in`, ground node `0`, output node `out`;
- an AC analysis of its own spanning at least 10 Hz..100 kHz at ≥ 20
  points/decade (e.g. `.control` / `ac dec 200 10 100k` / `.endc`); the
  judge never executes it — it injects its own analysis deck — but the
  artifact must be a runnable netlist, not just a fragment;
- component values for `R` and `C` elements that lie on the E24 (5 %) and
  E12 (10 %) series respectively;
- a first line that is a SPICE title comment (netlists parse as intended);
- no `.include`/`.inc`/`.lib`/`.model` directives: the judge grades one
  offline file, and other dot-cards it does not need are ignored.

The known-good example is a 4th-order unity-gain Sallen-Key cascade, but the
gates below apply to *any* topology the agent produces.

## Judge gates (`judge/grade.sh <artifact> [--seed N] [--json out.json]
[--allow-unverified]`)

All gates are numeric and deterministic. Exit 0 only if every gate passes.

- **G1 parse/DC**: the artifact declares its own qualifying AC analysis
  (above), `ngspice -b` parses it and its `op` point solves with no error,
  and the judge's AC sweep of 10 Hz..100 kHz at node `out` returns ≥ 100
  points.
- **G2 mask (nominal)**: gain in dB relative to DC gain, on the grid 10 Hz to
  100 kHz, 200 pts/decade:
  - passband: |H(f)| − |H(10 Hz)| ripple ≤ **1.0 dB** for all f ≤ 1 kHz;
  - stopband: |H(f)| (dB rel. DC) ≤ **−40.0 dB** for all f ≥ 10 kHz.
- **G3 Monte-Carlo**: ≥ 50 runs (default 100), resistors uniform in ±5 %,
  capacitors uniform in ±10 % (all independent, seeded from `--seed`, default
  20261014). ≥ **90 %** of runs must meet the relaxed mask: ripple ≤ 3.0 dB
  to 1 kHz and ≤ −34.0 dB for all f ≥ 10 kHz.
- **G4 component values**: every `R` and `C` element's value matches an E24
  (R) / E12 (C) series value at 2 significant figures (i.e. value =
  `mantissa × 10^k`, mantissa ∈ the series table, k any integer; any of
  `100E-9`, `0.1U`, `100n` spellings accepted).
- **G5 sanity**: DC gain within 0.1 dB of 1 (no accidental passband
  attenuation/gain built into the design), and node `out` is not the same
  node as `in` (a wire is not a filter).

Violating any gate fails with the offending numbers printed.

## Acceptance oracle (independent of "it ran")

1. **Analytic reference**: the judge extracts the Sallen-Key stage table
   (Ra, Rb, Cf, Cg per stage) from the netlist, computes the closed-form
   cascade transfer function H(f) = Π 1/(s²·Ra·Rb·Cf·Cg + s·Cg·(Ra+Rb) + 1),
   and requires the ngspice AC response to agree within **0.05 dB** at every
   grid frequency. This catches swapped nodes and mis-wired stages that
   still "run fine" — the simulator output is compared against math
   derived from the component values, not against itself.
   The ideal-case deviation is **exactly 0.0 dB by construction**: the
   spec's ideal op-amp is a unity-gain VCVS (`E` source), which realizes
   the buffer of the textbook Sallen-Key equations exactly — an `E`
   source has no offset, no pole and infinite input impedance, so at
   every frequency the simulated stage *is* the closed-form stage.
   Because a trivially-exact comparison proves little on its own, the
   judge runs a second case: it rebuilds the same netlist with the ideal
   buffers replaced by a **1 MHz-GBW one-pole op-amp macro-model**
   (VCCS + RC integrator + unity VCVS) and requires that response to
   stay within **0.5 dB** of the same closed form. The good example
   measures ~0.15 dB there — a real, non-trivial deviation caused by
   finite loop gain around the Sallen-Key poles, so a wrong stage table
   that somehow matched the ideal deck would not match this one.
2. **Fail-closed topology check**: if the judge cannot extract the
   Sallen-Key cascade table from the netlist, the analytic gate **fails**
   — the judge refuses to pass a design it cannot verify against
   independent math. `--allow-unverified` downgrades this to an
   explicitly marked verdict (`"unverified": true`) that grades the
   remaining gates only; an opted-in pass is never presented as a
   verified one.
3. **Spec mask**: the mask numbers above are measured from the simulation,
   not asserted by the artifact or its comments.
4. **Monte-Carlo reproducibility**: with the fixed seed the pass fraction
   must be identical between two consecutive grade invocations
   (deterministic RNG seeding); `--seed` overrides it.

## Self-test (`judge/selftest.sh`)

- The known-good example passes all gates.
- ≥ 5 known-bad single-edit mutants of the good artifact each fail ≥ 1
  gate; mutants generated by `judge/mutants.py` (one edit each), including
  `unrecognised-topology` (a valid-looking extra damping resistor that
  breaks the closed-form shape check and must fail closed) and
  `swap-feedback` (feedback capacitor moved to ground).
- Kill rate ≥ 90 % printed by the self-test; exit non-zero otherwise.
- Determinism: two `grade.sh` runs with the same seed produce
  byte-identical verdict JSON; checked by the self-test on every run.

## Judge-integrity rule

The artifact under test is copied to a temp dir before grading; the judge
compares `sha256` of its own `judge/` tree before and after every grade and
fails closed if anything changed.

## Out of scope for the judge

- Whether the design is *good engineering* beyond the mask (noise, dynamic
  range, parts count, cost).
- Anything the netlist claims in comments.

## Tools (pinned by `judge/setup.sh`)

- ngspice **39.3+ds-1** (Debian bookworm package, SHA256-pinned download),
  installed idempotently. Python 3.10+ (stdlib only) for the judge math.
