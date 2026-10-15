#!/usr/bin/env python3
"""Generate known-bad workbook mutants for the spreadsheet-recalc judge.

Each mutant is a single-edit mutation of the known-good dcf_model.xlsx.
Usage: python3 mutants.py [output_dir]
"""
import os
import shutil
import sys

import openpyxl


def load_good(src):
    return openpyxl.load_workbook(src)


def save(wb, dst):
    wb.save(dst)


def mutant_hardcoded_npv(src, dst):
    """Replace NPV formula with a static number (the negative control)."""
    wb = load_good(src)
    wb["Valuation"]["B2"] = 890.11  # hardcoded, not a formula
    save(wb, dst)


def mutant_wrong_cashflow(src, dst):
    """Change Year 2 cash flow from 4200 to 9999."""
    wb = load_good(src)
    wb["Assumptions"]["B5"] = 9999
    save(wb, dst)


def mutant_wrong_rate(src, dst):
    """Change discount rate from 0.08 to 0.50."""
    wb = load_good(src)
    wb["Assumptions"]["B3"] = 0.50
    save(wb, dst)


def mutant_missing_formula(src, dst):
    """Replace discount factor formula in C3 with a static value."""
    wb = load_good(src)
    wb["Projections"]["C3"] = 0.92  # static, not =1/(1+Assumptions!$B$3)^A3
    save(wb, dst)


def mutant_wrong_formula(src, dst):
    """Use simple sum instead of NPV (ignores discounting)."""
    wb = load_good(src)
    wb["Valuation"]["B2"] = "=SUM(Projections!B2:B5)"
    save(wb, dst)


def mutant_static_pv(src, dst):
    """Replace PV column with static values (no formula)."""
    wb = load_good(src)
    wb["Projections"]["D3"] = 3240.74
    wb["Projections"]["D4"] = 3600.82
    wb["Projections"]["D5"] = 4048.54
    save(wb, dst)


MUTANTS = [
    ("hardcoded_npv", mutant_hardcoded_npv),
    ("wrong_cashflow", mutant_wrong_cashflow),
    ("wrong_rate", mutant_wrong_rate),
    ("missing_formula", mutant_missing_formula),
    ("wrong_formula", mutant_wrong_formula),
    ("static_pv", mutant_static_pv),
]


def main():
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "examples", "good")
    src = os.path.join(src_dir, "dcf_model.xlsx")
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "mutants")
    os.makedirs(out_dir, exist_ok=True)

    for name, fn in MUTANTS:
        dst = os.path.join(out_dir, f"{name}.xlsx")
        fn(src, dst)
        print(name)


if __name__ == "__main__":
    main()
