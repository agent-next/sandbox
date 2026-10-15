# RECEIPT — ovui-native-ui

Real command output from **two fresh sandbox runs** (no tools preinstalled;
`judge/setup.sh` installed everything from nothing) in a disposable Debian
12 sandbox, 2 vCPU / ~4 GB RAM, no GPU, no display. Both runs used the same
image and the same commit; `TOOLS_DIR` was pointed at a fresh directory each
time so nothing was reused.

Host: Debian 12 (bookworm), Python 3.12.15, `gcc 12.2.0`, `binutils 2.40`.

## Tool versions (`judge/VERSIONS.txt`, written by `setup.sh`)

```
== apt ==
gcc 4:12.2.0-3
libc6-dev:amd64 2.36-9+deb12u14
libgl1:amd64 1.6.0-1
libvulkan1:amd64 1.3.239.0-1
mesa-vulkan-drivers:amd64 22.3.6-1+deb12u2
== compiler ==
cc (Debian 12.2.0-14+deb12u1) 12.2.0
== pip ==
numpy==2.5.4
ovui==0.3.0
pillow==12.3.0
pip==25.0.1
== vulkan device ==
	deviceType         = PHYSICAL_DEVICE_TYPE_CPU
	deviceName         = llvmpipe (LLVM 15.0.6, 256 bits)
	driverName         = llvmpipe
== cuda stub symbols ==
42
d4faa0f83494acac9638aa5a339fd3dff887aa631e789d4058c98c179aa4f904  .../cuda-stub/libcuda.so.1
0f5b56c7d7516c20cd40e568be2bf872153d796b995bd79f0738d9a53c235136  .../cuda-stub/libcudart.so.12
```

The two stub sha256s are identical in both runs: the stubs are a
deterministic function of the pinned ovui wheel (generated from its exact
undefined-symbol list), so a rebuild on the same wheel is bit-identical.

## `bash judge/setup.sh`

Run 1, from an empty `TOOLS_DIR` (apt lists already fetched; the wheels and
stubs were built from scratch):

```
$ bash judge/setup.sh
[notice] To update, run: python3 -m pip install --upgrade pip
/tmp/rcpt1/wheels.dl/ovui-0.3.0-cp312-cp312-manylinux_2_35_x86_64.whl: OK
/tmp/rcpt1/wheels.dl/pillow-12.3.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl: OK
/tmp/rcpt1/wheels.dl/numpy-2.5.4-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl: OK
generated stubs: 34 cudart + 8 driver symbols
omni.ui import OK
setup OK: /tmp/rcpt1
exit code: 0

real	1m5.185s
```

Run 2, same, empty `TOOLS_DIR`:

```
$ bash judge/setup.sh
...
generated stubs: 34 cudart + 8 driver symbols
omni.ui import OK
setup OK: /tmp/rcpt2
exit code: 0

real	1m32.142s
```

Warm re-run (idempotent, nothing to install): **7.7 s**, `exit 0`.

This image ships **empty apt lists** (`ls /var/lib/apt/lists/*Packages*` is
empty). `setup.sh` checks that before installing, and runs
`apt-get update` itself, verifying the lists actually landed. Tested by
clearing the lists and purging `mesa-vulkan-drivers`, then running
`setup.sh` from scratch: it fetched the lists, reinstalled the package
(`Status: install ok installed`), rebuilt the wheels and stubs, and
`judge/grade.sh examples/good/panel.py` then passed all four gates
(`exit 0`). So the cold-sandbox path works with no manual `apt-get update`.

The three `OK` lines are `sha256sum -c` verifying the pinned wheel hashes;
the three `...: FAILED` case (a corrupted or substituted wheel) aborts
`setup.sh` with `set -e`.

## `bash judge/selftest.sh`

```
$ bash judge/selftest.sh
wrote 11 mutants to /tmp/tmp.6vKpoRBLZJ: missing_slider wrong_range wrong_swatch_color swatch_overflow empty_window wrong_button_text wrong_swatch_size missing_checkbox missing_swatch baked_png nondeterministic
good: PASS (verdict byte-identical across 2 runs)
mutant baked_png: FAILS (widget_tree,pixels)
mutant empty_window: FAILS (render 1 failed)
mutant missing_checkbox: FAILS (render 1 failed)
mutant missing_slider: FAILS (widget_tree)
mutant missing_swatch: FAILS (widget_tree,pixels)
mutant nondeterministic: FAILS (determinism)
mutant swatch_overflow: FAILS (widget_tree,pixels)
mutant wrong_button_text: FAILS (widget_tree)
mutant wrong_range: FAILS (widget_tree)
mutant wrong_swatch_color: FAILS (widget_tree,pixels)
mutant wrong_swatch_size: FAILS (widget_tree,pixels)
kill rate: 11/11 = 100%
self-test OK
exit code: 0

real	1m3.230s
```

Run 1 wall time **2m3s**, run 2 **1m46s**; the block above is a third run
from a fresh clone of the pushed commit (13 graded runs, 26 renders at ~4.5 s each, plus the two
graded known-good runs). All runs: `kill rate: 11/11 = 100%`, `exit 0`.

The two runs that produced this receipt predate a reporting fix in the
self-test (see Deviations item 3): `empty_window` and `missing_checkbox`
throw while the panel is being built (`IndexError`, `TypeError`), so
`grade.sh` never reached the gates and — before the fix — wrote no `--json`
verdict, leaving the previous mutant's verdict on disk. The self-test then
misattributed those two kills to `widget_tree,pixels`. The fix has two
parts: `grade.sh` now always writes an error verdict
(`{"pass": false, "error": "render 1 failed", "log": …}`) to `--json` when a
render dies, and `selftest.sh` removes the verdict file before grading each
mutant. The block above is the corrected output. The kill rate is unchanged
— 11/11 — because both mutants were already killed; only the reported
reason was wrong.

Nine of the eleven mutants fail a **gate assertion**: `missing_slider`
renders fine (its third row is a `Label` instead of a `FloatSlider`) and is
caught by `widget_tree` with `sliders_ok: false`; `nondeterministic` passes
gates 0–2 and is caught only by `determinism`. The two build-crashers
(`empty_window`, `missing_checkbox`) are killed by the render step itself.
The self-test also checks that two graded runs of the known-good give
byte-identical verdicts excluding the `timing` key.

## `bash judge/grade.sh examples/good/panel.py --json /tmp/v.json`

```
$ bash judge/grade.sh examples/good/panel.py --json /tmp/v.json
{
  "gates": [
    { "gate": "rendered_png", "ok": true, "size": [1280, 720] },
    { "gate": "widget_tree", "ok": true,
      "detail": { "button_ok": true, "checkbox_ok": true, "ref_names_ok": true,
                  "sliders_distinct": true, "sliders_ok": true,
                  "swatch_color_ok": true, "swatch_size_ok": true,
                  "swatch_type_ok": true, "window_ok": true } },
    { "gate": "pixels", "ok": true,
      "detail": { "bbox_mismatch": [], "bg_lum": 69.0, "button_face_lum": 41.0,
                  "button_text_px": 127, "overflow": [], "rects_missing": [],
                  "swatch_median": [51.0, 128.0, 230.0],
                  "swatch_std": [0.0, 0.0, 0.0],
                  "swatch_target": [51.0, 128.0, 230.0],
                  "title_px": 328, "undrawn": [] } },
    { "gate": "determinism", "ok": true, "sha256": "0d8e03dcb161d859" }
  ],
  "pass": true,
  "seed": 1234,
  "timing": { "render_wall_s": 5 }
}
exit code: 0
```

(Shown compacted; the command prints the same JSON with one field per line.
The block is from a fresh clone of the pushed commit — a third run, after
the first two — and reproduces the first two exactly.)

Run 1: **12.0 s** wall, `exit 0`. Run 2: **10.2 s**, `exit 0`.

Key numbers, both runs side by side (identical):

| quantity | run 1 | run 2 |
|---|---|---|
| `pass` | true | true |
| gates ok | 4/4 | 4/4 |
| `swatch_median` | `[51.0, 128.0, 230.0]` | `[51.0, 128.0, 230.0]` |
| `swatch_std` | `[0.0, 0.0, 0.0]` | `[0.0, 0.0, 0.0]` |
| `swatch_target` (analytic) | `[51.0, 128.0, 230.0]` | `[51.0, 128.0, 230.0]` |
| `bg_lum` | 69.0 | 69.0 |
| `button_face_lum` | 41.0 | 41.0 |
| `button_text_px` | 127 | 127 |
| `title_px` | 328 | 328 |
| `overflow`, `bbox_mismatch` | `[]`, `[]` | `[]`, `[]` |
| render sha256 (first 16) | `0d8e03dcb161d859` | `0d8e03dcb161d859` |
| `timing.render_wall_s` | 7 | 8 |

The only number that differs between runs is the wall time. The render
sha256 is identical, so the two renders are byte-identical — that is Gate 3.

`--seed` is accepted and recorded (`"seed": 1234`) but the render takes no
random input, so it is seed-independent: grading with `--seed 1234` and
`--seed 999` gives byte-identical gates. `--seed` exists to match the
standard's `grade.sh` interface.

## Independent-oracle evidence

The swatch target is **analytic** (`round(255 * c)` for the spec colour
`(0.2, 0.5, 0.9)` → `[51, 128, 230]`), and the measured median equals it
exactly, with per-channel std `0.0` across the swatch interior. The oracle
is not "whatever the good example drew": a wrong-colour mutant measures
`[230.0, 51.0, 26.0]` — the correct channels, swapped — and fails both the
widget-tree and the pixel gate.

Mutant pixel evidence (grade.sh verdicts, run 2 tools):

```
wrong_range          pass=False  failed=widget_tree
wrong_swatch_color   pass=False  failed=widget_tree,pixels  swatch_med=[230.0, 51.0, 26.0]
swatch_overflow      pass=False  failed=widget_tree,pixels  overflow=['swatch']
empty_window         error="render 1 failed" (IndexError at build)
nondeterministic     pass=False  failed=determinism
```

`swatch_overflow` is caught by the real rect geometry (`overflow: ['swatch']`,
`bbox_mismatch: ['swatch']`), not by a size check alone. `nondeterministic`
passes gates 0–2 with a pixel-perfect panel and is caught only by the
byte-identical-render gate — so Gate 3 is load-bearing, not decorative.

## Judge immutability

`grade.sh` checksums the whole `judge/` tree before and after each run. An
artifact that appends to `judge/check_gates.py` from inside the render
process is caught:

```
$ bash judge/grade.sh /tmp/evil/panel2.py --json /tmp/ve.json
{"pass": false, "error": "judge/ changed during grade"}
grade.sh exit=1
```

## Deviations

1. **`ovui 0.3.0` is newer than the standard's two-week freshness rule.**
   `setup.sh` pins releases published at least two weeks before the demo.
   ovui 0.3.0 was published 2026-10-13, i.e. ~2 days before this run. It is
   required: ovui 0.1.0, 0.1.1 and 0.2.0 request
   `VK_KHR_external_semaphore_fd` unconditionally and abort at
   `VulkanBackend: vkCreateDevice failed (-7)` on Mesa lavapipe, which does
   not advertise that extension; 0.3.0 detects the missing extension and
   logs `device does not support VK_KHR_external_semaphore_fd, CUDA interop
   disabled` before rendering. Verified by extracting
   `libomniui_standalone.so.3` from each release: the fallback string is
   present only in 0.3.0. Pinning an older ovui would make the demo not run
   at all on a CPU-only host, so the freshness rule was traded for a demo
   that works. The pin is exact (`ovui==0.3.0`, sha256-checked), and
   `judge/requirements.txt` carries the hash.
2. **`run.py` was not run against a real sandbox by the builder.** Sandboxes
   cannot be created from inside a sandbox, so `run.py` was verified with
   `python3 -m py_compile`, by running the exact in-sandbox command sequence
   it sends (`git clone --depth 1 -b <ref> ...` then `judge/setup.sh`,
   `judge/selftest.sh`, `judge/grade.sh examples/good/panel.py`) against a
   fresh clone in this sandbox, and by parsing its real `grade.sh` output
   with `run.py`'s own verdict-extraction code. The lead runs it end to end.
3. **`media/` added by a later task.** `media/make_media.sh` regenerates
   `media/result.png`, `media/loop.png`, `media/demo.mp4` and
   `media/MANIFEST.json` from real judge outputs; its runs are recorded in
   the "Media build" section below. Building the media surfaced the
   self-test misattribution described above, fixed in the same commit.
4. **`REPRODUCE.md` is not yet present.** The standard requires an
   independent agent (different model family) to reproduce the numbers from
   `README.md` alone before merge; that is a separate step, and this receipt
   records only the builder's two runs.
5. **The CUDA stubs are hand-written C, not a third-party download.** They
   contain no CUDA code: each stub is one trivial function per undefined
   symbol in the pinned ovui wheel, returning "no CUDA device". They are
   generated and compiled by `setup.sh` from the installed wheel, so there
   is no version to pin beyond the wheel itself. Nothing on the lavapipe
   path calls them — they exist only to satisfy the dynamic linker.
6. **`ovui` was not built from source.** The demo uses the prebuilt
   manylinux wheel from PyPI (census: installs in ~6 s), not a source build,
   so no `git` SHA is pinned; the wheel sha256 is.
