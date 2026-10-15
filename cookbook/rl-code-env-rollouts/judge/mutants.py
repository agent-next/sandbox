#!/usr/bin/env python3
"""Generate the known-bad artifacts the self-test uses.

Each mutant is the good artifact with exactly one edit, so a mutant that
fails is evidence the judge can see *that* class of defect and nothing else.
Edits are keyed by a unique substring of the target text rather than by line
number, so the generator survives reasonable edits to the good source.

Usage:
    mutants.py list                 print the mutant names
    mutants.py make <name> <dest>   write one mutant tree to <dest>
    mutants.py make-all <destdir>   write every mutant tree
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = os.path.join(os.path.dirname(HERE), "examples", "good")
ENV_FILE = "code_task_env.py"


def edit(text, needle, replacement):
    """Replace the single occurrence of `needle`; fail loudly otherwise.

    A silently half-applied mutant is worse than no mutant: if the needle is
    missing or ambiguous the generator stops rather than emit a mutant that
    is really the good artifact.
    """
    hits = text.count(needle)
    if hits == 0:
        raise SystemExit("mutant edit failed: no match for %r" % needle)
    if hits > 1:
        raise SystemExit("mutant edit failed: %d matches for %r" % (hits, needle))
    return text.replace(needle, replacement, 1)


# --------------------------------------------------------------------------
# One function per mutant.  Each takes the good `code_task_env.py` source and
# returns the edited source.
# --------------------------------------------------------------------------
def m_leak_hidden_tests(src):
    """The observation carries the hidden tests, so the agent being evaluated
    can read the answers instead of solving the task."""
    return edit(
        src,
        '        return {"task_id": task["id"], "prompt": task["prompt"],\n'
        '                "index": self._order[pos]}',
        '        return {"task_id": task["id"], "prompt": task["prompt"],\n'
        '                "index": self._order[pos], "tests": task["tests"]}')


def m_no_reset(src):
    """reset() keeps the previous episode's position, so a second episode
    starts where the first ended instead of at task zero."""
    return edit(
        src,
        "        self._order = list(range(len(self.tasks)))\n"
        "        rng.shuffle(self._order)\n"
        "        self._pos = 0",
        "        self._order = list(range(len(self.tasks)))\n"
        "        rng.shuffle(self._order)")


def m_no_timeout(src):
    """The wall-clock timeout is dropped, so an infinite loop is only stopped
    by RLIMIT_CPU -- and the harness treats the resulting kill as a normal
    zero, not as a timeout it must enforce."""
    return edit(src, "timeout=self.timeout_s", "timeout=None")


def m_partial_wrong(src):
    """Reward is all-or-nothing: 1.0 if any test passed, else 0.0.  A partial
    solution is graded as a full one."""
    return edit(src, "        reward = passed / total",
                "        reward = 1.0 if passed else 0.0")


def m_nondeterministic_seed(src):
    """The task order is drawn from the unseeded global RNG, so the same seed
    gives a different order on every process."""
    return edit(src,
                "        rng = random.Random(self._seed)",
                "        rng = random.Random()")


def m_reward_off_by_one(src):
    """Reward divides by one test too many, so even a perfect solution scores
    0.8 instead of 1.0."""
    return edit(src, "        reward = passed / total",
                "        reward = passed / (total + 1)")


def m_no_rlimits(src):
    """The child's resource limits are never applied, so a fork bomb is not
    capped at RLIMIT_NPROC."""
    return edit(src, "                preexec_fn=_apply_limits,",
                "                preexec_fn=None,")


def m_api_broken(src):
    """step returns a 4-tuple, so the environment is not gymnasium-conformant."""
    return edit(src,
                "        return obs, float(reward), terminated, False, info",
                "        return obs, float(reward), terminated, info")


# name -> (mutator, gate it is meant to break, one-line description)
MUTANTS = {
    "leak-hidden-tests": (m_leak_hidden_tests, "no_leak",
                          "observation carries the hidden tests"),
    "no-reset": (m_no_reset, "reset_isolation",
                 "reset() does not restart the episode"),
    "no-timeout": (m_no_timeout, "hostile_zero",
                   "subprocess timeout dropped"),
    "partial-wrong": (m_partial_wrong, "partial_exact",
                      "reward is all-or-nothing, not a fraction"),
    "nondeterministic-seed": (m_nondeterministic_seed, "reset_determinism",
                              "task order drawn from the unseeded global RNG"),
    "reward-off-by-one": (m_reward_off_by_one, "reward_reference",
                          "reward divides by total + 1"),
    "no-rlimits": (m_no_rlimits, "hostile_zero",
                   "child resource limits not applied"),
    "api-broken": (m_api_broken, "gymnasium_api",
                   "step returns a 4-tuple"),
}


def make(name, dest):
    """Write the mutant `name` as a full artifact tree at `dest`."""
    if name not in MUTANTS:
        raise SystemExit("no mutant named %r (have: %s)"
                         % (name, ", ".join(sorted(MUTANTS))))
    mutator, _gate, _why = MUTANTS[name]

    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(GOOD, dest)

    path = os.path.join(dest, ENV_FILE)
    with open(path) as fh:
        src = fh.read()
    with open(path, "w") as fh:
        fh.write(mutator(src))
    return dest


def main(argv):
    if len(argv) < 2 or argv[1] not in ("list", "make", "make-all"):
        print(__doc__.strip())
        return 2

    if argv[1] == "list":
        for name in sorted(MUTANTS):
            print("%-22s %-18s %s" % (name, MUTANTS[name][1], MUTANTS[name][2]))
        return 0

    if argv[1] == "make":
        if len(argv) != 4:
            print("usage: mutants.py make <name> <dest>")
            return 2
        print(make(argv[2], argv[3]))
        return 0

    dest_root = argv[2] if len(argv) > 2 else "/tmp/rl-mutants"
    for name in sorted(MUTANTS):
        make(name, os.path.join(dest_root, name))
    print("\n".join(os.path.join(dest_root, n) for n in sorted(MUTANTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
