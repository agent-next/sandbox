#!/usr/bin/env python3
"""Judge for the multi-lang-runner demo.

Usage:
    grade.py <artifact_root> [--seed N] [--json out.json] [--cases-dir DIR]

Runs every gate in SPEC.md against the artifact, comparing each solution's
stdout byte-for-byte with the independent Python oracle (oracle.py).

Exit 0 iff every gate passes; otherwise exit 1 and print failures.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ORACLE = os.path.join(HERE, "oracle.py")
GENCASES = os.path.join(HERE, "gencases.py")

LANGS = ["python", "node", "go", "rust", "bash", "c"]
PROBS = ["sumsq", "rle", "primes"]
COMPILED = {"go", "rust", "c"}
INTERPRETED = {"python", "node", "bash"}

COMPILE_TIMEOUT = 60
RUN_TIMEOUT = 10


def here():
    return HERE


def lang_cmd(lang, artifact, prob):
    """Return (compile_cmd_or_None, run_cmd) for one (lang, prob)."""
    d = os.path.join(artifact, "solutions", lang)
    if lang == "go":
        src = os.path.join(d, prob + ".go")
        return (["go", "build", "-o", prob + ".bin", src],
                [os.path.join(d, prob + ".bin")])
    if lang == "rust":
        src = os.path.join(d, prob + ".rs")
        return (["rustc", "-O", "-o", prob + ".bin", src],
                [os.path.join(d, prob + ".bin")])
    if lang == "c":
        src = os.path.join(d, prob + ".c")
        return (["gcc", "-O2", "-o", prob + ".bin", src, "-lm"],
                [os.path.join(d, prob + ".bin")])
    if lang == "python":
        return None, ["python3", os.path.join(d, prob + ".py")]
    if lang == "node":
        return None, ["node", os.path.join(d, prob + ".js")]
    if lang == "bash":
        return None, ["bash", os.path.join(d, prob + ".sh")]
    raise ValueError("unknown lang " + lang)


def run_cmd(cmd, stdin_data=None, timeout=None):
    """Run cmd, return (rc, stdout_bytes, stderr_text, wall)."""
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd, input=stdin_data, capture_output=True, timeout=timeout
        )
        wall = time.time() - t0
        return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace"), wall
    except subprocess.TimeoutExpired:
        wall = time.time() - t0
        return 124, b"", "timeout after %ss" % timeout, wall


def oracle(prob, stdin_text):
    rc, out, err, _ = run_cmd(["python3", ORACLE, prob],
                              stdin_data=stdin_text.encode(), timeout=30)
    if rc != 0:
        raise RuntimeError("oracle failed on %s: %s" % (prob, err))
    return out


def gate_structure(artifact):
    """G1: all 18 solution files + run_all.sh exist."""
    missing = []
    for lang in LANGS:
        for prob in PROBS:
            p = os.path.join(artifact, "solutions", lang, prob + ext_for(lang))
            if not os.path.isfile(p):
                missing.append(p)
    if not os.path.isfile(os.path.join(artifact, "run_all.sh")):
        missing.append(os.path.join(artifact, "run_all.sh"))
    return missing


def ext_for(lang):
    return {"python": ".py", "node": ".js", "go": ".go",
            "rust": ".rs", "bash": ".sh", "c": ".c"}[lang]


def gate_compile(artifact, workdir):
    """G2: every compiled language builds every problem into workdir."""
    failures = []
    timing = {}
    for lang in sorted(COMPILED):
        timing[lang] = {"compile_s": {}, "build_ok": {}}
        for prob in PROBS:
            src = os.path.join(artifact, "solutions", lang, prob + ext_for(lang))
            outbin = os.path.join(workdir, "%s_%s.bin" % (lang, prob))
            if lang == "go":
                cmd = ["go", "build", "-o", outbin, src]
            elif lang == "rust":
                cmd = ["rustc", "-O", "-o", outbin, src]
            else:  # c
                cmd = ["gcc", "-O2", "-o", outbin, src, "-lm"]
            rc, _, err, wall = run_cmd(cmd, timeout=COMPILE_TIMEOUT)
            timing[lang]["compile_s"][prob] = round(wall, 3)
            timing[lang]["build_ok"][prob] = (rc == 0)
            if rc != 0:
                failures.append("%s/%s compile: rc=%d %s" % (lang, prob, rc, err[:200]))
    return failures, timing


def gate_run(artifact, cases_dir, workdir, compile_timing):
    """G3+G5: run every solution on every case, byte-compare to oracle."""
    failures = []
    run_timing = {}
    for lang in LANGS:
        run_timing[lang] = {"run_s": {}}
        for prob in PROBS:
            _, run_cmd_base = lang_cmd(lang, artifact, prob)
            # use prebuilt binary for compiled langs
            if lang in COMPILED:
                outbin = os.path.join(workdir, "%s_%s.bin" % (lang, prob))
                run_cmd_base = [outbin]
            case_files = sorted(
                f for f in os.listdir(cases_dir) if f.startswith(prob + "_") and f.endswith(".in")
            )
            slowest = 0.0
            for cf in case_files:
                stdin_text = open(os.path.join(cases_dir, cf)).read()
                rc, out, err, wall = run_cmd(run_cmd_base,
                                             stdin_data=stdin_text.encode(),
                                             timeout=RUN_TIMEOUT)
                slowest = max(slowest, wall)
                if rc != 0:
                    failures.append("%s/%s run %s: rc=%s %s" % (lang, prob, cf, rc, err[:200]))
                    continue
                expected = oracle(prob, stdin_text)
                if out != expected:
                    failures.append(
                        "%s/%s output mismatch on %s: got %r want %r"
                        % (lang, prob, cf, out[:120], expected[:120])
                    )
            run_timing[lang]["run_s"][prob] = round(slowest, 3)
    return failures, run_timing


def gate_case_count(cases_dir):
    """G4: each problem has >= 3 cases."""
    failures = []
    for prob in PROBS:
        n = len([f for f in os.listdir(cases_dir)
                 if f.startswith(prob + "_") and f.endswith(".in")])
        if n < 3:
            failures.append("%s has %d cases (< 3)" % (prob, n))
    return failures


def gate_run_all(artifact, cases_dir):
    """G6: run_all.sh smoke.

    The spec requires <case_dir>/../out/<lang>_<prob>.txt. run_all.sh writes
    one file per (problem, language) with that name, so count the files under
    <case_dir>/../out/ (creating nothing)."""
    outdir = os.path.join(cases_dir, "..", "out")
    rc, out, err, _ = run_cmd(["bash", os.path.join(artifact, "run_all.sh"), cases_dir],
                              timeout=180)
    if rc != 0:
        return ["run_all.sh exited %d: %s" % (rc, err[:300])]
    # expect 18 non-empty files (3 problems x 6 languages) under out/
    produced = []
    if os.path.isdir(outdir):
        for f in sorted(os.listdir(outdir)):
            p = os.path.join(outdir, f)
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                produced.append(f)
    if len(produced) < 18:
        return ["run_all.sh produced %d non-empty files (< 18)" % len(produced)]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--json", default=None)
    ap.add_argument("--cases-dir", default=None)
    args = ap.parse_args()

    artifact = args.artifact
    if not os.path.isdir(artifact):
        print("grade: artifact dir not found: %s" % artifact, file=sys.stderr)
        return 2

    cases_dir = args.cases_dir or os.path.join(artifact, "cases")
    if not os.path.isdir(cases_dir):
        # generate cases into a temp dir so we never touch the artifact
        cases_dir = os.path.join(tempfile.mkdtemp(prefix="mlr_cases_"), "cases")
        rc, _, err, _ = run_cmd(
            ["python3", GENCASES, "--cases-dir", cases_dir, "--seed", str(args.seed)],
            timeout=60)
        if rc != 0:
            print("grade: gencases failed: %s" % err, file=sys.stderr)
            return 2

    workdir = tempfile.mkdtemp(prefix="mlr_build_")
    all_failures = []
    gates = {}

    # G1
    missing = gate_structure(artifact)
    gates["G1_structure"] = not missing
    all_failures += ["missing: %s" % m for m in missing]

    # G2
    cfails, compile_timing = gate_compile(artifact, workdir)
    gates["G2_compiles"] = not cfails
    all_failures += cfails

    # G3+G5
    rfails, run_timing = gate_run(artifact, cases_dir, workdir, compile_timing)
    gates["G3_oracle_match"] = not any("mismatch" in f for f in rfails)
    gates["G5_run_time"] = not any("rc=" in f and "run" in f for f in rfails)
    all_failures += rfails

    # G4
    g4 = gate_case_count(cases_dir)
    gates["G4_case_count"] = not g4
    all_failures += g4

    # G6
    g6 = gate_run_all(artifact, cases_dir)
    gates["G6_run_all_sh"] = not g6
    all_failures += g6

    # G7 timing table: compile and run wall time per language, per problem.
    # The run times are keyed by problem only (not by case file) so that two
    # same-seed runs give byte-identical verdict JSON once the timing key is
    # dropped: a dict keyed by case name would still be deterministic, but
    # keying by problem keeps the table the SPEC describes.
    timing = {"compile": compile_timing, "run": run_timing}
    gates["G7_timing_table"] = bool(timing["compile"] and timing["run"])

    verdict = {
        "pass": not all_failures,
        "seed": args.seed,
        "gates": gates,
        "failures": all_failures,
        "timing": timing,
    }
    if args.json:
        with open(args.json, "w") as f:
            json.dump(verdict, f, indent=2)
    print(json.dumps(verdict, indent=2))
    return 0 if not all_failures else 1


if __name__ == "__main__":
    sys.exit(main())
