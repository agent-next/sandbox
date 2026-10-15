"""Tests for cookbook/tools/result.py and the committed result.json files.

Run from the repo root:  python3 -m pytest -q cookbook/tools/test_result.py
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))
import result  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n"
       b"\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x00"
       b"\x00\x00\x00\x00" + b"\x00" * 32)
MP4 = bytes.fromhex("00000018" + "66747970" + "69736f6d" +
                    "00000200" + "69736f6d69736f32")


def make_demo(tmp_path):
    """A minimal demo dir whose files satisfy every kind/magic check."""
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "result.png").write_bytes(PNG)
    (tmp_path / "media" / "loop.png").write_bytes(PNG)
    (tmp_path / "media" / "demo.mp4").write_bytes(MP4)
    (tmp_path / "RECEIPT.md").write_text("# receipt\n| metric | 1 |\n")
    return tmp_path


def valid_manifest():
    return {
        "schema": "agent-next/result@1",
        "demo": "demo-x",
        "headline": "The agent's beam passes every gate.",
        "verdict": "PASS",
        "gates": [{"name": "spec_limits", "pass": True,
                   "measured": "sigma 138.2 MPa",
                   "threshold": "<= 166.7 MPa"}],
        "numbers": [{"label": "sigma_wall", "value": 138.241,
                     "unit": "MPa", "source": "RECEIPT.md:2"}],
        "hero": {"kind": "image", "path": "media/result.png",
                 "caption": "the key figure"},
        "gallery": [
            {"kind": "image", "path": "media/loop.png"},
            {"kind": "video", "path": "media/demo.mp4",
             "poster": "media/result.png"},
        ],
        "launch": {"command": "python3 cookbook/demo-x/run.py",
                   "ask_agent": "Build the artifact and run the judge."},
        "receipt": "RECEIPT.md",
        "sandbox_commit": "a4ea685b2c3d4e5f60718293a4b5c6d7e8f90123",
    }


def write(tmp_path, doc):
    f = tmp_path / "media" / "result.json"
    f.write_text(json.dumps(doc, indent=2))
    return f


def test_valid_manifest_passes(tmp_path):
    root = make_demo(tmp_path)
    errors = result.check_manifest(write(root, valid_manifest()), root)
    assert errors == []


def test_write_result_roundtrip(tmp_path):
    root = make_demo(tmp_path)
    doc = valid_manifest()
    doc.pop("schema")  # write_result fills the schema id
    out = result.write_result(root / "media" / "result.json", **doc)
    assert json.loads(out.read_text())["schema"] == "agent-next/result@1"
    assert result.check_manifest(out, root) == []


def test_write_result_rejects_invalid(tmp_path):
    doc = valid_manifest()
    doc["verdict"] = "PASSING"
    with pytest.raises(ValueError, match="verdict"):
        result.write_result(tmp_path / "result.json", **doc)


# -- single-defect manifests: each fails exactly its own check -------------

DEFECTS = [
    ("missing field", lambda d: d.pop("headline"),
     "missing required field 'headline'"),
    ("bad verdict", lambda d: d.update(verdict="PASSING"),
     "must be one of ['PASS', 'FAIL']"),
    ("missing file", lambda d: d.update(receipt="NOPE.md"),
     "'NOPE.md' does not exist"),
    ("kind/magic mismatch", lambda d: d["hero"].update(kind="video"),
     "kind 'video' but 'media/result.png' sniffs as png"),
    ("number without source",
     lambda d: d["numbers"][0].update(source=""),
     "string shorter than 1"),
    ("bad schema id", lambda d: d.update(schema="other/result@9"),
     "must be 'agent-next/result@1'"),
]


@pytest.mark.parametrize("name,mutate,expect", DEFECTS,
                         ids=[d[0] for d in DEFECTS])
def test_single_defect_fails_its_check(tmp_path, name, mutate, expect):
    root = make_demo(tmp_path)
    doc = valid_manifest()
    mutate(doc)
    errors = result.check_manifest(write(root, doc), root)
    assert len(errors) == 1, f"{name}: expected exactly one error: {errors}"
    assert expect in errors[0], f"{name}: {errors[0]}"


def test_cli_exit_codes(tmp_path):
    root = make_demo(tmp_path)
    good = write(root, valid_manifest())
    ok = subprocess.run([sys.executable, str(TOOLS / "result.py"), "check",
                         str(good), "--root", str(root)],
                        capture_output=True, text=True)
    assert ok.returncode == 0 and ok.stdout.startswith("OK")

    doc = valid_manifest()
    doc["numbers"][0]["source"] = ""
    bad = write(root, doc)
    fail = subprocess.run([sys.executable, str(TOOLS / "result.py"), "check",
                           str(bad), "--root", str(root)],
                          capture_output=True, text=True)
    assert fail.returncode != 0 and "FAIL" in fail.stderr


# -- every committed manifest must pass ------------------------------------

COMMITTED = sorted(REPO.glob("cookbook/*/media/result.json"))


def test_committed_manifests_exist():
    assert COMMITTED, "no cookbook/*/media/result.json found"


@pytest.mark.parametrize("manifest", COMMITTED,
                         ids=[p.parent.parent.name for p in COMMITTED])
def test_committed_manifest_passes(manifest):
    errors = result.check_manifest(manifest)
    assert errors == [], f"{manifest}: {errors}"
