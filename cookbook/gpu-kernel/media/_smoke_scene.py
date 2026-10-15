#!/usr/bin/env python3
"""Write a throwaway video/src/data/scene.json so the Remotion bundle can be
type/compile-checked before the real clips exist. Not part of make_media.sh."""
import json, os, random
HERE = os.path.dirname(os.path.abspath(__file__))
r = random.Random(0)
cases = []
for i, (rows, cols, dist, seed) in enumerate([
    (64, 4096, "randn", 0), (64, 4096, "randn64", 1), (7, 4093, "randn", 2),
    (7, 4093, "last_max", 3), (37, 65, "randn", 4), (3, 1, "randn", 5),
    (1, 1024, "randn", 6), (8, 512, "zeros", 7), (8, 512, "const3", 8),
    (64, 512, "shift", 9)]):
    k = [round(r.uniform(0.2, 40), 3) for _ in range(4 if cols >= 1024 else 8)]
    e = [round(r.uniform(0.3, 60), 3) for _ in k]
    cases.append({"case": i, "shape": [rows, cols], "dist": dist, "seed": seed,
                  "kernel_ms": k, "eager_ms": e})
scene = {
    "gpu": {"kernel_ms": 0.0775, "eager_ms": 0.0793, "speedup": 1.0235,
            "gb_per_s": 1731.8, "worst": {"max_abs": 2.38e-7, "rowsum": 2.38e-7,
            "shift": 1.05e-6},
            "cases": [{"shape": [4096, 4096], "dist": "randn", "max_abs": 3.7e-9,
                       "rowsum": 2.4e-7, "ok": True, "seed": 0}] * 10,
            "gates": {"structure": True, "device-compile": True,
                      "correctness": True},
            "judge_intact": True, "mode": "full",
            "mutants": [{"name": f"m{i}", "failed": ["correctness"], "detail": {}} for i in range(11)],
            "mutants_killed": 11, "mutants_total": 11, "total_s": 38.0,
            "lease": "gl-2835a2-12"},
    "cpu": {"wall": {"setup_s": 3, "selftest_s": 190, "grade_s": 60},
            "mutants": [{"name": f"m{i}", "killed": True, "wall_s": 8 + i} for i in range(11)],
            "verdict": {"mode": "cpu-check", "gates": {"structure": True,
            "device-compile": True, "correctness": True}, "judge_intact": True,
            "worst": {"max_abs": 1.19e-7, "rowsum": 1.19e-7, "shift": 1.05e-6},
            "cases": 10},
            "cases": cases},
    "row": {"in": [round(r.gauss(0, 1), 3) for _ in range(65)],
            "out": [1 / 65] * 65},
    "terminal": {"clip": "terminal.mp4", "duration_s": 32.0},
}
out = os.path.join(HERE, "video", "src", "data", "scene.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
json.dump(scene, open(out, "w"))
print("wrote", out)
