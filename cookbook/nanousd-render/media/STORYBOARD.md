# STORYBOARD — nanousd-render demo.mp4

Written before the video is cut (DEMO-STANDARD "Media"); `make_media.sh`
cuts against this table and the review panel judges the video against it.
Master 1920×1080 @ 30 fps, target length ≈ 34 s. Hard cuts only — no
crossfades, no dissolves. Burned-in captions: DejaVu Sans Bold 72 px on
the 1080 p frame (cap height ≈ 53 px ≈ 4.9 % of frame height, above the
4 % floor). Every frame is real output of the pinned run: renders come
from the pinned `render_once` on llvmpipe, terminal text from the real
setup/selftest logs, verdict numbers from the real grade JSON.

| slot | time (s) | what fills the frame | source data / command | caption text |
|---|---|---|---|---|
| 1 hook | 0.0–2.2 | The finished graded render fills the frame (the judge's own 640×480 output of `examples/good/scene.usda`, re-rendered at 1440×1080 with the artifact camera, pillarboxed on the render's own background colour), slow push-in 1.00→1.03 | `judge/grade.sh examples/good/scene.usda --seed 0 --json media/build/verdict.json` → `render.png`; hero re-render via `render_once` | "Five meshes. Two USD implementations. One CPU render." |
| 2 input → output | 2.2–9.4 | Split: left third shows the real USDA source of one mesh (the `def Mesh "Cube"` block, verbatim from the good example); right two-thirds the same render, now with the judge's projected rectangles | `examples/good/scene.usda`; `media/build/verdict.json` G4 rects | "The artifact is one self-contained USDA file — the judge re-derives everything else" |
| 3 escalate (orbit) | 9.4–17.0 | A real camera orbit around the exact graded scene (per-frame `render_once` at 1920×1080, llvmpipe); at 13.2 s a hard cut to the same orbit with the oracle rectangles and per-mesh illuminance k burned on the frames | `render_once` per frame, camera = judge's convention (fov from the artifact), rectangles from the G4 oracle re-projected per orbit frame | 9.4–13.2: "The pinned renderer: Mesa llvmpipe, EGL pbuffer — no GPU, no X"; 13.2–17.0: "Where the numpy pinhole oracle says every mesh must land (k = fitted illuminance)" |
| 4 escalate (Nx speed) | 17.0–24.0 | Real terminal, cropped/zoomed to the active region: the toolchain build log scrolling (`[setup]` lines + ninja compile lines), then the selftest tail; a big "Nx speed" badge states the real compression factor | `/tmp` logs of the RECEIPT runs (`setup` ≈ 800 s of log in ≈ 7 s of video); `selftest.json` | "Pinned toolchain, built from sha256-checked source in a disposable sandbox" |
| 5 proof | 24.0–31.6 | Left: the verdict JSON's key lines (pass, G1–G4, rendered_frac, judge_integrity_ok) at phone-readable size; right: the mutant kill matrix, one row per mutant with the gate that killed it | `media/build/verdict.json`; `media/build/selftest.json` | "11/11 mutants killed by a named gate — the judge fails when it must" |
| 6 end card | 31.6–34.4 | Static end card, dark background, one command centred | — | "python3 cookbook/nanousd-render/run.py" + smaller: "one command → sandbox → pinned build → judge → kill" |

Cut list (hard cuts): 2.2, 9.4, 13.2, 17.0, 24.0, 31.6 — six cuts in
34.4 s = 1.74 cuts / 10 s (gate needs ≥ 0.8). The first frame is the
colour render (not dark, not solid). The last 2.8 s are a static frame
(end-card YDIF ≈ 0). Captions sit in the lower third with a dark scrim
behind the text.

Numbers that appear on screen trace to: `verdict.json` (gates,
rendered_frac, per-mesh k/own_dev), `selftest.json` (mutants, kill rate),
and the RECEIPT runs' wall times (the N× badge).
