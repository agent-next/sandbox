# STORYBOARD — nanousd-render demo.mp4

Written before the video is cut (DEMO-STANDARD "Media"); `make_media.sh`
cuts against this table and the review panel judges the video against it.
Master 1920×1080 @ 30 fps, total 32.0 s (960 frames). Hard cuts only — no
crossfades, no dissolves. Burned-in captions: DejaVu Sans Bold 72 px,
word-wrapped to at most two lines inside a 1560 px column (cap height
≈ 53 px ≈ 4.9 % of frame height, above the 4 % floor), so no caption is ever
clipped at a frame edge. Every frame is real output of the pinned run:
renders come from the pinned `render_once` on llvmpipe (the same binary and
the same GL path the judge's G3 uses), terminal text from the real
setup/selftest logs `make_media.sh` writes itself, verdict numbers from the
real grade JSON. The only static frames are the end card.

| slot | time (s) | what fills the frame | source data / command | caption text |
|---|---|---|---|---|
| 1 hook | 0.0–2.0 | The finished graded result fills the frame: the artifact's own camera view of the exact graded scene, re-rendered at 1440×1080 through the pinned `render_once` on llvmpipe and pillarboxed on the render's own background colour. Slow push-in 1.00→1.03 over the 2 s. The first frame is the coloured render — no title card, no logo, no terminal. | `render_once` per frame, eye/forward/up and vFOV derived from the artifact camera's world basis and its authored `focalLength`/`verticalAperture`; scene = `examples/good/scene.usda` | "Five meshes. Two USD implementations. One CPU render." |
| 2 input → output | 2.0–8.6 | The artifact beside the result it produced: the real `def Mesh "Cube"` block of `examples/good/scene.usda` verbatim in a dark source panel on the left third, the graded render on the rest, with the judge's projected rectangles sliding in over the render across the slot. | `examples/good/scene.usda` (source text); `media/build/verdict.json` (G4 rects, per-mesh k) | "The artifact is one self-contained USDA file — the judge re-derives everything else" |
| 3 escalate (orbit) | 8.6–12.4 | A real per-frame camera orbit around the exact graded scene at 1920×1080 on llvmpipe — every frame a fresh `render_once` call, not a panned still. | `render_once` per frame; radius/height/FOV from the artifact camera, fov from the authored intrinsics | "The pinned renderer: Mesa llvmpipe, EGL pbuffer — no GPU, no X" |
| 4 escalate (rects) | 12.4–16.4 | The same orbit continues under a hard cut, now with the G4 oracle rectangles and the per-mesh fitted illuminance `k` burned on the real frames (the rectangles re-projected per orbit frame with the judge's own pinhole math). | rectangles from `media/build/verdict.json` G4 rects and `k`, re-projected per frame by the numpy oracle in `media/build_video.py` | "Where the numpy pinhole oracle says every mesh must land (k = fitted illuminance)" |
| 5 escalate (Nx speed) | 16.4–23.0 | Real terminal, cropped and zoomed to the active region: the `[setup]` progress lines of the setup run this media was built from, scrolling, then the live selftest tail. The "Nx speed" badge sits top-right on its own strip, clear of both the log text and the caption scrim, and states the real compression (measured setup wall time ÷ this slot's duration). | `media/build/setup_run.log` (written by `make_media.sh` around a real `judge/setup.sh` run) → `media/setup_progress.txt`; `media/build/selftest.json` | "The pinned toolchain, built from sha256-checked source in a disposable sandbox" |
| 6 proof | 23.0–29.0 | The judge verdict (pass, G1–G4, `rendered_frac`, `judge_integrity_ok`, per-mesh k and dev) on the left and the mutant kill matrix on the right, both as a HUD over the still-moving real orbit render (a 10° drift, darkened for legibility) — never a text slide. | `media/build/verdict.json`; `media/build/selftest.json` | "13/13 mutants killed by a named judge gate" |
| 7 end card | 29.0–32.0 | Static end card on a dark background: the one-command run centred, with a smaller one-line summary beneath. | — | "python3 cookbook/nanousd-render/run.py" + smaller: "one command → sandbox → pinned build → judge → kill" |

Cut list (hard cuts): 2.0, 8.6, 12.4, 16.4, 23.0, 29.0 — six cuts in 32.0 s
= 1.88 cuts / 10 s (gate needs ≥ 0.8). The first frame is the colour render
(not dark, not a solid colour). The last 3.0 s are a static end card, so the
final 2 s window is static (gate end-card check). Every shot before the end
card is real per-frame renderer output moving under it; nothing is a Ken-Burns
pan over a still.

Guard: `media/build_video.py` re-checks the judge's own G3 emptiness floor
(≥ 1 % of pixels differing from the background) on every rendered frame it
uses, and the media build FAILS if a camera puts the scene outside the
frustum — so a regression that culls the geometry cannot ship as a black
video.

Numbers that appear on screen trace to: `verdict.json` (gates,
`rendered_frac`, per-mesh k/own_dev), `selftest.json` (mutants, kill rate),
and the setup run `make_media.sh` logs and times itself (the N× badge).