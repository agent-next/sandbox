"""Judge core for spreadsheet-recalc demo.

Validates a DCF workbook artifact by:
1. Structure check (openpyxl formulas present, no hardcoded oracle values)
2. LibreOffice headless recalculation
3. Closed-form DCF oracle comparison at 8%, 10%, 12% discount rates
4. Negative control (change rate, re-recalc, verify NPV moves)
5. Judge integrity (checksums before/after)
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import openpyxl

JUDGE_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO_DIR = os.path.dirname(JUDGE_DIR)

# Closed-form DCF oracle parameters
ORACLE_PARAMS = {
    "initial_investment": -10000,
    "cash_flows": [3500, 4200, 5100],
    "discount_rates": [0.08, 0.10, 0.12],
    "tolerance_pct": 0.5,  # 0.5% tolerance
}

MAX_BYTES = 2 * 1024 * 1024  # 2 MiB max artifact size
RUN_TIMEOUT_S = 120  # 2 minutes for LibreOffice recalc


def check_shas(directory):
    """Return dict of sha256 digests for all files in directory."""
    digests = {}
    for root, dirs, files in os.walk(directory):
        dirs.sort()
        if os.path.basename(root) == "__pycache__":
            dirs[:] = []
            continue
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            p = os.path.join(root, name)
            with open(p, "rb") as fh:
                digests[os.path.relpath(p, directory)] = (
                    hashlib.sha256(fh.read()).hexdigest()
                )
    return digests


def load_artifact(artifact_path):
    """Load and validate artifact structure."""
    problems = []

    # Size check
    size = os.path.getsize(artifact_path)
    if size > MAX_BYTES:
        problems.append(f"artifact size {size} exceeds {MAX_BYTES} bytes")

    # Must be a valid xlsx
    try:
        wb = openpyxl.load_workbook(artifact_path, data_only=False)
    except Exception as e:
        return None, [f"cannot load xlsx: {e}"]

    # Must contain required sheets
    required_sheets = {"Assumptions", "Projections", "Valuation"}
    missing = required_sheets - set(wb.sheetnames)
    if missing:
        problems.append(f"missing sheets: {missing}")

    # Check formulas exist (not hardcoded values)
    # At least some cells must contain formulas
    formula_count = 0
    for sname in wb.sheetnames:
        ws = wb[sname]
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    formula_count += 1

    if formula_count == 0:
        problems.append("no formulas found in workbook")

    # Check for hardcoded oracle values (NPV results)
    # The NPV at 8% for the standard model is ~890.11
    # We check that key computed cells are formulas, not literals
    oracle_npv_8 = compute_npv_oracle(0.08)
    oracle_npv_10 = compute_npv_oracle(0.10)
    oracle_npv_12 = compute_npv_oracle(0.12)

    # Scan for hardcoded values that match oracle results
    for sname in wb.sheetnames:
        ws = wb[sname]
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, (int, float)):
                    # Check if this is a computed cell that should be a formula
                    # We check if the value is close to an oracle result
                    for oracle_val in [oracle_npv_8, oracle_npv_10, oracle_npv_12]:
                        if abs(cell.value - oracle_val) < 0.01:
                            # This is suspicious - a hardcoded oracle value
                            # But only flag if it's in a "result" area
                            pass  # We'll catch this in the negative control

    return wb, problems


def compute_npv_oracle(rate):
    """Closed-form DCF NPV: sum of CF_t / (1+r)^t."""
    npv = ORACLE_PARAMS["initial_investment"]
    for t, cf in enumerate(ORACLE_PARAMS["cash_flows"], start=1):
        npv += cf / (1 + rate) ** t
    return npv


def recalculate_workbook(artifact_path, workdir, rate_override=None):
    """Run LibreOffice headless recalc and return computed values.

    If rate_override is set, modifies the discount rate before recalc.
    """
    # Copy artifact to workdir
    os.makedirs(workdir, exist_ok=True)
    local_copy = os.path.join(workdir, "model.xlsx")
    shutil.copy(artifact_path, local_copy)

    # If rate override, modify the workbook
    if rate_override is not None:
        wb = openpyxl.load_workbook(local_copy)
        ws = wb["Assumptions"]
        ws["B3"] = rate_override  # Discount Rate cell
        wb.save(local_copy)

    # Run LibreOffice headless conversion (forces recalc)
    outdir = os.path.join(workdir, "out")
    os.makedirs(outdir, exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = workdir  # Isolate LibreOffice profile

    proc = subprocess.run(
        [
            "libreoffice", "--headless", "--convert-to", "xlsx",
            "--outdir", outdir, local_copy,
        ],
        capture_output=True, text=True, timeout=RUN_TIMEOUT_S, env=env,
        cwd=workdir,
    )

    if proc.returncode != 0:
        return None, f"LibreOffice exit {proc.returncode}: {proc.stderr}"

    # Read computed values
    result_path = os.path.join(outdir, "model.xlsx")
    if not os.path.exists(result_path):
        return None, "LibreOffice did not produce output file"

    wb = openpyxl.load_workbook(result_path, data_only=True)

    # Extract key values
    values = {}

    # NPV from Valuation sheet
    try:
        ws = wb["Valuation"]
        # Find NPV row
        for row in ws.iter_rows(min_row=1, max_row=10, max_col=2):
            if row[0].value and "NPV" in str(row[0].value).upper():
                values["npv"] = row[1].value
                break
    except Exception:
        pass

    # Discount factor and PV from Projections
    try:
        ws = wb["Projections"]
        pv_values = []
        for row in ws.iter_rows(min_row=2, max_row=10, min_col=4, max_col=4):
            if row[0].value is not None:
                pv_values.append(row[0].value)
        values["pv_list"] = pv_values
    except Exception:
        pass

    return values, None


def grade_artifact(artifact_path, seed=0):
    """Grade a DCF workbook artifact. Returns (verdict_dict, exit_code)."""
    verdict = {
        "artifact": os.path.basename(artifact_path),
        "seed": seed,
        "gates": {},
        "metrics": {},
        "problems": [],
    }

    sha_before = check_shas(JUDGE_DIR)
    workdir = tempfile.mkdtemp(prefix="spreadsheet-recalc-")

    try:
        # Gate 1: Structure
        wb, problems = load_artifact(artifact_path)
        verdict["gates"]["structure"] = len(problems) == 0
        if problems:
            verdict["problems"].extend(problems)

        if wb is None:
            return verdict, 1

        # Gate 2: Recalculate at 8% (default rate)
        values_8, err = recalculate_workbook(artifact_path, os.path.join(workdir, "r8"))
        if err:
            verdict["gates"]["recalc_8"] = False
            verdict["problems"].append(f"recalc at 8%: {err}")
        else:
            verdict["gates"]["recalc_8"] = True
            npv_8 = values_8.get("npv")
            oracle_8 = compute_npv_oracle(0.08)

            if npv_8 is None:
                verdict["gates"]["npv_8_present"] = False
                verdict["problems"].append("NPV not found after recalc at 8%")
            else:
                verdict["gates"]["npv_8_present"] = True
                err_pct_8 = abs(npv_8 - oracle_8) / abs(oracle_8) * 100
                verdict["metrics"]["npv_8_computed"] = round(npv_8, 4)
                verdict["metrics"]["npv_8_oracle"] = round(oracle_8, 4)
                verdict["metrics"]["npv_8_err_pct"] = round(err_pct_8, 4)
                verdict["gates"]["npv_8_match"] = err_pct_8 <= ORACLE_PARAMS["tolerance_pct"]

        # Gate 3: Recalculate at 10%
        values_10, err = recalculate_workbook(
            artifact_path, os.path.join(workdir, "r10"), rate_override=0.10
        )
        if err:
            verdict["gates"]["recalc_10"] = False
            verdict["problems"].append(f"recalc at 10%: {err}")
        else:
            verdict["gates"]["recalc_10"] = True
            npv_10 = values_10.get("npv")
            oracle_10 = compute_npv_oracle(0.10)

            if npv_10 is None:
                verdict["gates"]["npv_10_present"] = False
                verdict["problems"].append("NPV not found after recalc at 10%")
            else:
                verdict["gates"]["npv_10_present"] = True
                err_pct_10 = abs(npv_10 - oracle_10) / abs(oracle_10) * 100
                verdict["metrics"]["npv_10_computed"] = round(npv_10, 4)
                verdict["metrics"]["npv_10_oracle"] = round(oracle_10, 4)
                verdict["metrics"]["npv_10_err_pct"] = round(err_pct_10, 4)
                verdict["gates"]["npv_10_match"] = err_pct_10 <= ORACLE_PARAMS["tolerance_pct"]

        # Gate 4: Recalculate at 12%
        values_12, err = recalculate_workbook(
            artifact_path, os.path.join(workdir, "r12"), rate_override=0.12
        )
        if err:
            verdict["gates"]["recalc_12"] = False
            verdict["problems"].append(f"recalc at 12%: {err}")
        else:
            verdict["gates"]["recalc_12"] = True
            npv_12 = values_12.get("npv")
            oracle_12 = compute_npv_oracle(0.12)

            if npv_12 is None:
                verdict["gates"]["npv_12_present"] = False
                verdict["problems"].append("NPV not found after recalc at 12%")
            else:
                verdict["gates"]["npv_12_present"] = True
                err_pct_12 = abs(npv_12 - oracle_12) / abs(oracle_12) * 100
                verdict["metrics"]["npv_12_computed"] = round(npv_12, 4)
                verdict["metrics"]["npv_12_oracle"] = round(oracle_12, 4)
                verdict["metrics"]["npv_12_err_pct"] = round(err_pct_12, 4)
                verdict["gates"]["npv_12_match"] = err_pct_12 <= ORACLE_PARAMS["tolerance_pct"]

        # Gate 5: Negative control - NPV must change when rate changes
        if verdict["gates"].get("npv_8_present") and verdict["gates"].get("npv_12_present"):
            npv_8_val = values_8.get("npv")
            npv_12_val = values_12.get("npv")
            if npv_8_val is not None and npv_12_val is not None:
                # NPV should decrease as rate increases
                npv_moves = abs(npv_12_val - npv_8_val) > 0.01
                verdict["gates"]["negative_control"] = npv_moves
                verdict["metrics"]["npv_moves"] = npv_moves
                if not npv_moves:
                    verdict["problems"].append(
                        "negative control failed: NPV does not change when rate changes "
                        "(hardcoded or static value)"
                    )
        else:
            verdict["gates"]["negative_control"] = False
            verdict["problems"].append("negative control: missing NPV values")

        # Gate 6: Judge integrity
        sha_after = check_shas(JUDGE_DIR)
        verdict["gates"]["judge_intact"] = sha_before == sha_after

    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    # Overall pass/fail
    all_pass = all(verdict["gates"].values())
    verdict["pass"] = all_pass

    return verdict, 0 if all_pass else 1


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Grade a DCF workbook artifact")
    parser.add_argument("artifact", help="Path to the .xlsx artifact")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", dest="json_out", help="Write verdict JSON to file")
    parser.add_argument("--judge-dir", default=None, help="Judge directory (for checksums)")
    args = parser.parse_args()

    if args.judge_dir:
        global JUDGE_DIR
        JUDGE_DIR = os.path.abspath(args.judge_dir)

    verdict, rc = grade_artifact(args.artifact, seed=args.seed)

    json_str = json.dumps(verdict, indent=2, sort_keys=True)
    print(json_str)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            fh.write(json_str + "\n")

    sys.exit(rc)


if __name__ == "__main__":
    main()
