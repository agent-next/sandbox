"""Keep compact judge evidence, and verify the separately retained CSVs."""

import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys


def read_selftest(path):
    text = path.read_text()
    assert "selftest: known-good: PASS" in text
    assert "selftest: determinism: OK" in text
    rows = re.findall(r"^selftest: mutant (\w+): killed \(gate: ([^)]+)\)$",
                      text, re.M)
    assert len(rows) == len(dict(rows)) == 8, "Expected eight killed mutants"
    killed, total, rate = map(int, re.search(
        r"selftest: kill rate: (\d+)/(\d+) = (\d+)%", text).groups())
    assert killed == total == len(rows) and rate == 100
    return rows


def main():
    work, out = map(Path, sys.argv[1:])
    module = importlib.util.spec_from_file_location("grade", work / "judge/_grade.py")
    grade = importlib.util.module_from_spec(module)
    module.loader.exec_module(grade)
    spec = json.loads((work / "judge/spec.json").read_text())
    verdict = json.loads((work / "grade.json").read_text())
    assert verdict["judge_intact"] and verdict["seed"] == 0
    assert all(g["pass"] for g in verdict["gates"].values())
    assert "mode" not in verdict["gates"]["run"], "Must not use --skip-run"
    grade.SPEC_DT = spec["timestep_s"]
    expected = grade.oracle_values(spec)
    for scene in spec["scenarios"]:
        name = scene["name"]
        src = work / "trajectories" / scene["output"]
        rows = grade.parse_traj(src)
        assert not grade.csv_shape(name, rows, scene)
        assert grade.analyze(name, rows, expected[name], spec) == \
            verdict["scenarios"][name]["oracle"], f"{name}: CSV/grade mismatch"
        shutil.copyfile(src, out / scene["output"])
    read_selftest(out / "selftest.txt")
    # Wall times are not plotted. Exclude them for byte-reproducible evidence.
    verdict.pop("timing")
    (out / "grade.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
    print("CSV oracle metrics: exactly equal to the full-run grade (4/4)")


if __name__ == "__main__":
    main()
