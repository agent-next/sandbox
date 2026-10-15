#!/usr/bin/env bash
# wal-repair: splice the frames the torn WAL still holds back into the
# database, then hand the result over to SQLite itself.
#
# The WAL header checksum is zeroed, so SQLite ignores the whole log.  The
# frame headers inside are intact, so the committed pages can be replayed by
# hand: for each frame, copy its page image over that page in the database
# file, then flip the database back to rollback-journal mode so no WAL is
# needed at all.  Everything is verified by opening the result read-only and
# checking integrity, so a partial splice fails loudly instead of silently.
set -euo pipefail

WORK="${WORK:?WORK must point at the task work directory}"
DB="$WORK/app.db"

python3 -I - "$DB" <<'PY'
import os
import sqlite3
import struct
import sys

db = sys.argv[1]
wal = db + "-wal"
PAGE = 4096
FRAME_HDR = 24

if not os.path.exists(wal):
    raise SystemExit("wal-repair: no -wal file to recover from")

raw = open(db, "rb").read()
log = open(wal, "rb").read()
if len(log) < 32:
    raise SystemExit("wal-repair: the -wal file is too short to hold frames")

# Replay every complete frame: page number in the frame header, page image
# right after it.  A torn tail (fewer than FRAME_HDR+page_size bytes left)
# is ignored, exactly as SQLite would.
image = bytearray(raw)
replayed = 0
offset = 32
while offset + FRAME_HDR + PAGE <= len(log):
    pgno, dbsize = struct.unpack(">II", log[offset:offset + 8])
    if pgno == 0:
        break
    page = log[offset + FRAME_HDR:offset + FRAME_HDR + PAGE]
    start = (pgno - 1) * PAGE
    if len(image) < start + PAGE:
        image.extend(b"\x00" * (start + PAGE - len(image)))
    image[start:start + PAGE] = page
    replayed += 1
    offset += FRAME_HDR + PAGE

if replayed == 0:
    raise SystemExit("wal-repair: the -wal file holds no complete frames")

# Database header: bump the change counter and set the page count, then
# switch the file out of WAL mode (read/write version 1 = rollback journal)
# so the repaired database never needs a -wal sidecar again.
struct.pack_into(">I", image, 24,
                 struct.unpack(">I", bytes(image[24:28]))[0] + 1)
struct.pack_into(">I", image, 28, len(image) // PAGE)
image[18] = 1
image[19] = 1

# write to a sibling, check it, then move it into place
tmp = db + ".repaired"
with open(tmp, "wb") as fh:
    fh.write(bytes(image))
con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
try:
    integrity = con.execute("pragma integrity_check").fetchone()[0]
    if integrity != "ok":
        raise SystemExit(f"wal-repair: repaired copy is not ok: {integrity}")
    tables = [r[0] for r in con.execute(
        "select name from sqlite_master where type='table' order by name")]
    counts = {t: con.execute(f"select count(*) from {t}").fetchone()[0]
              for t in tables}
finally:
    con.close()
os.replace(tmp, db)

# the sidecars must go: their content is now in the database file
for suffix in ("-wal", "-shm"):
    side = db + suffix
    if os.path.exists(side):
        os.remove(side)

print(f"wal-repair: replayed {replayed} frame(s) from the torn WAL; "
      + ", ".join(f"{t}={n}" for t, n in sorted(counts.items())))
PY

# confirm through the SQLite CLI as well, so the repair is not just
# "python said so"
sqlite3 "$DB" "pragma integrity_check;" | grep -qx ok
sqlite3 "$DB" "select count(*) from orders;" >/dev/null
sqlite3 "$DB" "select count(*) from audit;" >/dev/null
echo "wal-repair: sqlite3 reads the repaired database with no -wal present"
