#!/usr/bin/env python3
"""The judge.  Grades one artifact and prints one verdict JSON object.

    python3 drive.py <artifact-dir> [--seed N] [--json out.json]

Every gate compares the artifact against something outside itself: the
judge's own reference implementations (`oracle/reference.py`), the judge's own
action runner (`runner.py`), `gymnasium`'s own API checks, and checksums of
this directory.  Nothing the artifact says about itself is trusted.

The gates are listed in SPEC.md under "Gates".  Exit code is 0 only if every
gate passes.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "oracle"))

import reference   # noqa: E402  (the judge's own implementations)
import runner      # noqa: E402  (the judge's own action runner)

# Numeric constants.  Defaults are the values every number in README.md and
# RECEIPT.md was produced with; SPEC.md documents each one.
N_TASKS = int(os.environ.get("N_TASKS", 20))
TESTS_PER_TASK = int(os.environ.get("TESTS_PER_TASK", 5))
STEP_TIMEOUT_S = float(os.environ.get("STEP_TIMEOUT_S", 3.0))
HOSTILE_S = float(os.environ.get("HOSTILE_S", 20.0))
# The reference environment runs at ~4 steps/s on 2 vCPU (one subprocess per
# step), i.e. ~0.2 rollouts/s.  The floor is 0.05 rollouts/s = 1 step/s: a
# 4x margin under the measured rate, so a slower or loaded host still passes,
# while an environment that is catastrophically slow -- a sleep per step, a
# subprocess storm, a per-step model call -- fails.  See SPEC.md.
ROLLOUTS = int(os.environ.get("ROLLOUTS", 3))
THROUGHPUT_MIN = float(os.environ.get("THROUGHPUT_MIN", 0.05))

SCHEMA = "rl-code-env-rollouts/grade/1"


# --------------------------------------------------------------------------
# Gate bookkeeping
# --------------------------------------------------------------------------
class Verdict:
    def __init__(self):
        self.gates = {}

    def record(self, name, ok, detail):
        self.gates[name] = {"verdict": "pass" if ok else "fail",
                            "detail": detail}

    @property
    def passed(self):
        return all(g["verdict"] == "pass" for g in self.gates.values())


def judge_hash():
    """sha256 over every file under judge/, so an artifact cannot edit the
    rules it is graded by."""
    h = hashlib.sha256()
    for root, dirs, files in os.walk(HERE):
        dirs[:] = sorted(d for d in dirs if d not in ("__pycache__",))
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, HERE)
            h.update(rel.encode())
            with open(path, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def load_env_module(artifact_dir, workdir):
    """Import the artifact's `code_task_env` from a scratch copy.

    The module is imported from a copy, never from the artifact directory, so
    nothing it does at import time can write into `judge/` or `tasks/`.
    Returns `(module, tasks_path, env_path)` or `(None, reason, None)`.
    """
    src = os.path.join(artifact_dir, "code_task_env.py")
    if not os.path.isfile(src):
        return None, "code_task_env.py missing", None
    env_path = os.path.join(workdir, "code_task_env.py")
    shutil.copy2(src, env_path)
    # The bank travels with the module so a relative default path resolves.
    tasks_dst = os.path.join(workdir, "tasks.json")
    shutil.copy2(os.path.join(DEMO, "tasks", "tasks.json"), tasks_dst)
    spec = importlib.util.spec_from_file_location("artifact_env", env_path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except BaseException as exc:
        return None, "import failed: %s: %s" % (type(exc).__name__, exc), None
    if not hasattr(module, "CodeTaskEnv"):
        return None, "module defines no CodeTaskEnv", None
    return module, tasks_dst, env_path


def make_env(module, tasks_path, seed, timeout_s):
    return module.CodeTaskEnv(tasks_path=tasks_path, seed=seed,
                              timeout_s=timeout_s)


def make_env_from_path(env_path, tasks_path, seed, timeout_s):
    """Same as `make_env`, but loads the module from an explicit file path.

    Used where the judge needs a *second* instance of the same artifact in a
    directory it owns, without going through `load_env_module` again.
    """
    spec = importlib.util.spec_from_file_location("artifact_env_%d" % _next_id(),
                                                 env_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CodeTaskEnv(tasks_path=tasks_path, seed=seed,
                              timeout_s=timeout_s)


_ID = [0]


def _next_id():
    _ID[0] += 1
    return _ID[0]


def parse_jsonl(path):
    """Return {task_id: source} from a policy_outputs.jsonl, or raise."""
    out = {}
    with open(path) as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except ValueError as exc:
                raise ValueError("line %d is not JSON: %s" % (lineno, exc))
            if not isinstance(obj, dict) or "task_id" not in obj or "source" not in obj:
                raise ValueError("line %d: need task_id and source" % lineno)
            if not isinstance(obj["source"], str) or not obj["source"].strip():
                raise ValueError("line %d: source is empty" % lineno)
            out[obj["task_id"]] = obj["source"]
    return out


def hidden_fingerprints(bank):
    """Two fingerprints of the hidden tests, for the leak gate.

    Returns `(test_blobs, string_values)`:

    - `test_blobs` are canonical serialisations of each whole test (and of
      its argument list), so a payload that embeds a test verbatim is caught.
    - `string_values` are the hidden values that are strings, compared by
      **exact equality against a string leaf** of the payload, never by
      substring.  Substring matching is deliberately avoided: a two-character
      hidden string such as `li` is a substring of ordinary English in a
      prompt, so a substring rule reports a leak that is not one.  Numbers
      are excluded for the same reason -- `tests_total` is legitimately 5,
      which can coincide with a hidden expectation.

    A hidden value that is neither a whole test nor a string leaf can only
    reach the payload inside `task_id`, `prompt` or `index`, and those are
    compared byte for byte against the bank's own values.
    """
    blobs = set()
    strings = set()
    for task in bank["tasks"]:
        for test in task["tests"]:
            blobs.add(json.dumps({"args": test["args"], "expect": test["expect"]},
                                 sort_keys=True))
            blobs.add(json.dumps(test["args"], sort_keys=True))
            for value in [test["expect"]] + list(test["args"]):
                if isinstance(value, str):
                    strings.add(value)
    return blobs, strings


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------
def gate_bank_valid(v, bank):
    """1. Every stored expectation agrees with the judge's own reference."""
    total = 0
    bad = []
    for task in bank["tasks"]:
        for test in task["tests"]:
            total += 1
            try:
                got = reference.run_entry(task["entry"], test["args"])
            except Exception as exc:
                bad.append("%s: reference raised %s" % (task["id"], exc))
                continue
            if got != test["expect"] or type(got) is not type(test["expect"]):
                bad.append("%s: stored %r, reference %r"
                           % (task["id"], test["expect"], got))
    if len(bank["tasks"]) != N_TASKS:
        v.record("bank_valid", False,
                 "bank has %d tasks, want %d" % (len(bank["tasks"]), N_TASKS))
        return
    ok = not bad and total == N_TASKS * TESTS_PER_TASK
    v.record("bank_valid", ok,
             "%d/%d tests agree with the judge reference"
             % (total - len(bad), total) if not bad
             else "; ".join(bad[:3]))


def gate_artifact_valid(v, artifact_dir, bank):
    """2. policy_outputs.jsonl parses and covers every task; the module imports."""
    solutions = None
    try:
        solutions = parse_jsonl(os.path.join(artifact_dir, "policy_outputs.jsonl"))
    except (OSError, ValueError) as exc:
        v.record("artifact_valid", False, str(exc))
        return None

    ids = [t["id"] for t in bank["tasks"]]
    entries = {t["id"]: t["entry"] for t in bank["tasks"]}
    missing = [i for i in ids if i not in solutions]
    extra = [i for i in solutions if i not in ids]
    nodef = []
    for tid, source in solutions.items():
        if tid in entries:
            tree = None
            try:
                import ast
                tree = ast.parse(source)
            except SyntaxError:
                nodef.append("%s: syntax error" % tid)
                continue
            names = [n.name for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef)]
            if entries[tid] not in names:
                nodef.append("%s: no def %s" % (tid, entries[tid]))
    if missing or extra or nodef:
        detail = []
        if missing:
            detail.append("missing %d: %s" % (len(missing), ",".join(missing[:4])))
        if extra:
            detail.append("unknown %d: %s" % (len(extra), ",".join(extra[:4])))
        if nodef:
            detail.append("; ".join(nodef[:3]))
        v.record("artifact_valid", False, " | ".join(detail))
        return solutions
    v.record("artifact_valid", True,
             "%d/%d tasks covered, sources parse and define their entry"
             % (len(ids), len(ids)))
    return solutions


def gate_gymnasium_api(v, module, tasks_path, seed):
    """3. The environment really is a gymnasium.Env with conformant spaces."""
    import gymnasium
    problems = []
    env = make_env(module, tasks_path, seed, STEP_TIMEOUT_S)
    if not isinstance(env, gymnasium.Env):
        problems.append("not a gymnasium.Env")
    obs, info = env.reset()
    if not env.observation_space.contains(obs):
        problems.append("reset observation outside observation_space")
    if not isinstance(obs, dict):
        problems.append("observation is not a dict")
    for key in ("task_id", "prompt", "index"):
        if key not in obs:
            problems.append("observation missing %r" % key)

    src = "def %s(*a, **k):\n    return None\n" % _entry_for(obs, module, tasks_path)
    out = env.step(src)
    if not isinstance(out, tuple) or len(out) != 5:
        problems.append("step returned %r, want a 5-tuple" % type(out).__name__)
    else:
        o, r, term, trunc, info = out
        if not env.observation_space.contains(o):
            problems.append("step observation outside observation_space")
        if not isinstance(r, float):
            problems.append("reward is %s, want float" % type(r).__name__)
        if not isinstance(term, bool) or not isinstance(trunc, bool):
            problems.append("terminated/truncated are not bool")
        if trunc is not False:
            problems.append("truncated is %r, want False" % trunc)
        if not isinstance(info, dict):
            problems.append("info is not a dict")
    v.record("gymnasium_api", not problems,
             "conformant" if not problems else "; ".join(problems[:4]))


def _entry_for(obs, module, tasks_path):
    """The entry function name for the task in `obs`, from the bank."""
    bank = json.load(open(tasks_path))
    for task in bank["tasks"]:
        if task["id"] == obs.get("task_id"):
            return task["entry"]
    return "solution"


def gate_reward_reference(v, module, tasks_path, seed, solutions, bank):
    """4. Every reference solution scores exactly 1.0."""
    entry = {t["id"]: t["entry"] for t in bank["tasks"]}
    env = make_env(module, tasks_path, seed, STEP_TIMEOUT_S)
    obs, _ = env.reset()
    rewards = {}
    while True:
        tid = obs["task_id"]
        obs2, r, term, trunc, info = env.step(solutions[tid])
        rewards[tid] = r
        if term:
            break
        obs = obs2
    bad = {t: r for t, r in rewards.items() if r != 1.0}
    v.record("reward_reference", not bad,
             "%d/%d reference solutions score exactly 1.0"
             % (len(rewards) - len(bad), len(rewards))
             if not bad else
             "%d wrong: %s" % (len(bad), ", ".join(
                 "%s=%.4g" % kv for kv in list(bad.items())[:4])))


# The 20 scripted partial solutions: each task gets a solution that is
# deliberately right for exactly `k` of its 5 hidden tests, so the expected
# reward is k/5 and the judge can recompute it with its own runner.
def partial_solutions(bank):
    """Yield (task_id, source, expected_passed) for one partial per task."""
    out = []
    for index, task in enumerate(bank["tasks"]):
        want = (index % 5)          # 0,1,2,3,4 cycling over the 20 tasks
        entry = task["entry"]
        tests = task["tests"]
        if want == 0:
            out.append((task["id"], "def %s(*a, **k):\n    raise ValueError()\n"
                        % entry, 0))
            continue
        # A table keyed by the JSON of the args that must succeed, so the
        # candidate passes exactly the first `want` tests and no others.
        table = {}
        for test in tests[:want]:
            table[json.dumps(test["args"])] = test["expect"]
        source = (
            "import json\n"
            "_T = %r\n"
            "def %s(*a, **k):\n"
            "    key = json.dumps(list(a))\n"
            "    if key in _T:\n"
            "        return _T[key]\n"
            "    raise ValueError('not scripted')\n"
        ) % (table, entry)
        out.append((task["id"], source, want))
    return out


def gate_partial_exact(v, module, tasks_path, seed, bank):
    """5. Reward for a partial solution equals the judge's own computation."""
    by_id = {t["id"]: t for t in bank["tasks"]}
    partials = partial_solutions(bank)
    env = make_env(module, tasks_path, seed, STEP_TIMEOUT_S)

    # Group the partials by task, then run one episode whose every action is
    # the partial for the task the environment asks about.
    scripted = {tid: src for tid, src, _ in partials}
    obs, _ = env.reset()
    env_rewards = {}
    while True:
        tid = obs["task_id"]
        obs2, r, term, trunc, info = env.step(scripted[tid])
        env_rewards[tid] = r
        if term:
            break
        obs = obs2

    mismatches = []
    for tid, src, want in partials:
        task = by_id[tid]
        passed, total, oracle = runner.score(task, src, STEP_TIMEOUT_S)
        if passed != want:
            mismatches.append("%s: judge runner passed %d, scripted %d"
                              % (tid, passed, want))
            continue
        got = env_rewards[tid]
        if abs(got - oracle) != 0.0:
            mismatches.append("%s: env %.6f vs judge %.6f" % (tid, got, oracle))
    v.record("partial_exact", not mismatches,
             "%d/%d partial rewards equal the judge's own runner, exactly"
             % (len(partials) - len(mismatches), len(partials))
             if not mismatches else "; ".join(mismatches[:3]))


def gate_reset_isolation(v, env_path, tasks_path, seed, solutions, bank):
    """6. A hostile episode must not change the next episode's rewards.

    The hostile step is run through `hostile_probe.py` -- its own process, its
    own process group -- exactly as the hostile gate does.  It must not run
    inside the judge: an artifact whose kill aims at a process group it shares
    with its caller would otherwise take the judge down, and the judge would
    report its own death as a failure of this gate.
    """
    entry = {t["id"]: t["entry"] for t in bank["tasks"]}

    def full_episode():
        env = make_env_from_path(env_path, tasks_path, seed, STEP_TIMEOUT_S)
        obs, _ = env.reset()
        out = {}
        while True:
            tid = obs["task_id"]
            obs2, r, term, trunc, info = env.step(solutions[tid])
            out[tid] = r
            if term:
                break
            obs = obs2
        return out

    def hostile_step():
        """One hostile action in an isolated probe; returns True if it ran."""
        proc = subprocess.Popen(
            [sys.executable, "-I", os.path.join(HERE, "hostile_probe.py"),
             env_path, tasks_path, str(seed), "infinite-loop",
             str(STEP_TIMEOUT_S)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            preexec_fn=_probe_limits)
        group, session = _probe_identity(proc)
        try:
            proc.communicate(timeout=HOSTILE_S)
        except subprocess.TimeoutExpired:
            _kill_tree(proc, None, group, session)
            return False
        return True

    fresh = full_episode()

    # The same env instance is reused for the hostile episode and the one after
    # it, so a counter that reset() fails to clear shows up in `after`.
    workdir = tempfile.mkdtemp(prefix="rl-iso-")
    try:
        reused_path = os.path.join(workdir, "code_task_env.py")
        shutil.copy2(env_path, reused_path)
        shutil.copy2(os.path.join(DEMO, "tasks", "tasks.json"),
                     os.path.join(workdir, "tasks.json"))
        reused = make_env_from_path(reused_path, tasks_path, seed,
                                    STEP_TIMEOUT_S)
        obs, _ = reused.reset()
        while True:
            tid = obs["task_id"]
            obs2, r, term, trunc, info = reused.step(solutions[tid])
            if term:
                break
            obs = obs2
        # The hostile action goes through the isolated probe, not `reused`.
        hostile_step()
        after = {}
        obs, _ = reused.reset()
        while True:
            tid = obs["task_id"]
            obs2, r, term, trunc, info = reused.step(solutions[tid])
            after[tid] = r
            if term:
                break
            obs = obs2
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    diff = {t: (fresh[t], after[t]) for t in fresh if fresh[t] != after[t]}
    v.record("reset_isolation", not diff,
             "%d/%d rewards identical after a hostile episode"
             % (len(fresh) - len(diff), len(fresh))
             if not diff else
             "%d differ: %s" % (len(diff), ", ".join(
                 "%s %s->%s" % (t, a, b) for t, (a, b) in list(diff.items())[:3])))


def gate_reset_determinism(v, module, tasks_path, seed):
    """7. reset(seed=S) fixes the task order; different seeds differ."""
    def order(s):
        env = make_env(module, tasks_path, s, STEP_TIMEOUT_S)
        obs, _ = env.reset()
        seq = []
        while True:
            seq.append(obs["task_id"])
            src = "def _(*a, **k):\n    return None\n"
            # step needs the right entry name; a wrong one just scores 0 and
            # the order is what we are reading, so drive it with a generic def.
            o, r, term, trunc, info = env.step(src)
            if term:
                break
            obs = o
        return seq

    a = order(seed)
    b = order(seed)
    c = order(seed)
    other1 = order(seed + 1)
    other2 = order(seed + 2)

    same = a == b == c
    distinct = len({tuple(a), tuple(other1), tuple(other2)})
    ok = same and distinct >= 2
    detail = ("3 runs of seed %d identical (%s); %d distinct orders over 3 seeds"
              % (seed, "yes" if same else "NO", distinct))
    v.record("reset_determinism", ok, detail)


def gate_reward_determinism(v, module, tasks_path, seed, solutions):
    """8. The same action on the same task scores identically, 3 times."""
    env = make_env(module, tasks_path, seed, STEP_TIMEOUT_S)
    rewards = []
    for _ in range(3):
        obs, _ = env.reset()
        tid = obs["task_id"]
        o, r, term, trunc, info = env.step(solutions[tid])
        rewards.append(r)
    ok = rewards[0] == rewards[1] == rewards[2]
    v.record("reward_determinism", ok,
             "3 runs give %s" % ("/".join("%.4g" % r for r in rewards))
             if ok else "rewards differ: %s" % rewards)


def gate_hostile_zero(v, artifact_env, tasks_path, seed, bank):
    """9. Infinite loop, fork bomb and file deleter each score exactly 0.0.

    Each action runs in its own process (`hostile_probe.py`), in its own process
    group and session, with a hard wall-clock limit -- so an artifact that never
    returns from `step`, or that fork-bombs, can neither hang the judge nor
    exhaust the machine.  Sibling actions in this list run sequentially, and
    each is swept for leftovers before the next starts.

    Three things are checked per shape, not just the reward:

    - the reward is exactly 0.0;
    - the step returned inside `HOSTILE_S`, and the judge is still running;
    - **nothing the action started is still running.**  An artifact that forks
      children and lets its parent die is not contained, and the gate says so
      rather than absorbing the cost.  The judge cleans up after a failure, but
      a failure it is.

    The task bank's checksum is taken before the first shape and after the last,
    so an artifact that deletes or rewrites the bank it is graded against fails.
    """
    bank_path = os.path.join(DEMO, "tasks", "tasks.json")
    bank_before = sha256_file(bank_path)
    probe = os.path.join(HERE, "hostile_probe.py")

    problems = []
    results = {}
    for shape in ("infinite-loop", "fork-bomb", "file-deleter"):
        # what was running before this action, so a leak is a process that
        # appeared during it rather than something that happened to be there.
        before = _pid_snapshot()
        t0 = time.time()
        proc = subprocess.Popen(
            [sys.executable, "-I", probe, artifact_env, tasks_path,
             str(seed), shape, str(STEP_TIMEOUT_S)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            preexec_fn=_probe_limits)
        # Read the probe's own group and session while she is alive: once
        # communicate() returns she is gone and /proc/<pid> cannot be read.
        group, session = _probe_identity(proc)
        timed_out = False
        try:
            out, _ = proc.communicate(timeout=HOSTILE_S)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc, before, group, session)
            out = ""
        dt = time.time() - t0

        leaked = _leftovers(proc, before)
        if leaked:
            _kill_tree(proc, before, group, session)
            still = [pid for pid in leaked
                     if _state(pid) not in ("Z", "")]
            if still:
                problems.append(
                    "%s: left %d process(es) running after step returned "
                    "(pids %s)"
                    % (shape, len(still), ",".join(str(p) for p in still[:4])))
            results.setdefault(shape, {})["leaked"] = len(leaked)

        if timed_out:
            problems.append("%s: judge killed it after %.0fs (step never "
                            "returned)" % (shape, HOSTILE_S))
            results.setdefault(shape, {}).update(
                {"reward": None, "wall_s": round(dt, 3), "timed_out": True})
            continue
        try:
            payload = json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            problems.append("%s: probe produced no verdict" % shape)
            results.setdefault(shape, {}).update(
                {"reward": None, "wall_s": round(dt, 3), "timed_out": False})
            continue
        reward = payload.get("reward")
        results.setdefault(shape, {}).update(
            {"reward": reward, "wall_s": round(dt, 3),
             "timed_out": bool(payload.get("timed_out"))})
        if reward != 0.0:
            problems.append("%s: reward %r, want 0.0" % (shape, reward))
        if dt > HOSTILE_S:
            problems.append("%s: took %.1fs > %.0fs" % (shape, dt, HOSTILE_S))

    if sha256_file(bank_path) != bank_before:
        problems.append("task bank changed during the hostile gate")
    v.record("hostile_zero", not problems,
             "3 hostile actions scored 0.0, judge alive, bank unchanged"
             if not problems else "; ".join(problems[:3]))
    return results


def _leftovers(proc, before):
    """Processes the hostile action left running, excluding the judge's own.

    `before` is the pid snapshot taken just before the probe was spawned, so
    anything alive now that was not alive then was started by the action.  This
    is the only membership test that survives an artifact that reshapes its own
    process groups: a fork bomb's children are orphaned and reparented to pid 1
    the moment their parent dies, so neither their parent nor their group is
    still there to walk.  The judge's own lineage is excluded, so the judge's
    helpers are never mistaken for a leak.
    """
    mine = _own_lineage()
    out = []
    for pid in _all_pids():
        if pid in before or pid in mine or pid == 1:
            continue
        if pid == proc.pid or pid == os.getpid():
            continue
        if _state(pid) in ("Z", ""):
            continue
        out.append(pid)
    return out


# /proc/<pid>/stat field names, in order, counted after the "(comm)" part.
_STATE, _PPID, _PGID, _SID = 1, 2, 3, 4


def _field(pid, index):
    """A field of /proc/<pid>/stat, 1-based after the comm.  `None` if the
    process is gone or its stat cannot be parsed -- an unreadable process is
    assumed gone, never blamed on the artifact."""
    try:
        with open("/proc/%d/stat" % pid) as fh:
            fields = fh.read().rsplit(")", 1)[1].split()
        return int(fields[index - 1])
    except (OSError, ValueError, IndexError):
        return None


def _state(pid):
    try:
        with open("/proc/%d/stat" % pid) as fh:
            return fh.read().rsplit(")", 1)[1].split()[_STATE - 1]
    except (OSError, ValueError, IndexError):
        return ""


def _all_pids():
    try:
        return [int(e) for e in os.listdir("/proc") if e.isdigit()]
    except OSError:
        return []


def _pid_snapshot():
    """Every live, non-zombie pid at this instant."""
    return set(pid for pid in _all_pids() if _state(pid) not in ("Z", ""))


def _own_lineage():
    """This process and every ancestor of it, so none of them is ever treated
    as something the artifact started."""
    out = {os.getpid()}
    cursor = _field(os.getpid(), _PPID)
    seen = set()
    while cursor and cursor > 1 and cursor not in seen:
        seen.add(cursor)
        out.add(cursor)
        cursor = _field(cursor, _PPID)
    return out


def _descendants(root_pid):
    """Every pid descended from `root_pid` by parentage, excluding the judge.

    Walks /proc from the root outward, so it works even when an intermediate
    parent has already died and its children have been reparented to pid 1 --
    the shape a fork bomb leaves behind, and the reason a purely group-based
    kill is not enough.
    """
    parents = {}
    for pid in _all_pids():
        ppid = _field(pid, _PPID)
        if ppid is None:
            continue
        parents[pid] = ppid
    mine = _own_lineage()
    out = []
    for pid, ppid in parents.items():
        if pid == root_pid or pid in mine:
            continue
        seen = set()
        cursor = ppid
        while cursor and cursor not in seen:
            seen.add(cursor)
            if cursor == root_pid:
                out.append(pid)
                break
            cursor = parents.get(cursor, 0)
    return out


def _probe_limits():
    """Host-safety limits for the hostile probe: its own process group, so the
    judge can kill every descendant at once, and a CPU cap as a second net."""
    import resource
    try:
        resource.setrlimit(resource.RLIMIT_CPU,
                           (int(HOSTILE_S) + 5, int(HOSTILE_S) + 5))
    except (ValueError, OSError):
        pass
    os.setsid()


# The judge's own process group.  A group kill is the only way to take out a
# fork bomb's descendants at once, so the hostile gate does use killpg -- but
# it must never aim killpg at a group that contains the judge itself.  That is
# exactly what happens when the artifact under test forgets setsid(): the child
# then shares the judge's group, and killing the group kills the judge.
JUDGE_PGID = os.getpgrp()


def _kill_tree(proc, before=None, group=None, session=None):
    """Kill the probe and everything she spawned, without ever touching the
    judge's own process group.

    `group` and `session` are the probe's own ids, captured by `_probe_identity`
    while she was still alive.  They are what actually reaches a fork bomb: its
    parent is killed, the kernel reparents the children to pid 1, and their
    group and session still point at the dead probe -- which is the only thing
    left that identifies them as hers.

    Order: the process-group sweep, then the session sweep, then her descendants
    by parentage, then the probe herself.  A sweep is never aimed at the judge's
    own group or session, and `before` -- the pid snapshot from before she
    started -- bounds every sweep so it cannot reach the judge's own children.
    """
    mine = _own_lineage()
    own_group = JUDGE_PGID
    own_session = _session_id(os.getpid())
    targets = set()
    for index, theirs, ours in ((_PGID, group, own_group),
                                (_SID, session, own_session)):
        if theirs is None or theirs == ours:
            continue
        for pid in _all_pids():
            if pid in mine or (before and pid in before):
                continue
            if _field(pid, index) == theirs:
                targets.add(pid)
    for pid in _descendants(proc.pid):
        if pid in mine:
            continue
        targets.add(pid)

    for pid in targets:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        proc.kill()
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _session_id(pid):
    """The session id of `pid`, or None if it is gone."""
    return _field(pid, _SID)


def _probe_identity(proc):
    """The group and session the probe started in, captured while it is alive.

    This is read immediately after `Popen` returns, because by the time the
    judge needs it the probe is usually gone: `communicate` having returned means
    `/proc/<pid>` is closed, and a reaped process has no group to read.  The
    probe's `preexec_fn` calls `os.setsid()`, so both numbers are hers.
    """
    return (_field(proc.pid, _PGID), _field(proc.pid, _SID))


def gate_no_leak(v, module, tasks_path, seed, solutions, bank):
    """10. The observation carries only the visible task metadata.

    Three independent checks, because a leak can take three shapes:

    1. **Key sets** -- exactly `{task_id, prompt, index}` in the observation,
       exactly the six documented keys in `info`.  A `tests` field of any
       spelling fails here.
    2. **Field values** -- `task_id`, `prompt` and `index` must equal, byte
       for byte, the bank's own values for the task the observation claims to
       describe.  A hidden case smuggled into `prompt` fails here.
    3. **Fingerprints** -- no whole hidden test, and no hidden *string*
       value, may appear anywhere in the serialised payload.
    """
    blobs, hidden_strings = hidden_fingerprints(bank)
    by_id = {t["id"]: t for t in bank["tasks"]}
    obs_keys = {"task_id", "prompt", "index"}
    info_keys = {"task_id", "tests_total", "tests_passed", "exit_code",
                 "timed_out", "wall_s"}
    problems = []

    def check_obs(obs, where):
        if not isinstance(obs, dict):
            problems.append("%s: observation is not a dict" % where)
            return
        if set(obs) != obs_keys:
            problems.append("%s: observation keys %s, want %s"
                            % (where, sorted(obs), sorted(obs_keys)))
            return
        task = by_id.get(obs.get("task_id"))
        if task is None:
            problems.append("%s: task_id %r is not in the bank"
                            % (where, obs.get("task_id")))
            return
        if obs["prompt"] != task["prompt"]:
            problems.append("%s: prompt for %s is not the bank's prompt"
                            % (where, task["id"]))
        if obs["index"] != [t["id"] for t in bank["tasks"]].index(task["id"]):
            problems.append("%s: index for %s is %r, want %d"
                            % (where, task["id"], obs["index"],
                               [t["id"] for t in bank["tasks"]].index(task["id"])))

    def check_payload(payload, where):
        # A whole hidden test embedded verbatim: matched as a substring of the
        # serialised payload, because that is exactly the leak shape (a `tests`
        # field added to the observation).
        text = json.dumps(payload, sort_keys=True)
        for blob in blobs:
            if blob in text:
                problems.append("%s: a hidden test appears verbatim" % where)
                return
        # A hidden string carried as a leaf: compared by exact equality, so a
        # short hidden string that happens to occur inside a prompt is not
        # mistaken for a leak.
        for leaf in _string_leaves(payload):
            if leaf in hidden_strings:
                problems.append("%s: hidden string %r carried as a value"
                                % (where, leaf))
                return

    env = make_env(module, tasks_path, seed, STEP_TIMEOUT_S)
    obs, info = env.reset()
    if set(info) != {"task_id"}:
        problems.append("reset info keys %s" % sorted(info))
    check_obs(obs, "reset")
    check_payload({"obs": obs, "info": info}, "reset")

    checked = 0
    while True:
        tid = obs["task_id"]
        o, r, term, trunc, info = env.step(solutions[tid])
        if set(info) != info_keys:
            problems.append("step info keys %s, want %s"
                            % (sorted(info), sorted(info_keys)))
        check_obs(o, "step %s" % tid)
        check_payload({"obs": o, "info": info}, "step %s" % tid)
        checked += 1
        if term:
            break
        obs = o
    v.record("no_leak", not problems,
             "%d observations: keys exact, fields match the bank, no hidden value"
             % checked if not problems else "; ".join(problems[:3]))


def _string_leaves(payload):
    """Every string that appears as a value (not a key) anywhere in `payload`."""
    out = []
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
        elif isinstance(node, str):
            out.append(node)
    return out


def gate_throughput(v, module, tasks_path, seed, solutions):
    """11. Rollouts per second over ROLLOUTS full episodes.

    The gate verdict is the comparison against the floor; the *measured* rate
    and wall time are returned to the caller and land under the verdict's
    `timing` key, so two same-seed runs still produce byte-identical gate
    output.  See SPEC.md "Determinism".
    """
    env = make_env(module, tasks_path, seed, STEP_TIMEOUT_S)
    t0 = time.time()
    steps = 0
    for _ in range(ROLLOUTS):
        obs, _ = env.reset()
        while True:
            tid = obs["task_id"]
            o, r, term, trunc, info = env.step(solutions[tid])
            steps += 1
            if term:
                break
            obs = o
    dt = time.time() - t0
    rate = ROLLOUTS / dt if dt > 0 else float("inf")
    ok = rate >= THROUGHPUT_MIN
    v.record("throughput", ok,
             "%d rollouts of %d steps cleared the %.2f rollouts/s floor: %s"
             % (ROLLOUTS, N_TASKS, THROUGHPUT_MIN, "yes" if ok else "NO"))
    return {"rollouts": ROLLOUTS, "steps": steps,
            "wall_s": round(dt, 3), "rollouts_per_s": round(rate, 4),
            "steps_per_s": round(steps / dt, 3) if dt > 0 else None}


# --------------------------------------------------------------------------
def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--json")
    args = ap.parse_args(argv[1:])

    artifact = os.path.abspath(args.artifact)
    if not os.path.isdir(artifact):
        print("drive: not a directory: %s" % artifact, file=sys.stderr)
        return 2

    t_start = time.time()
    v = Verdict()
    judge_before = judge_hash()
    throughput_measure = None
    hostile_measure = None

    # The artifact is copied into scratch before it is imported, so nothing it
    # does at import time can touch judge/ or tasks/.
    work = tempfile.mkdtemp(prefix="rl-grade-")
    try:
        bank = json.load(open(os.path.join(DEMO, "tasks", "tasks.json")))
        gate_bank_valid(v, bank)

        module, tasks_path, env_path = load_env_module(artifact, work)
        if module is None:
            v.record("artifact_valid", False, tasks_path)
            for name in ("gymnasium_api", "reward_reference", "partial_exact",
                         "reset_isolation", "reset_determinism",
                         "reward_determinism", "hostile_zero", "no_leak",
                         "throughput"):
                v.record(name, False, "skipped: %s" % tasks_path)
            solutions = None
        else:
            solutions = gate_artifact_valid(v, artifact, bank)
            if solutions is None:
                for name in ("gymnasium_api", "reward_reference",
                             "partial_exact", "reset_isolation",
                             "reset_determinism", "reward_determinism",
                             "hostile_zero", "no_leak", "throughput"):
                    v.record(name, False, "skipped: no usable policy_outputs.jsonl")
            else:
                try:
                    gate_gymnasium_api(v, module, tasks_path, args.seed)
                except BaseException as exc:
                    v.record("gymnasium_api", False,
                             "%s: %s" % (type(exc).__name__, exc))
                for name, fn in (
                    ("reward_reference", lambda: gate_reward_reference(
                        v, module, tasks_path, args.seed, solutions, bank)),
                    ("partial_exact", lambda: gate_partial_exact(
                        v, module, tasks_path, args.seed, bank)),
                    ("reset_isolation", lambda: gate_reset_isolation(
                        v, env_path, tasks_path, args.seed, solutions, bank)),
                    ("reset_determinism", lambda: gate_reset_determinism(
                        v, module, tasks_path, args.seed)),
                    ("reward_determinism", lambda: gate_reward_determinism(
                        v, module, tasks_path, args.seed, solutions)),
                    ("hostile_zero", lambda: gate_hostile_zero(
                        v, env_path, tasks_path, args.seed, bank)),
                    ("no_leak", lambda: gate_no_leak(
                        v, module, tasks_path, args.seed, solutions, bank)),
                    ("throughput", lambda: gate_throughput(
                        v, module, tasks_path, args.seed, solutions)),
                ):
                    try:
                        result = fn()
                        if name == "throughput":
                            throughput_measure = result
                        elif name == "hostile_zero":
                            hostile_measure = result
                    except BaseException as exc:
                        v.record(name, False,
                                 "%s: %s" % (type(exc).__name__, exc))

        judge_after = judge_hash()
        v.record("judge_intact", judge_before == judge_after,
                 "judge checksum unchanged" if judge_before == judge_after
                 else "judge/ was modified during the run")

        elapsed = time.time() - t_start
        verdict = {
            "schema": SCHEMA,
            "artifact": artifact,
            "seed": args.seed,
            "pass": v.passed,
            "gates_passed": sum(1 for g in v.gates.values()
                                if g["verdict"] == "pass"),
            "gates_total": len(v.gates),
            "gates": v.gates,
            "constants": {
                "n_tasks": N_TASKS, "tests_per_task": TESTS_PER_TASK,
                "step_timeout_s": STEP_TIMEOUT_S, "hostile_s": HOSTILE_S,
                "rollouts": ROLLOUTS, "throughput_min": THROUGHPUT_MIN,
            },
            "timing": {
                "generated_at": _utc_now(),
                "elapsed_s": round(elapsed, 3),
                "throughput": throughput_measure,
                "hostile": hostile_measure,
            },
        }
        text = json.dumps(verdict, indent=2, sort_keys=True)

        print()
        print("verdict: %s  (%d/%d gates)"
              % ("PASS" if v.passed else "FAIL",
                 verdict["gates_passed"], verdict["gates_total"]))
        for name in sorted(v.gates):
            g = v.gates[name]
            print("  %-20s %-4s  %s" % (name, g["verdict"], g["detail"]))
        print()
        print(text)
        if args.json:
            with open(args.json, "w") as fh:
                fh.write(text + "\n")
        return 0 if v.passed else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _utc_now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
