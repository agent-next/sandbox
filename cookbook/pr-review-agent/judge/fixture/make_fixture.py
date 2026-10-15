#!/usr/bin/env python3
"""Generate the 6 PR diffs and the judge's private answer key.

Deterministic: the pristine tree in ``repo/`` plus this script produce
byte-identical ``pr<k>.diff`` files and ``oracle/GROUND_TRUTH.json`` on every
run.  Every PR is a *single-line* edit of the pristine tree, so the pristine
tree doubles as the "fixed" side the judge runs the reviewer's tests against
(gate G5) -- and a reviewer that ships no real oracle cannot satisfy it.

Usage: python3 make_fixture.py [--check]

``--check`` regenerates into a temp dir and diffs against what is on disk,
exiting non-zero on any difference (used by judge/selftest.sh).
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE / "repo"
ORACLE = HERE.parent / "oracle" / "GROUND_TRUTH.json"

# (pr number, defect class, file, the pristine line, the PR's line)
#   The pristine line is the fixed version; the PR's line is the planted
#   defect.  Each edit touches exactly one line of one file.
EDITS: list[tuple[int, str | None, str, str, str]] = [
    (1, "off-by-one", "orders/pagination.py",
     "    stop = start + page_size",
     "    stop = start + page_size - 1"),
    (2, "sql-injection", "orders/store.py",
     '        " WHERE customer = ? ORDER BY id DESC",\n        (customer,),',
     '        " WHERE customer = \'%s\' ORDER BY id DESC" % customer,'),
    (3, "none-deref", "orders/store.py",
     "    total = order_total(conn, order_id)\n"
     "    if total is None:\n"
     "        return None\n"
     "    return int(total * (1 + rate))",
     "    total = order_total(conn, order_id)\n"
     "    return int(total * (1 + rate))"),
    (4, "race", "orders/metrics.py",
     "        with self._lock:\n            self._write(self._read() + amount)",
     "        self._write(self._read() + amount)"),
    # 5: clean refactor -- behaviour identical, no defect.
    (5, None, "orders/config.py",
     "    with open(path, encoding=\"utf-8\") as handle:\n"
     "        loaded = json.load(handle)",
     "    handle = open(path, encoding=\"utf-8\")\n"
     "    try:\n"
     "        loaded = json.load(handle)\n"
     "    finally:\n"
     "        handle.close()"),
    # 6: clean addition -- a new helper plus its test, no defect.
    (6, None, "orders/worker.py",
     "    results = []\n    for job in jobs:\n        results.append(job())\n    return results",
     "    results = []\n"
     "    for job in jobs:\n"
     "        results.append(job())\n"
     "    return results\n"
     "\n"
     "\n"
     "def run_jobs_collecting_errors(jobs):\n"
     '    """Run every job, returning (results, errors) instead of raising."""\n'
     "    results, errors = [], []\n"
     "    for job in jobs:\n"
     "        try:\n"
     "            results.append(job())\n"
     "        except Exception as exc:  # noqa: BLE001 - reported, not swallowed\n"
     "            errors.append((job, exc))\n"
     "    return results, errors"),
]

SEVERITY = {
    "off-by-one": "major",
    "sql-injection": "critical",
    "none-deref": "major",
    "race": "major",
}


SKIP_DIRS = {"__pycache__", ".pytest_cache"}


def pristine_files() -> dict[str, str]:
    """Every tracked file in the pristine tree, as repo-relative path -> text.

    The skip rule matches the judge's ``sha256_tree`` exactly, so a stray
    ``__pycache__`` from a local test run cannot change the hash.
    """
    out = {}
    for path in sorted(REPO.rglob("*")):
        if not path.is_file():
            continue
        if SKIP_DIRS & set(path.parts) or path.suffix == ".pyc":
            continue
        rel = path.relative_to(REPO).as_posix()
        out[rel] = path.read_text(encoding="utf-8")
    return out


def pr_tree(base: dict[str, str], file: str, old: str, new: str) -> dict[str, str]:
    """The PR's tree: ``base`` with exactly one old->new replacement in ``file``."""
    if file not in base:
        raise SystemExit(f"make_fixture: {file} is not in the pristine tree")
    text = base[file]
    if text.count(old) != 1:
        raise SystemExit(
            f"make_fixture: the pristine text to replace occurs "
            f"{text.count(old)} times in {file}, expected exactly 1"
        )
    tree = dict(base)
    tree[file] = text.replace(old, new, 1)
    return tree


def unified(rel: str, old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=3,
        )
    )


def diff_for(base: dict[str, str], tree: dict[str, str]) -> str:
    """A unified diff of the whole tree (single hunk, one file)."""
    parts = [
        unified(rel, base[rel], tree[rel])
        for rel in sorted(base)
        if base[rel] != tree[rel]
    ]
    return "".join(parts)


def line_of(tree: dict[str, str], rel: str, needle: str) -> int:
    """1-based line number of the single line containing ``needle``."""
    hits = [
        i for i, line in enumerate(tree[rel].splitlines(), start=1)
        if needle in line
    ]
    if len(hits) != 1:
        raise SystemExit(
            f"make_fixture: needle {needle!r} matches {len(hits)} lines in {rel}"
        )
    return hits[0]


def tree_hash(base: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for rel, text in sorted(base.items()):
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(text.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def generate() -> tuple[dict[str, str], dict]:
    """Return (filename -> content, ground-truth dict) without touching disk."""
    base = pristine_files()
    files: dict[str, str] = {}
    defects = []
    clean = []
    trees = {}
    for pr, kind, rel, old, new in EDITS:
        tree = pr_tree(base, rel, old, new)
        diff = diff_for(base, tree)
        if not diff:
            raise SystemExit(f"make_fixture: PR {pr} produces an empty diff")
        files[f"pr{pr}.diff"] = diff
        trees[str(pr)] = tree_hash(tree)
        if kind is None:
            clean.append(pr)
        else:
            defects.append({
                "pr": pr,
                "file": rel,
                "line": line_of(tree, rel, new.splitlines()[-1]),
                "kind": kind,
                "severity": SEVERITY[kind],
            })
    ground_truth = {
        "pristine_sha256": tree_hash(base),
        "pr_sha256": trees,
        "defects": defects,
        "clean_prs": clean,
        "prs": [pr for pr, *_ in EDITS],
    }
    return files, ground_truth


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the files on disk are what this script generates")
    args = ap.parse_args()

    files, ground_truth = generate()

    if args.check:
        bad = []
        for name, content in files.items():
            path = HERE / name
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                bad.append(name)
        if not ORACLE.exists() or \
                json.loads(ORACLE.read_text(encoding="utf-8")) != ground_truth:
            bad.append("oracle/GROUND_TRUTH.json")
        if bad:
            print(f"make_fixture: stale or missing: {' '.join(sorted(bad))}",
                  file=sys.stderr)
            return 1
        print(f"make_fixture: OK ({len(files)} diffs + oracle match)")
        return 0

    for name, content in files.items():
        (HERE / name).write_text(content, encoding="utf-8")
    ORACLE.parent.mkdir(parents=True, exist_ok=True)
    ORACLE.write_text(json.dumps(ground_truth, indent=2) + "\n", encoding="utf-8")
    print(f"make_fixture: wrote {len(files)} diffs to {HERE}")
    print(f"make_fixture: wrote {ORACLE}")
    for d in ground_truth["defects"]:
        print(f"make_fixture:   PR {d['pr']}: {d['file']}:{d['line']} "
              f"{d['kind']} ({d['severity']})")
    print(f"make_fixture: clean PRs {ground_truth['clean_prs']}")
    print(f"make_fixture: pristine tree sha256 {ground_truth['pristine_sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
