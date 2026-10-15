# Add `--json` output to measurectl

## Summary

Implements `ISSUE.md`. A new `--json` flag prints the summary as a single
JSON document instead of the fixed-width table, so callers no longer have
to scrape column widths.

- `measurectl/jsonout.py` (new): builds and renders the
  `measurectl/summary/v1` document. Metrics are sorted by name in Unicode
  code point order; `count` stays an integer and the other fields are
  JSON numbers.
- `measurectl/cli.py`: adds the `--json` flag, wires it to the new
  module, and returns before the table path so `--json` output is the
  only thing on stdout. `--json` deliberately ignores `--sort` — the JSON
  array is always sorted by name.

Error handling, the table output, the existing flags and the exit codes
are unchanged. No new dependencies: the document is built from the
existing accumulator and serialised with the standard library.

## Test plan

- `python -m pytest` — the existing suite (26 tests) still passes; no
  test file was touched.
- `python -m measurectl --json data/sample.csv` — exits 0 and matches the
  schema in `ISSUE.md` (`total_count` 9, `alpha` sum 6.5, mean
  6.5 / 3).
- `python -m measurectl --json <missing-file>` — exits 2, stderr only.
- `python -m ruff check .` — clean.
