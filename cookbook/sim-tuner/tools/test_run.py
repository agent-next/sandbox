"""Regressions for the uploaded job and the user-facing runner."""

import contextlib
import io

import pytest

from test_rendered_job import exec_with_stubs, load_run


def test_grade_has_measured_wall_time(tmp_path):
    run = load_run()
    state, _ = exec_with_stubs(run.render_job(run.pack_demo(), 7), str(tmp_path))
    assert isinstance(state["report"]["stages"]["grade"]["wall_s"], (int, float)), \
        "grade must report measured wall time, not None"


def test_selftest_only_does_not_grade(tmp_path):
    run = load_run()
    src = run.render_job(run.pack_demo(), 7, selftest_only=True)
    state, calls = exec_with_stubs(src, str(tmp_path))
    assert "selftest" in state["report"]["stages"]
    assert "grade" not in state["report"]["stages"], \
        "--selftest-only must skip the final grade"


def test_main_prints_full_verdict_and_selftest(monkeypatch):
    run = load_run()
    verdict = {"pass": True, "verdict": "PASS", "seed": 7,
               "gates": {}, "judge_intact": True}
    report = {"verdict": verdict, "stages": {
        "stack-check": {"rc": 0, "wall_s": 0.1},
        "selftest": {"rc": 0, "wall_s": 1, "stdout_tail": "selftest: kill rate: 18/18 = 100%"},
        "grade": {"rc": 0, "wall_s": 2}}}
    calls = []

    def request(key, method, path, body=None, **kwargs):
        calls.append((method, path))
        if method == "POST" and path == "/sandboxes":
            return 201, {"sandboxID": "gl-test"}
        if method == "POST":
            return 200, {"result": {"ok": True, "report": report}}
        return (404, None) if method == "GET" else (204, None)

    monkeypatch.setenv("SBX_API_KEY", "test-only")
    monkeypatch.setattr(run, "request", request)
    monkeypatch.setattr("sys.argv", ["run.py"])
    output = io.StringIO()
    with contextlib.redirect_stdout(output), pytest.raises(SystemExit) as exc:
        run.main()
    assert exc.value.code == 0
    assert '"judge_intact": true' in output.getvalue(), "print the complete verdict JSON"
    assert "selftest: kill rate: 18/18 = 100%" in output.getvalue()
    assert calls[-2:] == [("DELETE", "/sandboxes/gl-test"), ("GET", "/sandboxes/gl-test")]
