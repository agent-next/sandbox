#!/usr/bin/env python3
"""MANIFEST.json -- for each shipped media file: what it shows, the command
that produced it, the source data file, size and sha256.

The "what" strings are assembled from the same media/data/ verdicts the
figures and the video read, so the manifest cannot describe a video or a kill
rate the run did not produce.  Every listed file must exist: a missing file is
a hard error, not a warning (DEMO-STANDARD.md: figures show measured numbers
only; the manifest describes what actually shipped).
"""
import hashlib
import json
import os
import re
import sys

MEDIA = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(MEDIA)

sys.path.insert(0, MEDIA)
from common import GATE_ORDER, load_verdict


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def selftest():
    """(killed, total, pct, mutants, det_ok) from the selftest log + verdicts."""
    with open(os.path.join(MEDIA, "data", "selftest_output.txt"),
              encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"kill rate (\d+)/(\d+) = (\d+)%", text)
    if not m:
        raise SystemExit("selftest_output.txt has no kill-rate line")
    det = "determinism OK" in text and "DETERMINISM FAILED" not in text
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), det


def gate_caught_counts():
    """{gate: mutants killed by it}, from the real per-mutant verdicts."""
    # the controls and the determinism replica are not mutants: a file that
    # is not in the mutant list is excluded, so a stray verdict file can
    # never inflate the mutant count.
    from common import MUTANT_ORDER
    wanted = set(MUTANT_ORDER)
    counts = {k: 0 for k in GATE_ORDER}
    names = []
    d = os.path.join(MEDIA, "data")
    for fn in sorted(os.listdir(d)):
        if not (fn.startswith("grade_") and fn.endswith(".json")):
            continue
        name = fn[len("grade_"):-len(".json")]
        if name not in wanted:
            continue
        names.append(name)
        with open(os.path.join(d, fn), encoding="utf-8") as fh:
            v = json.load(fh)
        gate = v.get("failed_gate")
        if gate in counts:
            counts[gate] += 1
    return counts, names


def main():
    good = load_verdict("good")
    killed, total, rate_pct, det_ok = selftest()
    caught, mutants = gate_caught_counts()
    n_mutants = len(mutants)
    broken = load_verdict("broken")
    sev = broken["gates"]["validator"]["issues_by_severity"]
    up = good["facts"]["up_axis"]
    meshes = good["facts"]["oracle"]["meshes"]

    gate_str = ", ".join("%s %d" % (k, caught[k]) for k in GATE_ORDER)
    gates_ok = "all %d gates PASS" % len(GATE_ORDER)

    spec = {
        "result.png": {
            "what": (
                "Key figure. Left = task/traffic_cone_broken.usda as the "
                "judge saw it: gray Band (no material binding), no normals to "
                "draw, NVIDIA validator %d FAILURE / %d ERROR, %d oracle "
                "errors, status FAIL. Right = "
                "examples/good/traffic_cone_fixed.usda: the same three "
                "meshes with the asset's own authored face-varying normals "
                "drawn, %s, per-mesh normals == corners, max |norm|-1 "
                "deviation, zero-area faces, world bbox deviation 0.0 cm, "
                "measured height axis %s. Bottom strip = the six seeded "
                "defects with real oracle error counts."
                % (sev.get("FAILURE", 0), sev.get("ERROR", 0),
                   len(broken["gates"]["oracle"]["errors"]), gates_ok,
                   up["height_axis"])),
            "command": "bash media/make_media.sh  (fig_result.py)",
            "source_data": ("media/data/grade_good.json, "
                            "media/data/grade_broken.json, "
                            "media/data/mesh_good.json, "
                            "media/data/mesh_broken.json"),
        },
        "loop.png": {
            "what": (
                "The self-test. Left = every verdict: the known-good control "
                "(passed all %d gates), the %d known-bad single-edit mutants "
                "with the gate that caught each and the error count that gate "
                "reported, and the task input. Right = the measured kill rate "
                "%d/%d = %d%% with the SPEC 90%% pass line, the determinism "
                "check (%s), and which gate caught the mutants (%s)."
                % (len(GATE_ORDER), n_mutants, killed, total, rate_pct,
                   "identical" if det_ok else "DIFFERS", gate_str)),
            "command": "bash media/make_media.sh  (fig_loop.py)",
            "source_data": ("media/data/grade_*.json (%d mutants + good + "
                            "broken), media/data/selftest_output.txt"
                            % n_mutants),
        },
        "make_video.py": {
            "what": (
                "The video source. Six shots -- hook (the finished repaired "
                "cone fills frame 1), input -> output (broken beside "
                "repaired), escalate (close orbit + all %d gate verdicts), "
                "the 4x-speed verdict replay, proof (the full mutant kill "
                "matrix and the measured kill rate as HUD on the moving "
                "cone), and a static end card with the one-command run line."
                % len(GATE_ORDER)),
            "command": "bash media/make_media.sh  (make_video.py + ffmpeg)",
            "source_data": ("media/data/grade_*.json, "
                            "media/data/selftest_output.txt, "
                            "media/data/mesh_good.json, "
                            "media/data/mesh_broken.json"),
        },
    }

    entries = []
    missing = []
    for fname, meta in spec.items():
        p = os.path.join(MEDIA, fname)
        if not os.path.exists(p):
            missing.append(fname)
            continue
        entries.append(dict(file=fname, bytes=os.path.getsize(p),
                            sha256=sha256(p), **meta))
    if missing:
        raise SystemExit("MANIFEST.json: missing media files: %s"
                         % ", ".join(missing))

    with open(os.path.join(MEDIA, "MANIFEST.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"demo": "cookbook/usd-validate-fix",
                   "note": ("every number plotted or captioned comes from "
                            "judge output regenerated by make_media.sh "
                            "(seed 20261015); the kill rate comes from "
                            "judge/selftest.sh and the gate verdicts from "
                            "judge/grade.sh"),
                   "mutants": n_mutants,
                   "kill_rate": {"killed": killed, "total": total,
                                 "pct": rate_pct,
                                 "by_gate": caught},
                   "files": entries}, fh, indent=2)
        fh.write("\n")

    for e in entries:
        print("  %-16s %9d bytes  %s..." % (e["file"], e["bytes"],
                                            e["sha256"][:16]))
    print("make_manifest: wrote MANIFEST.json (%d files, %d mutants, "
          "kill rate %d/%d)" % (len(entries), n_mutants, killed, total))


if __name__ == "__main__":
    main()
