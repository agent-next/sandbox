#!/usr/bin/env bash
# perms-maze: set the mode bits the tree needs, and nothing more.
#
# A blanket `chmod -R` is the wrong repair in both directions: 777 leaves
# the scratch dir world-writable, 755 exposes the credential file.  This
# script names every path it touches and checks the result, so the intent
# (tool runs, secret stays private) is what gets written.
set -euo pipefail

WORK="${WORK:?WORK must point at the task work directory}"
cd "$WORK"

# directories: traversable by their owner
for d in opt opt/bench opt/bench/bin opt/bench/lib opt/bench/data \
         opt/bench/var opt/bench/var/scratch; do
    chmod 755 "$d"
done

# scripts: readable and executable, not world-writable
chmod 755 opt/bench/bin/run.sh opt/bench/bin/helper.sh opt/bench/lib/common.sh

# data: readable
chmod 644 opt/bench/data/input.txt opt/bench/README

# the credential: owner only
chmod 600 opt/bench/data/private.txt

# the scratch dir was the source of the mess: keep it writable, but only by
# its owner
chmod 755 opt/bench/var/scratch

# prove the repair the way the verifier will: run the tool and look at the
# modes that must not have gone loose
out="$( opt/bench/bin/run.sh )"
[ -n "$out" ] || { echo "perms-maze: the runner printed nothing" >&2; exit 1; }

python3 -I - "$WORK" <<'PY'
import os
import stat
import sys

work = sys.argv[1]
bad = []
for dirpath, dirnames, filenames in os.walk(work):
    for name in dirnames + filenames:
        p = os.path.join(dirpath, name)
        mode = stat.S_IMODE(os.lstat(p).st_mode)
        if mode & stat.S_IWOTH:
            bad.append(f"{os.path.relpath(p, work)} is world-writable")
priv = os.path.join(work, "opt/bench/data/private.txt")
pmode = stat.S_IMODE(os.stat(priv).st_mode)
if pmode & (stat.S_IROTH | stat.S_IRGRP):
    bad.append(f"private.txt is group/other readable ({oct(pmode)})")
if bad:
    raise SystemExit("perms-maze: " + "; ".join(bad))
print("perms-maze: no world-writable path, credential is owner-only")
PY
echo "perms-maze: runner prints its token"
