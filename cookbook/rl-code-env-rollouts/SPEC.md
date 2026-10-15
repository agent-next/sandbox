# RL / eval environment rollouts: a verifiable-reward code environment

## Goal

Show an agent building the *harness* that RL and eval work is actually done
with: a gymnasium-compatible environment whose reward is **verifiable** —
computed by running submitted code against hidden tests in a locked-down
subprocess, never by asking the code whether it worked.

The agent produces two things, together called the **artifact**:

1. `code_task_env.py` — a module defining `CodeTaskEnv`, a
   `gymnasium.Env` subclass over 20 generated programming tasks. `step(action)`
   takes Python source as its action, runs it in a subprocess with a wall-clock
   timeout and POSIX resource limits, and returns
   `reward = (hidden tests passed) / (hidden tests total)`.
2. `policy_outputs.jsonl` — one reference solution per task, one JSON object
   per line.

The judge then drives the environment it was given and checks the reward
signal itself: determinism, exact partial credit, zero for hostile actions,
no leakage of the hidden tests into the observation, and throughput. An
environment that runs is not enough — the reward has to be *right*, and the
judge recomputes it from its own reference implementations.

Why a sandbox: the whole point of this environment is to execute untrusted
code. An agent iterating on it will feed it infinite loops, fork bombs and
file-deleting programs on purpose. That belongs in a disposable machine, not
on the machine you are reading this on.

## Non-goals

- **Not a benchmark and not a model.** No policy is trained, no LLM is called,
  no learning happens. `policy_outputs.jsonl` is a *reference solution set*
  written by hand — it exists so the judge has a known-1.0 input.
- **Not a security boundary.** The resource limits and the timeout are the
  ordinary `resource.setrlimit` / `SIGKILL` controls, applied to a process
  group. They stop an infinite loop, a fork bomb and a runaway allocator.
  They are not a container, not a seccomp filter, and not a defence against
  a determined adversary. See "What this demo does not prove".
- **Not a sandbox-product integration.** Nothing here is specific to any
  sandbox vendor; the environment is plain Python and the judge runs anywhere
  Python 3.10+ runs.
- Not a curriculum, not a difficulty ladder, no partial-observation or
  multi-turn tasks. One task, one action, one reward.
- Not a throughput benchmark. Throughput is *recorded* and gated at a low
  floor because an environment that takes an hour per rollout is unusable,
  not because speed is the thing being graded.

## The task bank

`tasks/tasks.json` is the **public** contract between the environment and the
judge: 20 tasks, 5 hidden tests each (100 tests total). Each task is

```json
{"id": "t07", "entry": "gcd", "prompt": "Write a function `gcd(a, b)` ...",
 "tests": [{"args": [12, 18], "expect": 6}, ...]}
```

The bank is generated once by `tasks/gen_tasks.py --seed 20261015` and
committed; it is data, not code. `prompt` and `id` are *visible* to the agent
being evaluated — they are the observation. `tests` are **hidden**: they must
never appear in the observation or in `info`.

The bank is not the oracle. The judge carries its own reference
implementations in `judge/oracle/reference.py`, written from the same task
specifications but sharing no code with the bank, and gate 1 requires the
bank's stored `expect` values to agree with the judge's reference on every one
of the 100 tests before anything else is graded.

## The environment contract

```python
import gymnasium

class CodeTaskEnv(gymnasium.Env):
    metadata = {"render_modes": []}

    def __init__(self, tasks_path=None, seed=None, timeout_s=3.0, **kw): ...
    def reset(self, *, seed=None, options=None) -> tuple[dict, dict]
    def step(self, action: str) -> tuple[dict, float, bool, bool, dict]
```

- **observation** — a `dict` with exactly the keys `task_id` (str), `prompt`
  (str) and `index` (int). It is contained in `observation_space`, a
  `gymnasium.spaces.Dict`. Nothing else is in it.
- **action** — a `str` of Python source defining the current task's `entry`
  function. `action_space` is a `gymnasium.spaces.Text`; the space is not
  used to validate the action's contents (arbitrary source is legal, including
  source that does not compile).
- **reward** — a `float` in `[0.0, 1.0]`, exactly
  `tests_passed / tests_total` for the current task. Never rounded, never
  clamped to a coarser grid, never `1.0` because the code merely ran.
- **terminated** — `True` on the step that answers the last task of the
  episode, else `False`. **truncated** is always `False`: a step that times
  out is a legal step that scored `0.0`, not an episode truncation.
- **info** — a `dict` with exactly the keys `task_id`, `tests_total`,
  `tests_passed`, `exit_code`, `timed_out`, `wall_s`. No test input, no
  expected output, no source of the hidden tests.
- **reset(seed=S)** — restarts the episode and fixes the task order from `S`.
  The same `S` gives the same order, always; different `S` values give
  different orders.

The episode is one pass over the 20 tasks in a seed-determined order.

### Hostile actions

The action is untrusted code. Three hostile shapes are graded, and each must
produce `reward == 0.0` within `HOSTILE_S` seconds with the judge still
running and the task bank byte-identical afterwards:

| shape | what it does | control that must stop it |
|---|---|---|
| infinite loop | `while True: pass` | wall-clock timeout -> `SIGKILL` on the process group; `RLIMIT_CPU` |
| fork bomb | spawns children until refused | `RLIMIT_NPROC`; the process group is killed as a unit |
| file deleter | `shutil.rmtree` of its working directory | each action runs in a throwaway directory the harness owns; the harness still reports `0.0` |

## The artifact

`examples/good/` is the reference artifact — a directory holding

```
code_task_env.py        # the environment
policy_outputs.jsonl    # 20 lines: {"task_id": "t00", "source": "def ..."}
```

`grade.sh` takes that directory. Any drop-in replacement with those two file
names is judged the same way. The artifact is copied into a scratch tree
before grading, so nothing it does can touch `judge/` or `tasks/`.

## Acceptance oracle

The judge never trusts the artifact's account of itself. Four oracles:

1. **The judge's own reference implementations** (`judge/oracle/reference.py`)
   — independent code for all 20 tasks, used to validate the bank and to
   recompute, test by test, the reward every action *should* get.
2. **The judge's own runner** (`judge/runner.py`) — its own subprocess
   launcher with its own limits, used to score actions independently of the
   environment under test. `partial_exact` compares the environment's reward
   to this number, exactly, for 20 scripted partial solutions.
3. **`gymnasium` itself** — `isinstance(env, gymnasium.Env)`, space
   containment of every observation, and the 5-tuple `step` return shape.
4. **Checksums** — of `judge/` before and after, and of `tasks/tasks.json`
   across the hostile-action gate, so no artifact can edit its own rules or
   the bank it is graded against.

## Gates

`judge/grade.sh <artifact-dir> [--seed N] [--json out.json]` prints exactly
one JSON verdict object and exits 0 only if every gate passes. `P` = measured,
`R` = rule.

| # | gate | what is measured | pass rule |
|---|---|---|---|
| 1 | `bank_valid` | 100 stored `expect` values vs `judge/oracle/reference.py` | 100/100 agree |
| 2 | `artifact_valid` | `policy_outputs.jsonl` parses; `code_task_env.py` imports | 20/20 tasks covered, each source non-empty and defines its `entry`; module imports clean |
| 3 | `gymnasium_api` | `isinstance(env, gymnasium.Env)`; `observation_space.contains(obs)` after `reset` and after each `step`; `step` returns a 5-tuple of the right types | all hold |
| 4 | `reward_reference` | env reward for the 20 artifact solutions | `== 1.0` for all 20 |
| 5 | `partial_exact` | env reward for 20 scripted partial solutions vs `judge/runner.py` | all 20 equal, exactly, `abs(diff) == 0.0` |
| 6 | `reset_isolation` | reward of a full episode after a hostile episode, vs a fresh env | identical for all 20 tasks |
| 7 | `reset_determinism` | task-id sequence from `reset(seed=S)` in 3 fresh envs; and for 2 other seeds | the 3 sequences are identical; the seeds give ≥ 2 distinct sequences |
| 8 | `reward_determinism` | reward for the same code, 3 times, same env, same task | bit-identical |
| 9 | `hostile_zero` | reward for infinite-loop, fork-bomb and file-deleting actions | `== 0.0` for all 3, each within `HOSTILE_S`; judge alive; bank sha256 unchanged |
| 10 | `no_leak` | obs + info JSON vs the 100 hidden test values and the exact key sets | no hidden test value present; key sets exact |
| 11 | `throughput` | rollouts/s over `ROLLOUTS` episodes with reference solutions | `>= THROUGHPUT_MIN` |
| 12 | `judge_intact` | sha256 of every file under `judge/`, before vs after | identical |

A **rollout** is one full episode: 20 steps, one per task.

### Numeric constants

Command line carries only `--seed` and `--json`. Everything else is an
environment variable read by `grade.sh`:

| constant | default | meaning |
|---|---|---|
| `N_TASKS` | 20 | tasks per episode |
| `TESTS_PER_TASK` | 5 | hidden tests per task |
| `STEP_TIMEOUT_S` | 3.0 | wall-clock limit for one action |
| `HOSTILE_S` | 20.0 | wall-clock limit for one hostile action, and the gate's ceiling |
| `ROLLOUTS` | 10 | episodes timed by the throughput gate |
| `THROUGHPUT_MIN` | 0.5 | rollouts/s floor (10 steps/s) |
| `RLIMIT_AS_MB` | 256 | address-space cap per action |
| `RLIMIT_CPU_S` | 2 | CPU-seconds cap per action |
| `RLIMIT_NPROC` | 64 | processes cap per action (fork-bomb control) |
| `RLIMIT_FSIZE_MB` | 8 | largest file an action may write |
| `RLIMIT_NOFILE` | 256 | open-file cap per action |

The defaults are the values every number in README.md and RECEIPT.md was
produced with.

## Determinism

`grade.sh` run twice with the same `--seed` prints byte-identical verdict
JSON apart from the `timing` key (wall clock, elapsed seconds, throughput
sample timestamps). `selftest.sh` checks this. Every random choice in the
judge and in the environment takes `--seed`; the environment's own task order
comes from `random.Random(seed)` seeded per episode, never from the global
`random` module and never from the clock.

## Known-bad artifact family

`judge/mutants.py` generates ≥ 5 mutants from `examples/good/` by exact
single-string edit, so each mutant differs from the good artifact by one
edit and a kill is evidence about that one defect:

| mutant | edit | gate that must fail |
|---|---|---|
| `leak-hidden-tests` | observation gains a `tests` key carrying the hidden cases | `no_leak` |
| `no-reset` | `reset` keeps the previous episode's counters | `reset_isolation` |
| `no-timeout` | subprocess timeout dropped, so an infinite loop runs to `RLIMIT_CPU` uncaught | `hostile_zero` |
| `partial-wrong` | reward is `1.0` if any test passed, else `0.0` | `partial_exact` |
| `nondeterministic-seed` | task order drawn from the unseeded global `random` | `reset_determinism` |
| `reward-off-by-one` | reward is `passed / (total + 1)` | `reward_reference` |
| `no-rlimits` | `preexec_fn` dropped, so the fork bomb is not capped | `hostile_zero` |
| `api-broken` | `step` returns a 4-tuple | `gymnasium_api` |

`judge/selftest.sh` runs the good artifact (must pass), proves determinism,
runs every mutant (each must fail at least one gate), prints the kill rate
and exits non-zero if the good artifact fails or the kill rate is below 90 %.

## What this demo does not prove

- **Not a security claim.** `resource.setrlimit` and `SIGKILL` on a process
  group are process hygiene. They do not isolate the filesystem, the network
  or the kernel. A user running untrusted code for real needs a sandbox or a
  container; this environment is what you point *at* one, not a replacement
  for one.
- The three hostile shapes are the three the gate scripts. There is no claim
  about other shapes (memory bombs past `RLIMIT_AS`, `/proc` games, symlink
  escapes, resource exhaustion by many small processes under `RLIMIT_NPROC`).
- The 20 tasks are toy exercises chosen so that a correct solution is a few
  lines and the reward is unambiguous. Difficulty, coverage and
  discriminative power against a real model are not measured here.
- No model is evaluated, so nothing here says anything about how hard the
  tasks are or how a policy would score.
- Throughput is measured on one 2 vCPU / ~4 GB machine. It is a sanity floor,
  not a performance claim about any other host.
- A passing artifact is an environment that behaves as specified. It is not
  the environment you would ship: no logging, no retries, no batch stepping,
  no vectorisation, no render mode.

## Tolerances for independent reproduction

`REPRODUCE.md` records a second agent's numbers. They must match RECEIPT.md
within:

| quantity | tolerance |
|---|---|
| every gate verdict (pass/fail) | exact |
| `tests_passed`, `tests_total`, all counts | exact |
| all rewards | exact (`abs(diff) == 0.0`) |
| kill rate | exact |
| wall times, throughput | ±50 %, and throughput must clear `THROUGHPUT_MIN` |
| tool versions | exact |
