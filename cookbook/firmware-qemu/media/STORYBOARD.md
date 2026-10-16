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
  run, made by `media/record.py` under
  `asciinema rec --cols 120 --rows 50`. `media/term.py play` replays each
  through pyte + Pillow at 30 fps and ffmpeg encodes; it never composes
  them.
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
* **Frame 0 insurance:** `media/clips.py` also writes a poster PNG — the
  real first frame of each clip — and the composition mounts it behind
  the `<video>`, so the video's very first frame is real footage even if
  the browser has not painted a decoded frame yet.

The measured start times below come from replaying each cast through pyte
frame by frame (`media/term.py play` uses the same emulator), so the
content each slot names is on screen for the whole slot. Landmarks in
this run's casts: banner 0.38 s, HELP 5.20 s, first CRC 10.81 s, ring
pushes 19.2–30.0 s, seeded CRC burst 30.9–69.1 s (boot.cast); six object
compiles 0.43–0.96 s, memory map 0.99 s (build.cast); gate table 7.54 s,
verdict JSON 7.57 s (grade.cast); MUTANT header 132.5 s, build-broken
140.4 s, crc-poly 184.2 s, ring-count-drift 235.1 s (selftest.cast).

## Slots

| # | time | footage | overlay motion | numbers |
| --- | --- | --- | --- | --- |
| 1 | 0.00–2.00 | `boot.cast` 30.90–46.90 s at **8x**: the seeded CRC burst at full width — long hex commands and `OK 0x…` answers landing over the session's history | kinetic headline `A QEMU shell that / answers like hardware`, on screen from frame 0, rising and clearing | — |
| 2 | 2.00–7.00 | `boot.cast` 4.00–44.00 s at **8x**: HELP → VER → ID → PING → ECHO → error cases → the whole seeded CRC set | HUD `SHELL RESPONSES` counting 0 → **46**, `CRC == zlib` 0 → **15** | 46/46, 15/15 |
| 3 | 7.00–10.00 | `build.cast` 0.00–3.00 s at 1x: the real toolchain compiling six objects, then the linker map | `FLASH` / `SRAM` bars filling to **2744 B** / **4456 B** | 2744 B, 4456 B |
| 4 | 10.00–15.00 | `grade.cast` 7.40–12.00 s at 1x: the judge's 8-row gate table landing, then its verdict JSON | eight gate rows sliding in over the scrolling verdict, each lighting; PASS badge scales in | 8/8 |
| 5 | 15.00–21.00 | `selftest.cast` 132–192 s at **12x**: the mutant table building, 6+ rows | `MUTANTS KILLED` counting 0 → **14**; a **PASS** badge with `100 % kill rate` snaps in; a `12× speed` tag | 14/14, 100 % |
| 6 | 21.00–27.00 | `boot.cast` 24.00–120.00 s at **16x**: ring-buffer push/pop wrap, then the CRC burst, fast | `16× SPEED` tag; `CRC-32 vs zlib` counter 0 → **15**; camera pushes across the terminal | 15/15 |
| 7 | 27.00–31.50 | `grade.cast` 7.40–11.90 s at 1x: the verdict JSON on screen, real bytes | HUD pinned over the moving footage; numbers held | 8/8, 46/46, 15/15, 2224 B |
| 8 | 31.50–34.00 | static end card | none (by design — the gate measures its 2 s near-still window) | `python3 cookbook/firmware-qemu/run.py` |

34 s total: inside the gate's 25–60 s band, with 2.5 s of end card
covering its 2.0 s end window, and 8 cuts in 31.5 s (~2.5 per 10 s,
well above the 0.8 floor).

## Rules this cut follows

* No text-only frame, no figure shown as a still, no Ken-Burns: every
  pre-end-card frame is a frame of a real recording, played back or panned.
  `term.py play` rasterises real pyte screen state; the composition moves a
  camera over it, never a synthetic zoom on a still.
* Cuts: 8 in 31.5 s ≈ 2.5 / 10 s (floor 0.8). The hook (slot 1) is a
  different width of text than slots 2/6 and a different screen than the
  build/verdict shots, so cuts register on the gate's scene metric.
* Motion: the gate is 0.20, our own bar is 0.50. Every slot replays a
  cast whose lines land continuously (a line every 0.25–0.5 s of clip
  time), *and* the overlays animate, so no frame is still. The first
  draft measured 0.59.
* Camera moves are the composition's transform over `<video>` elements
  holding the real recording — never a transform over an image. Zooms
  stay small over terminal text: a big zoom re-renders the glyph grid
  every frame and the re-encode alone ate most of an 8 MiB budget.
* Captions sit at ≥ 4 % of frame height (96 px on 1080 = 8.9 %; HUD values
  96 px, HUD keys 28 px, gate rows 30 px, headline 96 px).
* Renderer: **HyperFrames `0.8.99`** (published 2026-09-30, > 14 days
  before 2026-10-15), pinned exactly in
  `media/video/package.json` + `package-lock.json`. GSAP is vendored
  locally so the render never needs network. ffmpeg only encodes the
  clips, the posters and the final file; all visuals are the recorded
  terminal or the HTML composition.

## Status

`media/make_media.sh` regenerates the casts (footage), then the clips,
then the composition, then the encode — end to end. Every claim here is
checked by `cookbook/tools/video_gate.py`.
