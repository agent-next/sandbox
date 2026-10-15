#!/usr/bin/env bash
# Verifier for task symlink-maze.
#
# Oracle: analytic expectation.  expected.json records the release named in
# RELEASE.txt, the target the link must have, and the payload's sha256.  The
# link is resolved and its payload hashed; a symlink that merely "exists"
# is not enough.
set -euo pipefail

WORK="${1:?usage: verify.sh <work-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -I - "$WORK" "$HERE/expected.json" <<'PY'
import hashlib
import json
import os
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


cur = os.path.join(work, exp["current_link"])
loop = os.path.join(work, exp["loop_link"])
release_file = os.path.join(work, exp["release_file"])

# 1. the link must exist, be relative, and name the right target
if not os.path.islink(cur):
    bad(f"{exp['current_link']} is missing or is not a symlink")
else:
    target = os.readlink(cur)
    if os.path.isabs(target):
        bad(f"{exp['current_link']} -> {target!r} is absolute; "
            "the tree must survive being moved")
    if target != exp["expected_target"]:
        bad(f"{exp['current_link']} -> {target!r}, "
            f"expected {exp['expected_target']!r}")
    if not os.path.exists(cur):
        bad(f"{exp['current_link']} still dangles")

# 2. the resolved payload must be the right release's payload
payload = os.path.join(work, exp["payload"])
if not os.path.exists(payload):
    bad(f"{exp['payload']} is missing")
else:
    got = sha256_file(payload)
    if got != exp["payload_sha256"]:
        bad(f"{exp['payload']} contents changed "
            f"({got[:16]}... != {exp['payload_sha256'][:16]}...)")

# 2b. and the link must land on it, not merely exist
if os.path.islink(cur):
    landed = os.path.realpath(cur)
    want = os.path.realpath(os.path.join(work, exp["payload"][:-len("/payload/data.txt")]))
    if landed != want:
        bad(f"{exp['current_link']} resolves to "
            f"{os.path.relpath(landed, work)}, expected "
            f"{os.path.relpath(want, work)}")

# 3. resolving through the link must land on the payload
via_link = os.path.join(cur, "payload", "data.txt")
if not os.path.exists(via_link):
    bad(f"{exp['current_link']}/payload/data.txt does not resolve")
else:
    got = sha256_file(via_link)
    if got != exp["payload_sha256"]:
        bad(f"{exp['current_link']} resolves to the wrong release")

# 4. no cycle may remain: stat() raises ELOOP on a loop, and a dangling
#    link is equally unusable
if os.path.islink(loop):
    try:
        os.stat(loop)
    except OSError as exc:
        bad(f"{exp['loop_link']} -> {os.readlink(loop)!r} still does not "
            f"resolve ({exc.strerror})")
    else:
        print(f"note: {exp['loop_link']} was kept and resolves to "
              f"{os.readlink(loop)!r}")

# 5. RELEASE.txt must be untouched
if not os.path.isfile(release_file):
    bad(f"{exp['release_file']} is missing")
elif f"release: {exp['expected_version']}" not in open(release_file).read():
    bad(f"{exp['release_file']} was edited; it names the release to restore")

# 6. every release directory must still be intact
releases = os.path.join(work, "releases")
if not os.path.isdir(releases):
    bad("releases/ is missing")
else:
    for name in sorted(os.listdir(releases)):
        version_file = os.path.join(releases, name, "VERSION")
        if not os.path.isfile(version_file):
            bad(f"releases/{name}/VERSION is missing")
        elif open(version_file).read().strip() != name:
            bad(f"releases/{name}/VERSION says "
                f"{open(version_file).read().strip()!r}")

if problems:
    print(f"symlink-maze: {len(problems)} problem(s)")
    sys.exit(1)
print(f"symlink-maze: OK ({exp['current_link']} -> "
      f"{exp['expected_target']}, payload intact)")
PY
