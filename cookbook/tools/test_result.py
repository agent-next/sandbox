"""Tests for cookbook/tools/result.py and the committed result.json files.

Run from the repo root:  python3 -m pytest -q cookbook/tools/test_result.py
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))
import result  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n"
       b"\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x00"
       b"\x00\x00\x00\x00" + b"\x00" * 32)


def _box(typ, payload):
    return (8 + len(payload)).to_bytes(4, "big") + typ + payload


def _moov(handler_type):
    """A moov/trak/mdia/hdlr box chain carrying one handler type."""
    hdlr = _box(b"hdlr", b"\x00" * 8 + handler_type + b"\x00" * 13)
    return _box(b"moov", _box(b"trak", _box(b"mdia", hdlr)))


# MP4: ftyp with MP4 brands + a 'vide' track handler, as ffmpeg writes it.
MP4 = (_box(b"ftyp", b"isom" + b"\x00\x00\x02\x00" + b"isomiso2")
       + _moov(b"vide"))
# Byte-minimal fallbacks used only when ffmpeg cannot produce the real thing.
M4A = (_box(b"ftyp", b"M4A " + b"\x00" * 4 + b"M4A isommp42")
       + _moov(b"soun"))
AVIF = _box(b"ftyp", b"avif" + b"\x00" * 4 + b"avifmif1")
GLB = b"glTF" + b"\x00" * 28


def _ffmpeg(out, *args):
    if shutil.which("ffmpeg") is None:
        return False
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", *args, str(out)],
                       capture_output=True)
    return p.returncode == 0


def avif_file(path):
    """A real AVIF still image via ffmpeg, else a byte-minimal ftyp avif."""
    if not _ffmpeg(path, "-f", "lavfi", "-i", "color=red:size=32x32",
                   "-frames:v", "1", "-c:v", "libaom-av1",
                   "-still-picture", "1"):
        path.write_bytes(AVIF)


def m4a_file(path):
    """A real audio-only M4A via ffmpeg, else a byte-minimal one."""
    if not _ffmpeg(path, "-f", "lavfi", "-i",
                   "sine=frequency=440:duration=0.2", "-c:a", "aac"):
        path.write_bytes(M4A)


def make_demo(tmp_path):
    """A minimal demo dir whose files satisfy every kind/magic check."""
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "result.png").write_bytes(PNG)
    (tmp_path / "media" / "loop.png").write_bytes(PNG)
    (tmp_path / "media" / "demo.mp4").write_bytes(MP4)
    (tmp_path / "media" / "model.glb").write_bytes(GLB)
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


# -- per-kind hero rules ----------------------------------------------------

# Each of these satisfies the shared anyOf today but violates its kind's
# field rules, so the checker currently reports OK.
BAD_HEROES = [
    ("model3d with only images",
     {"kind": "model3d", "before": "media/result.png",
      "after": "media/loop.png"}),
    ("image with no path/url",
     {"kind": "image", "before": "media/result.png",
      "after": "media/loop.png"}),
    ("compare backed by MP4",
     {"kind": "compare", "path": "media/demo.mp4"}),
    ("app without url",
     {"kind": "app", "path": "media/result.png"}),
    ("compare before is a video",
     {"kind": "compare", "before": "media/demo.mp4",
      "after": "media/result.png"}),
    ("video poster is a video",
     {"kind": "video", "path": "media/demo.mp4",
      "poster": "media/demo.mp4"}),
]


@pytest.mark.parametrize("hero", BAD_HEROES,
                         ids=[h[0] for h in BAD_HEROES])
def test_kind_rule_violations_fail(tmp_path, hero):
    root = make_demo(tmp_path)
    doc = valid_manifest()
    doc["hero"] = hero[1]
    errors = result.check_manifest(write(root, doc), root)
    assert errors, f"{hero[0]}: expected check errors, got OK"


GOOD_HEROES = [
    {"kind": "image", "url": "https://example.com/h.png"},
    {"kind": "video", "url": "https://example.com/v.mp4"},
    {"kind": "video", "path": "media/demo.mp4",
     "poster": "media/result.png"},
    {"kind": "model3d", "path": "media/model.glb"},
    {"kind": "model3d", "url": "https://example.com/m.glb"},
    {"kind": "compare", "before": "media/result.png",
     "after": "media/loop.png"},
    {"kind": "app", "url": "https://example.com/app",
     "poster": "media/result.png"},
]


@pytest.mark.parametrize("hero", GOOD_HEROES,
                         ids=[h["kind"] for h in GOOD_HEROES])
def test_kind_rule_valid_heroes_pass(tmp_path, hero):
    root = make_demo(tmp_path)
    doc = valid_manifest()
    doc["hero"] = hero
    errors = result.check_manifest(write(root, doc), root)
    assert errors == [], f"{hero['kind']}: {errors}"


# -- ISO-BMFF sniffing: ftyp alone is not proof of MP4 video ---------------

def test_avif_is_not_sniffed_as_video(tmp_path):
    root = make_demo(tmp_path)
    image = root / "media" / "hero.avif"
    avif_file(image)
    assert result._sniff(image) != "mp4"
    doc = valid_manifest()
    doc["hero"] = {"kind": "video", "path": "media/hero.avif"}
    errors = result.check_manifest(write(root, doc), root)
    assert errors, "AVIF still image accepted as kind 'video'"


def test_audio_only_m4a_is_not_sniffed_as_video(tmp_path):
    root = make_demo(tmp_path)
    audio = root / "media" / "voice.m4a"
    m4a_file(audio)
    assert result._sniff(audio) != "mp4"
    doc = valid_manifest()
    doc["hero"] = {"kind": "video", "path": "media/voice.m4a"}
    errors = result.check_manifest(write(root, doc), root)
    assert errors, "audio-only M4A accepted as kind 'video'"


def test_ftyp_with_video_track_sniffs_mp4(tmp_path):
    root = make_demo(tmp_path)
    assert result._sniff(root / "media" / "demo.mp4") == "mp4"


# -- path hygiene -----------------------------------------------------------

def test_escaping_path_reports_once(tmp_path):
    root = make_demo(tmp_path)
    doc = valid_manifest()
    doc["hero"] = {"kind": "image", "path": "../outside.png"}
    errors = result.check_manifest(write(root, doc), root)
    assert len(errors) == 1, f"duplicate diagnostics: {errors}"
    assert "escapes the demo root" in errors[0]


def test_receipt_must_be_a_regular_file(tmp_path):
    root = make_demo(tmp_path)
    doc = valid_manifest()
    doc["receipt"] = "."
    errors = result.check_manifest(write(root, doc), root)
    assert any("regular file" in e for e in errors), errors


# -- template run.py provenance ----------------------------------------------

def test_template_records_sandbox_clone_commit():
    """run.py must record the commit of the clone it graded, resolved
    inside the sandbox — not the caller's local HEAD."""
    expected = "c" * 40
    with tempfile.TemporaryDirectory(dir=REPO / "cookbook") as td:
        demo = Path(td)
        shutil.copytree(REPO / "cookbook" / "_template", demo,
                        dirs_exist_ok=True)
        spec = importlib.util.spec_from_file_location(
            "template_run", demo / "run.py")
        run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run)
        commands = []

        def sbx_stub(*args):
            return ("test-sandbox", 0) if args[0] == "create" else ("", 0)

        def exec_stub(sid, command, step_timeout=900):
            commands.append(command)
            if "rev-parse" in command:
                return expected + "\n", 0, 0.0
            return json.dumps({"verdict": "PASS", "gates": {"load": {
                "pass": True, "measured": 1, "threshold": 2}}}), 0, 0.0

        with patch.object(sys, "argv", [str(demo / "run.py"), "--ref", "main"]), \
                patch.object(run.shutil, "which", return_value="/usr/bin/sbx"), \
                patch.dict(os.environ, {"SBX_API_KEY": "<your key>"}), \
                patch.object(run, "sbx", side_effect=sbx_stub), \
                patch.object(run, "sbx_exec", side_effect=exec_stub), \
                contextlib.redirect_stdout(io.StringIO()):
            code = 0
            try:
                run.main()
            except SystemExit as exc:
                code = exc.code
        assert code == 0
        assert any("rev-parse HEAD" in c and "/tmp/repo" in c
                   for c in commands), \
            f"no sandbox-side rev-parse ran: {commands}"
        doc = json.loads((demo / "media" / "result.json").read_text())
        assert doc["sandbox_commit"] == expected


# -- every committed manifest must pass ------------------------------------

COMMITTED = sorted(REPO.glob("cookbook/*/media/result.json"))


def test_committed_manifests_exist():
    assert COMMITTED, "no cookbook/*/media/result.json found"


@pytest.mark.parametrize("manifest", COMMITTED,
                         ids=[p.parent.parent.name for p in COMMITTED])
def test_committed_manifest_passes(manifest):
    errors = result.check_manifest(manifest)
    assert errors == [], f"{manifest}: {errors}"
