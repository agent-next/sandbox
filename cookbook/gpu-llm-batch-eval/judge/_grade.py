#!/usr/bin/env python3
"""Grade an LLM batch-eval bundle. See SPEC.md for the gates.

Runs the artifact (or reads a bundle it produced) from a copy in a fresh
temp directory, re-extracts every final answer with the judge's own
extractor (`extract.py`), and compares against the pinned gold answers in
`problems.json`. Prints one JSON verdict on stdout and exits 0 only if
every gate passes.

Usage:
    _grade.py <artifact.py | bundle.json> [--seed N] [--json out.json]
              [--floor F] [--device D]
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract as judge_extract  # noqa: E402  (the judge's own extractor)

REQUIRED = {
    "model": str,
    "problems_sha256": str,
    "n_problems": int,
    "batch_size": int,
    "max_new_tokens": int,
    "temperature": (int, float),
    "greedy": bool,
    "device": str,
    "throughput_tok_s": (int, float),
    "generated_tokens": int,
    "wall_time_s": (int, float),
    "reported_accuracy": (int, float),
    "generations": list,
}
ACCURACY_BAND = 0.005          # 0.5 percentage points, both directions
THROUGHPUT_TOL = 0.01          # 1 %
MIN_THROUGHPUT_TOK_S = 50.0    # a CPU-rate number on a GPU run is a red flag
UNTRUNCATED_FRACTION = 0.90    # >= 90 % of generations must end naturally


def die(msg, code=2):
    print(f"_grade.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tree_sha256(root):
    """sha256 of every file under `root`, keyed by relative path."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            out[rel] = sha256_file(path)
    return out


def load_problems(judge_dir):
    path = os.path.join(judge_dir, "problems.json")
    with open(path) as fh:
        doc = json.load(fh)
    return path, doc


def run_artifact(artifact, workdir, timeout, device, seed):
    """Copy the artifact into a fresh dir and run it there. Returns (rc, stderr)."""
    run_dir = os.path.join(workdir, "run")
    os.makedirs(run_dir, exist_ok=True)
    local = os.path.join(run_dir, os.path.basename(artifact))
    shutil.copy2(artifact, local)
    # the artifact must not see judge/; it gets the model dir and problems
    # through the environment only
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["LLM_EVAL_DEVICE"] = device
    env["LLM_EVAL_SEED"] = str(seed)
    proc = subprocess.run([sys.executable, local], cwd=run_dir, env=env,
                          capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stderr[-4000:], run_dir


def find_bundle(artifact, run_dir):
    """A .py artifact writes bundle.json next to itself; a .json is the bundle."""
    if artifact.endswith(".json"):
        return artifact
    candidate = os.path.join(run_dir, "bundle.json")
    return candidate if os.path.exists(candidate) else None


def check_structure(bundle, problems_doc, problems_sha):
    """Gate 1. Returns (ok, problems, detail)."""
    problems = []
    if not isinstance(bundle, dict):
        problems.append("bundle is not a JSON object")
        return False, problems, {}
    for field, kind in REQUIRED.items():
        if field not in bundle:
            problems.append(f"missing field {field}")
        elif isinstance(bundle[field], bool) and kind is not bool:
            problems.append(f"field {field} is a bool, expected {kind}")
        elif not isinstance(bundle[field], kind):
            problems.append(f"field {field} has type "
                            f"{type(bundle[field]).__name__}, expected "
                            f"{getattr(kind, '__name__', kind)}")
    if problems:
        return False, problems, {}

    gens = bundle["generations"]
    if bundle["n_problems"] != problems_doc["n"]:
        problems.append(f"n_problems {bundle['n_problems']} != "
                        f"{problems_doc['n']}")
    if len(gens) != bundle["n_problems"]:
        problems.append(f"len(generations) {len(gens)} != "
                        f"n_problems {bundle['n_problems']}")
    idx = [g.get("i") for g in gens if isinstance(g, dict)]
    if len(idx) != len(gens):
        problems.append("a generation entry is not an object")
    elif sorted(idx) != list(range(len(gens))):
        problems.append("generation i values are not exactly 0..n-1")
    if bundle["problems_sha256"] != problems_sha:
        problems.append("problems_sha256 does not match judge/problems.json")
    if float(bundle["temperature"]) != 0.0:
        problems.append(f"temperature {bundle['temperature']} is not 0")
    if bundle["greedy"] is not True:
        problems.append("greedy is not true")
    for name in ("generated_tokens", "wall_time_s", "throughput_tok_s",
                 "reported_accuracy"):
        value = bundle[name]
        if not isinstance(value, (int, float)) or value != value \
                or value in (float("inf"), float("-inf")):
            problems.append(f"{name} is not a finite number")
        elif name in ("generated_tokens", "wall_time_s",
                      "throughput_tok_s") and value <= 0:
            problems.append(f"{name} must be positive, got {value}")
    if bundle["max_new_tokens"] <= 0 or bundle["batch_size"] <= 0:
        problems.append("max_new_tokens and batch_size must be positive")

    # per-generation: non-empty string, question aligned with index i
    by_i = {}
    for g in gens:
        if not isinstance(g, dict):
            continue
        by_i[g.get("i")] = g
    for row in problems_doc["problems"]:
        g = by_i.get(row["i"])
        if g is None:
            continue
        text = g.get("generation")
        if not isinstance(text, str) or not text.strip():
            problems.append(f"problem {row['i']}: generation is empty")
        if g.get("question") != row["question"]:
            problems.append(f"problem {row['i']}: question does not match "
                            "problems.json (misaligned)")
    return (not problems), problems, {"by_i": by_i}


def check_accuracy(bundle, problems_doc, by_i, floor):
    """Gate 2: the judge re-extracts and scores against gold."""
    rows = problems_doc["problems"]
    correct = 0
    mismatched_artifact = []
    unparsed = []
    for row in rows:
        g = by_i.get(row["i"]) or {}
        gen = g.get("generation")
        got = judge_extract.extract(gen)
        gold = row["gold"]
        if got is None:
            unparsed.append(row["i"])
        elif got == gold:
            correct += 1
        claimed = g.get("extracted_answer")
        if claimed is not None and str(claimed).replace(",", "") not in (
                "", None) and judge_extract._normalise(str(claimed)) != got:
            mismatched_artifact.append(row["i"])
    acc = correct / len(rows)
    reported = float(bundle["reported_accuracy"])
    problems = []
    if acc < floor:
        problems.append(f"judge_accuracy {acc:.4f} < floor {floor:.4f}")
    if acc < reported - ACCURACY_BAND:
        problems.append(f"judge_accuracy {acc:.4f} is more than "
                        f"{ACCURACY_BAND * 100:.1f} pt below reported "
                        f"{reported:.4f} (reported accuracy inflated)")
    if acc > reported + ACCURACY_BAND:
        problems.append(f"judge_accuracy {acc:.4f} is more than "
                        f"{ACCURACY_BAND * 100:.1f} pt above reported "
                        f"{reported:.4f} (reported accuracy understated)")
    return (not problems), problems, {
        "judge_accuracy": round(acc, 6),
        "reported_accuracy": round(reported, 6),
        "correct": correct,
        "n": len(rows),
        "unparsed": len(unparsed),
        "extractor_disagreements": len(mismatched_artifact),
    }


def check_generations(bundle, by_i, problems_doc):
    """Gate 3: generations must not be truncated mid-answer."""
    max_new = bundle["max_new_tokens"]
    n = len(problems_doc["problems"])
    untruncated = 0
    short = []
    for row in problems_doc["problems"]:
        g = by_i.get(row["i"]) or {}
        text = g.get("generation") or ""
        # an answer that stops at the cap has no closing marker at all
        natural = judge_extract.extract(text) is not None and \
            ("final answer" in text.lower() or "####" in text
             or text.rstrip().endswith((".", "!", "?", "`")))
        declared = g.get("max_new_tokens")
        capped = isinstance(declared, int) and declared >= max_new
        if natural and not capped:
            untruncated += 1
        else:
            short.append(row["i"])
    frac = untruncated / n
    problems = []
    if frac < UNTRUNCATED_FRACTION:
        problems.append(f"only {frac:.2%} of generations end naturally "
                        f"(need >= {UNTRUNCATED_FRACTION:.0%}); "
                        f"{len(short)} truncated")
    return (not problems), problems, {
        "untruncated_fraction": round(frac, 6),
        "truncated": len(short),
        "max_new_tokens": max_new,
    }


def check_tokens(bundle):
    """Gate 4: the bundle's own numbers must be self-consistent."""
    tokens = float(bundle["generated_tokens"])
    wall = float(bundle["wall_time_s"])
    reported = float(bundle["throughput_tok_s"])
    derived = tokens / wall
    rel = abs(derived - reported) / max(derived, 1e-9)
    problems = []
    if rel > THROUGHPUT_TOL:
        problems.append(f"generated_tokens/wall_time_s = {derived:.2f} tok/s "
                        f"differs from throughput_tok_s {reported:.2f} by "
                        f"{rel * 100:.2f}% (limit {THROUGHPUT_TOL * 100:.0f}%)")
    if derived <= MIN_THROUGHPUT_TOK_S:
        problems.append(f"{derived:.2f} tok/s is below the "
                        f"{MIN_THROUGHPUT_TOK_S:.0f} tok/s GPU floor")
    return (not problems), problems, {
        "derived_tok_s": round(derived, 4),
        "reported_tok_s": round(reported, 4),
        "rel_error": round(rel, 8),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", help="eval.py or a bundle.json")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", metavar="PATH")
    ap.add_argument("--judge-dir", default=HERE)
    ap.add_argument("--floor", type=float, default=None,
                    help="override the accuracy floor (default: floor.txt)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--timeout", type=float, default=1800.0)
    args = ap.parse_args()

    judge_dir = os.path.abspath(args.judge_dir)
    if args.floor is None:
        with open(os.path.join(judge_dir, "floor.txt")) as fh:
            args.floor = float(fh.read().split()[0])

    problems_path, problems_doc = load_problems(judge_dir)
    problems_sha = sha256_file(problems_path)
    before = tree_sha256(judge_dir)

    workdir = tempfile.mkdtemp(prefix="llm-eval-grade-")
    t0 = time.monotonic()
    gates = {}
    artifact_error = None
    try:
        bundle_path = find_bundle(args.artifact, workdir)
        if bundle_path is None:
            rc, err, run_dir = run_artifact(args.artifact, workdir,
                                            args.timeout, args.device,
                                            args.seed)
            if rc != 0:
                artifact_error = (f"artifact exited {rc}: "
                                  f"{err.strip()[-500:]}")
            bundle_path = find_bundle(args.artifact, run_dir)
        if bundle_path is None or not os.path.exists(bundle_path):
            verdict = {
                "gates": {"structure": {
                    "pass": False,
                    "problems": [artifact_error or
                                 "artifact produced no bundle.json"],
                }},
                "judge_intact": True,
                "seed": args.seed,
                "timing": {"grade_s": round(time.monotonic() - t0, 3)},
            }
            emit(verdict, args.json)
            raise SystemExit(1)
        try:
            with open(bundle_path) as fh:
                bundle = json.load(fh)
        except (OSError, ValueError) as exc:
            verdict = {
                "gates": {"structure": {
                    "pass": False,
                    "problems": [f"bundle is not valid JSON: {exc}"],
                }},
                "judge_intact": True,
                "seed": args.seed,
                "timing": {"grade_s": round(time.monotonic() - t0, 3)},
            }
            emit(verdict, args.json)
            raise SystemExit(1)

        ok, problems, ctx = check_structure(bundle, problems_doc, problems_sha)
        gates["structure"] = {"pass": ok, "problems": problems}
        by_i = ctx.get("by_i", {})

        if ok:
            ok2, p2, m2 = check_accuracy(bundle, problems_doc, by_i, args.floor)
            gates["judge_accuracy"] = dict({"pass": ok2, "problems": p2}, **m2)
            ok3, p3, m3 = check_generations(bundle, by_i, problems_doc)
            gates["generations"] = dict({"pass": ok3, "problems": p3}, **m3)
            ok4, p4, m4 = check_tokens(bundle)
            gates["token_accounting"] = dict({"pass": ok4, "problems": p4}, **m4)
        else:
            for name in ("judge_accuracy", "generations", "token_accounting"):
                gates[name] = {"pass": False,
                               "problems": ["skipped: structure failed"]}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    after = tree_sha256(judge_dir)
    intact = before == after
    changed = sorted(set(before) ^ set(after)) or \
        sorted(k for k in before if before[k] != after.get(k))

    verdict = {
        "artifact": os.path.basename(args.artifact),
        "gates": gates,
        "judge_intact": intact,
        "judge_changed": changed,
        "seed": args.seed,
        "floor": args.floor,
        "timing": {"grade_s": round(time.monotonic() - t0, 3)},
    }
    all_ok = all(g.get("pass") for g in gates.values()) and intact
    emit(verdict, args.json)
    raise SystemExit(0 if all_ok else 1)


def emit(verdict, path):
    text = json.dumps(verdict, indent=2, sort_keys=True)
    if path:
        with open(path, "w") as fh:
            fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
