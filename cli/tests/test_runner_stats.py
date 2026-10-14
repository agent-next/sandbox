import copy
import json
from pathlib import Path

import pytest
import httpx

from sbx import runner_stats as stats
from sbx import cli, runners


FIXTURES = Path(__file__).parent / "fixtures" / "runner_stats"


def recording(name="mixed"):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def jobs(name="mixed"):
    return [job for page in recording(name)["jobs_pages"] for job in page["jobs"]]


def test_recorded_mixed_run_has_exact_timing_cost_and_hosted_comparison():
    report = stats.build_report("OWNER/REPO", jobs())
    assert len(report["jobs"]) == 9
    summary = report["summary"]
    assert summary["wait_s"] == {"samples": 9, "median": 1, "p95": 2}
    assert summary["run_s"] == {"samples": 9, "median": 36, "p95": 132}
    assert summary["failures"] == 0
    assert summary["vcpu_minutes"] == pytest.approx(12.3)
    assert summary["estimated_cost"] == pytest.approx(0.0246)
    assert summary["size_assumed_jobs"] == 9
    hosted = report["github_hosted"]["summary"]
    assert hosted["wait_s"] == {"samples": 9, "median": 2, "p95": 3}
    assert hosted["run_s"] == {"samples": 9, "median": 13, "p95": 61}
    assert hosted["vcpu_minutes"] is None
    assert report["comparisons"][0]["median_wait_delta_s"] == -1
    assert report["comparisons"][0]["median_run_delta_s"] == 23
    assert report["jobs"][0]["run_attempt"] == 16


def test_recorded_cancelled_job_retains_step_timing_and_is_not_a_failure():
    report = stats.build_report("OWNER/REPO", jobs("cancelled"))
    job = report["jobs"][0]
    assert (job["wait_s"], job["run_s"], job["conclusion"]) == (2, 74, "cancelled")
    assert [step["run_s"] for step in job["steps"]] == [0, 71, 1]
    assert [step["conclusion"] for step in job["steps"]] == ["success", "cancelled", "success"]
    assert report["summary"]["failures"] == 0
    assert report["summary"]["cancelled"] == 1
    assert report["comparisons"] == []


def test_recorded_live_serve_log_has_exact_ready_and_reclaim_oracles():
    report = stats.build_report("OWNER/REPO", jobs(), events=recording()["serve_events"])
    assert report["summary"]["vm_ready_s"] == {"samples": 9, "median": 1.26, "p95": 2.217}
    assert report["summary"]["reclaim_s"] == {"samples": 9, "median": 1.154, "p95": 1.597}
    first = report["jobs"][0]["lifecycle"]
    assert first["vm_ready_s"] == 1.679
    assert first["reclaim_s"] == 0.757
    assert first["queue_to_vm_ready_s"] == 0


def test_recorded_failed_steps_and_skips_are_not_invented_durations():
    report = stats.build_report("OWNER/REPO", jobs("failed"))
    failing = [job for job in report["jobs"] if job["conclusion"] == "failure"]
    assert len(failing) == 2
    assert sorted(job["run_s"] for job in failing) == [3, 58]
    assert report["summary"]["failures"] == 2
    assert any(step["conclusion"] == "failure" for job in failing for step in job["steps"])
    skipped = [step for job in report["jobs"] for step in job["steps"]
               if step["conclusion"] == "skipped"]
    assert skipped
    assert all(step["run_s"] is None for step in skipped)


def test_size_override_and_explicit_size_labels():
    data = jobs("cancelled")
    assumed = stats.build_report("OWNER/REPO", data, size="standard", price_per_vcpu_min=0.01)
    assert assumed["jobs"][0]["vcpus"] == 4
    assert assumed["summary"]["estimated_cost"] == pytest.approx(74 / 60 * 4 * 0.01)
    data[0]["labels"].append("sbx-standard")
    labelled = stats.build_report("OWNER/REPO", data)
    assert labelled["jobs"][0]["size"] == "standard"
    assert labelled["jobs"][0]["size_source"] == "label"
    assert labelled["summary"]["size_assumed_jobs"] == 0


def test_conflicting_size_labels_are_unknown_not_a_silent_guess():
    data = jobs("cancelled")
    data[0]["labels"] += ["sbx-small", "sbx-standard"]
    report = stats.build_report("OWNER/REPO", data)
    assert report["jobs"][0]["size"] is None
    assert report["summary"]["cost_samples"] == 0
    assert report["summary"]["vcpu_minutes"] is None


@pytest.mark.parametrize("field,value", [
    ("created_at", None), ("created_at", "invalid"),
    ("started_at", None), ("started_at", "0001-01-01T00:00:00Z"),
    ("started_at", "2026-10-14T03:15:00Z"),
])
def test_missing_or_reversed_timestamps_are_unknown(field, value):
    data = jobs("cancelled")
    data[0][field] = value
    report = stats.build_report("OWNER/REPO", data)
    assert report["jobs"][0]["wait_s"] is None
    assert report["summary"]["wait_s"] == {"samples": 0, "median": None, "p95": None}


def test_in_progress_job_has_wait_but_no_completed_runtime_or_cost():
    data = jobs("cancelled")
    data[0].update(status="in_progress", conclusion=None, completed_at=None)
    report = stats.build_report("OWNER/REPO", data)
    assert report["jobs"][0]["wait_s"] == 2
    assert report["jobs"][0]["run_s"] is None
    assert report["summary"]["incomplete"] == 1
    assert report["summary"]["estimated_cost"] is None


def test_prefix_is_authority_and_other_self_hosted_jobs_are_not_github_hosted():
    data = jobs("cancelled")
    other = copy.deepcopy(data[0])
    other.update(id=2, runner_name="other-runner", labels=["self-hosted", "sbx"])
    unassigned = copy.deepcopy(data[0])
    unassigned.update(id=3, runner_name="", status="queued", started_at=None, completed_at=None)
    report = stats.build_report("OWNER/REPO", data + [other, unassigned])
    assert [job["id"] for job in report["jobs"]] == [1]
    assert report["github_hosted"]["jobs"] == []
    data[0]["runner_name"] = "custom-123"
    assert len(stats.build_report("OWNER/REPO", data, prefix="custom-")["jobs"]) == 1


def test_comparison_never_pairs_separate_runs_or_attempts():
    data = jobs()
    for job in data:
        if job["runner_name"].startswith("GitHub Actions"):
            job["run_id"] = 2
    assert stats.build_report("OWNER/REPO", data)["comparisons"] == []
    for job in data:
        if job["runner_name"].startswith("GitHub Actions"):
            job.update(run_id=1, run_attempt=15)
    assert stats.build_report("OWNER/REPO", data)["comparisons"] == []


def test_log_join_uses_real_serve_events_and_only_successful_kills():
    data = jobs("cancelled")
    start = stats.timestamp(data[0]["started_at"])
    end = stats.timestamp(data[0]["completed_at"])
    runner = data[0]["runner_name"]
    events = [
        {"event": "spawn", "runner": runner, "t": start - 4},
        {"event": "sandbox", "runner": runner, "t": start - 3},
        {"event": "online", "runner": runner, "t": start - 1},
        {"event": "kill_failed", "runner": runner, "t": end + 1},
        {"event": "killed", "runner": runner, "t": end + 45},
        {"event": "killed", "runner": "unrelated", "t": end + 100},
    ]
    report = stats.build_report("OWNER/REPO", data, events=events)
    life = report["jobs"][0]["lifecycle"]
    assert life["vm_ready_s"] == 1
    assert life["runner_online_s"] == 3
    assert life["queue_to_vm_ready_s"] == 0  # already warm
    assert life["reclaim_s"] == 45
    assert report["summary"]["reclaim_s"] == {"samples": 1, "median": 45, "p95": 45}
    assert stats.build_report("OWNER/REPO", data, events=events[:-2])["jobs"][0]["lifecycle"]["reclaim_s"] is None


def test_partial_and_old_lifecycle_events_do_not_claim_reclaim():
    data = jobs("cancelled")
    runner = data[0]["runner_name"]
    end = stats.timestamp(data[0]["completed_at"])
    events = [{"event": "killed", "runner": runner, "t": end - 100},
              {"event": "online", "runner": runner, "t": float("nan")}]
    life = stats.build_report("OWNER/REPO", data, events=events)["jobs"][0]["lifecycle"]
    assert life["reclaim_s"] is None
    assert life["vm_ready_s"] is None


def test_summary_p95_is_nearest_rank_and_empty_report_is_explicit():
    report = stats.build_report("OWNER/REPO", [])
    assert report["summary"]["jobs"] == 0
    assert report["summary"]["run_s"] == {"samples": 0, "median": None, "p95": None}
    assert report["summary"]["estimated_cost"] is None
    assert stats.distribution(list(range(1, 21))) == {"samples": 20, "median": 10.5, "p95": 19}


def test_core_does_not_mutate_recorded_inputs():
    data = jobs()
    original = copy.deepcopy(data)
    stats.build_report("OWNER/REPO", data)
    assert data == original


def api_client(handler):
    return runners.GitHub("<FAKE>", "repos/OWNER/REPO", httpx.Client(
        base_url=runners.GITHUB_API, transport=httpx.MockTransport(handler),
    ))


def mock_recorded_api(monkeypatch, name="mixed"):
    data, requests = recording(name), []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/jobs"):
            assert f"/attempts/{data['run']['run_attempt']}/jobs" in request.url.path
            return httpx.Response(200, json=data["jobs_pages"][int(request.url.params["page"]) - 1])
        if request.url.path.endswith("/runs"):
            return httpx.Response(200, json={"total_count": 1, "workflow_runs": [data["run"]]})
        return httpx.Response(200, json=data["run"])

    gh = api_client(handler)
    monkeypatch.setenv("GH_TOKEN", "<FAKE>")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.delenv("SBX_API_KEY", raising=False)
    monkeypatch.setattr(runners, "GitHub", lambda *a, **k: gh)
    return requests, gh


def test_cli_json_uses_recorded_pagination_and_needs_no_sandbox_key(monkeypatch, capsys):
    requests, gh = mock_recorded_api(monkeypatch)
    assert cli.main(["runners", "stats", "--repo", "OWNER/REPO", "--run", "1", "--json"]) == 0
    out = capsys.readouterr()
    report = json.loads(out.out)
    assert report["summary"]["jobs"] == 9
    assert report["selection"] == {"run": 1, "since": None, "attempts": "latest"}
    assert [r.url.params["page"] for r in requests[1:]] == ["1", "2", "3", "4"]
    assert all(r.method == "GET" for r in requests)
    assert gh.http.is_closed
    assert out.err == ""


@pytest.mark.parametrize("duration", [None, "30m", "24h", "7d"])
def test_cli_since_queries_a_bounded_creation_window(duration, monkeypatch, capsys):
    from datetime import datetime

    requests, _ = mock_recorded_api(monkeypatch)
    argv = ["runners", "stats", "--repo", "OWNER/REPO", "--json"]
    if duration:
        argv += ["--since", duration]
    assert cli.main(argv) == 0
    report = json.loads(capsys.readouterr().out)
    start, end = requests[0].url.params["created"].split("..")
    seconds = (datetime.fromisoformat(end.replace("Z", "+00:00")) -
               datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()
    assert seconds == {None: 86400, "30m": 1800, "24h": 86400, "7d": 604800}[duration]
    assert report["selection"]["since"] == start


def test_runs_api_paginates_and_reports_search_cap():
    data = recording()
    pages = []

    def handler(request):
        pages.append(int(request.url.params["page"]))
        return httpx.Response(200, json={"total_count": 2, "workflow_runs": [data["run"]]})

    gh = api_client(handler)
    assert len(gh.workflow_runs("OWNER/REPO", "start", "end")) == 2
    assert pages == [1, 2]
    gh.http.close()
    with api_client(lambda r: httpx.Response(200, json={
        "total_count": 1001, "workflow_runs": [],
    })).http as http:
        gh = runners.GitHub("<FAKE>", "repos/OWNER/REPO", http)
        with pytest.raises(cli.SbxError, match="narrow --since"):
            gh.workflow_runs("OWNER/REPO", "start", "end")


@pytest.mark.parametrize("kind", ["runs", "jobs"])
def test_empty_api_page_cannot_look_like_complete_results(kind):
    key = "workflow_runs" if kind == "runs" else "jobs"
    gh = api_client(lambda r: httpx.Response(200, json={"total_count": 1, key: []}))
    with pytest.raises(cli.SbxError, match="incomplete"):
        if kind == "runs":
            gh.workflow_runs("OWNER/REPO", "start", "end")
        else:
            gh.jobs("OWNER/REPO", 1, 16)
    gh.http.close()


@pytest.mark.parametrize("options", [
    ["--repo", "bad"], ["--repo", "OWNER/REPO", "--run", "0"],
    ["--repo", "OWNER/REPO", "--prefix", " "],
    ["--repo", "OWNER/REPO", "--since", "yesterday"],
    ["--repo", "OWNER/REPO", "--since", "0h"],
    ["--repo", "OWNER/REPO", "--since", "999999d"],
    ["--repo", "OWNER/REPO", "--price-per-vcpu-min", "nan"],
    ["--repo", "OWNER/REPO", "--price-per-vcpu-min", "inf"],
    ["--repo", "OWNER/REPO", "--price-per-vcpu-min", "-0.1"],
])
def test_invalid_flags_fail_before_auth_or_network(options, monkeypatch, capsys):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert cli.main(["runners", "stats", *options]) == 2
    assert "no GitHub token" not in capsys.readouterr().err


def test_run_and_since_are_mutually_exclusive():
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["runners", "stats", "--repo", "OWNER/REPO",
                                      "--run", "1", "--since", "24h"])
    assert exc.value.code == 2


def test_missing_token_requests_only_read_access(monkeypatch, capsys):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert cli.main(["runners", "stats", "--repo", "OWNER/REPO", "--run", "1"]) == 2
    assert "Actions read access" in capsys.readouterr().err


def test_cli_serve_log_joins_actual_emit_schema(monkeypatch, capsys, tmp_path):
    mock_recorded_api(monkeypatch, "cancelled")
    job = jobs("cancelled")[0]
    start, end = stats.timestamp(job["started_at"]), stats.timestamp(job["completed_at"])
    for event, time in (("spawn", start - 4), ("sandbox", start - 3),
                        ("online", start - 1), ("killed", end + 45)):
        monkeypatch.setattr(runners.time, "time", lambda time=time: time)
        runners.emit(event, runner=job["runner_name"])
    log = tmp_path / "serve.jsonl"
    log.write_text(capsys.readouterr().out)
    assert cli.main(["runners", "stats", "--repo", "OWNER/REPO", "--run", "1",
                     "--serve-log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "small*\t2\t74\t1\t45" in out
    assert "step 2 Step 2: 71s (cancelled)" in out
    assert "1 jobs, 0 failures, 1 cancelled" in out


@pytest.mark.parametrize("content", ["not json", "[]", '{"event":\n'])
def test_bad_serve_logs_are_usage_errors_without_echoing_content(content, capsys, tmp_path):
    log = tmp_path / "serve.jsonl"
    log.write_text(content)
    assert cli.main(["runners", "stats", "--repo", "OWNER/REPO", "--serve-log", str(log)]) == 2
    assert "invalid JSONL at line 1" in capsys.readouterr().err


def test_missing_serve_log_does_not_echo_path(capsys, tmp_path):
    assert cli.main(["runners", "stats", "--repo", "OWNER/REPO",
                     "--serve-log", str(tmp_path / "missing")]) == 2
    err = capsys.readouterr().err
    assert "cannot read file" in err
    assert str(tmp_path) not in err


def test_api_error_closes_client_and_redacts_credentials(monkeypatch, capsys):
    monkeypatch.setenv("GH_TOKEN", "<FAKE>")
    gh = api_client(lambda r: httpx.Response(403, text="denied <FAKE>"))
    monkeypatch.setattr(runners, "GitHub", lambda *a, **k: gh)
    assert cli.main(["runners", "stats", "--repo", "OWNER/REPO", "--run", "1"]) == 2
    err = capsys.readouterr().err
    assert "HTTP 403" in err and "<FAKE>" not in err
    assert gh.http.is_closed
