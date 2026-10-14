# SPEC — control-tuning

## Goal

Show that an agent can do classical controller design inside a disposable
agent-next sandbox: design a feedback controller for a simulated plant
(an inverted pendulum on a cart, linearised for design, nonlinear for
verification), and have a judge — whose rules the artifact cannot influence —
decide numerically whether the closed loop is good and robust.

## Artifact

`examples/good/controller.json` — a JSON object with exactly these keys:

```json
{
  "type": "lqr",
  "Q": [q1, q2, q3, q4],
  "R": [r1, r2]
}
```

- `type`: must be `"lqr"` (only accepted type).
- `Q`: 4 non-negative weights for state `[x, x_dot, theta, theta_dot]`
  (cart position [m], cart velocity [m/s], pendulum angle from upright [rad],
  pendulum angular rate [rad/s]); `Q[0]` and `Q[2]` must be > 0.
- `R`: 2 positive weights for inputs `[cart force, pendulum torque]`.

The judge computes the resulting gain matrix `K` itself with
`control.lqr()` on the linearised plant. The artifact supplies weights, not
gains, so a wrong sign or an unbounded gain cannot be smuggled in through the
artifact; a destabilising or too-aggressive design must come from the weights.

## Plant (fixed by the judge, not tunable)

Inverted pendulum on a cart (linearised about upright), standard notation:

- `M = 1.0 kg` (cart mass), `m = 0.1 kg` (pendulum mass),
  `l = 0.5 m` (pivot-to-COM half-length), `g = 9.81 m/s^2`
- Actuator hard limits: cart force `|F| <= 10 N`, pendulum torque
  `|tau| <= 1 N·m`.

Linearised dynamics (standard state-space model, e.g. MIT 6.241 / UW ME 564
notes):

```
xdd = ((M+m)*g*theta - b*thetad - F) / (4/3*M + m - m^2*l/(M+m))     (b=0)
```

implemented as the standard 4-state A, B matrices with one input (force) and
two inputs (force + torque on the pendulum) for the LQR design; the nonlinear
simulation integrates the full (non-linearised) pendulum-on-cart equations
with the same limits via `scipy.integrate.solve_ivp`.

## Judge gates (numeric pass rules)

All gates are evaluated by `judge/grade.sh` in a clean copy of `judge/`
(checksummed before/after); the artifact only supplies `Q` and `R`.

1. **Linear design valid** — `control.lqr()` on the linearised plant with the
   given `Q`, `R` returns a finite `K`; the closed-loop `A - B*K` has all
   eigenvalues with real part < -0.05 (strictly stable with margin).
2. **Nominal linear step response** — from initial state
   `theta = 0.15 rad` (≈ 8.6°), all else 0, linear simulation of `A - B*K`:
   - overshoot of `|theta|` (as fraction of 0.15) <= 10 %;
   - 2 % settling time of `theta` (and of `x`) <= 5 s;
   - steady-state `|theta|` at t=10 s <= 0.001 rad and steady-state `|x|`
     <= 0.01 m.
3. **Robustness margins (SISO force loop)** — gain margin >= 6 dB and phase
   margin >= 45° for the loop transfer `K[0] * (sI - (A - B[:,1:] K[1:]))^-1
   B[:,0]` evaluated with `control.margin()`.
4. **Nonlinear closed loop with saturation** — `solve_ivp` simulation of the
   full nonlinear model from the same initial condition for 10 s with LQR
   feedback and actuator saturation:
   - cart force and pendulum torque stay within ±10 N / ±1 N·m when
     unsaturated is requested;
   - peak `|theta|` never exceeds 0.5 rad (does not fall over);
   - `|theta|` and `|x|` 2 % settling <= 6 s (relaxed vs. linear);
   - steady-state at t=10 s: `|theta|` <= 0.001 rad, `|x|` <= 0.01 m.
5. **Monte-Carlo robustness** — 200 samples, each perturbing `M`, `m`, `l`
   uniformly in ±20 % (seeded, deterministic): nonlinear sim as gate 4 for 10 s.
   A sample passes if the sim stays bounded (peak `|theta|` <= 0.5 rad) and
   `|theta|` settles to within 2 % of 0 by t = 8 s. Requirement: >= 95 % of the
   200 samples pass.

Exit code 0 only if all gates pass. One JSON verdict is printed with every
gate's number.

## Acceptance oracle (independent of the artifact)

The judge does not trust any numbers the artifact carries. It:

- reads only `Q`, `R` from the artifact;
- recomputes `K` with `control.lqr()` (slycot backend if installed, else the
  bundled `control` solver);
- checks the step-response gates against a spec mask derived from the
  simulated trajectories (peak value, first/last crossing of the ±2 % band,
  final value), not from any value in the artifact;
- uses the seeded numpy default_rng with a fixed seed for Monte Carlo, so
  results are reproducible bit-for-bit;
- verifies the checksum of `judge/` before and after the run: any artifact
  that touched the judge fails.

## Non-goals

- Not a tutorial on LQR or pendulum dynamics; the plant is fixed and cited.
- No gain scheduling, no adaptive control, no observer/Kalman design: full
  state feedback.
- No robustness synthesis (H-infinity, mu): plain LQR, robustness is only
  *measured* by the Monte Carlo gate, not designed for.
- Not tuning the plant: plant parameters and actuator limits are fixed.

## Known-bad mutants (self-test)

`judge/mutants.py` generates known-bad artifacts from the good one by
single edits; `judge/selftest.sh` requires each to fail at least one gate and
the good one to pass:

1. **Sign flip** — negate the second diagonal of `Q` (negative weight).
2. **Too aggressive** — scale `Q` by 1000 (saturates the actuators).
3. **Too sluggish** — scale `Q` by 1/100 (fails settling-time gate).
4. **Degenerate R** — set one `R` entry to 1e-6 (effectively no input penalty;
   saturates or fails margins).
5. **Wrong type** — `type: "pid"`.
6. **NaN weight** — one `Q` entry replaced by `NaN`.

Kill rate must be >= 90 % (i.e. at least 6 of 6 mutants fail — 100 %).
