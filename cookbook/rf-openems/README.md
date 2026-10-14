# rf-openems — 2.45 GHz microstrip patch antenna verified by an FDTD judge

An agent works on a real RF design problem inside a disposable agent-next
sandbox: design (or debug) a 2.45 GHz microstrip patch antenna on FR-4, and a
judge the agent cannot modify runs a full-wave 3-D FDTD simulation and
decides. The judge never trusts the artifact's self-report — it re-runs the
simulation itself, checks |S11| ≤ −10 dB at 2.45 GHz with the resonance
within ±2 %, verifies the whole toolchain against an analytic 50 Ω microstrip
line (Hammerstad-Jensen closed-form within 3 %), and requires a mesh
convergence repeat.

> **Deviation from the original brief:** openEMS has no pinnable binary
> distribution (no PyPI/conda/Debian packages, no hosted release tarballs from
> upstream since 2019), so the judge uses **pymeep 1.31.0 (MEEP, MIT licence)
> from conda-forge**, pinned by exact version with recorded sha256 package
> hashes — same physics (cartesian 3-D FDTD), same deliverable, same oracle
> class. See `SPEC.md` and `RECEIPT.md`.

## Ask your agent

> In this repo there is a sandbox demo at `cookbook/rf-openems/`. Run
> `python3 cookbook/rf-openems/run.py` — it spins up a disposable sandbox with
> MEEP installed and grades `examples/good/antenna.py`. Then **improve the
> artifact in the sandbox**: write your own `antenna.py` (parameterised with
> the variables listed in `SPEC.md`), point `judge/grade.sh` at it with
> `bash judge/grade.sh /path/to/antenna.py --json /tmp/v.json`, and iterate on
> the geometry until every gate passes. Tell me the final S11 and resonance
> frequency.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/rf-openems/run.py           # clones this repo at main
python3 cookbook/rf-openems/run.py --ref some-branch --keep
```

## What it does

1. `sbx create` a fresh 30-min sandbox.
2. Clones this repo at `--ref`.
3. `judge/setup.sh` — downloads micromamba 2.3.2 (sha256-checked), creates a
   pinned conda env (`pymeep=1.31.0`, `python=3.12.11`, `numpy=1.26.4`).
4. `judge/selftest.sh` — grades the known-good example (must pass) and six
   single-edit mutants (must all fail); kills the run unless kill rate ≥ 90 %.
5. `judge/grade.sh examples/good/antenna.py --json …` — full verdict JSON.
6. Always kills and verifies the sandbox is gone.

## Measured wall time (this repo's RECEIPT.md)

See `RECEIPT.md` — setup ~2 min, one grade ≈ 10-15 min on 2 vCPU.

## Limits

- One frequency band (2.2–2.7 GHz), driving-point only — gain/pattern are not
  graded.
- A coarse-but-converged mesh (10 cells/mm, confirmed at 12) — not a
  production convergence study.
- Runtime rises linearly with `resolution³`; keep it ≤ 12 on a 2-vCPU sandbox.
