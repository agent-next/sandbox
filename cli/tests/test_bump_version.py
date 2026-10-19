import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "bump_version", REPO_ROOT / "scripts" / "bump_version.py"
)
bump_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bump_version)

PYPROJECT = """\
[project]
name = "agent-next-sandbox"
version = "{version}"
requires-python = ">=3.10"

[project.urls]
Homepage = "https://agent-next.com"
"""


def make_repo(tmp_path, cli="0.0.3", claude="0.0.3", codex="0.0.3"):
    files = {
        "cli/pyproject.toml": PYPROJECT.format(version=cli),
        "plugins/sandbox/.claude-plugin/plugin.json": json.dumps(
            {"name": "sandbox", "version": claude, "description": "d"}, indent=2
        ),
        "plugins/sandbox/.codex-plugin/plugin.json": json.dumps(
            {"name": "sandbox", "version": codex}, indent=2
        ),
    }
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n")
    return tmp_path


def versions(root):
    return [bump_version.read_version(root / rel) for rel in bump_version.VERSION_FILES]


def test_bump_patch_rewrites_all_three(tmp_path, capsys):
    repo = make_repo(tmp_path)
    assert bump_version.main(["0.0.4"], root=repo) == 0
    assert versions(repo) == ["0.0.4"] * 3
    out = capsys.readouterr().out
    for rel in bump_version.VERSION_FILES:
        assert rel in out


def test_bump_preserves_file_contents(tmp_path):
    repo = make_repo(tmp_path, claude="0.0.3")
    bump_version.main(["0.0.4"], root=repo)
    plugin = json.loads(
        (repo / "plugins/sandbox/.claude-plugin/plugin.json").read_text()
    )
    assert plugin["description"] == "d"


@pytest.mark.parametrize("bad", ["0.4", "0.0.4.1", "0.0.4rc1", "v0.0.4", "latest"])
def test_bump_refuses_non_xyz(tmp_path, bad):
    repo = make_repo(tmp_path)
    assert bump_version.main([bad], root=repo) != 0
    assert versions(repo) == ["0.0.3"] * 3


@pytest.mark.parametrize("bad", ["0.0.4\n", "0.0.04", "0.0.1\u0663", "0.0.1\uff14"])
def test_bump_refuses_noncanonical_version(tmp_path, bad):
    repo = make_repo(tmp_path)
    assert bump_version.main([bad], root=repo) != 0
    assert versions(repo) == ["0.0.3"] * 3


def test_bump_refuses_going_backwards(tmp_path):
    repo = make_repo(tmp_path)
    assert bump_version.main(["0.0.2"], root=repo) != 0
    assert versions(repo) == ["0.0.3"] * 3


def test_bump_refuses_backwards_when_files_drifted(tmp_path):
    repo = make_repo(tmp_path, claude="0.0.5")
    assert bump_version.main(["0.0.4"], root=repo) != 0
    assert versions(repo) == ["0.0.3", "0.0.5", "0.0.3"]


@pytest.mark.parametrize("new", ["0.1.0", "1.0.0"])
def test_bump_minor_or_major_needs_flag(tmp_path, new):
    repo = make_repo(tmp_path)
    assert bump_version.main([new], root=repo) != 0
    assert versions(repo) == ["0.0.3"] * 3
    assert bump_version.main([new, "--allow-minor"], root=repo) == 0
    assert versions(repo) == [new] * 3


def test_check_ok_when_versions_agree(tmp_path):
    repo = make_repo(tmp_path)
    assert bump_version.main(["--check"], root=repo) == 0


def test_check_fails_when_versions_disagree(tmp_path, capsys):
    repo = make_repo(tmp_path, codex="0.0.2")
    assert bump_version.main(["--check"], root=repo) == 1
    err = capsys.readouterr().err
    assert "codex-plugin" in err


def test_check_with_matching_tag(tmp_path):
    repo = make_repo(tmp_path)
    assert bump_version.main(["--check", "--tag", "v0.0.3"], root=repo) == 0


def test_check_fails_when_tag_differs(tmp_path):
    repo = make_repo(tmp_path)
    assert bump_version.main(["--check", "--tag", "v0.0.4"], root=repo) == 1


def test_check_refuses_malformed_tag(tmp_path):
    repo = make_repo(tmp_path)
    assert bump_version.main(["--check", "--tag", "0.0.3"], root=repo) != 0


@pytest.mark.parametrize("tag", ["v0.0.04", "v0.0.1\u0663"])
def test_check_refuses_noncanonical_tag(tmp_path, tag):
    repo = make_repo(tmp_path, cli=tag[1:], claude=tag[1:], codex=tag[1:])
    assert bump_version.main(["--check", "--tag", tag], root=repo) != 0


def test_check_flags_noncanonical_stored_version(tmp_path):
    repo = make_repo(tmp_path, cli="0.0.04", claude="0.0.04", codex="0.0.04")
    assert bump_version.main(["--check"], root=repo) == 1


def test_check_fails_on_non_xyz_version(tmp_path):
    repo = make_repo(tmp_path, cli="dev", claude="dev", codex="dev")
    assert bump_version.main(["--check"], root=repo) == 1
