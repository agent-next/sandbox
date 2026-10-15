# Task: repair the corrupted WAL

`work/app.db` is a SQLite database in WAL mode. A crash left its
write-ahead log in a state SQLite refuses to read: the header checksum no
longer matches, so the whole log is ignored. The database still opens and
`pragma integrity_check` still says `ok` — but rows that were committed
after the last checkpoint are gone.

Recover **every committed row** of every table in the database, in place at
`work/app.db`, so that:

- the database reads correctly on its own, with no `-wal` file present;
- no committed row is lost and no row is invented;
- `pragma integrity_check` reports `ok`.

The database is the only source of truth. Do not recreate it from
scratch and do not edit the schema.

Verify with `bash verify.sh "$PWD/work"` (from this directory). It exits 0
only when the repair is complete.
