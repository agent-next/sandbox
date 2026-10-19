#!/usr/bin/env python3
"""Judge for cookbook/climate-glacier-model.

Stdlib only, deliberately: the artifact uses numpy + matplotlib, so the
oracle must not share a library with it -- a numpy version difference can
never move a verdict.  Every number below is pure-float Python.

    glacier_judge.py <artifact-dir> [--seed N] [--json out.json]
                     [--python PATH]

Prints one JSON verdict; exits 0 only if every gate passes.
"""

from __future__ import annotations

import argparse
import ast
import json
import hashlib
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

# --- SPEC constants (normative; duplicated from SPEC.md on purpose so the
#     oracle is derived here and not read from the artifact) -------------
Z_HEAD = 3500.0
SLOPE = 0.08
H0 = 650.0
DH = 0.02
W = 800.0
ELA0 = 2900.0
KAPPA = 200.0
TAU = 10.0
DX = 25.0
NX = 800
YEARS = 100

SCENARIOS = (("warm_2p0", 2.0), ("warm_2p4", 2.4), ("warm_2p8", 2.8))

L0 = 2.0 * (Z_HEAD - ELA0) / SLOPE
X = [(i + 0.5) * DX for i in range(NX)]
H = [H0 - DH * x for x in X]
V0_MASK = W * sum(h for x, h in zip(X, H) if x < L0) * DX / 1e9
# Continuum volume at L0; the cell-centre mask sum equals it to <0.4 %.
V0_CONT = W * (H0 * L0 - DH * L0 * L0 / 2.0) / 1e9

ALLOWED_IMPORTS = {"numpy", "matplotlib", "csv", "json", "math", "os",
                   "sys", "argparse"}
RUN_TIMEOUT_S = 300.0

# Tolerances (SPEC.md "Judge gates")
TOL_ZERO_MELT = 1e-9     # relative
TOL_CROSSING_Y = 3.0     # years
TOL_FINAL_REL = 0.02     # 2 %
TOL_SHAPE_REL = 0.02     # 2 %
TOL_MASK_CELLS = 1.0     # one cell of slack for the mask-consistency check
MIN_PNG_BYTES = 20_000
MIN_PNG_WIDTH = 900
MIN_PNG_DPI = 150


# --- analytic reference -------------------------------------------------
def l_exact(t: float, a2: float) -> float:
    """Closed-form solution of the yearly recurrence (SPEC.md):

    L_exact(t) = L0 - (2*KAPPA/SLOPE)*a2*(t/YEARS - (TAU/YEARS)*(1-e^-t/TAU))
    """
    c = (2.0 * KAPPA / SLOPE) * a2
    return L0 - c * (t / YEARS - (TAU / YEARS) * (1.0 - math.exp(-t / TAU)))


def v_exact(t: float, a2: float) -> float:
    """Continuum volume at time t (km^3)."""
    length = l_exact(t, a2)
    return W * (H0 * length - DH * length * length / 2.0) / 1e9


def crossing_exact(a2: float) -> float | None:
    """First t with V_exact(t) <= 0.5*V_exact(0), by bisection, else None."""
    target = 0.5 * V0_CONT
    if v_exact(float(YEARS), a2) > target:
        return None
    lo, hi = 0.0, float(YEARS)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if v_exact(mid, a2) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def mask_volume(n_cells: int) -> float:
    """Mask-sum volume of the first `n_cells` ice cells (km^3)."""
    return W * sum(H[:n_cells]) * DX / 1e9


def cells_for_volume(volume: float) -> int | None:
    """Invert the mask sum: the n with mask_volume(n) == volume."""
    best_n, best_err = None, None
    for n in range(NX + 1):
        err = abs(mask_volume(n) - volume)
        if best_err is None or err < best_err:
            best_n, best_err = n, err
    # Require a real match, not merely the nearest of 801 candidates.
    if best_err is None or best_err > 1e-6 * max(volume, 1.0):
        return None
    return best_n


# --- helpers ------------------------------------------------------------
def rel(a: float, b: float) -> float:
    """Relative difference, safe when b == 0."""
    return abs(a - b) / abs(b) if b else abs(a - b)


def read_csv(path: str) -> dict[str, dict[int, float]]:
    """Parse volumes.csv -> {scenario: {year: volume}} or raise ValueError."""
    with open(path, newline="") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    if not lines:
        raise ValueError("volumes.csv is empty")
    header = [c.strip() for c in lines[0].split(",")]
    if header != ["scenario", "year", "volume_km3"]:
        raise ValueError(f"volumes.csv header is {header!r}, expected "
                         "['scenario', 'year', 'volume_km3']")
    out: dict[str, dict[int, float]] = {}
    for lineno, line in enumerate(lines[1:], start=2):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            raise ValueError(f"volumes.csv line {lineno}: expected 3 fields, "
                             f"got {len(parts)}")
        name, year_s, vol_s = parts
        try:
            year = int(year_s)
        except ValueError as exc:
            raise ValueError(f"volumes.csv line {lineno}: year {year_s!r} is "
                             "not an integer") from exc
        try:
            volume = float(vol_s)
        except ValueError as exc:
            raise ValueError(f"volumes.csv line {lineno}: volume {vol_s!r} "
                             "is not a number") from exc
        if not math.isfinite(volume):
            raise ValueError(f"volumes.csv line {lineno}: volume {vol_s!r} "
                             "is not finite")
        if volume < 0.0:
            raise ValueError(f"volumes.csv line {lineno}: volume {volume} is "
                             "negative")
        column = out.setdefault(name, {})
        if year in column:
            raise ValueError(f"volumes.csv line {lineno}: duplicate row for "
                             f"({name}, {year})")
        column[year] = volume
    return out


def png_info(path: str) -> tuple[int, int, float]:
    """(width, height, dpi) from the PNG header + pHYs chunk."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file (bad signature)")
    width, height = struct.unpack(">II", data[16:24])
    dpi = 0.0
    pos = 8
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if ctype == b"pHYs" and length >= 9:
            px, py, unit = struct.unpack(">IIB", body[:9])
            if unit == 1 and px and py:  # metres -> dpi
                dpi = px * 0.0254
        pos += 12 + length
        if ctype == b"IDAT":
            break
    return width, height, dpi


def check_imports(path: str) -> list[str]:
    """Top-level module names imported by `path` (relative import -> '.').

    Raises SyntaxError on an unparsable artifact; the caller turns that into
    a failed gate rather than a traceback.
    """
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            names.append("." if node.level else (node.module or "").split(".")[0])
    return names


class Verdict:
    def __init__(self) -> None:
        self.gates: dict[str, dict] = {}
        self.order: list[str] = []

    def add(self, name: str, passed: bool, detail: dict | None = None,
            **extra) -> None:
        self.gates[name] = {"passed": passed, **(detail or {}), **extra}
        self.order.append(name)

    def first_failure(self) -> tuple[str, str] | None:
        for name in self.order:
            gate = self.gates[name]
            if not gate["passed"]:
                return name, gate.get("reason", "gate failed")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--json")
    ap.add_argument("--python", default=os.environ.get(
        "GLACIER_PYTHON", os.path.expanduser("~/glacier-venv/bin/python")))
    args = ap.parse_args()

    started = time.monotonic()
    verdict = Verdict()
    timings: dict[str, float] = {}
    verdict.add("_meta", True, artifact=args.artifact, seed=args.seed,
                python=args.python,
                spec_constants={"L0": L0, "V0_mask_km3": V0_MASK,
                                "V0_continuum_km3": V0_CONT})

    model = os.path.abspath(os.path.join(args.artifact, "model.py"))
    if not os.path.isfile(model):
        verdict.add("artifact", False, reason=f"{model} does not exist")
        return emit(verdict, args, started, timings)

    # G1: compiles, imports nothing outside the allow-list, runs cleanly.
    try:
        imports = check_imports(model)
    except (SyntaxError, OSError) as exc:
        verdict.add("artifact", False,
                    reason=f"model.py does not parse: {exc}")
        return emit(verdict, args, started, timings)
    bad_imports = sorted({n for n in imports
                          if n and n not in ALLOWED_IMPORTS})
    if bad_imports:
        verdict.add("artifact", False,
                    reason=f"model.py imports {bad_imports}, outside the "
                           f"allow-list {sorted(ALLOWED_IMPORTS)}")
        return emit(verdict, args, started, timings)

    if not os.path.isfile(args.python):
        verdict.add("artifact", False,
                    reason=f"python interpreter {args.python} not found; run "
                           "judge/setup.sh first")
        return emit(verdict, args, started, timings)

    work = tempfile.mkdtemp(prefix="glacier-judge-")
    try:
        # The artifact is copied before it is run: it never touches its own
        # directory (SPEC.md judge-integrity rule), and self_writes below
        # reports it if it tries.
        artifact_copy = os.path.join(work, "artifact")
        os.makedirs(artifact_copy)
        model_copy = os.path.join(artifact_copy, "model.py")
        shutil.copyfile(model, model_copy)
        before_self = sha256(model_copy)

        run_a = os.path.join(work, "run-a")
        run_b = os.path.join(work, "run-b")
        zero = os.path.join(work, "zero-melt")
        for d in (run_a, run_b, zero):
            os.makedirs(d)

        rc, out, err, secs = run_model(args.python, model_copy, run_a,
                                       args.seed)
        self_writes = [] if sha256(model_copy) == before_self else \
            ["model.py"]
        if rc != 0:
            verdict.add("artifact", False,
                        reason=f"model.py exited {rc}: {tail(err or out)}")
            timings["first_run_seconds"] = round(secs, 2)
            return emit(verdict, args, started, timings)
        missing = [f for f in ("volumes.csv", "crossings.json", "retreat.png",
                               "run.json")
                   if not os.path.isfile(os.path.join(run_a, f))]
        strays = strays_in(run_a)
        if missing or strays or self_writes:
            reason = (f"model.py did not write {missing}" if missing else
                      "model.py wrote outside --out: " +
                      ", ".join(strays or self_writes))
            verdict.add("artifact", False, reason=reason)
            timings["first_run_seconds"] = round(secs, 2)
            return emit(verdict, args, started, timings)

        try:
            table = read_csv(os.path.join(run_a, "volumes.csv"))
        except ValueError as exc:
            verdict.add("artifact", False, reason=f"volumes.csv: {exc}")
            return emit(verdict, args, started, timings)

        # Exactly one row per (scenario, year) pair.
        expected = {(n, y) for n, _ in SCENARIOS for y in range(YEARS + 1)}
        seen = {(n, y) for n, col in table.items() for y in col}
        if seen != expected:
            extra = sorted(seen - expected)[:4]
            absent = sorted(expected - seen)[:4]
            verdict.add("artifact", False,
                        reason=f"volumes.csv rows do not match the expected "
                               f"{len(expected)} (scenario, year) pairs; "
                               f"unexpected={extra} missing={absent}")
            return emit(verdict, args, started, timings)
        verdict.add("artifact", True, rows=len(seen))
        timings["first_run_seconds"] = round(secs, 2)

        # G2: same seed twice -> byte-identical data outputs.
        rc2, out2, err2, secs2 = run_model(args.python, model, run_b, args.seed)
        if rc2 != 0:
            verdict.add("determinism", False,
                        reason=f"second run exited {rc2}: {tail(err2 or out2)}")
        else:
            same = all(files_equal(os.path.join(run_a, f),
                                   os.path.join(run_b, f))
                       for f in ("volumes.csv", "crossings.json"))
            verdict.add("determinism", same,
                        reason=None if same else
                        "two runs with the same seed differ in volumes.csv "
                        "or crossings.json")
            timings["second_run_seconds"] = round(secs2, 2)

        # G3: zero-melt negative control.
        rc3, out3, err3, secs3 = run_model(args.python, model, zero,
                                           args.seed, zero_melt=True)
        if rc3 != 0:
            verdict.add("zero_melt", False,
                        reason=f"model.py --zero-melt exited {rc3}: "
                               f"{tail(err3 or out3)}")
        else:
            verdict.add("zero_melt", *zero_melt_gate(zero, table))
            timings["zero_melt_seconds"] = round(secs3, 2)

        # G4/G5/G6: analytic comparison, mask consistency, monotonicity.
        crossing_detail = crossing_gate(table, run_a)
        verdict.add("crossing", *crossing_detail)
        verdict.add("final_volume", *final_volume_gate(table))
        verdict.add("shape", *shape_gate(table))

        # G7: the figure.
        verdict.add("figure", *figure_gate(run_a))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return emit(verdict, args, started, timings)


def run_model(python: str, model: str, outdir: str, seed: int,
              zero_melt: bool = False):
    """Run the artifact with cwd set to an empty dir of its own.

    The cwd is deliberately *not* the output directory: SPEC.md says the
    artifact writes only inside `--out`, so anything left in the cwd is a
    stray write and `strays_in` reports it.
    """
    cwd = outdir + "-cwd"
    os.makedirs(cwd, exist_ok=True)
    cmd = [python, "-I", model, "--out", outdir, "--seed", str(seed)]
    if zero_melt:
        cmd.append("--zero-melt")
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=RUN_TIMEOUT_S, cwd=cwd)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {RUN_TIMEOUT_S:.0f}s", \
            time.monotonic() - started
    return proc.returncode, proc.stdout, proc.stderr, \
        time.monotonic() - started


def sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def strays_in(outdir: str) -> list[str]:
    """Files left in the artifact's cwd (it should write only to --out)."""
    cwd = outdir + "-cwd"
    if not os.path.isdir(cwd):
        return []
    return sorted(os.listdir(cwd))


def files_equal(a: str, b: str) -> bool:
    if not (os.path.isfile(a) and os.path.isfile(b)):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def zero_melt_gate(outdir: str, warm_table) -> tuple[bool, dict]:
    try:
        table = read_csv(os.path.join(outdir, "volumes.csv"))
    except ValueError as exc:
        return False, {"reason": f"zero-melt volumes.csv: {exc}"}
    try:
        with open(os.path.join(outdir, "crossings.json")) as fh:
            crossings = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return False, {"reason": f"zero-melt crossings.json unreadable: {exc}"}

    worst_name, worst = None, 0.0
    for name, _ in SCENARIOS:
        if name not in table:
            return False, {"reason": f"zero-melt CSV has no scenario {name!r}"}
        col = table[name]
        v0 = col.get(0)
        if v0 is None:
            return False, {"reason": f"zero-melt CSV has no year 0 for {name}"}
        for year in range(YEARS + 1):
            volume = col.get(year)
            if volume is None:
                return False, {"reason": f"zero-melt CSV missing {name} "
                                         f"year {year}"}
            deviation = rel(volume, v0)
            if deviation > worst:
                worst, worst_name = deviation, f"{name}@{year}"
    not_crossed = {n: crossings.get(n, {}).get("year") for n, _ in SCENARIOS}
    reported = {n: y for n, y in not_crossed.items() if y is not None}
    passed = worst <= TOL_ZERO_MELT and not reported
    detail = {"worst_relative_deviation": worst, "worst_at": worst_name,
              "reported_crossings": reported,
              "tolerance_relative": TOL_ZERO_MELT}
    if not passed:
        detail["reason"] = (
            f"a zero-melt (balanced) glacier lost mass: worst relative "
            f"deviation from V(0) is {worst:.3e} at {worst_name} "
            f"(tolerance {TOL_ZERO_MELT:.0e})"
            + (f"; it also reported crossing years {reported} for a glacier "
               "that never loses mass" if reported else ""))
    return passed, detail


def crossing_gate(table, run_dir: str) -> tuple[bool, dict]:
    """G4: the crossing year the artifact *reports* vs. the analytic root.

    The artifact reports it in crossings.json; the CSV is checked to agree,
    so a stale or invented JSON value cannot pass while the data says
    otherwise.
    """
    try:
        with open(os.path.join(run_dir, "crossings.json")) as fh:
            reported_json = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return False, {"reason": f"crossings.json unreadable: {exc}"}
    if not isinstance(reported_json, dict):
        return False, {"reason": "crossings.json is not a JSON object"}

    detail: dict = {"tolerance_years": TOL_CROSSING_Y, "scenarios": {}}
    ok = True
    reasons = []
    for name, a2 in SCENARIOS:
        reference = crossing_exact(a2)
        entry_json = reported_json.get(name)
        if not isinstance(entry_json, dict) or "year" not in entry_json:
            ok = False
            reasons.append(f"crossings.json has no {{'year': ...}} entry for "
                           f"{name} (got {entry_json!r})")
            detail["scenarios"][name] = {"reference_year": reference,
                                         "reported_year": None,
                                         "passed": False}
            continue
        reported = entry_json["year"]
        if reported is not None and not isinstance(reported, (int, float)):
            ok = False
            reasons.append(f"crossings.json {name} year is {reported!r}, "
                           "expected a number or null")
            reported = None
        from_csv = reported_crossing(table, name)
        entry = {"reference_year": reference, "reported_year": reported,
                 "csv_year": from_csv}

        if reference is None:
            entry["passed"] = reported is None and from_csv is None
            if reported is not None or from_csv is not None:
                ok = False
                reasons.append(
                    f"{name} reports a crossing (json {reported}, csv "
                    f"{from_csv}) but the analytic reference never crosses")
        elif reported is None:
            entry["passed"] = False
            ok = False
            reasons.append(f"{name} reported no crossing but the analytic "
                           f"reference crosses at year {reference:.3f}")
        else:
            entry["deviation_years"] = reported - reference
            entry["csv_deviation_years"] = (None if from_csv is None
                                            else from_csv - reference)
            entry["passed"] = abs(reported - reference) <= TOL_CROSSING_Y and \
                from_csv is not None and \
                abs(from_csv - reference) <= TOL_CROSSING_Y
            if abs(reported - reference) > TOL_CROSSING_Y:
                ok = False
                reasons.append(
                    f"{name} crossing year {reported:.3f} is "
                    f"{entry['deviation_years']:+.3f} yr from the analytic "
                    f"{reference:.3f} (tolerance ±{TOL_CROSSING_Y:g})")
            if from_csv is None or abs(from_csv - reference) > TOL_CROSSING_Y:
                ok = False
                reasons.append(
                    f"{name}: the CSV implies crossing year {from_csv}, "
                    f"{'which disagrees with' if from_csv is not None else ''} "
                    f"the analytic {reference:.3f} and the reported "
                    f"{reported} (tolerance ±{TOL_CROSSING_Y:g})")
        detail["scenarios"][name] = entry
    if not ok:
        detail["reason"] = "; ".join(reasons)
    return ok, detail


def reported_crossing(table, name: str) -> float | None:
    """Crossing year implied by the CSV itself (independent of the JSON)."""
    col = table[name]
    v0 = col[0]
    target = 0.5 * v0
    for year in range(YEARS):
        a, b = col[year], col[year + 1]
        if b <= target:
            span = a - b
            return float(year) + ((a - target) / span if span > 0 else 0.0)
    return None


def final_volume_gate(table) -> tuple[bool, dict]:
    detail: dict = {"tolerance_relative": TOL_FINAL_REL, "scenarios": {}}
    ok = True
    reasons = []
    for name, a2 in SCENARIOS:
        got = table[name][YEARS]
        want = v_exact(float(YEARS), a2)
        deviation = rel(got, want)
        entry = {"measured_km3": got, "reference_km3": want,
                 "relative_deviation": deviation,
                 "passed": deviation <= TOL_FINAL_REL}
        if not entry["passed"]:
            ok = False
            reasons.append(f"{name} V(100) = {got:.4f} km3, analytic "
                           f"{want:.4f} km3 ({deviation:.2%} off, tolerance "
                           f"{TOL_FINAL_REL:.0%})")
        detail["scenarios"][name] = entry
    if not ok:
        detail["reason"] = "; ".join(reasons)
    return ok, detail


def shape_gate(table) -> tuple[bool, dict]:
    detail: dict = {"tolerance_relative": TOL_SHAPE_REL, "scenarios": {}}
    ok = True
    reasons = []
    for name, a2 in SCENARIOS:
        col = table[name]
        worst_year, worst = None, 0.0
        rises = []
        for year in range(YEARS + 1):
            deviation = rel(col[year], v_exact(float(year), a2))
            if deviation > worst:
                worst, worst_year = deviation, year
            if year and col[year] > col[year - 1]:
                rises.append(year)
        # Mask consistency: the CSV volume must be the mask sum of some
        # whole number of ice cells, and that count must match the
        # analytic length to within one cell.
        mask_cells = cells_for_volume(col[YEARS])
        want_cells = math.ceil(l_exact(float(YEARS), a2) / DX)
        cell_ok = mask_cells is not None and \
            abs(mask_cells - want_cells) <= TOL_MASK_CELLS
        entry = {"worst_relative_deviation": worst, "worst_year": worst_year,
                 "increases_at_years": rises, "mask_cells": mask_cells,
                 "reference_cells": want_cells,
                 "passed": (worst <= TOL_SHAPE_REL and not rises and cell_ok)}
        if worst > TOL_SHAPE_REL:
            ok = False
            reasons.append(f"{name} deviates {worst:.2%} from the analytic "
                           f"volume at year {worst_year} (tolerance "
                           f"{TOL_SHAPE_REL:.0%})")
        if rises:
            ok = False
            reasons.append(f"{name} volume rises at years {rises[:4]} under "
                           "a warming scenario")
        if not cell_ok:
            ok = False
            reasons.append(
                f"{name} V(100) = {col[YEARS]:.6f} km3 is not the mask sum of "
                f"any whole cell count near the analytic "
                f"{want_cells} cells (got {mask_cells})")
        detail["scenarios"][name] = entry
    if not ok:
        detail["reason"] = "; ".join(reasons)
    return ok, detail


def figure_gate(outdir: str) -> tuple[bool, dict]:
    path = os.path.join(outdir, "retreat.png")
    size = os.path.getsize(path)
    try:
        width, height, dpi = png_info(path)
    except (ValueError, struct.error) as exc:
        return False, {"reason": f"retreat.png is not a readable PNG: {exc}"}
    try:
        with open(os.path.join(outdir, "run.json")) as fh:
            run = json.load(fh)
        legend = run.get("legend")
    except (OSError, json.JSONDecodeError) as exc:
        return False, {"reason": f"run.json unreadable: {exc}"}
    names = [n for n, _ in SCENARIOS]
    if not isinstance(legend, list) or \
            sorted(str(x) for x in legend) != sorted(names):
        return False, {"reason": f"run.json legend is {legend!r}, expected "
                                 f"the three scenario names {names}"}
    problems = []
    if width < MIN_PNG_WIDTH:
        problems.append(f"width {width}px < {MIN_PNG_WIDTH}px")
    if dpi < MIN_PNG_DPI:
        problems.append(f"dpi {dpi:.1f} < {MIN_PNG_DPI}")
    if size < MIN_PNG_BYTES:
        problems.append(f"{size} bytes < {MIN_PNG_BYTES} (empty plot?)")
    detail = {"width_px": width, "height_px": height, "dpi": round(dpi, 1),
              "bytes": size, "legend": legend,
              "note": "the judge checks the PNG header and run.json, not the "
                      "pixels: it does not OCR the plot"}
    if problems:
        detail["reason"] = "retreat.png " + "; ".join(problems)
        return False, detail
    return True, detail


def tail(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    return text[-limit:] if text else "(no output)"


def emit(verdict: Verdict, args, started: float,
         timings: dict[str, float] | None = None) -> int:
    failure = verdict.first_failure()
    doc = {
        "artifact": args.artifact,
        "seed": args.seed,
        "passed": failure is None,
        "gates": verdict.gates,
        "timing": {"total_seconds": round(time.monotonic() - started, 2),
                   **(timings or {})},
    }
    if failure is not None:
        doc["failed_gate"] = failure[0]
        doc["reason"] = failure[1]
    text = json.dumps(doc, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if failure is None else 1


if __name__ == "__main__":
    sys.exit(main())
