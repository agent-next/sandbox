# Releasing

Releases are GitHub releases only (tags `v0.0.N`; the CLI is not on PyPI).
Patch versions only (`0.0.x`) unless the maintainers approve a minor bump.

## The flow

1. **Bump PR.** Open a PR that bumps the three version strings —
   `cli/pyproject.toml`, `plugins/sandbox/.claude-plugin/plugin.json`,
   `plugins/sandbox/.codex-plugin/plugin.json` — with
   `python3 scripts/bump_version.py X.Y.Z`, which also scaffolds
   `docs/releases/vX.Y.Z.md` in the same PR; fill it in before merging. The
   notes follow the template below; the release workflow publishes the
   release from this file.
2. **Merge** the PR.
3. **Tag** `vX.Y.Z` at the merge commit.
4. **Release workflow** (`.github/workflows/release.yml`) checks the versions
   and the notes file (`bump_version.py --check --tag` fails a tag whose
   `docs/releases/vX.Y.Z.md` is missing), installs from the tag, runs the
   tests, and publishes the release from the notes file.
5. **Smoke test.** Run `python3 scripts/release_smoke.py --ref vX.Y.Z` (with a key in
   the environment; add `--gpu` for GPU changes) and attach its verdict to the
   release.

## Notes template

Match the existing notes in `docs/releases/`:

```markdown
One-paragraph summary of what this release is for.

## What is new

- **Thing**: what changed and why (#PR).

## Install

(claude plugin marketplace add / install, pip install from the tag, PATH note,
SBX_API_KEY / E2B_API_KEY, E2B SDK snippet — copy from the previous notes and
update the tag.)

## Known limits

(copy from the previous notes; remove what this release fixed, add anything
new.)
```

`CHANGELOG.md` is generated from the notes files (headings plus the
"What is new" bullets); regenerate it when you add a version.
