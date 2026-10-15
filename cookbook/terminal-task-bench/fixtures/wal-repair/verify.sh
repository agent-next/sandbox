#!/usr/bin/env bash
# Verifier for task wal-repair.
#
# Oracle: analytic expectation.  expected.json records every committed row of
# every table, read from the live database before its WAL header was torn.
# The repaired database must reproduce those rows exactly -- and must do so
# with no -wal file alongside it, which is the whole point of the task.
set -euo pipefail

WORK="${1:?usage: verify.sh <work-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -I - "$WORK" "$HERE/expected.json" <<'PY'
import json
import os
import shutil
import sqlite3
import sys
import tempfile

work, exp_path = sys.argv[1], sys.argv[2]
exp = json.load(open(exp_path))
db = os.path.join(work, exp["db"])
problems = []


def bad(msg):
    problems.append(msg)
    print("FAIL:", msg)


if not os.path.isfile(db):
    bad(f"{exp['db']} is missing")
    sys.exit(1)

# 1. the file itself must be a healthy database
try:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    integrity = con.execute("pragma integrity_check").fetchone()[0]
    if integrity != "ok":
        bad(f"integrity_check says {integrity!r}, not 'ok'")
except sqlite3.Error as exc:
    bad(f"cannot open {exp['db']}: {exc}")
    sys.exit(1)

# 2. every committed row, read through a copy that has no WAL beside it
tmp = tempfile.mkdtemp()
try:
    copy = os.path.join(tmp, "app.db")
    shutil.copyfile(db, copy)
    try:
        ro = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        bad(f"the database does not read without its WAL: {exc}")
        sys.exit(1)
    for table in ("orders", "audit"):
        want = [tuple(r) for r in exp[table]]
        cols = {"orders": "id, sku, qty", "audit": "seq, action, who"}[table]
        try:
            got = ro.execute(
                f"select {cols} from {table} order by 1").fetchall()
        except sqlite3.Error as exc:
            bad(f"table {table} unreadable: {exc}")
            continue
        if got != want:
            missing = [r for r in want if r not in got]
            extra = [r for r in got if r not in want]
            bad(f"table {table}: {len(got)} rows, expected {len(want)}"
                f" (missing {missing[:3]}, unexpected {extra[:3]})")
    ro.close()
finally:
    shutil.rmtree(tmp, ignore_errors=True)
con.close()

# 3. no stale sidecar left claiming to hold committed data
for suffix in ("-wal", "-shm"):
    side = db + suffix
    if os.path.exists(side) and os.path.getsize(side) > 0:
        print(f"note: {exp['db']}{suffix} still present "
              f"({os.path.getsize(side)} bytes)")

if problems:
    print(f"wal-repair: {len(problems)} problem(s)")
    sys.exit(1)
print(f"wal-repair: OK ({exp['orders_rows']} orders, "
      f"{exp['audit_rows']} audit rows recovered, no WAL needed)")
PY
