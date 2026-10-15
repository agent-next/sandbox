#!/usr/bin/env python3
"""Generate known-bad single-edit mutants of the good delivery.

Each mutant is exactly one textual edit of the good `delivery.patch`
(applied to a copy of the fixture, edited once, re-diffed) or one edit of
`PR.md`.  Used by `judge/selftest.sh` to prove the judge can fail.

Usage: python3 -I judge/mutants.py <good-delivery.patch> <good-PR.md> <outdir>

Writes `<outdir>/<name>/delivery.patch` and `<outdir>/<name>/PR.md`, plus
a summary line per mutant naming the edit.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

JDIR = Path(__file__).resolve().parent
FIXTURE = JDIR.parent / "fixture"

# Each entry: (name, gate it should be killed by, file, old, new, note).
# `file` is relative to the applied checkout; PR.md edits target the
# delivery description instead.
EDITS = [
    (
        "empty-patch", "patch", None, None, None,
        "the patch is emptied",
    ),
    (
        "touches-tests", "integrity", "tests/test_stats.py",
        "def test_empty_input_gives_no_metrics():",
        "def test_empty_input_gives_no_metrics():\n    assert True",
        "the patch also edits a file under tests/",
    ),
    (
        "breaks-old-test", "regression", "measurectl/stats.py",
        "        metric.count += 1\n        metric.total += value",
        "        metric.count += 2\n        metric.total += value",
        "the running count is doubled, breaking an existing test",
    ),
    (
        "json-missing-field", "acceptance", "measurectl/jsonout.py",
        '                "max": metric.max,\n',
        "",
        "the per-metric document loses its `max` field",
    ),
    (
        "startup-hook", "integrity", "__NEW__:sitecustomize.py", None, None,
        "a planted sitecustomize.py is added (interpreter startup hook)",
    ),
    (
        "json-count-as-float", "acceptance", "measurectl/jsonout.py",
        '                "count": metric.count,',
        '                "count": float(metric.count),',
        "`count` is emitted as a float, not an integer",
    ),
    (
        "lint-unused-import", "lint", "measurectl/jsonout.py",
        "import json\n",
        "import json\nimport math\n",
        "an unused import is added (ruff F401)",
    ),
    (
        "mean-sign-dropped", "oracle", "measurectl/jsonout.py",
        '                "mean": metric.mean,',
        '                "mean": abs(metric.mean),',
        "the sign of `mean` is dropped; only the judge's seeded inputs "
        "carry negative values",
    ),
    (
        "mean-not-sum-over-count", "oracle", "measurectl/jsonout.py",
        '                "sum": metric.total,',
        '                "sum": round(metric.total, 3),',
        "`sum` is rounded to 3 places, breaking the exact comparison",
    ),
    (
        "pr-omits-file", "pr", "PR.md",
        "- `measurectl/jsonout.py` (new): builds and renders the",
        "- the new module builds and renders the",
        "PR.md stops naming measurectl/jsonout.py",
    ),
    (
        "pr-no-test-plan", "pr", "PR.md",
        "## Test plan",
        "## Notes",
        "PR.md loses its test-plan heading",
    ),
]


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return sh(["git", "-C", str(root),
               "-c", "user.email=demo@example.invalid",
               "-c", "user.name=demo", *args])


def prepare_checkout(good_patch: Path, work: Path) -> str:
    """Fixture copy + the good patch applied, as a git repo whose base
    commit is the clean fixture.  Returns the base commit sha, so a mutant
    diff is always taken against the clean checkout the judge grades."""
    sh(["cp", "-r", str(FIXTURE), str(work)])
    for junk in list(work.rglob("__pycache__")):
        shutil.rmtree(junk, ignore_errors=True)
    git(work, "init", "-q")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "base")
    base = git(work, "rev-list", "--max-parents=0", "HEAD").stdout.strip()
    sh(["git", "-C", str(work), "apply", "-p1", str(good_patch.resolve())])
    git(work, "add", "-A")
    git(work, "commit", "-qm", "good")
    return base


def rediff(work: Path, base: str) -> str:
    return git(work, "diff", base, "HEAD", "--no-color", "--no-ext-diff",
               "--src-prefix=a/", "--dst-prefix=b/").stdout


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: mutants.py <good-delivery.patch> <good-PR.md> <outdir>",
              file=sys.stderr)
        return 2
    good_patch, good_pr, outdir = (Path(sys.argv[1]), Path(sys.argv[2]),
                                   Path(sys.argv[3]))
    if not good_patch.is_file() or not good_pr.is_file():
        print("mutants: good patch and PR.md are required", file=sys.stderr)
        return 1
    good_pr_text = good_pr.read_text()
    outdir.mkdir(parents=True, exist_ok=True)

    made = 0
    for name, gate, rel, old, new, note in EDITS:
        with tempfile.TemporaryDirectory(prefix="measurectl-mutant-") as td:
            work = Path(td) / "fixture"
            base = prepare_checkout(good_patch, work)
            pr_text = good_pr_text
            if rel is None:
                patch_text = ""  # empty-patch
            elif rel.startswith("__NEW__:"):
                (work / rel[len("__NEW__:"):]).write_text(
                    "import builtins\n\nbuiltins.__dict__.setdefault('_x', 0)\n")
                git(work, "add", "-A")
                git(work, "commit", "-qm", name)
                patch_text = rediff(work, base)
            elif rel == "PR.md":
                if pr_text.count(old) != 1:
                    print(f"mutants: anchor not unique in PR.md for {name!r}",
                          file=sys.stderr)
                    return 1
                pr_text = pr_text.replace(old, new)
                patch_text = rediff(work, base)
            else:
                target = work / rel
                text = target.read_text()
                if text.count(old) != 1:
                    print(f"mutants: anchor not unique in {rel} for {name!r}",
                          file=sys.stderr)
                    return 1
                target.write_text(text.replace(old, new))
                git(work, "add", "-A")
                git(work, "commit", "-qm", name)
                patch_text = rediff(work, base)
        case = outdir / name
        case.mkdir(parents=True, exist_ok=True)
        (case / "delivery.patch").write_text(patch_text)
        (case / "PR.md").write_text(pr_text)
        print(f"mutants: {name}/  expects gate {gate}: {note}")
        made += 1

    print(f"mutants: wrote {made} mutants to {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
