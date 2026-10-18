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
import time

state_file = os.environ["FAKE_SBX_STATE"]
state_dir = os.path.dirname(state_file)

leaks = [k for k in ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE")
         if k in os.environ]
leaks += [k for k in os.environ if k.startswith("PIP_")]
if leaks:
    print("env leak: " + ",".join(leaks), file=sys.stderr)
    sys.exit(9)


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
        if state.get("gpu_create_fails_noid"):
            # allocated remotely, then the reply was lost with no id printed
            print("fake sbx: gpu create lost, no id", file=sys.stderr)
            sys.exit(1)
        print(lid)
        if state.get("gpu_create_fails"):
            # allocated remotely, then the reply was lost
            print("fake sbx: gpu create lost", file=sys.stderr)
            sys.exit(1)
    elif sub == "list":
        if state.get("empty_list"):
            print("[]")
        else:
            print(json.dumps([{"sandboxID": i} for i in state["gpu"]]))
    elif sub == "exec":
        if state.get("gpu_exec_bad_output"):
            print("not cuda")
        elif state.get("gpu_exec_key_output"):
            # the key lands 72 chars in, so an 80-char truncation applied
            # before scrubbing leaks its first 8 characters
            print("x" * 72 + os.environ.get("FAKE_SBX_ERROR_KEY", "test-key-value"))
        else:
            print("cuda ok")
    elif sub == "kill":
        state.setdefault("killed", []).append(rest[0])
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
    if state.get("empty_list"):
        print("[]")
    elif state.get("whitespace_ids"):
        # ids that carry no information: they must not count as verified
        print(json.dumps([{"sandboxID": " "} for _ in state["cpu"]]))
    elif state.get("bad_list_keys"):
        # entries carry an id under an unrecognized key
        print(json.dumps([{"id": i} for i in state["cpu"]]))
    elif state.get("nonlist"):
        print(json.dumps({"oops": "not a list"}))
    else:
        print(json.dumps([{"sandboxID": i} for i in state["cpu"]]))
elif cmd == "create":
    sid = "sbx-fake-%d" % (len(state["cpu"]) + 1)
    state["cpu"].append(sid)
    save(state)
    if state.get("concurrent_client"):
        # another client's sandbox appears while ours is being created:
        # new ids in the inventory are not necessarily ours
        state["cpu"].append("sbx-other-job")
        del state["concurrent_client"]
        save(state)
    if state.get("create_fails_noid"):
        # allocated remotely, then the reply was lost with no id printed
        print("fake sbx: create lost, no id", file=sys.stderr)
        sys.exit(1)
    print(sid)
    if state.get("create_fails_after_print"):
        # allocated remotely, id printed, then the reply was lost
        print("fake sbx: create lost", file=sys.stderr)
        sys.exit(1)
    if state.get("create_fails"):
        # allocated remotely, then the reply was lost: nonzero exit after
        # the id was already printed
        print("fake sbx: create lost", file=sys.stderr)
        sys.exit(1)
elif cmd == "exec":
    if state.get("hang"):
        time.sleep(30)
    if state.get("exec_bad_output"):
        print("nope")
    else:
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
    state.setdefault("killed", []).append(rest[0])
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


def test_unrecognized_inventory_is_not_absence(fake_sbx, key, tmp_path, capsys):
    # an entry without a recognized id field: the inventory is UNKNOWN, so
    # the run must fail ("cannot confirm cleanup"), never count as absence
    fake_sbx.write_text(json.dumps({"cpu": ["sbx-fake-1"], "gpu": [], "bad_list_keys": 1}))
    rc, receipt = run_smoke(tmp_path)
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out
    checks = [s for s in receipt["steps"] if s["name"] == "leftover-check"]
    assert checks and checks[-1]["rc"] == 1
    assert "could not" in checks[-1].get("error", "")
    assert receipt["verdict"] == "fail"


def test_nonlist_inventory_is_not_absence(fake_sbx, key, tmp_path, capsys):
    # a list reply that is not a JSON list: same rule, unknown, fail
    fake_sbx.write_text(json.dumps({"cpu": ["sbx-fake-1"], "gpu": [], "nonlist": 1}))
    rc, receipt = run_smoke(tmp_path)
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out
    checks = [s for s in receipt["steps"] if s["name"] == "leftover-check"]
    assert checks and checks[-1]["rc"] == 1
    assert receipt["verdict"] == "fail"


def test_create_failure_with_printed_id_still_kills(
    fake_sbx, key, tmp_path, capsys
):
    # create allocated remotely, printed the id, then exited 1 (lost reply):
    # the sandbox is ours, so cleanup must kill it and the run must fail
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "create_fails": 1}))
    rc, receipt = run_smoke(tmp_path)
    capsys.readouterr()
    assert rc == 1
    assert receipt["verdict"] == "fail"
    # the sandbox was killed: the stub's inventory ends empty and the run
    # does not report anything left
    assert json.loads(fake_sbx.read_text())["cpu"] == []
    assert receipt["left"] == 0
    kill_steps = [s for s in receipt["steps"]
                  if s["name"] in ("kill", "cleanup-kill")]
    assert kill_steps, "a lost create reply must still be killed"
    assert "sbx-fake-1" in " ".join(
        step.get("error", "") for step in kill_steps) or any(
        step["rc"] == 0 for step in kill_steps)
    # create-id records why the run failed
    entry = next(s for s in receipt["steps"] if s["name"] == "create-id")
    assert entry["rc"] == 1
    assert "allocated" in entry.get("error", "")


def test_gpu_create_lost_reply_still_killed(fake_sbx, key, tmp_path, capsys):
    # a GPU create that allocated, printed the lease id and then exited 1:
    # the lease is ours, so cleanup must kill it and the run must fail
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "gpu_create_fails": 1}))
    rc, receipt = run_smoke(tmp_path, "--gpu")
    capsys.readouterr()
    assert rc == 1
    assert receipt["verdict"] == "fail"
    assert json.loads(fake_sbx.read_text())["gpu"] == []
    assert receipt["left"] == 0
    entry = next(s for s in receipt["steps"] if s["name"] == "gpu-create-id")
    assert entry["rc"] == 1
    assert "allocated" in entry.get("error", "")


def test_cpu_create_lost_reply_without_id_is_reported_not_killed(
    fake_sbx, key, tmp_path, capsys
):
    # a CPU create that allocated but lost its reply without printing an id:
    # ownership cannot be proven, so the run must kill nothing, fail, and
    # report the unattributed sandbox as a leftover for a human
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "create_fails_noid": 1}))
    rc, receipt = run_smoke(tmp_path)
    capsys.readouterr()
    assert rc == 1
    assert receipt["verdict"] == "fail"
    assert json.loads(fake_sbx.read_text())["cpu"] == ["sbx-fake-1"]
    assert receipt["left"] == 1
    assert receipt["left_ids"] == ["sbx-fake-1"]
    entry = next(s for s in receipt["steps"] if s["name"] == "create-id")
    assert entry["rc"] == 1
    kills = [s for s in receipt["steps"]
             if s["name"] in ("kill", "cleanup-kill")
             and not s.get("skipped")]
    assert not kills, "an unattributed id must never be killed"


def test_sweep_never_kills_unrelated_new_sandboxes(
    fake_sbx, key, tmp_path, capsys
):
    # another client's sandbox appears in the inventory while our create
    # fails without printing an id: the id difference cannot prove which
    # new sandbox is ours, so the sweep must kill nothing; the run fails
    # and every new id is reported as a leftover for a human instead
    fake_sbx.write_text(json.dumps(
        {"cpu": [], "gpu": [], "create_fails_noid": 1, "concurrent_client": 1}))
    rc, receipt = run_smoke(tmp_path)
    capsys.readouterr()
    assert rc == 1
    assert receipt["verdict"] == "fail"
    # nothing was destroyed: our lost create and the other client's sandbox
    # are both still in the stub's inventory, and no kill ever ran
    state = json.loads(fake_sbx.read_text())
    assert state["cpu"] == ["sbx-fake-1", "sbx-other-job"]
    assert state.get("killed", []) == []
    # both new ids are reported as leftovers, never killed
    assert receipt["left"] == 2
    assert receipt["left_ids"] == ["sbx-fake-1", "sbx-other-job"]


def test_gpu_create_lost_reply_without_id_is_reported_not_killed(
    fake_sbx, key, tmp_path, capsys
):
    # same rule for GPU leases: a create with no printed id owns nothing,
    # so the lease stays alive and is reported instead of swept and killed
    fake_sbx.write_text(json.dumps(
        {"cpu": [], "gpu": [], "gpu_create_fails_noid": 1}))
    rc, receipt = run_smoke(tmp_path, "--gpu")
    capsys.readouterr()
    assert rc == 1
    assert receipt["verdict"] == "fail"
    state = json.loads(fake_sbx.read_text())
    assert state["gpu"] == ["gl-fake-1"]
    assert state.get("killed", []) == ["sbx-fake-1"]  # only the cpu sandbox died
    assert receipt["left"] == 1
    assert receipt["left_ids"] == ["gl-fake-1"]
    entry = next(s for s in receipt["steps"] if s["name"] == "gpu-create-id")
    assert entry["rc"] == 1


def test_invalid_id_strings_are_not_verified_inventory(
    fake_sbx, key, tmp_path, capsys, monkeypatch
):
    # ids that are blank/non-printable carry no information: an inventory
    # made only of such ids is unverifiable, so the run must fail rather
    # than treat the set difference as proof of absence. keep-alive makes
    # the kill a no-op, mirroring the reported pass-while-alive repro
    monkeypatch.setenv("FAKE_SBX_KEEP", "1")
    fake_sbx.write_text(json.dumps({"cpu": ["sbx-fake-1"], "gpu": [], "whitespace_ids": 1}))
    rc, receipt = run_smoke(tmp_path)
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out
    checks = [s for s in receipt["steps"] if s["name"] == "leftover-check"]
    assert checks and checks[-1]["rc"] == 1
    assert receipt["verdict"] == "fail"
    # the sandbox created by this run is reported as left (the pre-existing
    # sbx-fake-1 was there before, so it is not this run's leftover)
    assert receipt["left"] == 1
    assert receipt["left_ids"] == ["sbx-fake-2"]


def test_inventory_must_see_the_created_sandbox(fake_sbx, key, tmp_path, capsys):
    # a list implementation that never shows the new sandbox (always [])
    # can't prove anything about cleanup: the run must fail, not pass
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "empty_list": 1}))
    rc, receipt = run_smoke(tmp_path)
    capsys.readouterr()
    assert rc == 1
    assert receipt["verdict"] == "fail"
    checks = [s for s in receipt["steps"] if s["name"] == "leftover-check"]
    assert checks and checks[-1]["rc"] == 1


def test_inventory_must_see_the_created_lease(fake_sbx, key, tmp_path, capsys):
    # same rule for GPU leases: an empty gpu list during the run fails it
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "empty_list": 1}))
    rc, receipt = run_smoke(tmp_path, "--gpu")
    capsys.readouterr()
    assert rc == 1
    assert receipt["verdict"] == "fail"


def test_exec_probe_verifies_output(fake_sbx, key, tmp_path, capsys):
    # exec exits 0 but prints the wrong thing: the probe failed
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "exec_bad_output": 1}))
    rc, receipt = run_smoke(tmp_path)
    capsys.readouterr()
    assert rc == 1
    entry = next(s for s in receipt["steps"] if s["name"] == "exec-check")
    assert entry["rc"] == 1


def test_gpu_exec_probe_verifies_output(fake_sbx, key, tmp_path, capsys):
    # gpu exec exits 0 but never prints "cuda ok": the probe failed
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "gpu_exec_bad_output": 1}))
    rc, receipt = run_smoke(tmp_path, "--gpu")
    capsys.readouterr()
    assert rc == 1
    entry = next(s for s in receipt["steps"] if s["name"] == "gpu-exec-check")
    assert entry["rc"] == 1


def test_gpu_exec_error_scrubs_key_before_truncation(
    fake_sbx, key, tmp_path, capsys
):
    # gpu exec prints the key 72 chars into its output: the 80-char error
    # cut must scrub first, or the first 8 key characters survive in the
    # receipt and on stdout
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "gpu_exec_key_output": 1}))
    rc, receipt = run_smoke(tmp_path, "--gpu")
    out = capsys.readouterr().out
    assert rc == 1
    entry = next(s for s in receipt["steps"] if s["name"] == "gpu-exec-check")
    assert entry["rc"] == 1
    for i in range(4, len("test-key-value") + 1):
        assert "test-key-value"[:i] not in entry.get("error", "")
    assert "test-key-value" not in out
    assert "test-key-value" not in json.dumps(receipt)


def test_runner_exception_still_writes_verdict_and_receipt(
    fake_sbx, key, tmp_path, capsys, monkeypatch
):
    # an unexpected exception (e.g. install produced no sbx entry point)
    # must still end in a FAIL verdict and a receipt on disk
    monkeypatch.setattr(
        rs, "cmd_install",
        lambda venv, ref: [str(Path(__file__).parent / "helper-missing.py")],
    )
    rc, receipt = run_smoke(tmp_path)
    out = capsys.readouterr().out
    assert rc == 1
    assert out.startswith("FAIL")
    assert receipt["verdict"] == "fail"
    assert receipt["left"] == 0


def test_hanging_step_is_killed_at_deadline(
    fake_sbx, key, tmp_path, capsys, monkeypatch
):
    # a step that never exits is killed at the step deadline and recorded
    # as a failure; the run still terminates and cleans up
    monkeypatch.setattr(rs, "STEP_TIMEOUT_S", 2)
    fake_sbx.write_text(json.dumps({"cpu": [], "gpu": [], "hang": 1}))
    rc, receipt = run_smoke(tmp_path)
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out
    entry = next(s for s in receipt["steps"] if s["name"] == "exec")
    assert entry["rc"] != 0
    assert "timed out" in entry.get("error", "").lower()
    assert json.loads(fake_sbx.read_text())["cpu"] == []
    assert receipt["left"] == 0


def test_python_env_is_scrubbed_for_sbx_calls(
    fake_sbx, key, tmp_path, capsys, monkeypatch
):
    # inherited PYTHONPATH/PYTHONHOME/PYTHONUSERBASE/PIP_* must not leak
    # into the fresh venv: the stub fails with rc 9 if it sees any of them
    monkeypatch.setenv("PYTHONPATH", "/some/checkout/path")
    monkeypatch.setenv("PYTHONHOME", "/some/other/python")
    monkeypatch.setenv("PYTHONUSERBASE", "/some/user/site")
    monkeypatch.setenv("PIP_INDEX_URL", "https://example.invalid/simple")
    rc, receipt = run_smoke(tmp_path)
    capsys.readouterr()
    assert rc == 0
    assert receipt["verdict"] == "pass" and receipt["left"] == 0
