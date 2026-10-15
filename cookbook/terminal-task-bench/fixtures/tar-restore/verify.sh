#!/usr/bin/env bash
# Verifier for task tar-restore.
#
# Oracle: analytic expectation.  The manifest is the literal intent (path,
# sha256, mode, size); the verifier hashes every restored file and compares
# modes, then requires the restore tree to contain nothing else.  Extracting
# "successfully" is not the oracle -- the bytes and the modes are.
set -euo pipefail

WORK="${1:?usage: verify.sh <work-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -I - "$WORK" "$HERE/expected.json" <<'PY'
import hashlib
import json
import os
import stat
import sys

work, exp_path = sys.argv[1], sys.argv[2]
exp = json.load(open(exp_path))
restore = os.path.join(work, exp["restore_dir"])
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


if not os.path.isdir(restore):
    bad(f"{exp['restore_dir']}/ is missing")
    sys.exit(1)

want_paths = set()
for entry in exp["entries"]:
    rel = entry["path"]
    want_paths.add(rel)
    p = os.path.join(restore, rel)
    if not os.path.isfile(p):
        bad(f"{rel} is missing from the restore")
        continue
    got_sha = sha256_file(p)
    if got_sha != entry["sha256"]:
        bad(f"{rel} contents differ "
            f"({got_sha[:16]}... != {entry['sha256'][:16]}...)")
    size = os.path.getsize(p)
    if size != entry["size"]:
        bad(f"{rel} is {size} bytes, expected {entry['size']}")
    mode = stat.S_IMODE(os.stat(p).st_mode)
    if mode != entry["mode"]:
        bad(f"{rel} mode is {oct(mode)}, expected {oct(entry['mode'])}")

# nothing extra may be left behind
got_paths = set()
for dirpath, _dirnames, filenames in os.walk(restore):
    for name in filenames:
        got_paths.add(os.path.relpath(os.path.join(dirpath, name), restore))
extra = sorted(got_paths - want_paths)
if extra:
    bad(f"{len(extra)} path(s) not in the manifest: {extra[:5]}")

# the inputs must be untouched
arch = os.path.join(work, exp["archive"])
if not os.path.isfile(arch):
    bad(f"{exp['archive']} is missing")
elif sha256_file(arch) != exp["archive_sha256"]:
    bad(f"{exp['archive']} was modified")
manifest = os.path.join(work, exp["manifest"])
if not os.path.isfile(manifest):
    bad(f"{exp['manifest']} is missing")

if problems:
    print(f"tar-restore: {len(problems)} problem(s)")
    sys.exit(1)
print(f"tar-restore: OK ({exp['entry_count']} files restored with matching "
      "contents and modes, no leftovers)")
PY
