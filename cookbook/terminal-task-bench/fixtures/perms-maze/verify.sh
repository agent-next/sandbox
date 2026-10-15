#!/usr/bin/env bash
# Verifier for task perms-maze.
#
# Oracle: reference execution + a spec mask over the whole tree.
#   * the runner is executed and its stdout compared with the recorded token
#     (reference execution: the repair has to make the tool work, not just
#     look plausible);
#   * the mask then walks every path in the tree and rejects world-writable
#     paths and unreadable/unexecutable files, which is what kills the
#     `chmod -R 777` non-repair;
#   * file contents are compared by sha256 so a rewrite is not a repair.
set -euo pipefail

WORK="${1:?usage: verify.sh <work-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -I - "$WORK" "$HERE/expected.json" <<'PY'
import hashlib
import json
import os
import stat
import subprocess
import sys

work, exp_path = sys.argv[1], sys.argv[2]
exp = json.load(open(exp_path))
problems = []


def bad(msg):
    problems.append(msg)
    print("FAIL:", msg)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# 1. reference execution: run the runner the way a user would
runner = os.path.join(work, exp["runner"])
if not os.path.isfile(runner):
    bad(f"{exp['runner']} is missing")
else:
    try:
        run = subprocess.run([runner], capture_output=True, text=True,
                             timeout=30, cwd=work)
    except PermissionError as exc:
        bad(f"{exp['runner']} cannot be executed: {exc}")
        run = None
    except OSError as exc:
        bad(f"{exp['runner']} failed to start: {exc}")
        run = None
    if run is not None:
        if run.returncode != 0:
            bad(f"{exp['runner']} exited {run.returncode}: "
                f"{run.stderr.strip()[:200]}")
        elif run.stdout.strip() != exp["token"]:
            bad(f"{exp['runner']} printed {run.stdout.strip()!r}, "
                f"expected {exp['token']!r}")

# 2. the mask over the whole tree
for dirpath, dirnames, filenames in os.walk(work):
    for name in dirnames + filenames:
        p = os.path.join(dirpath, name)
        rel = os.path.relpath(p, work)
        st = os.lstat(p)
        mode = stat.S_IMODE(st.st_mode)
        if mode & stat.S_IWOTH:
            bad(f"{rel} is world-writable (mode {oct(mode)})")
        if stat.S_ISDIR(st.st_mode):
            if not mode & stat.S_IXUSR:
                bad(f"directory {rel} is not traversable "
                    f"(mode {oct(mode)})")
        else:
            if not mode & stat.S_IRUSR:
                bad(f"{rel} is not readable by its owner (mode {oct(mode)})")

for rel in exp["scripts"]:
    p = os.path.join(work, rel)
    if not os.path.isfile(p):
        bad(f"{rel} is missing")
        continue
    mode = stat.S_IMODE(os.stat(p).st_mode)
    if not mode & stat.S_IXUSR:
        bad(f"{rel} is not executable (mode {oct(mode)})")

for rel in ("opt/bench/data/input.txt", "opt/bench/README"):
    p = os.path.join(work, rel)
    if not os.path.isfile(p):
        bad(f"{rel} is missing")
        continue
    if not stat.S_IMODE(os.stat(p).st_mode) & stat.S_IRUSR:
        bad(f"{rel} is not readable")

# 3. the private file must stay private
priv = os.path.join(work, exp["private_file"])
if not os.path.isfile(priv):
    bad(f"{exp['private_file']} is missing")
else:
    mode = stat.S_IMODE(os.stat(priv).st_mode)
    if mode & (stat.S_IROTH | stat.S_IRGRP):
        bad(f"{exp['private_file']} is readable by group/other "
            f"(mode {oct(mode)}): it holds a credential")

# 4. contents unchanged
for rel, want in exp["contents_sha256"].items():
    p = os.path.join(work, rel)
    if not os.path.isfile(p):
        bad(f"{rel} is missing")
    elif sha256_file(p) != want:
        bad(f"{rel} was modified; this task is about modes, not contents")

if problems:
    print(f"perms-maze: {len(problems)} problem(s)")
    sys.exit(1)
print(f"perms-maze: OK (runner prints its token, no world-writable path, "
      "contents untouched)")
PY
