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
| 1 | **hook — the result, moving** | 0.0–2.0 | The finished site, hero at 1440×900, filling the frame on a zoom-and-ping-pong pan (1.3→1.55 zoom, window bounces ±700/±450 px) — real scrolling, the wind form live | `media/clips/scroll-hero.mp4` (real Chromium recording) | chip `examples/good/site — judged live in headless Chromium 153`; kinetic serif headline `Kestrel — all 7 gates pass`, words sliding up one by one |
| 2 | **input → output** | 2.0–10.0 | `brief.md` scrolls full-frame under a zoom+pan, then the built site **wipes in from the right** (2.3–3.7 s) and takes 56% of the frame, still scrolling and panning | `brief-scroll.mp4`, then `site-scroll-full.mp4` | chip `brief.md — the product, in the agent's own words`; `the built site` tag on the incoming pane |
| 3 | **escalate — the browser drives it** | 10.0–16.5 | Close-up push (1.6→2.0 zoom) and ping-pong pan over the live wind widget: the slider is dragged, the `<select>` cycles directions, the honest minutes re-render | `media/clips/widget-scrub.mp4` (real interaction) | two counting-up HUD counters: the still-air 40 km loop minutes, then the real saving from the verdict (`68 min`) |
| 4 | **escalate — every breakpoint** | 16.5–23.5 | Three side-by-side panes at 375 / 768 / 1440 px, each a real recording ping-pong-panning independently | `resp-375.mp4`, `resp-768.mp4`, `resp-1440.mp4` | width labels `375 px` / `768 px` / `1440 px`; chip `no horizontal overflow … measured, not claimed` |
| 5 | **escalate — the agent, sped up** | 23.5–30.5 | The judge actually grading, in a terminal, under a sustained ping-pong pan | `media/clips/grade-run.mp4` (real `judge/grade.sh` output) | rotated `8× speed` badge; footer with the real selftest kill count and the baseline's real failure count |
| 6 | **escalate — the same brief, without the skill** | 30.5–36.0 | Split viewport: the good site scrolling on the left, `examples/baseline/site` scrolling on the right, each ping-pong panning | `site-scroll-full.mp4` + `baseline-scroll.mp4` | `with the skill` / `without it` tags; footer `the same brief: 4 of 7 gates fail without the taste rules` |
| 7 | **proof — HUD over moving footage** | 36.0–41.5 | The good site keeps scrolling underneath (1.35→1.7 zoom, ping-pong pan) while the 7 gate rows slide in from the left one by one, then the PASS badge stamps in | `site-scroll-slow.mp4` underneath; rows read from the seed-42 verdict | chip with the real verdict numbers (`ALL 7 GATES PASS · contrast AA 5.19:1 · taste rules 15/15 · axe-core 4.10.3 clean`); `PASS · 7/7` badge |
| 8 | **end card (static)** | 41.5–44.0 | Static frame: the wordmark, `python3 run.py`, and the pinned tool versions | none (static, allowed) | `python3 run.py` |

Notes

- **Every number on screen is read at render time** from the judge
  outputs of the *same* run, via `media/make_facts.py` →
  `media/video/src/facts.json` → `src/facts.ts`. Nothing is hand-typed:
  the gate count and pass text, the 5.19:1 contrast ratio, the 15/15
  taste-rule tally, the 68-minute wind saving, the `23/23` mutant kill
  count and the baseline's 4 failing gates are all read out of
  `judge/grade.sh` and `judge/selftest.sh` output.
- The end card is the only static window (2.5 s); `endcard_static` is
  measured over the final 2 s of the 44 s file.
- Scene cuts: one per slot change (7 cuts) plus the wipes, giving ≈ 9
  cuts in 44 s (≈ 2.0 per 10 s, above the gate's 0.8). Measured on the
  encoded file — see the gate JSON in the commit message.
