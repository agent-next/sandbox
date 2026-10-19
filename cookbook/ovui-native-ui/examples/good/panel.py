"""examples/good/panel.py -- known-good ovui "Tool Panel".

Builds the panel fixed by SPEC.md: a 420x360 ``ui.Window`` titled
"Tool Panel" holding three labelled ``FloatSlider`` rows (0..10, 0..20,
0..50), a 140x24 ``ColorWidget`` swatch of rgba (0.2, 0.5, 0.9, 1.0), a
``CheckBox`` and an "Apply" ``Button``; then returns the window and the
named widget references the judge reads.

Importing this module has no side effects; ``build_panel()`` builds the
panel and returns ``(window, refs)``. The frame loop is driven by the
judge's harness (judge/render.py), never by this file.
"""

import omni.ui as ui

# Fixed by SPEC.md
TITLE = "Tool Panel"
WINDOW_W, WINDOW_H = 420, 360
SLIDER_RANGES = [(0.0, 10.0), (0.0, 20.0), (0.0, 50.0)]
SLIDER_LABELS = ("S1", "S2", "S3")
ROW_W, ROW_H = 300, 24
LABEL_W = 32
SWATCH_RGBA = (0.2, 0.5, 0.9, 1.0)
SWATCH_W, SWATCH_H = 140, 24
CHECKBOX_W, CHECKBOX_H = 140, 22
BUTTON_W, BUTTON_H = 140, 28


def build_panel():
    """Build the spec panel; return ``(window, refs)``."""
    window = ui.Window(TITLE, width=WINDOW_W, height=WINDOW_H)
    sliders = []
    with window.frame:
        with ui.VStack(spacing=6):
            for label, (lo, hi) in zip(SLIDER_LABELS, SLIDER_RANGES):
                with ui.HStack(width=ui.Pixel(ROW_W), height=ui.Pixel(ROW_H)):
                    ui.Label(label, width=ui.Pixel(LABEL_W))
                    sliders.append(ui.FloatSlider(min=lo, max=hi))
            swatch = ui.ColorWidget(
                *SWATCH_RGBA,
                width=ui.Pixel(SWATCH_W), height=ui.Pixel(SWATCH_H))
            checkbox = ui.CheckBox(
                width=ui.Pixel(CHECKBOX_W), height=ui.Pixel(CHECKBOX_H))
            button = ui.Button(
                "Apply", width=ui.Pixel(BUTTON_W), height=ui.Pixel(BUTTON_H))

    refs = {
        "window": window,
        "slider1": sliders[0],
        "slider2": sliders[1],
        "slider3": sliders[2],
        "checkbox": checkbox,
        "button": button,
        "swatch": swatch,
    }
    return window, refs
