# Torque-only rejection fixture

`torque-heavy.npz` is the unchanged iteration-3 policy from the development
loop, recovered from `out/fresh1/policy.npz`, not a retrained or synthesized
checkpoint.

- SHA256: `9bd882ef19c93ef5fe8e0624f779a0b08ce04422d4c8a9a1c52002ebebb0754d`
- Saved verdict: `examples/good/loop.json`, iteration 3.
- Command: `_eval.main`, seeds 101/202/303, 64 episodes per seed, 500 steps,
  mass scale 1.0. This was a pinned local CPU diagnosis, not a fresh lease.
- Recorded speed: 0.824245 m/s; falls: 0.0; saturation: 0.205657.
- Only `g3_torque_saturation` fails. Self-test now requires that exact
  failed-gate set, so disabling G3 makes the self-test fail.

The fixture uses the demo's own trainer and model, under the repository's
licence. Its recorded numbers are not a claim that the revised self-test
has run on a new lease. No GPU key was available during this review fix.
