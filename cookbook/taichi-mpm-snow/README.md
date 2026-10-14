# taichi-mpm-snow — MLS-MPM snow with Taichi (CPU)

An agent writes the classic
[MLS-MPM snow simulation](https://github.com/taichi-dev/taichi)
([taichi-dev/taichi](https://github.com/taichi-dev/taichi), v1.7.4, MIT
license) running on Taichi's CPU backend: an elastoplastic snowball
(Stomakhin-style hardening) with a second, fluid blob for contrast,
dropped onto the ground and splashing. A judge the agent cannot fool
decides whether the result is real MPM — every gate compares a number
extracted from the artifact's own log against a physical invariant
(mass conservation, free-fall under gravity, the boundary condition,
plastic deformation), not against the agent's claims.

A disposable sandbox is what makes this honest: the toolchain, the
simulation and every metric are installed from nothing on a machine
the agent does not control, and the whole thing is thrown away
afterwards.  Nothing about the host leaks into the verdict.

## Results

- `examples/good` passes **6/6 gates**: particle mass exactly
  conserved and grid mass equal to within **2e-7**, pre-contact
  free-fall velocity matching `g*t` to **1.8e-5**, no particle
  crossing the domain boundary through 5000 steps, snow height
  squashing to **0.89** of its start on impact with **62 %** of
  particles past the plasticity threshold, and horizontal
  momentum below **1e-5** of the mass.
- The self-test kills **6/6** scripted mutants (gate list in
  `SPEC.md`; the kill rate floor is 90 %).
- Two same-seed grades produce byte-identical verdict JSON, the
  `timing` key excluded — `selftest.sh` proves it on every run.

**Ask your agent:** "Write `sim.py` + `params.json` for a 2D MLS-MPM
snow simulation with Taichi on the CPU backend per
`cookbook/taichi-mpm-snow/SPEC.md`: a Stomakhin-hardening snowball
dropped onto a squishy fluid blob, deterministic for a fixed seed,
with mass conserved and the boundary held. The judge will run it and
check every invariant."

## Run it

```
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export PATH="$HOME/.local/bin:$PATH"   # pip --user installs sbx here
export SBX_API_KEY=<your key>          # or E2B_API_KEY
python3 run.py                         # --ref <branch> to clone a ref
```

A `pip --user` install puts the `sbx` console script in `~/.local/bin`,
which is not on `PATH` everywhere — add it or `run.py` reports
"sbx CLI not found". `SBX_API_KEY` (or `E2B_API_KEY`) is required;
without it `run.py` exits immediately. `run.py` creates a disposable
sandbox, clones this repo, installs the pinned toolchain, proves the
judge on the known-good and known-bad artifacts, grades
`examples/good/`, prints the verdict JSON, then kills the sandbox and
confirms it is gone. `--keep` leaves the sandbox up.

**No sandbox credentials?** The three judge steps `run.py` runs inside
the sandbox work verbatim on any Debian 12 box. From this directory:

```
bash judge/setup.sh
bash judge/selftest.sh
bash judge/grade.sh examples/good --seed 0
```

`0` is the seed every figure, verdict and reproduction here uses
(it is also `grade.sh`'s built-in default).

Measured wall time per step (see `RECEIPT.md` for the full record):

| step | wall time |
|---|---|
| create sandbox | ~2 s |
| clone repo | ~4 s |
| `judge/setup.sh` (venv + pinned wheels, hash-checked) | ~26 s |
| `judge/selftest.sh` (good + 6 mutants + determinism) | ~250 s |
| `judge/grade.sh examples/good` | ~23 s |

## What the judge checks

Six gates, all numeric and deterministic (`SPEC.md` has the full
rules): completion + no NaN/Inf, per-particle mass conserved to
1e-12 relative and grid mass after P2G equal to that within 1e-6,
free-fall velocity matching `g*t` to 1 % before first contact, no
particle leaving the boundary layer, snow squashing plastically on
impact (height ratio and plastic-Jp fraction), and horizontal
momentum staying at zero for a symmetric drop. `judge/` checksums
are taken before and after grading to prove the artifact cannot
modify the judge.

## Known-bad artifacts

`judge/mutants.py` generates 6 single-edit mutants of
`examples/good/` (the standard's `examples/bad/` equivalent — see
`SPEC.md` for the gates each must trip): gravity flipped, dt 20x too
large, boundary condition removed, a P2G weight bug that breaks mass
conservation, hardening off with plasticity disabled, and an
asymmetric initial velocity. All six must fail at least one gate;
`selftest.sh` reports the kill rate and requires it ≥ 90 %.

## Limits

- 2D only; Taichi CPU backend only; the pinned Taichi 1.7.4 wheel.
- The demo renders stacked RGB particle plots per step for a later
  video; it does not produce a video itself.
- Taichi compiles kernels on first use (cold JIT ~15 s on 2 vCPU).

## Upstream

- [taichi-dev/taichi](https://github.com/taichi-dev/taichi) —
  version 1.7.4, MIT license.
