# demo.mp4 storyboard — firmware-qemu

The owner rejected the previous cut as "the ppt video": it was matplotlib
scenes and still figures with a fade between them. **This cut has no
slides.** Every second before the end card is real moving output of this
demo — the firmware booting in QEMU, the Arm toolchain compiling it, the
judge grading it, the judge killing 14 mutants — played back as terminal
footage through a pyte emulator, composed in HyperFrames, with animated
overlays whose numbers come from the same run the footage came from.

## Source of truth

* **Footage:** `media/clips/*.cast` — asciicast v2 recordings of a real
  run, made by `media/record.py` under `asciinema rec` at 120×50 cells.
  `media/term.py play` replays each through pyte + Pillow at 30 fps and
  ffmpeg encodes; it never composes them.
  * `boot.cast` — one real QEMU `lm3s6965evb` session: launch line, boot
    banner, the 46-command scripted shell, and the 15 seeded CRC buffers.
  * `build.cast` — real `make clean build/firmware.elf` with the pinned
    Arm GNU toolchain, ending in its memory map.
  * `grade.cast` — real `judge/grade.sh examples/good --seed 20260814`.
  * `selftest.cast` — real `judge/selftest.sh`: 14 mutants, one per line.
* **Numbers:** the casts themselves, plus `media/data/verdict-good.json`
  (8/8 gates, 46/46 shell, 15/15 CRC, `.text+.rodata` 2224 B),
  `media/data/selftest.log` (14/14 killed, 100 % behavioural) and the
  build's memory map in `build.cast` (FLASH 2744 B of 256 KB, SRAM 4456 B
  of 64 KB). `media/video/index.html` reads them from a JSON
  `--variables-file`; no number is typed into the composition by hand.

The measured start times below come from replaying each cast through
pyte frame by frame (`media/term.py play` uses the same emulator), so the
content each slot names is on screen for the whole slot.

## Slots

| # | time | footage | overlay motion | numbers |
| --- | --- | --- | --- | --- |
| 1 | 0.00–2.00 | `boot.cast` 0.45–2.45 s at **8x**: the QEMU launch line and the boot banner landing | kinetic headline `A QEMU shell that / answers like hardware`, rising through and clearing | — |
| 2 | 2.00–7.00 | `boot.cast` 4.20–9.20 s at **8x**: the scripted shell — HELP, VER, ID, PING, ECHO | HUD `SHELL RESPONSES` counting 0 → **46**, `CRC == zlib` 0 → **15** | 46/46, 15/15 |
| 3 | 7.00–10.00 | `build.cast` 0.10–2.90 s at 1x: the real toolchain compiling six objects, then the linker map | `FLASH` / `SRAM` bars filling to **2744 B** / **4456 B** | 2744 B, 4456 B |
| 4 | 10.00–15.00 | `grade.cast` 7.90–12.50 s at 1x: the judge's verdict line and its JSON | eight gate rows sliding in over the scrolling verdict, each lighting; PASS badge scales in | 8/8 |
| 5 | 15.00–21.00 | `selftest.cast` 268–328 s at **12x**: the mutant table building, 14 lines | `MUTANTS KILLED` counting 0 → **14**; a **PASS** badge with `100 % kill rate` snaps in | 14/14, 100 % |
| 6 | 21.00–27.00 | `boot.cast` 24.00–40.00 s at **16x**: the ring-buffer push/pop tail, fast | `16x SPEED` tag; camera pushes across the terminal | 16x |
| 7 | 27.00–31.50 | `grade.cast` 7.90–12.40 s at 1x: the verdict JSON still scrolling | HUD pinned over the moving footage; numbers held | 8/8, 2224 B |
| 8 | 31.50–34.00 | static end card | none (by design — the gate measures its 2 s near-still window) | `python3 cookbook/firmware-qemu/run.py` |

34 s total: inside the gate's 25–60 s band, with 2.5 s of end card
covering its 2.0 s end window, and 8 cuts in 31.5 s (~2.5 per 10 s,
well above the 0.8 floor).

## Rules this cut follows

* No text-only frame, no figure shown as a still, no Ken-Burns: every
  pre-end-card frame is a frame of a real recording, played back or panned.
  `term.py play` rasterises real pyte screen state; the composition moves a
  camera over it, never a synthetic zoom on a still.
* Cuts: 8 in 31.5 s ≈ 2.5 / 10 s (floor 0.8).
* Motion: the gate is 0.20, our own bar is 0.50. Slots 4, 5 and 7 pan the
  footage (the camera is a moving window over a live recording) *and*
  animate the overlay, so no frame is still.
* Camera moves are the composition's transform over `<video>` elements
  holding the real recording — never a transform over an image.
* Captions sit at ≥ 4 % of frame height (96 px on 1080 = 8.9 %; HUD values
  96 px, HUD keys 24 px, gate rows 30 px, headline 96 px).
* Renderer: **HyperFrames `0.8.99`** (published 2026-09-30, > 14 days
  before 2026-10-15), pinned exactly in
  `media/video/package.json` + `package-lock.json`. GSAP is vendored
  locally so the render never needs network. ffmpeg only encodes the
  clips and the final file; all visuals are the HTML composition.

## Status

`media/make_media.sh` regenerates the casts (footage), then the clips,
then the composition, then the encode — end to end. Every claim here is
checked by `cookbook/tools/video_gate.py`.
