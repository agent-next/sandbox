# spreadsheet-recalc: DCF workbook with live formulas, graded by recalculation

Build a 3-year DCF workbook in xlsx where every computed cell is a live
formula, recalculate it headlessly with LibreOffice, and have a judge verify
the computed values against a closed-form DCF oracle.

## Try it

- **One-command run (fresh sandbox):**
  `python3 cookbook/spreadsheet-recalc/run.py --ref main`
- **Ask your agent** (prompt below) if you use the sandbox plugin.

## One-command run

```bash
python3 cookbook/spreadsheet-recalc/run.py
```

Requires the `sbx` CLI and `SBX_API_KEY` (or `E2B_API_KEY`) in the
environment. The script creates a 30-minute sandbox, clones this repo,
runs `judge/setup.sh`, `judge/selftest.sh`, grades the known-good example,
prints the verdict, and kills the sandbox.

Local alternative (no sandbox):

```bash
bash cookbook/spreadsheet-recalc/judge/setup.sh
bash cookbook/spreadsheet-recalc/judge/selftest.sh
bash cookbook/spreadsheet-recalc/judge/grade.sh cookbook/spreadsheet-recalc/examples/good/dcf_model.xlsx
```

Measured wall time: setup ~20 s, selftest ~35 s, grade ~8 s.

## Ask your agent

> Build a 3-year DCF workbook at `dcf_model.xlsx` with three sheets:
> `Assumptions` (parameters in column B), `Projections` (year-by-year
> discount factors and present values as formulas referencing the
> assumptions), and `Valuation` (NPV as a `=SUM(...)` formula over the
> present-value column). Use openpyxl to author the workbook with live
> formulas — no hardcoded computed values. Then recalculate it headlessly
> and show me the computed NPV at three different discount-rate inputs
> (8%, 10%, 12%).
>
> Run `bash judge/setup.sh` first. Then iterate with
> `bash judge/grade.sh /path/to/your/dcf_model.xlsx --json /tmp/v.json`
> until every gate passes. The judge recalculates your workbook with
> LibreOffice and compares the computed NPV against a closed-form DCF
> oracle at each discount rate. A negative control changes the discount
> rate and re-recalculates — a hardcoded NPV fails.

## What the judge checks (short form)

1. **structure** — the workbook has the required sheets and cells, the NPV
   cell is a formula (not a literal), and no numeric literal inside it
   matches the oracle NPV within 2% (hardcode detection).
2. **recalc** — LibreOffice recalculates it headlessly at each discount
   rate and a computed NPV is read back.
3. **oracle** — the recalculated NPV at each discount rate (8%, 10%, 12%)
   is within 0.5% of the closed-form DCF reference.
4. **negative_control** — the judge changes the discount rate in the
   assumptions sheet, re-recalculates, and verifies the NPV moves by at
   least 1% relative. A static or hardcoded NPV fails this gate.
5. **judge_intact** — sha256 checksums of `judge/` are identical before
   and after grading (the artifact cannot modify the judge).

## Known-bad workbooks (self-test)

`judge/mutants.py` generates 6 known-bad workbooks from the good one by
scripted single edits (openpyxl load → edit → save):

| mutant | edit | gate that kills it |
|---|---|---|
| `static_npv` | NPV cell is a literal number, not a formula | structure + negative_control |
| `wrong_cashflow` | Year-2 FCF changed from =F4 (5000) to 5500 | oracle |
| `wrong_exponent` | Discount factor uses `A3-1` instead of `A3` | oracle |
| `missing_year` | Year-3 FCF set to 0 | oracle |
| `npv_literal_override` | NPV cell is `=2753.39` (hardcoded literal formula) | structure + negative_control |
| `discount_rate_literal` | Discount rate made self-referencing (circular) | structure |

Self-test kill rate: 6/6 = 100% (≥ 90% required).

## Limits, stated plainly

- The DCF model uses simple round-number cash flows so the closed-form
  oracle is exact.
- LibreOffice is the Debian bookworm build of libreoffice-calc
  (`4:7.4.7-1+deb12u14`), installed via apt with a version pin.
- openpyxl is pinned to 3.1.5 with et_xmlfile 2.0.0, installed into
  `$HOME/.venvs/spreadsheet-recalc` from a sha256-checked
  `judge/requirements.lock` (pip `--require-hashes`).
- The judge runs the artifact from a copy; the judge directory is
  checksummed before and after.
