# Task: untangle the symlink maze

`work/links/current` is a dangling symlink (it points at a release that was
never published) and `work/links/loop` points at itself, so anything that
walks the tree hangs or fails.

Repair the tree so that:

- `links/current` resolves to the release named in `work/RELEASE.txt`,
  as a **relative** symlink whose target is `releases/<version>` (so the
  link survives the tree being moved);
- `links/current/payload/data.txt` exists and its contents are unchanged;
- `links/loop` no longer exists as a symlink cycle — remove it, or point
  it somewhere that resolves;
- `RELEASE.txt` is unchanged, and every file under `releases/` is
  unchanged.

Verify with `bash verify.sh "$PWD/work"` (from this directory).
