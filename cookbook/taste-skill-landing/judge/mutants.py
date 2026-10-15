#!/usr/bin/env python3
"""Generate known-bad mutant sites for self-testing the judge.

Each mutant is a single-edit copy of examples/good/site and declares the
one check it is intended to trip (a gate name, or a taste_rules
sub-check). selftest.sh reads examples/bad/manifest.json and counts a
kill only when grade.sh exits non-zero AND a readable verdict JSON shows
the intended check failing — a crash, a missing verdict or a kill by the
wrong gate is a survivor, and zero survivors are allowed.

Output: examples/bad/<name>/ + examples/bad/manifest.json (gitignored,
regenerated).
"""

import json
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = os.path.join(BASE, "examples", "good", "site")
BAD = os.path.join(BASE, "examples", "bad")

HTML = "index.html"
CSS = "assets/css/style.css"

INTENDED = {}


def declare(name, gate):
    """Copy the good site to examples/bad/<name> and record the check the
    mutant must fail."""
    dst = os.path.join(BAD, name)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(GOOD, dst)
    INTENDED[name] = gate
    return dst


def patch(path, old, new, count=1):
    with open(path, encoding="utf-8") as f:
        s = f.read()
    if s.count(old) < count:
        raise RuntimeError(f"pattern not found in {path}: {old[:60]!r}")
    s = s.replace(old, new, count)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)
    return s


def append(path, extra):
    with open(path, "a", encoding="utf-8") as f:
        f.write(extra)


def main():
    os.makedirs(BAD, exist_ok=True)

    # low-contrast ink (gate 3: contrast_aa)
    d = declare("low_contrast", "contrast_aa")
    patch(os.path.join(d, CSS), "--ink: #1A241F;", "--ink: #A9A296;")

    # fixed 1200px container (gate 2: no_overflow)
    d = declare("fixed_container", "no_overflow")
    append(os.path.join(d, CSS), "\n/* mutant */\nbody { min-width: 1200px; }\n")

    # pricing section removed (gate 4: brief_sections)
    d = declare("missing_section", "brief_sections")
    s = patch(os.path.join(d, HTML),
              '<section id="pricing">', '<section data-id="pricing-mutant">')
    assert 'id="pricing"' not in s

    # console error (gate 1: clean_load)
    d = declare("console_error", "clean_load")
    patch(os.path.join(d, HTML), "</body>",
          '<script>console.error("mutant: boom")</script>\n</body>')

    # remote script load (gate 1: clean_load — the judge's request route
    # must abort it before anything leaves the box)
    d = declare("remote_asset", "clean_load")
    patch(os.path.join(d, HTML), "</body>",
          '<script src="https://cdn.taste-mutant.invalid/remote.js">'
          '</script>\n</body>')

    # external WebSocket (gate 1: clean_load — ctx.route() matches HTTP
    # only, so the judge's WebSocket route must mock the socket). The
    # mocked socket still reports open to the page, so the onopen
    # tripwire fires a fetch() to an external URL; the selftest asserts
    # the attempt was recorded under websocket_remote and every external
    # request was route-aborted — zero bytes left the box.
    d = declare("ws_external", "clean_load")
    patch(os.path.join(d, HTML), "</body>",
          '<script>/* mutant: external WebSocket */\n'
          'var ws = new WebSocket("wss://cdn.taste-mutant.invalid/socket");\n'
          'ws.onopen = function () {\n'
          '  fetch("https://cdn.taste-mutant.invalid/onopen");\n'
          '};</script>\n</body>')

    # default browser font (5.2: no_default_fonts)
    d = declare("default_font", "no_default_fonts")
    append(os.path.join(d, CSS),
           "\n/* mutant */\nbody, h1, h2, h3, p, a, select, label "
           "{ font-family: 'Times New Roman', serif !important; }\n")

    # third typeface (5.1: two_typefaces_max)
    d = declare("third_typeface", "two_typefaces_max")
    append(os.path.join(d, CSS),
           "\n/* mutant */\nh3 { font-family: 'Gill Sans', sans-serif "
           "!important; }\n")

    # sixth+ type size (5.3: type_scale_max_5)
    d = declare("type_scale_burst", "type_scale_max_5")
    patch(os.path.join(d, HTML), "</body>",
          '<div><span style="font-size:13.3px">a</span>'
          '<span style="font-size:17.7px">b</span>'
          '<span style="font-size:22.1px">c</span>'
          '<span style="font-size:29.9px">d</span>'
          '<span style="font-size:36.7px">e</span></div>\n</body>')

    # off-grid spacing (5.4: spacing_scale_4px)
    d = declare("off_grid", "spacing_scale_4px")
    append(os.path.join(d, CSS),
           "\n/* mutant */\nsection { padding-top: 14px !important; }\n")

    # image without alt (5.5: alt_text)
    d = declare("img_no_alt", "alt_text")
    patch(os.path.join(d, HTML),
          ' alt="Three loop ribbons of different lengths drawn on paper">', ">")

    # tiny tap targets (5.6: tap_targets_44px)
    d = declare("tiny_taps", "tap_targets_44px")
    append(os.path.join(d, CSS),
           "\n/* mutant */\n@media (max-width: 480px) {\n"
           "  .nav-links a { padding: 4px 8px !important; }\n"
           "  a.button { padding: 4px 12px !important; }\n}\n")

    # gradient button (5.7: no_gradients)
    d = declare("gradient_button", "no_gradients")
    append(os.path.join(d, CSS),
           "\n/* mutant */\na.button { background-image: "
           "linear-gradient(90deg, #0E6E54, #2FA07C) !important; }\n")

    # box-shadow at rest (5.8: no_shadows_at_rest)
    d = declare("boxed_shadow", "no_shadows_at_rest")
    append(os.path.join(d, CSS),
           "\n/* mutant */\n.live-thing { box-shadow: 0 0 24px #1A241F; }\n")

    # same shadow, but hidden from a getComputedStyle that the artifact
    # monkey-patches in the main world (5.8 again — only caught because
    # the judge measures in an isolated world)
    d = declare("patched_styles", "no_shadows_at_rest")
    append(os.path.join(d, CSS),
           "\n/* mutant */\n.live-thing { box-shadow: 0 0 24px #1A241F; }\n")
    patch(os.path.join(d, HTML), "</body>",
          "<script>/* mutant: poison the main world's getComputedStyle */\n"
          "window.getComputedStyle = (function (orig) {\n"
          "  return function (el, pseudo) {\n"
          "    var s = orig.call(window, el, pseudo);\n"
          "    return new Proxy(s, {get: function (t, k) {\n"
          "      if (k === 'boxShadow' || k === 'textShadow')"
          " return 'none';\n"
          "      var v = t[k];\n"
          "      return typeof v === 'function' ? v.bind(t) : v;\n"
          "    }});\n"
          "  };\n"
          "})(window.getComputedStyle);</script>\n</body>")

    # 1px hairline border (5.9: no_thin_rules)
    d = declare("hairline", "no_thin_rules")
    append(os.path.join(d, CSS),
           "\n/* mutant */\nsection { border-top: 1px solid #1A241F; }\n")

    # monospace body text (5.10: no_monospace_outside_code)
    d = declare("mono_body", "no_monospace_outside_code")
    append(os.path.join(d, CSS),
           "\n/* mutant */\n.qa p, .footer-meta { font-family: "
           "'Courier New', monospace !important; }\n")

    # index-numbered heading (5.11: no_index_numbering)
    d = declare("numbered_step", "no_index_numbering")
    patch(os.path.join(d, HTML),
          "<h3>The Harbour Drag</h3>", "<h3>01 The Harbour Drag</h3>")

    # running text under 16px (5.12: running_text_16px)
    d = declare("tiny_text", "running_text_16px")
    append(os.path.join(d, CSS),
           "\n/* mutant */\np { font-size: 13px !important; }\n")

    # headline wrapped past two lines (5.13: headlines_two_lines) — a
    # longer label inside a capped width wraps at every viewport
    d = declare("long_headline", "headlines_two_lines")
    patch(os.path.join(d, HTML),
          '<h2 class="live-label">Try the wind math</h2>',
          '<h2 class="live-label">Try the wind math for your own '
          'commute and see the honest saving</h2>')
    append(os.path.join(d, CSS),
           "\n/* mutant */\nh2.live-label { max-width: 260px !important; }\n")

    # under the four-picture floor (5.14: image_floor_4)
    d = declare("few_images", "image_floor_4")
    patch(os.path.join(d, HTML),
          '    <img src="assets/img/elevation.png" width="960" height="540"\n'
          '         alt="The stepped elevation profile of the Harbour Drag,'
          ' drawn in three tones">\n', "")

    # clipped control text (5.15: control_text_fits)
    # Reintroduces the reported defect: the hero select keeps height 48px
    # but 16px vertical padding leaves a 16px box for a 24px line box.
    d = declare("clipped_control", "control_text_fits")
    append(os.path.join(d, CSS),
           "\n/* mutant */\n.live-thing select { padding: 16px; }\n")

    # wind-widget sign bug (gate 7: wind_widget_sane)
    # Reintroduces the original sign error: the saving is computed as an
    # ordered difference (second direction minus first, no min/max), so
    # for some winds the widget prints a negative saving.
    d = declare("wind_sign_bug", "wind_widget_sane")
    js = os.path.join(d, "assets", "js", "main.js")
    patch(js,
          "    var best = Math.min(times[0], times[1]);\n"
          "    var worst = Math.max(times[0], times[1]);",
          "    var best = times[0];\n"
          "    var worst = times[1];")

    with open(os.path.join(BAD, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(INTENDED, f, indent=2, sort_keys=True)
        f.write("\n")

    print(f"Created {len(INTENDED)} mutants in {BAD}")


if __name__ == "__main__":
    main()
