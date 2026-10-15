"""A gymnasium environment whose reward is a fraction of hidden tests passed.

`CodeTaskEnv` steps over a bank of small programming tasks.  The action is
Python source defining the current task's entry function; the environment
writes it to a throwaway directory, runs it in a subprocess with a wall-clock
timeout and POSIX resource limits, and scores it against the task's hidden
tests.  The reward is `tests_passed / tests_total`, exactly.

    env = CodeTaskEnv(tasks_path="tasks/tasks.json", seed=20261015)
    obs, info = env.reset()
    obs, reward, terminated, truncated, info = env.step(source)

This file is the artifact the judge grades.  It is deliberately plain: the
subprocess is the whole isolation story, and the SPEC says so.
"""

import json
import os
import random
import resource
import shutil
import signal
import string
import subprocess
import sys
import tempfile
import time

import gymnasium

# One action's resource envelope.  See SPEC.md "Numeric constants": these are
# the defaults the environment uses when its caller does not override them.
RLIMIT_AS_MB = 256
RLIMIT_CPU_S = 2
RLIMIT_NPROC = 64
RLIMIT_FSIZE_MB = 8
RLIMIT_NOFILE = 256

STEP_TIMEOUT_S = 3.0

# The child runs this.  It reads a JSON job on stdin, imports the candidate
# module by path, calls the entry function on each test's args and prints one
# JSON result on stdout.  Nothing else is printed, so the parent can parse it.
CHILD = r'''
import importlib.util, json, sys

job = json.load(sys.stdin)
spec = importlib.util.spec_from_file_location("candidate", job["module"])
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except BaseException as exc:
    print(json.dumps({"load_error": "%s: %s" % (type(exc).__name__, exc)}))
    sys.exit(0)

fn = getattr(mod, job["entry"], None)
if not callable(fn):
    print(json.dumps({"load_error": "no callable %r" % job["entry"]}))
    sys.exit(0)

passed = 0
for test in job["tests"]:
    try:
        got = fn(*test["args"])
    except BaseException:
        continue
    if got == test["expect"] and type(got) is type(test["expect"]):
        passed += 1
print(json.dumps({"passed": passed}))
'''


def _apply_limits():
    """Set the child's resource limits, then exec.  Runs between fork and
    exec in the child, so it must not allocate or print."""
    mb = 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (RLIMIT_AS_MB * mb, RLIMIT_AS_MB * mb))
    resource.setrlimit(resource.RLIMIT_CPU, (RLIMIT_CPU_S, RLIMIT_CPU_S))
    resource.setrlimit(resource.RLIMIT_FSIZE, (RLIMIT_FSIZE_MB * mb, RLIMIT_FSIZE_MB * mb))
    resource.setrlimit(resource.RLIMIT_NOFILE, (RLIMIT_NOFILE, RLIMIT_NOFILE))
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (RLIMIT_NPROC, RLIMIT_NPROC))
    except (ValueError, OSError):
        # RLIMIT_NPROC needs privilege on some kernels; the timeout and the
        # process-group kill still bound a fork bomb.
        pass
    os.setsid()


class CodeTaskEnv(gymnasium.Env):
    """Gymnasium environment over the task bank.  See the module docstring."""

    metadata = {"render_modes": []}

    def __init__(self, tasks_path=None, seed=None, timeout_s=STEP_TIMEOUT_S):
        super().__init__()
        if tasks_path is None:
            tasks_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      os.pardir, "tasks", "tasks.json")
        with open(tasks_path) as fh:
            bank = json.load(fh)
        self.tasks = bank["tasks"]
        self.timeout_s = float(timeout_s)
        self._seed = seed
        self._rng = None
        self._order = []
        self._pos = 0

        # The observation is exactly the visible task metadata.  The hidden
        # tests are never part of it -- see gate `no_leak`.  The charset is
        # printable ASCII, which covers every id and prompt in the bank (the
        # space, punctuation and backticks included) and every Python source
        # an action can carry.
        self.observation_space = gymnasium.spaces.Dict({
            "task_id": gymnasium.spaces.Text(max_length=64, min_length=1,
                                             charset=string.printable),
            "prompt": gymnasium.spaces.Text(max_length=512, min_length=1,
                                            charset=string.printable),
            "index": gymnasium.spaces.Discrete(len(self.tasks)),
        })
        self.action_space = gymnasium.spaces.Text(
            max_length=65536, min_length=0, charset=string.printable)

    # -------------------------------------------------------------- episode ---
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._seed = seed
        # Order comes from a local Random, never the global module, so two
        # environments cannot perturb each other.
        rng = random.Random(self._seed)
        self._order = list(range(len(self.tasks)))
        rng.shuffle(self._order)
        self._pos = 0
        return self._observation(), {"task_id": self.tasks[self._order[0]]["id"]}

    def _observation(self):
        """The observation for the task at the current position.  The position
        is clamped to the last task, so the terminal step -- which advances
        past the end -- still returns a real observation the space accepts."""
        pos = min(self._pos, len(self._order) - 1)
        task = self.tasks[self._order[pos]]
        return {"task_id": task["id"], "prompt": task["prompt"],
                "index": self._order[pos]}

    # ----------------------------------------------------------------- step ---
    def step(self, action):
        """Answer the current task.  The returned observation describes the
        *next* task to answer -- except on the terminal step, where there is
        no next task and the observation repeats the one just answered.  A
        normal rollout loop therefore ignores the observation when
        `terminated` is True."""
        if self._pos >= len(self._order):
            raise RuntimeError("step() called after the episode ended; call reset()")
        task = self.tasks[self._order[self._pos]]

        if not isinstance(action, str):
            raise TypeError("action must be a str of Python source, got %r"
                            % type(action).__name__)

        passed, total, exit_code, timed_out, wall_s = self._run(task, action)
        reward = passed / total

        terminated = self._pos == len(self._order) - 1
        self._pos += 1
        obs = self._observation()

        info = {"task_id": task["id"], "tests_total": total,
                "tests_passed": passed, "exit_code": exit_code,
                "timed_out": timed_out, "wall_s": wall_s}
        return obs, float(reward), terminated, False, info

    # ------------------------------------------------------------- executor ---
    def _run(self, task, source):
        """Run one action in a locked-down subprocess.  Returns
        (passed, total, exit_code, timed_out, wall_s)."""
        total = len(task["tests"])
        workdir = tempfile.mkdtemp(prefix="cte-")
        try:
            module = os.path.join(workdir, "candidate.py")
            with open(module, "w") as fh:
                fh.write(source)
            job = json.dumps({"module": module, "entry": task["entry"],
                              "tests": task["tests"]})

            t0 = time.time()
            proc = subprocess.Popen(
                [sys.executable, "-I", "-c", CHILD],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, cwd=workdir, text=True,
                preexec_fn=_apply_limits,
            )
            timed_out = False
            try:
                out, _ = proc.communicate(job, timeout=self.timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._kill(proc)
                out = ""
            wall_s = time.time() - t0

            passed = 0
            if out:
                try:
                    result = json.loads(out.strip().splitlines()[-1])
                    passed = int(result.get("passed", 0))
                except (ValueError, IndexError):
                    passed = 0
            if timed_out:
                passed = 0
            return passed, total, proc.returncode, timed_out, wall_s
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    @staticmethod
    def _kill(proc):
        """Kill the child's whole process group, so a fork bomb's children die
        with it, then reap it."""
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    def close(self):
        pass
