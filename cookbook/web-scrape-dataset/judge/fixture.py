#!/usr/bin/env python3
"""Deterministic static catalogue for the web-scrape-dataset judge.

Writes a small multi-page product site into a directory, and exposes the
ground truth as a closed-form function of the product index (an independent
oracle: the values are never read back from the HTML).

Site layout:
    index.html            5 pagination pages, 10 products each
    product/PROD-0001..050.html
    internal/index.html   the /internal/ prefix listed in robots.txt
    robots.txt            User-agent: * / Disallow: /internal/

Prices are written into the DOM by an inline script on every page: the HTML
serves a placeholder ("$--.--"), and the script rewrites it with the real
price, so a scraper that does not run JS reads the placeholder.

Three products are malformed by construction, one per fault kind, picked by
the seed (default 20261015 -> PROD-0001 empty sku, PROD-0014 empty price, the
script leaves the placeholder rendered, PROD-0017 price text is not numeric at
all, "N/A"). The count is always 3 whatever the seed.

Nothing here is random: every value is a pure function of the seed and the
product index, so the same seed always builds the same site.

Usage (as a library from grade.py; CLI for a human eyeball):
    python3 fixture.py <outdir> [--seed N] [--list]
"""
import argparse
import os
import sys

DEFAULT_SEED = 20261015

N_PRODUCTS = 50
PER_PAGE = 10
N_PAGES = N_PRODUCTS // PER_PAGE

INTERNAL_SKUS = ('PROD-9001', 'PROD-9002', 'PROD-9003')

MATERIALS = ('Aluminium', 'Bamboo', 'Brass', 'Ceramic', 'Copper')
PARTS = ('Bracket', 'Clamp', 'Collar', 'Flange', 'Gasket', 'Hinge', 'Lid')
FINISHES = ('Anodised', 'Brushed', 'Chrome', 'Enamelled', 'Galvanised',
            'Lacquered', 'Matte', 'Nickel', 'Polished', 'Powder-Coated',
            'Raw')


def name_of(i, seed=DEFAULT_SEED):
    """A product name, unique for every product i (5*7*11 = 385 combinations
    for 50 products). Deliberately independent of the seed, so the name is a
    stable key the judge can identify a row by -- including the malformed row
    whose SKU is empty.

    The Chinese-remainder pairing (mod 5 / mod 7 / mod 11) guarantees
    uniqueness as long as 5*7*11 >= N_PRODUCTS.
    """
    return '%s %s, %s' % (MATERIALS[i % len(MATERIALS)],
                          PARTS[i % len(PARTS)],
                          FINISHES[i % len(FINISHES)])


# the three fault kinds, in the order the seed assigns them to products
FAULTS = ('missing_sku', 'missing_price', 'bad_price')


# --------------------------------------------------------------------------
# malformed selection: exactly 3 distinct products, a pure function of seed
# --------------------------------------------------------------------------
def malformed_products(seed=DEFAULT_SEED):
    """{product_index: fault} with exactly 3 distinct indices, 1..N_PRODUCTS.

    A 32-bit LCG walks the seed; a collision steps forward until it finds a
    free index, so the count is always 3 and every fault kind is used once.
    """
    picked = {}
    state = (seed * 2654435761) & 0xFFFFFFFF
    for fault in FAULTS:
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        idx = state % N_PRODUCTS + 1
        while idx in picked:
            idx = idx % N_PRODUCTS + 1
        picked[idx] = fault
    return picked


# --------------------------------------------------------------------------
# ground truth: pure functions of (seed, index)
# --------------------------------------------------------------------------
def price_of(i, seed=DEFAULT_SEED):
    """Exact integer cents -> decimal string. No float error anywhere."""
    cents = ((i * 7 + seed) % 19101) + 501      # 5.01 .. 195.99
    return '%d.%02d' % divmod(cents, 100)


def stock_of(i, seed=DEFAULT_SEED):
    return (i * 13 + seed) % 7                  # 0 .. 6


def weight_of(i, seed=DEFAULT_SEED):
    cents = ((i * 29 + seed) % 495) + 5         # 0.05 .. 4.99
    return '%d.%02d' % divmod(cents, 100)


def fault_of(i, seed=DEFAULT_SEED):
    """Which fault this product has, or None."""
    return malformed_products(seed).get(i)


def sku_of(i):
    return 'PROD-%04d' % i


def ground_truth(seed=DEFAULT_SEED):
    """The full expected dataset, one dict per product, in catalogue order.

    This is the oracle the judge compares the CSV against. It is derived from
    the index, never from the HTML.
    """
    rows = []
    for i in range(1, N_PRODUCTS + 1):
        fault = fault_of(i, seed)
        row = {
            'sku': sku_of(i),
            'name': name_of(i, seed),
            'price': price_of(i, seed),
            'stock': str(stock_of(i, seed)),
            'weight_kg': weight_of(i, seed),
            'status': 'malformed' if fault else 'ok',
            'fault': fault,
        }
        row['expected_notes'] = [] if not fault else [fault]
        rows.append(row)
    return rows


# --------------------------------------------------------------------------
# page rendering
# --------------------------------------------------------------------------
def _product_card(i, seed):
    """The markup for one product on an index page. `data-price` carries the
    real value; the visible text is the placeholder the JS replaces."""
    fault = fault_of(i, seed)
    sku = sku_of(i)
    name = name_of(i, seed)
    price = price_of(i, seed)
    if fault == 'missing_sku':
        sku = ''
    if fault == 'missing_price':
        price = ''
    if fault == 'bad_price':
        price = 'N/A'
    price_attr = 'N/A' if fault == 'bad_price' else price
    return (
        '<div class="product" data-sku="%s" data-price="%s">\n'
        '  <span class="name">%s</span>\n'
        '  <span class="price" data-pending>$--.--</span>\n'
        '  <span class="stock">%s in stock</span>\n'
        '  <span class="weight">%s kg</span>\n'
        '</div>'
    ) % (sku, price_attr, name, stock_of(i, seed), weight_of(i, seed))


def _detail_card(i, seed):
    """Per-product detail page. Same data, also JS-rendered."""
    fault = fault_of(i, seed)
    sku = sku_of(i) if fault != 'missing_sku' else ''
    price = price_of(i, seed)
    if fault == 'missing_price':
        price = ''
    elif fault == 'bad_price':
        price = 'N/A'
    # carries the same `.product` class and the same `data-sku`/`data-price`
    # attributes as the index card, so a crawler that follows detail links sees
    # each product a second time -- and has to deduplicate to get 50 rows.
    return (
        '<div class="product product-detail" data-sku="%s" data-price="%s">\n'
        '  <h1 class="name">%s</h1>\n'
        '  <p class="price" data-pending>$--.--</p>\n'
        '  <p class="stock">%s in stock</p>\n'
        '  <p class="weight">%s kg</p>\n'
        '</div>'
    ) % (sku, price, name_of(i, seed), stock_of(i, seed), weight_of(i, seed))


RENDER_SCRIPT = """
<script>
// Prices are filled in *after* the page loads, the way a real catalogue does
// it: the served HTML carries a placeholder, and the real value arrives a
// moment later. A scraper that reads the DOM at DOMContentLoaded sees
// "$--.--" for every product; only one that waits for the render marker gets
// the real price. The delay is what makes that difference observable -- an
// inline script at the end of <body> would run during parsing and leave no
// pre-JS window at all.
window.addEventListener('load', function () {
  setTimeout(function () {
    document.querySelectorAll('[data-price]').forEach(function (el) {
      var p = el.getAttribute('data-price');
      var span = el.querySelector('.price');
      if (!span) { return; }
      if (p === '' || isNaN(parseFloat(p))) {
        // malformed entry: leave the placeholder / bad text in place
        if (p !== '') { span.textContent = p; span.removeAttribute('data-pending'); }
        return;
      }
      span.textContent = '$' + parseFloat(p).toFixed(2);
      span.removeAttribute('data-pending');
    });
    // deterministic "the JS has run" marker: a scraper that reads before this
    // sees the placeholder, one that waits for it sees the real price
    document.documentElement.setAttribute('data-rendered', '1');
  }, 150);
});
</script>
"""


def _page(title, body):
    return (
        '<!doctype html>\n<html><head><meta charset="utf-8"><title>%s</title>'
        '<style>.product{border:1px solid #ddd;padding:4px;margin:4px}'
        '.pager a{margin-right:6px}</style></head>\n'
        '<body>\n<h1>%s</h1>\n%s\n%s\n</body></html>\n'
    ) % (title, title, body, RENDER_SCRIPT)


def _pager(page):
    out = ['<div class="pager">']
    for p in range(1, N_PAGES + 1):
        label = 'page %d' % p
        if p == page:
            out.append('<span>%s</span>' % label)
        else:
            out.append('<a href="/index.html?page=%d">%s</a>' % (p, label))
    out.append('<a href="/internal/index.html">archive</a>')
    out.append('</div>')
    return '\n'.join(out)


def build(outdir, seed=DEFAULT_SEED):
    """Write the whole site into outdir. Returns a summary dict."""
    os.makedirs(os.path.join(outdir, 'product'), exist_ok=True)
    os.makedirs(os.path.join(outdir, 'internal'), exist_ok=True)

    for page in range(1, N_PAGES + 1):
        first = (page - 1) * PER_PAGE + 1
        cards = '\n'.join(
            '<a class="pdetail" href="/product/%s.html">%s</a>'
            % (sku_of(i), _product_card(i, seed))
            for i in range(first, first + PER_PAGE)
        )
        fname = 'page%d.html' % page if page > 1 else 'index.html'
        with open(os.path.join(outdir, fname), 'w') as f:
            f.write(_page('Catalogue page %d of %d' % (page, N_PAGES),
                          cards + '\n' + _pager(page)))

    for i in range(1, N_PRODUCTS + 1):
        with open(os.path.join(outdir, 'product', '%s.html' % sku_of(i)), 'w') as f:
            f.write(_page(sku_of(i), _detail_card(i, seed)))

    # the disallowed prefix: three off-catalogue products a polite robot skips
    cards = '\n'.join(
        '<div class="product" data-sku="%s" data-price="1.00">\n'
        '  <span class="name">Archived %s</span>\n'
        '  <span class="price" data-pending>$--.--</span>\n'
        '  <span class="stock">0 in stock</span>\n'
        '  <span class="weight">1.00 kg</span>\n'
        '</div>' % (s, s)
        for s in INTERNAL_SKUS
    )
    with open(os.path.join(outdir, 'internal', 'index.html'), 'w') as f:
        f.write(_page('Internal archive (do not crawl)',
                      cards + '\n<div class="pager">archive</div>'))

    with open(os.path.join(outdir, 'robots.txt'), 'w') as f:
        f.write('User-agent: *\nDisallow: /internal/\n')

    return {'products': N_PRODUCTS, 'pages': N_PAGES,
            'malformed': sorted(malformed_products(seed)),
            'outdir': outdir}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('outdir')
    ap.add_argument('--seed', type=int, default=DEFAULT_SEED)
    ap.add_argument('--list', action='store_true', help='print the ground truth')
    args = ap.parse_args()
    if args.list:
        for row in ground_truth(args.seed):
            print('%-9s %-28s %8s %2s %6s %-9s %s' % (
                row['sku'], row['name'], row['price'], row['stock'],
                row['weight_kg'], row['status'], ','.join(row['expected_notes'])))
        return 0
    print(build(args.outdir, args.seed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
