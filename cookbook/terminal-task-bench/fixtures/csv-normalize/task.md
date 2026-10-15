# Task: normalize the dirty CSV

`work/in/export.csv` came off a legacy till. It is not a clean CSV: it has
CRLF line endings, comment lines, a header with stray spaces, rows with too
many or too few fields, one field with an embedded comma inside quotes, and
rows in no particular order.

Write `work/out/clean.csv` so that it is exactly:

- a single header line `id,name,qty`;
- one line per **kept** row, ordered by `id`, ascending;
- fields separated by commas, `LF` line endings, no trailing spaces, no
  comment lines, no blank lines, no quoting anywhere;
- a row is **dropped** when it does not have exactly three fields;
- surrounding spaces around a field are stripped, and quotes around a field
  are removed (a quoted comma stays part of the field).

Nothing else may appear in `out/clean.csv`, and `in/export.csv` must be
left alone.

Verify with `bash verify.sh "$PWD/work"` (from this directory).
