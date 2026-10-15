# SPEC: ovui native tool panel (NVIDIA Omniverse `ovui`, headless Vulkan on lavapipe)

## Goal

Show an agent building a small **native 3D-tool UI panel** with
[NVIDIA Omniverse `ovui`](https://github.com/NVIDIA-Omniverse/ovui) (pip
`ovui`, Apache-2.0) inside a CPU-only agent-next sandbox, and rendering it
**headless** through ovui's offscreen Vulkan backend on Mesa lavapipe (a
CPU software renderer: no GPU, no display, no NVIDIA driver). A judge that
checks the rendered pixels *and* the live widget objects decides whether
the panel matches the fixed spec below.

The panel is a real ovui/ImGui/Vulkan render, not a drawing: the same
software stack that drives a 3D tool's docked panel, with the window
offscreen. ovui's own headless documentation
(`ovui/HEADLESS.md`, "Running without a GPU (Lavapipe / software ICD)")
describes this path; the demo is that path in a sandbox.

### Why the CUDA stubs

`omni.ui`'s shared objects declare `DT_NEEDED` on `libcuda.so.1` and
`libcudart.so.12`, so on a CPU-only host a bare `import omni.ui` fails with
`libcuda.so.1: cannot open shared object file`. `judge/setup.sh` compiles
two **stub** libraries (generated from the exact undefined-symbol list of
the installed ovui shared objects) that report "no CUDA device". With
`OMNIUI_LAVAPIPE=1`, ovui logs

```
VulkanBackend: selected device: "llvmpipe (LLVM 15.0.6, 256 bits)" (vendorID=0x10005, type=CPU (software renderer))
VulkanBackend: device does not support VK_KHR_external_semaphore_fd, CUDA interop disabled
VulkanBackend: initialized successfully (1280x720, offscreen)
```

and renders. The stubs are never *called* on this path — they only satisfy
the dynamic linker. No CUDA device, driver or account is involved.

## Non-goals

- Interactive editing, scene manipulators, or the `omni.ui.scene` 3D viewport.
- Any GPU/CUDA path: the demo must prove CPU-only works.
- Fonts/DPI variants, multiple panel designs, animation: one settled frame is the artifact.
- ovui features beyond the widget types listed below.

## Artifact

One Python file, `panel.py`, importable without side effects, defining

```python
def build_panel() -> tuple["omni.ui.Window", dict]:
    ...
```

It builds the spec panel and returns `(window, refs)`, where `refs` maps
exactly these names to the **widget objects** it created: `window`,
`slider1`, `slider2`, `slider3` (the three `ui.FloatSlider`, in spec order),
`checkbox`, `button`, `swatch`. The judge reads geometry, slider ranges and
the swatch colour directly from these live objects, and renders through its
own harness (`judge/render.py`), which the artifact cannot modify or feed:
the harness binds the screenshot path, the frame tick, the widget classes,
the window lookup and the tree walk to locals **before** importing the
artifact; it looks the spec window up itself and requires every ref to be
an instance of a pre-bound class and a live widget of that window's tree
(`Inspector.get_children`). An artifact that returns plain objects named
after the widget classes with attributes copied from a real run, and swaps
`omni.ui.testing.capture_screenshot` for a function writing baked PNG
bytes, fails gates 1 and 2: the screenshot is taken by the pre-bound
function from the real framebuffer, which drew no panel.

The artifact may import only `omni.ui` (and its submodules), `numpy`, and
the Python standard library. Its module body must not run the frame loop.

Known-good: `examples/good/panel.py`.

## Fixed spec for the panel

| element | requirement |
|---|---|
| window | `ui.Window` titled `Tool Panel`, `width=420`, `height=360` |
| body layout | inside the window frame, one `ui.VStack`: three slider rows, then swatch, checkbox, button, in that order |
| slider rows | each slider in its own `ui.HStack` of `width=300 px`, `height=24 px`, beside a `ui.Label` (`S1`,`S2`,`S3`, `width=32 px`) |
| slider 1 | `ui.FloatSlider`, `min=0.0`, `max=10.0` |
| slider 2 | `ui.FloatSlider`, `min=0.0`, `max=20.0` |
| slider 3 | `ui.FloatSlider`, `min=0.0`, `max=50.0` |
| color swatch | one `ui.ColorWidget`, constant colour rgba `(0.2, 0.5, 0.9, 1.0)`, `width=140 px`, `height=24 px` |
| checkbox | one `ui.CheckBox`, `width=140 px`, `height=22 px` |
| button | one `ui.Button` with visible text `Apply`, `width=140 px`, `height=28 px` |

Widget *values* (slider values, checkbox state, callbacks) are the agent's
free choice. Widget types, slider ranges, the swatch colour and size, the
window title and size, and the resulting layout are not.

## Gates (numeric pass rules)

`judge/grade.sh <panel.py> [--seed N] [--json out.json]` runs every gate on
a scratch copy of the artifact and exits 0 only if every gate passes.

- **Gate 0 — runs and renders.** `judge/render.py` imports the artifact,
  calls `build_panel()`, settles 9 frames, and saves a screenshot, inside a
  90 s wall limit; exit 0, `out.png` is a valid PNG at least 420x360. A
  build crash exits non-zero with the exception's own name and message
  (the reason is not swallowed by the frame loop).
- **Gate 1 — widget objects.** From the returned `refs`:
  - every ref is an instance of the matching pre-bound `omni.ui` class
    (the harness binds `ui.Window`, `ui.FloatSlider`, `ui.CheckBox`,
    `ui.Button`, `ui.ColorWidget` before importing the artifact, so a
    class merely *named* `FloatSlider` does not pass) and a live widget
    of the window's tree, which the harness walks itself with
    `Inspector.get_children`; `refs["window"]` must *be* the window the
    judge looked up itself via `ui.Workspace.get_window("Tool Panel")`;
  - `refs["window"]` has `title == "Tool Panel"` and
    `width`/`height` >= 420/360;
  - `refs["slider1".."3"]` are exactly three distinct `ui.FloatSlider`
    instances with `(min, max)` = `(0,10)`, `(0,20)`, `(0,50)` (tol 1e-6);
  - `refs["checkbox"]` is a `ui.CheckBox`; `refs["button"]` is a `ui.Button`
    whose `text` contains `Apply`;
  - `refs["swatch"]` is a `ui.ColorWidget` with `computed_width` 140 +/- 2 and
    `computed_height` 24 +/- 2, and its colour model's first three channels
    equal `(0.2, 0.5, 0.9)` within 1e-6.
- **Gate 2 — pixel spec mask.** Against the screenshot, which the harness
  captured itself through its pre-bound screenshot functions (an artifact
  that rebinds `omni.ui.testing.capture_screenshot` changes nothing: the
  graded image is the real framebuffer of what it built):
  - **no overflow:** every widget rect (from `screen_position_*` /
    `computed_*`) lies fully inside the window content region — the window
    rect (`position_x/y`, `width/height`) inset by the 26 px title bar
    (top) and a 4 px border (other three sides);
  - **expected bboxes:** each widget rect matches its expected bbox in
    `judge/reference.json` within 8 px on position and 4 px on size;
  - **swatch colour:** the median RGB over the swatch rect inset by 3 px
    matches the spec colour (analytic sRGB of `(0.2,0.5,0.9)`, stored in
    `judge/reference.json` as `swatch_rgb`) within `swatch_tol` per channel,
    and that interior is uniform (per-channel std <= `swatch_uniform_std_max`);
  - **widgets drawn:** for each of the six widget rects (inset 2 px), the
    interior differs from the window background by >= 20 luminance in at
    least 20 pixels;
  - **title text drawn:** the title-bar band contains >= 25 pixels whose
    luminance differs from the band median by >= 20;
  - **button text drawn:** the button interior contains >= 25 pixels whose
    luminance differs from the button-face median by >= 28.
- **Gate 3 — determinism.** The judge renders the artifact a second time in
  a fresh process; the two screenshots must be byte-identical and the two
  widget-facts dumps equal. A baked-PNG artifact fails gates 1 and 2
  (no live widgets, no panel drawn); nondeterministic rendering fails
  this gate.

The judge also verifies `judge/` is byte-identical before and after the run,
so an artifact cannot rewrite the judge.

## Acceptance oracle

Nothing passes because "the script ran":

- **Gate 1** reads the *live widget objects* the artifact's own builder
  returned: types by `isinstance` against classes bound before the
  artifact ran, membership in the window tree the harness itself walked,
  slider ranges, swatch size and the swatch colour from the widget's
  colour model. It cannot be satisfied by pixels alone, by plain objects
  named after widget classes, or by refs detached from the live tree.
- **Gate 2** is a **measured spec mask**: required regions (window content
  rect, six widget bboxes, title band, button interior) with numeric
  predicates, all measured from the render the harness itself captured
  through its pre-bound screenshot functions. The swatch target is
  *analytic* — the sRGB value of the spec colour `(0.2, 0.5, 0.9)`,
  `[51, 128, 230]` — not "whatever the good example produced"; the
  tolerance band comes from the known-good's measured 3-render jitter
  (`judge/reference.json`), and the gate additionally requires the
  known-good's measured median to equal the analytic value within that band.
- **Gate 3** needs a fresh process to reproduce the render bit-for-bit, so
  output caching, environment spoofing or a baked screenshot fail. The
  self-test's `baked_png` mutant is exactly that exploit — plain objects
  named after the widget classes with attributes copied from the committed
  `media/data/`, plus `capture_screenshot` swapped for a function writing
  the graded PNG bytes — and the judge kills it on gates 1 and 2.

## Determinism

The lavapipe render is byte-identical across runs for a fixed ovui version,
window geometry and settled frame count (the harness settles 9 frames).
`judge/grade.sh` run twice with the same `--seed` produces byte-identical
verdict JSON except the `timing` key; `judge/selftest.sh` checks this.

## Reproducibility tolerances

A second agent reproducing the demo must obtain, from a fresh sandbox: the
same `pass` verdict for `examples/good/panel.py`, the same swatch median RGB
`[51, 128, 230]` exactly, and the same kill rate. The one number expected to
differ is wall time.
