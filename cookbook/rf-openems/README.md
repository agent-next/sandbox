# rf-openems — 2.45 GHz microstrip patch antenna verified by an FDTD judge

An agent works on a real RF design problem inside a disposable agent-next
sandbox: design (or debug) a 2.45 GHz microstrip patch antenna on FR-4, and a
judge the agent cannot modify runs a full-wave 3-D FDTD simulation (openEMS)
and decides. The judge never trusts the artifact's self-report — it re-runs
the simulation itself, checks |S11| ≤ −10 dB at 2.45 GHz with the resonance
within ±2 %, re-derives S11 from the raw port time series, verifies the whole
toolchain against an analytic ~50 Ω microstrip line (Hammerstad-Jensen
closed form within 4 %), and requires a mesh-convergence repeat.

## Results

![S11 of the graded-good patch antenna against the -10 dB spec and the G5
band, with the fine-mesh re-run and the Hammerstad-Jensen line
oracle](media/result.png)
![Replayed verdicts of the seven known-bad variants and the good design, and
the self-test kill table](media/loop.png)

[media/demo.mp4](media/demo.mp4) — 36 s: one recorded grade per known-bad
variant, then the good design.

Numbers below are from `media/data/verdicts/good.json`
(`judge/grade.sh examples/good/antenna.py --trace`, seed 42) and
`media/data/selftest.txt`:

- verdict **PASS** on all 9 gates: S11 at 2.45 GHz −17.0 dB (spec ≤ −10 dB),
  resonance 2.44 GHz (spec 2.45 GHz ± 2 %)
- the judge's own S11 from the raw port time series matches the artifact's
  curve to 0.0 dB (tolerance 1.5 dB)
- line oracle: ε_eff 3.24 simulated vs 3.33 Hammerstad-Jensen, 2.8 %
  (tolerance 4 %)
- fine-mesh re-run (0.9 mm): S11 −10.4 dB at 2.45 GHz, resonance shift
  0.4 % — the dip depth is mesh-sensitive, so G8 re-checks the spec on the
  finer mesh
- self-test: 7/7 mutants killed (100 %), two same-seed grades identical

Media are rebuilt from the committed judge outputs with
`bash media/make_media.sh` after `judge/setup.sh`; `media/make_data.sh`
re-runs openEMS for every case to refresh `media/data/` (one good grade
took 368 s and the self-test 642 s in our runs).

## Ask your agent

> In this repo there is a sandbox demo at `cookbook/rf-openems/`. Run
> `python3 cookbook/rf-openems/run.py` — it spins up a disposable sandbox with
> openEMS installed and grades `examples/good/antenna.py`. Then **improve the
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

1. `sbx create` a fresh sandbox.
2. Clones this repo at `--ref`.
3. `judge/setup.sh` — installs into `$HOME/.rf-openems` without root:
   Debian bookworm `python3-openems` 0.0.35 plus its library closure (each
   .deb sha256-verified against `judge/packages.txt` and the signed apt
   metadata) and a pinned PyPI wheel set (`judge/requirements.txt`,
   `--hash=sha256:` per package, re-verified after download).
4. `judge/selftest.sh` — grades the known-good example (must pass) and seven
   single-edit mutants (must all fail, killer gate reported per mutant);
   checks verdict determinism; exits non-zero unless kill rate ≥ 90 %.
5. `judge/grade.sh examples/good/antenna.py --json …` — full verdict JSON.
6. Always kills and verifies the sandbox is gone.

## Measured wall time (see RECEIPT.md)

- setup: ~45 s
- one grade of the good example: ~5–7 min (artifact sim ~2 min, oracle line
  sim ~10 s, fine-mesh convergence sim ~3 min)
- selftest (good + 7 mutants + determinism check): ~15 min

## Limits

- One frequency band (2.2–2.7 GHz), driving-point only — gain, efficiency and
  far-field pattern are not graded.
- One coarse→fine confirmation run (mesh_res × 0.75), not a production
  convergence study.
- The physics model is a probe-fed patch on an ungrounded-edge FR-4 slab with
  PML boundaries — a teaching-grade geometry, not a manufacturing design.
