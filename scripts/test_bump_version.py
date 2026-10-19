"""Tests for scripts/bump_version.py.

Each test reproduces a follow-up finding from the #119 review (issue #123):
fixtures are the three version files built in tmp_path, and every case is
exercised through the same entry points CI uses -- bump(), check() and main().

Run:  pytest -q scripts     (from the repo root)
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bump_version as bv  # noqa: E402

PYPROJECT = """[project]
name = "agent-next-sandbox"
version = "0.0.4"

[tool.hatch.build.targets.wheel]
packages = ["src/sbx"]
"""

# A nested "version" key ("interface" holds one, as plugin manifests may)
# before the top-level one: _JSON_VERSION rewrites the FIRST match.
CLAUDE_PLUGIN = json.dumps({
    "name": "sandbox",
    "interface": {"version": "9.9.9", "displayName": "agent-next sandbox"},
    "version": "0.0.4",
})
CODEX_PLUGIN = json.dumps({"name": "sandbox", "version": "0.0.4"})


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """The three version files the script manages, in their real layout."""
    pyproject = tmp_path / "cli" / "pyproject.toml"
    pyproject.parent.mkdir()
    pyproject.write_text(PYPROJECT, encoding="utf-8")
    for rel, text in (
        ("plugins/sandbox/.claude-plugin/plugin.json", CLAUDE_PLUGIN),
        ("plugins/sandbox/.codex-plugin/plugin.json", CODEX_PLUGIN),
    ):
        p = tmp_path / rel
        p.parent.mkdir(parents=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def versions(root: Path) -> list[str]:
    """The three version strings as read_version (and CI's --check) see them."""
    return [bv.read_version(root / rel) for rel in bv.VERSION_FILES]


# --- finding 1: the wrong "version" field -------------------------------

def test_bump_rewrites_the_top_level_version_not_a_nested_one(root):
    """A manifest with a nested "version" key before the top-level one must
    still have its top-level version bumped; the nested key is not ours."""
    bv.bump(root, "0.0.5")
    manifest = json.loads((root / bv.VERSION_FILES[1]).read_text(encoding="utf-8"))
    assert manifest["interface"]["version"] == "9.9.9"
    assert manifest["version"] == "0.0.5"
    assert versions(root) == ["0.0.5"] * 3


# --- finding 2: TOML formatting variants ---------------------------------

@pytest.mark.parametrize("line", [
    "version = '0.0.4'",
    'version = "0.0.4"  # bumped by the release workflow',
])
def test_check_reads_version_in_valid_toml_shapes(root, line):
    """--check (what CI's version-check job runs) must read the version
    however valid TOML spells it, not only `version = "x"`."""
    pyproject = root / "cli" / "pyproject.toml"
    pyproject.write_text(PYPROJECT.replace('version = "0.0.4"', line), encoding="utf-8")
    assert bv.check(root) == []


def test_bump_rewrites_a_quoted_toml_version_keeping_the_comment(root):
    """A bump must find the version in a single-quoted line too, and keep
    the rest of the line."""
    pyproject = root / "cli" / "pyproject.toml"
    pyproject.write_text(
        PYPROJECT.replace('version = "0.0.4"',
                          "version = '0.0.4'  # bumped by the release workflow"),
        encoding="utf-8")
    bv.bump(root, "0.0.5")
    text = pyproject.read_text(encoding="utf-8")
    assert 'version = "0.0.5"  # bumped by the release workflow' in text


# --- finding 3: owner-only permissions ------------------------------------

def test_bump_keeps_the_files_world_readable(root):
    """The rewrite must not shrink the metadata files' permissions below
    what the repo ships them with."""
    before = {rel: (root / rel).stat().st_mode for rel in bv.VERSION_FILES}
    bv.bump(root, "0.0.5")
    for rel, mode in before.items():
        after = stat.S_IMODE((root / rel).stat().st_mode)
        assert after == stat.S_IMODE(mode), f"{rel}: {oct(after)} != {oct(stat.S_IMODE(mode))}"


# --- finding 4: all-or-nothing writes -------------------------------------

def test_a_failed_bump_leaves_all_three_versions_untouched(root, monkeypatch):
    """A write that dies partway through must not leave the versions
    inconsistent: either all three files move or none does."""
    real_write = bv._write
    seen = []

    def failing_write(path, text):
        if seen:  # the second or third file
            seen.append(path)
            raise OSError("disk full")
        seen.append(path)
        real_write(path, text)

    monkeypatch.setattr(bv, "_write", failing_write)
    with pytest.raises(OSError):
        bv.bump(root, "0.0.5")
    assert versions(root) == ["0.0.4"] * 3


# --- finding 5: an empty --tag ---------------------------------------------

def test_bump_rejects_an_empty_tag(root):
    """An empty --tag (an unset variable in a workflow) is still a --tag:
    a bump must refuse it, not skip validation and rewrite the files."""
    with pytest.raises(SystemExit) as e:
        bv.main(["0.0.5", "--tag", ""], root=root)
    assert e.value.code == 2
    assert versions(root) == ["0.0.4"] * 3


def test_check_rejects_an_empty_tag(root):
    """--check with an empty tag is not vX.Y.Z and must fail."""
    assert bv.main(["--check", "--tag", ""], root=root) == 1
