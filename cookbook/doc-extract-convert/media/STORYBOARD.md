# Storyboard — doc-extract-convert

Slot order and craft rules: `cookbook/DEMO-STANDARD.md` (Media). Machine
check: `cookbook/tools/video_gate.py`; blind panel verdicts:
`media/REVIEW.json`. Written before the video is cut; the cut is judged
against this table.

The demo's "physical thing" is a page being read: a scanner band — full
frame width, passing down and back like a flatbed scan — the ink it finds,
the boxes that lock onto that ink, and the JSON that fills in as a result.
Every shot animates that; the band never stops inside a content shot, so
no slide holds and no still pans — only the end card is static.

Real sources (nothing invented):

- `media/data/corpus/` — the corpus `judge/fixtures.py --seed 42` renders
  (the very bytes the extractor is graded on);
- `media/data/extract/` — `examples/good/extract.py` run on that corpus
  (the real records.json/quarantine.json, real confidences);
- `media/data/corrupt/` + `media/data/extract-corrupt/` — the G4 negative
  control (`judge/corrupt.py`, then the extractor again);
- `media/data/*.json` — the seven verdict JSONs `judge/grade.sh` wrote
  (the same ones behind `result.png`/`loop.png` and RECEIPT.md §2–3).

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0–2 s | hook — the finished result | The inv-01 grounded record card: four field rows typing in, confidences landing with them; the page beside it with its four boxes locking on as they land. Full-frame scanner band sweeping throughout | extract/records.json page inv-01; corpus/pages/p000.png + truth.json boxes; seed 42 | "ugly scans → grounded JSON — every value carries its page region" |
| 2–9.5 s | input → output | Left 55 %: the real skewed scan p004.png under the full-frame scanner band. One field's box locks on per pass — the band highlights the ink it just read and the box thickens as it lands. Right 45 %: records.json filling field by field as the boxes do, with the real confidences | corpus/pages/p004.png; truth.json (inv-05); extract/records.json (inv-05) | "12 scans · 3 layouts · skew, dust, fade — a box locks on as the band passes the ink" |
| 9.5–14 s | escalate — the faded photocopy | The low-contrast page p011.png; adaptive binarisation sweeps down it once — rows above the divider re-thresholded live, below it still raw — and the measured ink % of each box appears as the divider passes that box. Scanner band keeps sweeping over the recovering page | corpus/pages/p011.png; check_gates._ink_threshold + the judge's G2 re-measure per box (mode 217 → threshold 177) | "a fixed threshold sees nothing here — adaptive binarisation recovers the ink" |
| 14–18.5 s | escalate — the negative control | The two corrupted pages slide in — the blank and the scanner smear — each stamped QUARANTINE with its real reason code (NO_TEXT, UNREADABLE_PAGE), under the sweeping band | corrupt/ (judge/corrupt.py --which b0,b1); extract-corrupt/quarantine.json reason codes; G4 row of data/good.json | "a blank and a smear, swapped in unseen — both quarantined, 12/12 pages accounted" |
| 18.5–23 s | escalate — the judge proves it can fail | The real selftest verdicts typing line by line at 3× speed (each "killed <mutant> (failed: …)" is a real verdict JSON), beside the per-mutant kill matrix and the 6/6 kill rate; a caret keeps the terminal alive | data/m01-total-as-float … data/m06-accept-bad-date.json verdicts (same run as RECEIPT.md §2) | "the judge proves it can fail — 6/6 single-edit mutants killed" |
| 23–28 s | proof | Still-moving footage: the band sweeps the speckled page under a dim, the ALL GATES PASSED HUD with the G1–G4 rows — 48/48 exact fields, every box on ink, 11/11 totals at 0 ulp, 2/2 pages quarantined | data/good.json gates G1/G3/G4 (same numbers as RECEIPT.md §3) | "one command, one sandbox, one judge — judged against the answer key the corpus generator wrote itself" |
| 28–30 s | end card — static | Flat terminal surface, the demo name and the one-line launch command | — | "python3 cookbook/doc-extract-convert/run.py · a disposable agent-next sandbox: installed, graded, thrown away" |

Numbers on screen trace to: 48/48, 11/11, 0 grounding failures, 2/2 +
12/12 (RECEIPT.md §3 verdict), 6/6 kill rate (RECEIPT.md §2),
confidences and reason codes (the extractor's own JSON in
`media/data/extract*`), threshold 177 (the judge's own
`check_gates._ink_threshold` on that page).

Checklist: 16:9 1920×1080 @ 30 fps | 30 s | 6 hard cuts ≈ 2.0/10 s
(gate ≥ 0.8) | every content frame moves — the band passes the full 1920
and back every 2.6 s, measured ≈ 0.99 of frames with YDIF ≥ 1 on the
640-px downscale (gate ≥ 0.20) | caption cap height ≥ 4 % of frame height
(60 px bold DejaVu ≈ 44 px caps) | payoff visible at 0 s | readable
muted on a phone | every number traces to RECEIPT.md.
