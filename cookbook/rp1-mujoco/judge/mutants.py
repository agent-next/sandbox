#!/usr/bin/env python3
"""Generate the known-bad controller family by single-line edits.

Each mutant is one exact edit of examples/good/controller.py; the judge
must kill every one of them (selftest.sh checks that it does).
"""
import argparse
import os
import sys

# (name, anchor line, replacement) -- the edit is exact and asserted
EDITS = [
    ("zero_gains",
     "        KP = np.array([kp[n] for n in names])  # gain table, actuator order",
     "        KP = np.array([kp[n] for n in names])  # gain table, actuator order\n"
     "        KP = KP * 0.0"),
    ("sign_flip_knee",
     "        KP = np.array([kp[n] for n in names])  # gain table, actuator order",
     '        kp["left_knee_joint"] = -kp["left_knee_joint"]\n'
     "        KP = np.array([kp[n] for n in names])  # gain table, actuator order"),
    ("gains_100x",
     "        KP = np.array([kp[n] for n in names])  # gain table, actuator order",
     "        KP = np.array([kp[n] for n in names])  # gain table, actuator order\n"
     "        KP = KP * 100.0"),
    ("wrong_joint_order",
     "        order = list(range(len(names)))  # index map: actuator -> joint",
     "        order = list(range(len(names)))  # index map: actuator -> joint\n"
     "        order = order[::-1]"),
    ("no_balance",
     "        u += self._balance()\n",
     ""),
    ("clamp_1pct",
     "        u = np.clip(u, -self.lim, self.lim)\n        return u",
     "        u = np.clip(u, -self.lim, self.lim)\n"
     "        u = np.clip(u, -0.01*self.lim, 0.01*self.lim)\n"
     "        return u"),
    # oracle mutant: a controller that applies nothing at all
    ("zero_torque",
     "        u = np.clip(u, -self.lim, self.lim)",
     "        u = np.zeros_like(u)"),
    # cheat mutant: zero the applied push through the live data handle --
    # the judge's state-tamper check must catch it, not the physics
    ("cancels_push",
     "    def compute_ctrl(self, t):\n        d = self.data\n",
     "    def compute_ctrl(self, t):\n        d = self.data\n"
     "        d.xfrc_applied[:] = 0.0\n"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("good", nargs="?")
    ap.add_argument("outdir", nargs="?")
    args = ap.parse_args()

    if args.list:
        for name, _a, _r in EDITS:
            print(name)
        return 0

    src = open(args.good).read()
    os.makedirs(args.outdir, exist_ok=True)
    for name, anchor, repl in EDITS:
        if src.count(anchor) == 0:
            print(f"mutants: anchor not found for {name}: {anchor!r}", file=sys.stderr)
            return 1
        if name == "no_balance":
            mutated = src.replace(anchor, repl, 1)
        else:
            mutated = src.replace(anchor, repl, 1)
        if mutated == src:
            print(f"mutants: edit produced no change for {name}", file=sys.stderr)
            return 1
        path = os.path.join(args.outdir, f"controller_{name}.py")
        with open(path, "w") as fh:
            fh.write(mutated)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
