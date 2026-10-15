"""judge/mutants.py -- generate known-bad artifacts as single-edit mutants
of examples/good/panel.py.

Usage: python mutants.py <good_panel.py> <out_dir>

Each mutant is the good file with exactly one spec-relevant edit. The
self-test expects every mutant to fail at least one gate. The edits map to
the known-bad classes in SPEC.md: missing slider, wrong slider range, wrong
swatch colour, layout overflow outside the window, empty window -- plus
wrong button text, wrong swatch size, a baked-PNG artifact, and a
nondeterministic render.
"""
import os
import sys

# name -> (old, new); applied as a single str.replace on the good source
MUTANTS = {
    # -- the classes named in the brief ------------------------------------
    # missing slider: the third row's widget is not a FloatSlider, so the
    # panel still builds and renders and the widget-tree gate must catch it
    "missing_slider": (
        "sliders.append(ui.FloatSlider(min=lo, max=hi))",
        "sliders.append(ui.FloatSlider(min=lo, max=hi)\n                              if hi != 50.0 else ui.Label(\"S3\"))"),
    # wrong slider range: slider 3 is 0..99 instead of 0..50
    "wrong_range": (
        "SLIDER_RANGES = [(0.0, 10.0), (0.0, 20.0), (0.0, 50.0)]",
        "SLIDER_RANGES = [(0.0, 10.0), (0.0, 20.0), (0.0, 99.0)]"),
    # wrong swatch colour
    "wrong_swatch_color": (
        "SWATCH_RGBA = (0.2, 0.5, 0.9, 1.0)",
        "SWATCH_RGBA = (0.9, 0.2, 0.1, 1.0)"),
    # layout overflow: the swatch is wider than the window content region
    "swatch_overflow": (
        "SWATCH_W, SWATCH_H = 140, 24",
        "SWATCH_W, SWATCH_H = 500, 24"),
    # empty window: no sliders at all
    "empty_window": (
        "for label, (lo, hi) in zip(SLIDER_LABELS, SLIDER_RANGES):",
        "for label, (lo, hi) in zip(SLIDER_LABELS, []):"),

    # -- further single-edit mutants ---------------------------------------
    # wrong button text: the required "Apply" label is gone
    "wrong_button_text": ('ui.Button(\n                "Apply"', 'ui.Button(\n                "Save"'),
    # wrong swatch size: colour is right, geometry is not
    "wrong_swatch_size": (
        "SWATCH_W, SWATCH_H = 140, 24",
        "SWATCH_W, SWATCH_H = 90, 24"),
    # missing checkbox: the widget tree loses a required type
    "missing_checkbox": (
        "checkbox = ui.CheckBox(",
        "checkbox = ui.Label("),
    # missing swatch: the widget tree loses a required type
    "missing_swatch": (
        "ui.ColorWidget(\n                *SWATCH_RGBA,",
        'ui.Label(\n                "swatch",'),
}

# not single-line edits: whole-file replacements for behaviour classes the
# judge must also catch
BAKED_PNG = '''"""Baked-PNG artifact: returns widgets but renders nothing of its own."""
import omni.ui as ui

_PNG = __file__.replace("panel.py", "baked.png")


def build_panel():
    window = ui.Window("Tool Panel", width=420, height=360)
    with window.frame:
        pass
    refs = {"window": window, "slider1": None, "slider2": None, "slider3": None,
            "checkbox": None, "button": None, "swatch": None}
    return window, refs
'''

NONDETERMINISTIC = '''"""Nondeterministic artifact: the swatch colour changes every run."""
import random

import omni.ui as ui
'''




def mutate(src, old, new, name):
    if old not in src:
        raise SystemExit(f"mutant {name}: source line not found: {old!r}")
    return src.replace(old, new, 1)


def main():
    good_path, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    src = open(good_path).read()

    written = []
    for name, (old, new) in MUTANTS.items():
        out = os.path.join(out_dir, f"mut_{name}.py")
        with open(out, "w") as f:
            f.write(mutate(src, old, new, name))
        written.append(name)

    # baked PNG: a widget-less window; no live widgets to read, nothing drawn
    with open(os.path.join(out_dir, "mut_baked_png.py"), "w") as f:
        f.write(BAKED_PNG)
    written.append("baked_png")

    # nondeterministic: the S1 row label gets a random suffix, so the panel
    # renders differently in each process. Every graded rect (the FloatSlider
    # rows, swatch, checkbox, button) is untouched, so gates 0-2 still pass
    # and only the byte-identical-render gate catches it.
    nd = src.replace("import omni.ui as ui",
                     "import random\n\nimport omni.ui as ui", 1)
    nd = nd.replace("ui.Label(label, width=ui.Pixel(LABEL_W))",
                    "ui.Label(label + str(random.randint(0, 9)),"
                    " width=ui.Pixel(LABEL_W))", 1)
    assert "random.randint" in nd, "nondeterministic mutant edit did not apply"
    with open(os.path.join(out_dir, "mut_nondeterministic.py"), "w") as f:
        f.write(nd)
    written.append("nondeterministic")

    print(f"wrote {len(written)} mutants to {out_dir}: {' '.join(written)}")


if __name__ == "__main__":
    main()
