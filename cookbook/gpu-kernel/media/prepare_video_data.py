#!/usr/bin/env python3
"""Assemble video/src/data/scene.json for the Remotion composition.

Reads only real recorded data:
  media/data/report.json    the demo's committed GPU judge run (verdict,
                            per-case errors, timing, mutants)
  media/data/gpu-run.log    that run's stdout (lease lifecycle, totals)
  media/clips/racedata.json this sandbox's judge run (walls, mutant times)
  media/clips/timings.jsonl this sandbox's per-iteration kernel/eager ms
  media/clips/row.json      one real input row + its softmax
  media/clips/terminal.mp4  the recorded terminal footage (for its duration)

Validates every field the composition needs and exits non-zero naming the
first missing one — the video must never render from partial data.
"""

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS = os.path.join(HERE, "clips")
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "video", "src", "data", "scene.json")


def die(msg):
    print(f"prepare_video_data.py: {msg}", file=sys.stderr)
    raise SystemExit(1)


def need(obj, *keys):
    cur = obj
    for i, k in enumerate(keys):
        if not isinstance(cur, dict) or k not in cur:
            die(f"report.json missing field {'.'.join(map(str, keys[:i+1]))}")
        cur = cur[k]
    return cur


def main():
    # --- committed GPU run ---------------------------------------------------
    with open(os.path.join(DATA, "report.json")) as fh:
        report = json.load(fh)
    verdict = need(report, "good", "verdict")
    timing = need(verdict, "timing")
    cases = need(verdict, "cases")
    mutants = report["mutants"]
    if not cases or len(cases) != 10:
        die(f"report.json has {len(cases)} cases, expected 10")

    with open(os.path.join(DATA, "gpu-run.log")) as fh:
        runlog = fh.read()

    def log_number(marker, cast=float):
        for line in runlog.splitlines():
            if marker in line:
                tail = line.split(marker)[-1].strip().split()[0]
                return cast(eval(tail.replace("x", "").replace("s", "")
                                 .replace(",", "")))
        die(f"gpu-run.log missing a line containing {marker!r}")

    # total seconds of the GPU run: line "total: 38 s"
    total_s = None
    for line in runlog.splitlines():
        if line.startswith("total:"):
            total_s = float(line.split()[1])
    if total_s is None:
        die("gpu-run.log missing 'total:' line")
    lease = None
    for line in runlog.splitlines():
        if line.startswith("created gl-"):
            lease = line.split()[1]
    if not lease:
        die("gpu-run.log missing 'created gl-' line")

    kernel_ms = timing["kernel_ms"]
    eager_ms = timing["eager_ms"]
    gb_per_s = 2 * 4096 * 4096 * 4 / (kernel_ms / 1e3) / 1e9

    gpu = {
        "kernel_ms": kernel_ms,
        "eager_ms": eager_ms,
        "speedup": timing["speedup"],
        "gb_per_s": round(gb_per_s, 1),
        "worst": verdict["gates"]["correctness"]["worst"],
        "cases": [
            {"shape": c["shape"], "dist": c["dist"],
             "max_abs": c["max_abs_err"], "rowsum": c["rowsum_err"],
             "ok": c["ok"], "seed": c["seed"]}
            for c in cases],
        "gates": {k: v.get("pass") for k, v in verdict["gates"].items()},
        "judge_intact": verdict["judge_intact"],
        "mode": verdict["mode"],
        "mutants": [
            {"name": n,
             "failed": m.get("failed") or [],
             "detail": m.get("detail") or {}}
            for n, m in sorted(mutants.items())],
        "mutants_killed": sum(1 for m in mutants.values() if m.get("failed")),
        "mutants_total": len(mutants),
        "total_s": total_s,
        "lease": lease,
    }

    # --- this sandbox's run ---------------------------------------------------
    for name in ("racedata.json", "timings.jsonl", "row.json"):
        if not os.path.isfile(os.path.join(CLIPS, name)):
            die(f"missing clips/{name}; run record_clips.py first")
    with open(os.path.join(CLIPS, "racedata.json")) as fh:
        racedata = json.load(fh)
    if not racedata["mutants"] or \
            sum(1 for m in racedata["mutants"] if m["killed"]) != len(racedata["mutants"]):
        die("racedata.json does not show every mutant killed")
    if not all(racedata["verdict"]["gates"].values()) or \
            not racedata["verdict"]["judge_intact"]:
        die("racedata.json verdict is not a full PASS")

    race = []
    with open(os.path.join(CLIPS, "timings.jsonl")) as fh:
        for line in fh:
            line = line.strip()
            if line:
                race.append(json.loads(line))
    if len(race) < 30:
        die(f"timings.jsonl has only {len(race)} iterations recorded")
    per_case = {}
    for r in race:
        per_case.setdefault(r["case"], []).append(r)
    cases_out = []
    for idx in sorted(per_case):
        rows = per_case[idx]
        cases_out.append({
            "case": idx, "shape": rows[0]["shape"], "dist": rows[0]["dist"],
            "seed": rows[0]["seed"],
            "kernel_ms": [r["kernel_ms"] for r in rows],
            "eager_ms": [r["eager_ms"] for r in rows]})

    with open(os.path.join(CLIPS, "row.json")) as fh:
        row = json.load(fh)
    if len(row["in"]) != len(row["out"]) or len(row["in"]) < 32:
        die("row.json malformed")

    # --- terminal footage -----------------------------------------------------
    term = os.path.join(CLIPS, "terminal.mp4")
    if not os.path.isfile(term):
        die("missing clips/terminal.mp4; run render_clips.py first")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", term], capture_output=True, text=True)
    try:
        term_s = float(probe.stdout.strip())
    except ValueError:
        die(f"could not probe terminal.mp4 duration: {probe.stdout!r}")
    # Remotion's staticFile() only serves from video/public/; the clip itself
    # stays in gitignored media/clips/
    public = os.path.join(HERE, "video", "public")
    os.makedirs(public, exist_ok=True)
    shutil.copyfile(term, os.path.join(public, "terminal.mp4"))

    scene = {
        "gpu": gpu,
        "cpu": {
            "wall": racedata["wall"],
            "mutants": racedata["mutants"],
            "verdict": racedata["verdict"],
            "cases": cases_out,
        },
        "row": row,
        "terminal": {"clip": "terminal.mp4", "duration_s": term_s},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(scene, fh)
    print(f"prepare_video_data.py: wrote video/src/data/scene.json "
          f"(gpu total {total_s:.0f} s, {len(cases_out)} cpu cases, "
          f"{len(race)} iterations, terminal {term_s:.1f} s)")


if __name__ == "__main__":
    main()
