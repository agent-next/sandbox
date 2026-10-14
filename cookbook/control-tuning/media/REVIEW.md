# Media Review — control-tuning

Generated 2026-10-14 13:14:26 UTC by `make_media.sh`.

## Files produced
| file | sha256 | bytes |
|------|--------|-------|
| result.png | 038a837a5f54939d4b29034c8557c66e7c4cea9496bdabcd83e6d930650bcf59 | 495471 |
| loop.png | be9d50b9ba58514b7db281d88f0e494219e10efeaf2e52a3cfcd6aea438281e2 | 515279 |
| demo.mp4 | 70ed24c68d5c29bcd38c090716123748218d342d3bf13038d2cfebb18d9574b6 | 1170387 |

## Video checks (ffprobe)
- Duration: 56.000000 s
- Resolution: 1920,1080
- Size: 1170387 bytes (1 MB) — under 8 MB limit: PASS
- Codec: h264, yuv420p, 30 fps, +faststart

## PNG verification (opened at full size)
- **result.png**: 13×8.6 in @ 200 dpi
  - Top-left: Scenario 1 θ trace (blue) with green ±0.003 rad settling band, mark at 0.70 s settle — gate: 2 % settle ≤ 5 s ✓
  - Top-right: Scenario 2 x trace (blue) with green ±0.02 m band, mark at 6.05 s settle — gate: 2 % settle ≤ 7 s ✓
  - Bottom-left: Gate table with 10 rows — all PASS in green, values match verdict JSON exactly
  - Bottom-right: MC scatter (200 blue dots) with red limits at x=7 s, y=8 s — all dots pass, 200/200 = 1.000 ≥ 0.95
  - Caption names all gate rules; no label overlaps; legends outside data
- **loop.png**: 13×9.6 in @ 200 dpi
  - Left: 4×18 gate matrix (too-aggressive, too-sluggish, mc-marginal, good) — ✓/✕ per gate from verdict JSONs
  - Middle-left: too-aggressive vs good torque demand (S2) — red ±1 N·m lines, orange exceeds at 2.52 N·m
  - Middle-right: too-sluggish vs good cart position (S2) — green band, orange never settles (10 s)
  - Right-top: First-failing gate per step with measured values (τ=2.52 N·m, x=10 s, MC=161/200)
  - Right-bottom: Selftest bars — 9/9 mutants killed, gate numbers listed
  - Caption states this is a replay, not a live agent trace; mc-marginal row highlighted as passing all deterministic gates, failing only MC
  - No overlaps: legends outside data, labels readable

## Frame extraction check (4 frames)
- Frame at 2s: extracted (90020 bytes)
- Frame at 10s: extracted (377472 bytes)
- Frame at 20s: extracted (388036 bytes)
- Frame at 30s: extracted (103768 bytes)

## Numbers traceability
Every plotted number was spot-checked against its source file:
- result.png scenario traces ↔ data/good/s1_trace.csv, s2_trace.csv
- result.png gate table ↔ data/good/verdict.json
- result.png MC panel ↔ data/good/mc_samples.csv + verdict.json mc_pass/mc_n
- loop.png matrix cells ↔ each candidate's verdict.json gate pass flags
- loop.png killer traces ↔ data/too-aggressive/s2_trace.csv (τ demand), data/too-sluggish/s2_trace.csv (x position)
- loop.png first-failing gate text ↔ the corresponding verdict.json gate values
- loop.png selftest bars ↔ selftest.sh output (9/9 = 100%)

All match. No synthesised data.

