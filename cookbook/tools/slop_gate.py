#!/usr/bin/env python3
"""Mechanical slop gate for cookbook demos (cookbook/DEMO-STANDARD.md).

Usage:

    python3 slop_gate.py <demo dir> [<demo dir> ...]
    python3 slop_gate.py --base <ref> [--repo <path>]

With demo dirs, every listed dir is checked. With --base, the checked
demos are the `cookbook/<name>/` dirs touched by `git diff <merge-base>`,
i.e. committed and uncommitted tracked changes since the merge base;
`cookbook/tools` and `cookbook/_template` are not demos and are skipped.
The file set is `git ls-files` when the dir sits in a work tree, else the
whole dir is walked (a `.git` dir inside it is skipped).

Rules per demo dir (the limits are the module constants below; tests
import this module):

* code-lines: at most MAX_CODE_LINES lines of hand-written code in
  CODE_EXTS files, excluding anything under `examples/` or `media/clips/`
  (fixture artifacts and video helper clips are not demo code). Every
  line of the file counts, blanks and comments included.
* root-markdown: only README.md and SPEC.md may sit at the demo root; any
  other `*.md` there fails. Markdown in subdirs is not counted here.
* file-size: no tracked file larger than MAX_FILE_BYTES, except
  `media/demo.mp4` and `media/result.png`.
* generated-output: no tracked `*.csv`, `*.jsonl`, `*.npz`,
  `verdicts/*.json` or file under `judge_runs/` larger than
  GENERATED_MAX_BYTES -- generated data is regenerated, not committed.
* duplicate: no two tracked files with the same sha256, empty included.

Exit status: 0 when every checked demo passes, 1 when at least one
violation is printed (one line each: path, rule, measured vs limit), 2
on usage or measurement errors (missing dir, git failure).

Requirements: Python 3.10+ standard library; git for --base and for
tracked-file listing inside a work tree.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

# --- limits (single source of truth; tests import this module) ----------------
MAX_CODE_LINES = 1500
CODE_EXTS = {
    ".py", ".sh",
    ".ts", ".tsx",
    ".js", ".jsx", ".mjs", ".cjs",
    ".glsl", ".vert", ".frag",
}
CODE_EXCLUDED_DIRS = (("examples",), ("media", "clips"))
ALLOWED_ROOT_MARKDOWN = {"README.md", "SPEC.md"}
MAX_FILE_BYTES = 50 * 1024
SIZE_EXEMPT = {"media/demo.mp4", "media/result.png"}
GENERATED_MAX_BYTES = 5 * 1024
GENERATED_SUFFIXES = {".csv", ".jsonl", ".npz"}
GENERATED_DIRS = {"judge_runs"}
GENERATED_JSON_DIRS = {"verdicts"}
NON_DEMO_DIRS = {"tools", "_template"}


class GateError(Exception):
    """Input could not be measured; the gate exits 2."""


def _is_git_work_tree(d: Path) -> bool:
    r = subprocess.run(
        ["git", "-C", str(d), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and r.stdout.strip() == "true"


def _tracked_files(demo: Path) -> list[str]:
    """Demo-relative posix paths of the files under test."""
    if _is_git_work_tree(demo):
        r = subprocess.run(
            ["git", "-C", str(demo), "ls-files", "-z", "--", "."],
            capture_output=True,
        )
        if r.returncode != 0:
            raise GateError(r.stderr.decode(errors="replace").strip())
        return [p for p in r.stdout.decode(errors="replace").split("\0") if p]
    out = []
    for root, dirs, files in os.walk(demo):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            out.append((Path(root) / f).relative_to(demo).as_posix())
    return sorted(out)


def _code_excluded(rel: PurePosixPath) -> bool:
    return any(rel.parts[: len(prefix)] == prefix for prefix in CODE_EXCLUDED_DIRS)


def _is_generated(rel: PurePosixPath) -> bool:
    if rel.suffix.lower() in GENERATED_SUFFIXES:
        return True
    if rel.suffix.lower() == ".json" and GENERATED_JSON_DIRS & set(rel.parts):
        return True
    return bool(GENERATED_DIRS & set(rel.parts))


def check_demo(demo: Path) -> list[str]:
    """Return one violation line per failure: `path: rule: measured (limit)`."""
    demo = Path(demo)
    if not demo.is_dir():
        raise GateError(f"not a directory: {demo}")
    files = _tracked_files(demo)
    label = demo.as_posix().rstrip("/")
    v: list[str] = []

    def loc(rel: str) -> str:
        return f"{label}/{rel}" if rel else label

    code_lines = 0
    hashes: dict[str, list[str]] = {}
    for rel in files:
        p = PurePosixPath(rel)
        data = (demo / rel).read_bytes()

        if p.suffix.lower() in CODE_EXTS and not _code_excluded(p):
            code_lines += len(data.splitlines())

        if len(p.parts) == 1 and p.suffix.lower() == ".md" \
                and p.name not in ALLOWED_ROOT_MARKDOWN:
            v.append(
                f"{loc(rel)}: root-markdown: {p.name} "
                f"(only {' and '.join(sorted(ALLOWED_ROOT_MARKDOWN))} allowed)"
            )

        if len(data) > MAX_FILE_BYTES and rel not in SIZE_EXEMPT:
            v.append(
                f"{loc(rel)}: file-size: {len(data)} B > {MAX_FILE_BYTES} B "
                f"(only {' and '.join(sorted(SIZE_EXEMPT))} exempt)"
            )

        if _is_generated(p) and len(data) > GENERATED_MAX_BYTES:
            v.append(
                f"{loc(rel)}: generated-output: {len(data)} B "
                f"> {GENERATED_MAX_BYTES} B"
            )

        hashes.setdefault(hashlib.sha256(data).hexdigest(), []).append(rel)

    if code_lines > MAX_CODE_LINES:
        v.append(f"{loc('')}: code-lines: {code_lines} > {MAX_CODE_LINES}")

    for group in hashes.values():
        if len(group) > 1:
            first, *dups = sorted(group)
            for rel in dups:
                v.append(
                    f"{loc(rel)}: duplicate: sha256 identical to {loc(first)}"
                )

    return sorted(v)


def _changed_demos(repo: Path, base: str) -> list[Path]:
    mb = subprocess.run(
        ["git", "-C", str(repo), "merge-base", base, "HEAD"],
        capture_output=True, text=True,
    )
    if mb.returncode != 0:
        raise GateError(mb.stderr.strip() or f"no merge base with {base}")
    r = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", "-z",
         mb.stdout.strip(), "--", "cookbook"],
        capture_output=True,
    )
    if r.returncode != 0:
        raise GateError(r.stderr.decode(errors="replace").strip())
    names = set()
    for path in r.stdout.decode(errors="replace").split("\0"):
        parts = PurePosixPath(path).parts
        if len(parts) >= 3 and parts[0] == "cookbook" \
                and parts[1] not in NON_DEMO_DIRS:
            names.add(parts[1])
    return sorted(repo / "cookbook" / n for n in names
                  if (repo / "cookbook" / n).is_dir())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="slop_gate.py", description=__doc__.splitlines()[0])
    ap.add_argument("demos", nargs="*", type=Path,
                    help="demo dirs to check (e.g. cookbook/cfd-openfoam)")
    ap.add_argument("--base", metavar="REF",
                    help="check every demo dir changed vs REF...HEAD")
    ap.add_argument("--repo", type=Path, default=Path("."),
                    help="repo root for --base (default: cwd)")
    args = ap.parse_args(argv)

    try:
        if args.base:
            if args.demos:
                ap.error("demo dirs and --base are mutually exclusive")
            demos = _changed_demos(args.repo.resolve(), args.base)
        else:
            if not args.demos:
                ap.error("give at least one demo dir, or --base REF")
            demos = args.demos
        violations = [line for d in demos for line in check_demo(d)]
    except GateError as e:
        print(f"slop-gate: error: {e}", file=sys.stderr)
        return 2

    for line in violations:
        print(line)
    if violations:
        print(f"slop-gate: FAIL ({len(violations)} violation(s) "
              f"in {len(demos)} demo dir(s))")
        return 1
    if demos:
        print(f"slop-gate: PASS ({len(demos)} demo dir(s) checked)")
    else:
        print("slop-gate: PASS (no changed demo dirs under cookbook/)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
