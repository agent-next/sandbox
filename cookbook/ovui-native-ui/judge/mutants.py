"""judge/mutants.py -- generate known-bad artifacts as single-edit mutants
of examples/good/panel.py.

Usage: python mutants.py <good_panel.py> <out_dir>

Each mutant is the good file with exactly one spec-relevant edit. The
self-test expects every mutant to fail at least one judge gate (a mutant
that only crashes the build proves nothing about the gates). The edits map
to the known-bad classes in SPEC.md: missing slider, wrong slider range,
wrong swatch colour, layout overflow outside the window, empty window --
plus wrong button text, wrong swatch size, a baked-PNG artifact, and a
nondeterministic render. The baked-PNG mutant is the full judge-fooling
exploit (plain objects named after the widget classes, attributes copied
from a real run, capture_screenshot swapped for baked bytes), generated
from the demo's committed media data.
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
    # empty window (visually): the panel builds and the widgets are live,
    # but the VStack is invisible so nothing is drawn -- the pixel gate's
    # "widgets drawn" check must catch it
    "empty_window": (
        "with ui.VStack(spacing=6):",
        "with ui.VStack(spacing=6, visible=False):"),

    # -- further single-edit mutants ---------------------------------------
    # wrong button text: the required "Apply" label is gone
    "wrong_button_text": ('ui.Button(\n                "Apply"', 'ui.Button(\n                "Save"'),
    # wrong swatch size: colour is right, geometry is not
    "wrong_swatch_size": (
        "SWATCH_W, SWATCH_H = 140, 24",
        "SWATCH_W, SWATCH_H = 90, 24"),
    # missing checkbox: the widget tree loses a required type (an empty
    # Label builds fine, so the widget-tree gate has to catch it)
    "missing_checkbox": (
        "checkbox = ui.CheckBox(",
        'checkbox = ui.Label("",'),
    # missing swatch: the widget tree loses a required type
    "missing_swatch": (
        "ui.ColorWidget(\n                *SWATCH_RGBA,",
        'ui.Label(\n                "swatch",'),
}

# not single-line edits: whole-file replacement for the behaviour class the
# judge must also catch. The baked-PNG artifact is the real exploit a
# type-name judge falls for: plain classes *named* after the widget types
# with attributes copied from a real run, plus omni.ui.testing.capture_
# screenshot swapped for a function that writes the graded PNG bytes.
# The module docstring and the bodies below are filled in by
# baked_png_source() from the demo's committed media data.
_BAKED_TEMPLATE = '''"""Baked-PNG artifact: draws nothing, fakes the widgets, swaps the shot.

The classic judge-fooling exploit, in one file:

* builds an empty 50x50 window titled "Nothing" (nothing of the spec is
  drawn anywhere on the framebuffer);
* returns plain-Python objects whose class *names* are the widget types
  (FloatSlider, ColorWidget, ...), with every attribute a real run reports
  copied from media/data/facts.json, so a judge that checks type names,
  ranges, geometry and colour off the returned refs sees a perfect panel;
* replaces omni.ui.testing.capture_screenshot with a function that writes
  the real graded render's PNG bytes (embedded below), so a judge that
  looks the function up after importing the artifact measures a perfect
  screenshot -- twice, byte-identical, so even a determinism gate passes.

Only a harness that binds its screenshot path, its frame tick and the
widget classes *before* importing this file, looks the window up itself
and requires the refs to be live widgets of that window's tree can tell
this artifact from the real panel.
"""
import base64

import omni.ui as ui
from omni.ui import testing

_PNG = base64.b64decode("{png_b64}")

ATTRS = {attrs_literal}


def _make(cls_name, **attrs):
    # a class whose *name* is the widget type -- what a type(w).__name__
    # judge reads
    cls = type(cls_name, (), {{}})
    obj = cls()
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


def _baked_capture_screenshot(filepath):
    with open(filepath, "wb") as f:
        f.write(_PNG)
    return True


def build_panel():
    window = ui.Window("Nothing", width=50, height=50)
    with window.frame:
        pass
    refs = {{name: _make(spec["cls"], **{{k: v for k, v in spec.items()
                                          if k != "cls"}})
            for name, spec in ATTRS.items()}}
    refs["window"] = _make("Window", title="Tool Panel", width=420,
                           height=360)
    testing.capture_screenshot = _baked_capture_screenshot
    return window, refs
'''


def baked_png_source(demo_dir):
    """Build the exploit artifact from the demo's committed real outputs.

    Copies the widget facts of the known-good run (media/data/facts.json)
    and embeds the graded render (media/data/render.png) so the faked
    refs and the baked screenshot would satisfy a type-name judge
    exactly. The demo ships both files; this only reads them.
    """
    import base64
    import json as _json
    from pathlib import Path

    media_data = Path(demo_dir) / "media" / "data"
    render_png = media_data / "render.png"
    facts_json = media_data / "facts.json"
    for p in (render_png, facts_json):
        if not p.is_file():
            raise SystemExit(
                f"baked_png mutant needs {p.name} under media/data/ (the "
                "demo's committed real outputs); not found")
    facts = _json.loads(facts_json.read_text())
    cls_of = {"slider1": "FloatSlider", "slider2": "FloatSlider",
              "slider3": "FloatSlider", "checkbox": "CheckBox",
              "button": "Button", "swatch": "ColorWidget"}
    attrs = {}
    for name, cls in cls_of.items():
        spec = {"cls": cls}
        for k in ("min", "max", "text", "color",
                  "screen_position_x", "screen_position_y",
                  "computed_width", "computed_height"):
            if k in facts.get(name, {}):
                spec[k] = facts[name][k]
        attrs[name] = spec
    return _BAKED_TEMPLATE.format(
        png_b64=base64.b64encode(render_png.read_bytes()).decode(),
        attrs_literal=_json.dumps(attrs, indent=4))


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

    # baked PNG: the full judge-fooling exploit (fake widget objects with
    # copied attributes + capture_screenshot swapped for baked bytes)
    demo_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(good_path))))
    with open(os.path.join(out_dir, "mut_baked_png.py"), "w") as f:
        f.write(baked_png_source(demo_dir))
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
