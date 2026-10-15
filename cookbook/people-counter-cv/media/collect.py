"""Keep compact judge evidence, and verify the separately retained CSVs.

Runs the real good counter and the judge's reference counter on the
regenerated clip and asserts the oracle metrics computed from those CSVs
exactly equal the full-run grade verdict. Also dumps every clip frame as
PNG (ignored) for the video renderer, which runs cv2-free.
"""

import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


def read_selftest(path):
    text = path.read_text()
    assert "selftest: known-good: PASS" in text
    assert "selftest: determinism: OK" in text
    rows = re.findall(r"^selftest: mutant (\w+): killed \(gate: ([^)]+)\)$",
                      text, re.M)
    assert len(rows) == len(dict(rows)) == 9, "Expected nine killed mutants"
    killed, total, rate = map(int, re.search(
        r"selftest: kill rate: (\d+)/(\d+) = (\d+)%", text).groups())
    assert killed == total == len(rows) and rate == 100
    return rows


def main():
    work, out = map(Path, sys.argv[1:3])
    module = importlib.util.spec_from_file_location("grade", work / "judge/_grade.py")
    grade = importlib.util.module_from_spec(module)
    module.loader.exec_module(grade)
    spec = json.loads((work / "judge/spec.json").read_text())
    verdict = json.loads((work / "grade.json").read_text())
    assert verdict["judge_intact"] and verdict["seed"] == 0
    assert all(g["pass"] for g in verdict["gates"].values())
    assert "mode" not in verdict["gates"]["run"], "Must not use --skip-run"

    # regenerate the exact graded clip and re-run both counters on it
    run_dir = work / "run"
    (run_dir / "input").mkdir(parents=True)
    shutil.copyfile(work / "judge/spec.json", run_dir / "spec.json")
    sys.path.insert(0, str(work / "judge"))
    import gen_scene
    truth = grade.ensure_scene(spec, work / "judge/spec.json", 0, run_dir)
    jpy = Path.home() / ".venvs/people-counter-cv/bin/python"
    shutil.copyfile(work / "examples/good/counter.py", run_dir / "counter.py")
    shutil.copyfile(work / "judge/ref_count.py", run_dir / "ref.py")
    for name, dest in (("counter.py", out / "crossings.csv"),
                       ("ref.py", out / "ref_crossings.csv")):
        proc = subprocess.run([str(jpy), name], cwd=run_dir,
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr[-400:]
        shutil.copyfile(run_dir / "crossings.csv", dest)

    # parse_crossings validates t against the clip duration (module global)
    grade.t_max = spec["video"]["duration_s"] + 0.5
    art = grade.parse_crossings(out / "crossings.csv")
    truth_events = [(e["t"], e["dir"]) for e in truth["events"]]
    (out / "truth.json").write_text(json.dumps(truth, indent=2,
                                               sort_keys=True) + "\n")
    matches = grade.pair_events(truth_events, art, grade.PAIR_WINDOW_S)
    devs = [d for _, _, d in matches]
    m = verdict["gates"]["oracle"]["metrics"]
    assert m["artifact_counts"] == grade.counts_by_dir(art)
    assert m["matched"] == len(matches)
    assert abs(m["time_mae_s"] - round(sum(devs) / len(devs), 4)) < 5e-4
    assert abs(m["time_max_dev_s"] - round(max(devs), 4)) < 5e-4
    read_selftest(out / "selftest.txt")

    # dump clip frames for the cv2-free renderer
    (out / "frames").mkdir(parents=True, exist_ok=True)
    dump = subprocess.run(
        [str(jpy), "-c",
         "import cv2, sys\n"
         "cap = cv2.VideoCapture(sys.argv[1])\n"
         "k = 0\n"
         "while True:\n"
         "    ok, f = cap.read()\n"
         "    if not ok:\n"
         "        break\n"
         "    cv2.imwrite(sys.argv[2] + f'/f{k:04d}.png', f)\n"
         "    k += 1\n"
         "print(k)\n",
         str(run_dir / "input/video.avi"), str(out / "frames/")],
        capture_output=True, text=True)
    assert dump.returncode == 0, dump.stderr[-400:]
    n_frames = int(dump.stdout.strip())
    assert n_frames == int(spec["video"]["duration_s"] * spec["video"]["fps"])

    # Wall times are not plotted. Exclude them for byte-reproducible evidence.
    verdict.pop("timing")
    (out / "grade.json").write_text(json.dumps(verdict, indent=2,
                                               sort_keys=True) + "\n")
    print(f"collect: oracle metrics exactly equal the full-run grade "
          f"({len(matches)}/{len(truth_events)} events); {n_frames} frames dumped")


if __name__ == "__main__":
    main()
