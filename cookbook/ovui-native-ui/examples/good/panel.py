"""examples/good/panel.py -- known-good ovui Tool Panel.

Builds the SPEC.md panel (title, 3 labelled FloatSliders in fixed-width
rows, CheckBox, Button, a 140x24 ColorWidget swatch rgba (0.2,0.5,0.9,1))
and returns the window and named widget references for the judge.
"""

import sys

import omni.ui as ui

# Spec values (fixed by SPEC.md)
TITLE = "Tool Panel"
SLIDER_RANGES = [(0.0, 10.0), (0.0, 20.0), (0.0, 50.0)]
SLIDER_LABELS = ("S1", "S2", "S3")
SWATCH_RGBA = (0.2, 0.5, 0.9, 1.0)
SWATCH_W, SWATCH_H = 140, 24
WINDOW_W, WINDOW_H = 420, 360
SLIDER_ROW_W = 300
LABEL_W = 32


def build_panel():
    """Build the spec panel and return (window, refs)."""
    window = ui.Window(TITLE, width=WINDOW_W, height=WINDOW_H)
    with window.frame:
        with ui.VStack():
            sliders = []
            for label, (lo, hi) in zip(SLIDER_LABELS, SLIDER_RANGES):
                with ui.HStack(width=ui.Pixel(SLIDER_ROW_W)):
                    ui.Label(label, width=ui.Pixel(LABEL_W))
                    sliders.append(ui.FloatSlider(min=lo, max=hi))
            swatch = ui.ColorWidget(
                *SWATCH_RGBA, width=ui.Pixel(SWATCH_W), height=ui.Pixel(SWATCH_H))
            checkbox = ui.CheckBox()
            button = ui.Button("Apply")
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


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/panel.png"
    from omni.ui import testing

    async def _main():
        build_panel()
        await testing.wait_frames(9)
        ok = testing.capture_screenshot(out)
        print("screenshot:", ok)

    ui.run(_main())
