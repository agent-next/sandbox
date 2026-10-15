#!/usr/bin/env python3
"""Generate known-bad mutant sites for self-testing the judge.

Each mutant is a single-edit copy of examples/good/site and must fail at
least one gate. Output: examples/bad/<name>/ (gitignored, regenerated).
"""

import os
import re
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = os.path.join(BASE, "examples", "good", "site")
BAD = os.path.join(BASE, "examples", "bad")

HTML = "index.html"
CSS = "assets/css/style.css"


def clone(name):
    dst = os.path.join(BAD, name)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(GOOD, dst)
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

    # 1. low-contrast ink (gate 3: contrast_aa)
    d = clone("low_contrast")
    patch(os.path.join(d, CSS), "--ink: #1A241F;", "--ink: #A9A296;")

    # 2. fixed 1200px container (gate 2: no_overflow)
    d = clone("fixed_container")
    append(os.path.join(d, CSS), "\n/* mutant */\nbody { min-width: 1200px; }\n")

    # 3. pricing section removed (gate 4: brief_sections)
    d = clone("missing_section")
    s = patch(os.path.join(d, HTML),
              '<section id="pricing">', '<section data-id="pricing-mutant">')
    assert 'id="pricing"' not in s

    # 4. console error (gate 1: clean_load)
    d = clone("console_error")
    append(os.path.join(d, HTML),
           '<script>console.error("mutant: boom")</script>\n')

    # 5. default browser font (gate 5.2: no_default_fonts)
    d = clone("default_font")
    append(os.path.join(d, CSS),
           "\n/* mutant */\nbody, h1, h2, h3, p, a, select, label "
           "{ font-family: 'Times New Roman', serif !important; }\n")

    # 6. tiny tap targets (gate 5.6: tap_targets_44px)
    d = clone("tiny_taps")
    append(os.path.join(d, CSS),
           "\n/* mutant */\n@media (max-width: 480px) {\n"
           "  .nav-links a { padding: 4px 8px !important; }\n"
           "  a.button { padding: 4px 12px !important; }\n}\n")

    # 7. image without alt (gate 5.5: alt_text)
    d = clone("img_no_alt")
    patch(os.path.join(d, HTML),
          ' alt="Three loop ribbons of different lengths drawn on paper">', ">")

    # 8. wind-widget sign bug (gate 7: wind_widget_sane)
    # Reintroduces the original sign error: the saving is computed as an
    # ordered difference (second direction minus first, no min/max), so
    # for some winds the widget prints a negative saving.
    d = clone("wind_sign_bug")
    js = os.path.join(d, "assets", "js", "main.js")
    patch(js,
          "    var best = Math.min(times[0], times[1]);\n"
          "    var worst = Math.max(times[0], times[1]);",
          "    var best = times[0];\n"
          "    var worst = times[1];")

    # 9. gradient button (gate 5.7: no_gradients)
    d = clone("gradient_button")
    append(os.path.join(d, CSS),
           "\n/* mutant */\na.button { background-image: "
           "linear-gradient(90deg, #0E6E54, #2FA07C) !important; }\n")

    # 10. clipped control text (gate 5.15: control_text_fits)
    # Reintroduces the reported defect: the hero select keeps height 48px
    # but 16px vertical padding leaves a 16px box for a 24px line box.
    d = clone("clipped_control")
    append(os.path.join(d, CSS),
           "\n/* mutant */\n.live-thing select { padding: 16px; }\n")

    print(f"Created 10 mutants in {BAD}")


if __name__ == "__main__":
    main()
