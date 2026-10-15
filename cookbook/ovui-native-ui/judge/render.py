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
substitute a baked image or skip the render. Because the artifact runs in
this process, everything the judge later reads is bound to locals here
**before** ``exec_module`` runs the artifact, so a module that rebinds
``omni.ui.testing.capture_screenshot``, the frame tick or the ``ui.*``
widget classes cannot affect what is graded:

  * the screenshot path, the frame tick, the widget classes, the window
    lookup and the tree walk are all bound to locals from the C extension
    module first; the artifact can only rebind module attributes, which
    the harness no longer reads;
  * the window is looked up by the judge
    (``ui.Workspace.get_window("Tool Panel")``), never taken on trust
    from the artifact's return value, and ``refs["window"]`` must *be*
    that live window;
  * every other ref must pass ``isinstance`` against the pre-bound
    classes and be one of the live widgets of that window's tree, walked
    by the harness with ``Inspector.get_children``.

A plain-Python object whose class is *named* ``FloatSlider``, with
attributes copied from a real run, and a ``capture_screenshot`` swapped in
to write a baked PNG -- the artifact that would fool a type-name judge --
fails gate 1 (not a pre-bound-class instance, not in the live tree) and
gate 2 (the screenshot is the real framebuffer, which drew no panel).

Errors keep their identity: the coroutine catches its own exceptions,
stores the reason, and render.py exits non-zero with that message instead
of dying on a stray ``KeyError: 'facts'``.
"""
import asyncio
import json
import os
import sys

os.environ.setdefault("OMNIUI_HEADLESS", "1")
os.environ.setdefault("OMNIUI_LAVAPIPE", "1")
os.environ.setdefault("OMNIUI_BACKEND", "vulkan")

from omni.ui import _ui  # noqa: E402  (env vars must be set first)
from omni.ui.standalone import _tick_one_frame, run as UI_RUN  # noqa: E402

REFS = ("window", "slider1", "slider2", "slider3", "checkbox", "button", "swatch")
SETTLE_FRAMES = 9
SPEC_TITLE = "Tool Panel"

# ---- judge-owned bindings: taken before the artifact is imported ------------
CLS_WINDOW = _ui.Window
CLS_FLOAT_SLIDER = _ui.FloatSlider
CLS_CHECKBOX = _ui.CheckBox
CLS_BUTTON = _ui.Button
CLS_COLOR_WIDGET = _ui.ColorWidget
GET_WINDOW = _ui.Workspace.get_window
GET_CHILDREN = _ui.Inspector.get_children
SCHEDULE_SHOT = _ui._schedule_screenshot
POLL_SHOT = _ui._poll_screenshot_done
SHOT_RESULT = _ui._get_screenshot_result
DIRECT_SHOT = _ui._capture_screenshot
TICK = _tick_one_frame
SLEEP = asyncio.sleep
GET_LOOP = asyncio.get_running_loop


def _screenshot(filepath):
    """Capture the framebuffer using only pre-bound C functions.

    Mirrors ``omni.ui.testing.capture_screenshot`` (scheduled pre-swap
    capture, one tick, asyncio pump, then the direct path as fallback) but
    resolves every function through locals bound before the artifact ran,
    so rebinding ``omni.ui.testing.*`` or ``omni.ui.stalone.*`` module
    attributes cannot feed the judge a baked image.
    """
    if SCHEDULE_SHOT(filepath):
        TICK()  # fires the pre-swap capture
        try:
            loop = GET_LOOP()
            loop.call_soon(loop.stop)
            loop.run_forever()
        except RuntimeError:
            pass
        if not POLL_SHOT():
            return False
        result = SHOT_RESULT()
        return bool(result.get("success", False)) if result else True
    return DIRECT_SHOT(filepath)


async def _settle(n):
    """Advance n frames; same primitive pair testing.wait_frames uses."""
    for _ in range(n):
        TICK()
        await SLEEP(0)


def _live_tree(root):
    """The widget objects of root's tree, walked by the harness."""
    out, stack, seen = [], [root], set()
    while stack:
        w = stack.pop()
        if id(w) in seen:
            continue
        seen.add(id(w))
        out.append(w)
        for child in GET_CHILDREN(w):
            stack.append(child)
    return out


def _class_of(w):
    """The widget's class by isinstance against the pre-bound classes."""
    for name, cls in (("Window", CLS_WINDOW), ("FloatSlider", CLS_FLOAT_SLIDER),
                      ("CheckBox", CLS_CHECKBOX), ("Button", CLS_BUTTON),
                      ("ColorWidget", CLS_COLOR_WIDGET)):
        if isinstance(w, cls):
            return name
    return "unknown"


def _num(v):
    """Return v as float if it is a plain number, else None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _widget_facts(w):
    """Facts of one widget, all read from the live object."""
    facts = {"type": _class_of(w)}
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
    if isinstance(w, CLS_COLOR_WIDGET):
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

    # The artifact is imported only after every judge-owned binding above
    # has been taken; from here on the harness reads no module attribute
    # the artifact could rebind.
    spec = importlib.util.spec_from_file_location("panel_artifact", panel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    build = getattr(mod, "build_panel", None)
    if build is None:
        raise SystemExit("artifact has no build_panel()")

    result = {}

    async def _main():
        try:
            built = build()
            if not (isinstance(built, tuple) and len(built) == 2):
                raise SystemExit("build_panel() must return (window, refs)")
            _window, refs = built
            if not isinstance(refs, dict):
                raise SystemExit("build_panel() must return a dict of refs")

            await _settle(SETTLE_FRAMES)

            # the judge looks the spec window up itself; the artifact's
            # ref has to *be* that live window
            live_window = GET_WINDOW(SPEC_TITLE)
            window_live = (live_window is not None
                           and isinstance(live_window, CLS_WINDOW)
                           and refs.get("window") is live_window)
            tree_ids = ({id(w) for w in _live_tree(live_window.frame)}
                        if window_live else set())

            facts = {}
            for name in REFS:
                w = refs.get(name)
                if w is None:
                    continue
                f = _widget_facts(live_window if name == "window" else w)
                f["live"] = (name == "window" and window_live) \
                    or id(w) in tree_ids
                facts[name] = f
            facts["_ref_names"] = sorted(refs.keys())
            facts["_window_live"] = window_live

            if not _screenshot(out_png):
                raise SystemExit("capture_screenshot returned False")
            result["facts"] = facts
        except SystemExit as e:
            result["error"] = str(e) or "SystemExit"
        except Exception as e:  # noqa: BLE001 - the reason must survive
            result["error"] = f"{type(e).__name__}: {e}"

    UI_RUN(_main())

    if "error" in result:
        print(f"render.py: {result['error']}", file=sys.stderr)
        sys.exit(1)
    if "facts" not in result:
        print("render.py: frame loop ended without facts", file=sys.stderr)
        sys.exit(1)

    with open(facts_json, "w") as f:
        json.dump(result["facts"], f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
