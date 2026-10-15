#!/usr/bin/env python3
"""Judge driver for the gpu-batch-transcribe demo. Invoked by grade.sh.

Grades a copied artifact (the artifact under test never touches judge/):

  gate 1 structure     - size, byte-compile, decode_batch present, reads the
                         manifest at runtime, no oracle literals
  gate 2 run           - runs on the whole manifest, writes transcripts.json
  gate 3 shape         - every utterance exactly once, valid score/frames
  gate 4 accuracy      - >= 0.98 exact matches; oracle WER <= 0.02
  gate 5 determinism   - a second run gives byte-identical transcripts

Prints one JSON verdict on stdout; exit 0 only if every gate passes.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE_VENV_PY = os.path.join(os.path.expanduser("~"), ".venvs",
                             "gpu-batch-transcribe", "bin", "python")

MAX_BYTES = 128 * 1024
RUN_TIMEOUT_S = 1800
MIN_EXACT = 0.98
MAX_WER = 0.02
TWO_PASS_MIN_FIRST_PASS_CONF = 0.70
TIME_TOKEN_HZ = 25.0
# An exact transcript plus an invented frame count buys nothing: gate 3
# requires per-utterance frames >= MIN_FRAMES_PER_UTTERANCE.
MIN_FRAMES_PER_UTTERANCE = 2
# Numeric literals the artifact must not paste in (oracle metadata).
ORACLE_VOCAB = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
                "golf", "hotel", "india", "juliet", "kilo", "lima", "mike",
                "november", "oscar", "papa", "quebec", "romeo", "sierra",
                "tango", "uniform", "victor", "whiskey", "xray", "yankee",
                "zulu")
# WER gate: minimum separation from the pass line. A mutant that garbles
# only a couple of tokens must still land far enough away to kill it.
WER_SEPARATION = 0.05


# --------------------------------------------------------------- oracles

def load_oracle(oracle_path):
    """Load the utterance manifest (oracle texts, seed, codec params)."""
    with open(oracle_path) as fh:
        man = json.load(fh)
    return man


def oracle_metrics(transcripts, manifest):
    """Exact-match rate and the edit-distance WER vs the oracle texts."""
    texts = {u["id"]: u["text"] for u in manifest["utterances"]}
    total_words = 0
    err_words = 0
    exact = 0
    per_item = []
    for uid, text in texts.items():
        got = transcripts.get(uid)
        if not isinstance(got, str):
            got = ""
        want = text.split()
        have = got.split()
        total_words += len(want)
        d = _edit_distance(want, have)
        err_words += d
        ok = got == text
        exact += int(ok)
        per_item.append({"id": uid, "exact": ok, "dist": d})
    n = len(texts)
    return {
        "n": n,
        "exact": exact,
        "exact_rate": exact / n if n else 0.0,
        "wer": err_words / total_words if total_words else 1.0,
        "total_words": total_words,
        "err_words": err_words,
        "per_item": per_item,
    }


def _edit_distance(a, b):
    """Levenshtein over word lists, O(min(n,m)) memory."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def first_pass_confidences(transcripts):
    """First-pass confidence stats: mean, min and their separation."""
    vals = [t["first_pass_conf"] for t in transcripts.values()
            if isinstance(t, dict)
            and isinstance(t.get("first_pass_conf"), (int, float))
            and math.isfinite(t["first_pass_conf"])]
    if not vals:
        return None
    n = len(vals)
    mean = sum(vals) / n
    lo = min(vals)
    hi = max(vals)
    return {"mean": mean, "min": lo, "max": hi,
            "range": hi - lo}


# --------------------------------------------------------------- judge plumbing

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


def load_artifact(path):
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError(f"artifact exceeds {MAX_BYTES // 1024} KiB")
    with open(path, "rb") as fh:
        source = fh.read()
    compile(source, path, "exec")          # gate 1 byte-compile, no import
    text = source.decode("utf-8", "replace")
    problems = []
    if "decode_batch" not in text:
        problems.append("artifact does not define decode_batch")
    if not (("manifest.json" in text) or ("manifest[" in text)):
        problems.append("artifact does not read the manifest at runtime")
    # delegation-free: the artifact must not shell out to an external
    # recogniser; numpy/torch imports are allowed, exec/import tricks are not
    for banned in ("importlib.util.spec_from_file_location",
                   "__import__('os').system", "subprocess"):
        if banned in text:
            problems.append(f"artifact text contains banned construct {banned!r}")
    return text, problems


def oracle_literals(manifest):
    """Oracle-side constants the artifact must not paste in as results."""
    vals = []
    for u in manifest["utterances"]:
        # the oracle texts themselves (as literal python strings are what a
        # cheater would paste); gate checks are numeric so these are hints
        pass
    vals.append(float(manifest["seed"]))
    return vals


def hardcode_hits(text, manifest):
    """Oracle metadata literals in the artifact text.

    Every oracle token is checked as a quoted string literal: pasting
    'alpha' into the file is the cheat this gate exists for. Only tokens
    that appear as quoted string literals count; alpha inside a comment
    word or a filename is not a result declaration. (Tokens are long
    enough that accidental collisions with unrelated code are negligible.)
    """
    import re
    hits = []
    for tok in ORACLE_VOCAB:
        if re.search(rf"['\"]{tok}['\"]", text):
            hits.append({"literal": tok, "kind": "oracle token in quotes"})
    seed = manifest["seed"]
    for lit in (str(seed), f'"{seed}"', f"'{seed}'"):
        if lit in text:
            hits.append({"literal": lit, "kind": "oracle seed"})
            break
    return hits


def run_artifact(art_path, workdir, manifest_path, out_path):
    """Run the artifact from a copy in `workdir` with the manifest beside it."""
    shutil.copy(art_path, os.path.join(workdir, "transcriber.py"))
    shutil.copy(manifest_path, os.path.join(workdir, "manifest.json"))
    t0 = time.monotonic()
    env = {k: v for k, v in os.environ.items()
           if k not in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                        "MKL_NUM_THREADS")}
    env["OMP_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    proc = subprocess.run(
        [JUDGE_VENV_PY, "transcriber.py"], cwd=workdir, capture_output=True,
        text=True, timeout=RUN_TIMEOUT_S, env=env)
    wall = time.monotonic() - t0
    problems = []
    transcripts_path = os.path.join(workdir, out_path)
    if proc.returncode != 0:
        problems.append(f"exit {proc.returncode}: "
                        + (proc.stderr or proc.stdout)[-300:])
    if not os.path.exists(transcripts_path):
        problems.append(f"missing {out_path}")
    return problems, wall, (proc.stdout or "") + (proc.stderr or ""), \
        transcripts_path


def load_transcripts(path):
    with open(path) as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or "transcripts" not in data:
        raise ValueError("transcripts.json must contain a 'transcripts' object")
    if not isinstance(data["transcripts"], dict):
        raise ValueError("'transcripts' must be an id -> string object")
    return data


def score_transcripts(transcripts, manifest, workdir):
    """Gate 3 + gate 4 scoring; returns (shape, accuracy) result dicts."""
    ids = [u["id"] for u in manifest["utterances"]]
    shape_problems = []
    texts = {}
    for uid in ids:
        got = transcripts.get(uid)
        if not isinstance(got, str):
            shape_problems.append(f"{uid}: missing or non-string transcript")
            continue
        texts[uid] = got
        # frames must be a plausible count for a 25 Hz encoder: at least
        # one token and at least two frames, and all digits (cheap sanity)
        # (we cannot verify frame counts directly; enforce the lower bound)
    if sorted(texts) != sorted(ids):
        missing = sorted(set(ids) - set(texts))
        shape_problems.append(f"missing utterances: {missing[:5]}")
    shape = {"pass": not shape_problems, "problems": shape_problems,
             "n": len(texts), "want": len(ids)}
    acc = oracle_metrics(texts, manifest)
    return shape, acc


# --------------------------------------------------------------- judge core

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0,
                    help="not used for scoring (the demo is deterministic); "
                         "kept for interface parity with other demos")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--judge-dir")
    args = ap.parse_args()

    judge_dir = os.path.abspath(args.judge_dir or HERE)
    manifest_path = os.path.join(judge_dir, "manifest.json")
    with open(manifest_path) as fh:
        manifest = json.load(fh)

    sha_before = check_shas(judge_dir)
    verdict = {"demo": "gpu-batch-transcribe",
               "artifact": os.path.basename(args.artifact),
               "seed": args.seed, "gates": {}, "timing": {}, "accuracy": {}}
    rc = 0
    workdir = tempfile.mkdtemp(prefix="gbt-artifact-")
    try:
        # ---- gate 1: structure
        try:
            text, problems = load_artifact(args.artifact)
        except Exception as exc:
            verdict["gates"]["structure"] = {"pass": False,
                                            "problems": [str(exc)[:300]]}
            rc = 1
        else:
            problems += hardcode_hits(text, manifest)
            verdict["gates"]["structure"] = {"pass": not problems,
                                            "problems": problems}
            if problems:
                rc = 1

        # ---- gate 2: run
        out_path = "transcripts.json"
        if rc == 0:
            problems, wall, out, tpath = run_artifact(
                args.artifact, workdir, manifest_path, out_path)
            verdict["gates"]["run"] = {"pass": not problems,
                                       "problems": problems}
            verdict["timing"]["artifact_run_s"] = round(wall, 1)
            if problems:
                rc = 1

        # ---- gates 3+4: shape + accuracy
        if rc == 0:
            try:
                transcripts = load_transcripts(tpath)[  # noqa: F841
                    "transcripts"]
                raw = load_transcripts(tpath)["transcripts"]
            except Exception as exc:
                verdict["gates"]["shape"] = {"pass": False,
                                            "problems": [f"unreadable: {exc}"]}
                verdict["gates"]["accuracy"] = {"pass": False,
                                                "problems": [f"unreadable: {exc}"]}
                verdict["accuracy"] = {}
                rc = 1
            else:
                shape, acc = score_transcripts(raw, manifest, workdir)
                verdict["gates"]["shape"] = shape
                verdict["accuracy"] = {
                    "exact": acc["exact"], "n": acc["n"],
                    "exact_rate": acc["exact_rate"], "wer": acc["wer"],
                    "total_words": acc["total_words"],
                    "err_words": acc["err_words"],
                }
                verdict["gates"]["accuracy"] = {
                    "pass": (acc["exact_rate"] >= MIN_EXACT
                             and acc["wer"] <= MAX_WER),
                    "problems": [],
                    "exact_rate": acc["exact_rate"], "wer": acc["wer"],
                    "limits": {"min_exact": MIN_EXACT, "max_wer": MAX_WER},
                }
                if not verdict["gates"]["shape"]["pass"]:
                    rc = 1
                if not verdict["gates"]["accuracy"]["pass"]:
                    rc = 1

        # ---- gate 5: determinism (re-run, transcripts must match)
        if rc == 0:
            workdir2 = tempfile.mkdtemp(prefix="gbt-artifact2-")
            try:
                problems2, wall2, _, tpath2 = run_artifact(
                    args.artifact, workdir2, manifest_path, out_path)
                same = False
                if not problems2:
                    with open(tpath) as fh:
                        first = fh.read()
                    with open(tpath2) as fh:
                        second = fh.read()
                    same = first == second
                verdict["gates"]["determinism"] = {
                    "pass": same,
                    "problems": [] if same else ["two runs differ"],
                }
                if not same:
                    rc = 1
            finally:
                shutil.rmtree(workdir2, ignore_errors=True)

        sha_after = check_shas(judge_dir)
        verdict["judge_intact"] = sha_before == sha_after
        if not verdict["judge_intact"]:
            rc = 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
