# Task: restore the lost branch

`work/repo` is a git repository that was left in a detached-HEAD state
during a migration. The branch `feature/ingest` was deleted, but its tip
commit is still reachable through the reflog — no data is actually gone.

Restore the repository so that:

- `HEAD` is a symbolic reference to the branch `feature/ingest`
  (not a detached HEAD);
- `feature/ingest` points at the commit that was its tip before deletion;
- the working tree is clean (`git status --porcelain` prints nothing) and
  matches that commit exactly;
- no commit is lost and no new commit is created.

Verify with `bash verify.sh "$PWD/work"` (from this directory). It exits 0
only when the branch, its tip and the working tree are all correct.
