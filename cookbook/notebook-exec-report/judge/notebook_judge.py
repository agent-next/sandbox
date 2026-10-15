#!/usr/bin/env python3
"""notebook-exec-report judge engine, called by judge/grade.sh.

Gates per SPEC.md:
  G1 execution    nbclient runs the notebook on a clean kernel, allow_errors
                   False, and every code cell's execution_count is exactly
                   its 1-based position (no re-runs, no out-of-order cells)
  G2 determinism  two executions from two different working directories
                   agree on rmse_test (1e-12) and on every figure digest
  G3 figures      >= 3 distinct image/png outputs, each >= 8 kB, and
                   report.html references every figure file
  G4 oracle       the reported rmse_test / rmse_train / r2_test / n_train /
                   n_test match an independent stdlib refit of the SPEC
                   pipeline (Gaussian elimination; no scikit-learn, no BLAS)
  G5 accuracy     the refit's rmse_test is <= 0.3040 (noise floor 0.30)
  G6 report       report.html parses, carries every metric key and value,
                   embeds all figures, and holds no traceback text
  G7 integrity    the judge tree's sha256 is unchanged and the notebook
                   references no judge/ path

Prints one JSON verdict; exits 0 only if every gate passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

JDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(JDIR))
import oracle  # noqa: E402

FIG_MIN_BYTES = 8 * 1024
FIG_MIN_COUNT = 3
RMSE_TEST_MAX = 0.3040
ORACLE_TOL_RMSE = 1e-6
ORACLE_TOL_R2 = 1e-9
BLIND_MEDIAN_FACTOR = 1.25
RECOVERY_MAX = 0.05
BLIND_SEEDS = (1, 2, 3, 4, 5)
DET_TOL = 1e-12


class GateFailure(Exception):
    def __init__(self, gate: str, reason: str, detail: dict | None = None):
        super().__init__(reason)
        self.gate = gate
        self.reason = reason
        self.detail = detail or {}


# --- notebook execution ----------------------------------------------------
def run_notebook(dest: Path, nb_path: Path) -> dict:
    """Execute one notebook copy in `dest` on a fresh kernel; return the
    parsed metrics plus the executed notebook and figure digests."""
    from nbclient import NotebookClient
    from nbformat import read

    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(nb_path, dest / "analysis.ipynb")
    # the dataset sits next to the artifact; the notebook writes its outputs
    # to _out/ next to itself, which is where the judge looks for them.
    shutil.copy2(nb_path.parent / "dataset.csv", dest / "dataset.csv")

    nb = read(str(dest / "analysis.ipynb"), as_version=4)
    code_cells = [c for c in nb.cells if c.cell_type == "code"]
    for position, cell in enumerate(code_cells, start=1):
        if cell.get("execution_count") is not None:
            raise GateFailure(
                "execution", "artifact ships an already-executed notebook; a "
                             "clean re-run is required",
                {"cell": position, "execution_count": cell["execution_count"]})
        tags = cell.get("metadata", {}).get("tags", [])
        if "metrics" in tags and tags != ["metrics"]:
            raise GateFailure("execution",
                              "metrics tag must stand alone", {"tags": tags})

    client = NotebookClient(nb, timeout=900, kernel_name="python3",
                            allow_errors=False,
                            resources={"metadata": {"path": str(dest)}})
    try:
        client.execute()
    except Exception as exc:  # CellExecutionError and everything else
        tb = ""
        for cell in nb.cells:
            for out in cell.get("outputs", []):
                if out.get("output_type") == "error":
                    tb = f"{out.get('ename')}: {out.get('evalue')}"
        raise GateFailure("execution", "a cell failed during execution",
                          {"error": tb or str(exc)[-500:]})

    # G1b: execution counts must be exactly the code cells' positions
    for position, cell in enumerate(code_cells, start=1):
        got = cell.get("execution_count")
        if got != position:
            raise GateFailure("execution",
                              "execution counts are not sequential 1..N",
                              {"expected": position, "got": got})
    for cell in nb.cells:
        for out in cell.get("outputs", []):
            if out.get("output_type") == "error":
                raise GateFailure("execution",
                                  "an output is an error object",
                                  {"ename": out.get("ename"),
                                   "evalue": out.get("evalue")})

    metrics = extract_metrics(nb)
    figs = figure_digests(dest)
    return {"metrics": metrics, "figs": figs, "nb": nb}


def extract_metrics(nb) -> dict:
    """Pull the JSON object out of the cell tagged `metrics`."""
    found = []
    for cell in nb.cells:
        tags = cell.get("metadata", {}).get("tags", [])
        if "metrics" not in tags:
            continue
        for out in cell.get("outputs", []):
            if out.get("output_type") == "stream":
                text = "".join(out.get("text", []))
                try:
                    found.append(json.loads(text))
                except json.JSONDecodeError:
                    raise GateFailure("execution",
                                      "metrics cell output is not JSON",
                                      {"text": text[:300]})
    if len(found) != 1:
        raise GateFailure("execution",
                          "expected exactly one metrics-tagged JSON output",
                          {"found": len(found)})
    required = {"seed", "alpha", "n_train", "n_test", "rmse_test", "rmse_train",
                "r2_test", "rmse_price", "dataset_sha256", "figures"}
    missing = required - set(found[0])
    if missing:
        raise GateFailure("execution", "metrics JSON is missing keys",
                          {"missing": sorted(missing)})
    return found[0]


def figure_digests(dest: Path) -> dict:
    figs = {}
    for p in sorted((dest / "_out" / "figures").glob("*.png")):
        figs[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return figs


def png_outputs(nb) -> list:
    out = []
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        for o in cell.get("outputs", []):
            data = o.get("data", {})
            if "image/png" in data:
                raw = data["image/png"]
                if isinstance(raw, str):
                    import base64
                    raw = base64.b64decode(raw)
                out.append(raw)
    return out


# --- gates -----------------------------------------------------------------
def gate_execution(res: dict) -> dict:
    return {"cells_ok": True}


def gate_determinism(dest_a: Path, dest_b: Path, nb_path: Path,
                     metrics_a: dict, figs_a: dict, metrics_b: dict,
                     figs_b: dict) -> dict:
    d_rmse = abs(metrics_a["rmse_test"] - metrics_b["rmse_test"])
    if d_rmse > DET_TOL:
        raise GateFailure(
            "determinism",
            "two clean runs of the notebook disagree on rmse_test",
            {"rmse_test_a": metrics_a["rmse_test"],
             "rmse_test_b": metrics_b["rmse_test"], "diff": d_rmse})
    if figs_a != figs_b:
        only_a = {k: v for k, v in figs_a.items() if figs_b.get(k) != v}
        raise GateFailure("determinism",
                          "two clean runs produced different figures",
                          {"diff": only_a})
    if metrics_a.get("r2_test") != metrics_b.get("r2_test"):
        raise GateFailure("determinism",
                          "two clean runs disagree on r2_test",
                          {"a": metrics_a.get("r2_test"),
                           "b": metrics_b.get("r2_test")})
    return {"rmse_test_diff": d_rmse, "figures": len(figs_a),
            "dirs": [str(dest_a.name), str(dest_b.name)]}


def gate_figures(metrics: dict, figs: dict, sizes: dict, nb, html: str) -> dict:
    """G3: three distinct real figures, and the report references them all."""
    names = sorted(figs)
    if len(names) < FIG_MIN_COUNT:
        raise GateFailure("figures", "fewer than three figures were saved",
                          {"saved": names, "expected_min": FIG_MIN_COUNT})
    if len(set(figs.values())) != len(figs):
        raise GateFailure("figures", "two saved figures are identical",
                          {"digests": figs})
    small = [n for n in names if sizes.get(n, 0) < FIG_MIN_BYTES]
    if small:
        raise GateFailure("figures", "a saved figure is too small to be real",
                          {"small": small, "min_bytes": FIG_MIN_BYTES,
                           "bytes": {n: sizes.get(n, 0) for n in names}})
    pngs = png_outputs(nb)
    if len(pngs) < FIG_MIN_COUNT:
        raise GateFailure("figures",
                          "fewer than three image/png outputs in the notebook",
                          {"found": len(pngs)})
    digests = [hashlib.sha256(b).hexdigest() for b in pngs]
    if len(set(digests)) != len(digests):
        raise GateFailure("figures", "two notebook figures are identical",
                          {"dupes": len(digests) - len(set(digests))})
    for name in sorted(metrics.get("figures", [])):
        if f'src="figures/{name}"' not in html and f"src='figures/{name}'" not in html:
            raise GateFailure("figures",
                              "report.html does not reference a figure the "
                              "notebook saved",
                              {"missing": name})
    return {"count": len(names), "bytes": {n: sizes[n] for n in names}}


def figure_sizes(dest: Path) -> dict:
    return {p.name: p.stat().st_size
            for p in (dest / "_out" / "figures").glob("*.png")}


def load_report(dest: Path) -> str:
    p = dest / "_out" / "report.html"
    if not p.exists():
        raise GateFailure("report", "report.html was not written",
                          {"expected": "_out/report.html"})
    html = p.read_text(encoding="utf-8")
    if "Traceback" in html or "CellExecutionError" in html:
        raise GateFailure("report", "report.html contains traceback text")
    return html


def gate_report(metrics: dict, html: str) -> dict:
    for key in ("seed", "alpha", "n_train", "n_test", "rmse_test", "r2_test"):
        val = metrics[key]
        rendered = [str(val)]
        if isinstance(val, float):
            rendered.append(f"{val:.6f}")
        if not any(r in html for r in rendered):
            raise GateFailure("report",
                              f"report.html omits metric {key}",
                              {"key": key, "expected": val})
    return {"metrics_rendered": True}


def gate_oracle(metrics: dict, csv_bytes: bytes, seed: int, alpha: float) -> dict:
    ref = oracle.refit(csv_bytes, seed, alpha)
    checks = [("n_train", 0), ("n_test", 0), ("rmse_test", ORACLE_TOL_RMSE),
              ("rmse_train", ORACLE_TOL_RMSE), ("r2_test", ORACLE_TOL_R2)]
    for key, tol in checks:
        got, want = metrics.get(key), ref[key]
        if tol == 0:
            ok = int(got) == int(want)
            diff = None
        else:
            got = float(got)
            diff = abs(got - float(want))
            ok = diff <= tol
        if not ok:
            raise GateFailure("oracle",
                              f"reported {key} disagrees with the independent "
                              f"refit", {"reported": got, "refit": want,
                                         "diff": diff, "tolerance": tol})
    if ref["rmse_test"] > RMSE_TEST_MAX:
        raise GateFailure("accuracy", "refit rmse_test exceeds the noise floor",
                          {"rmse_test": ref["rmse_test"], "limit": RMSE_TEST_MAX})
    if ref["coef_recovery"] > RECOVERY_MAX:
        raise GateFailure("oracle",
                          "coefficient recovery against the generator's exact "
                          "weight vector is too large",
                          {"recovery": ref["coef_recovery"],
                           "limit": RECOVERY_MAX})
    return ref


def gate_blind(csv_bytes: bytes, blind_base: int, alpha: float,
               metrics: dict) -> dict:
    """The artifact's split seed is part of the artifact (SPEC-fixed), so
    --seed does not touch it: it offsets the judge's own random choice,
    the five blind refit seeds."""
    blind_seeds = tuple(range(blind_base, blind_base + len(BLIND_SEEDS)))
    others = [oracle.refit(csv_bytes, s, alpha)["rmse_test"]
              for s in blind_seeds]
    others.sort()
    median = others[len(others) // 2]
    ratio = metrics["rmse_test"] / median
    if ratio > BLIND_MEDIAN_FACTOR:
        raise GateFailure("oracle",
                          "reported rmse_test is not within the blind-seed "
                          "band", {"rmse_test": metrics["rmse_test"],
                                   "median_blind": median,
                                   "limit_ratio": BLIND_MEDIAN_FACTOR,
                                   "ratio": ratio})
    return {"median_blind": median, "ratio": ratio,
            "seeds": list(blind_seeds)}


def gate_integrity(nb) -> dict:
    text = "\n".join("".join(c.get("source", "")) for c in nb.cells)
    for needle in ("judge/", "judge\\", "grade.sh", "selftest.sh",
                   "notebook_judge", "oracle.py"):
        if needle in text:
            raise GateFailure("integrity",
                              "the artifact references the judge",
                              {"needle": needle})
    return {"clean": True}


# --- driver ----------------------------------------------------------------
def grade(artifact: Path, seed: int | None) -> dict:
    t_start = time.monotonic()
    if not artifact.is_file():
        raise GateFailure("input", "artifact is not a file", {"path": str(artifact)})

    workdir = Path(tempfile.mkdtemp(prefix="nbr-grade-"))
    try:
        # the notebook runs next to its dataset in the copied dir
        bundle = workdir / "bundle"
        bundle.mkdir()
        dataset = artifact.parent / "dataset.csv"
        if not dataset.is_file():
            raise GateFailure("input", "dataset.csv not found beside the artifact",
                              {"expected": str(dataset)})
        csv_bytes = dataset.read_bytes()

        # two clean executions, in two different working directories
        res_a = run_notebook(bundle / "runA", artifact)
        sizes_a = figure_sizes(bundle / "runA")
        html_a = load_report(bundle / "runA")
        t_exec = time.monotonic() - t_start
        res_b = run_notebook(bundle / "runB", artifact)
        html_b = load_report(bundle / "runB")

        gates: dict = {}
        gates["execution"] = gate_execution(res_a)

        gates["determinism"] = gate_determinism(
            bundle / "runA", bundle / "runB", artifact,
            res_a["metrics"], res_a["figs"], res_b["metrics"], res_b["figs"])
        gates["determinism"]["html_identical"] = html_a == html_b

        metrics = res_a["metrics"]
        gates["figures"] = gate_figures(metrics, res_a["figs"], sizes_a,
                                        res_a["nb"], html_a)
        # The split seed is the artifact's own (SPEC-fixed) choice; the
        # oracle refits with that seed so a notebook that reports a
        # different split than it used cannot match.  --seed offsets only
        # the judge's own random choice: the blind-seed band.
        split_seed = int(metrics["seed"])
        blind_base = seed if seed is not None else 1
        alpha_used = float(metrics["alpha"])
        gates["oracle"] = gate_oracle(metrics, csv_bytes, split_seed,
                                      alpha_used)
        gates["blind"] = gate_blind(csv_bytes, blind_base, alpha_used,
                                    metrics)
        gates["report"] = gate_report(metrics, html_a)
        gates["integrity"] = gate_integrity(res_a["nb"])

        return {
            "artifact": str(artifact),
            "passed": True,
            "failed_gate": None,
            "reason": None,
            "gates": gates,
            "metrics": {
                "rmse_test": metrics["rmse_test"],
                "r2_test": metrics["r2_test"],
                "n_train": metrics["n_train"],
                "n_test": metrics["n_test"],
                "dataset_sha256": metrics["dataset_sha256"],
            },
            "timing": {"total_s": round(time.monotonic() - t_start, 2),
                       "first_run_s": round(t_exec, 2)},
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    try:
        verdict = grade(Path(args.artifact), args.seed)
    except GateFailure as exc:
        verdict = {
            "artifact": args.artifact,
            "passed": False,
            "failed_gate": exc.gate,
            "reason": exc.reason,
            "detail": exc.detail,
            "gates": {},
            "metrics": {},
        }

    text = json.dumps(verdict, indent=2, sort_keys=True)
    print(text)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
