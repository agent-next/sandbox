"""judge/mutants.py -- generate known-bad artifacts as single-edit mutants
of examples/good/panel.py.

Usage: python mutants.py <good_panel.py> <out_dir>

Writes <out_dir>/mut_<name>.py for each mutant in MUTANTS, where each
mutant is the good file with exactly one spec-mandated line replaced.
The judge self-test expects every mutant to fail at least one gate.
"""
import os
import sys

MUTANTS = {
    # wrong slider range on slider 1 -> Gate 1 (min/max mismatch)
    "bad_range": ("ui.FloatSlider(min=lo, max=hi) for (lo, hi) in SLIDER_RANGES",
                  "ui.FloatSlider(min=lo, max=hi) for (lo, hi) in [(0.0, 10.0), (0.0, 20.0), (0.0, 99.0)]"),
    # wrong swatch color -> Gate 1 (color) + Gate 2 (pixel)
    "bad_color": ("SWATCH_RGBA = (0.2, 0.5, 0.9, 1.0)",
                  "SWATCH_RGBA = (0.9, 0.2, 0.1, 1.0)"),
    # missing third slider -> Gate 2 (rects undefined / only 3 refs spec; window too short)
    "missing_slider": ("ui.FloatSlider(min=lo, max=hi) for (lo, hi) in SLIDER_RANGES",
                       "ui.FloatSlider(min=lo, max=hi) for (lo, hi) in SLIDER_RANGES[:2]"),
    # wrong button text -> Gate 2 (button text region empty)
    "bad_button_text": ('ui.Button("Apply")', 'ui.Button("Save")'),
    # swatch overflow: width larger than window -> Gate 2 (overflow / wrong swatch rect)
    "swatch_overflow": ("width=ui.Pixel(SWATCH_W),",
                        "width=ui.Pixel(500),"),
    # empty window: everything except the window body removed -> Gate 1 + Gate 2
    "empty_window": ("ui.FloatSlider(min=lo, max=hi) for (lo, hi) in SLIDER_RANGES",
                     "ui.FloatSlider(min=lo, max=hi) for (lo, hi) in []"),
}


def mutate(src, old, new):
    if old not in src:
        raise SystemExit(f"mutant source line not found: {old!r}")
    return src.replace(old, new, 1)


def main():
    good_path, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    src = open(good_path).read()
    for name, (old, new) in MUTANTS.items():
        out = os.path.join(out_dir, f"mut_{name}.py")
        with open(out, "w") as f:
            f.write(mutate(src, old, new))
    print(f"wrote {len(MUTANTS)} mutants to {out_dir}")


if __name__ == "__main__":
    main()
