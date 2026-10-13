"""The public recipe must release paid GPU resources on job failure."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def recipe(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "cookbook/small-gpu/run.py"
    spec = importlib.util.spec_from_file_location("small_gpu_recipe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("SBX_API_KEY", "test-only-key")
    return module


@pytest.mark.parametrize("execution", [
    (409, None),
    (200, {"result": {"ok": False}}),
    (200, {"result": {"ok": True, "report": {"sum": 0}}}),
])
def test_failed_job_still_destroys_and_confirms(recipe, monkeypatch, execution):
    replies = iter([(201, {"sandboxID": "gl-test-1"}), execution, (204, None), (404, None)])
    calls = []

    def request(key, method, path, body=None):
        calls.append((method, path))
        return next(replies)

    monkeypatch.setattr(recipe, "request", request)
    with pytest.raises(RuntimeError, match="GPU (exec|job)"):
        recipe.main()
    assert calls[-2:] == [("DELETE", "/sandboxes/gl-test-1"), ("GET", "/sandboxes/gl-test-1")]


def test_cleanup_acknowledgement_without_death_is_failure(recipe, monkeypatch):
    replies = iter([
        (201, {"sandboxID": "gl-test-1"}),
        (200, {"result": {"ok": True, "report": {"sum": 523776}}}),
        (204, None), (200, {"phase": "resident"}),
    ])
    monkeypatch.setattr(recipe, "request", lambda *args, **kwargs: next(replies))
    with pytest.raises(RuntimeError, match="cleanup unconfirmed"):
        recipe.main()


@pytest.mark.parametrize("gone", [True, False])
def test_lost_destroy_reply_still_checks_lease(recipe, monkeypatch, gone):
    calls = []

    def request(key, method, path, body=None):
        calls.append(method)
        if method == "DELETE":
            raise TimeoutError("destroy reply lost")
        if method == "GET":
            return (404, None) if gone else (200, {"phase": "resident"})
        if path.endswith("/exec"):
            return 200, {"result": {"ok": True, "report": {"sum": 523776}}}
        return 201, {"sandboxID": "gl-test-1"}

    monkeypatch.setattr(recipe, "request", request)
    if gone:
        recipe.main()
    else:
        with pytest.raises(RuntimeError, match="cleanup unconfirmed for gl-test-1"):
            recipe.main()
    assert calls[-2:] == ["DELETE", "GET"]
