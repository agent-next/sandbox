"""Exercise CI's actual detector shell over local Git diffs, without network.

The tiny condition reader supports only the literal terms used by these steps;
it does not emulate GitHub Actions. No script under test or live check is run.
Run with pytest scripts or python -m unittest discover -s scripts -p this file.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
LIVE_CONDITION = (
    "github.event_name != 'pull_request' || steps.docs.outputs.changed == 'true'"
)


def _step(lines: list[str], heading: str) -> list[str]:
    start = lines.index("      - " + heading)
    end = start + 1
    while end < len(lines) and lines[end].startswith("        "):
        end += 1
    return lines[start:end]


def _condition(step: list[str]) -> str:
    return next(line.strip()[4:] for line in step if line.strip().startswith("if: "))


def _selected(condition: str, event: str, outputs: dict[str, str]) -> bool:
    terms = []
    for term in condition.split(" || "):
        if term == "github.event_name != 'pull_request'":
            terms.append(event != "pull_request")
        else:
            match = re.fullmatch(r"steps\.docs\.outputs\.(\w+) == 'true'", term)
            if match is None:
                raise AssertionError(f"Unsupported workflow condition: {term}")
            terms.append(outputs.get(match[1]) == "true")
    return any(terms)


class ScriptsSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        # Restrict the uses-heading search to the contract job's Python setup.
        lines = workflow.split("  contract:\n", 1)[1].splitlines()
        detector = _step(lines, "name: Detect contract changes")
        if "        id: docs" not in detector or _condition(detector) != (
            "github.event_name == 'pull_request'"
        ):
            raise AssertionError("The detector must expose docs outputs on PRs")
        run = detector.index("        run: |")
        shell = textwrap.dedent("\n".join(detector[run + 1:])) + "\n"
        if shell.count("${{ github.base_ref }}") < 1:
            raise AssertionError("The detector must compare against the PR base")
        cls.shell = shell.replace("${{ github.base_ref }}", "fixture-base")
        setup = _step(lines, "uses: actions/setup-python@v5")
        unit = _step(lines, "name: Unit tests (no network)")
        live = _step(lines, "name: Contract check on this tree")
        cls.conditions = tuple(_condition(step) for step in (setup, unit, live))
        if _condition(live) != LIVE_CONDITION:
            raise AssertionError("Offline script coverage must not broaden live checks")
        if "          pytest -q -s scripts" not in unit:
            raise AssertionError("The unit step must collect the scripts directory")

    def decisions(self, before, after, event="pull_request"):
        with tempfile.TemporaryDirectory(prefix="ci-scripts-selection-") as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(root),
                "LC_ALL": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_AUTHOR_NAME": "CI fixture",
                "GIT_AUTHOR_EMAIL": "fixture@localhost",
                "GIT_COMMITTER_NAME": "CI fixture",
                "GIT_COMMITTER_EMAIL": "fixture@localhost",
            }

            def git(*args):
                return subprocess.run(
                    ["git", "-c", f"core.hooksPath={os.devnull}", *args],
                    cwd=repo, env=env, check=True, capture_output=True,
                    text=True, timeout=5,
                ).stdout.strip()

            def write(files):
                for name, content in files.items():
                    path = repo / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")

            git("init", "-b", "fixture-head")
            write({".fixture": "Local path-selection fixture only.\n", **before})
            git("add", ".")
            git("commit", "-m", "fixture base")
            git("update-ref", "refs/remotes/origin/fixture-base", "HEAD")
            for name in before.keys() - after.keys():
                (repo / name).unlink()
            write(after)
            git("add", "--all")
            git("commit", "--allow-empty", "-m", "fixture head")
            changed = git("diff", "--name-status", "origin/fixture-base...")
            output = root / "github-output"
            output.touch()
            if event == "pull_request":
                env["GITHUB_OUTPUT"] = str(output)
                result = subprocess.run(
                    ["bash", "--noprofile", "--norc", "-e", "-c", self.shell],
                    cwd=repo, env=env, capture_output=True, text=True, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "", "Git errors must not look like no changes")
            outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
            decisions = tuple(_selected(c, event, outputs) for c in self.conditions)
            return decisions, f"changed={changed!r}; outputs={outputs!r}"

    def assert_decisions(self, before, after, expected, event="pull_request"):
        decisions, detail = self.decisions(before, after, event)
        self.assertEqual(decisions, expected, detail + "; order=setup, unit, live")

    def test_bump_source_selects_offline_tests(self):
        path = "scripts/bump_version.py"
        self.assert_decisions({path: "old\n"}, {path: "new\n"}, (True, True, False))

    def test_new_followup_test_selects_offline_tests(self):
        self.assert_decisions({}, {"scripts/test_bump_version_followups.py": "new\n"},
                              (True, True, False))

    def test_actual_pr130_paths_select_offline_tests(self):
        self.assert_decisions({"scripts/bump_version.py": "old\n"}, {
            "scripts/bump_version.py": "new\n",
            "scripts/test_bump_version_followups.py": "new test\n",
        }, (True, True, False))

    def test_this_new_regression_selects_itself(self):
        self.assert_decisions({}, {"scripts/test_ci_scripts_selection.py": "new\n"},
                              (True, True, False))

    def test_deleted_script_selects_offline_tests(self):
        self.assert_decisions({"scripts/bump_version.py": "old\n"}, {},
                              (True, True, False))

    def test_script_renames_select_offline_tests(self):
        for old, new in (
            ("scripts/old.py", "scripts/new.py"),
            ("scripts/old.py", "tools/old.py"),
            ("tools/old.py", "scripts/old.py"),
        ):
            with self.subTest(old=old, new=new):
                self.assert_decisions({old: "same\n"}, {new: "same\n"},
                                      (True, True, False))

    def test_future_nested_script_selects_offline_tests(self):
        self.assert_decisions({}, {"scripts/nested/new.py": "new\n"},
                              (True, True, False))

    def test_existing_live_triggers_are_preserved(self):
        for path in ("README.md", "docs/example.md", "scripts/contract_check.py",
                     "scripts/test_contract_check.py", ".github/workflows/ci.yml"):
            with self.subTest(path=path):
                self.assert_decisions({path: "old\n"}, {path: "new\n"},
                                      (True, True, True))

    def test_unrelated_paths_are_not_selected(self):
        for path in ("cli/src/sbx/main.py", "assets/example.txt", "docs/example.txt",
                     "other/scripts/new.py", "scripts-other/new.py"):
            with self.subTest(path=path):
                self.assert_decisions({}, {path: "new\n"}, (False, False, False))

    def test_empty_diff_is_not_selected(self):
        self.assert_decisions({}, {}, (False, False, False))

    def test_push_and_schedule_are_unconditional(self):
        for event in ("push", "schedule"):
            with self.subTest(event=event):
                self.assert_decisions({}, {}, (True, True, True), event=event)


if __name__ == "__main__":
    unittest.main()
