"""run.py cleanup: an unconfirmed kill is a failure, never "confirmed gone".

Run:  python3 -m pytest cookbook/pr-review-agent/tests -q

Covers the LESSONS.md shape (616b07c / d877345 / e08022b): a 503 on both
`sbx kill` and `sbx list` must exit non-zero naming the sandbox id, instead
of printing "killed and confirmed gone" off an empty listing.  Against the
pre-fix run.py the first test fails on its exit-code assertion.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

RUN_PY = Path(__file__).resolve().parents[1] / "run.py"


def load_run():
    spec = importlib.util.spec_from_file_location("pr_review_run", RUN_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VERDICT = json.dumps({
    "passed": True, "failed_gate": None,
    "gates": {
        "g2_coverage": {"caught": 4, "planted": 4},
        "g3_clean_prs": {"major_findings_on_clean_prs": 0},
        "g4_failing_test": {"passed": True},
        "g5_passing_test": {"passed": True},
    },
})


class FakeSbx:
    """Answers `sbx` calls from scripted kill/list results.

    kill_results / list_results are consumed one per call; the last entry
    repeats.  Each entry is (returncode, stdout).
    """

    SID = "0123abcd-45ef-6789-abcd-ef0123456789"

    def __init__(self, kill_results, list_results):
        self.kill_results = list(kill_results)
        self.list_results = list(list_results)
        self.calls = []

    def __call__(self, *args, timeout=120.0):
        self.calls.append(args)
        if args[0] == "--version":
            rc, out = 0, "sbx 0.0.1\n"
        elif args[0] == "create":
            rc, out = 0, f"{self.SID}\n"
        elif args[0] == "exec":
            rc, out = 0, VERDICT + "\n"
        elif args[0] == "kill":
            rc, out = self.kill_results.pop(0) if len(self.kill_results) > 1 \
                else self.kill_results[0]
        elif args[0] == "list":
            rc, out = self.list_results.pop(0) if len(self.list_results) > 1 \
                else self.list_results[0]
        else:
            raise AssertionError(f"unexpected sbx call {args!r}")
        return subprocess.CompletedProcess(args, rc, stdout=out, stderr="")


@pytest.fixture
def run(monkeypatch):
    mod = load_run()
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    monkeypatch.setattr(sys, "argv", ["run.py"])
    return mod


def exercise(run, fake):
    """Run main() with the fake sbx in place; return its exit code.

    load_run() builds a fresh module per test, so assigning mod.sbx here
    leaks nowhere.
    """
    run.sbx = fake
    try:
        return run.main()
    except SystemExit as exc:
        return exc.code


def test_kill_and_list_both_503_exits_nonzero(run, capsys):
    """The prod-1 quota-blip shape (review PR #74): 503 on kill AND list —
    exit 1, name the id, never print "killed and confirmed gone"."""
    fake = FakeSbx(kill_results=[(1, "")], list_results=[(503, "")])
    code = exercise(run, fake)
    out, err = capsys.readouterr()
    assert code == 1, "an unconfirmed kill must not exit 0"
    assert fake.SID in err, "the failure must name the sandbox id"
    assert "killed and confirmed gone" not in out


def test_list_503_exits_nonzero(run, capsys):
    """Kill lands, but the confirming list 503s: still unconfirmed, exit 1."""
    fake = FakeSbx(kill_results=[(0, "killed\n")],
                   list_results=[(503, "")])
    code = exercise(run, fake)
    out, err = capsys.readouterr()
    assert code == 1
    assert fake.SID in err
    assert "cannot confirm" in err
    assert "killed and confirmed gone" not in out


def test_kill_503_alone_still_succeeds_because_list_confirms(run, capsys):
    """A 503'd kill that a clean list proves dead exits 0.

    `sbx list` exiting 0 without the id means the lookup ran and the
    sandbox is gone, so the run is a success even though the kill command
    itself 503'd (a lost reply is not a failed kill — LESSONS.md d877345).
    run.py does not retry the kill: the listing decides.
    """
    fake = FakeSbx(kill_results=[(503, "")], list_results=[(0, "")])
    code = exercise(run, fake)
    out, err = capsys.readouterr()
    assert code == 0
    assert f"killed and confirmed gone: {fake.SID}" in out
    assert "WARNING kill exit 503" in err
    assert sum(1 for c in fake.calls if c[0] == "kill") == 1


def test_still_listed_after_kill_exits_nonzero(run, capsys):
    """A kill that 'succeeded' while the list still shows the id fails."""
    fake = FakeSbx(kill_results=[(0, "killed\n")],
                   list_results=[(0, f"{FakeSbx.SID}\ttemplate\t2026-01-01Z\n")])
    code = exercise(run, fake)
    out, err = capsys.readouterr()
    assert code == 1
    assert fake.SID in err
    assert "still live" in err
    assert "killed and confirmed gone" not in out


def test_id_requires_a_whole_column_match(run, capsys):
    """A *substring* of another sandbox's id must not read as still-live."""
    other = FakeSbx.SID + "ff"  # contains the killed id as a substring
    fake = FakeSbx(kill_results=[(0, "killed\n")],
                   list_results=[(0, f"{other}\ttemplate\t2026-01-01Z\n")])
    code = exercise(run, fake)
    out, _ = capsys.readouterr()
    assert code == 0
    assert "killed and confirmed gone" in out
