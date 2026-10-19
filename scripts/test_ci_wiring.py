"""The ci workflow must select PR tests, not run the whole suite serially.

Pins the wiring, not the tools (scripts/test_ci_tools.py pins those): the cli
job computes the affected tests on pull_request and fails safe to ALL, runs
only those files through run_parallel.py, keeps the full suite for pushes to
main and the schedules, and passes the selection through the TESTS
environment variable -- never inline in run:, where a file name could be
evaluated as shell code. Text assertions over ci.yml, no network.
Run with pytest scripts or python3 -m unittest scripts.test_ci_wiring.
"""

import re
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
WEEKLY_CRON = "7 3 * * 1"


def job_block(text, name):
    """The `  <name>:` ... block, up to the next top-level two-space key."""
    match = re.search(rf"(?m)^  {name}:\n", text)
    if match is None:
        raise AssertionError(f"ci.yml has no {name} job")
    rest = text[match.end():]
    return rest[: re.search(r"(?m)^  \w", rest).start()]


def step_block(job, anchor):
    """The step containing `anchor` (a `- name:`/`- uses:` line), indented block."""
    start = job.index("      - " + anchor)
    end = re.search(r"(?m)^      - ", job[start + 7:])
    return job[start: start + 7 + end.start()] if end else job[start:]


class CliJobWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.job = job_block(cls.text, "cli")

    def test_prs_select_the_tests_the_change_can_reach(self):
        select = step_block(self.job, "name: Select tests")
        self.assertIn("id: select", select)
        self.assertIn('"$GITHUB_EVENT_NAME" = pull_request', select)
        self.assertIn(
            "python3 scripts/ci/affected.py --base HEAD^1 --format args", select
        )
        # a selector failure (or a non-PR event) must fall back to ALL, so a
        # broken selector can never turn into "no tests"
        self.assertIn('T=$(python3 scripts/ci/affected.py', select)
        self.assertIn('echo "tests=ALL" >> "$GITHUB_OUTPUT"', select)

    def test_selection_reaches_pytest_through_the_env_only(self):
        test_step = step_block(self.job, "name: Test")
        self.assertIn("working-directory: cli", test_step)
        self.assertIn("TESTS: ${{ steps.select.outputs.tests }}", test_step)
        run = test_step[test_step.index("run: |"):]
        self.assertNotIn("${{", run, "inline expressions must not shape the command")
        self.assertNotIn("eval", run, "file names must never run as shell source")

    def test_selected_and_full_runs_both_go_through_run_parallel(self):
        run = step_block(self.job, "name: Test")
        self.assertEqual(
            run.count("run_parallel.py --runner pytest"), 2,
            "the ALL run and the selected run must both use the parallel runner",
        )
        self.assertIn("--runner pytest ALL", run)
        self.assertIn('case $t in\n                  cli/*) selected="$selected ${t#cli/}"',
                      run, "only cli-suite files are passed, repo paths cut to cli's cwd")

    def test_no_step_still_runs_the_whole_suite_serially(self):
        self.assertNotIn("run: pytest -q\n", self.job,
                         "the cli job must not run pytest over its whole tree")

    def test_pr_diff_needs_the_merge_parent(self):
        checkout = step_block(self.job, "uses: actions/checkout@v4")
        self.assertIn("fetch-depth: 2", checkout,
                      "HEAD^1 of the PR merge commit must be fetched for the diff")

    def test_main_pushes_and_schedules_run_everything(self):
        push = re.search(r"(?ms)^on:.*?^jobs:", self.text).group()
        self.assertIn("branches: [main]", push,
                      "branch pushes must not re-run the full suite on top of the PR run")
        crons = re.findall(r'- cron: "([^"]+)"', push)
        self.assertIn(WEEKLY_CRON, crons)
        self.assertTrue(any(c != WEEKLY_CRON and c.endswith("* * *") for c in crons),
                        "a nightly schedule must run the full suite")


class ContractCadenceTests(unittest.TestCase):
    def test_live_check_stays_weekly_under_the_nightly_schedule(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        contract = job_block(text, "contract")
        guard = re.search(r"(?m)^    if: (.+)$", contract)
        self.assertIsNotNone(guard, "the contract job needs a schedule guard")
        self.assertIn("github.event_name != 'schedule'", guard.group(1))
        self.assertIn(f"github.event.schedule == '{WEEKLY_CRON}'", guard.group(1))


if __name__ == "__main__":
    unittest.main()
