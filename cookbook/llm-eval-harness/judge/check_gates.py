#!/usr/bin/env python3
"""judge/check_gates.py — all gates for the llm-eval-harness judge.

Usage: check_gates.py <samples.jsonl> <eval.py> [--json out.json] [--seed N]

Grades the artifact (samples.jsonl + eval.py) against the pinned MBPP
subset.  All rules are numeric and deterministic; exit 0 only if every gate
passes.  The judge never trusts eval.py: it re-executes every sample itself
in fresh subprocesses and recomputes pass@1 / pass@k with exact Fraction
arithmetic.  Besides the artifact's own samples, the judge grades eval.py a
second time on a judge-built mixed samples file (some tasks n=2, some n=3,
with deliberate failures and one hanging sample) so that estimator bugs that
are invisible on an all-pass n=1 artifact still change the numbers.
"""

import argparse
import json
import math
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = HERE.parent / "data" / "mbpp_subset.jsonl"
SAMPLE_TIMEOUT_S = 10.0
EVAL_TIMEOUT_S = 120.0
P1_FORMAT = "pass@1: "
PK_FORMAT = "pass@k: "

verdict = {
    "gates": [],
    "all_gates_passed": False,
}


def gate(name, passed, detail):
    verdict["gates"].append({"gate": name, "passed": bool(passed),
                             "detail": detail})
    return passed


def combi(n_, k_):
    return math.comb(n_, k_) if 0 <= k_ <= n_ else 0


def run_solution_probe(sol, setup, tests, timeout=SAMPLE_TIMEOUT_S):
    """Run one solution against a task's test_list in a fresh, isolated
    subprocess.  Returns True iff every assertion passes.  A wall-clock
    timeout is a failure, not a hang."""
    with tempfile.TemporaryDirectory(prefix="judge-probe-") as td:
        probe = Path(td) / "probe.py"
        probe.write_text("\n".join([setup, sol, "", *tests]))
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(probe)],
                cwd=td, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False
        return proc.returncode == 0


def parse_metrics(stdout):
    """Parse eval.py's contract: exactly two non-empty stdout lines,
    'pass@1: <float>' then 'pass@k: <float>'."""
    lines = [l for l in stdout.splitlines() if l.strip()]
    if len(lines) < 2:
        return None, f"stdout must have two lines, got {len(lines)}: {stdout!r}"
    for line, prefix in ((lines[0], P1_FORMAT), (lines[1], PK_FORMAT)):
        if not line.startswith(prefix):
            return None, (f"stdout line {line!r} does not start with "
                          f"{prefix!r}")
    try:
        p1 = float(lines[0][len(P1_FORMAT):].strip())
        pk = float(lines[1][len(PK_FORMAT):].strip())
    except ValueError as exc:
        return None, f"unparseable metric: {exc}"
    return (p1, pk), None


def run_eval_py(eval_py, samples_path, dataset):
    """Run eval.py on samples_path; return (metrics_or_None, detail)."""
    try:
        proc = subprocess.run(
            [sys.executable, str(eval_py), str(samples_path), str(dataset)],
            capture_output=True, text=True, timeout=EVAL_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None, f"did not finish within {EVAL_TIMEOUT_S:.0f}s"
    if proc.returncode != 0:
        return None, (f"exit {proc.returncode}: {proc.stderr.strip()[-200:]}")
    metrics, err = parse_metrics(proc.stdout)
    if metrics is None:
        return None, err
    return metrics, None


def judge_counts(samples_rows, ds):
    """The judge's own execution: per-task (n, c) from fresh subprocesses."""
    per_task = {}
    for row in samples_rows:
        tid = row["task_id"]
        setup = ds[tid].get("test_setup_code", "") or ""
        ok = run_solution_probe(row["solution"], setup, ds[tid]["test_list"])
        per_task.setdefault(tid, []).append(ok)
    return per_task


def judge_metrics(per_task):
    """pass@1 (fraction of tasks with >=1 passing sample) and the unbiased
    pass@k estimator with k = n_total/n_tasks, in exact Fraction arithmetic
    (oracle #1); averaged over tasks."""
    n_tasks = len(per_task)
    n_total = sum(len(v) for v in per_task.values())
    k = n_total // n_tasks if n_tasks else 0
    pass1 = Fraction(sum(1 for v in per_task.values() if any(v)), n_tasks) \
        if n_tasks else Fraction(0)
    if n_tasks and k:
        terms = []
        for v in per_task.values():
            n, c = len(v), sum(1 for ok in v if ok)
            if n - c < k:
                terms.append(Fraction(1))
            else:
                terms.append(Fraction(1)
                             - Fraction(combi(n - c, k), combi(n, k)))
        passk = sum(terms) / n_tasks
    else:
        passk = Fraction(0)
    return pass1, passk, k, n_total


def build_mixed_samples(ds, seed):
    """Deterministically build the judge's second samples file from the
    pinned dataset: reference solutions (pass), 'pass' scripts (fail every
    test), and one hanging sample.  Mixed n per task so k=2 and the
    combinatorics of the estimator are exercised."""
    tids = sorted(ds)
    broken = "pass"                      # valid Python, fails every test
    hanging = "while True:\n    pass\n"  # must be cut off by the timeout
    rows = []
    layout = {
        "n2_half_pass": tids[0:10],    # n=2: reference + broken   -> c=1
        "n2_all_broken": tids[10:15],  # n=2: broken + broken      -> c=0
        "n3": tids[15:20],             # n=3: reference + 2 broken -> c=1
        "n2_half_pass2": tids[20:30],  # n=2: reference + broken   -> c=1
    }
    first_n3 = True
    for group, ids in layout.items():
        for tid in ids:
            ref = ds[tid]["code"]
            if group in ("n2_half_pass", "n2_half_pass2"):
                rows += [{"task_id": tid, "solution": ref},
                         {"task_id": tid, "solution": broken}]
            elif group == "n2_all_broken":
                rows += [{"task_id": tid, "solution": broken},
                         {"task_id": tid, "solution": broken}]
            else:  # n3
                rows += [{"task_id": tid, "solution": ref},
                         {"task_id": tid, "solution": broken}]
                # exactly one hanging sample overall (still n=3, c=1)
                rows.append({"task_id": tid,
                             "solution": hanging if first_n3 else broken})
                first_n3 = False
    assert len(rows) == 65 and len({r["task_id"] for r in rows}) == 30
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("samples")
    ap.add_argument("eval_py")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    samples_path = Path(args.samples).resolve()
    eval_py = Path(args.eval_py).resolve()
    dataset = DATASET.resolve()
    seed = args.seed

    # ---- load pinned dataset ------------------------------------------------
    ds = {}
    with dataset.open() as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                tid = row["task_id"]
                assert tid not in ds, f"duplicate task_id {tid} in dataset"
                ds[tid] = row
    assert ds, "empty dataset"

    # ---- oracle #2: boundary self-checks on the judge's own arithmetic ------
    assert Fraction(combi(1, 1), combi(1, 1)) == 1
    assert combi(1, 2) == 0, "C(1,2) must be 0"
    for n, c in ((30, 30), (30, 0), (2, 1), (3, 1), (1, 0)):
        # at k=1 the unbiased estimator reduces to c/n for a single task
        pk = Fraction(1) - Fraction(combi(n - c, 1), combi(n, 1))
        assert pk == Fraction(c, n), (n, c, pk)
    # all-pass and none-pass extremes of the averaged estimator
    for rows, want in (([[True]] * 3, Fraction(1)),
                       ([[True, True]] * 2, Fraction(1)),
                       ([[False, False]] * 2, Fraction(0))):
        pt = {i: v for i, v in enumerate(rows)}
        p1, pk, _, _ = judge_metrics(pt)
        assert p1 == want and pk == want, (rows, p1, pk)

    # ---- copy the artifact to a scratch dir (judge-integrity rule) ----------
    work = Path(tempfile.mkdtemp(prefix="harness-judge-"))
    scratch_samples = work / "samples.jsonl"
    scratch_eval = work / "eval.py"
    shutil.copy2(samples_path, scratch_samples)
    shutil.copy2(eval_py, scratch_eval)

    # ============================ G1: format =================================
    problems = []
    per_task_sols = {}
    with samples_path.open() as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(f"line {i}: malformed JSON: {exc}")
                continue
            if not isinstance(row, dict):
                problems.append(f"line {i}: not a JSON object")
                continue
            tid, sol = row.get("task_id"), row.get("solution")
            if not isinstance(tid, int) or isinstance(tid, bool):
                problems.append(f"line {i}: task_id must be an integer, got {tid!r}")
                continue
            if tid not in ds:
                problems.append(f"line {i}: task_id {tid} not in the pinned dataset")
                continue
            if not isinstance(sol, str):
                problems.append(f"line {i}: solution must be a string, got {type(sol).__name__}")
                continue
            per_task_sols.setdefault(tid, []).append(sol)
    if per_task_sols:
        dup = sorted(t for t, s in per_task_sols.items() if len(s) > 1)
        if dup:
            problems.append(f"more than one sample for task(s) {dup[:10]}")
    try:
        py_compile.compile(str(scratch_eval), doraise=True)
    except py_compile.PyCompileError as exc:
        problems.append(f"eval.py does not compile: {str(exc).splitlines()[-1]}")

    n_tasks = len(per_task_sols)
    n_total = sum(len(v) for v in per_task_sols.values())
    gate("G1_format", not problems,
         "; ".join(problems) if problems else
         f"{n_total} samples over {n_tasks} tasks, one per task; eval.py compiles")

    # ===================== G2: judge's own execution =========================
    samples_rows = [json.loads(l) for l in samples_path.read_text().splitlines()
                    if l.strip()]
    per_task_results = {}
    if n_tasks:
        for tid in sorted(per_task_sols):
            setup = ds[tid].get("test_setup_code", "") or ""
            tests = ds[tid]["test_list"]
            per_task_results[tid] = [
                run_solution_probe(sol, setup, tests)
                for sol in per_task_sols[tid]]
    c_task = {t: sum(1 for ok in r if ok) for t, r in per_task_results.items()}
    gate("G2_execution", True,
         f"executed {n_total} sample(s) in fresh isolated subprocesses "
         f"({sum(c_task.values())} passed)")

    # judge's reference numbers for the artifact's own samples (exact)
    pass1_judge, passk_judge, k_own, _ = judge_metrics(per_task_results)
    pass1_judge = float(pass1_judge)
    passk_judge = float(passk_judge)

    # ===================== G3: eval.py runs ==================================
    g3_ok = False
    if n_tasks:
        metrics, err = run_eval_py(scratch_eval, scratch_samples, dataset)
        g3_ok = metrics is not None
        detail = "exit 0, both metric lines printed" if g3_ok else err
    else:
        detail = "no tasks to evaluate"
    gate("G3_eval_py_runs", g3_ok, detail)

    # ============== G4: numbers match on BOTH sample files ===================
    # G4a: the artifact's own samples.jsonl
    # G4b: the judge's mixed samples file (n in {1,2,3}, deliberate failures,
    #      one hanging sample) — estimator bugs invisible on an all-pass n=1
    #      artifact change the numbers there.
    g4_ok = False
    g4_detail = "skipped: eval.py did not run"
    eval_own = None
    mixed_summary = None
    if g3_ok:
        g4_ok = True
        diffs = []
        metrics, err = run_eval_py(scratch_eval, scratch_samples, dataset)
        if metrics is None:
            g4_ok, g4_detail = False, f"own samples: {err}"
        else:
            p1, pk = metrics
            eval_own = {"pass@1": round(p1, 10), "pass@k": round(pk, 10)}
            d1, d2 = abs(p1 - pass1_judge), abs(pk - passk_judge)
            diffs.append(f"own: d(pass@1)={d1:.1e} d(pass@k)={d2:.1e}")
            if d1 > 1e-9 or d2 > 1e-9:
                g4_ok = False
                g4_detail = (f"own samples: eval.py pass@1={p1:.10f} "
                             f"pass@k={pk:.10f} vs judge pass@1={pass1_judge:.10f} "
                             f"pass@k={passk_judge:.10f}")
        if g4_ok:
            mixed_rows = build_mixed_samples(ds, seed)
            mixed_path = work / "mixed_samples.jsonl"
            with mixed_path.open("w") as fh:
                for r in mixed_rows:
                    fh.write(json.dumps(r) + "\n")
            mixed_per_task = judge_counts(mixed_rows, ds)
            mp1, mpk, mk, mn = judge_metrics(mixed_per_task)
            # oracle #2 on the mixed file: still a valid probability
            assert 0 <= mp1 <= 1 and 0 <= mpk <= 1
            mixed_summary = {"pass@1": round(float(mp1), 10),
                             "pass@k": round(float(mpk), 10),
                             "k": mk, "n_total": mn, "n_tasks": len(mixed_per_task)}
            metrics, err = run_eval_py(scratch_eval, mixed_path, dataset)
            if metrics is None:
                g4_ok, g4_detail = False, f"judge mixed samples: {err}"
            else:
                p1, pk = metrics
                mixed_summary["eval_pass@1"] = round(p1, 10)
                mixed_summary["eval_pass@k"] = round(pk, 10)
                d1 = abs(p1 - float(mp1))
                d2 = abs(pk - float(mpk))
                diffs.append(f"mixed: d(pass@1)={d1:.1e} d(pass@k)={d2:.1e}")
                if d1 > 1e-9 or d2 > 1e-9:
                    g4_ok = False
                    g4_detail = (f"judge mixed samples (n_total={mn}, k={mk}): "
                                 f"eval.py pass@1={p1:.10f} pass@k={pk:.10f} vs "
                                 f"judge pass@1={float(mp1):.10f} "
                                 f"pass@k={float(mpk):.10f}")
        if g4_ok:
            g4_detail = "; ".join(diffs) + " (tol 1e-9)"
    gate("G4_numbers_match", g4_ok, g4_detail)

    # ============== G5: a timeout counts as a failure ========================
    if n_tasks:
        hang = "while True:\n    pass\n"
        rows = [dict(r) for r in samples_rows]
        first_tid = rows[0]["task_id"]
        idx = next(i for i, r in enumerate(rows) if r["task_id"] == first_tid)
        rows[idx] = {"task_id": first_tid, "solution": hang}
        hang_path = work / "hang_samples.jsonl"
        with hang_path.open("w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        metrics, err = run_eval_py(scratch_eval, hang_path, dataset)
        if metrics is None:
            ok, detail = False, f"on the hanging-sample copy: {err}"
        else:
            p1 = metrics[0]
            if not 0.0 <= p1 <= 1.0 + 1e-12:
                ok, detail = False, f"pass@1 {p1} out of range"
            elif p1 > 1.0 - 1.0 / n_tasks + 1e-9:
                ok, detail = (False,
                              f"pass@1 {p1:.10f} with a hanging sample is still "
                              f">= 1 - 1/{n_tasks}; the timeout was counted as "
                              f"a pass")
            else:
                ok, detail = (True,
                              f"timeout sample failed as required "
                              f"(pass@1 dropped to {p1:.10f})")
        gate("G5_timeout_is_failure", ok, detail)
    else:
        gate("G5_timeout_is_failure", False, "no tasks to test the timeout on")

    # ==========================================================================
    passed_all = all(g["passed"] for g in verdict["gates"])
    verdict["all_gates_passed"] = passed_all
    verdict["seed"] = seed
    verdict["judge_values"] = {
        "pass@1": round(pass1_judge, 10),
        "pass@k": round(passk_judge, 10),
        "k": k_own, "n_total": n_total, "n_tasks": n_tasks,
    }
    if eval_own is not None:
        verdict["eval_values"] = eval_own
    if mixed_summary is not None:
        verdict["mixed_samples"] = mixed_summary
    verdict["per_task_c"] = {str(t): c_task[t] for t in sorted(per_task_results)}

    print(json.dumps(verdict, indent=2) + "\n")
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as fh:
            fh.write(json.dumps(verdict, indent=2) + "\n")

    shutil.rmtree(work, ignore_errors=True)
    return 0 if passed_all else 1


if __name__ == "__main__":
    sys.exit(main())
