"""judge/render.py -- render an ovui panel artifact headless and dump its
layout/model facts as JSON.

Run by grade.sh:

    OMNIUI_HEADLESS=1 LD_LIBRARY_PATH=<cuda-stub> \
        python render.py <panel.py> <out.png> <facts.json>

Imports the artifact in this process (the artifact's module body must not
run the frame loop), calls its ``build_panel() -> (window, refs)``,
settles 9 frames, reads the refs' live widget geometry/models, and saves
a screenshot. Exits 0 only on success; writes the facts JSON the judge
grades from.
"""
import json
import os
import sys

os.environ.setdefault("OMNIUI_HEADLESS", "1")

REFS = ("window", "slider1", "slider2", "slider3", "checkbox", "button", "swatch")


def _widget_facts(w):
    """Facts of one widget, all read from the live object."""
    facts = {"type": type(w).__name__}
    for attr in ("title", "text",
                 "screen_position_x", "screen_position_y",
                 "computed_width", "computed_height"):
        try:
            v = getattr(w, attr)
            facts[attr] = float(v) if isinstance(v, (int, float)) else v
        except Exception:
            pass
    for attr in ("min", "max"):
        try:
            facts[attr] = float(getattr(w, attr))
        except Exception:
            pass
    # ColorWidget: first 4 model channels
    try:
        if type(w).__name__ == "ColorWidget":
            model = w.model
            kids = model.get_item_children()
            chans = []
            for k in kids:
                try:
                    vm = model.get_item_value_model(k, 0)
                    chans.append(float(vm.get_value_as_float()))
                except Exception:
                    break
            if len(chans) >= 3:
                facts["color"] = chans[:4]
    except Exception:
        pass
    return facts


def main():
    panel_path, out_png, facts_json = sys.argv[1], sys.argv[2], sys.argv[3]
    import importlib.util
    import omni.ui as ui
    from omni.ui import testing

    spec = importlib.util.spec_from_file_location("panel_artifact", panel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    build = getattr(mod, "build_panel", None)
    if build is None:
        raise SystemExit("artifact has no build_panel()")

    async def _main():
        window, refs = build()
        await testing.wait_frames(9)
        facts = {}
        for name in REFS:
            if name in refs and refs[name] is not None:
                facts[name] = _widget_facts(refs[name])
        ok = testing.capture_screenshot(out_png)
        # include the raw screenshot size so the judge can crop the window
        try:
            from PIL import Image  # noqa: F401  -- pillow is a judge dep
        except Exception:
            pass
        with open(facts_json, "w") as f:
            json.dump(facts, f)
        if not ok:
            raise SystemExit("capture_screenshot returned False")

    ui.run(_main())


if __name__ == "__main__":
    main()
