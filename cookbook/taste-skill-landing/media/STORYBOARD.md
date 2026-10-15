# STORYBOARD — `cookbook/taste-skill-landing/media/demo.mp4`

25–60 s, 1920×1080, 30 fps, H.264 yuv420p CRF 18 +faststart, ≤ 8 MiB.
Every frame before the end card is **real moving browser output** of
`examples/good/site` (headless Chromium 153, Playwright 1.63.0), captured
live into `media/clips/` by `media/record_clips.py`, composited by the
Remotion project in `media/video/` (pinned `remotion@4.0.531`). No stills,
no slide-style step-through, no Ken-Burns.

Total: **44 s** = 41.5 s of moving footage + a 2.5 s static end card.

| # | slot | in–out (s) | what fills the frame | source | caption / HUD |
|---|---|---|---|---|---|
| 1 | **hook — the result, moving** | 0.0–2.0 | The finished Kestrel site, hero at 1440×900, filling the frame; a slow camera push over the compass image (`CameraPush` over `scroll-hero.mp4`), wind form auto-filling | `media/clips/scroll-hero.mp4` (real Chromium recording) | HUD chip: `ALL 7 GATES PASS` + one-line lead |
| 2 | **input → output** | 2.0–10.0 | Left half: the **brief** (`brief.md`) scrolling inside a browser window; right half: the **built site** at 1440×900 scrolling beside it — the same section headings appear on both sides | `media/clips/brief-scroll.mp4` + `media/clips/site-scroll-full.mp4` | split-screen wipe; captions `brief → site` |
| 3 | **escalate — the browser drives it** | 10.0–16.5 | Close-up of the live wind widget: the range slider is dragged, the `<select>` cycles through 8 wind directions, the honest minutes re-render on every change | `media/clips/widget-scrub.mp4` (real interaction) | HUD counter: wind speed value + the site's own computed sentence |
| 4 | **escalate — every breakpoint** | 16.5–23.5 | Three side-by-side panes at 375 / 768 / 1440 px, each scrolling independently (real responsive layout + reveal animations) | `media/clips/resp-375.mp4`, `resp-768.mp4`, `resp-1440.mp4` | width labels 375 / 768 / 1440 |
| 5 | **escalate — the agent, sped up** | 23.5–30.5 | A terminal recording of the judge actually grading both sites inside the sandbox, played at **8× speed** with a `8× speed` badge | `media/clips/grade-run.mp4` (real `judge/grade.sh` output, both artifacts) | `8× speed` chip + elapsed numbers from the receipt |
| 6 | **escalate — the same brief, without the skill** | 30.5–36.0 | `examples/baseline/site` scrolling beside the good site at the same viewport — the fixed-width overflow and grey body text are visible without a caption | `media/clips/baseline-scroll.mp4` + `site-scroll-full.mp4` | labels `with the skill` / `without` |
| 7 | **proof — HUD over moving footage** | 36.0–41.5 | The good site keeps scrolling underneath; gate rows slide in one by one, each naming the rule it enforces, then a PASS badge stamps in | `media/clips/site-scroll-slow.mp4` underneath; gate rows from the seed-42 verdict JSON | `SEED 42 · PASS 7/7`, rows slide in, `PASS` badge |
| 8 | **end card (static)** | 41.5–44.0 | Static frame: `python3 run.py` plus the one-command line and the pinned tool versions | none (static, allowed) | `python3 run.py` |

Notes

- Every number on screen (gate count, contrast ratio 5.19:1, the
  `min 92 px` type scale, `Nx speed`, wall seconds) is read at render time
  from `media/verdict-good.json` / `verdict-baseline.json` /
  `media/selftest-kills.txt` produced by `judge/grade.sh` and
  `judge/selftest.sh` in the same `make_media.sh` run — no invented values.
- The end card is the only static window (2.5 s); `endcard_static` is
  measured over the final 2 s of the 44 s file.
- Scene cuts: every slot change plus the split-screen wipe is a hard cut,
  giving ≈ 13 cuts in 44 s (≈ 3.0 per 10 s, above the gate's 0.8).
