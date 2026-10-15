#!/usr/bin/env python3
"""Write the fixture app this demo reviews.

Three build trees of one dashboard route, byte-identical apart from the
intended change and (in `sneaky`) one extra cosmetic edit:

    base    the route before the change
    head    after the intended change: the Signups card is rewritten
    sneaky  head, plus the footer shifted up 3 px -- the change that must
            fail the review

Also writes `patch.diff`, the unified diff base -> head, so "apply the patch
then review it" is a literal step.

stdlib only; every choice comes from --seed, so a fresh generate is
reproducible.  Usage:

    gen.py <outdir> [--seed N] [--font /abs/path/DejaVuSans.ttf]
"""

import argparse
import difflib
import hashlib
import os
import sys

# ---------------------------------------------------------------------------
# Fixed geometry.  The viewport is 1280x720 and the page is laid out to fit in
# it with no scrolling, so the footer is inside every screenshot.
# ---------------------------------------------------------------------------
VIEWPORT_W = 1280
VIEWPORT_H = 720

# Card geometry is snapped to the 32x24 judge block grid: CARD_TOP is a
# multiple of 24, CARD_H a multiple of 24, and the card width a multiple of
# 32, so a changed card covers an exact whole number of blocks and the
# bounding box is a clean rectangle.
CARD_GAP = 24
CARD_TOP = 144
CARD_H = 120
CARD_COLS = 4
CARD_W = (VIEWPORT_W - 2 * 32 - (CARD_COLS - 1) * CARD_GAP) // CARD_COLS

SPARK_BARS = 24

# The footer must render identically in all three builds: the judge requires
# zero changed blocks outside the intended card, and a build stamp in the
# footer would be a second region of its own.
FOOTER_REV = "d4e5f6a"


# ---------------------------------------------------------------------------
# The deterministic data behind the numbers.  A linear congruential generator
# keeps the seeded values stable across Python versions, which `random` does
# not guarantee.
# ---------------------------------------------------------------------------
def _lcg(seed):
    state = seed & 0xFFFFFFFF
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield state


def seeded_numbers(seed, count, lo, hi):
    gen = _lcg(seed)
    span = hi - lo + 1
    return [lo + (next(gen) % span) for _ in range(count)]


CARDS = [
    # (key, label, base value, head value, base delta, head delta)
    ("visits", "Visits", "18,204", "18,204", "+2.1%", "+2.1%"),
    ("signups", "Signups", "1,248", "1,491", "+0.4%", "+6.8%"),
    ("trials", "Trials", "312", "312", "-1.2%", "-1.2%"),
    ("churn", "Churn", "4.1%", "4.1%", "-0.3%", "-0.3%"),
]

ROWS = [
    ("/dashboard", "18,204", "1,248", "01:42", "ok"),
    ("/pricing", "9,881", "601", "02:10", "ok"),
    ("/checkout", "4,213", "1,007", "02:31", "slow"),
    ("/blog/2026-q3-review", "7,650", "96", "03:04", "ok"),
    ("/docs/quickstart", "12,004", "388", "03:22", "ok"),
    ("/api/v2/metrics", "1,802", "44", "04:55", "ok"),
]


# ---------------------------------------------------------------------------
# The page.
# ---------------------------------------------------------------------------
def css(font_family, variant):
    """The stylesheet.  `variant` only changes the footer transform in sneaky,
    and the intended card's colours in head/sneaky."""
    footer_extra = ""
    if variant == "sneaky":
        footer_extra = ("\n  /* unrelated cleanup in the same commit */\n"
                        "  transform: translateY(-3px);")

    if variant in ("head", "sneaky"):
        intended = ("\n.card[data-card=\"signups\"] { color: #4e342e;"
                    " background: #ffcc80; }\n"
                    ".card[data-card=\"signups\"] .delta { color: #1b5e20; }\n")
    else:
        intended = ("\n.card[data-card=\"signups\"] { color: #0b2b45;"
                    " background: #eef6ff; }\n"
                    ".card[data-card=\"signups\"] .delta { color: #0a6c3b; }\n")

    return """:root {{
  --ink: #1a2430; --muted: #5b6b7c; --line: #d8e0e8; --bg: #f5f7f9;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{
  width: {VW}px; height: {VH}px; overflow: hidden;
  background: var(--bg); color: var(--ink);
  font-family: {FONT}; font-size: 14px; line-height: 20px;
  -webkit-font-smoothing: antialiased;
}}
.topbar {{
  height: 56px; background: #12283d; color: #ffffff;
  display: flex; align-items: center; padding: 0 32px;
}}
.topbar .brand {{ font-size: 15px; font-weight: bold; letter-spacing: .4px; }}
.topbar nav {{ margin-left: 40px; display: flex; gap: 24px; color: #c6d4e2; }}
.topbar nav .on {{ color: #ffffff; border-bottom: 2px solid #4da3ff;
  height: 56px; display: flex; align-items: center; }}
.main {{ padding: 24px 32px 0 32px; }}
h1 {{ font-size: 20px; line-height: 28px; margin: 0 0 4px 0; font-weight: bold; }}
.sub {{ color: var(--muted); margin: 0 0 20px 0; }}
.cards {{ display: flex; gap: {GAP}px; }}
.card {{
  width: {CW}px; height: {CH}px; background: #ffffff;
  border: 1px solid var(--line); padding: 12px 14px;
}}
.card .label {{ color: var(--muted); font-size: 12px; line-height: 16px;
  text-transform: uppercase; letter-spacing: .6px; }}
.card .value {{ font-size: 28px; line-height: 34px; font-weight: bold;
  margin-top: 2px; }}
.card .delta {{ font-size: 12px; line-height: 16px; margin-top: 2px; }}
.panels {{ display: flex; gap: 16px; margin-top: 20px; }}
.panel {{ background: #ffffff; border: 1px solid var(--line); padding: 14px 16px; }}
.panel.traffic {{ width: 524px; }}
.panel.table {{ flex: 1; }}
.panel h2 {{ font-size: 13px; line-height: 18px; margin: 0 0 12px 0;
  text-transform: uppercase; letter-spacing: .6px; color: var(--muted);
  font-weight: bold; }}
.spark {{ display: flex; align-items: flex-end; gap: 3px; height: 96px; }}
.spark .bar {{ width: 18px; background: #4da3ff; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: left; padding: 3px 8px 3px 0; font-size: 13px;
  line-height: 18px; border-bottom: 1px solid #eef2f6; }}
th {{ color: var(--muted); font-size: 11px; text-transform: uppercase;
  letter-spacing: .5px; }}
td.num {{ text-align: right; padding-right: 0; }}
.ok {{ color: #0a6c3b; }}
.slow {{ color: #a5610a; }}
.footer {{
  position: absolute; left: 0; bottom: 0; width: {VW}px; height: 40px;
  background: #12283d; color: #c6d4e2; display: flex; align-items: center;
  padding: 0 32px; font-size: 12px; line-height: 16px;{FOOTER}
}}
.footer .right {{ margin-left: auto; }}
{INTENDED}""".format(
        VW=VIEWPORT_W, VH=VIEWPORT_H, GAP=CARD_GAP, CW=CARD_W, CH=CARD_H,
        FOOTER=footer_extra, FONT=font_family, INTENDED=intended)


def card_html(card, variant):
    key, label, base_v, head_v, base_d, head_d = card
    value = head_v if variant in ("head", "sneaky") else base_v
    delta = head_d if variant in ("head", "sneaky") else base_d
    cls = "up" if delta.startswith("+") else "down"
    return (
        '      <div class="card" data-card="{key}">\n'
        '        <div class="label">{label}</div>\n'
        '        <div class="value">{value}</div>\n'
        '        <div class="delta {cls}">{delta} vs last week</div>\n'
        '      </div>\n'
    ).format(key=key, label=label, value=value, delta=delta, cls=cls)


def sparkline_html(variant, seed):
    """Deterministic bar heights, identical in all three builds."""
    heights = seeded_numbers(seed, SPARK_BARS, 24, 96)
    bars = "".join(
        '        <div class="bar" style="height:%dpx"></div>\n' % h
        for h in heights)
    return '    <div class="spark">\n%s    </div>\n' % bars


def table_html():
    out = ['    <table>\n',
           '      <tr><th>Path</th><th>Views</th><th>Signups</th>'
           '<th>P95</th><th>Status</th></tr>\n']
    for path, views, signups, p95, status in ROWS:
        out.append(
            '      <tr><td>{path}</td><td class="num">{views}</td>'
            '<td class="num">{signups}</td><td class="num">{p95}</td>'
            '<td class="{cls}">{status}</td></tr>\n'.format(
                path=path, views=views, signups=signups, p95=p95,
                status=status, cls=status))
    out.append('    </table>\n')
    return ''.join(out)


def page_html(variant, font_family, seed):
    cards = ''.join(card_html(c, variant) for c in CARDS)
    # the intended card carries the marker in every build, so the judge can
    # find it without knowing which text changed
    cards = cards.replace('data-card="signups"',
                          'data-card="signups" data-pdr-intended="1"', 1)
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Acme Analytics / dashboard</title>
<link rel="stylesheet" href="/assets/app.css">
</head>
<body>
  <header class="topbar">
    <span class="brand">ACME ANALYTICS</span>
    <nav><span class="on">Dashboard</span><span>Reports</span><span>Audiences</span></nav>
  </header>
  <main class="main">
    <h1>Product dashboard</h1>
    <p class="sub">Rolling 7 days &middot; updated 2026-10-15 04:00 UTC</p>
    <section class="cards">
{CARDS}    </section>
    <section class="panels">
      <div class="panel traffic">
        <h2>Traffic by hour &middot; last 24 h</h2>
{SPARK}      </div>
      <div class="panel table">
        <h2>Top paths</h2>
{TABLE}      </div>
    </section>
  </main>
  <footer class="footer" data-region="footer">
    <span>&copy; 2026 Acme Analytics</span>
    <span class="right">build {REV} &middot; env production</span>
  </footer>
</body>
</html>
""".format(CARDS=cards, SPARK=sparkline_html(variant, seed),
           TABLE=table_html(), REV=FOOTER_REV)


APP_JS = """// The fixture app has no behaviour worth testing: the route is static, so a
// screenshot is reproducible.  This file exists because a real app has one.
document.querySelectorAll(".spark .bar").forEach(function (bar) {
  bar.setAttribute("data-bar", "1");
});
"""


def write_tree(root, files):
    os.makedirs(os.path.join(root, "assets"), exist_ok=True)
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outdir")
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--font", default=None,
                    help="absolute path of a .ttf/.otf to @font-face; the page "
                         "renders in whatever the machine has when omitted")
    args = ap.parse_args(argv[1:])

    root = os.path.abspath(args.outdir)
    out = {"base": {}, "head": {}, "sneaky": {}}

    font_family = '"DejaVu Sans", sans-serif'
    font_face = ""
    if args.font:
        if not os.path.isfile(args.font):
            raise SystemExit("gen: --font %s is not a file" % args.font)
        font_dir = os.path.join(root, "font")
        os.makedirs(font_dir, exist_ok=True)
        dest = os.path.join(font_dir, "DejaVuSans.ttf")
        with open(args.font, "rb") as src, open(dest, "wb") as dst:
            dst.write(src.read())
        font_family = '"FixtureSans", sans-serif'
        font_face = (
            '@font-face {\n  font-family: "FixtureSans";\n'
            '  src: url("/font/DejaVuSans.ttf") format("truetype");\n'
            '  font-weight: normal;\n  font-style: normal;\n}\n\n')
        sys.stderr.write("gen: font %s -> %s\n" % (args.font, dest))

    for variant in ("base", "head", "sneaky"):
        out[variant] = {
            "index.html": page_html(variant, font_family, args.seed),
            "assets/app.css": font_face + css(font_family, variant),
            "assets/app.js": APP_JS,
        }

    for variant in ("base", "head", "sneaky"):
        write_tree(os.path.join(root, variant), out[variant])

    # patch.diff: base -> head.  Generated, not hand-written, so it cannot
    # disagree with the builds.
    chunks = []
    for label in ("index.html", "assets/app.css"):
        diff = difflib.unified_diff(
            out["base"][label].splitlines(True), out["head"][label].splitlines(True),
            fromfile="a/" + label, tofile="b/" + label, n=3)
        chunks.append(''.join(diff))
    with open(os.path.join(root, "patch.diff"), "w", encoding="utf-8") as fh:
        fh.write(''.join(chunks))

    # A manifest so a reader can see exactly which bytes differ where.
    lines = ['# fixture manifest (generated)', 'seed %d' % args.seed, '']
    for variant in ("base", "head", "sneaky"):
        lines.append('[%s]' % variant)
        for name in sorted(os.listdir(os.path.join(root, variant))):
            sub = os.path.join(root, variant, name)
            if os.path.isdir(sub):
                for f in sorted(os.listdir(sub)):
                    lines.append('  %s/%s %s' % (
                        name, f, sha256(os.path.join(sub, f))))
            else:
                lines.append('  %s %s' % (name, sha256(sub)))
        lines.append('')
    with open(os.path.join(root, "MANIFEST.txt"), "w", encoding="utf-8") as fh:
        fh.write('\n'.join(lines))

    sys.stderr.write("gen: wrote %s (%s)\n" % (root, ', '.join(
        '%s=%s' % (v, sha256(os.path.join(root, v, 'index.html'))[:12])
        for v in ('base', 'head', 'sneaky'))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
