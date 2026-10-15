# measurectl

Summarise a CSV file of measurements.

Input files have a two-column header and two columns per data row:

```text
metric,value
alpha,1.0
gamma,-2.5
```

Blank lines and lines starting with `#` are ignored. Metric names are
stripped of surrounding whitespace; duplicate names accumulate into one
summary. Values must be finite numbers (`float()` syntax, so `1.5e3` is
fine).

```console
$ python -m measurectl data/sample.csv
metric  count  mean      min   max
------  -----  --------  ----  ----
alpha   3      2.16667   1     3
beta    1      42        42    42
delta   2      875       250   1500
gamma   3      -1        -2.5  0.5

$ python -m measurectl data/sample.csv --sort count
```

`--sort` takes `name` (default) or `count`.

Exit codes: `0` on success, `2` for an unreadable file or a malformed row.

## Tests

```console
$ python -m pytest -q
```
