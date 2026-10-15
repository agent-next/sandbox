# web-scrape-dataset

A headless-browser scraper is written by an agent inside a disposable agent-next
sandbox, against a small product catalogue served on `localhost`, and a judge the
scraper cannot fool decides whether the dataset it produced is exactly right.
The catalogue is deliberately awkward the way real sites are: 50 products over 5
pagination pages, prices written into the DOM by JavaScript *after* load, three
malformed entries, and a `robots.txt`-disallowed path the pager links but a
polite crawler must not fetch.

Why a sandbox helps: the job needs a pinned Chromium + Playwright installed,
a real HTTP server, and an agent free to iterate against a judge — on a machine
that can be thrown away afterwards. Nothing the agent does can touch your
machine, and the judge is checksummed before and after the scraper runs, so the
artifact cannot edit the gates it is graded by.

Ask your agent:

> Write `scrape.py` in this directory: a Playwright scraper that crawls every
> pagination page of the catalogue the judge serves, waits for the JavaScript to
> render the prices, flags the malformed entries instead of dropping them, and
> respects the `robots.txt`-disallowed path. Then run `bash judge/grade.sh
> examples/good/scrape.py` and iterate until every gate passes. Do not edit
> anything under `judge/`.

## Run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/web-scrape-dataset/run.py            # clone main, set up, self-test, grade
python3 cookbook/web-scrape-dataset/run.py --ref <branch-or-sha>
python3 cookbook/web-scrape-dataset/run.py --keep     # leave the sandbox up, print its id
```

`run.py` creates a sandbox (`--timeout-min 30`), clones this repo at `--ref`,
runs `judge/setup.sh`, `judge/selftest.sh` and `judge/grade.sh
examples/good/scrape.py`, prints the verdict JSON and a short summary, then
**always** kills the sandbox and confirms with `sbx list` that the id is gone.
An unconfirmed cleanup fails the run and names the sandbox id, rather than
reporting a success it cannot back up.

## Grading

`judge/grade.sh <artifact.py> [--seed N] [--json out.json]` serves a freshly
generated catalogue, runs the artifact against it, and compares the CSV with the
**generator's own ground truth** — a closed-form function of the product index
in `judge/fixture.py`, never read back from the served HTML. Eleven gates, all
numeric:

| gate | pass rule |
|---|---|
| `runs` | artifact exits 0 and writes `products.csv` |
| `no_internal_paths` | zero requests for the disallowed path, from the judge's own HTTP log |
| `csv_readable` | the CSV parses and has the seven expected columns |
| `row_count` | exactly 50 data rows (47 `ok` + 3 `malformed`) |
| `field_exact` | every `ok` row's sku, name, price, stock, weight byte-equal the oracle; 0 mismatches |
| `no_missing_ok` | all 47 non-malformed products present *and* `status=ok` |
| `malformed_flagged` | the 3 malformed products present, flagged with exactly the right note |
| `no_dup_rows` | no SKU appears twice among `ok` rows |
| `no_invented` | no row has a SKU outside the ground truth |
| `used_browser` | the server saw a non-`Python-urllib` user agent |
| `judge_integrity` | `judge/` checksums unchanged before and after the run |

The robots gate is measured **at the server**: the judge logs every path it
serves, so a scraper that fetches `/internal/` and merely omits the row is still
killed.

`judge/selftest.sh` proves the judge can fail: the good example must pass all
gates, every single-edit mutant of it must fail at least one gate, and two runs
at the same seed must produce byte-identical verdicts (minus `timing` and
`base_url`). Measured: **good example 11/11 gates; 7 mutants, 7 killed (100 %)**.

## Limits

- The site is a plain static server on `127.0.0.1`. No authentication, cookies,
  CAPTCHA, proxy rotation or User-Agent spoofing is simulated, and none is
  needed.
- The crawl is sequential and deterministic; wall time is a few tens of seconds,
  not minutes. This is a correctness demo, not a throughput one.
- The judge grades a browser-driven scraper. Fetching the HTML with `urllib` and
  parsing it is a failure (the `reads_prejs_price` / `used_browser` mutants), not
  a shortcut.
- `judge/setup.sh` downloads ~115 MB of Chromium the first time. On an image
  that already ships a Playwright browser tree it reuses that instead.

Measured wall times, the two fresh-sandbox runs and the tool versions are in
`RECEIPT.md`; the design and the numeric gates are in `SPEC.md`.
