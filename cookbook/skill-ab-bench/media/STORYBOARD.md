# demo.mp4 storyboard — skill-ab-bench

Planned before cutting the video; the video is judged against this table.
Total 43 s at 30 fps (1290 frames), 1920×1080. Every shot animates real
output from the committed `media/data/` files — no stills, no Ken-Burns
pans, no text-only frames except the end card. Captions are burned in at
fontsize 45+ pt (cap height ≈ 45 px ≈ 4.2 % of frame height). "Replay ×6"
means real recorded output streamed faster than it ran, and is labelled.

| slot | time | what fills the frame (moving) | source data | caption (burned in) |
|---|---|---|---|---|
| hook | 0.0–2.4 | the finished hero: pass-count bars grow to 16/16, 5/16, 4/16 and the bootstrap CI whiskers draw to +75.0 pts across the judge's 25-pt bar; the delta counter ticks to +75.0 | `verdict-bench-fresh.json` (G5/G6/G7) | "16/16 with the skill vs 4/16 without — judged PASS" |
| input → output | 2.4–10.0 | three real tasks type themselves out from the corpus (kv02 section trap, kv03 commented block, kv04 case trap), then each arm's answer stamps in with its verified verdict: skill ✓, no-skill ✗, placebo ✗ | `judge/tasks.json` (inputs/prompts), `bench-fresh-results.json` (answers + verified verdicts) | "same 16 questions, three desks: skill / none / placebo" |
| escalate 1 | 10.0–17.2 | the bench replays: a 16×3 grid of task×arm cells fills pair by pair green/red while the real bench stdout streams beside it (48 pairs in 2.7 s, shown ×6) | `bench-run.log`, `bench-fresh-results.json` | "replay ×6 — 48 fresh-interpreter pairs, one bench run" |
| escalate 2 | 17.2–27.8 | the fixing loop replays: three graded records in sequence, gates light up per record, the killing gate stamps red with its measured number (−75.0 pts / p = 0.101 ≥ 0.05 / pass) | `verdict-arms-swapped.json`, `verdict-marginal-win.json`, `verdict-bench-fresh.json` | "the loop: grade → fix → grade (a replay of graded records, not a live trace)" |
| escalate 3 | 27.8–32.4 | close-up: the significance bars — Fisher p markers drop onto a log axis against the 0.05 line; the marginal 12/16 record lands on the fail side, the real one at 1.6e-05 | `verdict-marginal-win.json` (p = 0.101), `verdict-bench-fresh.json` (p = 1.6e-05) | "a real 25-pt gap that is NOT significant: the bar is honest" |
| proof | 32.4–40.0 | the judge's PASS verdict as a HUD: the nine gates tick green with their measured numbers while the CI hero sweeps in the background; then the mutant kill matrix — 11 cells stamp killed, counter runs to 11/11 | `verdict-bench-fresh.json`, `selftest.log` (11/11 killed) | "judge PASS — 9/9 gates · self-test 11/11 mutants killed (100 %)" |
| end card | 40.0–43.0 | static: the one-command launch + the ask-your-agent pointer | — | "python3 cookbook/skill-ab-bench/run.py" |

## Rules the cut must obey

- 0–2 s is the finished result, not a title card; the end card is the only
  static shot and covers the last 3 s.
- Every number on screen traces to a committed `media/data/` file; nothing
  is synthesised (no sin/random/linspace anywhere in `make_video.py`).
- The ×6 replay label rides every sped-up stream.
- Cuts between slots are hard cuts between visually distinct layouts
  (≥ 0.8 per 10 s: 6 cuts / 43 s ≈ 1.4 per 10 s).
- Encode chain: frames → lossless per-slot clips (`media/clips/`) →
  lossless master (`media/master/demo-master.mp4`, `-crf 0`) → web encode
  `demo.mp4` (H.264 `-crf 18 -preset slow -pix_fmt yuv420p -movflags
  +faststart`), all at 30 fps.
