#!/usr/bin/env bash
# git-lost-branch: recreate the deleted branch at its reflog tip and
# reattach HEAD to it.
#
# The branch ref is gone but its commit is still reachable from the reflog,
# so nothing has to be guessed: read the tip out of the reflog, point a
# branch at it, and check that branch out.  The commit is then verified to
# descend from main, so a wrong sha fails here instead of in the verifier.
set -euo pipefail

WORK="${WORK:?WORK must point at the task work directory}"
REPO="$WORK/repo"
BRANCH="feature/ingest"

cd "$REPO"

# the reflog for the branch records its last value before deletion; take the
# newest entry that is a real commit object
tip=""
for cand in $(git reflog --all --format='%H' 2>/dev/null | awk '!seen[$0]++'); do
    if git cat-file -e "${cand}^{commit}" 2>/dev/null; then
        tip="$cand"
        break
    fi
done
if [ -z "$tip" ]; then
    echo "git-lost-branch: no reflog entry resolves to a commit" >&2
    exit 1
fi

# prefer the tip that actually carries the branch's work, so we never
# resurrect an unrelated commit that happens to be newer in the reflog
for cand in $(git reflog --all --format='%H' | awk '!seen[$0]++'); do
    if git cat-file -e "${cand}^{commit}" 2>/dev/null &&
       git ls-tree -r --name-only "$cand" | grep -qx 'src/ingest.py'; then
        tip="$cand"
        break
    fi
done

if ! git merge-base --is-ancestor "$(git rev-parse main)" "$tip"; then
    echo "git-lost-branch: $tip does not descend from main" >&2
    exit 1
fi

git checkout -q -B "$BRANCH" "$tip"
git status --porcelain | grep -q . && {
    echo "git-lost-branch: working tree is dirty after checkout" >&2
    exit 1
}
echo "git-lost-branch: $BRANCH restored at $(git rev-parse --short HEAD), "\
"HEAD -> $(git symbolic-ref --short HEAD)"
