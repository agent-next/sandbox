#!/usr/bin/env python3
"""Single-edit mutants of examples/good/scrape.py.

Each mutant flips one place in the known-good scraper, so a judge that fails
on it has caught a real behavioural deviation rather than a syntax error.

Usage:
    mutate.py <good_scrape.py> <outdir>   writes <name>.py for each mutant
    mutate.py --list                      prints names + one-line description
"""
import os
import sys

GOOD_UA = "USER_AGENT = 'web-scrape-dataset-scraper/1.0 (+https://example.invalid/contact)'"
GOOD_WAIT = ("page.wait_for_function(PAGE_WAIT, timeout=30000)\n"
             "        return read_cards(page)")
GOOD_MALFORMED = """    flags = []
    if not sku:
        flags.append('missing_sku')"""

# (name, old, new, description)
MUTATIONS = [
    ('misses_page_2plus',
     "    urls = [base_url + '/index.html']\n",
     "    urls = [base_url + '/index.html']\n    return urls[:1]  # MUTANT\n",
     'crawls only page 1: 10 of 50 products, missing 40 ok rows'),

    ('reads_prejs_price',
     "page.wait_for_function(PAGE_WAIT, timeout=30000)\n    return read_cards(page)",
     "page.goto(url, wait_until='domcontentloaded')  # MUTANT: no wait\n    return read_cards(page)",
     "reads the price before the render script runs: every price is '$--.--'"),

    ('drops_malformed_rows',
     GOOD_MALFORMED,
     GOOD_MALFORMED + "\n    if flags:\n        return None  # MUTANT: silently drop",
     'malformed rows are dropped instead of flagged: 3 rows missing'),

    ('scrapes_disallowed_path',
     "def visit(page, url, robots, stats):\n    \"\"\"Load one already-fetched page and hand back its cards.\"\"\"\n    if not robots.allowed(url):",
     "def visit(page, url, robots, stats):\n    \"\"\"Load one already-fetched page and hand back its cards.\"\"\"\n    if False:  # MUTANT: the robots.txt gate is gone",
     'robots.txt is ignored: the /internal/ archive is fetched'),

    ('dup_rows',
     "            if key in by_key:\n                return False",
     "            if False:  # MUTANT: no deduplication\n                return False",
     'no deduplication: each product appears on both its index and detail page'),

    ('no_browser_ua',
     GOOD_UA,
     "USER_AGENT = 'Python-urllib/3.13'  # MUTANT: presents itself as a bare urllib fetch",
     'user agent is the stdlib default, so the used_browser gate fails'),

    ('unflagged_malformed',
     "        'status': 'ok' if ok else 'malformed',",
     "        'status': 'ok',  # MUTANT: malformed rows claimed as clean",
     'malformed rows are written as ok with empty notes: flags are wrong'),
]


def apply(src, old, new):
    assert old in src, 'pattern not found: %r' % old[:60]
    return src.replace(old, new, 1)


def main():
    if sys.argv[1] == '--list':
        for name, _, _, desc in MUTATIONS:
            print('%s: %s' % (name, desc))
        return 0
    good, outdir = sys.argv[1], sys.argv[2]
    src = open(good).read()
    os.makedirs(outdir, exist_ok=True)
    for name, old, new, desc in MUTATIONS:
        with open(os.path.join(outdir, name + '.py'), 'w') as f:
            f.write(apply(src, old, new))
        print('%s: %s' % (name, desc))
    print('wrote %d mutants to %s/' % (len(MUTATIONS), outdir))
    return 0


if __name__ == '__main__':
    sys.exit(main())
