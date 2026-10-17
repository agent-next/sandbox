"""Tests for cookbook/tools/slop_gate.py.

Fixtures are demo dirs built in tmp_path. "Tracked" files come from
`git init` + `git add -A` (staging is enough for ls-files; no commit or
user config needed). One test covers the non-git dir walk, and --base is
tested on a real two-commit repo.

Run:  pytest -q -s cookbook/tools     (from the repo root)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import slop_gate  # noqa: E402

OVER_FILE = slop_gate.MAX_FILE_BYTES + 1
OVER_GENERATED = slop_gate.GENERATED_MAX_BYTES + 1


def _git(d: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(d), *args],
                       check=True, capture_output=True, text=True)
    return r.stdout.strip()


def _demo(tmp_path: Path, files: dict[str, str | bytes], git: bool = True) -> Path:
    d = tmp_path / "demo-x"
    for rel, data in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data.encode() if isinstance(data, str) else data)
    if git:
        _git(d, "init", "-q")
        _git(d, "add", "-A")
    return d


def _rules(violations: list[str]) -> list[str]:
    return [line.split(": ", 2)[1] for line in violations]


BASE = {"README.md": "demo\n", "SPEC.md": "spec\n", "run.py": "print('x')\n"}


# --- code-lines ---------------------------------------------------------

def test_code_lines_pass(tmp_path):
    d = _demo(tmp_path, {**BASE, "judge/grade.sh": "#!/bin/sh\nexit 0\n"})
    assert slop_gate.check_demo(d) == []


def test_code_lines_fail(tmp_path):
    d = _demo(tmp_path, {**BASE,
                         "run.py": "x = 1\n" * (slop_gate.MAX_CODE_LINES + 1)})
    assert _rules(slop_gate.check_demo(d)) == ["code-lines"]


def test_code_lines_exclude_examples_and_clips(tmp_path):
    n = slop_gate.MAX_CODE_LINES
    d = _demo(tmp_path, {**BASE,
                         "examples/good/big.py": "x = 1\n" * n,
                         "media/clips/cut.sh": "y = 2\n" * n})
    assert slop_gate.check_demo(d) == []


def test_code_lines_count_all_source_exts(tmp_path):
    per = slop_gate.MAX_CODE_LINES // 3 + 1
    d = _demo(tmp_path, {**BASE, "a.ts": "a\n" * per,
                         "b.cjs": "b\n" * per, "c.glsl": "c\n" * per})
    assert _rules(slop_gate.check_demo(d)) == ["code-lines"]


# --- root-markdown -------------------------------------------------------

def test_root_markdown_pass(tmp_path):
    d = _demo(tmp_path, {**BASE, "media/STORYBOARD.md": "shots\n",
                         "docs/NOTES.md": "nested is fine\n"})
    assert slop_gate.check_demo(d) == []


def test_root_markdown_fail(tmp_path):
    d = _demo(tmp_path, {**BASE, "NOTES.md": "prose\n", "PLAN.md": "more\n"})
    assert _rules(slop_gate.check_demo(d)) == ["root-markdown"] * 2


# --- file-size -----------------------------------------------------------

def test_file_size_pass_and_exempt_media(tmp_path):
    d = _demo(tmp_path, {**BASE,
                         "media/demo.mp4": b"\0" * OVER_FILE,
                         "media/result.png": b"\1" * OVER_FILE})
    assert slop_gate.check_demo(d) == []


def test_file_size_fail(tmp_path):
    d = _demo(tmp_path, {**BASE, "media/loop.png": b"\0" * OVER_FILE})
    assert _rules(slop_gate.check_demo(d)) == ["file-size"]


# --- generated-output ----------------------------------------------------

def test_generated_output_pass(tmp_path):
    d = _demo(tmp_path, {**BASE,
                         "verdicts/ok.json": "{}\n",
                         "media/data/small.csv": "a,b\n"})
    assert slop_gate.check_demo(d) == []


@pytest.mark.parametrize("rel", [
    "media/data/traces.csv",
    "logs/run.jsonl",
    "arrays/weights.npz",
    "verdicts/grade.json",
    "judge_runs/seed-7/log.txt",
])
def test_generated_output_fail(tmp_path, rel):
    d = _demo(tmp_path, {**BASE, rel: b"\0" * OVER_GENERATED})
    assert _rules(slop_gate.check_demo(d)) == ["generated-output"]


# --- duplicate -----------------------------------------------------------

def test_duplicate_pass(tmp_path):
    d = _demo(tmp_path, {**BASE, "a.py": "x = 1\n", "b.py": "x = 2\n"})
    assert slop_gate.check_demo(d) == []


def test_duplicate_fail(tmp_path):
    d = _demo(tmp_path, {**BASE,
                         "judge/util.py": "def f():\n    return 1\n",
                         "util_copy.py": "def f():\n    return 1\n"})
    violations = slop_gate.check_demo(d)
    assert _rules(violations) == ["duplicate"]
    assert "util_copy.py" in violations[0]


# --- tracked vs untracked, git vs plain dir -------------------------------

def test_untracked_files_ignored(tmp_path):
    files = {**BASE, "scratch/huge.bin": b"\0" * OVER_FILE}
    d = _demo(tmp_path, files, git=False)          # add only after .gitignore
    (d / ".gitignore").write_text("scratch/\n")
    _git(d, "init", "-q")
    _git(d, "add", "-A")
    assert slop_gate.check_demo(d) == []


def test_plain_dir_walk(tmp_path):
    d = _demo(tmp_path, {**BASE, "big.bin": b"\0" * OVER_FILE}, git=False)
    assert _rules(slop_gate.check_demo(d)) == ["file-size"]


# --- main() / --base ------------------------------------------------------

def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "--no-verify", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def test_base_finds_changed_demos(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "cookbook" / "demo-old").mkdir(parents=True)
    (repo / "cookbook" / "demo-old" / "README.md").write_text("old\n")
    base = _commit(repo, "init")

    (repo / "cookbook" / "demo-new").mkdir()
    (repo / "cookbook" / "demo-new" / "README.md").write_text("new\n")
    (repo / "cookbook" / "demo-new" / "NOTES.md").write_text("slop\n")
    (repo / "cookbook" / "tools" / "x.py").parent.mkdir(exist_ok=True)
    (repo / "cookbook" / "tools" / "x.py").write_text("print(1)\n")
    _commit(repo, "add demo")

    assert slop_gate.main(["--base", base, "--repo", str(repo)]) == 1
    out = capsys.readouterr().out
    assert "demo-new/NOTES.md: root-markdown:" in out
    assert "demo-old" not in out and "tools" not in out


def test_base_no_changes_passes(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "cookbook" / "demo-x").mkdir(parents=True)
    (repo / "cookbook" / "demo-x" / "README.md").write_text("x\n")
    base = _commit(repo, "init")
    assert slop_gate.main(["--base", base, "--repo", str(repo)]) == 0
    assert "no changed demo dirs" in capsys.readouterr().out


def test_main_demo_arg_exit_codes(tmp_path, capsys):
    clean = _demo(tmp_path, BASE)
    capsys.readouterr()
    assert slop_gate.main([str(clean)]) == 0
    dirty = _demo(tmp_path, {**BASE, "dump.csv": b"\0" * OVER_GENERATED})
    assert slop_gate.main([str(dirty)]) == 1
    assert "dump.csv" in capsys.readouterr().out
