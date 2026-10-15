#!/usr/bin/env python3
"""pr-review-agent judge engine: grade one artifact directory.

    python3 pr_review_judge.py <artifact-dir> [--seed N] [--json out.json]

Prints one JSON verdict on stdout; exits 0 only if every gate in SPEC.md
passes.  Standard library only; pytest is run from the pinned venv that
judge/setup.sh installed.

The judge never trusts the artifact's prose, and it does not trust its own
successful run either: findings are scored against the private answer key in
judge/oracle/GROUND_TRUTH.json, and the reviewer's tests are run twice --
once against the PR tree (must fail) and once against the pristine tree,
which is the fixed version (must pass).  A test that cannot tell the two
trees apart is not evidence of anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
FIXTURE = HERE / "fixture"
REPO = FIXTURE / "repo"
ORACLE = HERE / "oracle" / "GROUND_TRUTH.json"

SEVERITIES = {"info": 0, "minor": 1, "major": 2, "critical": 3}
KINDS = {"off-by-one", "sql-injection", "none-deref", "race", "other"}
LINE_TOLERANCE = 2
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
# pytest exit codes: 0 ok, 1 tests failed, 2 interrupted, 3 internal error,
# 4 usage error, 5 no tests collected.  Only 1 counts as "the test failed".
PYTEST_TESTS_FAILED = 1


class JudgeError(RuntimeError):
    """A condition the judge refuses to grade through (fails closed)."""


def sha256_tree(root: Path) -> str:
    """Hash every file under ``root`` (path + content), skipping caches."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if SKIP_DIRS & set(path.parts) or path.suffix == ".pyc":
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def tree_hash_of_files(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for rel, text in sorted(files.items()):
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(text.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def read_oracle() -> dict:
    if not ORACLE.exists():
        raise JudgeError(
            f"the answer key {ORACLE} is missing; run "
            "python3 judge/fixture/make_fixture.py")
    return json.loads(ORACLE.read_text(encoding="utf-8"))


def materialize(pr: int, dest: Path, expected_sha: str) -> None:
    """Copy the pristine tree to ``dest`` and apply PR ``pr``'s diff.

    The applied tree is hashed and compared against the answer key, so a
    diff that silently does not land (a wrong ``-p`` level, a patched repo)
    fails closed instead of grading an unmodified tree.
    """
    shutil.copytree(REPO, dest)
    diff = FIXTURE / f"pr{pr}.diff"
    proc = subprocess.run(
        ["git", "apply", "-p1", "--whitespace=nowarn", str(diff)],
        cwd=dest, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise JudgeError(
            f"could not apply {diff.name} to the pristine tree: "
            f"{proc.stderr.strip()}")
    actual = sha256_tree(dest)
    if actual != expected_sha:
        raise JudgeError(
            f"PR {pr} tree hash {actual[:16]} != answer key "
            f"{expected_sha[:16]}: the fixture and the answer key disagree")


def pytest_python() -> Path:
    """The pinned pytest interpreter installed by judge/setup.sh."""
    override = os.environ.get("PR_REVIEW_PYTEST_PYTHON")
    candidates = [Path(override)] if override else []
    candidates += [
        Path(os.environ.get("HOME", "/root")) / ".pr-review-agent/venv/bin/python",
        HERE / "venv/bin/python",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    raise JudgeError(
        "the pinned pytest venv is missing; run judge/setup.sh first "
        "(or set PR_REVIEW_PYTEST_PYTHON)")


SUMMARY_RE = re.compile(
    r"(\d+) (passed|failed|error|errors|skipped|deselected)")
COUNT_NAMES = {"passed": "passed", "failed": "failed", "error": "error",
               "errors": "error", "skipped": "skipped"}


def parse_counts(output: str) -> dict:
    """Parse pytest's final summary line (``1 failed, 1 passed in 0.05s``).

    The last line carrying counts is authoritative; pytest prints the
    short-summary FAILED/ERROR lines above it, which have no numbers.
    """
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for line in output.splitlines():
        found = SUMMARY_RE.findall(line)
        if found:
            counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
            for number, what in found:
                counts[COUNT_NAMES[what]] += int(number)
    return counts


NODEID_RE = re.compile(r"^(?:FAILED|ERROR) (\S+)")


def parse_nodeids(output: str) -> list[str]:
    """The failing/erroring test ids, from pytest's short summary.

    Only names go in the verdict: pytest's own output carries wall-clock
    times and, for a timing-dependent failure, the observed value -- neither
    is reproducible, and the SPEC requires a byte-identical verdict.
    """
    return sorted({m.group(1) for m in
                   (NODEID_RE.match(line) for line in output.splitlines())
                   if m})


def run_test(python: Path, tree: Path, test_file: Path) -> dict:
    """Run one reviewer test module inside ``tree`` and report the counts."""
    dest = tree / "tests" / test_file.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(test_file, dest)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tree)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider",
         str(dest.relative_to(tree))],
        cwd=tree, env=env, capture_output=True, text=True, timeout=300,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return {
        "exit_code": proc.returncode,
        "counts": parse_counts(output),
        "failed_tests": parse_nodeids(output),
        "output": output,
    }


def load_artifact(artifact: Path, oracle: dict) -> tuple[dict, list[str]]:
    """Gate G1: shape and field validity.  Returns (reviews, problems)."""
    problems: list[str] = []
    reviews: dict[int, list[dict]] = {}
    for pr in oracle["prs"]:
        pr_dir = artifact / f"pr{pr}"
        if not pr_dir.is_dir():
            problems.append(f"pr{pr}/ is missing")
            continue
        extra = sorted(p.name for p in pr_dir.iterdir()
                       if p.name not in {"review.json", "tests"})
        if extra:
            problems.append(f"pr{pr}/ has unexpected entries: {extra}")
        test_file = pr_dir / "tests" / f"test_pr{pr}.py"
        if not test_file.is_file():
            problems.append(f"pr{pr}/tests/test_pr{pr}.py is missing")
        review_file = pr_dir / "review.json"
        if not review_file.is_file():
            problems.append(f"pr{pr}/review.json is missing")
            continue
        try:
            doc = json.loads(review_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"pr{pr}/review.json is not valid JSON: {exc}")
            continue
        if not isinstance(doc, dict) or doc.get("pr") != pr:
            problems.append(f"pr{pr}/review.json must be an object with pr={pr}")
            continue
        findings = doc.get("findings")
        if not isinstance(findings, list):
            problems.append(f"pr{pr}/review.json has no findings list")
            continue
        tree_dir = artifact / "_trees" / f"pr{pr}"
        for i, finding in enumerate(findings):
            where = f"pr{pr}/review.json findings[{i}]"
            if not isinstance(finding, dict):
                problems.append(f"{where} is not an object")
                continue
            rel = finding.get("file")
            line = finding.get("line")
            severity = finding.get("severity")
            kind = finding.get("kind")
            if not isinstance(rel, str):
                problems.append(f"{where}.file is not a string")
                continue
            target = tree_dir / rel
            if not target.is_file():
                problems.append(f"{where}.file {rel!r} is not in the PR tree")
                continue
            n_lines = len(target.read_text(encoding="utf-8").splitlines())
            if not isinstance(line, int) or isinstance(line, bool):
                problems.append(f"{where}.line is not an integer")
                continue
            if not 1 <= line <= n_lines:
                problems.append(
                    f"{where}.line {line} is outside {rel} (1..{n_lines})")
                continue
            if severity not in SEVERITIES:
                problems.append(f"{where}.severity {severity!r} is not one of "
                                f"{sorted(SEVERITIES)}")
                continue
            if kind not in KINDS:
                problems.append(f"{where}.kind {kind!r} is not one of "
                                f"{sorted(KINDS)}")
                continue
        reviews[pr] = findings
    return reviews, problems


def match_defects(reviews: dict[int, list[dict]], oracle: dict) -> dict:
    """Gate G2: how many planted defects a finding localizes."""
    used: set[tuple[int, int]] = set()
    matched = []
    for defect in oracle["defects"]:
        pr = defect["pr"]
        for i, finding in enumerate(reviews.get(pr, [])):
            if (pr, i) in used:
                continue
            if (finding["file"] == defect["file"]
                    and abs(finding["line"] - defect["line"]) <= LINE_TOLERANCE
                    and SEVERITIES[finding["severity"]] >= SEVERITIES["major"]
                    and finding["kind"] == defect["kind"]):
                used.add((pr, i))
                matched.append({
                    "pr": pr, "kind": defect["kind"],
                    "planted_line": defect["line"],
                    "found_line": finding["line"],
                    "line_error": finding["line"] - defect["line"],
                    "severity": finding["severity"],
                })
                break
    missed = [{"pr": d["pr"], "kind": d["kind"], "file": d["file"],
               "line": d["line"]}
              for d in oracle["defects"]
              if d["pr"] not in {m["pr"] for m in matched}]
    return {"matched": matched, "missed": missed, "caught": len(matched),
            "planted": len(oracle["defects"])}


def false_positives(reviews: dict[int, list[dict]], oracle: dict) -> dict:
    """Gate G3: findings of severity >= major on the clean PRs."""
    bad = []
    for pr in oracle["clean_prs"]:
        for finding in reviews.get(pr, []):
            if SEVERITIES[finding["severity"]] >= SEVERITIES["major"]:
                bad.append({"pr": pr, **finding})
    return {"count": len(bad), "findings": bad,
            "clean_prs": oracle["clean_prs"]}


def grade(artifact: Path, seed: int) -> tuple[dict, dict[tuple[int, str], str]]:
    started = time.monotonic()
    oracle = read_oracle()
    python = pytest_python()

    gates: dict[str, dict] = {}
    timing: dict[str, float] = {}
    raw: dict[tuple[int, str], str] = {}
    tmp = Path(tempfile.mkdtemp(prefix="pr-review-grade-"))
    try:
        trees = tmp / "trees"
        trees.mkdir()
        t0 = time.monotonic()
        fixture_before = sha256_tree(REPO)
        if fixture_before != oracle["pristine_sha256"]:
            raise JudgeError(
                "the pristine tree does not match the answer key: the fixture "
                "has been edited (the fixed tree is not trustworthy)")
        # The fixed version of a defect PR is the pristine tree (the diff
        # reverted).  A clean PR has nothing to fix, so its fixed version is
        # the PR tree itself -- G5 still runs, and a test that cannot even
        # import against the tree it was written for fails closed.
        fixed = trees / "fixed"
        shutil.copytree(REPO, fixed)
        for pr in oracle["prs"]:
            materialize(pr, trees / f"pr{pr}", oracle["pr_sha256"][str(pr)])
        clean_prs = set(oracle["clean_prs"])
        timing["materialize_trees_s"] = round(time.monotonic() - t0, 3)

        # The artifact is graded from a copy; nothing under it may reach the
        # judge's own tree.  Trees are staged next to the copy for G1's
        # existence checks, then removed before any test runs.
        work = tmp / "artifact"
        shutil.copytree(artifact, work)
        staged = work / "_trees"
        staged.mkdir(exist_ok=True)
        for pr in oracle["prs"]:
            shutil.copytree(trees / f"pr{pr}", staged / f"pr{pr}")

        t0 = time.monotonic()
        reviews, problems = load_artifact(work, oracle)
        shutil.rmtree(staged, ignore_errors=True)
        timing["g1_shape_s"] = round(time.monotonic() - t0, 3)
        gates["g1_shape"] = {"passed": not problems, "problems": problems,
                             "prs_graded": sorted(reviews)}

        if problems:
            for name in ("g2_coverage", "g3_clean_prs", "g4_failing_test",
                         "g5_passing_test"):
                gates[name] = {"passed": False, "skipped": "G1 failed"}
        else:
            coverage = match_defects(reviews, oracle)
            gates["g2_coverage"] = {
                "passed": coverage["caught"] == coverage["planted"],
                "caught": coverage["caught"],
                "planted": coverage["planted"],
                "matched": coverage["matched"],
                "missed": coverage["missed"],
            }
            fps = false_positives(reviews, oracle)
            gates["g3_clean_prs"] = {
                "passed": fps["count"] == 0,
                "major_findings_on_clean_prs": fps["count"],
                "findings": fps["findings"],
                "clean_prs": fps["clean_prs"],
            }

            t0 = time.monotonic()
            defect_prs = [d["pr"] for d in oracle["defects"]]
            per_pr = {}
            for pr in oracle["prs"]:
                test_file = work / f"pr{pr}" / "tests" / f"test_pr{pr}.py"
                buggy = run_test(python, trees / f"pr{pr}", test_file)
                fixed_run = run_test(
                    python,
                    trees / f"pr{pr}" if pr in clean_prs else fixed,
                    test_file)
                per_pr[pr] = {
                    "pr": pr,
                    "buggy_exit": buggy["exit_code"],
                    "buggy_counts": buggy["counts"],
                    "buggy_failed_tests": buggy["failed_tests"],
                    "fixed_exit": fixed_run["exit_code"],
                    "fixed_counts": fixed_run["counts"],
                    "fixed_failed_tests": fixed_run["failed_tests"],
                }
                raw[(pr, "buggy")] = buggy["output"]
                raw[(pr, "fixed")] = fixed_run["output"]
            timing["g4_g5_pytest_s"] = round(time.monotonic() - t0, 3)

            g4_fail = [
                {"pr": pr, "exit_code": r["buggy_exit"],
                 "counts": r["buggy_counts"],
                 "why": "no test failed on the buggy tree"
                        if r["buggy_exit"] != PYTEST_TESTS_FAILED
                        else "no test was collected"}
                for pr, r in per_pr.items()
                if pr in defect_prs
                and not (r["buggy_exit"] == PYTEST_TESTS_FAILED
                         and r["buggy_counts"]["failed"] >= 1)
            ]
            g5_fail = [
                {"pr": pr, "exit_code": r["fixed_exit"],
                 "counts": r["fixed_counts"],
                 "why": "the test does not pass on the fixed tree"}
                for pr, r in per_pr.items()
                if pr in defect_prs
                and not (r["fixed_exit"] == 0
                         and r["fixed_counts"]["passed"] >= 1)
            ]
            gates["g4_failing_test"] = {
                "passed": not g4_fail, "prs": per_pr,
                "failures": g4_fail,
                "rule": "buggy tree: pytest exit 1 with >= 1 failed test",
            }
            gates["g5_passing_test"] = {
                "passed": not g5_fail, "failures": g5_fail,
                "rule": "fixed tree: pytest exit 0 with >= 1 passed test "
                        "(defect PRs: the pristine tree; clean PRs: the PR "
                        "tree, which is already clean)",
            }

        # G6: nothing the artifact shipped may have been able to reach the
        # judge -- no judge tree inside the artifact, and the fixture the
        # answer key describes must be exactly what was on disk when the
        # trees were built (the working copies get test files written into
        # them, so hash the source fixture, not the copies).
        t0 = time.monotonic()
        leaks = [p.relative_to(work).as_posix() for p in work.rglob("*")
                 if p.name in {"oracle", "GROUND_TRUTH.json", "fixture"}]
        if sha256_tree(REPO) != fixture_before:
            leaks.append("judge/fixture/repo changed during grading")
        timing["g6_isolation_s"] = round(time.monotonic() - t0, 3)
        gates["g6_isolation"] = {"passed": not leaks, "problems": leaks}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed_gate = next((name for name in
                        ("g1_shape", "g2_coverage", "g3_clean_prs",
                         "g4_failing_test", "g5_passing_test", "g6_isolation")
                        if not gates.get(name, {}).get("passed")), None)
    timing["total_s"] = round(time.monotonic() - started, 3)
    return {
        "artifact": str(artifact),
        "seed": seed,
        "passed": failed_gate is None,
        "failed_gate": failed_gate,
        "gates": gates,
        "timing": timing,
        "tool": {"pytest_python": str(python),
                 "python": sys.version.split()[0]},
    }, raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", help="artifact directory to grade")
    ap.add_argument("--seed", type=int, default=20261015,
                    help="seed for the (deterministic) grading run")
    ap.add_argument("--json", help="also write the verdict JSON here")
    args = ap.parse_args()

    artifact = Path(args.artifact).resolve()
    if not artifact.is_dir():
        print(json.dumps({"passed": False, "failed_gate": "g1_shape",
                          "reason": f"{artifact} is not a directory"},
                         indent=2))
        return 1
    try:
        verdict, raw = grade(artifact, args.seed)
    except JudgeError as exc:
        print(json.dumps({"artifact": str(artifact), "passed": False,
                          "failed_gate": "judge_error", "reason": str(exc)},
                         indent=2))
        return 1
    # The verdict on stdout is deterministic; pytest's own output (which
    # carries wall-clock times and observed values) goes to stderr, so a
    # human can still see *why* a gate failed without polluting the JSON.
    for (pr, side), output in sorted(raw.items()):
        if not output.strip():
            continue
        keep = [line for line in output.splitlines()
                if line.startswith(("FAILED", "ERROR"))]
        if keep:
            print(f"grade: PR {pr} {side} tree -- {'; '.join(keep)}",
                  file=sys.stderr)
    text = json.dumps(verdict, indent=2, sort_keys=False)
    print(text)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
