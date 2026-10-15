# SPEC — control-tuning

## Goal

Show that an agent can do classical controller design inside a disposable
agent-next sandbox: choose LQR weights for a simulated plant (inverted
pendulum on a cart, linearised for design, nonlinear for verification), and
have a judge — whose rules the artifact cannot influence — decide numerically
whether the closed loop is stable, fast, respects the actuator limits, has
healthy robustness margins, and survives plant-parameter uncertainty.

## Artifact

`examples/good/controller.json` — a JSON object with exactly these keys:

```json
{
  "type": "lqr",
  "Q": [q1, q2, q3, q4],
  "R": [r1, r2]
}
```

- `type`: must be the string `"lqr"` (only accepted value).
- `Q`: 4 finite numbers, weights for state `[x, x_dot, theta, theta_dot]`
  (cart position [m], cart velocity [m/s], pendulum angle from upright [rad],
  pendulum angular rate [rad/s]); elementwise >= 0, and the position weights
  `Q[0]`, `Q[2]` must be > 0.
- `R`: 2 finite numbers > 0, weights for inputs `[cart force, pendulum
  torque]`.

The judge computes the gain matrix `K` itself with `control.lqr()` on the
linearised plant. The artifact supplies weights, not gains, so a wrong sign
or an unbounded gain cannot be smuggled in; a destabilising or too-aggressive
design must come from the weights.

## Plant (fixed by the judge, not tunable)

Inverted pendulum on a cart, point-mass pendulum on a massless rod, no
friction, linearised about the upright:

- `M = 1.0 kg` cart mass, `m = 0.1 kg` pendulum mass, `l = 0.5 m`
  pivot-to-COM distance, `g = 9.81 m/s^2`
- `(M+m)·xdd + m·l·thedd = F` and `m·l·xdd + (m·l²)·thedd = m·g·l·theta + tau`
- actuator hard limits `|F| <= 10 N`, `|tau| <= 1 N·m`.

The nonlinear simulation integrates the full (non-linearised) cart-pole
equations with `scipy.integrate.solve_ivp` and clamps the inputs at the
limits; the unclamped demand is measured separately.

## Judge gates (numeric pass rules)

All gates run in `judge/grade.py` against a checksummed copy of `judge/`;
the artifact only supplies `Q` and `R`. Default Monte-Carlo seed 20260101
(`--seed N` overrides).

Settling time, everywhere below, is the first sample after which the signal
stays inside its band for the rest of the run: a sample still outside the
band never counts as settled, even if it is the last outside sample, and a
signal outside its band at the horizon never settles.

1. **Artifact valid** — parses as JSON, exact key set, `type == "lqr"`,
   all weights finite, `Q >= 0` with `Q[0]`, `Q[2] > 0`, `R > 0`.
2. **Linear design valid** — `control.lqr()` succeeds (slycot raises on
   e.g. indefinite weights) and every eigenvalue of `A - B·K` has real part
   `< -0.05`.
3. **Nonlinear scenario 1** — recover from a `0.15 rad` lean (`x = 0`),
   clamped inputs, 10 s: unclamped demand stays within the actuator limits
   (`|F| <= 10 N`, `|tau| <= 1 N·m`); overshoot `max|theta|/0.15 - 1 <= 10 %`;
   2 % settling of `theta` (band 0.003 rad) `<= 5 s` and of `x`
   (band 0.01 m) `<= 5 s`; `|theta| <= 0.001 rad` and `|x| <= 0.01 m` at
   t = 10 s.
4. **Nonlinear scenario 2** — cart displaced `1 m`, pendulum upright:
   peak `|theta| <= 0.5 rad` (never falls over); demand within actuator
   limits; 2 % settling of `x` (band 0.02 m) `<= 7 s`; `|theta| <= 0.001 rad`
   at t = 10 s.
5. **Robustness margins** — loop-at-a-time SISO loops of the linearised
   plant, `L_i(s) = K_i·(sI - A)^-1·B_i`, negative feedback, both loops:
   gain margin `>= 6 dB` and phase margin `>= 45 deg`. Margins are measured
   on a 6000-point log frequency sweep from 0.01 to 1000 rad/s. The gain
   margin is read at every phase crossing of an odd multiple of 180 deg —
   +180 deg crossings count exactly like -180 deg ones (a +180 deg crossing
   is just as unstable under a gain change), and the worst crossing wins;
   if the phase crosses no odd multiple of 180 deg the gain margin is
   taken as unlimited (reported as 99 dB). Phase margins are normalised
   to the conventional signed range (-180 deg, 180 deg] — a raw margin of
   209 deg is really -151 deg and fails the 45 deg rule; if `|L|` never
   crosses 1 the phase margin is 180 deg.
6. **Monte-Carlo robustness** — 200 samples, each perturbing `M`, `m`, `l`
   independently and uniformly in ±20 % (seeded `numpy.default_rng`): two
   nonlinear 10 s runs per sample, one per spec scenario (the 0.15 rad
   lean and the 1 m cart displacement). A sample passes if both
   trajectories stay finite, peak `|theta| <= 0.5 rad`, `|theta|` settles
   within the 0.003 rad band by t = 8 s (lean run), and `|x|` settles
   within the 0.02 m band by t = 7 s (displacement run). Gate passes if
   `>= 95 %` of samples pass. The displacement criterion is the
   load-bearing one: theta recovery has direct torque authority and
   survives ±20 % drift for any design that passes the deterministic
   gates, while displacement settling is margin-limited and degrades
   under perturbation — it is what makes this gate able to fail.

Exit code 0 only if every gate passes. `--json out.json` writes the full
verdict (every gate's measured number and pass flag) to a file.

## Acceptance oracle (independent of the artifact)

The judge trusts no number the artifact carries: it reads only `Q`, `R`:

- recomputes `K` with `control.lqr()` (slycot backend; an slycot failure is
  a gate failure, not a judge crash);
- derives every spec number (peaks, settling times, final values, demands)
  from trajectories it simulates itself — `solve_ivp` for the nonlinear
  plant, eigenvalues for stability, a frequency sweep for margins — and
  compares them against the fixed numeric thresholds above;
- uses a seeded `numpy.random.default_rng`, so the Monte-Carlo result is
  reproducible bit-for-bit for a given seed;
- grades against a checksummed copy of `judge/` and verifies the checksum
  after grading: any modification of the judge fails the run (exit 3).

## Non-goals

- Not a tutorial on LQR or pendulum dynamics; the plant is fixed and cited.
- No gain scheduling, no adaptive control, no observer/Kalman design: full
  state feedback is assumed available.
- No robustness synthesis (H-infinity, mu): plain LQR; robustness is only
  *measured* by gates 5 and 6, not designed for.
- Not tuning the plant: plant parameters and actuator limits are fixed.

## Known-bad mutants (self-test)

`judge/mutants.py` generates known-bad artifacts from the good one by single
edits; `judge/selftest.sh` requires the good example to pass and every mutant
to be rejected with exit code 1 and a verdict JSON whose overall verdict is
FAIL and whose declared target gate is the one that failed. A grade that
crashes, writes no verdict, or trips the judge-integrity check is not a kill.
Mutants marked **isolated** must fail their target gate and nothing else —
that is what proves the gate has independent killing power:

1. **sign-flip** — `Q[2] = -50`: negative state weight, rejected by
   validation (gate 1).
2. **too-aggressive** — all `Q` × 1000: high-gain design whose demand far
   exceeds the actuator limits (gate 3).
3. **too-sluggish** — all `Q` / 100: misses the settling-time gates.
4. **degenerate-r-torque** — `R[1] = 1e-6`: enormous torque demand
   (gate 3).
5. **degenerate-r-force** — `R[0] = 1e-6`: enormous force demand (gate 3).
6. **nan-weight** — `Q[2] = NaN`: rejected by validation (gate 1).
7. **wrong-type** — `type = "pid"`: rejected by validation (gate 1).
8. **wrong-shape** — `Q` of length 3: rejected by validation (gate 1).
9. **weak-feedback** — all `R` × 1e5: feedback too weak for the pole check
   (gate 2) — proves the design gate itself can fire on a valid artifact.
10. **pm-fail** — `R[1]` × 30: the force loop's phase margin sags below
    45 deg while every other gate passes (**isolated**, gate 5) — proves
    the phase-margin gate has killing power.
11. **gm-fail** — `R[1]` × 120: the force loop crosses an odd multiple of
    180 deg with `|L| > 1`, a negative gain margin, and nothing else fails
    (**isolated**, gate 5) — proves the gain-margin gate sees +180 deg
    crossings too.
12. **mc-marginal** — all `Q` × 0.8: passes every deterministic gate
    (gates 1–5, graded `--no-mc`) but misses displacement settling on
    perturbed plants; killed by the Monte-Carlo gate alone (gate 6,
    `mc_pass_fraction` < 0.95). Proves the robustness gate can fail.

Kill rate must be >= 90 % (the reference judge kills 12/12, three of them
isolated single-gate kills: one by the Monte-Carlo gate, one by the phase-
margin gate, one by the gain-margin gate).
