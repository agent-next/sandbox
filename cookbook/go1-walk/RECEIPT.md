# Go1 walking receipt

Measured on 2026-10-15. These are real jobs, not predicted results.
Both complete `run.py` invocations exited 0, including the full mutation
self-test, independent grade and confirmed lease deletion. Neither run
used `--keep` or `--no-selftest`.

## Commands and environment

From the repository root, with the GPU-enabled key already exported:

```bash
env -u HTTPS_PROXY -u https_proxy -u HTTP_PROXY -u http_proxy \
  GO1_LEASE_WAIT_S=7200 python3 cookbook/go1-walk/run.py \
  --outdir cookbook/go1-walk/out/resume2-train

env -u HTTPS_PROXY -u https_proxy -u HTTP_PROXY -u http_proxy \
  GO1_LEASE_WAIT_S=7200 python3 cookbook/go1-walk/run.py \
  --skip-train cookbook/go1-walk/examples/good \
  --outdir cookbook/go1-walk/out/final-replay --trace
```

The first invocation trained from random weights. Its policy, actual
step-0 and short-training checkpoints, config and curve were copied
unchanged to `examples/good/`. The second used that exact policy on a
different new lease. Training seed 1 and selection seed 4242 are distinct
from held-out judge seeds 101/202/303. Each judge seed uses 64 episodes,
500 control steps, a 0.002 s physics timestep and 0.02 s control timestep.

## Two fresh runs

| Measurement | Fresh training, gl-0626f0-9 | Fresh replay, gl-e0bca3-2 |
|---|---:|---:|
| Mean forward speed (m/s) | 0.768245 | 0.768245 |
| Fall rate | 0.0 | 0.0 |
| Maximum per-seed saturation fraction | 0.076125 | 0.076125 |
| Peak torque / actuator limit | 1.0 | 1.0 |
| Best baseline (m/s) | -0.001227 | -0.001227 |
| Baseline margin (m/s) | 0.769472 | 0.769472 |
| Verdict / self-test | PASS / 11 of 11 killed | PASS / 11 of 11 killed |
| Setup / self-test / grade / driver exits | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Create (s) | 3.471 | 3.865 |
| Pinned stack setup (s) | 3.134 | 18.784 |
| Training round trips (s) | 1680.882 | Not retrained |
| Self-test round trips (s) | 1482.869 | 2135.622 |
| Final grade round trip (s) | 188.902 | 472.812 |
| Cleanup (s) | 0.951 | 0.826 |
| Total including transfers and cleanup (s) | 4012.31 | 2652.438 |

Policy SHA256: `fceee5a28ccf99ee3063291431634d46d587716a815bf9d37dbe1f2ea65e9f02`.
Model SHA256: `1a8174762926e860e28dff93c20c5eb5cef0606daf2b3e6a19159a751dbe1e90`.

PPO: **500 iterations**, **49,152,000 env-steps**,
**486.1 s**, **101,114 env-steps/s**.
The reported PyTorch peak reserved memory is 736,100,352 bytes and peak
allocated memory is 470,649,856 bytes. These exclude Warp and driver
allocations. Six chunk warmups totalled 56.49 s. The requested allocation
was 4 GiB; the image's `nvidia-smi` reported 4916 MiB, not a total-memory
guarantee established by these counters.

The replay requested traces and therefore adds a `traces` dictionary.
All other non-timing verdict fields are exactly equal. Each run's
self-test additionally performed two complete, identically configured
grades and verified byte-identical JSON after removing only `timing`.

### First complete run, raw output

```text
$ GO1_LEASE_WAIT_S=7200 python3 cookbook/go1-walk/run.py --outdir cookbook/go1-walk/out/resume2-train
create: gl-0626f0-9, 4 GiB, 3.471 s
setup: rc=0, 3.134 s; gpu=NVIDIA GeForce RTX 5090, 4916 MiB; stack={"warp-lang": "1.13.0", "mujoco": "3.8.1", "mujoco-warp": "3.8.1", "numpy": "1.26.4", "torch": "2.10.0", "torch_runtime": "2.10.0+cu128"}
training chunk 1: rc=0 it=101 reward=1.8651 train_wall=90.5 s kernel_warmup=52.12 s torch_peak_reserved=734003200 bytes walk_evals=[]
training chunk 2: rc=0 it=195 reward=2.4113 train_wall=180.7 s kernel_warmup=0.82 s torch_peak_reserved=736100352 bytes walk_evals=[]
exec reply unavailable; recovering token 681a9148add84f689a996e5d030444ad, attempt 1/6 (HTTP 503)
exec reply unavailable; recovering token 681a9148add84f689a996e5d030444ad, attempt 2/6 (HTTP 503)
exec reply unavailable; recovering token 681a9148add84f689a996e5d030444ad, attempt 3/6 (HTTP 503)
training chunk 3: rc=0 it=291 reward=2.7444 train_wall=271.0 s kernel_warmup=0.907 s torch_peak_reserved=736100352 bytes walk_evals=[]
training chunk 4: rc=0 it=388 reward=2.7991 train_wall=361.4 s kernel_warmup=0.933 s torch_peak_reserved=736100352 bytes walk_evals=[]
training chunk 5: rc=0 it=476 reward=3.0697 train_wall=451.9 s kernel_warmup=0.747 s torch_peak_reserved=736100352 bytes walk_evals=[{'it': 400, 'forward_mps': 0.1658, 'upright': 0.9688}]
training chunk 6: rc=0 it=500 reward=3.0734 train_wall=486.1 s kernel_warmup=0.963 s torch_peak_reserved=736100352 bytes walk_evals=[{'it': 400, 'forward_mps': 0.1658, 'upright': 0.9688}, {'it': 500, 'forward_mps': 0.7631, 'upright': 1.0}]
exec reply unavailable; recovering token 245ae17053bc4059b5d76b9d021fb2f6, attempt 1/6 (HTTP 503)
training: {"env_steps": 49152000, "iters": 500, "kernel_warmup_per_chunk_s": [52.12, 0.82, 0.907, 0.933, 0.747, 0.963], "kernel_warmup_s": 0.963, "kernel_warmup_total_s": 56.49, "last_chunk_wall_s": 40.0, "reward_end": 3.0734, "selected_checkpoint_it": 500, "selection_seed": 4242, "steps_per_s": 101114, "torch_peak_allocated_bytes": 470649856, "torch_peak_reserved_bytes": 736100352, "train_wall_s": 486.1, "walk_evals": [{"forward_mps": 0.1658, "it": 400, "upright": 0.9688}, {"forward_mps": 0.7631, "it": 500, "upright": 1.0}]}
selftest: good 1 PASS fwd=0.768245 m/s fall=0.0 sat=0.076125
selftest: good 2 PASS fwd=0.768245 m/s fall=0.0 sat=0.076125
selftest: byte-identical verdicts outside timing
selftest: untrained: KILLED (g1_forward_speed, g4_beats_baseline; fwd=-0.000982)
selftest: short-training: KILLED (g1_forward_speed, g2_fall_rate, g4_beats_baseline; fwd=0.007502)
selftest: reward-flipped: KILLED (g1_forward_speed, g4_beats_baseline; fwd=-0.083633)
selftest: random-init: KILLED (g1_forward_speed, g2_fall_rate, g3_torque_saturation, g4_beats_baseline; fwd=-0.005932)
selftest: zero-output: KILLED (g1_forward_speed, g4_beats_baseline; fwd=-0.001187)
selftest: negated-output: KILLED (g1_forward_speed, g2_fall_rate, g3_torque_saturation, g4_beats_baseline; fwd=-0.008108)
selftest: shuffled-output: KILLED (g1_forward_speed, g2_fall_rate, g4_beats_baseline; fwd=-0.003597)
selftest: noisy-weights: KILLED (g1_forward_speed, g2_fall_rate, g3_torque_saturation, g4_beats_baseline; fwd=-0.004526)
selftest: saturating: KILLED (g1_forward_speed, g4_beats_baseline; fwd=-0.000924)
selftest: weak-output: KILLED (g1_forward_speed, g4_beats_baseline; fwd=0.00514)
selftest: mass2x: KILLED (g1_forward_speed, g2_fall_rate, g3_torque_saturation, g4_beats_baseline; fwd=0.04619)
selftest: kill rate 11/11 = 100%; PASS
grade: rc=0, 188.902 s
{"artifact": "policy.npz", "backend": "mujoco-cpu-float64", "baselines": {"random": {"fall_rate": 1.0, "forward_mps": -0.019033, "min_forward_mps": -0.125432, "peak_torque_ratio": 1.0, "sat_frac": 0.40576}, "zero": {"fall_rate": 0.0, "forward_mps": -0.001227, "min_forward_mps": -0.00261, "peak_torque_ratio": 0.700419, "sat_frac": 0.0}}, "determinism": {"a": {"fall_rate": 0.0, "forward_mps": 0.773951, "min_forward_mps": 0.415346, "peak_torque_ratio": 1.0, "sat_frac": 0.076125}, "b": {"fall_rate": 0.0, "forward_mps": 0.773951, "min_forward_mps": 0.415346, "peak_torque_ratio": 1.0, "sat_frac": 0.076125}, "identical": true, "seed": 101}, "eval": {"cmd": [1.0, 0.0, 0.0], "episodes_per_seed": 64, "mass_scale": 1.0, "seeds": [101, 202, 303], "steps": 500}, "gates": {"g1_forward_speed": {"pass": true, "rule": "mean forward m/s >= 0.5", "value": 0.768245}, "g2_fall_rate": {"pass": true, "rule": "fall rate <= 0.05", "value": 0.0}, "g3_torque_saturation": {"pass": true, "rule": "saturation <= 0.15; torque ratio <= 1.000001", "value": 0.076125}, "g4_beats_baseline": {"pass": true, "rule": "beats best zero/random baseline by >= 0.30 m/s", "value": 0.769472}, "g5_determinism": {"pass": true, "rule": "same seed gives identical metrics", "value": true}}, "judge_intact": true, "measured": {"best_baseline_forward_mps": -0.001227, "fall_rate": 0.0, "max_sat_frac": 0.076125, "mean_forward_mps": 0.768245, "peak_torque_ratio": 1.0}, "model_sha256": "1a8174762926e860e28dff93c20c5eb5cef0606daf2b3e6a19159a751dbe1e90", "ok": true, "policy_sha256": "fceee5a28ccf99ee3063291431634d46d587716a815bf9d37dbe1f2ea65e9f02", "policy_shapes": [[512, 45], [256, 512], [128, 256], [12, 128]], "runs": [{"fall_rate": 0.0, "forward_mps": 0.773951, "min_forward_mps": 0.415346, "peak_torque_ratio": 1.0, "policy": "under_test", "sat_frac": 0.076125, "seed": 101}, {"fall_rate": 0.0, "forward_mps": 0.769977, "min_forward_mps": 0.565536, "peak_torque_ratio": 1.0, "policy": "under_test", "sat_frac": 0.075911, "seed": 202}, {"fall_rate": 0.0, "forward_mps": 0.760806, "min_forward_mps": 0.545352, "peak_torque_ratio": 1.0, "policy": "under_test", "sat_frac": 0.075922, "seed": 303}, {"fall_rate": 0.0, "forward_mps": -0.001227, "min_forward_mps": -0.00261, "peak_torque_ratio": 0.700419, "policy": "zero", "sat_frac": 0.0, "seed": 101}, {"fall_rate": 1.0, "forward_mps": -0.019033, "min_forward_mps": -0.125432, "peak_torque_ratio": 1.0, "policy": "random", "sat_frac": 0.40576, "seed": 101}], "stack": {"mujoco": "3.8.1", "mujoco-warp": "3.8.1", "numpy": "1.26.4", "torch": "2.10.0", "torch_runtime": "2.10.0+cu128", "warp-lang": "1.13.0"}, "timing": {"wall_s": 95.97}}
destroyed gl-0626f0-9; GET 404 confirmed
total: 4012.31 s; rc=0

process_exit=0
command_wall_s=4012
```

### Second complete run, raw output

```text
$ GO1_LEASE_WAIT_S=7200 python3 cookbook/go1-walk/run.py --skip-train cookbook/go1-walk/examples/good --outdir cookbook/go1-walk/out/final-replay --trace
create: gl-e0bca3-2, 4 GiB, 3.865 s
setup: rc=0, 18.784 s; gpu=NVIDIA GeForce RTX 5090, 4916 MiB; stack={"warp-lang": "1.13.0", "mujoco": "3.8.1", "mujoco-warp": "3.8.1", "numpy": "1.26.4", "torch": "2.10.0", "torch_runtime": "2.10.0+cu128"}
selftest: good 1 PASS fwd=0.768245 m/s fall=0.0 sat=0.076125
selftest: good 2 PASS fwd=0.768245 m/s fall=0.0 sat=0.076125
selftest: byte-identical verdicts outside timing
selftest: untrained: KILLED (g1_forward_speed, g4_beats_baseline; fwd=-0.000982)
selftest: short-training: KILLED (g1_forward_speed, g2_fall_rate, g4_beats_baseline; fwd=0.007502)
selftest: reward-flipped: KILLED (g1_forward_speed, g4_beats_baseline; fwd=-0.083633)
selftest: random-init: KILLED (g1_forward_speed, g2_fall_rate, g3_torque_saturation, g4_beats_baseline; fwd=-0.005932)
selftest: zero-output: KILLED (g1_forward_speed, g4_beats_baseline; fwd=-0.001187)
selftest: negated-output: KILLED (g1_forward_speed, g2_fall_rate, g3_torque_saturation, g4_beats_baseline; fwd=-0.008108)
selftest: shuffled-output: KILLED (g1_forward_speed, g2_fall_rate, g4_beats_baseline; fwd=-0.003597)
selftest: noisy-weights: KILLED (g1_forward_speed, g2_fall_rate, g3_torque_saturation, g4_beats_baseline; fwd=-0.004526)
selftest: saturating: KILLED (g1_forward_speed, g4_beats_baseline; fwd=-0.000924)
selftest: weak-output: KILLED (g1_forward_speed, g4_beats_baseline; fwd=0.00514)
selftest: mass2x: KILLED (g1_forward_speed, g2_fall_rate, g3_torque_saturation, g4_beats_baseline; fwd=0.04619)
selftest: kill rate 11/11 = 100%; PASS
grade: rc=0, 472.812 s
{"artifact": "policy.npz", "backend": "mujoco-cpu-float64", "baselines": {"random": {"fall_rate": 1.0, "forward_mps": -0.019033, "min_forward_mps": -0.125432, "peak_torque_ratio": 1.0, "sat_frac": 0.40576}, "zero": {"fall_rate": 0.0, "forward_mps": -0.001227, "min_forward_mps": -0.00261, "peak_torque_ratio": 0.700419, "sat_frac": 0.0}}, "determinism": {"a": {"fall_rate": 0.0, "forward_mps": 0.773951, "min_forward_mps": 0.415346, "peak_torque_ratio": 1.0, "sat_frac": 0.076125}, "b": {"fall_rate": 0.0, "forward_mps": 0.773951, "min_forward_mps": 0.415346, "peak_torque_ratio": 1.0, "sat_frac": 0.076125}, "identical": true, "seed": 101}, "eval": {"cmd": [1.0, 0.0, 0.0], "episodes_per_seed": 64, "mass_scale": 1.0, "seeds": [101, 202, 303], "steps": 500}, "gates": {"g1_forward_speed": {"pass": true, "rule": "mean forward m/s >= 0.5", "value": 0.768245}, "g2_fall_rate": {"pass": true, "rule": "fall rate <= 0.05", "value": 0.0}, "g3_torque_saturation": {"pass": true, "rule": "saturation <= 0.15; torque ratio <= 1.000001", "value": 0.076125}, "g4_beats_baseline": {"pass": true, "rule": "beats best zero/random baseline by >= 0.30 m/s", "value": 0.769472}, "g5_determinism": {"pass": true, "rule": "same seed gives identical metrics", "value": true}}, "judge_intact": true, "measured": {"best_baseline_forward_mps": -0.001227, "fall_rate": 0.0, "max_sat_frac": 0.076125, "mean_forward_mps": 0.768245, "peak_torque_ratio": 1.0}, "model_sha256": "1a8174762926e860e28dff93c20c5eb5cef0606daf2b3e6a19159a751dbe1e90", "ok": true, "policy_sha256": "fceee5a28ccf99ee3063291431634d46d587716a815bf9d37dbe1f2ea65e9f02", "policy_shapes": [[512, 45], [256, 512], [128, 256], [12, 128]], "runs": [{"fall_rate": 0.0, "forward_mps": 0.773951, "min_forward_mps": 0.415346, "peak_torque_ratio": 1.0, "policy": "under_test", "sat_frac": 0.076125, "seed": 101}, {"fall_rate": 0.0, "forward_mps": 0.769977, "min_forward_mps": 0.565536, "peak_torque_ratio": 1.0, "policy": "under_test", "sat_frac": 0.075911, "seed": 202}, {"fall_rate": 0.0, "forward_mps": 0.760806, "min_forward_mps": 0.545352, "peak_torque_ratio": 1.0, "policy": "under_test", "sat_frac": 0.075922, "seed": 303}, {"fall_rate": 0.0, "forward_mps": -0.001227, "min_forward_mps": -0.00261, "peak_torque_ratio": 0.700419, "policy": "zero", "sat_frac": 0.0, "seed": 101}, {"fall_rate": 1.0, "forward_mps": -0.019033, "min_forward_mps": -0.125432, "peak_torque_ratio": 1.0, "policy": "random", "sat_frac": 0.40576, "seed": 101}], "stack": {"mujoco": "3.8.1", "mujoco-warp": "3.8.1", "numpy": "1.26.4", "torch": "2.10.0", "torch_runtime": "2.10.0+cu128", "warp-lang": "1.13.0"}, "timing": {"wall_s": 84.539}, "traces": {"101": "26f8ec54c101d6835e0dd2304ab9e3b228a13668ca4ec4bbabb5914120ffeae9", "202": "8267ae46b8af5fd29a75c8beeeffc9f5e99007a305441984c9de20428385d5d8", "303": "4fd80a7eb692fd47f10326bb551164dbb8272f1a77c7508a0dfd89edb249ea44"}}
destroyed gl-e0bca3-2; GET 404 confirmed
total: 2652.438 s; rc=0

process_exit=0
command_wall_s=2652
```

## Actual policy-development loop

`examples/good/loop.json` retains every distinct available policy grade
used in the loop figure, including failures. The first two were inherited
development runs; their full original argv was not retained, and they
are not counted as either fresh reproduction above.

| Iteration | Change | Speed (m/s) | Falls | Saturation | Policy gates |
|---|---|---:|---:|---:|---|
| 1 | Initial 400-iteration policy | 0.457239 | 0.494792 | 0.061188 | 3/5 |
| 2 | Longer reward-tuned training | 0.445714 | 0.0 | 0.088794 | 4/5 |
| 3 | Recovered policy: torque gate fails | 0.824245 | 0.0 | 0.205657 | 4/5 |
| 4 | Output gain 0.4, separate validation | 0.589354 | 0.0 | 0.121484 | 5/5 |
| 5 | Fresh PPO: unmodified actor passes | 0.768245 | 0.0 | 0.076125 | 5/5 |

Iteration 3 was a pinned local CPU diagnosis, not a fresh-lease receipt.
It used `_eval.main` on seeds 101/202/303, 64 episodes and 500 steps.
The same recovered policy also failed G3 on lease gl-0626f0-8:
`run.py --skip-train examples/good --outdir out/resume2-replay2`
returned 1 after 230.198 s and confirmed GET 404. A previous capacity
attempt returned HTTP 409 before creating a lease.

Iteration 4 scaled the output layer after a separate seed-4242 validation
sweep. Its real lease grade passed, but its full driver did not:
`run.py --skip-train out/resume2-gain/good --outdir out/resume2-calibrated
--trace` returned 1 after 3507.344 s when six transport-recovery attempts
were exhausted after eight mutants. Lease gl-0626f0-10 was deleted with
GET 404. It is not a successful full run or the shipped policy.

The final policy is the *unmodified* actor from the successful fresh PPO
run, not that scaled candidate. An experimental automatic output
calibration path was removed because this measured training run did not
need or exercise it. No judge threshold was relaxed.

## Media and provenance

The collection and raw render output in this section describe the
previous cut. The close-tracking recut below supersedes its video size,
camera, shot timing, state-check count and web-encode setting.

```bash
env -u HTTPS_PROXY -u https_proxy -u HTTP_PROXY -u http_proxy \
  GO1_LEASE_WAIT_S=7200 bash cookbook/go1-walk/media/make_media.sh
bash cookbook/go1-walk/media/make_media.sh --render-only
```

The first command collected another full real 11/11 mutation self-test,
a trained grade and an actual random-initialization grade on fresh lease
gl-e0bca3-3, then confirmed deletion with GET 404. The random-init
comparison measured -0.005932 m/s, 100% falls, and saturation 0.271384.
The first cut exceeded the 8 MB web limit, so its driver correctly
returned 1. Render-only rebuilt from the same checked lease states,
with a less busy render-only floor and slower camera movement. That cut
was still 8,150,055 bytes, above the strict 8,000,000-byte limit. Adding
x264's animation tune retained CRF 18/preset slow and brought it below
the limit. It did
not change physics, poses, the policy, or measured results.

The media command and hashes of all inputs are in `media/MANIFEST.json`.
The exact-state assertions, renderer and frame counts are recorded in
`media/data/render.json`. Each rendered qpos/qvel is checked to 1e-9.
The untrained frozen fall is a real terminated episode, not an invented
animation. The storyboard's training process view is recorded PPO
telemetry, not a fabricated agent transcript or screen capture.

### Successful render-only command, raw output

```text
$ bash cookbook/go1-walk/media/make_media.sh --render-only
== reuse hash-verified judge states (no new grade) ==
== MuJoCo 3D replay (egl), Pillow labels, lossless master ==
{"frames": 900, "duration_s": 30, "width": 1920, "height": 1080, "fps": 30, "backend": "egl", "graphics": {"vendor": "NVIDIA Corporation", "renderer": "NVIDIA GeForce RTX 5090/PCIe/SSE2", "version": "4.6.0 NVIDIA 580.95.05"}, "lighting": "render-only world lights follow robot xy for shadow-map coverage", "state_checks": {"trained-101": 451, "trained-202": 181, "trained-303": 181, "untrained-101": 1, "untrained-202": 181, "untrained-303": 181}, "episode_selection": "episode 0, fixed before grading", "model_sha256": "1a8174762926e860e28dff93c20c5eb5cef0606daf2b3e6a19159a751dbe1e90", "render_model_sha256": "0b33a68e08554f3218b6428729b5d2cc2bb71e3cf1533cf092d7517a0ef89256"}
== web encode from CRF 0 master ==
media verified: 30.0 s, 7200578 bytes
test_media_contract_and_checks (test_media.MediaTests.test_media_contract_and_checks) ... ok
test_no_plotting_library_in_media (test_media.MediaTests.test_no_plotting_library_in_media) ... ok
test_render_model_preserves_physics (test_media.MediaTests.test_render_model_preserves_physics) ... ok
test_replay_metrics_come_from_exact_scored_states (test_media.MediaTests.test_replay_metrics_come_from_exact_scored_states) ... ok
test_replay_rejects_a_changed_checkpoint (test_media.MediaTests.test_replay_rejects_a_changed_checkpoint) ... ok
test_state_check_rejects_drift (test_media.MediaTests.test_state_check_rejects_drift) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.150s

OK
codec_name=h264
width=1920
height=1080
pix_fmt=yuv420p
r_frame_rate=30/1
duration=30.000000
size=7200578
make_media: done

process_exit=0
command_wall_s=78
```

## Versions

```text
# local side (2026-10-15)
python3 3.12.3
venv $HOME/.venvs/go1-walk:
numpy==2.2.6
pip==24.0
lease stack (asserted by _eval.py at grade time):
  warp-lang 1.13.0
  mujoco 3.8.1
  mujoco-warp 3.8.1
  torch 2.10.0+cu128
  numpy 1.26.4
  GPU: RTX 5090 slice, 4 GiB VRAM
```

Actual local setup and idempotency check:

```text
$ bash cookbook/go1-walk/judge/setup.sh
setup.sh: creating $HOME/.venvs/go1-walk
setup.sh: rc=0 (pinned local NumPy; lease stack asserted before training and grading)
first_process_exit=0
$ bash cookbook/go1-walk/judge/setup.sh
setup.sh: venv already provides numpy 2.2.6
setup.sh: rc=0 (pinned local NumPy; lease stack asserted before training and grading)
second_process_exit=0
```

## Validation

- Go1 regression suite: 16 passed. The old six-attempt exec implementation
  fails the new lost-reply/busy-job assertion, not an import error.
- The old renderer fails the new changed-checkpoint assertion, not an
  import error.
- Current-main integration was tested in an isolated synthetic merge of
  source commit 070f8a5c with main ecfbcfa1: CLI tests passed on Python
  3.10 and 3.13, 310 each; cookbook tool tests passed, 61. The tool tests
  intentionally report pre-existing demo-video failures as baseline data.
- Final media checks and full-size image review are recorded in
  `media/REVIEW.md`; any blind-panel limitation is recorded there.
- On resume, all 16 demo regression tests and all 6 media tests passed
  again. `ffprobe` confirmed H.264, 1920×1080, 30 fps, yuv420p, 30 s and
  7,200,578 bytes. Saved raw fresh-run logs were checked against the
  pasted output above; no replacement run or invented output was used.
- Two saved blind frame reviews are retained in `media/REVIEW.json`.
  One describes an opening terminal that is absent from the decoded
  video. This is not claimed as a passing blind panel.

## Final lease audit

The resumed worker created no new lease. It queried only the twenty
lease IDs recorded in this demo's development logs. Sixteen returned
404 directly. Four returned HTTP 200 with `phase: dead`, despite the
earlier confirmed deletions. Deleting those dead owned records again
gave the required immediate GET 404 confirmation. No live or unrelated
sandbox was deleted.

```text
gl-08a900-9: GET 404
gl-08a900-11: GET 404
gl-08a900-13: GET 404
gl-08a900-14: GET 404
gl-08a900-15: GET 404
gl-08a900-18: GET 404
gl-08a900-22: GET 404
gl-08a900-23: GET 404
gl-08a900-24: GET 404
gl-a6b86e-31: GET 404
gl-a6b86e-32: GET 404
gl-a6b86e-33: GET 404
gl-0626f0-2: GET 404
gl-0626f0-3: GET 404
gl-0626f0-4: GET 404
gl-0626f0-8: GET 404
gl-0626f0-9: GET 200, phase dead
gl-0626f0-10: GET 200, phase dead
gl-e0bca3-2: GET 200, phase dead
gl-e0bca3-3: GET 200, phase dead
initial_audit_exit=1

destroyed gl-0626f0-9; GET 404 confirmed
destroyed gl-0626f0-10; GET 404 confirmed
destroyed gl-e0bca3-2; GET 404 confirmed
destroyed gl-e0bca3-3; GET 404 confirmed
cleanup_process_exit=0
```

## Deviations and limits

- Networkless GPU REST leases replace the standard CPU sandbox clone.
  The fixed lease image already includes the pinned physics stack; every
  grade checks it and fails closed on drift. The runner ships the model
  and judge rather than using pip or git inside the lease.
- PPO itself completed in 8.10 minutes. Complete acceptance took 66.87
  and 44.21 minutes, including repeated independent CPU evaluation,
  transfer and transport delays. This does not meet current main's
  under-10-minute full GPU launch target. These are actual wall times,
  not a claimed training-only time-to-result.
- Lost 503 training replies were recovered using the same execution
  token. The started marker prevents repeating interrupted work; failed
  results are cached as failures. Busy-job recovery now waits beyond six
  replies, with a finite deadline.
- A foreground local setup attempt timed out while installing, before
  the longer recorded installation/idempotency check.
- Only foot spheres collide with the floor. A fall terminates the
  episode; a fallen body may penetrate the floor. No hardware safety or
  sim-to-real claim is made.
- Independent reproduction by a different model family remains a
  pre-merge task. This builder intentionally did not write
  `REPRODUCE.md`; its unfinished inherited draft was removed.
- Every lease created by these final commands was deleted and GET 404
  was confirmed. Earlier owned gl-0626f0-3 and gl-0626f0-4 were also
  independently confirmed 404. No unrelated inventory was deleted.

## Close-tracking media recut, 2026-10-15

```text
$ bash cookbook/go1-walk/media/make_media.sh --render-only
== reuse hash-verified judge states (no new grade) ==
== MuJoCo 3D replay (egl), Pillow labels, lossless master ==
== web encode from CRF 0 master ==
media verified: 30.0 s, 7262402 bytes
Ran 9 tests in 1.048s
OK
codec_name=h264
width=1920
height=1080
pix_fmt=yuv420p
r_frame_rate=30/1
duration=30.000000
size=7262402
make_media: done
```

This excerpt omits the long render JSON and individual successful test
names; the complete render report is `media/data/render.json`.
Every one of 831 rendered views matches saved judge qpos/qvel within
1e-9. No source checkpoint, scored trace, verdict, model physics, training
number, or mutation result changed. No lease was created.

The new opener is a close MuJoCo trunk-tracking shot. Training numbers
occupy 3 s, without a plot. The actual random-initialization fall ends on
the terminating step rather than holding a frozen state. Five checks
draw in over a walking robot, followed by the plain-language 11/11
broken-policy result. The only static shot is the 2.5 s end card.
Opened all 30 decoded 1 fps frames in five contact sheets: no slide-like
pre-card shot. See `media/STORYBOARD.md` and `media/REVIEW.md`.

```text
$ python cookbook/tools/video_gate.py cookbook/go1-walk/media/demo.mp4
passed: true
failed: []
duration_s: 30.0
fps: 30.0
size_mib: 6.926
scene_cuts_per_10s: 1.0
motion_fraction: 0.9249
endcard_static: 0.0005
```

This is an excerpt of the gate's JSON fields, not an alternative gate.
All 16 checks passed, including H.264, yuv420p, 1920×1080, faststart
and first-frame luma. The size is below both 8 MiB and 8,000,000 bytes.

The resumed worker inspected and retained the inherited recut, then
reran `python3 -m pytest -q cookbook/tools/test_video_gate.py`:
**20 passed in 1085.15 s**. The MP4 gate passed again with the values
above, along with all **9 media tests** and **16 Go1 regression tests**.
A fresh extraction of all 30 decoded 1 fps frames was visually inspected
in five contact sheets. No slide-like pre-card shot was found. Temporary
review frames and unchanged upstream gate-tool copies were cleaned up;
the cached judge states and ignored lossless master were retained.

### Recut deviations and validation limits

- Existing compositor used because Remotion and HyperFrames were absent.
- CRF 22 replaces CRF 18 for the web encode. The first close-up candidate
  at CRF 18 was 11,996,858 bytes and failed both size and scene-cut checks.
  The final cut uses a render-only charcoal floor for the untrained
  comparison, then returns to the bright walking shot; no physics changes.
- The branch lacks `cookbook/tools/`. The requested verification used
  unchanged tools temporarily materialized from upstream
  `ecfbcfa1f67718a55a651e487b149be686ca0712`. They are not PR changes.
- A first gate-suite run scored the intermediate oversized candidate
  and reported 19 passed, 1 failed (the Go1 committed-video baseline).
- A first extra demo-test attempt used a Python environment without
  NumPy and failed collection. Running the correct existing render
  environment's unittest command passed all 16 Go1 regression tests.
- Old-versus-new test power: the old renderer fails the new camera test
  with `0 != mjCAMERA_TRACKING: video camera must track the trunk body`;
  the current renderer passes.
- No fresh sandbox run or CLI test matrix was run for this media-only
  recut. The two recorded real runs above are unchanged.
- Gemini/Opus blind rescoring was not run. The owner-provided prior
  scores are not claimed as scores for the new video.