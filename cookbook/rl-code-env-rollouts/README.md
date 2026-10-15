# rl-code-env-rollouts: a verifiable-reward code environment

An agent builds the harness that RL and eval work is actually done with: a
`gymnasium` environment over 20 small programming tasks where the action is
Python source, `step()` runs it in a locked-down subprocess (wall-clock
timeout + POSIX rlimits), and the reward is the exact fraction of hidden
tests passed — never the code's own opinion of itself. A judge the
environment cannot fool then drives it: reference solutions must score
exactly 1.0, 20 scripted *partial* solutions must score exactly k/5 as
recomputed by the judge's own independent runner, the same input must give a
bit-identical reward three times, an infinite loop / fork bomb /
file-deleting action must score 0.0 with the judge still standing, and
nothing about the hidden tests may ever reach the observation. Eight
single-edit mutants prove the judge can fail.

Why a sandbox: the whole point of this environment is to execute untrusted
code. An agent iterating on it will feed it infinite loops, fork bombs and
file-deleting programs *on purpose*. That belongs in a disposable machine,
not on the machine you are reading this on.

## Results

| | |
|---|---|
| **Verdict** | ✅ **PASS** — 12/12 gates (seed 20261015) |
| **Reference solutions** | 20/20 score reward exactly 1.0 |
| **Partial credit** | 20/20 match the judge's own runner, `abs(diff) == 0.0` |
| **Reward determinism** | bit-identical across 3 runs |
| **Hostile actions** | infinite loop, fork bomb, file deleter: all 0.0, judge alive, task bank byte-identical |
| **Throughput** | ~0.2 rollouts/s (floor 0.05), 20 steps per rollout |
| **Kill rate** | 8/8 mutants killed (100 %) |

Every number above is from `bash judge/grade.sh examples/good --seed
20261015` and `bash judge/selftest.sh` on 2 vCPU / ~4 GB; see RECEIPT.md.

## What the artifact must do

See [SPEC.md](SPEC.md). The deliverable is a directory holding:

- `code_task_env.py` — `CodeTaskEnv(gymnasium.Env)` over the 20-task bank in
  `tasks/tasks.json`: `step(action)` runs the source in a subprocess with a
  wall-clock timeout and rlimits and returns `reward = passed / total`;
- `policy_outputs.jsonl` — one reference solution per task, one JSON object
  per line.

The judge never trusts the artifact's account of itself. It recomputes every
reward with its own runner, validates the bank against its own reference
implementations (`judge/oracle/reference.py`, sharing no code with the
generator), and checksums `judge/` and the task bank before and after — so
nothing the environment does can edit the rules it is graded by.

## One-command run

```bash
export SBX_API_KEY=<your key>     # https://sbx.agent-next.com/console
python3 cookbook/rl-code-env-rollouts/run.py    # needs the sbx CLI (pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli")
```

`run.py` creates a disposable sandbox (`--timeout-min 30`), clones this repo
at `--ref main` (override with `--ref`), runs `judge/setup.sh` →
`judge/selftest.sh` → `judge/grade.sh examples/good --json`, prints the
verdict JSON and a human summary, and **always** kills the sandbox and
confirms it is gone (`--keep` leaves it up for exploration). Non-zero exit on
any failure, naming the sandbox id if cleanup could not be confirmed.

Without a key, the same steps run on any Debian box with Python ≥ 3.10, from
`cookbook/rl-code-env-rollouts/`:

```bash
bash judge/setup.sh                                  # pinned, sha256-checked wheels into ~/.rl-code-env-rollouts/venv
bash judge/selftest.sh                               # good artifact + 8 single-edit mutants + determinism
bash judge/grade.sh examples/good --seed 20261015 --json /tmp/v.json
```

Measured wall times (2 vCPU / ~4 GB / Python 3.12, see RECEIPT.md):

| step | wall |
|---|---|
| `judge/setup.sh` (fresh venv + pinned wheels) | ~55 s |
| `judge/grade.sh examples/good` | ~80 s (5 rollouts) |
| `judge/selftest.sh` (1 good + 2 determinism + 8 mutants = 11 grade runs) | ~13 min |
| `sbx create` | ~1 s |

## Ask your agent

Paste this into a session with the sandbox plugin enabled:

> In a sandbox, build the verifiable-reward code environment for
> `cookbook/rl-code-env-rollouts` from scratch. Read `SPEC.md` first — it is
> the contract. Then write your own artifact: a `code_task_env.py` defining
> `CodeTaskEnv`, a gymnasium-compatible environment over the 20 tasks in
> `tasks/tasks.json` where `step(action)` runs the given Python source in a
> subprocess with a wall-clock timeout and POSIX resource limits and returns
> `reward = hidden tests passed / hidden tests total`, plus a
> `policy_outputs.jsonl` with one reference solution per task. Iterate with
> `bash judge/grade.sh <your-artifact-dir> --json /tmp/v.json` until all 12
> gates pass, then prove it with `bash judge/selftest.sh` (your environment
> must not pass any of the 8 single-edit mutants' edits — and neither may
> you: do not modify anything under `judge/` or `tasks/`). Show me the final
> verdict JSON: 12/12 gates, 20/20 reference solutions at 1.0, 20/20
> partial rewards exact, all 3 hostile actions at 0.0, and the kill rate.

The agent designs and fixes the artifact itself inside the disposable
sandbox; the judge lives in the repo and grades a scratch copy, so nothing
the agent runs can touch it.

## What this demo does not prove

- **Not a security boundary.** `resource.setrlimit` + `SIGKILL` on a process
  group are process hygiene, not isolation: no filesystem or network
  containment, no seccomp. Running untrusted code for real needs a sandbox
  or a container — this environment is what you point *at* one.
- No policy is trained and no model is evaluated; the "policy outputs" are
  hand-written reference solutions. Difficulty and discriminative power of
  the 20 tasks are not measured.
- The three hostile shapes (infinite loop, fork bomb, file deleter) are the
  three the gate scripts; other shapes are out of scope.
- Throughput is measured on one 2 vCPU host; it is a sanity floor, not a
  performance claim.

## Licensing

The task bank, artifact and judge code are MIT (this repo). The judge's one
third-party dependency is `gymnasium` 1.3.0 (MIT License, PyPI wheel,
sha256-checked in `judge/setup.sh`; its numpy / cloudpickle /
typing-extensions / farama-notifications wheels carry BSD-3-Clause,
BSD-3-Clause, PSF-2.0 and MIT). See `judge/VERSIONS.txt` for what
`setup.sh` actually installed.
