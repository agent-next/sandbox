#!/usr/bin/env python3
"""Build a 3-year DCF workbook with live formulas.

Creates dcf_model.xlsx with three sheets:
  - Assumptions: initial investment, discount rate, tax rate
  - Projections: year-by-year P&L → FCF → discount factor → PV (all formulas)
  - Valuation: NPV cell driven by a SUM formula over the PVs

All computed cells are formulas — no hardcoded values.
"""

import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side

# ── Assumptions ──────────────────────────────────────────────────────────────
INITIAL_INVESTMENT = -10000
DISCOUNT_RATE = 0.08
TAX_RATE = 0.20

# ── Revenue / Cost per year (round numbers) ──────────────────────────────────
# EBIT = Revenue - Cost;  NOPAT = EBIT * (1 - tax);  FCF = NOPAT
# With tax=0.20:  FCF = (Revenue - Cost) * 0.80
REVENUE = [10000, 11000, 12000]
COST = [5000, 4750, 4500]

# ── Build workbook ───────────────────────────────────────────────────────────
wb = openpyxl.Workbook()

header_font = Font(bold=True)
header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
thin = Side(style="thin")
border = Border(left=thin, right=thin, top=thin, bottom=thin)

# ── Sheet 1: Assumptions ─────────────────────────────────────────────────────
ws_a = wb.active
ws_a.title = "Assumptions"

rows = [
    ("Parameter", "Value"),
    ("Initial Investment", INITIAL_INVESTMENT),
    ("Discount Rate", DISCOUNT_RATE),
    ("Tax Rate", TAX_RATE),
]
for r, (label, val) in enumerate(rows, 1):
    ws_a.cell(row=r, column=1, value=label)
    ws_a.cell(row=r, column=2, value=val)
    if r == 1:
        for c in (1, 2):
            ws_a.cell(row=r, column=c).font = header_font
            ws_a.cell(row=r, column=c).fill = header_fill

ws_a.column_dimensions["A"].width = 22
ws_a.column_dimensions["B"].width = 14

# ── Sheet 2: Projections ─────────────────────────────────────────────────────
ws_p = wb.create_sheet("Projections")

headers = ["Year", "Revenue", "Cost", "EBIT", "Tax", "NOPAT",
           "Free Cash Flow", "Discount Factor", "PV of FCF"]
for c, h in enumerate(headers, 1):
    cell = ws_p.cell(row=1, column=c, value=h)
    cell.font = header_font
    cell.fill = header_fill

# Years 1-3 in rows 3-5
for year in (1, 2, 3):
    r = year + 2  # rows 3, 4, 5
    ws_p.cell(row=r, column=1, value=year)
    ws_p.cell(row=r, column=2, value=REVENUE[year - 1])
    ws_p.cell(row=r, column=3, value=COST[year - 1])
    ws_p.cell(row=r, column=4, value=f"=B{r}-C{r}")                          # EBIT
    ws_p.cell(row=r, column=5, value=f"=D{r}*Assumptions!$B$4")               # Tax
    ws_p.cell(row=r, column=6, value=f"=D{r}-E{r}")                           # NOPAT
    ws_p.cell(row=r, column=7, value=f"=F{r}")                                # FCF
    ws_p.cell(row=r, column=8, value=f"=1/(1+Assumptions!$B$3)^A{r}")        # DF
    ws_p.cell(row=r, column=9, value=f"=G{r}*H{r}")                           # PV

for col, w in zip("ABCDEFGHI", (8, 12, 12, 12, 10, 12, 16, 16, 14)):
    ws_p.column_dimensions[col].width = w

# ── Sheet 3: Valuation ───────────────────────────────────────────────────────
ws_v = wb.create_sheet("Valuation")

ws_v.cell(row=1, column=1, value="Metric").font = header_font
ws_v.cell(row=1, column=1).fill = header_fill
ws_v.cell(row=1, column=2, value="Value").font = header_font
ws_v.cell(row=1, column=2).fill = header_fill

ws_v.cell(row=2, column=1, value="NPV")
ws_v.cell(row=2, column=2, value="=Assumptions!B2+SUM(Projections!I3:I5)")

ws_v.column_dimensions["A"].width = 16
ws_v.column_dimensions["B"].width = 14

# ── Save ─────────────────────────────────────────────────────────────────────
wb.save("dcf_model.xlsx")
print("Created dcf_model.xlsx")
