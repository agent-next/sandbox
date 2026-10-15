# ISSUE — `--json` output for `measurectl`

`measurectl` prints a fixed-width table. Anything that wants to consume a
summary from a script has to scrape that table, which breaks whenever a
metric name gets longer than the current column width.

Add a `--json` flag that prints one JSON document instead.

## Required schema

`python -m measurectl --json <path>` writes exactly this document to
stdout:

```json
{
  "schema": "measurectl/summary/v1",
  "total_count": 9,
  "metrics": [
    {"name": "alpha", "count": 3, "sum": 6.5, "mean": 2.1666666666666665,
     "min": 1.0, "max": 3.0}
  ]
}
```

- `schema` is the literal string `measurectl/summary/v1`.
- `total_count` is the number of data rows in the file — every row that is
  neither blank nor a `#` comment — across all metrics.
- `metrics` has exactly one entry per metric name that occurs in the data,
  sorted by `name` in Unicode code point order.
- `count` is an integer. `sum`, `mean`, `min` and `max` are JSON numbers.
- For every metric: `min <= mean <= max` and `mean` is `sum / count`.
- No other keys, at the top level or per metric.

## Behaviour

- `--json` replaces the table: with `--json`, stdout carries the JSON
  document and nothing else.
- `--json` ignores `--sort`. The JSON array is always sorted by name.
- Error handling is unchanged: an unreadable file or a malformed row exits
  `2` with a message on stderr and nothing on stdout.
- The existing table output, the existing flags and the existing exit codes
  do not change.
- No new third-party dependencies: the project is stdlib-only and stays
  that way.
- The output must be correct for **any** valid input file, not only
  `data/sample.csv`.

## Done means

`python -m measurectl --json data/sample.csv` exits `0` and matches the
schema above, and `python -m pytest` still passes.
