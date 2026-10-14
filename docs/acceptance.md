# Acceptance rules

Every merge to `main` must show all four checks below in a PR comment that
names the reviewed head commit sha. A check that wasn't run is listed as
"Not run" — never left out.

## 1. A test that fails without the change

For any behavior change: put the old code back, the new test must FAIL on an
assertion naming the behavior. A compile/import error or a skip doesn't
count. Docs-only changes say how the doc was checked (read against the code
it describes, manifest check, link check, etc.).

## 2. The repo's CI commands, run on the change merged onto current origin/main

Copied from `.github/workflows/ci.yml`:

- `cli` job (matrix Python 3.10, 3.13): `pip install "./cli[test]"`, then
  `pytest -q` with working-directory `cli`.
- `manifests` job: for every `git ls-files '*.json'`, `python -m json.tool
  "$f"` must pass; the marketplace plugin path check (the source in
  `.claude-plugin/marketplace.json` must be a directory containing
  `.claude-plugin`); the plugin manifest required-fields check (the Python
  heredoc in the job: `marketplace.json` has `name`; each marketplace plugin
  entry has `name`, `source`, `description`; `plugins/sandbox/.claude-plugin/plugin.json`
  has `name`, `description`, `version`; `plugins/sandbox/.codex-plugin/plugin.json`
  has `name`, `version`; `.agents/plugins/marketplace.json` has `name`).

## 3. Real use

A CLI/plugin change is exercised against a real sandbox the way a user would;
if that isn't possible, say so and don't tell users it works. A cookbook demo
is actually run end-to-end (`run.py`), with the receipt attached.

## 4. Merge only the reviewed head

After a PR comment listing Run / Not run at that sha:

    gh pr merge <N> --squash --match-head-commit <reviewed sha>

## Moved from LESSONS.md

| Rule | What a reviewer looks at | Evidence |
| --- | --- | --- |
| A behavior change ships a test that fails without the change | The PR contains a test; reverting the source (not the test) makes it fail on an assertion naming the behavior | 60b2634 (#3), 9c9a8e5 (#6), d5fc63a (#9), 1a793d8 (#8) — seen on 3 distinct days |
