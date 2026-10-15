# SPEC: ovui native tool panel (NVIDIA Omniverse `ovui`, headless Vulkan/lavapipe)

## Goal

Demonstrate an agent building a small **native 3D-tool UI panel** with
[NVIDIA Omniverse `ovui`](https://github.com/NVIDIA-Omniverse/ovui) (pip
`ovui`, Apache-2.0) inside a CPU-only agent-next sandbox, rendered
**headless** through ovui's Vulkan offscreen backend on Mesa lavapipe (CPU
renderer; no GPU, no display). A pixel-level judge the agent cannot fool
checks the rendered panel against a fixed UI spec.

ovui headless mode (`OMNIUI_HEADLESS=1`) renders through its real
ImGui/Vulkan stack, so a headless screenshot is pixel-identical to a
display-connected run of the same software version; on a CPU-only host the
Vulkan device is Mesa lavapipe.

## Spec for the artifact (fixed)

The panel the agent must build is fixed in every structural detail:

| element | requirement |
|---|---|
| window | `ui.Window` with title text `Tool Panel`, `width=420`, `height=360` |
| body layout | all widgets below are descendants of a single `ui.VStack` inside the window's frame |
| sliders | exactly 3 `ui.FloatSlider` widgets |
| slider 1 | `min = 0.0`, `max = 10.0` |
| slider 2 | `min = 0.0`, `max = 20.0` |
| slider 3 | `min = 0.0`, `max = 50.0` |
| checkbox | exactly 1 `ui.CheckBox` |
| button | exactly 1 `ui.Button` with text `Apply` |
| color swatch | exactly 1 `ui.ColorWidget`, constant model color rgba `(0.2, 0.5, 0.9, 1.0)`, `width = 140 px`, `height = 24 px` |

Model **values** (slider values, checkbox state, callback behaviour) are
the agent's free choice; widget types, ranges, the swatch color/size and
the window title are not.

## Non-goals

- Interactive editing, scene manipulators, or the `omni.ui.scene` 3D
  viewport.
- Any GPU/CUDA path: the demo must prove CPU-only works (the agent sandbox
  has no `libcuda.so.1`; the judge installs the stub documented in
  `judge/setup.sh` so ovui's Vulkan/lavapipe path is used).
- Fonts/DPI variants, multiple panel designs, animations: one settled
  frame is the artifact.
- ovui features beyond the widget types above.

## Artifact

One Python file, `panel.py`, importable without side effects, that defines

```python
def build_panel() -> "omni.ui.Window":
    ...
```

building exactly the spec panel and returning the window. It may import
only `omni.ui`, `math`/`json`/`numpy` (already required by the judge) and
other Python-stdlib modules. The judge harness (`judge/render.py`) imports
the artifact in a headless ovui process, calls `build_panel()`, settles 9
frames, walks the returned window's widget tree itself, and screenshots.
Known-good: `examples/good/panel.py`.

## Gates (numeric pass rules)

`judge/grade.sh <panel.py> [--json out.json]` runs all gates in a scratch
copy and exits 0 only if every gate passes.

- **Gate 0 — runs and renders.** The harness imports the artifact, calls
  `build_panel()` without an exception, settles 9 frames, and writes a PNG
  screenshot — all within a 90 s wall limit; judge harness exit 0.
- **Gate 1 — widget tree.** The tree walk of the returned window finds
  exactly: one `ui.Window` with title `Tool Panel` and `width=420`,
  `height=360`; one `ui.VStack` ancestor of every widget below; three
  `ui.FloatSlider` whose `(min, max)` equal `(0,10)`, `(0,20)`, `(0,50)`
  in exactly these pairs (order free); one `ui.CheckBox`; one `ui.Button`
  with text `Apply`; and one `ui.ColorWidget` with `width=140`,
  `height=24` whose model's first three components equal
  `(0.2, 0.5, 0.9)` within 1e-6.
- **Gate 2 — pixel spec mask.** In the cropped window-content screenshot
  (the judge crops to the window's own screen rect):
  - every required widget's reported screen rect lies inside the window
    content region (no layout overflow);
  - the swatch rect (screen rect inset 3 px) median RGB is within `|Δ|
    <= 16` per channel of the sRGB render of `(0.2, 0.5, 0.9)`, where the
    target is the known-good example's own rendered median (fixed in
    `judge/reference.json`) plus that example's render jitter across 3
    runs, floored at 16 per channel;
  - each slider, the checkbox, the button and the title-bar text region
    is *drawn*: pixel luminance variance in its screen rect (inset 2 px)
    exceeds the variance of an identically sized region of plain window
    background by >= 8 (on the 0..255 scale);
  - the button's text `Apply` renders: the button rect contains >= 25
    pixels whose luminance differs from the button's background luminance
    by >= 30.
- **Gate 3 — determinism / independence.** The judge renders the artifact
  a second time in a fresh process with the same seed; the two cropped
  screenshots must be byte-identical. A baked-in PNG cannot pass Gate 1
  (no widget tree); drift between renders fails this gate.

## Acceptance oracle

Nothing passes because "the script ran":

- Gate 1 compares the artifact's own live widget tree (built by the
  judge's harness, not by the artifact's `__main__`) against the fixed
  spec table — widget types, slider ranges, swatch size and color.
- Gate 2 compares rendered pixels in explicit spec regions against the
  spec mask; the swatch target is anchored to the known-good render with a
  fixed per-channel tolerance derived from measured render jitter
  (`judge/reference.json`, see RECEIPT), an independent reference rather
  than the artifact's own claims.
- Gate 3 requires a fresh process to reproduce the render bit-for-bit, so
  any nondeterministic or environment-spoofing path fails.

## Determinism

The Vulkan/lavapipe render is deterministic for a fixed ovui version,
fixed window geometry and a fixed settled frame count (the harness settles
9 frames). `judge/grade.sh` run twice with the same `--seed` produces
byte-identical verdict JSON except the `timing` key; `judge/selftest.sh`
checks this.
