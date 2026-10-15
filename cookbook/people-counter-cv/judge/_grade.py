#!/usr/bin/env python3
"""Judge driver for the people-counter-cv demo. Invoked by grade.sh; see SPEC.md.

Grades a copied artifact (the artifact under test never touches judge/):
  gate 1 structure   - size, byte-compile, cv2-based, reads the spec at
                       runtime, no truth times hard-coded
  gate 2 run         - deterministic scene generated fresh, the artifact
                       runs and writes crossings.csv
  gate 3 csv-shape   - header, sorted one-hot rows, finite in-range times
  gate 4 oracle      - analytic truth from the scripted trajectories
  gate 5 agreement   - independent MOG2 reference counter, same clip

Prints one JSON verdict on stdout; exit 0 only if every gate passes.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_scene                                    # noqa: E402

JUDGE_VENV_PY = os.path.join(os.path.expanduser("~"), ".venvs",
                             "people-counter-cv", "bin", "python")

MAX_BYTES = 96 * 1024
RUN_TIMEOUT_S = 300

# oracle tolerances (SPEC.md)
COUNT_ERR_MAX = 1          # per direction
RECALL_MIN = 0.95
PRECISION_MIN = 0.95
TIME_MAE_MAX_S = 0.15
TIME_MAX_DEV_S = 0.30
PAIR_WINDOW_S = 0.50       # truth/artifact pairing window
DIR_ACCURACY_MIN = 1.0

# agreement tolerances (vs the judge's MOG2 reference counter)
AGREE_COUNT_DIFF_MAX = 1   # per direction
AGREE_TIME_DEV_MAX_S = 0.35
AGREE_UNPAIRED_MAX = 1     # per direction, per side


# ---------------------------------------------------------------- scene

def scene_cache_dir(spec_path, seed):
    """One render per (spec, seed, generator) - the generator is
    deterministic, so re-rendering identical bytes is pure waste."""
    with open(spec_path, "rb") as fh:
        spec_b = fh.read()
    with open(os.path.join(HERE, "gen_scene.py"), "rb") as fh:
        gen_b = fh.read()
    h = hashlib.sha256(spec_b + gen_b + str(seed).encode()).hexdigest()[:16]
    d = os.path.join(tempfile.gettempdir(), f"people-counter-cv-{h}")
    os.makedirs(d, exist_ok=True)
    return d


def ensure_scene(spec, spec_path, seed, out_dir):
    """Render (or reuse) the clip into out_dir/input/video.avi; -> truth."""
    cache = scene_cache_dir(spec_path, seed)
    vid_path = os.path.join(cache, "video.avi")
    truth_path = os.path.join(cache, "truth.json")
    if not (os.path.exists(vid_path) and os.path.exists(truth_path)):
        actors, truth = gen_scene.build_scene(spec, seed)
        gen_scene.render(spec, actors, vid_path)
        with open(truth_path, "w") as fh:
            json.dump(truth, fh, indent=2)
    with open(truth_path) as fh:
        truth = json.load(fh)
    os.makedirs(os.path.join(out_dir, "input"), exist_ok=True)
    shutil.copy(vid_path, os.path.join(out_dir, "input", "video.avi"))
    return truth


# ---------------------------------------------------------------- csv

def parse_crossings(path):
    """-> [(t, 'east'|'west')]. Raises ValueError on anything malformed."""
    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise ValueError("empty csv")
    if rows[0] != ["t_cross_s", "east", "west"]:
        raise ValueError(f"header {rows[0]} != ['t_cross_s', 'east', 'west']")
    out = []
    for i, row in enumerate(rows[1:], 2):
        if len(row) != 3:
            raise ValueError(f"row {i}: {len(row)} fields, want 3")
        t_s, e_s, w_s = row
        try:
            t = float(t_s)
        except ValueError:
            raise ValueError(f"row {i}: t_cross_s {t_s!r} is not a number")
        if not math.isfinite(t):
            raise ValueError(f"row {i}: non-finite t_cross_s")
        if e_s not in ("0", "1") or w_s not in ("0", "1"):
            raise ValueError(f"row {i}: east/west must be 0 or 1")
        if (e_s == "1") == (w_s == "1"):
            raise ValueError(f"row {i}: exactly one of east/west must be 1")
        out.append((t, "east" if e_s == "1" else "west"))
    if not out:
        raise ValueError("no data rows")
    if any(out[i][0] < out[i - 1][0] for i in range(1, len(out))):
        raise ValueError("rows not sorted by t_cross_s")
    if not all(0.0 <= t <= t_max for t, _ in out):
        raise ValueError(f"t_cross_s outside [0, {t_max}]")
    return out


# ---------------------------------------------------------------- pairing

def pair_events(a, b, window, same_dir=True):
    """Greedy nearest same-direction pairing of event lists -> matches.

    Each a-item pairs with at most one b-item within `window`; earlier
    a-items choose first (events are >= 1.4 s apart in truth, so greedy
    is unambiguous). -> [(i_a, i_b, |dt|)].
    """
    used, matches = set(), []
    for i, (ta, da) in enumerate(a):
        best, bd = None, window
        for j, (tb, db) in enumerate(b):
            if j in used or (same_dir and db != da):
                continue
            d = abs(tb - ta)
            if d < bd:
                best, bd = j, d
        if best is not None:
            used.add(best)
            matches.append((i, best, bd))
    return matches


def counts_by_dir(events):
    return {"east": sum(1 for _, d in events if d == "east"),
            "west": sum(1 for _, d in events if d == "west")}


# ---------------------------------------------------------------- structure

NUM_RE = re.compile(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?")


def load_artifact(path):
    with open(path, "rb") as fh:
        source = fh.read()
    if len(source) > MAX_BYTES:
        raise ValueError(f"artifact exceeds {MAX_BYTES // 1024} KiB")
    compile(source, path, "exec")       # gate 1 byte-compile, no import
    text = source.decode("utf-8", "replace")
    problems = []
    if "cv2" not in text:
        problems.append("artifact does not use the cv2 package")
    if not re.search(r"VideoCapture", text):
        problems.append("artifact does not decode the clip with cv2.VideoCapture")
    if not re.search(r"spec\.json|json\.load|json\.loads", text):
        problems.append("artifact does not read the spec at runtime")
    return text, problems


def hardcode_hits(text, truth_times):
    """Float literals in the artifact within 2 % of a truth event time.

    Only literals with a decimal point or exponent count: a bare `12` is
    a size or a count far more often than a faked crossing time, and a
    faked table of times is what this check exists to catch.
    """
    hits = []
    for m in NUM_RE.finditer(text):
        lit = m.group()
        if "." not in lit and "e" not in lit and "E" not in lit:
            continue
        try:
            v = float(lit)
        except ValueError:
            continue
        for tt in truth_times:
            if abs(v - tt) / tt <= 0.02:
                hits.append({"literal": lit, "near truth t": round(tt, 3)})
                break
    return hits


# ---------------------------------------------------------------- judge core

def check_shas(judge_dir):
    digests = {}
    for root, dirs, files in os.walk(judge_dir):
        dirs.sort()
        if os.path.basename(root) == "__pycache__":
            dirs[:] = []
            continue
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            p = os.path.join(root, name)
            with open(p, "rb") as fh:
                digests[os.path.relpath(p, judge_dir)] = \
                    hashlib.sha256(fh.read()).hexdigest()
    return digests


def main():
    global t_max
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--skip-run", action="store_true",
                    help="score crossings.csv already next to the artifact "
                         "(loop bookkeeping only; selftest never uses this)")
    ap.add_argument("--judge-dir")
    args = ap.parse_args()

    judge_dir = os.path.abspath(args.judge_dir or HERE)
    spec_path = os.path.join(judge_dir, "spec.json")
    with open(spec_path) as fh:
        spec = json.load(fh)
    seed = args.seed if args.seed is not None else spec.get("seed", 0)
    t_max = spec["video"]["duration_s"] + 0.5
    dur = spec["video"]["duration_s"]

    sha_before = check_shas(judge_dir)
    verdict = {"demo": "people-counter-cv",
               "artifact": os.path.basename(args.artifact),
               "seed": seed, "gates": {}, "timing": {}}
    rc = 0
    workdir = tempfile.mkdtemp(prefix="pccv-artifact-")
    refdir = tempfile.mkdtemp(prefix="pccv-ref-")
    try:
        # ---- gate 1: structure
        try:
            text, problems = load_artifact(args.artifact)
        except Exception as exc:
            verdict["gates"]["structure"] = {"pass": False,
                                             "problems": [str(exc)[:300]]}
            rc = 1
        else:
            t0 = time.monotonic()
            truth = ensure_scene(spec, spec_path, seed, workdir)
            verdict["timing"]["scene_s"] = round(time.monotonic() - t0, 1)
            truth_events = [(e["t"], e["dir"]) for e in truth["events"]]
            problems += hardcode_hits(text, [t for t, _ in truth_events])
            verdict["gates"]["structure"] = {
                "pass": not problems, "problems": problems}
            if problems:
                rc = 1

        # ---- gate 2: run
        if rc == 0:
            if args.skip_run:
                src = os.path.join(os.path.dirname(os.path.abspath(
                    args.artifact)), spec["artifact"]["output"])
                problems = []
                if os.path.exists(src):
                    shutil.copy(src, os.path.join(workdir, "crossings.csv"))
                else:
                    problems = [f"missing {spec['artifact']['output']}"]
                verdict["gates"]["run"] = {"pass": not problems,
                                           "problems": problems,
                                           "mode": "skip-run"}
                if problems:
                    rc = 1
            else:
                shutil.copy(args.artifact, os.path.join(workdir, "counter.py"))
                shutil.copy(spec_path, os.path.join(workdir, "spec.json"))
                t0 = time.monotonic()
                try:
                    proc = subprocess.run(
                        [JUDGE_VENV_PY, "counter.py"], cwd=workdir,
                        capture_output=True, text=True, timeout=RUN_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    proc = None
                verdict["timing"]["artifact_run_s"] = round(
                    time.monotonic() - t0, 1)
                problems = []
                if proc is None:
                    problems = [f"timed out after {RUN_TIMEOUT_S} s"]
                elif proc.returncode != 0:
                    problems = [f"exit {proc.returncode}: "
                                + (proc.stderr or proc.stdout)[-300:]]
                elif not os.path.exists(os.path.join(workdir,
                                                     "crossings.csv")):
                    problems = ["no crossings.csv written"]
                verdict["gates"]["run"] = {"pass": not problems,
                                           "problems": problems}
                if problems:
                    rc = 1

        # ---- gates 3-4: csv shape + oracle
        if rc == 0:
            try:
                art = parse_crossings(os.path.join(workdir,
                                                   "crossings.csv"))
            except (ValueError, OSError) as e:
                verdict["gates"]["csv_shape"] = {"pass": False,
                                                 "problems": [f"unreadable: {e}"]}
                rc = 1
            else:
                shape_p = []
                if any(t > dur + 0.25 for t, _ in art):
                    shape_p.append("t_cross_s beyond clip duration")
                verdict["gates"]["csv_shape"] = {"pass": not shape_p,
                                                 "problems": shape_p,
                                                 "rows": len(art)}
                if shape_p:
                    rc = 1

                if rc == 0:
                    tc, ac = counts_by_dir(truth_events), counts_by_dir(art)
                    matches = pair_events(truth_events, art, PAIR_WINDOW_S)
                    devs = [d for _, _, d in matches]
                    mae = sum(devs) / len(devs) if devs else None
                    maxdev = max(devs) if devs else None
                    # direction accuracy: of artifact events with a
                    # same-time truth event (direction ignored), the
                    # fraction whose direction agrees
                    loose = pair_events(truth_events, art, PAIR_WINDOW_S,
                                        same_dir=False)
                    dir_checked = 0
                    dir_right = 0
                    for i, j, _ in loose:
                        dir_checked += 1
                        if truth_events[i][1] == art[j][1]:
                            dir_right += 1
                    metrics = {
                        "truth_counts": tc, "artifact_counts": ac,
                        "count_err": {d: ac[d] - tc[d] for d in ("east", "west")},
                        "matched": len(matches),
                        "recall": round(len(matches) / len(truth_events), 4),
                        "precision": round(len(matches) / len(art), 4),
                        "time_mae_s": None if mae is None else round(mae, 4),
                        "time_max_dev_s": None if maxdev is None
                        else round(maxdev, 4),
                        "direction_accuracy": None if dir_checked == 0
                        else round(dir_right / dir_checked, 4),
                    }
                    problems = []
                    for d in ("east", "west"):
                        if abs(metrics["count_err"][d]) > COUNT_ERR_MAX:
                            problems.append(
                                f"{d} count error {metrics['count_err'][d]:+d} "
                                f"> {COUNT_ERR_MAX}")
                    if metrics["recall"] < RECALL_MIN:
                        problems.append(f"recall {metrics['recall']} < {RECALL_MIN}")
                    if metrics["precision"] < PRECISION_MIN:
                        problems.append(
                            f"precision {metrics['precision']} < {PRECISION_MIN}")
                    if mae is None or mae > TIME_MAE_MAX_S:
                        problems.append(f"time MAE {mae} > {TIME_MAE_MAX_S} s")
                    if maxdev is None or maxdev > TIME_MAX_DEV_S:
                        problems.append(
                            f"time max dev {maxdev} > {TIME_MAX_DEV_S} s")
                    if (metrics["direction_accuracy"] or 0) < DIR_ACCURACY_MIN:
                        problems.append(
                            f"direction accuracy {metrics['direction_accuracy']} "
                            f"< {DIR_ACCURACY_MIN}")
                    verdict["gates"]["oracle"] = {"pass": not problems,
                                                  "problems": problems,
                                                  "metrics": metrics}
                    if problems:
                        rc = 1

        # ---- gate 5: agreement with the judge's MOG2 reference counter
        if rc == 0:
            shutil.copy(spec_path, os.path.join(refdir, "spec.json"))
            os.makedirs(os.path.join(refdir, "input"), exist_ok=True)
            shutil.copy(os.path.join(workdir, "input", "video.avi"),
                        os.path.join(refdir, "input", "video.avi"))
            t0 = time.monotonic()
            ref = subprocess.run(
                [JUDGE_VENV_PY, os.path.join(judge_dir, "ref_count.py")],
                cwd=refdir, capture_output=True, text=True, timeout=300)
            verdict["timing"]["ref_run_s"] = round(time.monotonic() - t0, 1)
            if ref.returncode != 0:
                verdict["gates"]["agreement"] = {
                    "pass": False,
                    "problems": [f"reference counter failed: "
                                 f"{(ref.stderr or ref.stdout)[-200:]}"]}
                rc = 1
            else:
                refv = parse_crossings(os.path.join(refdir, "crossings.csv"))
                problems = []
                for d in ("east", "west"):
                    diff = counts_by_dir(art)[d] - counts_by_dir(refv)[d]
                    if abs(diff) > AGREE_COUNT_DIFF_MAX:
                        problems.append(f"{d} count differs from reference "
                                        f"by {diff:+d}")
                matches = pair_events(art, refv, PAIR_WINDOW_S)
                devs = [d for _, _, d in matches]
                unmatched_a = len(art) - len(matches)
                unmatched_r = len(refv) - len(matches)
                if devs and max(devs) > AGREE_TIME_DEV_MAX_S:
                    problems.append(f"max time deviation vs reference "
                                    f"{max(devs):.3f} s > "
                                    f"{AGREE_TIME_DEV_MAX_S} s")
                if unmatched_a > AGREE_UNPAIRED_MAX or \
                        unmatched_r > AGREE_UNPAIRED_MAX:
                    problems.append(f"unpaired events vs reference: "
                                    f"artifact {unmatched_a}, reference "
                                    f"{unmatched_r}")
                verdict["gates"]["agreement"] = {
                    "pass": not problems, "problems": problems,
                    "metrics": {
                        "reference_counts": counts_by_dir(refv),
                        "paired": len(matches),
                        "unpaired_artifact": unmatched_a,
                        "unpaired_reference": unmatched_r,
                        "max_time_dev_s": round(max(devs), 4) if devs else None}}
                if problems:
                    rc = 1

        sha_after = check_shas(judge_dir)
        verdict["judge_intact"] = sha_before == sha_after
        if not verdict["judge_intact"]:
            rc = 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        shutil.rmtree(refdir, ignore_errors=True)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
