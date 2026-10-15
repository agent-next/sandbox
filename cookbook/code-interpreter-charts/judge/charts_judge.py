#!/usr/bin/env python3
"""Judge for cookbook/code-interpreter-charts (gates in ../SPEC.md).

Grades one `analysis.py` artifact:

  G1 artifact contract   parses, imports pandas + matplotlib, runs within
                         300 s and writes answers.json, charts.json and the
                         three declared PNGs
  G2 answers             all five answers match judge/oracle.py within
                         1e-6 * max(1, |oracle|)
  G3 images              each PNG decodes, matches its declared size, has
                         >= 8 distinct RGB colours and grey variance >= 50
  G4 plotted data        charts.json series match the oracle (OLS slope,
                         amplitude, 12 monthly means, top-10, total, C1
                         monthly series)
  G5 honesty             every number finite; the three PNGs are not the
                         same bytes

Prints one JSON verdict; exits 0 only if every gate passes.  Run through
judge/grade.sh, which supplies the pinned interpreter (Pillow) and checks
that judge/ is unchanged before and after.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402  (same directory; judge is stdlib + Pillow)

TOL_REL = 1e-6
RUN_TIMEOUT_S = 300.0
MIN_COLOURS = 8
MIN_VARIANCE = 50.0
CHART_FILES = {
    "C1": ("c1_mauna_loa_trend.png", 1280, 800),
    "C2": ("c2_seasonal_cycle.png", 1280, 800),
    "C3": ("c3_top_emitters_2024.png", 1280, 900),
}
ANSWER_KEYS = [
    "mauna_loa_trend_ppm_per_year",
    "mauna_loa_seasonal_amplitude_ppm",
    "mauna_loa_mean_annual_growth_ppm",
    "owid_world_emissions_2024_gt",
    "owid_top_emitter_2024_share",
]


class GateFailed(RuntimeError):
    """A gate failed; the message is the reason recorded in the verdict."""

    def __init__(self, gate, reason):
        super().__init__(reason)
        self.gate = gate
        self.reason = reason


def tol(reference):
    return TOL_REL * max(1.0, abs(reference))


def close(got, want):
    return (isinstance(got, (int, float)) and not isinstance(got, bool)
            and math.isfinite(got) and abs(got - want) <= tol(want))


def imports_of(source):
    """Top-level module names the artifact imports, via the AST."""
    names = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def run_artifact(artifact_dir, data_dir, work, venv_python, timing):
    """G1: run the artifact on a copy; return (answers, charts, png dir)."""
    src = Path(artifact_dir)
    if not (src / "analysis.py").is_file():
        raise GateFailed("G1", f"no analysis.py in {src}")
    source = (src / "analysis.py").read_text()
    try:
        compile(source, "analysis.py", "exec")
    except SyntaxError as exc:
        raise GateFailed("G1", f"analysis.py does not parse: {exc}") from exc
    have = imports_of(source)
    missing = {"pandas", "matplotlib"} - have
    if missing:
        raise GateFailed("G1", "analysis.py does not import "
                               f"{', '.join(sorted(missing))} (the brief is a "
                               "pandas + matplotlib script)")

    # Everything the artifact sees lives in a temp dir: it never touches the
    # judge tree, and its own directory is recreated from scratch.
    run_dir = work / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "analysis.py", run_dir / "analysis.py")
    shutil.copytree(data_dir, run_dir / "data")
    out_dir = run_dir / "out"
    out_dir.mkdir()

    env = dict(os.environ, MPLBACKEND="Agg", MPLCONFIGDIR=str(work / "mpl"))
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [venv_python, "-I", "analysis.py",
             "--data-dir", "data", "--out-dir", "out"],
            cwd=run_dir, env=env, capture_output=True, text=True,
            timeout=RUN_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise GateFailed("G1", f"analysis.py did not finish within "
                               f"{RUN_TIMEOUT_S:.0f} s") from exc
    timing["artifact_run_s"] = round(time.monotonic() - start, 3)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-1500:]
        raise GateFailed("G1", f"analysis.py exited {proc.returncode}:\n{tail}")

    for name in ("answers.json", "charts.json"):
        if not (out_dir / name).is_file():
            raise GateFailed("G1", f"analysis.py did not write {name}")
    try:
        answers = json.loads((out_dir / "answers.json").read_text())
        charts = json.loads((out_dir / "charts.json").read_text())
    except (ValueError, OSError) as exc:
        raise GateFailed("G1", f"answers.json / charts.json are not "
                               f"readable JSON: {exc}") from exc
    if not isinstance(answers, dict) or not isinstance(charts, dict):
        raise GateFailed("G1", "answers.json and charts.json must be JSON "
                               "objects")
    return answers, charts, out_dir


def gate_answers(answers, ref):
    """G2: the five answers against the independent oracle."""
    detail = {}
    problems = []
    for key in ANSWER_KEYS:
        if key not in answers:
            problems.append(f"{key}: missing")
            continue
        got, want = answers[key], ref["answers"][key]
        detail[key] = {"got": got, "oracle": want,
                       "abs_diff": (abs(got - want)
                                    if isinstance(got, (int, float))
                                    and not isinstance(got, bool) else None)}
        if not close(got, want):
            problems.append(f"{key}: got {got!r}, oracle {want!r}")
    if problems:
        raise GateFailed("G2", "answers do not match the oracle: "
                               + "; ".join(problems))
    return detail


def gate_images(charts, out_dir, timing):
    """G3: each PNG is a real, non-blank image of the declared size."""
    from PIL import Image

    detail = {}
    for key, (fname, want_w, want_h) in CHART_FILES.items():
        meta = charts.get(key)
        if not isinstance(meta, dict):
            raise GateFailed("G3", f"charts.json has no {key} object")
        if meta.get("file") != fname:
            raise GateFailed("G3", f"{key}.file is {meta.get('file')!r}, "
                                   f"expected {fname!r}")
        if (meta.get("width_px"), meta.get("height_px")) != (want_w, want_h):
            raise GateFailed(
                "G3", f"{key} declares {meta.get('width_px')}x"
                      f"{meta.get('height_px')} px, expected "
                      f"{want_w}x{want_h}")
        path = out_dir / fname
        if not path.is_file():
            raise GateFailed("G3", f"{fname} was not written")
        try:
            with Image.open(path) as im:
                im.load()
                size = im.size
                rgb = im.convert("RGB")
                raw = rgb.tobytes()
        except Exception as exc:  # Pillow raises a family of errors
            raise GateFailed("G3", f"{fname} does not decode as an image: "
                                   f"{exc}") from exc
        if size != (want_w, want_h):
            raise GateFailed("G3", f"{fname} is {size[0]}x{size[1]} px, "
                                   f"declared {want_w}x{want_h}")
        n = len(raw) // 3
        colours = len({raw[i:i + 3] for i in range(0, len(raw), 3)})
        grey_sum = 0.0
        grey_sq = 0.0
        for i in range(0, len(raw), 3):
            r, g, b = raw[i], raw[i + 1], raw[i + 2]
            v = 0.299 * r + 0.587 * g + 0.114 * b
            grey_sum += v
            grey_sq += v * v
        mean = grey_sum / n
        variance = grey_sq / n - mean * mean
        detail[key] = {"file": fname, "width_px": size[0],
                       "height_px": size[1], "distinct_colours": colours,
                       "grey_variance": round(variance, 3)}
        if colours < MIN_COLOURS:
            raise GateFailed("G3", f"{fname} has {colours} distinct RGB "
                                   f"colours (< {MIN_COLOURS}): blank or "
                                   "near-blank image")
        if variance < MIN_VARIANCE:
            raise GateFailed("G3", f"{fname} grey variance {variance:.2f} "
                                   f"(< {MIN_VARIANCE}): blank or "
                                   "near-blank image")
    return detail


def _pair_close(got, want, label, problems):
    if (not isinstance(got, (list, tuple)) or len(got) != 2
            or not close(got[0], want[0]) or not close(got[1], want[1])):
        problems.append(f"{label}: got {got!r}, oracle {want!r}")


def gate_charts(charts, ref):
    """G4: the plotted series against the oracle's own aggregation."""
    problems = []
    ml, ow = ref["mauna_loa"], ref["owid"]

    c1 = charts.get("C1")
    if not isinstance(c1, dict):
        raise GateFailed("G4", "charts.json has no C1 object")
    if not close(c1.get("mauna_loa_trend_ppm_per_year"),
                 ml["mauna_loa_trend_ppm_per_year"]):
        problems.append("C1 trend "
                        f"{c1.get('mauna_loa_trend_ppm_per_year')!r} != oracle "
                        f"{ml['mauna_loa_trend_ppm_per_year']!r}")
    months = c1.get("months")
    want_months = ml["months"]
    if not isinstance(months, list) or len(months) != len(want_months):
        problems.append(f"C1 months: got "
                        f"{len(months) if isinstance(months, list) else 'n/a'}"
                        f" points, oracle has {len(want_months)}")
    else:
        for i, (got, want) in enumerate(zip(months, want_months)):
            if (not close(got[0], want[0])) or not close(got[1], want[1]):
                problems.append(f"C1 months[{i}]: got {got!r}, oracle {want!r}")
                break
    line = c1.get("trend_line")
    if not isinstance(line, list) or len(line) != 2:
        problems.append(f"C1 trend_line: got {line!r}, oracle has 2 points")
    else:
        for i, (got, want) in enumerate(zip(line, ml["trend_line"])):
            _pair_close(got, want, f"C1 trend_line[{i}]", problems)

    c2 = charts.get("C2")
    if not isinstance(c2, dict):
        raise GateFailed("G4", "charts.json has no C2 object")
    if not close(c2.get("amplitude_ppm"), ml["amplitude_ppm"]):
        problems.append(f"C2 amplitude {c2.get('amplitude_ppm')!r} != oracle "
                        f"{ml['amplitude_ppm']!r}")
    got_means = c2.get("months")
    want_means = ml["monthly_means"]
    if not isinstance(got_means, list) or len(got_means) != len(want_means):
        problems.append(f"C2 months: got "
                        f"{len(got_means) if isinstance(got_means, list) else 'n/a'}"
                        f" entries, oracle has {len(want_means)}")
    else:
        for i, (got, want) in enumerate(zip(got_means, want_means)):
            if (not close(got[0], want[0])) or not close(got[1], want[1]):
                problems.append(f"C2 months[{i}]: got {got!r}, oracle {want!r}")
                break

    c3 = charts.get("C3")
    if not isinstance(c3, dict):
        raise GateFailed("G4", "charts.json has no C3 object")
    if not close(c3.get("total_gt"), ow["total_gt"]):
        problems.append(f"C3 total_gt {c3.get('total_gt')!r} != oracle "
                        f"{ow['total_gt']!r}")
    got_emis = c3.get("emissions_gt")
    want_emis = ow["emissions_gt"]
    if not isinstance(got_emis, list) or len(got_emis) != len(want_emis):
        problems.append(f"C3 emissions_gt: got "
                        f"{len(got_emis) if isinstance(got_emis, list) else 'n/a'}"
                        f" entries, oracle has {len(want_emis)}")
    else:
        for i, (got, want) in enumerate(zip(got_emis, want_emis)):
            if got[0] != want[0] or not close(got[1], want[1]):
                problems.append(f"C3 emissions_gt[{i}]: got {got!r}, oracle "
                                f"{want!r}")
                break
    entities = c3.get("entities")
    if entities != ow["entities"]:
        problems.append(f"C3 entities: got {entities!r}, oracle "
                        f"{ow['entities']!r}")

    if problems:
        raise GateFailed("G4", "plotted data does not match the oracle: "
                               + "; ".join(problems))
    return {"C1_points": len(months) if isinstance(months, list) else 0,
            "C2_months": len(got_means) if isinstance(got_means, list) else 0,
            "C3_top": len(got_emis) if isinstance(got_emis, list) else 0,
            "top_entity": (entities[0] if isinstance(entities, list)
                           and entities else None)}


def walk_numbers(obj, path="charts"):
    """Yield (path, value) for every number in a nested JSON structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_numbers(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_numbers(v, f"{path}[{i}]")
    else:
        yield path, obj


def gate_honesty(charts, out_dir):
    """G5: no NaN/Infinity/null, and the PNGs are not copies of each other."""
    for path, value in walk_numbers(charts):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not math.isfinite(value):
            raise GateFailed("G5", f"{path} is {value!r}, not a finite number")
    blobs = {}
    for key, (fname, _, _) in CHART_FILES.items():
        blobs[key] = (out_dir / fname).read_bytes()
    if blobs["C1"] == blobs["C2"] or blobs["C1"] == blobs["C3"] \
            or blobs["C2"] == blobs["C3"]:
        raise GateFailed("G5", "two of the three PNGs are byte-identical: "
                               "one image was copied, not drawn three times")
    return {k: len(v) for k, v in blobs.items()}


def grade(artifact_dir, data_dir, venv_python):
    verdict = {"artifact": str(Path(artifact_dir).resolve()),
               "data_dir": str(Path(data_dir).resolve()),
               "passed": False, "failed_gate": None, "reason": None,
               "gates": {}, "timing": {}}
    work = Path(tempfile.mkdtemp(prefix="charts-judge-"))
    try:
        ref = oracle.compute(Path(data_dir))
        verdict["gates"]["oracle"] = {
            k: round(v, 12) for k, v in sorted(ref["answers"].items())}
        t0 = time.monotonic()
        answers, charts, out_dir = run_artifact(
            artifact_dir, Path(data_dir), work, venv_python,
            verdict["timing"])
        verdict["timing"]["g1_s"] = round(time.monotonic() - t0, 3)
        verdict["gates"]["G1"] = {"answers": sorted(answers),
                                  "charts": sorted(charts)}
        t0 = time.monotonic()
        verdict["gates"]["G2"] = gate_answers(answers, ref)
        verdict["gates"]["G3"] = gate_images(charts, out_dir,
                                             verdict["timing"])
        verdict["gates"]["G4"] = gate_charts(charts, ref)
        verdict["gates"]["G5"] = gate_honesty(charts, out_dir)
        verdict["timing"]["gates_s"] = round(time.monotonic() - t0, 3)
        verdict["passed"] = True
    except GateFailed as exc:
        verdict["failed_gate"] = exc.gate
        verdict["reason"] = exc.reason
        verdict["passed"] = False
    except oracle.OracleError as exc:
        verdict["failed_gate"] = "oracle"
        verdict["reason"] = f"the judge could not compute its oracle: {exc}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return verdict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", help="directory holding analysis.py")
    ap.add_argument("--data-dir", default=None,
                    help="pinned CSV directory (default examples/good/data)")
    ap.add_argument("--seed", type=int, default=20261015,
                    help="accepted for interface parity; the judge is "
                         "seed-free")
    ap.add_argument("--json", default=None, help="write the verdict here")
    ap.add_argument("--venv-python", default=sys.executable,
                    help="interpreter that has pandas/matplotlib/Pillow")
    args = ap.parse_args()

    demo = Path(__file__).resolve().parent.parent
    data_dir = Path(args.data_dir) if args.data_dir else demo / \
        "examples" / "good" / "data"

    verdict = grade(args.artifact, data_dir, args.venv_python)
    verdict["seed"] = args.seed
    text = json.dumps(verdict, indent=2, sort_keys=True)
    if args.json:
        Path(args.json).write_text(text + "\n")
    print(text)
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
