# Storyboard — Premiere, open source

Written before cutting. All playback uses `data/render.mp4`, produced by
`bash judge/grade.sh examples/good/edit.mlt --seed 1 --export media/data`.
Numbers come from `data/verdict.json`, `data/selftest.json`, and
`data/frames.json`. No stock footage or invented terminal output.

| slot | what fills the frame | real source | burned-in caption |
|---|---|---|---|
| 0–2 s, hook | the finished MLT render, edge to edge, with the title and the verdict on frame 0 | graded render, normal speed; verdict.json | `AN AGENT CUT THIS VIDEO IN CODE` / `PASS 225/225` / `THE CUT. EVERY FRAME.` |
| 2–6 s, input → output | numeric brief beside the playing edit | spec.json + render | `225 FRAMES. ZERO GUESSWORK.` |
| 6–10 s, source → timeline | three source strips above the graded playback | generated clips, EDL | `A → DISSOLVE → B → C` |
| 10–15 s, dissolve close-up | real overlap frames replayed slowly, with measured weight and per-frame barcode | output frames 100–124; frames.json | `25 FRAMES. ONE DISSOLVE.` / `0.2x speed` |
| 15–20 s, provenance | playing output and enlarged decoded clip/frame readout | frames.json, frames 195–224 | `THE JUDGE READS THE PIXELS.` / `0.24x speed` |
| 20–25 s, audio | measured music-band RMS bars and pass line at 8 dB | verdict.json + frames.json | `MUSIC DOWN. VOICE THROUGH.` |
| 25–28 s, process | actual fresh-sandbox run log, replayed on a cropped terminal panel | data/run.log from RECEIPT run 1 | `SANDBOX RUN` / measured `Nx speed · log replay` |
| 28–35 s, proof | large numeric PASS cards | verdict.json | `225 / 225 FRAMES CHECKED` |
| 35–40 s, mutation proof | two-column matrix with every intended failing gate | selftest.json, all 11 mutants | `11 / 11 BAD EDITS REJECTED` |
| 40–44 s, static end card | one launch command, split across two lines to stay legible | README | `python3 cookbook/video-edit-mlt/run.py` |

Master: 1920×1080, 30 fps, 44 s, lossless H.264 under ignored `master/`.
Web: CRF 18, preset slow, yuv420p, faststart, <8 MB.
Caption font 64 px (capital height ≥43.2 px). Figures are 200 dpi.
Mechanical verdict: `video_gate.json`. Blind panel: `REVIEW.json`;
unavailable reviews are explicitly marked, never scored by the builder.
