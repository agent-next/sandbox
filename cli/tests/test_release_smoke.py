"""Tests for scripts/release_smoke.py using a fake `sbx` on PATH.

The smoke script creates a venv, pip-installs the CLI into it and then runs
the installed `sbx` binary. The fixture replaces the venv and install steps
with commands that drop a stub `sbx` executable (below) into the venv's bin
directory, so every later step runs the stub as a real subprocess with the
script's real argument handling, timeouts and JSON parsing.

The stub keeps its inventory in the JSON file named by FAKE_SBX_STATE, so
tests can assert what the smoke run actually left behind.
"""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release_smoke.py"
spec = importlib.util.spec_from_file_location("release_smoke", SCRIPT)
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

STUB = r"""#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import sys

state_file = os.environ["FAKE_SBX_STATE"]
state_dir = os.path.dirname(state_file)


def load():
    try:
        with open(state_file) as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return {"cpu": [], "gpu": []}


def save(state):
    with open(state_file, "w") as stream:
        json.dump(state, stream)


def maybe_fail(name):
    if os.environ.get("FAKE_SBX_FAIL") == name:
        key = os.environ.get("FAKE_SBX_ERROR_KEY", "test-key-value")
        # straddle the key across the 300-char truncation boundary so a
        # truncate-then-scrub implementation leaks at least 8 key characters
        sys.stderr.write("x" * 292 + key + ": more\n")
        sys.exit(1)


def remote(value):
    sid, sep, path = value.partition(":")
    return (sid, path) if sep and "/" not in sid else None


args = sys.argv[1:]
if args == ["--version"]:
    print(os.environ.get("FAKE_SBX_VERSION", "0.0.3"))
    sys.exit(0)

if args[0] == "gpu":
    sub, rest = args[1], args[2:]
    maybe_fail("gpu-" + sub)
    state = load()
    if sub == "create":
        lid = "gl-fake-%d" % (len(state["gpu"]) + 1)
        state["gpu"].append(lid)
        save(state)
        print(lid)
    elif sub == "list":
        print(json.dumps([{"sandboxID": i} for i in state["gpu"]]))
    elif sub == "exec":
        print("cuda ok")
    elif sub == "kill":
        if not os.environ.get("FAKE_SBX_KEEP"):
            state["gpu"] = [i for i in state["gpu"] if i != rest[0]]
            save(state)
        print("killed " + rest[0])
    sys.exit(0)

cmd, rest = args[0], args[1:]
maybe_fail(cmd)
state = load()
if cmd == "templates":
    print("base")
elif cmd == "list":
    print(json.dumps([{"sandboxID": i} for i in state["cpu"]]))
elif cmd == "create":
    sid = "sbx-fake-%d" % (len(state["cpu"]) + 1)
    state["cpu"].append(sid)
    save(state)
    print(sid)
elif cmd == "exec":
    print("ok")
elif cmd == "cp":
    src, dst = rest[0], rest[1]
    sid, path = remote(src) or remote(dst)
    store = os.path.join(
        state_dir, hashlib.sha256((sid + ":" + path).encode()).hexdigest()
    )
    if remote(src):
        if state.get("missing_cp"):
            sys.exit(0)  # exit 0 but produce no downloaded file
        if state.get("corrupt_cp"):
            shutil.copyfile(store, dst)
            with open(dst, "a") as stream:
                stream.write("corrupted\n")
        else:
            shutil.copyfile(store, dst)
    else:
        shutil.copyfile(src, store)
elif cmd == "kill":
    if state.get("kill_fail"):
        state["kill_fail"] -= 1
        save(state)
        print("fake sbx: kill refused", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("FAKE_SBX_KEEP"):
        state["cpu"] = [i for i in state["cpu"] if i != rest[0]]
        save(state)
    print("killed " + rest[0])
sys.exit(0)
"""


@pytest.fixture
def fake_sbx(tmp_path, monkeypatch):
    """Point the smoke script's venv/install steps at the stub `sbx`."""
    state = tmp_path / "state.json"
    monkeypatch.setenv("FAKE_SBX_STATE", str(state))
    for name in ("FAKE_SBX_FAIL", "FAKE_SBX_KEEP", "FAKE_SBX_VERSION"):
        monkeypatch.delenv(name, raising=False)

    def install(venv, ref):
        stub = rs.venv_bin(venv) / "sbx"
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text(STUB)
        stub.chmod(0o755)
        return ["true"]

    monkeypatch.setattr(
        rs, "cmd_venv", lambda venv: ["mkdir", "-p", str(rs.venv_bin(venv))]
    )
    monkeypatch.setattr(rs, "cmd_install", install)
    return state


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("SBX_API_KEY", "test-key-value")


def run_smoke(tmp_path, *extra, ref="v0.0.3"):
    receipt = tmp_path / "receipt.json"
    rc = rs.main(["--ref", ref, "--json", str(receipt), *extra])
    return rc, json.loads(receipt.read_text())


def step_names(receipt):
    return [step["name"] for step in receipt["steps"]]


def test_pass(fake_sbx, key, tmp_path, capsys):
    rc, receipt = run_smoke(tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("PASS ref=v0.0.3")
    assert receipt["verdict"] == "pass" and receipt["left"] == 0
    for name in (
        "venv", "install", "version", "version-check", "templates",
        "list-before", "create", "exec", "cp-up", "cp-down", "cp-verify",
        "kill", "list-after",
    ):
        assert name in step_names(receipt)
    assert all(step["rc"] == 0 for step in receipt["steps"])
    assert all(step["duration_s"] >= 0 for step in receipt["steps"])
    # the key never reaches stdout or the receipt
    assert "test-key-value" not in out
    assert "test-key-value" not in json.dumps(receipt)
    # the stub's inventory confirms the sandbox is really gone
    assert json.loads(fake_sbx.read_text())["cpu"] == []


def test_failing_step_still_kills(fake_sbx, key, tmp_path, capsys, monkeypatch):
    # exec fails and the first `sbx kill` is refused, so only the finally
    # cleanup can get rid of the sandbox
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "kill_fail": 1}))
    monkeypatch.setenv("FAKE_SBX_FAIL", "exec")
    rc, receipt = run_smoke(tmp_path)
    out = capsys.readouterr().out
    assert rc == 1
    assert out.startswith("FAIL")
    # the key is scrubbed before truncation: no part of it may survive in
    # the receipt, even when it straddles the 300-char boundary
    entry = next(s for s in receipt["steps"] if s["name"] == "exec")
    assert entry["rc"] == 1
    for i in range(4, len("test-key-value") + 1):
        assert "test-key-value"[:i] not in entry.get("error", "")
    kills = [s for s in receipt["steps"] if "kill" in s["name"]]
    assert any(s["rc"] != 0 for s in kills)
    assert kills[-1]["rc"] == 0
    assert receipt["left"] == 0
    assert json.loads(fake_sbx.read_text())["cpu"] == []


def test_leftover_is_a_failure(fake_sbx, key, tmp_path, capsys, monkeypatch):
    # `sbx kill` exits 0 but the sandbox stays in the inventory
    monkeypatch.setenv("FAKE_SBX_KEEP", "1")
    rc, receipt = run_smoke(tmp_path)
    out = capsys.readouterr().out
    assert rc == 1
    assert out.startswith("FAIL")
    assert "left=1" in out
    assert receipt["left"] == 1
    assert receipt["left_ids"] == ["sbx-fake-1"]


def test_no_key_runs_install_and_version_only(fake_sbx, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SBX_API_KEY", raising=False)
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    rc, receipt = run_smoke(tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("PASS")
    assert "keyless" in out or "no key" in out
    assert receipt["keyless"] is True
    assert step_names(receipt) == ["venv", "install", "version", "version-check"]
    assert not fake_sbx.exists() or json.loads(fake_sbx.read_text())["cpu"] == []


def test_gpu_lease_cycle(fake_sbx, key, tmp_path, capsys):
    rc, receipt = run_smoke(tmp_path, "--gpu")
    assert rc == 0
    assert capsys.readouterr().out.startswith("PASS")
    for name in (
        "gpu-list-before", "gpu-create", "gpu-exec", "gpu-kill", "gpu-list-after"
    ):
        assert name in step_names(receipt)
    assert receipt["left"] == 0
    state = json.loads(fake_sbx.read_text())
    assert state["gpu"] == [] and state["cpu"] == []


def test_version_mismatch_fails(fake_sbx, key, tmp_path, capsys):
    rc, receipt = run_smoke(tmp_path, ref="v9.9.9")
    assert rc == 1
    assert "FAIL" in capsys.readouterr().out
    entry = next(s for s in receipt["steps"] if s["name"] == "version-check")
    assert entry["rc"] == 1


def test_passing_check_records_detail_not_error(fake_sbx, key, tmp_path, capsys):
    # a passing check carries its text as `detail`; a failing one as `error`
    rc, receipt = run_smoke(tmp_path, ref="v9.9.9")
    capsys.readouterr()
    entry = next(s for s in receipt["steps"] if s["name"] == "version-check")
    assert entry["rc"] == 1
    assert "error" in entry and "detail" not in entry

    rc, receipt = run_smoke(tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    entry = next(s for s in receipt["steps"] if s["name"] == "version-check")
    assert entry["rc"] == 0
    assert "detail" in entry and "error" not in entry
    assert "error" not in json.dumps(receipt)
    assert "version-check" not in out or "FAIL" not in out


def test_sha_mismatch_error_only_on_failure(fake_sbx, key, tmp_path, capsys, monkeypatch):
    # cp-up produces a wrong copy, so cp-verify fails with an error field and
    # no error text is ever recorded for a passing cp-verify
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "corrupt_cp": 1}))
    rc, receipt = run_smoke(tmp_path)
    capsys.readouterr()
    assert rc == 1
    entry = next(s for s in receipt["steps"] if s["name"] == "cp-verify")
    assert entry["rc"] == 1
    assert "sha256 mismatch" in entry.get("error", "")
    assert "detail" not in entry

    # and a passing cycle never records the sha text at all
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": []}))
    monkeypatch.delenv("FAKE_SBX_FAIL", raising=False)
    rc, receipt = run_smoke(tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    entry = next(s for s in receipt["steps"] if s["name"] == "cp-verify")
    assert entry["rc"] == 0
    assert "sha256" not in json.dumps(receipt)
    assert "sha256" not in out


def test_cp_verify_fails_when_download_produces_nothing(
    fake_sbx, key, tmp_path, capsys
):
    # cp-up and cp-down both exit 0 but cp-down writes no file: the round
    # trip failed, so cp-verify must be a failed check, never skipped
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "missing_cp": 1}))
    rc, receipt = run_smoke(tmp_path)
    capsys.readouterr()
    assert rc == 1
    entry = next(s for s in receipt["steps"] if s["name"] == "cp-verify")
    assert "skipped" not in entry
    assert entry["rc"] == 1
    assert "missing" in entry.get("error", "")
    # the sandbox is still killed and nothing is left behind
    assert receipt["left"] == 0
    assert json.loads(fake_sbx.read_text())["cpu"] == []
