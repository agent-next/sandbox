# spreadsheet-recalc: DCF workbook demo — SPEC

An agent works inside a disposable sandbox on a real financial-modeling
problem: build a 3-year DCF (discounted cash flow) workbook in xlsx where
every computed cell is a live formula, recalculate it headlessly with
LibreOffice, and report the NPV at three discount-rate inputs. A judge the
agent cannot fool then recalculates the workbook itself and compares the
computed cell values against a closed-form DCF oracle — never trusting
the agent's own claimed numbers.

## Goal

- Artifact: one `.xlsx` workbook (`dcf_model.xlsx`) containing an
  Assumptions sheet, a Projections sheet with year-by-year DCF formulas,
  and a Valuation sheet whose NPV cell is a formula driven by the
  discount-rate assumption.
- Judge: `judge/grade.sh` runs LibreOffice headless to recalculate the
  workbook, reads the computed cell values, and scores them against the
  closed-form DCF oracle at discount rates 8 %, 10 % and 12 %. A negative
  control changes the discount rate and re-recalculates; a hardcoded or
  static NPV fails.
- Self-test: `judge/selftest.sh` proves the judge fails known-bad
  workbooks.

## Non-goals

- Real-world financial data or projections: the cash flows are simple,
  round numbers chosen so the closed-form oracle is exact.
- Multiple valuation scenarios, sensitivity tables, or Monte-Carlo
  analysis: the demo tests one DCF model at three discount rates.
- GUI interaction with the spreadsheet: everything is headless
  (openpyxl authoring + LibreOffice recalc).
- Currency conversion, inflation adjustment, or tax complexity beyond a
  flat tax rate.

## The artifact contract

`dcf_model.xlsx` is a single workbook with three sheets. The layout is
fixed so the judge can locate cells deterministically.

### Sheet: `Assumptions`

| Cell | Content | Type |
|------|---------|------|
| A1 | "Parameter" | string |
| B1 | "Value" | string |
| A2 | "Initial Investment" | string |
| B2 | numeric (e.g. -10000) | number |
| A3 | "Discount Rate" | string |
| B3 | numeric (e.g. 0.08) | number |
| A4 | "Tax Rate" | string |
| B4 | numeric (e.g. 0.25) | number |

### Sheet: `Projections`

Row 1 headers: `Year`, `Revenue`, `Cost`, `EBIT`, `Tax`, `NOPAT`,
`Free Cash Flow`, `Discount Factor`, `PV of FCF`.

Data rows 2–4 (years 0–2) or 3–5 (years 1–3). The judge expects
years 1–3 in rows 3–5 with formulas:

- `D{row}` = `B{row} - C{row}` (EBIT)
- `E{row}` = `D{row} * Assumptions!B4` (Tax)
- `F{row}` = `D{row} - E{row}` (NOPAT)
- `G{row}` = `F{row}` (Free Cash Flow)
- `H{row}` = `=1/(1+Assumptions!$B$3)^A{row}` (Discount Factor)
- `I{row}` = `G{row} * H{row}` (PV of FCF)

### Sheet: `Valuation`

| Cell | Content | Type |
|------|---------|------|
| A1 | "Metric" | string |
| B1 | "Value" | string |
| A2 | "NPV" | string |
| B2 | formula | formula |

The NPV formula must reference the Assumptions discount rate and the
Projections PV column. A valid formula is:

```
=Assumptions!B2 + SUM(Projections!I3:I5)
```

where `Assumptions!B2` is the initial investment (negative) and the SUM
adds the discounted cash flows for years 1–3.

**Rules the judge enforces structurally** (gate 1):
- The file is a valid xlsx loadable by openpyxl.
- The three required sheets exist.
- `Valuation!B2` contains a formula (starts with `=`), not a literal.
- `Projections!I3` contains a formula (starts with `=`).
- `Assumptions!B3` (discount rate) is numeric.
- No numeric literal in `Valuation!B2` matches the oracle NPV within
  2 % (hardcode detection).

## Judge gates (numeric pass rules)

`judge/grade.sh <artifact> [--seed N] [--json out.json]` exits 0 only
if gates 1–4 all pass. `--seed` (default 0) is recorded in the verdict.
The judge never runs the artifact as a program — it recalculates the
xlsx with LibreOffice and reads computed values.

### Gate 1 — structure

- File exists, size ≤ 5 MiB.
- Loads with openpyxl (`import openpyxl; openpyxl.load_workbook(path)`).
- Sheets `Assumptions`, `Projections`, `Valuation` exist.
- `Valuation!B2` starts with `=` (is a formula).
- `Projections!I3` starts with `=` (is a formula).
- `Assumptions!B3` is numeric.
- No hardcode: `Valuation!B2` does not contain a numeric literal that
  is within 2 % of the oracle NPV at 8 % (the base rate).

### Gate 2 — recalc

- `libreoffice --headless --convert-to xlsx --outdir <tmp> <artifact>`
  exits 0 within 120 s.
- The converted file exists and is loadable by openpyxl.

### Gate 3 — oracle (closed-form DCF)

For each discount rate r in {0.08, 0.10, 0.12}:

1. The judge writes r into `Assumptions!B3` of a working copy.
2. Runs LibreOffice headless recalc on the working copy.
3. Reads `Valuation!B2` with `data_only=True`.
4. Computes the closed-form NPV:
   `NPV = Initial_Investment + sum(FCF_t / (1+r)^t, t=1..3)`
   where FCF values are read from `Projections!G3:G5` (the Free Cash
   Flow column) and Initial_Investment from `Assumptions!B2`.
5. The computed NPV must be within **±0.5 %** of the closed-form value.

### Gate 4 — negative control

1. Read the base NPV (rate = 8 %).
2. Change `Assumptions!B3` to 0.10 in a working copy.
3. Run LibreOffice recalc.
4. Read the new NPV.
5. The NPV must have moved by **at least 1 %** relative to the base
   (a static or hardcoded value does not move).
6. The new NPV must also be within ±0.5 % of the closed-form at 10 %
   (already checked in gate 3, but this confirms the move is real).

## Tolerances

| quantity | tolerance |
|---|---|
| NPV vs closed form (each rate) | ±0.5 % relative |
| Negative-control movement | ≥ 1 % relative change |

The 0.5 % tolerance is tight enough that a wrong formula (wrong
exponent, wrong initial investment, missing a year) produces errors
above 5 %, while absorbing floating-point noise from LibreOffice.

## Acceptance oracle

The judge never trusts the artifact's own computed values as ground
truth. Correctness is decided by the closed-form DCF formula:

```
NPV(r) = I + sum_{t=1}^{3} FCF_t / (1+r)^t
```

where I = `Assumptions!B2` (initial investment, negative),
FCF_t = `Projections!G{row}` (free cash flow for year t),
r = discount rate.

The judge reads I and FCF_t from the recalculated workbook (so the
agent's numbers feed the oracle), computes the closed form in Python
float arithmetic, and compares against the workbook's computed NPV.

This is an **analytic solution** — no reference tool needed. The
closed form is exact for the simple 3-year DCF with no terminal value.

## Known-bad examples (self-test)

`judge/mutants.py` derives 6 known-bad workbooks from the known-good
one by scripted single edits (openpyxl load → edit formula/value →
save):

| mutant | edit | gate that kills it |
|---|---|---|
| `static_npv` | `Valuation!B2` formula replaced with literal number | structure (no formula) + negative control (no movement) |
| `wrong_cashflow` | `Projections!G3` FCF changed from 4000 to 5000 | oracle (NPV off by ~10 %) |
| `wrong_exponent` | `Projections!H3` formula uses `A3-1` instead of `A3` | oracle (year-1 discount factor wrong) |
| `missing_year` | `Projections!G5` (year 3) set to 0 | oracle (NPV too low) |
| `npv_literal_override` | `Valuation!B2` = `=2753.39` (hardcoded literal formula) | structure + negative control |
| `discount_rate_literal` | `Assumptions!B3` = 0.08 replaced with formula `=0.08+0.02` (self-referencing) | recalc (circular ref) or oracle |

`judge/selftest.sh` grades the known-good (must pass) and every mutant
(each must fail ≥ 1 gate), prints the kill rate, and checks determinism
(two grades produce byte-identical verdicts except `timing`). It exits
non-zero unless the kill rate is ≥ 90 %.

## Determinism

LibreOffice recalc is deterministic for a given input file and version.
Two grades of the same artifact give byte-identical verdict JSON except
`timing` — enforced by `selftest.sh`.

## Toolchain (pinned, sha256-checked)

`judge/setup.sh` installs:

- `libreoffice-calc` 7.4.7 (Debian bookworm) via sha256-checked `.deb`
  from the Debian pool.
- `python3-openpyxl` 3.0.9 (Debian bookworm) via apt.
- The judge engine itself is stdlib-only (openpyxl + subprocess +
  json + hashlib); no pip venv needed.

`judge/VERSIONS.txt` records what setup actually installed.
