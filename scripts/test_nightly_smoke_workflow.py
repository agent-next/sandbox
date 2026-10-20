"""The nightly smoke workflow's issue lifecycle (.github/workflows/nightly-smoke.yml).

Each test runs a step's real `run:` script under bash with a fake `gh` on
PATH that records its arguments, so the oracle is what the step would ask
GitHub to do: comment on the one open failure issue or open it, and close it
on recovery. The step gates are pinned too: only a scheduled failure files an
issue, and only a passing run closes one.
"""
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/nightly-smoke.yml"
CONTEXT = {
    "github.repository": "agent-next/sandbox",
    "github.run_id": "4242",
    "github.server_url": "https://github.com",
    "secrets.GITHUB_TOKEN": "fake-token",
}


def step(name):
    """The `if:` condition and the `run:` script of the step called `name`."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"      - name: {name}")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("      - ")),
               len(lines))
    block = lines[start:end]
    cond = next((l.split("if:", 1)[1].strip() for l in block if l.startswith("        if:")), None)
    run_at = block.index("        run: |")
    script = "\n".join(l[10:] for l in block[run_at + 1:])
    script = re.sub(r"\$\{\{\s*([\w.]+)\s*\}\}", lambda m: CONTEXT[m.group(1)], script)
    return cond, script


def run_step(tmp_path, name, existing):
    """Run the step's script with a fake gh whose `issue list` answers `existing`."""
    log = tmp_path / "gh.log"
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir()
    gh.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$GH_LOG"\n'
                  'if [ "$1 $2" = "issue list" ]; then printf "%s\\n" "$FAKE_EXISTING"; fi\n')
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PATH=f"{gh.parent}:{os.environ['PATH']}", GH_LOG=str(log),
               FAKE_EXISTING=existing, ref="v0.0.4")
    _, script = step(name)
    result = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines() if log.exists() else []
    return [c for c in calls if not c.startswith("issue list")]


def test_failure_issue_is_filed_only_for_a_scheduled_failure():
    cond, _ = step("Open or update failure issue")
    assert cond == "failure() && github.event_name == 'schedule'"


def test_failure_issue_is_closed_only_on_success():
    cond, _ = step("Close failure issue on recovery")
    assert cond == "success()"


def test_failure_comments_on_the_open_issue(tmp_path):
    calls = run_step(tmp_path, "Open or update failure issue", existing="17")
    assert len(calls) == 1
    assert calls[0].startswith("issue comment 17 --repo agent-next/sandbox --body ")
    assert "v0.0.4" in calls[0] and "/actions/runs/4242" in calls[0]


def test_failure_opens_one_issue_when_none_is_open(tmp_path):
    calls = run_step(tmp_path, "Open or update failure issue", existing="")
    assert len(calls) == 1
    assert calls[0].startswith("issue create --repo agent-next/sandbox --title nightly smoke failed")


@pytest.mark.parametrize("existing, expected", [("17", 1), ("", 0)])
def test_recovery_closes_the_open_issue_only(tmp_path, existing, expected):
    calls = run_step(tmp_path, "Close failure issue on recovery", existing=existing)
    assert len(calls) == expected
    if expected:
        assert calls[0].startswith("issue close 17 --repo agent-next/sandbox --comment ")
