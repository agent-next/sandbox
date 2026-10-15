#!/usr/bin/env python3
"""Generate known-bad workbook mutants for the spreadsheet-recalc judge.

Each mutant is a single-edit mutation of the known-good dcf_model.xlsx.
Usage: python3 mutants.py [output_dir]
"""
import os
import sys

import openpyxl


def load_good(src):
    return openpyxl.load_workbook(src)


def save(wb, dst):
    wb.save(dst)


def mutant_static_npv(src, dst):
    """Replace NPV formula with a literal number (the negative control)."""
    wb = load_good(src)
    wb["Valuation"]["B2"] = 2753.39  # hardcoded, not a formula
    save(wb, dst)


def mutant_wrong_cashflow(src, dst):
    """Change Year 2 free cash flow from =F4 (5000) to a wrong 5500."""
    wb = load_good(src)
    wb["Projections"]["G4"] = 5500  # was =F4 (5000)
    save(wb, dst)


def mutant_wrong_exponent(src, dst):
    """Discount factor uses A3-1 instead of A3 (wrong exponent)."""
    wb = load_good(src)
    wb["Projections"]["H3"] = "=1/(1+Assumptions!$B$3)^(A3-1)"
    save(wb, dst)


def mutant_missing_year(src, dst):
    """Year 3 free cash flow set to 0 (missing year)."""
    wb = load_good(src)
    wb["Projections"]["G5"] = 0  # was =F5 (6000)
    save(wb, dst)


def mutant_npv_literal_override(src, dst):
    """NPV cell is a hardcoded literal formula (=2753.39)."""
    wb = load_good(src)
    wb["Valuation"]["B2"] = "=2753.39"  # hardcoded literal formula
    save(wb, dst)


def mutant_discount_rate_literal(src, dst):
    """Discount rate replaced with a self-referencing formula (circular)."""
    wb = load_good(src)
    wb["Assumptions"]["B3"] = "=B3+0.02"  # circular reference
    save(wb, dst)


MUTANTS = [
    ("static_npv", mutant_static_npv),
    ("wrong_cashflow", mutant_wrong_cashflow),
    ("wrong_exponent", mutant_wrong_exponent),
    ("missing_year", mutant_missing_year),
    ("npv_literal_override", mutant_npv_literal_override),
    ("discount_rate_literal", mutant_discount_rate_literal),
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
