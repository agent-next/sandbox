# Agent routing

This file routes; it holds no rules. Before a job, read the file named for it.
Before merging anything, read `docs/acceptance.md`. `CLAUDE.md` is just
`@AGENTS.md` and `@LESSONS.md`.

| Job | Read first | Commands |
| --- | --- | --- |
| CLI: `cli/`, its tests | `cli/README.md` | from the repo root: `pip install "./cli[test]"`, then in `cli/`: `pytest -q` (what CI runs) |
| Plugins: `plugins/`, `.claude-plugin/`, `.agents/` | `plugins/sandbox/README.md`, then `plugins/sandbox/skills/sandbox/SKILL.md` | the `manifests` job in `.github/workflows/ci.yml` (JSON validity, marketplace path, required fields) |
| Cookbook: `cookbook/` | `cookbook/DEMO-STANDARD.md`, then the demo's `README.md` and `SPEC.md` | run the demo's `run.py` end-to-end in a real sandbox; regenerate media with `media/make_media.sh` |
| CI: `.github/workflows/ci.yml` | the file itself | its two jobs: `cli` (Python 3.10 + 3.13 matrix) and `manifests` |
| Reviewing or merging a PR | `docs/acceptance.md`, then `LESSONS.md` | `gh pr merge <N> --squash --match-head-commit <reviewed sha>` |
| Recording what went wrong | `LESSONS.md` | the nightly review: `.claude/skills/nightly-review/SKILL.md` |
