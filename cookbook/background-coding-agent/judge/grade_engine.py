#!/usr/bin/env python3
"""background-coding-agent judge engine (stdlib only), called by grade.sh.

Grades one delivery — a `delivery.patch` plus the `PR.md` beside it —
against the gates in SPEC.md.  The patch is applied to a temp copy of the
pinned fixture; the hidden acceptance suite and the independent reference
implementation live in this directory and are copied in, read-only.

Gates:
  G1 patch       fixture matches judge/FIXTURE.sha256; patch parses and
                 applies cleanly; 1..20 files, >=1 under measurectl/,
                 <= 2000 changed lines; PR.md present and >= 200 chars.
  G2 integrity   patch touches no test or tool-config file and no path
                 escaping the checkout; tests/ re-hashed after applying.
  G3 regression  the fixture's own suite passes on the patched checkout.
  G4 acceptance  the hidden suite passes on the patched checkout.
  G5 lint        pinned ruff with the judge's own config reports 0 issues.
  G6 oracle      the emitted JSON matches judge/reference.py's independent
                 computation to 1e-9 relative on the sample plus two
                 seeded synthetic inputs, and satisfies the schema mask
                 and min/mean/max/count/sum identities.
  G7 pr          PR.md has a summary and a test plan and mentions every
                 file the patch changes.

The artifact is never executed inside judge/; the judge hashes its own
tree before and after grading and fails closed if anything changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference  # noqa: E402  (judge-owned oracle)

JDIR = Path(__file__).resolve().parent
DEMO = JDIR.parent
FIXTURE = DEMO / "fixture"
ACCEPTANCE = JDIR / "acceptance"
RUFF_CONFIG = JDIR / "ruff.toml"
MANIFEST = JDIR / "FIXTURE.sha256"

SEED_DEFAULT = 20261015
MAX_FILES = 20
MAX_LINES = 2000
MIN_PR_CHARS = 200
MIN_REGRESSION_TESTS = 12
MIN_ACCEPTANCE_TESTS = 18
REL_TOL = 1e-9
CLI_TIMEOUT = 20

FORBIDDEN_BASENAMES = {
    "pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "pytest.ini",
    "conftest.py", "ruff.toml", ".ruff.toml",
    "version.py", "__init__.py",
}
FORBIDDEN_PREFIXES = ("tests/",)
# Interpreter startup hooks: the checkout root is on PYTHONPATH for the
# test and CLI subprocesses, and `site` imports `sitecustomize` at startup,
# so a planted sitecustomize.py could rewrite pytest's results.  New files
# with these names are refused.
STARTUP_HOOKS = {"sitecustomize.py", "usercustomize.py"}
JSON_SCHEMA = "measurectl/summary/v1"
TOP_KEYS = {"schema", "total_count", "metrics"}
METRIC_KEYS = {"name", "count", "sum", "mean", "min", "max"}
# PR.md headings the judge accepts (lower-cased, whitespace-normalised).
SUMMARY_HEADS = ("summary", "what changed", "changes", "overview")
PLAN_HEADS = ("test plan", "testing", "tests", "how tested", "verification")


class GateFail(Exception):
    def __init__(self, gate: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.gate, self.message = gate, message
        self.extra = extra or {}


# --------------------------------------------------------------------------
# tool discovery
# --------------------------------------------------------------------------
def find_tool(name: str) -> str | None:
    """Locate pytest/ruff: judge venvs first, then PATH."""
    root = Path(os.environ.get("MEASURECTL_JUDGE_HOME",
                               Path.home() / ".local/share/measurectl-judge"))
    if name == "pytest":
        cand = root / "pytest-venv" / "bin" / "pytest"
    else:
        cand = root / "ruff-venv" / "bin" / "ruff"
    if cand.is_file() and os.access(cand, os.X_OK):
        return str(cand)
    return shutil.which(name)


def tool_version(tool: str) -> str:
    try:
        out = subprocess.run([tool, "--version"], capture_output=True,
                             text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return "?"
    m = re.search(r"\d+\.\d+(?:\.\d+)?", out)
    return m.group(0) if m else out.strip().splitlines()[0] if out.strip() else "?"


def child_env(root: Path, extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["MEASURECTL_CHECKOUT"] = str(root)
    env.pop("PYTEST_ADDOPTS", None)
    if extra:
        env.update(extra)
    return env


# --------------------------------------------------------------------------
# fixture integrity
# --------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_entries() -> dict[str, str]:
    if not MANIFEST.is_file():
        raise GateFail("patch", f"judge/FIXTURE.sha256 missing "
                                f"(run judge/make_manifest.sh)")
    entries = {}
    for line in MANIFEST.read_text().splitlines():
        if not line.strip():
            continue
        digest, _, rel = line.partition("  ")
        entries[rel.strip()] = digest.strip()
    return entries


def check_fixture(root: Path, entries: dict[str, str]) -> None:
    """Fail closed if the checkout differs from the pinned manifest."""
    for rel, digest in sorted(entries.items()):
        path = root / rel
        if not path.is_file():
            raise GateFail("patch", f"fixture file missing: {rel}")
        if sha256_file(path) != digest:
            raise GateFail("patch", f"fixture file modified: {rel} "
                                    f"(does not match judge/FIXTURE.sha256)")
    on_disk = {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
        and not p.name.endswith(".pyc")
    }
    extra = sorted(on_disk - set(entries))
    if extra:
        raise GateFail("patch", "fixture has files not in the manifest: "
                                + ", ".join(extra[:5]))


# --------------------------------------------------------------------------
# patch parsing
# --------------------------------------------------------------------------
DIFF_HEADER = re.compile(r"^diff --git a/(?P<a>.+?) b/(?P<b>.+?)\s*$")
FILE_HEADER = re.compile(r"^\+\+\+ (?:b/)?(?P<path>\S+)")
NEW_FILE = re.compile(r"^new file mode ")
DELETED_FILE = re.compile(r"^deleted file mode ")


class PatchInfo:
    def __init__(self) -> None:
        self.files: list[str] = []
        self.new_files: set[str] = set()
        self.added = 0
        self.removed = 0
        self.hunks = 0
        self.binary = False


def parse_patch(text: str) -> PatchInfo:
    info = PatchInfo()
    seen: set[str] = set()
    current: str | None = None
    for line in text.splitlines():
        header = DIFF_HEADER.match(line)
        if header:
            current = header.group("b")
            if current not in seen:
                seen.add(current)
                info.files.append(current)
            continue
        if FILE_HEADER.match(line) and not info.files:
            current = FILE_HEADER.match(line).group("path")
            if current not in seen:
                seen.add(current)
                info.files.append(current)
            continue
        if NEW_FILE.match(line) and current is not None:
            info.new_files.add(current)
            continue
        if line.startswith("@@"):
            info.hunks += 1
        elif line.startswith("+") and not line.startswith("+++"):
            info.added += 1
        elif line.startswith("-") and not line.startswith("---"):
            info.removed += 1
        elif line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            info.binary = True
    return info


REPO_PREFIX = "cookbook/background-coding-agent/fixture/"


def normalise_path(path: str) -> str:
    """Map a patch path onto the fixture root (accept repo-rooted paths)."""
    if path.startswith(REPO_PREFIX):
        return path[len(REPO_PREFIX):]
    return path


def _reroot_path(path: str) -> str:
    """Strip the leading a/ or b/ and the repository prefix, if present."""
    prefix = ""
    if path.startswith(("a/", "b/")):
        prefix, path = path[:2], path[2:]
    return prefix + normalise_path(path)


def reroot_patch(text: str, files: list[str]) -> str:
    """Strip the repository prefix from a repo-rooted patch.

    A patch produced from the repository root has paths like
    `cookbook/background-coding-agent/fixture/measurectl/cli.py`; the judge
    grades against the fixture root, so those header paths are rewritten.
    Returns the text unchanged unless every changed path carries the
    prefix (a mixed patch is left for `git apply` to reject).
    """
    if not files or not all(f.startswith(REPO_PREFIX) for f in files):
        return text
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        newline = line[len(stripped):]
        header = DIFF_HEADER.match(stripped)
        if header:
            out.append(f"diff --git {_reroot_path('a/' + header.group('a'))} "
                       f"{_reroot_path('b/' + header.group('b'))}{newline}")
            continue
        if stripped.startswith(("--- ", "+++ ")) and "/dev/null" not in stripped:
            marker, _, path = stripped.partition(" ")
            out.append(f"{marker} {_reroot_path(path)}{newline}")
            continue
        out.append(line)
    return "".join(out)


def check_paths(files: list[str]) -> list[str]:
    """Reject absolute paths, parent escapes and anything outside fixture/."""
    bad = []
    for path in files:
        norm = normalise_path(path)
        if path.startswith("/") or norm.startswith("/"):
            bad.append(path)
            continue
        if norm.startswith("..") or "/../" in norm or norm.endswith("/.."):
            bad.append(path)
            continue
        if norm in ("", "."):
            bad.append(path)
    return bad


# --------------------------------------------------------------------------
# PR.md
# --------------------------------------------------------------------------
def normalise_head(text: str) -> str:
    return re.sub(r"[^a-z ]+", " ", text.lower()).strip()


def heading_lines(text: str) -> list[str]:
    heads = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heads.append(stripped.lstrip("#").strip())
        elif stripped.endswith(":") and len(stripped) < 60:
            heads.append(stripped[:-1].strip())
    return heads


def check_pr(text: str, files: list[str]) -> dict:
    if len(text) < MIN_PR_CHARS:
        raise GateFail("pr", f"PR.md is {len(text)} chars; need "
                             f">= {MIN_PR_CHARS}")
    heads = [normalise_head(h) for h in heading_lines(text)]
    has_summary = any(h in SUMMARY_HEADS for h in heads)
    has_plan = any(h in PLAN_HEADS for h in heads)
    if not has_summary:
        raise GateFail("pr", "PR.md has no summary heading "
                             f"(looked for one of {SUMMARY_HEADS})")
    if not has_plan:
        raise GateFail("pr", "PR.md has no test-plan heading "
                             f"(looked for one of {PLAN_HEADS})")
    lowered = text.lower()
    missing = []
    for path in files:
        norm = normalise_path(path)
        base = Path(norm).name
        if norm.lower() not in lowered and base.lower() not in lowered:
            missing.append(norm)
    if missing:
        raise GateFail("pr", "PR.md does not mention "
                             f"{len(missing)} changed file(s)",
                       {"missing": missing})
    return {"passed": True, "chars": len(text),
            "summary_heading": True, "test_plan_heading": True,
            "files_mentioned": len(files)}


# --------------------------------------------------------------------------
# running the artifact
# --------------------------------------------------------------------------
def run_pytest(tool: str, root: Path, targets: list[str], timeout: int) -> dict:
    cmd = [tool, "-q", "-p", "no:cacheprovider", "--no-header", *targets]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=str(root), env=child_env(root),
                              timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {"exit": 124, "summary": f"pytest exceeded {timeout} s",
                "counts": {}, "output": str(exc)}
    out = (proc.stdout or "") + (proc.stderr or "")
    summary = ""
    for line in reversed(out.splitlines()):
        if re.search(r"\d+ (passed|failed|error)", line):
            summary = line.strip()
            break
    numbers = {k: int(v) for v, k in re.findall(
        r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)", out)}
    return {"exit": proc.returncode, "summary": summary, "counts": numbers,
            "output": out}


def collected_count(result: dict) -> int:
    counts = result["counts"]
    return (counts.get("passed", 0) + counts.get("failed", 0)
            + counts.get("error", 0) + counts.get("errors", 0)
            + counts.get("skipped", 0) + counts.get("xfailed", 0)
            + counts.get("xpassed", 0))


def run_ruff(tool: str, root: Path) -> dict:
    cmd = [tool, "check", "--config", str(RUFF_CONFIG),
           "--no-cache", "--output-format", "concise", "."]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=str(root), env=child_env(root), timeout=180)
    except subprocess.TimeoutExpired as exc:
        return {"exit": 124, "findings": [f"ruff exceeded 180 s: {exc}"],
                "output": str(exc)}
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    findings = [ln for ln in out.splitlines()
                if re.match(r"^\S+:\d+:\d+:", ln)]
    return {"exit": proc.returncode, "findings": findings, "output": out}


# --------------------------------------------------------------------------
# the oracle: emitted JSON vs an independent computation
# --------------------------------------------------------------------------
def synth_inputs(seed: int) -> list[tuple[str, str]]:
    """Two seeded CSV inputs the artifact has never seen, with names that
    sort before and after the sample's and magnitudes over decades."""
    rng = random.Random(seed)
    cases: list[tuple[str, str]] = []

    lines = ["# synthetic A", "metric,value"]
    names = ["Alpha", "zeta", "Mid_2"]
    for name in names:
        for _ in range(rng.randint(1, 6)):
            magnitude = 10 ** rng.randint(-4, 4)
            value = magnitude * rng.uniform(-1.0, 1.0)
            lines.append(f"{name},{value!r}")
    cases.append(("synthetic-a.csv", "\n".join(lines) + "\n"))

    lines = ["metric,value"]
    lines.append(f"solo,{rng.uniform(-1000.0, 1000.0)!r}")
    for name in ("beta", "alpha"):
        for _ in range(rng.randint(2, 5)):
            lines.append(f"{name},{rng.uniform(-5.0, 5.0)!r}")
    cases.append(("synthetic-b.csv", "\n".join(lines) + "\n"))
    return cases


def close(a: float, b: float) -> bool:
    if a == b:
        return True
    return abs(a - b) <= REL_TOL * max(1.0, abs(a), abs(b))


def compare_document(got: dict, want: dict, label: str) -> list[str]:
    """Return a list of human-readable mismatches (empty means agreement)."""
    problems: list[str] = []
    if set(got) != TOP_KEYS:
        problems.append(f"{label}: top-level keys {sorted(got)} != "
                        f"{sorted(TOP_KEYS)}")
        return problems
    if got["schema"] != want["schema"]:
        problems.append(f"{label}: schema {got['schema']!r} != "
                        f"{want['schema']!r}")
    if not isinstance(got["total_count"], int) or \
            isinstance(got["total_count"], bool):
        problems.append(f"{label}: total_count is not an integer")
    elif got["total_count"] != want["total_count"]:
        problems.append(f"{label}: total_count {got['total_count']} != "
                        f"{want['total_count']}")
    if not isinstance(got["metrics"], list):
        problems.append(f"{label}: metrics is not a list")
        return problems
    got_names = [m.get("name") if isinstance(m, dict) else None
                 for m in got["metrics"]]
    want_names = [m["name"] for m in want["metrics"]]
    if got_names != want_names:
        problems.append(f"{label}: metrics order {got_names} != "
                        f"{want_names}")
        return problems
    # The reference orders by name in Unicode code point order; the
    # artifact must emit the same order (sorted() on str).
    if got_names != sorted(got_names):
        problems.append(f"{label}: metrics are not sorted by name "
                        f"({got_names} != {sorted(got_names)})")
    for entry, expect in zip(got["metrics"], want["metrics"]):
        name = expect["name"]
        if not isinstance(entry, dict) or set(entry) != METRIC_KEYS:
            problems.append(f"{label}: metric {name!r} keys "
                            f"{sorted(entry) if isinstance(entry, dict) else entry} "
                            f"!= {sorted(METRIC_KEYS)}")
            continue
        if not isinstance(entry["count"], int) or isinstance(entry["count"], bool):
            problems.append(f"{label}: metric {name!r} count is not an integer")
        elif entry["count"] != expect["count"]:
            problems.append(f"{label}: metric {name!r} count "
                            f"{entry['count']} != {expect['count']}")
        for field in ("sum", "mean", "min", "max"):
            value = entry[field]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                problems.append(f"{label}: metric {name!r} {field} is not a "
                                f"number ({value!r})")
                continue
            if not close(float(value), float(expect[field])):
                problems.append(
                    f"{label}: metric {name!r} {field} {value!r} != "
                    f"{expect[field]!r} (rel "
                    f"{abs(value - expect[field]) / max(1.0, abs(expect[field])):.2e})")
        # identities, checked against the emitted numbers themselves
        if all(isinstance(entry[k], (int, float)) for k in ("min", "mean", "max")):
            if not entry["min"] <= entry["mean"] <= entry["max"]:
                problems.append(f"{label}: metric {name!r} min <= mean <= max "
                                f"violated ({entry['min']}, {entry['mean']}, "
                                f"{entry['max']})")
        if isinstance(entry["count"], int) and entry["count"] > 0 and \
                all(isinstance(entry[k], (int, float)) for k in ("sum", "mean")):
            if abs(entry["sum"] - entry["count"] * entry["mean"]) > \
                    REL_TOL * max(1.0, abs(entry["sum"])):
                problems.append(f"{label}: metric {name!r} sum != count * mean")
    return problems


def run_cli_json(root: Path, csv_path: Path) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "measurectl", "--json", str(csv_path)],
            capture_output=True, text=True, cwd=str(root),
            env=child_env(root), timeout=CLI_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"the CLI exceeded {CLI_TIMEOUT} s"
    return proc.returncode, proc.stdout, proc.stderr


def oracle_gate(root: Path, seed: int) -> dict:
    cases: list[tuple[str, Path, str]] = []
    sample = root / "data" / "sample.csv"
    cases.append(("sample.csv", sample, sample.read_text()))
    workdir = Path(tempfile.mkdtemp(prefix="measurectl-oracle-"))
    try:
        for name, text in synth_inputs(seed):
            path = workdir / name
            path.write_text(text, encoding="utf-8")
            cases.append((name, path, text))

        problems: list[str] = []
        results = []
        for name, path, text in cases:
            try:
                want = reference.summarise_text(text)
            except reference.ReferenceError as exc:
                problems.append(f"{name}: judge reference could not parse the "
                                f"input: {exc}")
                continue
            code, out, err = run_cli_json(root, path)
            if code != 0:
                problems.append(f"{name}: `--json` exited {code} "
                                f"({err.strip()[:200]})")
                continue
            try:
                got = json.loads(out)
            except json.JSONDecodeError as exc:
                problems.append(f"{name}: stdout is not JSON: {exc}")
                continue
            mismatches = compare_document(got, want, name)
            problems.extend(mismatches)
            results.append({
                "input": name,
                "metrics": len(want["metrics"]),
                "total_count": want["total_count"],
                "agreed": not mismatches,
            })
        if problems:
            raise GateFail("oracle",
                           f"{len(problems)} mismatch(es) against the "
                           f"independent reference; first: {problems[0]}",
                           {"problems": problems[:8]})
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return {"passed": True, "reference": "judge/reference.py (statistics.fsum)",
            "tolerance": f"{REL_TOL:g} relative", "cases": results}


# --------------------------------------------------------------------------
# the grade
# --------------------------------------------------------------------------
def grade(patch: Path, pr: Path, seed: int) -> dict:
    gates: dict = {}
    try:
        _grade(patch, pr, seed, gates)
    except GateFail as exc:
        verdict = {"patch": str(patch), "pr": str(pr), "seed": seed,
                   "passed": False, "failed_gate": exc.gate,
                   "reason": exc.message, "gates": gates}
        if exc.extra:
            verdict["details"] = exc.extra
        return verdict
    return {"patch": str(patch), "pr": str(pr), "seed": seed,
            "passed": True, "gates": gates}


def _grade(patch: Path, pr: Path, seed: int, gates: dict) -> None:
    entries = manifest_entries()

    # -- G1 patch ----------------------------------------------------------
    if not patch.is_file():
        raise GateFail("patch", f"no such patch: {patch}")
    text = patch.read_text(errors="replace")
    info = parse_patch(text)
    if not info.files or info.hunks == 0:
        raise GateFail("patch", "the patch contains no file changes")
    if info.binary:
        raise GateFail("patch", "the patch contains binary changes")
    if len(info.files) > MAX_FILES:
        raise GateFail("patch", f"the patch changes {len(info.files)} files "
                                f"(limit {MAX_FILES})")
    changed_lines = info.added + info.removed
    if changed_lines > MAX_LINES:
        raise GateFail("patch", f"the patch changes {changed_lines} lines "
                                f"(limit {MAX_LINES})")
    source_files = [normalise_path(f) for f in info.files]
    if not any(f.startswith("measurectl/") for f in source_files):
        raise GateFail("patch", "the patch changes no file under measurectl/")
    if not pr.is_file():
        raise GateFail("patch", f"no PR.md beside the patch (looked for {pr})")
    if not FIXTURE.is_dir():
        raise GateFail("patch", f"fixture not found at {FIXTURE}")

    workdir = Path(tempfile.mkdtemp(prefix="measurectl-grade-"))
    root = workdir / "fixture"
    try:
        shutil.copytree(FIXTURE, root,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        check_fixture(root, entries)

        # Repo-rooted paths are re-rooted onto the fixture before applying.
        apply_text = reroot_patch(text, info.files)
        patch_file = workdir / "delivery.patch"
        patch_file.write_text(apply_text)
        rerooted = apply_text != text
        apply = subprocess.run(["git", "apply", "--check", "-p1",
                                str(patch_file)],
                               cwd=str(root), capture_output=True, text=True)
        if apply.returncode != 0:
            raise GateFail("patch", "git apply --check failed: "
                                    + (apply.stderr.strip() or "unknown error"))
        applied = subprocess.run(["git", "apply", "-p1", str(patch_file)],
                                 cwd=str(root), capture_output=True, text=True)
        if applied.returncode != 0:
            raise GateFail("patch", "git apply failed: "
                                    + (applied.stderr.strip() or "unknown error"))
        gates["patch"] = {
            "passed": True,
            "files": len(info.files),
            "added_lines": info.added,
            "removed_lines": info.removed,
            "hunks": info.hunks,
            "repo_rooted": rerooted,
            "rule": f"1..{MAX_FILES} files, >=1 under measurectl/, "
                    f"<= {MAX_LINES} changed lines",
        }

        # -- G2 integrity --------------------------------------------------
        escapes = check_paths(info.files)
        if escapes:
            raise GateFail("integrity", "the patch contains unsafe path(s): "
                                        + ", ".join(escapes[:5]))
        forbidden = []
        for path in source_files:
            base = Path(path).name
            if path.startswith(FORBIDDEN_PREFIXES) or base in FORBIDDEN_BASENAMES:
                forbidden.append(path)
        for path in info.new_files:
            if Path(normalise_path(path)).name in STARTUP_HOOKS:
                forbidden.append(path)
        if forbidden:
            raise GateFail("integrity",
                           "the patch modifies test or tool-configuration "
                           "file(s), which are judge-owned: "
                           + ", ".join(forbidden[:5]),
                           {"forbidden": forbidden})
        for rel, digest in sorted(entries.items()):
            if not rel.startswith("tests/"):
                continue
            path = root / rel
            if not path.is_file() or sha256_file(path) != digest:
                raise GateFail("integrity",
                               f"tests/ changed after applying the patch: {rel}")
        gates["integrity"] = {"passed": True, "unsafe_paths": [],
                              "protected": "tests/ + tool config",
                              "rule": "tests/ and tool config are judge-owned"}

        # -- G3 regression -------------------------------------------------
        pytest_tool = find_tool("pytest")
        if pytest_tool is None:
            raise GateFail("regression",
                           "pytest not found; run judge/setup.sh")
        regression = run_pytest(pytest_tool, root, ["tests"], timeout=300)
        collected = collected_count(regression)
        failed = regression["counts"].get("failed", 0) + \
            regression["counts"].get("error", 0) + \
            regression["counts"].get("errors", 0)
        gates["regression"] = {
            "passed": regression["exit"] == 0 and failed == 0
            and collected >= MIN_REGRESSION_TESTS,
            "tests_collected": collected,
            "failed": failed,
            "pytest": tool_version(pytest_tool),
            "rule": f"0 failed, >= {MIN_REGRESSION_TESTS} tests collected",
        }
        if failed or regression["exit"] != 0:
            raise GateFail("regression", "the fixture's own suite fails on "
                                         "the patched checkout: "
                                         + regression["summary"])
        if collected < MIN_REGRESSION_TESTS:
            raise GateFail("regression", f"only {collected} tests collected "
                                         f"(need >= {MIN_REGRESSION_TESTS})")

        # -- G4 acceptance -------------------------------------------------
        dest = root / "tests" / "acceptance"
        dest.mkdir(parents=True, exist_ok=True)
        for src in sorted(ACCEPTANCE.glob("test_*.py")):
            shutil.copy2(src, dest / src.name)
        acceptance = run_pytest(pytest_tool, root,
                                ["tests/acceptance"], timeout=300)
        acc_collected = collected_count(acceptance)
        acc_failed = acceptance["counts"].get("failed", 0) + \
            acceptance["counts"].get("error", 0) + \
            acceptance["counts"].get("errors", 0)
        gates["acceptance"] = {
            "passed": acceptance["exit"] == 0 and acc_failed == 0
            and acc_collected >= MIN_ACCEPTANCE_TESTS,
            "tests_collected": acc_collected,
            "failed": acc_failed,
            "pytest": tool_version(pytest_tool),
            "rule": f"0 failed, >= {MIN_ACCEPTANCE_TESTS} tests collected",
        }
        if acc_failed or acceptance["exit"] != 0:
            raise GateFail("acceptance", "the hidden acceptance suite fails: "
                                         + acceptance["summary"])
        if acc_collected < MIN_ACCEPTANCE_TESTS:
            raise GateFail("acceptance", f"only {acc_collected} acceptance "
                                         f"tests collected (need >= "
                                         f"{MIN_ACCEPTANCE_TESTS})")

        # -- G5 lint -------------------------------------------------------
        ruff = find_tool("ruff")
        if ruff is None:
            raise GateFail("lint", "ruff not found; run judge/setup.sh")
        lint = run_ruff(ruff, root)
        gates["lint"] = {
            "passed": lint["exit"] == 0 and not lint["findings"],
            "findings": len(lint["findings"]),
            "ruff": tool_version(ruff),
            "config": "judge/ruff.toml",
            "rule": "0 ruff diagnostics",
        }
        if lint["findings"] or lint["exit"] != 0:
            raise GateFail("lint", f"ruff reported {len(lint['findings'])} "
                                   f"diagnostic(s); first: "
                                   + (lint["findings"][0] if lint["findings"]
                                      else lint["output"][:200]))

        # -- G6 oracle -----------------------------------------------------
        gates["oracle"] = oracle_gate(root, seed)

        # -- G7 pr ---------------------------------------------------------
        gates["pr"] = check_pr(pr.read_text(errors="replace"), info.files)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def judge_tree_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(JDIR.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts \
                and not path.name.endswith(".pyc"):
            digest.update(str(path.relative_to(JDIR)).encode())
            digest.update(sha256_file(path).encode())
    return digest.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="grade one delivery")
    ap.add_argument("patch", type=Path)
    ap.add_argument("--pr", type=Path, default=None,
                    help="PR.md path (default: beside the patch)")
    ap.add_argument("--seed", type=int, default=SEED_DEFAULT)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    pr = args.pr if args.pr is not None else args.patch.parent / "PR.md"
    try:
        verdict = grade(args.patch, pr, args.seed)
    except OSError as exc:
        verdict = {"patch": str(args.patch), "passed": False,
                   "failed_gate": "io", "reason": str(exc)}
    text = json.dumps(verdict, indent=2)
    if args.json:
        args.json.write_text(text)
    print(text)
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
