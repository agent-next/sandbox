#!/usr/bin/env bash
# csv-normalize: rebuild the export as one canonical CSV.
#
# Parsing is done with the csv module against the raw text, so the quoted
# field with a comma in it stays one field; ragged rows are dropped by field
# count, then the result is written sorted by id with LF endings.  The
# output is re-read and re-checked before it is left in place.
set -euo pipefail

WORK="${WORK:?WORK must point at the task work directory}"

python3 -I - "$WORK" <<'PY'
import csv
import io
import os
import sys

work = sys.argv[1]
src = os.path.join(work, "in", "export.csv")
dst = os.path.join(work, "out", "clean.csv")

text = open(src, encoding="utf-8", newline="").read()
rows = []
for row in csv.reader(io.StringIO(text)):
    # comment and blank lines are not data
    if not row or all(not f.strip() for f in row):
        continue
    first = row[0].strip()
    if first.startswith("#"):
        continue
    fields = [f.strip() for f in row]
    if fields[0].lower() == "id":
        continue                      # header, however it was spaced
    if len(fields) != 3:
        continue                      # ragged rows are dropped
    rid, name, qty = fields
    if not rid.lstrip("-").isdigit() or not qty.lstrip("-").isdigit():
        continue
    rows.append((int(rid), name, int(qty)))

if not rows:
    raise SystemExit("csv-normalize: no usable data rows found")

rows.sort(key=lambda r: r[0])

# canonical form: RFC 4180 minimal quoting (a field is quoted only when it
# has to be), LF line endings
buf = io.StringIO()
writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
writer.writerow(["id", "name", "qty"])
writer.writerows(rows)
out = buf.getvalue()

os.makedirs(os.path.dirname(dst), exist_ok=True)
with open(dst, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(out)

# read it back the strict way: it has to be exactly what we meant to write
check = open(dst, "rb").read()
if b"\r" in check:
    raise SystemExit("csv-normalize: CR bytes survived")
back = list(csv.reader(io.StringIO(check.decode())))
if back[0] != ["id", "name", "qty"]:
    raise SystemExit(f"csv-normalize: bad header {back[0]}")
if len(back) - 1 != len(rows):
    raise SystemExit(f"csv-normalize: {len(back) - 1} rows written, "
                     f"{len(rows)} expected")
ids = [int(r[0]) for r in back[1:]]
if ids != sorted(ids):
    raise SystemExit("csv-normalize: rows are not sorted by id")
print(f"csv-normalize: wrote {len(rows)} rows to out/clean.csv")
PY
