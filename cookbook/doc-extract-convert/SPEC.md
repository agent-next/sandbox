# SPEC: ugly documents → grounded JSON (doc-extract-convert)

## Goal

Show an agent-next sandbox turning a pile of ugly, mixed-format scans into
clean structured JSON in which **every field carries the page region it was
read from**, and documents the extractor is not sure about are **quarantined
instead of guessed**.

The input pile is 12 scanned invoices/receipts. Four of them are
**structured documents** (a fenced, typed record block on the page — the
machine-readable form an EDI/e-invoice feed would carry); the other eight
are plain raster scans in three layout families with three raster
degradations (skew, speckle, low contrast + grain). Every page is rendered
locally by a seeded script, so the corpus is byte-reproducible and no
third-party document is shipped.

The artifact under test is an **extractor**: a program that reads the scans
and writes the JSON. The judge does not trust it: it re-derives the ground
truth from the *fixture source* with a path independent of the artifact's
own parsing, and it checks that every emitted bounding box actually contains
the ink of the value it claims to have read.

## Non-goals

- No OCR-engine bake-off, no training, no ML models, no GPU.
- No PDF, no multi-page documents, no tables beyond the line items the
  fixtures contain (line items are not graded; four header fields are).
- No handwriting, no non-Latin scripts, no rotated-90° pages (skew is
  bounded at 0.6°).
- No network access at grade time: the corpus is generated locally from a
  seed, the judge is offline.
- The extractor is not required to be fast; it is required to be
  deterministic and to ground every value.

## Artifact

A directory the agent produces, containing:

```
<artifact>/
├── extract.py        # entry point, stdlib-only Python 3.10+
└── ...               # any other files it wants to add
```

`extract.py` is invoked by the judge exactly as:

```
python3 <artifact>/extract.py --in <pages_dir> --out <out_dir> [--seed N]
```

and must write, inside `<out_dir>`:

```
<out_dir>/
├── records.json      # one record per input page, in page-id order
└── quarantine.json   # one entry per page routed to quarantine
```

`records.json`:

```json
{"pages": [
  {"page_id": "inv-01", "fields": {
      "vendor":       {"value": "NORTHWIND TRADING COMPANY", "bbox": [x0,y0,x1,y1], "confidence": 0.93},
      "invoice_no":   {"value": "INV-3041",                   "bbox": [x0,y0,x1,y1], "confidence": 0.91},
      "date":         {"value": "2026-03-14",                 "bbox": [x0,y0,x1,y1], "confidence": 0.90},
      "total":        {"value": "467.75",                     "bbox": [x0,y0,x1,y1], "confidence": 0.95}}}]}
```

- `value` — the field value. `date` is normalised to `YYYY-MM-DD`, `total`
  is an **exact decimal string** with two fraction digits (no float, no
  currency symbol, no thousands separator), `vendor` is the uppercased
  vendor name, `invoice_no` is the document's identifier verbatim.
- `bbox` — `[x0, y0, x1, y1]` in **page pixels**, origin top-left,
  `x0 < x1`, `y0 < y1`, integers, inside the page bounds. It must be a
  **tight-ish box around the printed value**: at most
  `MAX_BOX_AREA_RATIO = 0.08` of the page area (8 %).
- `confidence` — a number in `[0, 1]` the extractor assigns to the field.

`quarantine.json`:

```json
{"pages": [
  {"page_id": "inv-07", "reason_code": "LOW_CONFIDENCE",
   "detail": "best field confidence 0.42 < 0.90"}]}
```

`reason_code` is one of `LOW_CONFIDENCE`, `NO_TEXT`, `MALFORMED_FIELD`,
`UNREADABLE_PAGE`. A quarantined page **must not** appear in
`records.json`, and `records.json` must never carry an invented value for
it.

The known-good artifact lives at `examples/good/`.

## Corpus (generated, seeded)

`judge/fixtures.py --seed N --out DIR` writes the corpus and the
ground-truth file `truth.json` (the *fixture source of truth*, see below).

- 12 pages, `inv-01` … `inv-12`, deterministic from `--seed` (default 42).
- 4 structured pages (`inv-01`…`inv-04`) and 8 raster scans (`inv-05`…`inv-12`).
- 3 layout families, 3 degradation profiles (skew / speckle / low contrast
  + grain), and one **already-quarantined** page (`inv-08`) whose date field
  prints as a non-date token.
- Renderer: Pillow, DejaVu fonts. The corpus is *generated*, not
  downloaded, so no third-party licence applies to it.

`judge/corrupt.py --pages DIR --which b0,b1 --out DIR` derives the negative
control: it copies the corpus and replaces two named pages with a blank
page and a noise page.

## Gates (numeric pass rules)

The judge grades with the ground truth derived by its own generator, and
compares it against the truth the artifact's own report claims. All gates
are deterministic at a fixed seed.

- **G0 — schema and containment.** `records.json` and `quarantine.json`
  parse; every page id present exactly once across the two files; every
  `bbox` is 4 integers with `x0 < x1`, `y0 < y1`, inside the page; every
  `confidence` in `[0, 1]`; every `total` an exact 2-decimal string; every
  `date` `YYYY-MM-DD`; `reason_code` from the allowed set. Any violation
  fails G0 outright (this is the gate that catches "printed something
  plausible but malformed").
- **G1 — field accuracy ≥ 95 %.** Over the 12 pages × 4 fields = 48 field
  slots, a field counts correct only if the value is exact (string
  equality after the normalisation above; `total` compared as
  `decimal.Decimal`). Accuracy = correct / 48 ≥ **0.95**.
- **G2 — grounding.** Every non-quarantined field's `bbox` must (a) satisfy
  the area ratio bound and (b) **contain ink**: the judge re-reads that
  page region from the original raster, binarises it, and requires the
  dark-pixel count to be ≥ 1 % and ≤ 60 % of the box area. A box pointing
  at whitespace, or at the whole page, fails.
- **G3 — exact totals.** For every non-quarantined page whose `total` is
  correct in G1, `Decimal(value)` must equal the fixture's total exactly
  (0 ulp). Reported separately from G1 so a float-rounded extractor is
  visible: `exact_totals == pages_with_correct_total`.
- **G4 — negative control (the mutant killer).** Grading is run twice:
  once on the clean corpus, once on the corpus with 2 corrupted pages
  (blank + noise). The corrupted run must satisfy, with the **same**
  extractor binary and no flag telling it about the corruption:
  - both corrupted pages quarantined, each with its expected reason code
    (`NO_TEXT` for the blank, `UNREADABLE_PAGE` for the smear), and no
    page whose ink is intact quarantined — the default corpus still
    carries its one already-unreadable page (`inv-08`), which a correct
    extractor legitimately quarantines alongside the two corrupted ones;
  - `records.json` never carries a record for a corrupted page — no
    invented values, no dropped pages; total page count across both
    files still 12.
- **G5 — determinism and self-consistency.** Two grading runs at the same
  seed produce byte-identical verdict JSON apart from the `timing` key
  (checked by `selftest.sh`); the extractor may not read the ground truth
  (see Judge integrity).  `selftest.sh` additionally proves the grounding
  gate is load-bearing: a judge-guard mutant with the ink check weakened
  to a fixed threshold (blind to the low-contrast pages) must *fail* the
  known-good artifact — if it does not, the gate was never checking
  grounding.

### Gate thresholds, one table

| gate | pass rule |
| --- | --- |
| G0 | 0 schema violations |
| G1 | field accuracy ≥ 0.95 (48 slots) |
| G2 | 0 boxes failing area bound or ink check |
| G3 | exact totals == correct totals, 0 ulp |
| G4 | 2/2 corrupted pages quarantined with expected codes, no intact page quarantined, 0 invented values, 12/12 pages accounted |
| G5 | verdict JSON identical across two runs at the same seed; weakened-judge mutant fails the good artifact |

## Acceptance oracle

The judge never asks "did the tool run". Its oracle is an **independent
re-derivation from the fixture source**:

1. `judge/fixtures.py` builds each page *and* the ground truth in the same
   pass from a seeded record list. The truth is written by the generator,
   not by any OCR step, and not by the artifact. The generated truth is
   **checked in** as `judge/truth.json` (readable, reviewable) together with
   `judge/corpus.sha256` (per-page raster digests); `grade.sh` regenerates
   the corpus at the requested seed and fails if the regenerated truth or
   any page digest differs from the checked-in file, so a drift in the
   generator or the seed is visible instead of silently re-defining the
   answer key.
2. The artifact's claim is then checked against that truth by string /
   `Decimal` comparison (G1, G3) and by re-measuring the page raster
   (G2: the box must contain ink where the generator put it).
3. G4's oracle is the corruption script itself: the two pages it replaced
   are known by construction, so "quarantined exactly those two" is an
   exact set comparison, not a heuristic.
4. G5's oracle is the judge's own repeat run.

Because the truth is generated, the judge cannot be satisfied by a tool
that "always produces a result": an extractor that emits a plausible-looking
record for every page fails G4 (it must quarantine the blank/noise pages) and
an extractor that quarantines everything fails G1 (accuracy 0).

## Judge integrity

- `judge/grade.sh` copies the artifact to a scratch directory and runs it
  there; the artifact is never executed from a path it can write to inside
  the judge.
- The corpus is generated into a fresh scratch dir at grade time and its
  `truth.json` is written *outside* the directory the extractor is pointed
  at (`--in`), so an extractor that scans its input directory cannot pick
  up the answers.
- `judge/` is sha256-checksummed before and after grading; a difference
  fails the run. The artifact cannot modify the judge.
- The extractor's `--in` directory contains only page images and a
  `pages.json` listing page ids and sizes — no truth, no field names.

## Reproducibility

- Every tool version is pinned and sha256-checked by `judge/setup.sh`
  (`judge/package-sha256.txt` for Debian packages,
  `judge/requirements.txt` for wheels); `judge/VERSIONS.txt` records what
  was installed.
- Every random choice takes `--seed` (default 42); fixtures, corruption and
  grading are deterministic. No wall-clock, no `set`-order iteration, no
  threading in the judge.
- Tolerances for the independent reproduction in `REPRODUCE.md`: the
  verdict JSON must match this SPEC's receipt byte-for-byte apart from
  `timing`, and the two measured numbers (field accuracy, quarantine count)
  must be identical.

## Size budget

Corpus pages are 900 × 1270 px grayscale PNGs (~60–150 KB each, ~1 MB for
12). `examples/good/` is source code only; no corpus is committed.
