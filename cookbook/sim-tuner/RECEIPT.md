# RECEIPT — sim-tuner, round r2 (2026-10-14)

Builder round 2 of this demo. Round 1 (commits f158f17, a1ee211, eeb4c29)
shipped the judge and a good example; a wip commit (0644647) held round 2 in
progress when its session was interrupted. This round continued from there.
Branch: `sbx/tuner-r2`. Tool versions: judge venv per `judge/VERSIONS.txt`
(CPython 3.13.5, mujoco 3.8.1, numpy 1.26.4); GPU lease stack per
`judge/version-table.json` (RTX 5090 slice, warp 1.13.0, mujoco-warp 3.8.1).

## What this round changed

1. **`requirements.lock` completed** (9b6543f): the pin set now carries the
   full transitive closure with per-wheel sha256s (absl-py, etils, glfw,
   pyopengl, fsspec, typing_extensions, zipp, importlib_resources, plus
   per-cpython mujoco/numpy wheels); `setup.sh` verified from a clean venv and
   idempotently re-run.
2. **`_grade.py` verdict crash fixed** (78509e1): a dead block indexed a
   string with `g4["version_check"]["problems"]` and would have raised
   `TypeError` instead of failing the grade when the lease version check
   failed.
3. **Mutants grade `--cpu-only`** (78509e1): every mutant dies on a CPU gate,
   so only artifacts that pass all CPU gates ever lease a GPU; the self-test
   now creates exactly one lease (for the good grade).
4. **The metric was re-derived** (e553223). The round-1 6-signal scene cannot
   gate `solref`: with `box_zdot` unrecorded, `solref` range-edge mutants of a
   converged fit score 1.01–1.08× the noise floor — inside the honest-fit
   scatter — and no threshold separates them (measured; see SPEC). Recording
   the landing channel (7 signals) fixes identifiability, but per-RMS
   normalisation of that mostly-zero channel amplifies landing-timing error at
   the 8 ms observation frame into a needle: 0.0149 at truth vs 0.19 one
   13×13-grid step (1.3 % of range) away in `solref_tc`. Four search methods
   (CEM with stagnation kicks, top-1 walk, differential evolution, batched-FD
   BFGS) and two block decompositions (the box rig and the arm rig never
   touch, so the problem factorises into 3-dim and 2-dim subproblems) all
   stall at 0.10–0.18 under that metric. Peak normalisation (95th percentile
   of |signal|) for that one channel removes the needle while keeping the
   mutant band at 2.8–45× the floor; G3's absolute cap recalibrated to 0.025
   (1.6× floor, 1.6× below the weakest edge mutant). Full calibration table in
   SPEC.md; all numbers measured on CPU MuJoCo 3.8.1, seed 7.
5. **`tools/search.py` loop replaced** (e553223): uniform pre-sample + BFGS
   with batched finite-difference gradients (two GPU chunks per iteration:
   5-point gradient, 4-point simultaneous line search), restarted from the
   next-best pre-sample starts on stall.

## (not done: reason)

- **`examples/good/` does not yet pass G3.** The search — under the committed
  peak-normalised metric — still stalls at train error ≈ 0.099–0.119
  (7–8.5× the 0.01400 floor) where G3 needs ≤ 0.025. Diagnosis, measured: the
  landing transient is sampled every 8 ms, and a parameter offset that shifts
  the landing by one sample frame changes the pointwise error discontinuously;
  the residual sub-percent needle at truth survives peak normalisation
  (0.0140 at truth vs 0.075–0.118 one grid step away). The fix this
  diagnosis points at — comparing recordings **aligned at the landing event**
  (a standard sim-to-real system-ID practice) or filtering the impact channel
  — is an engine + GPU-payload change with a full recalibration; it did not
  fit in this round's time box and was not started. The round-1 good example
  (committed a1ee211, train 0.01697 under the 6-signal metric) is likewise not
  valid under the new metric. `examples/good/` currently holds the round-2
  search's real output, and `selftest.sh` will report it FAILING G3 until the
  aligned-metric search converges.
- **Consequently `run.py`'s two fresh end-to-end runs, the self-test's green
  run, and the RECEIPT key-number table are pending** on the same fix; there
  is no honest green run to paste this round.
- **`media/` untouched** (per the round plan; every number the figures need is
  in `examples/good/loop.json`).

## GPU leases created and destroyed this round

| lease | purpose | destroyed + confirmed |
|---|---|---|
| `gl-951d38-5` | metric/identifiability probe (good + edge mutants, GPU vs CPU) | yes (GET → 404) |
| `gl-951d38-11` | search round 1 (stalled 0.14720, 6-signal metric) | yes (GET → 404) |
| `gl-951d38-14` | search round 2 (stalled 0.11886, 7-signal RMS metric) | yes (GET → 404) |
| (this round's final search — see loop.json for its id) | search round 3 (peak metric) | yes, confirmed in the search log |

No sandbox, snapshot or template other than leases created by this round's
own code was touched. Scratch files under `/tmp/st-calib/` and `/tmp/st-wheels*`
were deleted after the round.
