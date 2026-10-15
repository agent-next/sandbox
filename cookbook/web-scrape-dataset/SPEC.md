# web-scrape-dataset: headless-browser extraction to a clean dataset

## Goal

An agent writes a **headless-browser scraper** that crawls a small, seeded
multi-page product catalogue served on `localhost`, executes the pages'
JavaScript, and writes a clean, exactly-correct CSV dataset. A judge it cannot
fool then re-generates the catalogue from its own generator, runs the agent's
scraper against the served site, and compares the CSV row-by-row with the
generator's ground truth.

The catalogue is deliberately awkward in the ways real sites are awkward:

- **50 products over 5 pagination pages** — the scraper must follow every
  page, not just the first.
- **JS-rendered prices** — each page's prices are written into the DOM by an
  inline script after load, so the raw HTML contains a placeholder value.
  Reading the placeholder instead of the rendered value is the classic
  pre-JS-scrape bug, and it is a judged failure.
- **A few malformed entries** — some product rows have an empty SKU or a
  non-numeric price. These must be **flagged**, not silently dropped and not
  silently invented.
- **A robots.txt-disallowed path** — the site ships a `robots.txt` that
  disallows one path prefix. The scraper must not request it. Requesting it is
  a judged failure.

The point of using a sandbox: the agent installs a pinned Chromium + Playwright,
writes the scraper, and iterates against the judge in an isolated, disposable
machine. Nothing it does can touch the real machine, the judge is unmodified by
anything the artifact does, and every number in the README comes from a real
run.

## Non-goals (explicitly out of scope)

- No authentication, no cookies, no session handling, no POST/PDF/image
  extraction.
- No anti-bot handling: no CAPTCHA, no challenge pages, no proxy rotation, no
  User-Agent spoofing. The site is a plain static server on `127.0.0.1`.
- No JavaScript-free fallback: the judge grades a browser-driven scraper.
  Fetching the HTML with `urllib` and parsing the placeholder prices is a
  failure (that is the `reads_prejs_price` mutant), not a cheap win.
- No concurrency requirement: the crawl is sequential and every run is
  deterministic given a seed, so wall time stays a few seconds.
- No "clean the data" pass that invents values. A malformed row is reported
  with its `ok=0` status; the judge checks the flags exist and name the right
  fields.

## The site (fixture)

A single deterministic generator, `judge/fixture.py`, writes a static site into
a temp dir and the judge serves it with Python's stdlib `http.server`:

```
/
  index.html            pagination, 10 products per page
  product/PROD-0001.html .. product/PROD-0050.html
  internal/index.html   the disallowed prefix (lists 3 off-catalogue products)
  robots.txt            User-agent: * / Disallow: /internal/
```

Page structure (this is what the scraper has to cope with):

```html
<!-- /index.html, page 2 -->
<div class="product" data-sku="PROD-0011" data-price-pending="true">
  <span class="name">Aluminium Lid</span>
  <span class="price" data-pending>$--.--</span>   <!-- placeholder, in HTML -->
</div>
<script>
  // runs after load; rewrites every .price span with the real value
  document.querySelectorAll('.product').forEach(function (el) {
    var p = el.getAttribute('data-price');
    el.querySelector('.price').textContent = '$' + p.toFixed(2);
    el.querySelector('.price').removeAttribute('data-pending');
  });
</script>
```

`data-price` holds the real price as a decimal string (`"19.99"`); the rendered
text is `"$19.99"`. A scraper that reads `.price`'s text before the script runs
sees `$--.--`.

**50 products.** Product `i` (1-based) has:

- `sku`: `PROD-%04d` with `i`,
- `name`: `"<Material> <Part>, <Finish>"` chosen from fixed lists by `i`
  (Chinese-remainder over 5/7/11, unique for all 50 products and independent
  of the seed, so a row is identifiable even when its SKU is empty),
- `price`: integer cents `((i * 7 + seed) % 19101) + 501`, i.e. exactly
  `[5.01 .. 195.99]` in steps of 0.01 — computed in integer cents so the
  ground truth has no floating-point fuzz, and the CSV must match it to the cent,
- `stock`: `(i * 13 + seed) % 7` units, `[0 .. 6]`,
- `weight_kg`: integer cents `((i * 29 + seed) % 495) + 5`, i.e.
  `[0.05 .. 4.99]`.

The values are a pure function of `(seed, i)`: a different seed moves every
price, stock and weight (and the malformed choice), so the scraper cannot
hard-code a table — it has to read the rendered page.

**Three malformed entries**, one per fault kind, chosen deterministically from
the seed. With the default seed `20261015`:

| product | fault |
|---|---|
| `PROD-0001` | empty SKU (`data-sku=""`) |
| `PROD-0014` | empty price (`data-price=""`, script leaves `$--.--` rendered) |
| `PROD-0017` | non-numeric price (`data-price="N/A"`, rendered as `N/A`) |

Exactly these three products, and no others, are malformed. Everything else
must appear as a full, exact row. A different `--seed` moves the three faults
to different products (e.g. seed `7` → `PROD-0017`, `PROD-0028`, `PROD-0047`;
seed `999` → `PROD-0007`, `PROD-0017`, `PROD-0044`); the count is always 3 and
each fault kind is used exactly once. The judge never assumes which SKUs are
malformed: it reads them from the oracle for the seed it is running.

**The disallowed path.** `robots.txt` is:

```
User-agent: *
Disallow: /internal/
```

`/internal/` lists three products (`PROD-9001..9003`) that are **not** part of
the dataset. Their rows must never appear in the CSV.

**Seeds.** The catalogue is a function of one seed. `--seed N` re-derives the
malformed-product choice and the disallowed-path listing from `N`; the 50
allowed products and their values are fixed. The default seed is `20261015`
and every number quoted in the README uses it.

## The artifact

The agent produces a single file: **`scrape.py`**, run by the judge as

```bash
python3 scrape.py --url http://127.0.0.1:<port> --out products.csv
```

with Playwright available in the environment the judge sets up
(`playwright==1.63.0`, Chromium headless shell pinned by sha256). `scrape.py`
must:

- crawl every pagination page,
- let the JavaScript run and read the **rendered** price,
- write `products.csv` with the header
  `sku,name,price,stock,weight_kg,status,notes`,
- emit one row per product found, in any order,
- set `status=ok` for a fully-parsed row and `status=malformed` with a
  `notes` string naming the broken field for the rest,
- emit no row for anything under `/internal/`,
- exit 0 on a complete crawl.

Column formats (the judge compares as text after normalisation):

| column | format for an `ok` row |
|---|---|
| `sku` | `PROD-%04d` |
| `name` | as rendered |
| `price` | `NN.NN`, exactly two decimals, e.g. `19.99` |
| `stock` | integer digits |
| `weight_kg` | `N.NN`, exactly two decimals, e.g. `0.05` |
| `status` | `ok` or `malformed` |
| `notes` | empty for `ok`; for `malformed`, one or more of `missing_sku`, `missing_price`, `bad_price` in any order |

The judge accepts a conforming CSV from any order of rows and any quoting
style that the Python `csv` module reads back identically, and is tolerant of
`notes` order because `notes` is compared as a set of flags.

## Judge gates (numeric pass rules)

`judge/grade.sh scrape.py --seed N --json out.json` runs the gates below; every
gate must pass for a green verdict. The oracle is the **generator's own ground
truth**, computed independently in `judge/fixture.py` (a closed-form function
of the product index) and never read back from the served HTML.

| # | gate | pass rule |
|---|---|---|
| 1 | `runs` | `scrape.py` exits 0 and writes `products.csv` |
| 2 | `no_internal_paths` | **zero** HTTP requests for any URL whose path starts with `/internal/` — recorded by the judge's request log, not by the scraper's honesty |
| 3 | `row_count` | exactly `50` data rows in the CSV (47 `ok` + 3 `malformed`) |
| 4 | `field_exact` | for every `ok` row, all of `sku,name,price,stock,weight_kg` byte-equal the ground truth after normalisation; **0** mismatches |
| 5 | `no_missing_ok` | every one of the 47 non-malformed products is present with `status=ok`; **0** absent |
| 6 | `malformed_flagged` | all 3 malformed products (for the seed's own oracle set) present with `status=malformed`, and each one's `notes` flags exactly the fault kind the oracle assigns it (`missing_sku` / `missing_price` / `bad_price`). **3/3** correct, and no `ok` row may carry a fault flag |
| 7 | `no_dup_rows` | no `sku` appears more than once among `ok` rows |
| 8 | `no_invented` | no row has a `sku` not in the ground truth (the `/internal/` products and made-up ids) |
| 9 | `used_browser` | at least one request in the server's log came from a user agent that is **not** the Python stdlib default (`Python-urllib/*`) — a real scraper announces itself or presents a browser UA; a bare `urllib` fetch fails here |
| 10 | `judge_integrity` | checksums of `judge/` are unchanged before and after the artifact ran |

Gate 2 is the robots gate and it is measured at the **server**: the judge wraps
`http.server`'s request log and records every path served, so a scraper that
fetches `/internal/` and then just doesn't write the row is still killed.

## Acceptance oracle

The judge fails (non-zero exit) if any gate fails.

`judge/selftest.sh` proves the judge can fail:

- `examples/good/scrape.py` must pass all gates,
- each of the single-edit mutants generated by `judge/mutate.py` from the good
  example must fail at least one gate,
- determinism: same `--seed` twice → byte-identical verdict JSON minus the
  `timing` key,
- kill rate printed; **≥ 90 %** required.

## Tools (pinned by the judge)

| tool | version | how pinned |
|---|---|---|
| Playwright (Python) | `1.63.0` (released 2026-09-15) | pip wheel `playwright-1.63.0-py3-none-manylinux1_x86_64.whl`, sha256 `ad21bc07516b187965a7521c5cf0df0bd657b17482eaad74335272d35a2b07de` (and the aarch64 wheel for arm64 hosts, sha256 `354e15b29503565fc598b89f16fbe070459343bef9d7498a93e304864000c6a7`); Apache-2.0 |
| Chromium headless shell | `153.0.8010.12`, build `cft/153.0.8010.12/linux64` (playwright `chromium-headless-shell` r1243) | zip sha256 `a9da028861a0cf789ff25c2fed45f5f1aaf969ed9247835b6a7821a4f7af9d1d`; licence: BSD-3-Clause + others, see `LICENSE.headless_shell` |
| Python | 3.12 (stdlib only) | system `python3` |

Playwright is published on PyPI under the Apache-2.0 licence; Chromium
Headless Shell is built by the Playwright project from Chromium and is
redistributable under the Chromium licence terms (BSD-3-Clause and others) —
its licence file ships in the browser tree. No tool is fetched with `latest`.

## Deviations from the lead's brief

- The brief says "50 product pages with pagination". The site uses 5 index
  pages × 10 products, where each product *also* has its own detail page. A
  scraper that only crawls the index pages gets all 50 products' data (the
  brief's ground truth is defined on the 50 products, not on the detail pages),
  so the detail pages are reachable but optional, and the `/internal/` prefix
  is behind a link on page 1 (`/internal/index.html`, a link the robot must not
  follow) so the robots gate is a real trap and not a file nobody would ever
  request.
- "JS-rendered prices" is implemented as an inline script that rewrites the
  price spans and drops a `data-pending` attribute, so a scraper can detect
  un-rendered content rather than guessing.
