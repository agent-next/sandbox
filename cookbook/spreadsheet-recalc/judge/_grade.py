"""Judge core for spreadsheet-recalc demo.

Validates a DCF workbook artifact by:
1. Structure check (sheets present, computed cells are live formulas, no
   hardcoded NPV literal)
2. LibreOffice headless recalculation at 8%, 10%, 12% discount rates
3. Closed-form DCF oracle comparison at each rate (reference parameters)
4. Negative control (NPV must move when the discount rate changes)
5. Judge integrity (checksums before/after)

The oracle is the closed-form DCF over the reference parameters (the good
workbook's inputs): NPV(r) = I + sum_t FCF_t / (1+r)^t. The judge compares
the workbook's recalculated NPV against this closed form, so a workbook
whose formulas implement the discounting correctly passes regardless of the
rate written into Assumptions!B3, and a hardcoded or static NPV fails.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import openpyxl

JUDGE_DIR = os.path.dirname(os.path.abspath(__file__))

# Reference DCF parameters (the good workbook's inputs). The closed-form
# oracle is exact for these; see SPEC.md.
ORACLE_PARAMS = {
    "initial_investment": -10000,
    "cash_flows": [4000.0, 5000.0, 6000.0],  # years 1..3 (NOPAT from good model)
    "discount_rates": [0.08, 0.10, 0.12],
    "tolerance_pct": 0.5,        # NPV vs closed form, relative
    "move_tolerance_pct": 1.0,   # negative control, relative change
    "hardcode_tolerance_pct": 2.0,  # literal vs oracle, relative
}
MAX_BYTES = 5 * 1024 * 1024  # 5 MiB artifact size limit
RUN_TIMEOUT_S = 120           # 2 minutes per LibreOffice recalc
REQUIRED_SHEETS = {"Assumptions", "Projections", "Valuation"}


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


def npv_oracle(rate):
    """Closed-form reference NPV at a discount rate."""
    npv = ORACLE_PARAMS["initial_investment"]
    for t, cf in enumerate(ORACLE_PARAMS["cash_flows"], start=1):
        npv += cf / (1.0 + rate) ** t
    return npv


def _strip_cell_refs(formula):
    """Remove cell references (I3, B2, $B$3) from a formula string."""
    return re.sub(r"\$?[A-Za-z]+\$?\d+", "", formula)


def _numeric_literals(text):
    """Extract standalone numeric literals from a formula string."""
    stripped = _strip_cell_refs(text)
    return [float(m) for m in re.findall(r"-?\d+\.?\d*", stripped)]


def _is_formula(value):
    return isinstance(value, str) and value.startswith("=")


def load_artifact(artifact_path):
    """Load and validate artifact structure. Returns (workbook, problems)."""
    problems = []

    size = os.path.getsize(artifact_path)
    if size > MAX_BYTES:
        problems.append(f"artifact size {size} exceeds {MAX_BYTES} bytes")

    try:
        wb = openpyxl.load_workbook(artifact_path, data_only=False)
    except Exception as e:
        return None, [f"cannot load xlsx: {e}"]

    missing = REQUIRED_SHEETS - set(wb.sheetnames)
    if missing:
        problems.append(f"missing sheets: {sorted(missing)}")

    # Valuation!B2 (NPV) must be a formula, not a literal.
    try:
        b2 = wb["Valuation"]["B2"].value
        if not _is_formula(b2):
            problems.append("Valuation!B2 (NPV) is not a formula")
    except Exception:
        problems.append("Valuation!B2 (NPV) is missing")

    # Projections!I3 (PV of FCF, year 1) must be a formula.
    try:
        i3 = wb["Projections"]["I3"].value
        if not _is_formula(i3):
            problems.append("Projections!I3 (PV of FCF) is not a formula")
    except Exception:
        problems.append("Projections!I3 (PV of FCF) is missing")

    # Assumptions!B3 (discount rate) must be numeric.
    try:
        b3 = wb["Assumptions"]["B3"].value
        if not isinstance(b3, (int, float)):
            problems.append("Assumptions!B3 (discount rate) is not numeric")
    except Exception:
        problems.append("Assumptions!B3 (discount rate) is missing")

    # Hardcode detection: a numeric literal in the NPV formula that matches
    # the oracle NPV at the base rate means the "formula" is a constant.
    if not problems:
        try:
            b2_val = wb["Valuation"]["B2"].value
            if _is_formula(b2_val):
                oracle_8 = npv_oracle(0.08)
                for lit in _numeric_literals(b2_val):
                    if abs(lit - oracle_8) / abs(oracle_8) * 100 < ORACLE_PARAMS["hardcode_tolerance_pct"]:
                        problems.append(
                            f"Valuation!B2 contains hardcoded NPV literal {lit} "
                            f"(within {ORACLE_PARAMS['hardcode_tolerance_pct']}% of oracle {oracle_8:.2f})"
                        )
                        break
        except Exception:
            pass  # hardcode check is best-effort; structural errors already caught

    return wb, problems


def recalculate_at_rate(artifact_path, workdir, rate):
    """Recalculate the workbook at a discount rate via LibreOffice headless.

    Writes the rate into Assumptions!B3 of a working copy, converts to xlsx
    (which forces a recalculation because openpyxl writes formulas with no
    cached values), and reads the computed NPV back. Returns (npv, error).
    """
    os.makedirs(workdir, exist_ok=True)
    local_copy = os.path.join(workdir, "model.xlsx")
    shutil.copy(artifact_path, local_copy)

    wb = openpyxl.load_workbook(local_copy)
    wb["Assumptions"]["B3"] = rate
    wb.save(local_copy)

    outdir = os.path.join(workdir, "out")
    os.makedirs(outdir, exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = workdir  # isolate the LibreOffice profile

    proc = subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "xlsx",
         "--outdir", outdir, local_copy],
        capture_output=True, text=True, timeout=RUN_TIMEOUT_S, env=env,
        cwd=workdir,
    )
    if proc.returncode != 0:
        return None, f"LibreOffice exit {proc.returncode}: {proc.stderr.strip()[:200]}"

    result_path = os.path.join(outdir, "model.xlsx")
    if not os.path.exists(result_path):
        return None, "LibreOffice did not produce output file"

    wb_out = openpyxl.load_workbook(result_path, data_only=True)
    try:
        npv = float(wb_out["Valuation"]["B2"].value)
    except Exception:
        return None, "Valuation!B2 has no computed value after recalc"
    return npv, None


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
            verdict["gates"]["recalc"] = False
            verdict["gates"]["oracle"] = False
            verdict["gates"]["negative_control"] = False
            verdict["gates"]["judge_intact"] = check_shas(JUDGE_DIR) == sha_before
            verdict["pass"] = False
            return verdict, 1

        # Gate 2: recalculate at all three rates (parallel, isolated HOME)
        npvs = {}
        errors = {}

        def _recalc(rate):
            rd = os.path.join(workdir, f"r{int(round(rate * 100))}")
            return rate, recalculate_at_rate(artifact_path, rd, rate)

        with ThreadPoolExecutor(max_workers=3) as pool:
            for rate, (npv, err) in pool.map(_recalc, ORACLE_PARAMS["discount_rates"]):
                if err:
                    errors[rate] = err
                else:
                    npvs[rate] = npv

        verdict["gates"]["recalc"] = len(errors) == 0
        for rate, err in errors.items():
            verdict["problems"].append(f"recalc at {rate:.0%}: {err}")

        # Gate 3: oracle — each NPV vs the closed form
        oracle_ok = len(errors) == 0
        for rate in ORACLE_PARAMS["discount_rates"]:
            if rate not in npvs:
                oracle_ok = False
                continue
            npv_computed = npvs[rate]
            npv_ref = npv_oracle(rate)
            err_pct = abs(npv_computed - npv_ref) / abs(npv_ref) * 100
            verdict["metrics"][f"npv_{int(round(rate * 100))}_computed"] = round(npv_computed, 4)
            verdict["metrics"][f"npv_{int(round(rate * 100))}_oracle"] = round(npv_ref, 4)
            verdict["metrics"][f"npv_{int(round(rate * 100))}_err_pct"] = round(err_pct, 4)
            if err_pct > ORACLE_PARAMS["tolerance_pct"]:
                oracle_ok = False
                verdict["problems"].append(
                    f"oracle at {rate:.0%}: NPV {npv_computed:.4f} vs "
                    f"closed-form {npv_ref:.4f} (err {err_pct:.2f}% > "
                    f"{ORACLE_PARAMS['tolerance_pct']}%)"
                )
        verdict["gates"]["oracle"] = oracle_ok

        # Gate 4: negative control — NPV must move when the rate changes
        if 0.08 in npvs and 0.12 in npvs:
            npv_8, npv_12 = npvs[0.08], npvs[0.12]
            move_pct = abs(npv_12 - npv_8) / abs(npv_8) * 100
            verdict["metrics"]["negative_control_move_pct"] = round(move_pct, 4)
            verdict["gates"]["negative_control"] = (
                move_pct >= ORACLE_PARAMS["move_tolerance_pct"]
            )
            if move_pct < ORACLE_PARAMS["move_tolerance_pct"]:
                verdict["problems"].append(
                    f"negative control: NPV moved only {move_pct:.2f}% "
                    f"(< {ORACLE_PARAMS['move_tolerance_pct']}%) — hardcoded or static value"
                )
        else:
            verdict["gates"]["negative_control"] = False
            verdict["problems"].append("negative control: missing NPV values")

        # Gate 5: judge integrity
        sha_after = check_shas(JUDGE_DIR)
        verdict["gates"]["judge_intact"] = sha_before == sha_after

    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    verdict["pass"] = all(verdict["gates"].values())
    return verdict, 0 if verdict["pass"] else 1


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
