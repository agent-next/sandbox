# ovui native tool panel (headless, CPU-only)

An agent builds a small **native 3D-tool UI panel** with
[NVIDIA Omniverse `ovui`](https://github.com/NVIDIA-Omniverse/ovui) inside a
disposable agent-next sandbox, and a judge that checks both the rendered
pixels and the live widget objects decides whether the panel matches a fixed
spec. The panel is a real ovui/ImGui/Vulkan render, drawn **offscreen on a
CPU** — no GPU, no display, no NVIDIA account.

A sandbox helps here because ovui's runtime is awkward to host: it needs a
Vulkan stack, a display-less render target, and its own window state, and a
mis-set environment produces a plausible-looking failure rather than an
error. Inside a throwaway sandbox the agent can install the pinned stack,
render, read the judge's verdict, and iterate without touching anyone's
machine.

## Ask your agent

Paste this into a plugin user's agent session (the agent works inside a
sandbox):

> Build me a native 3D-tool UI panel with NVIDIA Omniverse `ovui` (the pip
> package) that renders headless on a CPU-only machine. Work in a clone of
> the `agent-next/sandbox` repo, under `cookbook/ovui-native-ui/`; read
> `cookbook/DEMO-STANDARD.md` and `cookbook/ovui-native-ui/SPEC.md` first.
> The panel must be a 420x360 `ui.Window` titled "Tool Panel" holding three
> labelled `FloatSlider` rows (ranges 0..10, 0..20, 0..50), a 140x24
> `ColorWidget` swatch of colour rgba(0.2, 0.5, 0.9, 1.0), a `CheckBox`, and
> an "Apply" `Button` — exactly the widget tree SPEC.md fixes. Run
> `bash judge/setup.sh` once, then iterate: write `panel.py` with
> `build_panel() -> (window, refs)`, and run
> `bash judge/grade.sh panel.py --json /tmp/v.json` until every gate passes.
> Do not edit anything under `judge/` — the judge checksums itself and fails
> if it changed. Show me the final verdict JSON and the rendered PNG.

The agent installs the pinned tools itself; `judge/setup.sh` is idempotent.

## One-command run

Needs the `sbx` CLI and `SBX_API_KEY` (or `E2B_API_KEY`):

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY="<your key>"
python3 cookbook/ovui-native-ui/run.py            # --ref main (default), --keep, --timeout-min N
```

`run.py` creates a sandbox, clones the repo at `--ref`, runs
`judge/setup.sh`, `judge/selftest.sh` and
`judge/grade.sh examples/good/panel.py`, prints the verdict JSON and a short
summary, and always kills the sandbox afterwards (confirming with `sbx list`
that the id is gone; it exits non-zero if it cannot).

## What the judge does

`judge/grade.sh <panel.py>` renders the artifact twice in fresh processes
through its own harness (`judge/render.py` — the artifact only builds
widgets, it never owns the frame loop or the screenshot) and checks four
gates; it exits 0 only if all pass. The harness binds the screenshot path,
the frame tick and the widget classes to locals **before** it imports the
artifact, looks the spec window up itself
(`ui.Workspace.get_window("Tool Panel")`), and requires every returned ref
to be a live widget in that window's tree — so an artifact that returns
plain objects named after the widget classes with attributes copied from a
real run, and swaps `omni.ui.testing.capture_screenshot` for a function
that writes baked PNG bytes, still fails: the screenshot it is graded on
is the real framebuffer, which drew no panel.

- **Gate 0 — runs and renders:** a valid PNG at least 420x360, inside a 90 s limit.
- **Gate 1 — widget objects:** from the `refs` the artifact returned — each
  one an instance of the pre-bound `ui` class and a live child of the
  window the judge looked up itself (walked with `Inspector.get_children`);
  window title and size, three distinct `FloatSlider` with the exact
  ranges, a `CheckBox`, a `Button` labelled `Apply`, and a `ColorWidget`
  whose size and colour model match the spec.
- **Gate 2 — pixel spec mask:** no widget overflows the window content
  region; each widget's bbox matches the reference within 8 px (position) /
  4 px (size); the swatch's median RGB matches the analytic sRGB target
  `[51, 128, 230]` within 12 per channel and is uniform; every widget is
  actually drawn (interior differs from the window background); the title
  text and the `Apply` text are rendered.
- **Gate 3 — determinism:** the two renders are byte-identical, screenshot
  and widget facts alike.

`judge/selftest.sh` proves the judge can fail: the known-good passes, and
11 known-bad mutants (missing slider, wrong range, wrong swatch colour,
layout overflow, an invisible-panel window, wrong button text, wrong
swatch size, missing checkbox/swatch, a baked-PNG artifact that fakes the
widget objects and swaps the screenshot function, and a nondeterministic
render) each fail a judge gate assertion. The kill rate counts only
mutants a gate failed — a mutant that merely crashes the build proves
nothing about the judge — and is 11/11 = 100%.

## Measured wall time

From the receipt (2 vCPU, ~4 GB RAM, no GPU; Debian 12, Python 3.12):

| step | wall time |
|---|---|
| `judge/setup.sh` (cold: apt + pinned wheels + stubs) | 44–92 s |
| `judge/setup.sh` (warm, idempotent) | 8 s |
| `judge/selftest.sh` (13 graded runs, 26 renders) | 44–123 s |
| `judge/grade.sh examples/good/panel.py` (2 renders + gates) | 3–12 s |
| one render (`judge/render.py`) | ~2–4.5 s |
| `media/make_media.sh` (13 graded runs + 2 encodes) | ~13 min |

The render itself is CPU rasterisation of a 1280x720 offscreen Vulkan target
on Mesa lavapipe; a 420x360 panel is ~4 s, and the selftest's 26 renders
dominate its wall time.

## How the CPU-only path works

`omni.ui`'s shared objects declare `DT_NEEDED` on `libcuda.so.1` and
`libcudart.so.12`, so on a host with no CUDA a bare `import omni.ui` fails:

```
ImportError: libcuda.so.1: cannot open shared object file: No such file or directory
```

`judge/setup.sh` generates two **stub** libraries from the exact
undefined-symbol list of the installed ovui shared objects, satisfying the
dynamic linker without a CUDA device. With `OMNIUI_LAVAPIPE=1`,
`OMNIUI_HEADLESS=1` and `OMNIUI_BACKEND=vulkan`, ovui selects the lavapipe
CPU device and disables CUDA interop itself:

```
VulkanBackend: selected device: "llvmpipe (LLVM 15.0.6, 256 bits)" (vendorID=0x10005, type=CPU (software renderer))
VulkanBackend: device does not support VK_KHR_external_semaphore_fd, CUDA interop disabled
VulkanBackend: initialized successfully (1280x720, offscreen)
```

This is the path ovui's own `ovui/HEADLESS.md` documents under "Running
without a GPU (Lavapipe / software ICD)".

**ovui 0.3.0 is required.** Earlier releases (0.1.0, 0.1.1, 0.2.0) request
`VK_KHR_external_semaphore_fd` unconditionally and die at
`VkResult = -7` (`VK_ERROR_EXTENSION_NOT_PRESENT`) on lavapipe, which does
not provide it; 0.3.0 falls back instead. See `RECEIPT.md` "Deviations".

## Limits, stated plainly

- The panel is one settled frame, not an interactive tool: no input handling,
  no scene viewport, no animation.
- CPU rasterisation is slow. The judge renders at ovui's default 1280x720
  offscreen size and grades a fixed window, so wall time scales with that
  surface, not with the panel.
- Gate 3 requires the render to be byte-reproducible. This holds for a fixed
  ovui version on lavapipe, but a different Mesa or ovui version could change
  rasterisation or layout, so `judge/reference.json`'s bboxes and swatch
  target are pinned to the versions in `judge/VERSIONS.txt`.
- No interactive media: `media/demo.mp4` is a walkthrough of judge outputs,
  not a recording of someone using the panel.

## Media

![The known-good render with the judge's measured bboxes and the swatch-gate
chart](media/result.png)

`media/` is regenerated from real judge outputs by `bash media/make_media.sh`
(no judge verdict, no media):

- `media/result.png` — the real 1280×720 render with the judge's measured
  widget bboxes and content region, the swatch-gate chart (measured median
  vs the judge's ±12 mask), and the PASS stamp with the real sha256.
- `media/loop.png` — the agent loop: a scripted replay of real judge verdicts
  (build error → pixel mismatch → nondeterminism → PASS) and the self-test
  kill table, one row per mutant with the gate(s) that failed it.
- `media/demo.mp4` — a 38.1 s, 1920×1080, 30 fps walkthrough of the same
  judge outputs (4.5 MB H.264, from a lossless `-crf 0` master); it opens on
  the finished render with the verdict stamped on it, and passes
  `cookbook/tools/video_gate.py` (cuts/10 s, motion, static end card).
- `media/REVIEW.json` — the two blind vision-model verdicts on that video
  (`cookbook/DEMO-STANDARD.md`, "Review panel"); no README, no repo context.
- `media/result.json` — the `agent-next/result@1` manifest: verdict, gate
  numbers, hero media and launch, validated by
  `cookbook/tools/result.py`.
- `media/MANIFEST.json` — what each file shows, the command that makes it,
  its source data, and its sha256.

`media/data/` holds the underlying real outputs (the good-grade verdict, the
selftest log, the per-mutant verdicts, the sha-verified render and its
widget facts); `media/master/` (the lossless `-crf 0` video master) is
git-ignored. The figures never draw a number the judge did not produce.

## Files

| path | what |
|---|---|
| `SPEC.md` | the panel spec, the gates and their numeric pass rules, the acceptance oracle |
| `judge/setup.sh` | pinned tools: apt packages, sha256-checked wheels, generated CUDA stubs |
| `judge/render.py` | the harness: builds the artifact, settles 9 frames, screenshots, dumps widget facts |
| `judge/check_gates.py` | the four gates |
| `judge/reference.json` | analytic swatch target + measured expected bboxes |
| `judge/grade.sh` | one verdict, exit 0 only if all gates pass |
| `judge/selftest.sh`, `judge/mutants.py` | known-good passes, 11 known-bad mutants all fail |
| `examples/good/panel.py` | the known-good artifact |
| `run.py` | the one-command run |
| `media/` | the figures, video and manifest, regenerated from real judge outputs |
| `RECEIPT.md` | real command output and tool versions |

## Licence and sources

`ovui` is Apache-2.0 (`github.com/NVIDIA-Omniverse/ovui`, pip `ovui`, pinned
to 0.3.0). The known-good panel is written for this demo, not copied from
upstream; its style follows ovui's own examples and the `omni.ui` API
documented in the wheel's bundled skill files. Pillow (MIT-CMU) and numpy
(BSD-3-Clause) are judge-only dependencies. Exact versions and sha256s are in
`judge/VERSIONS.txt` and `judge/requirements.txt`.
