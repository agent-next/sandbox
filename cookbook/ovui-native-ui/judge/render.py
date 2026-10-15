"""judge/render.py -- render an ovui panel artifact headless and dump the
facts the judge grades from.

Run by grade.sh:

    OMNIUI_HEADLESS=1 OMNIUI_LAVAPIPE=1 OMNIUI_BACKEND=vulkan \
        LD_LIBRARY_PATH=<cuda-stub> \
        python render.py <panel.py> <out.png> <facts.json>

Imports the artifact in this process (the artifact's module body must not
run the frame loop), calls its ``build_panel() -> (window, refs)``, settles
9 frames, reads the refs' live widget geometry/models, and saves a
screenshot. Exits 0 only on success.

The harness owns the frame loop and the screenshot, so the artifact cannot
substitute a baked image or skip the render.
"""
import json
import os
import sys

os.environ.setdefault("OMNIUI_HEADLESS", "1")
os.environ.setdefault("OMNIUI_LAVAPIPE", "1")
os.environ.setdefault("OMNIUI_BACKEND", "vulkan")

REFS = ("window", "slider1", "slider2", "slider3", "checkbox", "button", "swatch")
SETTLE_FRAMES = 9


def _num(v):
    """Return v as float if it is a plain number, else None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _widget_facts(w):
    """Facts of one widget, all read from the live object."""
    facts = {"type": type(w).__name__}
    for attr in ("title", "text"):
        try:
            v = getattr(w, attr)
            if isinstance(v, str):
                facts[attr] = v
        except Exception:
            pass
    for attr in ("min", "max", "width", "height", "position_x", "position_y",
                 "screen_position_x", "screen_position_y",
                 "computed_width", "computed_height"):
        try:
            v = _num(getattr(w, attr))
            if v is not None:
                facts[attr] = v
        except Exception:
            pass
    # ColorWidget: the widget's colour model, first channel of each child
    if type(w).__name__ == "ColorWidget":
        try:
            model = w.model
            chans = []
            for child in model.get_item_children():
                vm = model.get_item_value_model(child, 0)
                chans.append(float(vm.get_value_as_float()))
            if len(chans) >= 3:
                facts["color"] = chans
        except Exception:
            pass
    return facts


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: render.py <panel.py> <out.png> <facts.json>")
    panel_path, out_png, facts_json = sys.argv[1:4]

    import importlib.util

    import omni.ui as ui
    from omni.ui import testing

    spec = importlib.util.spec_from_file_location("panel_artifact", panel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    build = getattr(mod, "build_panel", None)
    if build is None:
        raise SystemExit("artifact has no build_panel()")

    result = {}

    async def _main():
        built = build()
        if not (isinstance(built, tuple) and len(built) == 2):
            raise SystemExit("build_panel() must return (window, refs)")
        _window, refs = built
        if not isinstance(refs, dict):
            raise SystemExit("build_panel() must return a dict of refs")
        await testing.wait_frames(SETTLE_FRAMES)
        facts = {}
        for name in REFS:
            w = refs.get(name)
            if w is not None:
                facts[name] = _widget_facts(w)
        facts["_ref_names"] = sorted(refs.keys())
        if not testing.capture_screenshot(out_png):
            raise SystemExit("capture_screenshot returned False")
        result["facts"] = facts

    ui.run(_main())

    with open(facts_json, "w") as f:
        json.dump(result["facts"], f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
