#!/usr/bin/env bash
# tar-restore: rebuild restore/ from the archive, guided by the manifest.
#
# Extraction alone is not the repair: a stale file has to go, and modes have
# to be restored (tar only sets the mode it stored when running as the
# owner).  So the archive is extracted to a scratch dir, each path is copied
# into restore/ and its mode and sha256 checked against the manifest, and
# anything in restore/ that the manifest does not name is removed.
set -euo pipefail

WORK="${WORK:?WORK must point at the task work directory}"

python3 -I - "$WORK" <<'PY'
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

work = sys.argv[1]
archive = os.path.join(work, "archive.tar.gz")
manifest_path = os.path.join(work, "manifest.json")
restore = os.path.join(work, "restore")

manifest = json.load(open(manifest_path))
entries = manifest["entries"]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


tmp = tempfile.mkdtemp()
try:
    # extract into an empty scratch dir, never into restore/
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            target = os.path.join(tmp, member.name)
            if not os.path.realpath(target).startswith(os.path.realpath(tmp)):
                raise SystemExit(f"tar-restore: {member.name!r} escapes the "
                                 "extraction root")
        tar.extractall(tmp)

    os.makedirs(restore, exist_ok=True)

    # 1. remove anything the manifest does not name
    wanted = {e["path"] for e in entries}
    for dirpath, dirnames, filenames in os.walk(restore, topdown=False):
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), restore)
            if rel not in wanted:
                os.remove(os.path.join(dirpath, name))
        for name in dirnames:
            d = os.path.join(dirpath, name)
            if not os.listdir(d):
                os.rmdir(d)

    # 2. copy each entry into place and restore its recorded mode
    for entry in entries:
        rel = entry["path"]
        src = os.path.join(tmp, rel)
        dst = os.path.join(restore, rel)
        if not os.path.isfile(src):
            raise SystemExit(f"tar-restore: {rel} is not in the archive")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        os.chmod(dst, entry["mode"])
        got = sha256_file(dst)
        if got != entry["sha256"]:
            raise SystemExit(f"tar-restore: {rel} hashes to {got[:16]}..., "
                             f"manifest says {entry['sha256'][:16]}...")
        if os.path.getsize(dst) != entry["size"]:
            raise SystemExit(f"tar-restore: {rel} is the wrong size")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# 3. final sweep: nothing extra, every mode exactly right
extra = []
for dirpath, _dirnames, filenames in os.walk(restore):
    for name in filenames:
        rel = os.path.relpath(os.path.join(dirpath, name), restore)
        if rel not in wanted:
            extra.append(rel)
if extra:
    raise SystemExit(f"tar-restore: leftovers in restore/: {extra[:5]}")

print(f"tar-restore: {len(entries)} files restored from the archive with "
      "manifest modes, no leftovers")
PY
