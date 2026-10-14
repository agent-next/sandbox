#!/usr/bin/env python3
"""Unit test for make_figures.py: both figures build from a fixture
report generated in code, and a report missing `timing` raises.

Run with the media venv: media/.venv/bin/python media/test_make_figures.py
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_figures


def fixture_report():
    """Build a report dict in code; every number is computed, none typed
    in from a real run."""
    dists = ["randn", "randn64", "big", "randn", "last_max",
             "randn", "randn", "randn", "zeros", "shift"]
    cases = []
    for i, dist in enumerate(dists):
        rows = 2 ** (i % 7 + 4)
        cols = 4096 - i * 37
        err = 0.0 if dist in ("zeros", "const3") else 10.0 ** (-9 + i * 0.4)
        case = {"shape": [rows, cols], "dist": dist, "seed": i,
                "max_abs_err": err, "rowsum_err": err / 10,
                "rowsum_ok": True, "finite01": True, "allclose": True,
                "input_intact": True, "launched": True, "ok": True}
        if dist == "shift":
            case["shift_err"] = err / 2
            case["shift_ok"] = True
        cases.append(case)
    kernel_ms = 0.05 + 0.01 * len(cases)
    mutants = {}
    for i in range(10):
        name = f"mutant_{i:02d}"
        bad = "device-compile" if i == 0 else "correctness"
        gates = {"structure": True, "device-compile": i != 0}
        if i != 0:
            gates["correctness"] = False
        mutants[name] = {"rc": 1, "failed": [bad], "gates": gates,
                         "detail": {bad: f"{i}/10 cases"}}
    return {
        "good": {"rc": 0, "stderr": "",
                 "verdict": {"artifact": "kernel.py", "mode": "full",
                             "seed": 0, "judge_intact": True,
                             "timing": {"kernel_ms": kernel_ms,
                                        "eager_ms": kernel_ms * 0.9,
                                        "speedup": 0.9},
                             "gates": {
                                 "structure": {"pass": True,
                                               "problems": []},
                                 "device-compile": {"pass": True,
                                                    "problems": []},
                                 "correctness": {"pass": True,
                                                 "cases": len(cases),
                                                 "failed": [],
                                                 "worst": {
                                                     "max_abs": 1e-7,
                                                     "rowsum": 1e-7,
                                                     "shift": 1e-6}}},
                             "cases": cases}},
        "mutants": mutants,
    }


class MakeFiguresTest(unittest.TestCase):
    def test_builds_both_figures(self):
        report = fixture_report()
        with tempfile.TemporaryDirectory() as tmp:
            result = os.path.join(tmp, "result.png")
            loop = os.path.join(tmp, "loop.png")
            make_figures.build_result_png(report, result)
            make_figures.build_loop_png(report, loop)
            for path in (result, loop):
                self.assertTrue(os.path.isfile(path), path)
                self.assertGreater(os.path.getsize(path), 0, path)

    def test_mutant_without_gate_status_raises(self):
        report = fixture_report()
        del report["mutants"]["mutant_00"]["gates"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                make_figures.build_loop_png(
                    report, os.path.join(tmp, "loop.png"))

    def test_missing_timing_raises(self):
        report = fixture_report()
        del report["good"]["verdict"]["timing"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                make_figures.build_result_png(
                    report, os.path.join(tmp, "result.png"))


if __name__ == "__main__":
    unittest.main()
