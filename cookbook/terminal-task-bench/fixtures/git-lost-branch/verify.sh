#!/usr/bin/env bash
# Verifier for task git-lost-branch.
#
# Oracle: reference tool.  git itself is the reference implementation, so the
# verifier asks git -- rev-parse, symbolic-ref, status -- and compares the
# answers against the SHAs recorded before the branch was deleted.  Nothing
# here trusts the repair script's exit status.
set -euo pipefail

WORK="${1:?usage: verify.sh <work-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -I - "$WORK" "$HERE/expected.json" <<'PY'
import json
import os
import subprocess
import sys

work, exp_path = sys.argv[1], sys.argv[2]
exp = json.load(open(exp_path))
repo = os.path.join(work, exp["repo"])
problems = []
env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1")


def bad(msg):
    problems.append(msg)
    print("FAIL:", msg)


def git(*args):
    p = subprocess.run(["git", *args], cwd=repo, env=env,
                       capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


if not os.path.isdir(os.path.join(repo, ".git")):
    bad(f"{exp['repo']}/.git is missing")
    sys.exit(1)

# 1. HEAD must be a symbolic ref to the branch, not a raw sha
rc, head, _ = git("symbolic-ref", "-q", "HEAD")
if rc != 0:
    rc2, sha, _ = git("rev-parse", "HEAD")
    bad(f"HEAD is detached at {sha} (symbolic-ref failed)")
elif head != f"refs/heads/{exp['branch']}":
    bad(f"HEAD points at {head!r}, expected refs/heads/{exp['branch']}")

# 2. the branch must exist and hold the pre-deletion tip
rc, tip, err = git("rev-parse", f"refs/heads/{exp['branch']}")
if rc != 0:
    bad(f"branch {exp['branch']} does not exist ({err})")
elif tip != exp["tip"]:
    bad(f"branch {exp['branch']} is at {tip}, expected {exp['tip']}")

# 3. the restored tree must carry the file the branch introduced
rc, got, _ = git("rev-parse", f"HEAD:{exp['ingest_file']}")
if rc != 0:
    bad(f"{exp['ingest_file']} is not in the restored commit")
else:
    rc2, blob, _ = git("show", f"HEAD:{exp['ingest_file']}")
    if rc2 != 0:
        bad(f"cannot read {exp['ingest_file']} from the restored commit")
    elif exp["token"] not in blob:
        bad(f"{exp['ingest_file']} lost its content "
            f"(token {exp['token']} not found)")

# 4. the working tree must be clean and the checkout must match
rc, status, _ = git("status", "--porcelain")
if status:
    bad(f"working tree is dirty:\n{status}")

# 5. main must not have moved
rc, main_sha, _ = git("rev-parse", "refs/heads/main")
if rc == 0 and main_sha != exp["main_sha"]:
    bad(f"main moved: {main_sha} != {exp['main_sha']}")

# 6. no commit may have been lost: the tip is still an ancestor of nothing
#    new, and the commit graph must still contain main
rc, _, _ = git("merge-base", "--is-ancestor", exp["main_sha"], exp["tip"])
if rc != 0:
    bad(f"the restored tip {exp['tip']} does not descend from main")

if problems:
    print(f"git-lost-branch: {len(problems)} problem(s)")
    sys.exit(1)
print(f"git-lost-branch: OK (HEAD -> {exp['branch']} at {exp['tip'][:12]}, "
      "clean tree)")
PY
